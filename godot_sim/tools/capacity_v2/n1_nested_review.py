"""Two-station topology review only. Never rewrite N1/D2 or deformation inputs."""
from n1_analysis import *
from audit_tissue_cavity import contact_pairs
OUT=PROJECT/'deformation/capacity_v2_n1_nested_review_v1'
TARGETS=['B_27:25','B_30:4']

def protect(initialize=False):
    OUT.mkdir(parents=True,exist_ok=True);path=OUT/'protected_before.json'
    if initialize and not path.exists():
        names=subprocess.check_output(['git','ls-files','-z'],cwd=REPO).decode('utf8').split('\0')
        paths={REPO/n for n in names if n and (REPO/n).is_file() and OUT not in (REPO/n).parents}
        for base in [PROJECT/'deformation',PROJECT/'analysis/irrigation_baseline',REPO/'docs',PROJECT/'scripts']:
            paths.update(p for p in base.rglob('*') if p.is_file() and OUT not in p.parents and '__pycache__' not in p.parts and p.suffix not in ['.translation'])
        write_json(path,{p.relative_to(REPO).as_posix():sha(p) for p in sorted(paths)})
    before=read_json(path);changed=[p for p,h in before.items() if not (REPO/p).is_file() or sha(REPO/p)!=h]
    write_json(OUT/'protected_after.json',{'files':len(before),'changed':changed})
    if changed:raise ValueError('Protected source/history changed: '+str(changed))
    verify_sources();return len(before)

def winding(v,f,point):
    x=v[f]-point;l=np.linalg.norm(x,axis=2)
    num=np.einsum('ij,ij->i',x[:,0],np.cross(x[:,1],x[:,2]))
    den=l.prod(1)+np.einsum('ij,ij->i',x[:,0],x[:,1])*l[:,2]+np.einsum('ij,ij->i',x[:,1],x[:,2])*l[:,0]+np.einsum('ij,ij->i',x[:,2],x[:,0])*l[:,1]
    return float(math.fsum((2*np.arctan2(num,den)).tolist())/(4*math.pi))

def point_inside(xy,p):
    a=xy-p;b=np.roll(a,-1,axis=0);mask=(a[:,1]>0)!=(b[:,1]>0)
    return bool(np.sum(a[mask,0]-a[mask,1]*(b[mask,0]-a[mask,0])/(b[mask,1]-a[mask,1])>0)%2)

def loop_info(row,loop,k,analyzer):
    points=np.array(loop['ring_positions_mm']);center=np.array(row['position_mm']);n=np.array(row['plane_normal_unit']);basis=np.array(row['plane_basis_unit'])
    xy=(points-center)@basis.T;area=float(np.sum(xy[:,0]*np.roll(xy[:,1],-1)-xy[:,1]*np.roll(xy[:,0],-1))/2)
    ids=np.array(loop['segments_D2_face_ids']);tri=analyzer.v[analyzer.f[ids]]
    normals=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);normals/=np.linalg.norm(normals,axis=1)[:,None]
    tangent=np.roll(points,-1,axis=0)-points;cosine=np.einsum('ij,ij->i',tangent,np.cross(n,normals))/np.linalg.norm(tangent,axis=1)
    sign=1 if np.all(cosine>0) else -1 if np.all(cosine<0) else 0
    mesh_signed_area=area*sign if sign else None
    # An ear triangle provides an actual interior point even when polygon centroid lies outside.
    triangles=triangulate_ring(list(range(len(xy))),xy)
    u=xy[triangles[:,1]]-xy[triangles[:,0]];w=xy[triangles[:,2]]-xy[triangles[:,0]];areas=np.abs(u[:,0]*w[:,1]-u[:,1]*w[:,0])
    seed=xy[triangles[np.argmax(areas)]].mean(0);probe=center+seed@basis
    landmarks=sorted([(name,float(np.linalg.norm(points.mean(0)-node['position_mm']))) for name,node in analyzer.resolved['nodes'].items() if name.startswith(('J_','T_','P_'))],key=lambda x:x[1])[:4]
    return {'loop_id':k,'signed_area_in_saved_order_mm2':area,'absolute_area_mm2':abs(area),
       'mesh_outward_oriented_signed_area_mm2':mesh_signed_area,'orientation_relative_plane_normal':'CCW_DOMAIN_LEFT' if mesh_signed_area and mesh_signed_area>0 else 'CW_DOMAIN_LEFT' if mesh_signed_area else 'INCONSISTENT',
       'segment_orientation_cosine_min_max':[float(cosine.min()),float(cosine.max())],
       'plane_center_mm':center.tolist(),'plane_normal_unit':n.tolist(),'ring_positions_mm':points.tolist(),'ring_in_plane_mm':xy.tolist(),
       'ring_D2_edge_vertex_ids_and_t':loop['ring_D2_edge_vertex_ids_and_t'],
       'D2_face_ids':ids.tolist(),'source_face_ids':loop['segments_source_face_ids'],
       'source_face_ids_unique':sorted(set(i for i in loop['segments_source_face_ids'] if i>=0)),
       'path_boundary_votes':loop['path_owner_boundary_length_fractions'],
       'contains_path_station':loop['contains_station'],'virtual_cap_segments':loop['virtual_cap_segments'],
       'nearest_landmarks_mm_LOCALIZATION_ONLY':landmarks,
       'interior_probe_mm':probe.tolist(),'interior_probe_winding':winding(analyzer.v,analyzer.f,probe),
       'bounds_mm':[points.min(0).tolist(),points.max(0).tolist()],
       'plane_max_residual_mm':float(abs((points-center)@n).max())}

