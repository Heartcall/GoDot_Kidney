"""Local plane splits and virtual caps, for anatomical review ONLY.

Every full-plane loop is inventoried; only the loop containing the selected
path station is used as a topological barrier. Other branches are not cropped.
"""
from n0_common import *
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree
from audit_tissue_cavity import contact_pairs,ray_scene
import open3d as o3d
from collections import Counter

def plane_basis(n):
    axis=np.eye(3)[np.argmin(np.abs(n))]
    e=np.cross(n,axis);e/=np.linalg.norm(e)
    return np.stack([e,np.cross(n,e)])

def polygon_info(xy):
    area=abs(float(np.sum(xy[:,0]*np.roll(xy[:,1],-1)-xy[:,1]*np.roll(xy[:,0],-1)))/2)
    try:triangulate_ring(list(range(len(xy))),xy);valid=True
    except ValueError:valid=False
    inside=False
    for a,b in zip(xy,np.roll(xy,-1,axis=0)):
        if (a[1]>0)!=(b[1]>0) and a[0]+(-a[1])/(b[1]-a[1])*(b[0]-a[0])>0:inside=not inside
    return area,valid,inside

def ordered_loops(edges):
    graph={}
    for a,b in edges:
        graph.setdefault(int(a),[]).append(int(b));graph.setdefault(int(b),[]).append(int(a))
    if any(len(v)!=2 for v in graph.values()):raise ValueError('Non-regular plane section: open loop or vertex tangency')
    loops=[];seen=set()
    for start in sorted(graph):
        if start in seen:continue
        ring=[start];previous=-1;current=start
        while True:
            nxt=next(x for x in graph[current] if x!=previous)
            if nxt==start:break
            if nxt in seen or nxt in ring:raise ValueError('Repeated plane-section vertex')
            ring.append(nxt);previous,current=current,nxt
        seen.update(ring);loops.append(ring)
    return loops