def preliminary():
    protect(True);a=SectionAnalyzer();data=json.loads(gzip.decompress((ROOT/'sections.json.gz').read_bytes()));byid={r['id']:r for r in data['stations']}
    for name in TARGETS:
        row=byid[name];infos=[loop_info(row,loop,k,a) for k,loop in enumerate(row['loops'])]
        print(name,'s',row['station_arc_mm'],'center',row['position_mm'],'outer',row['selected_loop'])
        for info in infos:
            print('loop',info['loop_id'],'area',info['absolute_area_mm2'],'oriented',info['mesh_outward_oriented_signed_area_mm2'],'windingprobe',info['interior_probe_winding'],'votes',info['path_boundary_votes'],'faces',len(info['source_face_ids_unique']))
        write_json(OUT/(name.replace(':','_')+'_loops.json'),{'station':{k:row[k] for k in ['id','path_id','station_arc_mm','position_mm','plane_normal_unit','plane_basis_unit','status','selected_loop','nested_loop_ids']},'loops':infos})

def ring_relation(a,b):
    x=np.array(a['ring_in_plane_mm']);y=np.array(b['ring_in_plane_mm']);xx=np.roll(x,-1,axis=0);yy=np.roll(y,-1,axis=0)
    cross=lambda u,v:u[...,0]*v[...,1]-u[...,1]*v[...,0]
    u=cross((xx-x)[:,None,:],y[None,:,:]-x[:,None,:]);w=cross((xx-x)[:,None,:],yy[None,:,:]-x[:,None,:])
    q=cross((yy-y)[None,:,:],x[:,None,:]-y[None,:,:]);r=cross((yy-y)[None,:,:],xx[:,None,:]-y[None,:,:])
    crossings=int(((u*w<0)&(q*r<0)).sum())
    def distances(points,start,end):
        edge=end-start;delta=points[:,None,:]-start[None,:,:]
        t=np.clip(np.einsum('ijk,jk->ij',delta,edge)/np.sum(edge*edge,axis=1),0,1)
        return np.linalg.norm(delta-t[:,:,None]*edge[None,:,:],axis=2)
    gap=min(float(distances(x,y,yy).min()),float(distances(y,x,xx).min()))
    inside=[point_inside(x,p) for p in y]
    return {'first_loop':a['loop_id'],'second_loop':b['loop_id'],'second_all_vertices_inside_first':bool(all(inside)),
            'second_any_vertices_inside_first':bool(any(inside)),'finite_boundary_crossings':crossings,
            'minimum_boundary_distance_mm':0. if crossings else gap}

def interior_probes(info,a,center,normal,basis):
    xy=np.array(info['ring_in_plane_mm']);tri=triangulate_ring(list(range(len(xy))),xy)
    uv=xy[tri].mean(1);points=center+uv@basis
    values=[winding(a.v,a.f,p) for p in points]
    import open3d as o3d
    scene=ray_scene(a.v,a.f)
    signed=scene.compute_signed_distance(o3d.core.Tensor((points-ORIGIN).astype('float32')),nsamples=5).numpy()
    # Independent signed-angle integral is float64, not the ray parity implementation.
    return {'points_mm':points.tolist(),'D2_winding_float64':values,'D2_signed_distance_ray5_mm':signed.tolist(),
            'all_winding_outside':bool(np.max(abs(np.array(values)))<1e-8),
            'all_winding_inside':bool(np.max(abs(np.array(values)-1))<1e-8),
            'all_ray_outside':bool(np.min(signed)>1e-6),'all_ray_inside':bool(np.max(signed)<-1e-6),
            'minimum_absolute_distance_mm':float(abs(signed).min()),
            'scope':'One centroid for every nonoverlapping ear triangle. Finite disjoint loop arrangement plus oriented surface determines region winding; probes independently check that interpretation.'}

def local_crossings(a,ids):
    f=a.f[ids];pairs=contact_pairs(a.v,f,a.v,f);rows=[];feature_candidates=[]
    for i,j in pairs:
        if i>=j:continue
        ia,ib=int(ids[i]),int(ids[j]);shared=np.intersect1d(a.f[ia],a.f[ib]);ta,tb=a.v[a.f[ia]],a.v[a.f[ib]]
        seg=intersection_segment(ta,tb);area=coplanar_overlap_area(ta,tb)
        if len(shared)==1:
            p=a.v[shared[0]];ca=np.roll(ta,-int(np.where(a.f[ia]==shared[0])[0][0]),axis=0)-p;cb=np.roll(tb,-int(np.where(a.f[ib]==shared[0])[0][0]),axis=0)-p
            canonical=intersection_segment(ca,cb) # Same tolerance, exact common point as both plane origins.
            if seg is not None and canonical is None:
                feature_candidates.append({'source_face_pair':a.source[[ia,ib]].tolist(),'raw_positive_length_mm':float(np.linalg.norm(seg[1]-seg[0])),
                    'shared_source_vertex_id':int(shared[0]),'canonical_positive_segment':False,
                    'classification':'SHARED_VERTEX_POINT_CONTACT_NUMERICAL_PLANE_CANDIDATE',
                    'method':'Cyclic reorder and translate to actual shared vertex before independent finite clipping; epsilon unchanged at 1e-10 mm.'})
            seg=None if canonical is None else canonical+p
        legitimate=False
        if seg is not None and len(shared)==2:
            p,q=a.v[shared];edge=q-p;t=(seg-p)@edge/(edge@edge)
            legitimate=bool(np.linalg.norm(seg-(p+t[:,None]*edge),axis=1).max()<1e-8 and t.min()>=-1e-8 and t.max()<=1+1e-8)
        if area>1e-10 or (seg is not None and not legitimate):
            rows.append({'D2_face_pair':[ia,ib],'source_face_pair':a.source[[ia,ib]].tolist(),
                         'finite_length_mm':0. if seg is None else float(np.linalg.norm(seg[1]-seg[0])),
                         'coplanar_overlap_mm2':area,'shared_vertices':shared.tolist()})
    sensitivity={}
    for eps in [1e-12,1e-10,1e-8,1e-6]:
        nonadj=0
        for i,j in pairs:
            if i>=j or np.intersect1d(f[i],f[j]).size:continue
            if intersection_segment(a.v[f[i]],a.v[f[j]],epsilon=eps) is not None:nonadj+=1
        sensitivity[str(eps)]=nonadj
    return {'local_faces':len(ids),'broadphase_pairs_including_shared_features':len(pairs),'confirmed_invalid_pairs':rows,
            'shared_point_numerical_candidates':feature_candidates,
            'nonadjacent_positive_intersection_count_by_tolerance':sensitivity,
            'scope':'Only two-ring source neighborhoods and bridge; shared mesh edges/vertices are permitted. Not a global or continuous deformation collision certificate.'}