def local_cut(v,f,source,cap_label,weights,center,normal,end,port):
    dist=(v-center)@normal
    if np.any(np.abs(dist)<1e-10):raise ValueError('Plane coincides with existing vertex: choose a separately named offset candidate')
    crossing=np.flatnonzero((dist[f].min(1)<0)&(dist[f].max(1)>0))
    edge_to_id={};positions=[];pairs=[];face_nodes={};new_weights=[]
    for face_id in crossing:
        ids=f[face_id];nodes=[]
        for a,b in zip(ids,np.roll(ids,-1)):
            if dist[a]*dist[b]>=0:continue
            key=tuple(sorted([int(a),int(b)]))
            if key not in edge_to_id:
                t=dist[a]/(dist[a]-dist[b])
                edge_to_id[key]=len(v)+len(positions);positions.append(v[a]+t*(v[b]-v[a]))
                w={}
                for idx,coefficient in weights[a].items():w[idx]=w.get(idx,0)+(1-t)*coefficient
                for idx,coefficient in weights[b].items():w[idx]=w.get(idx,0)+t*coefficient
                new_weights.append(w)
            nodes.append(edge_to_id[key])
        if len(nodes)!=2:raise ValueError('Non-simple triangle/plane intersection')
        pairs.append(nodes);face_nodes[int(face_id)]=nodes
    if not pairs:raise ValueError('No section through source surface')
    full_v=np.vstack([v,positions]);basis=plane_basis(normal);loops=ordered_loops(pairs)
    loop_info=[];choices=[]
    for ring in loops:
        xy=(full_v[ring]-center)@basis.T;area,valid,inside=polygon_info(xy)
        contains=valid and inside
        loop_info.append({'intersection_node_ids':ring,'area_mm2':area,'simple':valid,'contains_path_station':contains})
        if contains:choices.append(ring)
    if len(choices)!=1:raise ValueError('Ambiguous path section: '+str(len(choices))+' containing loops')
    ring=choices[0];ring_set=set(ring)
    selected=[int(i) for i in crossing if set(face_nodes[int(i)]).issubset(ring_set)]
    if len(selected)!=len(ring):raise ValueError('Section ring/face correspondence not bijective')
    choose=np.zeros(len(f),bool);choose[selected]=True
    out_f=f[~choose].tolist();out_source=source[~choose].tolist();out_caps=cap_label[~choose].tolist()
    def clip(ids,sign):
        poly=[]
        for a,b in zip(ids,np.roll(ids,-1)):
            if sign*dist[a]>0:poly.append(int(a))
            if dist[a]*dist[b]<0:poly.append(edge_to_id[tuple(sorted([int(a),int(b)]))])
        return [[poly[0],poly[i],poly[i+1]] for i in range(1,len(poly)-1)]
    for face_id in selected:
        pieces=clip(f[face_id],1)+clip(f[face_id],-1)
        out_f.extend(pieces);out_source.extend([int(source[face_id])]*len(pieces));out_caps.extend([int(cap_label[face_id])]*len(pieces))
    ff=np.asarray(out_f,int);ss=np.asarray(out_source,int);cc=np.asarray(out_caps,int)
    edges=np.concatenate([ff[:,[0,1]],ff[:,[1,2]],ff[:,[2,0]]]);face_for_edge=np.tile(np.arange(len(ff)),3)
    se=np.sort(edges,axis=1);order=np.lexsort((se[:,1],se[:,0]));sort_edges=se[order]
    same=np.all(sort_edges[:-1]==sort_edges[1:],axis=1)
    barrier={tuple(sorted([a,b])) for a,b in zip(ring,np.roll(ring,-1))}
    locations=np.flatnonzero(same)
    locations=np.array([i for i in locations if tuple(sort_edges[i]) not in barrier],int)
    a,b=face_for_edge[order[locations]],face_for_edge[order[locations+1]]
    adjacency=coo_matrix((np.ones(2*len(a)),(np.r_[a,b],np.r_[b,a])),shape=(len(ff),len(ff))).tocsr()
    count,labels=connected_components(adjacency,directed=False)
    if count!=2:raise ValueError('Local cut creates '+str(count)+' components, expected exactly 2')
    nearest=cKDTree(full_v[ff].mean(1)).query(end,k=5)[1];distal=labels[nearest]
    if np.unique(distal).size!=1:raise ValueError('Artificial END has ambiguous component')
    keep=labels!=distal[0];removed_faces=ff[~keep];removed_source=ss[~keep]
    kept=ff[keep];ks=ss[keep];kc=cc[keep]
    ed=np.concatenate([kept[:,[0,1]],kept[:,[1,2]],kept[:,[2,0]]]);_,inv,num=np.unique(np.sort(ed,axis=1),axis=0,return_inverse=True,return_counts=True)
    boundary=ed[num[inv]==1]
    directed={int(a):int(b) for a,b in boundary};start=int(boundary.min());oriented=[start]
    if len(directed)!=len(boundary):raise ValueError('Non-manifold kept boundary')
    while directed[oriented[-1]]!=start:
        oriented.append(directed[oriented[-1]])
        if len(oriented)>len(boundary):raise ValueError('Unclosed retained boundary')
    if set(oriented)!=ring_set or len(oriented)!=len(boundary):raise ValueError('Extra retained boundary loops')
    cap=triangulate_ring(oriented,(full_v[oriented]-center)@basis.T)
    excluded_cap=cap[:,::-1]
    excluded=np.vstack([removed_faces,excluded_cap])
    closed=np.vstack([kept,cap]);new_source=np.r_[ks,np.full(len(cap),-1)];new_cap_label=np.r_[kc,np.full(len(cap),port)]
    info={'center_mm':center.tolist(),'normal_toward_artificial_END':normal.tolist(),'all_plane_loops':loop_info,
          'selected_boundary_vertex_ids':oriented,'split_source_face_ids':source[selected].tolist(),
          'removed_source_face_ids':sorted(set(removed_source[removed_source>=0].tolist())),
          'cap_face_ids_in_candidate':list(range(len(kept),len(closed))), 'cap_triangle_vertex_ids':cap.tolist(),
          'maximum_section_nonplanarity_mm':float(np.abs((full_v[oriented]-center)@normal).max()),
          'removed_volume_mL':signed_volume(full_v,excluded)/1000,
          'additivity_error_mm3':signed_volume(full_v,closed)+signed_volume(full_v,excluded)-signed_volume(v,f),
          'section_area_mm2':polygon_info((full_v[oriented]-center)@basis.T)[0],
          'local_barrier_method':'Split only faces of selected loop; flood to artificial END. Other global plane loops and branches are retained untouched.'}
    return full_v,closed,new_source,new_cap_label,weights+new_weights,info,removed_faces