def build():
    protect(True);a=SectionAnalyzer();db=json.loads(gzip.decompress((ROOT/'sections.json.gz').read_bytes()));byid={r['id']:r for r in db['stations']}
    approval=read_json(ROOT/'D2_approval_2026_10_14_v1.json')
    feedback={'schema':'N1_HUMAN_REVIEW_V1','date':'2026-10-15','authority':'Direct user review feedback in current conversation',
       'N1_engineering_tools_and_existing_data_accepted':True,'reviewed_regions':['J_05','J_09','B_31','B_32'],
       'nested_closed_contours_visually_confirmed':TARGETS,'new_true_wall_crossing_confirmed_by_user':False,
       'outer_area_approved_as_effective_net_area':False,'candidate_regional_volumes_approved_as_final_anatomical_partition':False,
       'source_N1_report_sha256':sha(REPO/'docs/kidney_irrigation_capacity_v2_n1_result.md'),
       'source_N1_database_sha256':sha(ROOT/'sections.json.gz'),'D2_approval_sha256':sha(ROOT/'D2_approval_2026_10_14_v1.json'),
       'limits':'Engineering delivery accepted; no final anatomical partition or new morphology authorization.'}
    immutable(OUT/'human_review_2026_10_15_v1.json',feedback)
    mesh=trimesh.Trimesh(a.v,a.f,process=False);adj=mesh.face_adjacency
    graph=coo_matrix((np.ones(2*len(adj)),(np.r_[adj[:,0],adj[:,1]],np.r_[adj[:,1],adj[:,0]])),shape=(len(a.f),len(a.f))).tocsr()
    results=[]
    for name in TARGETS:
        row=byid[name];center=np.array(row['position_mm']);normal=np.array(row['plane_normal_unit']);basis=np.array(row['plane_basis_unit'])
        infos=[loop_info(row,loop,k,a) for k,loop in enumerate(row['loops'])]
        relationships=[ring_relation(x,y) for x in infos for y in infos if x['loop_id']!=y['loop_id']]
        inner_ids=row['nested_loop_ids'];outer_id=row['selected_loop'];outer=infos[outer_id]
        nesting=[];bridge_faces=set()
        for innerid in inner_ids:
            inner=infos[innerid];relation=next(x for x in relationships if x['first_loop']==outer_id and x['second_loop']==innerid)
            probes=interior_probes(inner,a,center,normal,basis)
            distances,pred,sources=dijkstra(graph,indices=np.array(inner['D2_face_ids']),min_only=True,unweighted=True,return_predecessors=True)
            target=min(outer['D2_face_ids'],key=lambda i:distances[i]);path=[int(target)]
            while pred[path[-1]]>=0:path.append(int(pred[path[-1]]))
            bridge_faces.update(path);signed=(a.v[a.f[path]].mean(1)-center)@normal
            nesting.append({'inner_loop':innerid,'outer_loop':outer_id,'relation':relation,'inner_probes':probes,
                'surface_shortest_face_chain_D2':path,'surface_shortest_face_chain_source':a.source[path].tolist(),
                'surface_face_graph_hops':float(distances[target]),'bridge_centroid_plane_distance_mm':signed.tolist(),
                'classification':'ORIENTED_D2_SLICE_EXTERIOR_POCKET_CONFIRMED' if inner['mesh_outward_oriented_signed_area_mm2']<0 and probes['all_winding_outside'] and probes['all_ray_outside'] and relation['second_all_vertices_inside_first'] and relation['minimum_boundary_distance_mm']>1e-8 else 'THREE_DIMENSIONAL_OWNERSHIP_UNRESOLVED',
                'anatomical_cause':'Neighboring connected branch/interface wall intersection creates an exterior pocket in this plane; exact anatomical branch ownership is not independently validated.'})
        inner_faces=set(i for k in inner_ids for i in infos[k]['D2_face_ids']);outer_faces=set(outer['D2_face_ids'])
        local=set(inner_faces)|set(outer_faces)|bridge_faces
        for _ in range(2):
            all_ids=np.array(sorted(local));local.update(graph[all_ids].indices.tolist())
        groups={'outer_source_faces':sorted(outer_faces),'inner_source_faces':sorted(inner_faces),
                'off_plane_bridge':sorted(bridge_faces-outer_faces-inner_faces),
                'local_neighbor_faces':sorted(local-outer_faces-inner_faces-bridge_faces),
                'context':np.flatnonzero((a.source>=0)&~np.isin(np.arange(len(a.f)),list(local))).tolist()}
        contacts=local_crossings(a,np.array(sorted(local)))
        neighbors=[];path=a.by_id[row['path_id']]
        for offset in [-.5,-.25,-.1,-.075,-.05,-.025,0,.025,.05,.075,.1,.25,.5]:
            for kind in ['FIXED_NORMAL_PARALLEL','ALONG_PATH_LOCAL_NORMAL']:
                s=row['station_arc_mm']+offset
                if not 0<s<path['length_mm']:continue
                if offset==0:
                    section=row # A zero-offset comparison must reuse the exact approved central plane, not recompute a chord.
                elif kind=='FIXED_NORMAL_PARALLEL':
                    # Reuse the exact section parser on a straight diagnostic path through the original plane normal.
                    synthetic={'id':path['id'],'points_mm':[(center-normal*2).tolist(),(center+normal*2).tolist()],'length_mm':4.}
                    section=a.section(synthetic,2+offset,0)
                else:section=a.section(path,s,0)
                child_infos=[loop_info(section,loop,k,a) for k,loop in enumerate(section['loops'])]
                for info in child_infos:
                    current=set(info['source_face_ids_unique'])
                    info['source_face_overlap_with_central_loops']={str(c['loop_id']):len(current&set(c['source_face_ids_unique'])) for c in infos}
                    # Two-hop source-face adjacency support; no nearest-centroid correspondence.
                    two=set(info['D2_face_ids'])
                    for _ in range(2):two.update(graph[np.array(sorted(two))].indices.tolist())
                    info['central_loop_two_hop_face_support']={str(c['loop_id']):len(two&set(c['D2_face_ids'])) for c in infos}
                neighbors.append({'id':kind+':'+str(offset),'kind':kind,'offset_mm':offset,
                    'station':{k:section[k] for k in ['position_mm','plane_normal_unit','plane_basis_unit','status','selected_loop']},
                    'loops':child_infos,'effective_branch_area_mm2':None})
        directory=OUT/name.replace(':','_');directory.mkdir(exist_ok=True)
        for key,ids in groups.items():
            save_npy(directory/(key+'_D2_ids.npy'),np.array(ids,dtype=np.int64))
            save_npy(directory/(key+'_source_ids.npy'),a.source[ids])
            binary_mesh(directory/(key+'.bin'),a.v,a.f[ids])
        result={'id':name,'station_arc_mm':row['station_arc_mm'],'position_mm':row['position_mm'],
             'plane_normal_unit':row['plane_normal_unit'],'plane_basis_unit':row['plane_basis_unit'],
             'status':'MULTIRING_WITH_HOLE_UNRESOLVED','effective_branch_area_mm2':None,'outer_minus_inner_area_computed':False,
             'classification':'D2_PLANAR_EXTERIOR_POCKET_FROM_CONNECTED_BRANCH_NEIGHBORHOOD; TARGET_BRANCH_NET_DOMAIN_UNRESOLVED',
             'limits':'Exterior side verified geometrically for this plane, not an anatomical wall perforation. Outer loop spans multiple paths; no approved exclusive branch net-section domain, so no area subtraction or promotion.',
             'loops':infos,'relationships':relationships,'nesting':nesting,'neighbors':neighbors,'local_finite_contacts':contacts,
             'mesh_groups':{key:{'file':name.replace(':','_')+'/'+key+'.bin','sha256':sha(directory/(key+'.bin')),'D2_faces':len(ids)} for key,ids in groups.items()},
             'source_face_map_sha256':sha(ROOT/'d2/source_face_ids.npy'),
             'source_vertex_stencil_sha256':{key:sha(ROOT/'d2'/key) for key in ['source_vertex_ids.npy','source_vertex_weights.npy']}}
        write_json(directory/'review.json',result);results.append(result)
        print(name,[(x['inner_loop'],x['classification'],x['surface_face_graph_hops']) for x in nesting],len(local),'local faces, confirmed invalid',len(contacts['confirmed_invalid_pairs']),flush=True)
    write_json(OUT/'review_data.json',{'schema':'N1_NESTED_RING_REVIEW_V1','V_reference_D2_mL':approval['V_reference_D2_mL'],
        'source_D2_hashes':approval['frozen_geometry_sha256'],'accepted_source_sha256':AUTHORITY,
        'cases':results,'normal_V_min_mL':None,'normal_V_max_mL':None,'N2_started':False})
    print('Protected unchanged',protect(),flush=True)

if __name__=='__main__':build()