def cap_validation(v,f,labels):
    cap=np.flatnonzero(labels>0);wall=np.flatnonzero(labels==0)
    pairs=contact_pairs(v,f[cap],v,f[wall]);records=[];bad=[]
    for i,j in pairs:
        ia,ib=int(cap[i]),int(wall[j]);a,b=v[f[ia]],v[f[ib]]
        segment=intersection_segment(a,b);overlap=coplanar_overlap_area(a,b)
        shared=np.intersect1d(f[ia],f[ib]);legitimate=False
        if segment is not None and len(shared)==2:
            x,y=v[shared];axis=y-x;length=np.linalg.norm(axis);axis/=length
            along=(segment-x)@axis;off=np.linalg.norm(segment-x-along[:,None]*axis,axis=1)
            legitimate=bool(np.max(off)<1e-8 and along.min()>=-1e-8 and along.max()<=length+1e-8)
        invalid=overlap>1e-10 or (segment is not None and not legitimate)
        row={'cap_face':ia,'wall_face':ib,'source_shared_vertex_ids':shared.tolist(),'finite_segment_mm':0. if segment is None else float(np.linalg.norm(segment[1]-segment[0])),
             'coplanar_overlap_mm2':overlap,'allowed_boundary_edge':legitimate,'invalid':bool(invalid)}
        records.append(row)
        if invalid:bad.append(row)
    # Each planar simple polygon was ear-clipped without overlaps; verify cap pairs independently too.
    self_pairs=contact_pairs(v,f[cap],v,f[cap]);cap_bad=[]
    for i,j in self_pairs:
        if i>=j:continue
        ia,ib=int(cap[i]),int(cap[j]);a,b=v[f[ia]],v[f[ib]]
        area=coplanar_overlap_area(a,b)
        segment=intersection_segment(a,b)
        if area>1e-10 or (labels[ia]!=labels[ib] and segment is not None):cap_bad.append([ia,ib])
    return {'candidate_wall_pairs':len(pairs),'cap_wall_invalid_count':len(bad),'cap_cap_invalid_pairs':cap_bad,'pairs':records,
            'tolerance_mm':1e-10,'method':'VTK finite candidate broad phase + finite plane-edge intersection + coplanar finite polygon overlap; actual shared cut boundary edges are allowed, overlapping area is not.'}

def cap_original_validation(v,f,labels,source_f,cuts):
    cap=np.flatnonzero(labels>0);pairs=contact_pairs(v,f[cap],v,source_f);rows=[];bad=[]
    for i,j in pairs:
        cap_id=int(cap[i]);source_id=int(j);cut=cuts[int(labels[cap_id])] if isinstance(cuts,dict) else cuts[int(labels[cap_id])-1]
        seg=intersection_segment(v[f[cap_id]],v[source_f[source_id]])
        area=coplanar_overlap_area(v[f[cap_id]],v[source_f[source_id]]);allowed=False
        if seg is not None and source_id in cut['split_source_face_ids']:
            ring=v[cut['selected_boundary_vertex_ids']];samples=np.vstack([seg,seg.mean(0)])
            closest=np.full(len(samples),np.inf)
            for x,y in zip(ring,np.roll(ring,-1,axis=0)):
                edge=y-x;t=np.clip((samples-x)@edge/(edge@edge),0,1);closest=np.minimum(closest,np.linalg.norm(samples-(x+t[:,None]*edge),axis=1))
            allowed=bool(closest.max()<1e-8)
        invalid=bool(area>1e-10 or (seg is not None and not allowed))
        row={'cap_face':cap_id,'original_source_face':source_id,'intended_section_ring_intersection':allowed,'coplanar_area_mm2':area,
             'finite_segment_mm':0. if seg is None else float(np.linalg.norm(seg[1]-seg[0])),'invalid':invalid}
        rows.append(row)
        if invalid:bad.append(row)
    return {'candidate_pairs':len(pairs),'invalid_count':len(bad),'pairs':rows,'scope':'All original walls, including excluded structures. Only the recorded selected-loop intersection in source split faces is allowed; other finite lines or overlapping areas are rejected.'}

def station(path,fraction):
    points=np.asarray(path['points_mm']);arc=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
    target=fraction*arc[-1];i=min(len(points)-2,int(np.searchsorted(arc,target,side='right')-1))
    t=(target-arc[i])/(arc[i+1]-arc[i]);return points[i]+t*(points[i+1]-points[i]),(points[i+1]-points[i])/np.linalg.norm(points[i+1]-points[i])

def build_candidate(name,fractions,offsets=None):
    _,a=verify_sources();v=a['cavity_reference_vertices'].copy();source_v=v.copy();f=a['cavity_faces'].copy()
    source=np.arange(len(f));labels=np.zeros(len(f),int);weights=[{i:1.} for i in range(len(v))]
    r=read_json(PROJECT/'deformation/cavity_topology_resolved.json');paths={p['id']:p for p in r['paths']}
    cuts=[];excluded=[];offsets=offsets or {}
    for index,(port,transition) in enumerate([('BLADDER','BLADDER_TRANSITION'),('IN_01','B_31'),('IN_02','B_32')],1):
        fraction=fractions[port]
        if fraction is None:
            path=paths[port];p,n=station(path,1./path['length_mm']);where='1 mm distal to artificial BASE; transition retained'
        else:
            # Fractions always run from natural-side marker towards artificial BASE.
            raw=1-fraction if port=='BLADDER' else fraction;p,n=station(paths[transition],raw);where=f'natural-to-BASE transition fraction {fraction}'
        end=np.asarray(paths[port]['points_mm'][-1]);n=n if (end-p)@n>0 else -n
        p=p+offsets.get(port,0)*n
        v,f,source,labels,weights,info,removed=local_cut(v,f,source,labels,weights,p,n,end,index)
        info.update({'port':port,'transition_path':transition,'station_definition':where,'offset_mm':offsets.get(port,0),'anatomical_status':'UNAPPROVED_GEOMETRIC_STATION_NOT_IDENTIFIED_UPJ_OR_ORIGINAL_WALL'})
        cuts.append(info);excluded.append(removed)
    directory=OUT/'domains'/name;directory.mkdir(parents=True,exist_ok=True)
    mesh=trimesh.Trimesh(v,f,process=False);ed=np.sort(mesh.edges,axis=1);_,counts=np.unique(ed,axis=0,return_counts=True)
    check=cap_validation(v,f,labels);original_check=cap_original_validation(v,f,labels,a['cavity_faces'],cuts)
    volume=signed_volume(v,f);origins=[np.zeros(3),v.mean(0),ORIGIN,np.array([1000.,-1000.,500.])]
    triangles=(v-v.mean(0))[f];norm2=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
    flux=[float(np.sum(triangles[:,:,axis].mean(1)*norm2[:,axis]/2)) for axis in range(3)]
    values=[signed_volume(v,f,o) for o in origins]+[float(mesh.volume)]+flux
    landmark_names=[name for name in r['nodes'] if name.startswith(('A_','J_','T_'))]
    landmarks=np.array([r['nodes'][name]['position_mm'] for name in landmark_names])
    distances=ray_scene(v,f).compute_signed_distance(o3d.core.Tensor((landmarks-ORIGIN).astype('float32')),nsamples=3).numpy()
    outside=[name for name,distance in zip(landmark_names,distances) if distance>1e-4]
    scene=ray_scene(v,f);natural=[]
    for path in r['paths']:
        if path['id']!='MAIN' and not (path['id'].startswith('B_') and int(path['id'][2:])<=30):continue
        pts=np.asarray(path['samples_mm']);gap=scene.compute_signed_distance(o3d.core.Tensor((pts-ORIGIN).astype('float32')),nsamples=3).numpy()
        natural.append({'id':path['id'],'samples':len(pts),'outside_count':int((gap>1e-4).sum()),'maximum_signed_distance_mm':float(gap.max())})
    outside_paths=[p['id'] for p in natural if p['outside_count']]
    kept_source=np.unique(source[source>=0]);removed=np.setdiff1d(np.arange(len(a['cavity_faces'])),kept_source)
    owner=np.load(PROJECT/'deformation/p1_masks/path_owner.npy');votes=Counter(r['paths'][int(i)]['id'] for i in owner[a['cavity_faces'][removed]].ravel())
    row={'id':name,'review_status':'PENDING_USER_ANATOMICAL_REVIEW','V_reference_effective_mL':None,
       'used_surface_bounds_mm':[v[np.unique(f)].min(0).tolist(),v[np.unique(f)].max(0).tolist()],
       'candidate_measurement_volume_mL':volume/1000,'removed_volume_mL':(signed_volume(source_v,a['cavity_faces'])-volume)/1000,
       'cuts':cuts,'topology':{'watertight':bool(mesh.is_watertight),'winding_consistent':bool(mesh.is_winding_consistent),
       'boundary_edges':int((counts==1).sum()),'nonmanifold_edges':int((counts>2).sum()),'degenerate_faces':int((mesh.area_faces<1e-10).sum()),
       'face_components':len(mesh.split(only_watertight=False))},'volume_checks':{'origin_values_mm3':values,'spread_mm3':float(np.ptp(values)),
       'sum_cut_additivity_error_mm3':float(sum(abs(c['additivity_error_mm3']) for c in cuts))},
       'landmark_signed_distances_mm':dict(zip(landmark_names,map(float,distances))),
       'excluded_natural_marker_ids':outside,'natural_path_samples':natural,'natural_paths_with_outside_samples':outside_paths,
       'anatomical_recommendation':'REJECT_FOR_NATURAL_DOMAIN_CONFIRMED_NATURAL_REGIONS_EXCLUDED' if outside or outside_paths else 'NEEDS_USER_REVIEW_NATURAL_CENTERLINES_RETAINED',
       'cap_checks':{k:value for k,value in check.items() if k!='pairs'},'fully_removed_source_faces':len(removed),
       'cap_against_all_original_walls':{k:value for k,value in original_check.items() if k!='pairs'},
       'removed_source_vertex_path_votes':dict(votes),'virtual_cap_triangles':int((labels>0).sum()),
       'source_hashes':AUTHORITY,'source_obj_sha256':sha(PROJECT/'source_assets/kidney_cavity.obj'),
       'limits':['Geometrically valid does not identify UPJ, original anatomy, or physiological capacity.','Terminal caps retain original unknown segmentation boundary.','Source vertices retained without moving; plane intersection vertices use saved source barycentric weights.']}
    row['geometry_valid']=bool(mesh.is_watertight and mesh.is_winding_consistent and row['topology']['degenerate_faces']==0 and row['topology']['face_components']==1 and not check['cap_wall_invalid_count'] and not check['cap_cap_invalid_pairs'] and not original_check['invalid_count'] and row['volume_checks']['spread_mm3']<3e-6)
    for key,arr in [('reference_vertices',v),('faces',f),('source_face_ids',source),('virtual_port_labels',labels),('fully_removed_source_faces',removed)]:save_npy(directory/(key+'.npy'),arr)
    wids=np.full((len(v),3),-1,int);wval=np.zeros((len(v),3))
    for i,w in enumerate(weights):
        if len(w)>3:raise ValueError('Unexpected material weight stencil')
        for j,(idx,value) in enumerate(w.items()):wids[i,j]=idx;wval[i,j]=value
    save_npy(directory/'source_vertex_ids.npy',wids);save_npy(directory/'source_vertex_weights.npy',wval)
    binary_mesh(directory/'original_wall.bin',v,f[labels==0]);binary_mesh(directory/'virtual_caps.bin',v,f[labels>0])
    binary_mesh(directory/'excluded_structure.bin',v,np.vstack(excluded))
    write_json(directory/'cap_contact_details.json',check)
    write_json(directory/'cap_original_contact_details.json',original_check)
    row['output_sha256']={p.name:sha(p) for p in sorted(directory.iterdir()) if p.is_file() and p.name!='candidate.json'}
    write_json(directory/'candidate.json',row)
    return row

def build():
    freeze();rows=[];failures=[]
    definitions=[('C00_distal_control',dict.fromkeys(['BLADDER','IN_01','IN_02'],None)),
       ('C01_transition_mid',dict.fromkeys(['BLADDER','IN_01','IN_02'],.5)),
       ('C02_transition_proximal',dict.fromkeys(['BLADDER','IN_01','IN_02'],.2)),
       ('C03_transition_distal',dict.fromkeys(['BLADDER','IN_01','IN_02'],.8)),
       ('C04_bladder_proximal',{'BLADDER':.2,'IN_01':.5,'IN_02':.5}),
       ('C05_bladder_distal',{'BLADDER':.8,'IN_01':.5,'IN_02':.5}),
       ('C06_near_BASE',{'BLADDER':.5,'IN_01':.98,'IN_02':.98}),
       ('C07_IN01_collar',{'BLADDER':.5,'IN_01':.95,'IN_02':.98}),
       ('C08_IN02_collar',{'BLADDER':.5,'IN_01':.98,'IN_02':.95}),
       ('C09_UPJ_proximal_unconfirmed',{'BLADDER':.2,'IN_01':.98,'IN_02':.98}),
       ('C10_UPJ_distal_unconfirmed',{'BLADDER':.8,'IN_01':.98,'IN_02':.98})]
    definitions.append(('C11_inlet_distal_control',{'BLADDER':.5,'IN_01':None,'IN_02':None}))
    for name,fractions in definitions:
        try:
            row=build_candidate(name,fractions);rows.append(row)
            print(name,row['candidate_measurement_volume_mL'],row['geometry_valid'],row['cap_checks'],flush=True)
        except ValueError as e:failures.append({'id':name,'status':'REJECTED','reason':str(e)});print(name,'REJECTED',e,flush=True)
    control=next(x for x in rows if x['id']=='C00_distal_control')
    control_areas={c['port']:c['section_area_mm2'] for c in control['cuts']}
    for row in rows:
        row['cap_area_vs_distal_control']={c['port']:c['section_area_mm2']/control_areas[c['port']] for c in row['cuts']}
        row['wide_chamber_cut_warning']=[port for port,ratio in row['cap_area_vs_distal_control'].items() if port.startswith('IN_') and ratio>3]
        row['full_natural_branch_wall_retention']='UNCONFIRMED_CENTERLINE_RETENTION_IS_NOT_WHOLE_SURFACE_CERTIFICATION'
        write_json(OUT/'domains'/row['id']/'candidate.json',row)
    volumes=[x['candidate_measurement_volume_mL'] for x in rows if x['geometry_valid']]
    report={'date':'2026-10-14','status':'UNAPPROVED_MEASUREMENT_CANDIDATES_ONLY','V_reference_effective_mL':None,
       'D0_volume_mL':signed_volume(*[verify_sources()[1][k] for k in ['cavity_reference_vertices','cavity_faces']])/1000,
       'candidates':rows,'rejected':failures,'section_choice_volume_range_mL':[min(volumes),max(volumes)],
       'section_choice_interpretation':'Named geometric boundary choices, NOT physiological uncertainty or an interval estimate for true capacity.',
       'previous_rejected_methods':'No centroid-fan closure or jagged fixed-mask cap is used. IN_01 earlier cap/index conflict remains rejected.',
       'scope':'Reference-only measurement geometry, never added to P2 runtime cavity.'}
    write_json(OUT/'domain_candidates.json',report);protected();return report

if __name__=='__main__':build()
