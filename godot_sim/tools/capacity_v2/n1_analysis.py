"""Capacity V2 N1: immutable approved D2, reference sections, candidate accounting.

No displacement solver and no writes to N0, original meshes, or P2 resources.
All lengths are mm, areas mm2, volumes mm3 internally (1000 mm3 = 1 mL).
"""
import os
for _key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[_key]='1'
from n0_common import *
from build_n0_domains import plane_basis, ordered_loops, polygon_info
from audit_tissue_cavity import ray_scene
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra, connected_components
from scipy.spatial import cKDTree
from collections import Counter
import argparse, csv, math, shutil, gzip

ROOT = PROJECT/'deformation/capacity_v2_n1_v1'
R1 = PROJECT/'deformation/capacity_v2_n0_closeout/domains/C11_R1_IN02_fixed_collar'
TOPOLOGY = PROJECT/'deformation/cavity_topology_resolved.json'

def protect(initialize=False):
    ROOT.mkdir(parents=True,exist_ok=True)
    target=ROOT/'protected_before.json'
    if initialize and not target.exists():
        names=subprocess.check_output(['git','ls-files','-z'],cwd=REPO).decode('utf8').split('\0')
        paths={REPO/n for n in names if n and (REPO/n).is_file() and ROOT not in (REPO/n).parents}
        for base in [PROJECT/'deformation',PROJECT/'analysis/irrigation_baseline',REPO/'docs',PROJECT/'scripts',PROJECT/'tools']:
            paths.update(p for p in base.rglob('*') if p.is_file() and ROOT not in p.parents
                         and '__pycache__' not in p.parts and not p.name.startswith(('n1_','test_n1','verify_n1'))
                         and p.suffix in ('.npy','.bin','.json','.md','.csv','.png','.log','.import','.gd','.py','.uid'))
        write_json(target,{p.relative_to(REPO).as_posix():sha(p) for p in sorted(paths)})
    before=read_json(target)
    changed=[p for p,h in before.items() if not (REPO/p).is_file() or sha(REPO/p)!=h]
    write_json(ROOT/'protected_after.json',{'files':len(before),'changed':changed})
    if changed:raise ValueError('Protected files changed: '+str(changed))
    verify_sources()
    return len(before)

def immutable(path,record):
    if path.exists():
        if read_json(path)!=record:raise ValueError('Versioned approval differs: create a new version')
    else:write_json(path,record)

def volume_review(v,f):
    origins=[np.zeros(3),v[np.unique(f)].mean(0),ORIGIN,np.array([1000.,-1000.,500.])]
    values=[signed_volume(v,f,o) for o in origins]
    mesh=trimesh.Trimesh(v,f,process=False)
    tri=(v-origins[1])[f];cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    flux=[float(math.fsum((tri[:,:,axis].mean(1)*cross[:,axis]/2).tolist())) for axis in range(3)]
    all_values=values+[float(mesh.volume)]+flux
    _,counts=np.unique(mesh.edges_sorted,axis=0,return_counts=True)
    result={'signed_tetrahedral_integrals_mm3':values,'origins_mm':[o.tolist() for o in origins],
            'trimesh_volume_mm3':float(mesh.volume),'axis_flux_integrals_mm3':flux,
            'V_reference_D2_mm3':values[1],'V_reference_D2_mL':values[1]/1000,
            'method_spread_mm3':float(np.ptp(all_values)),
            'watertight':bool(mesh.is_watertight),'winding_consistent':bool(mesh.is_winding_consistent),
            'boundary_edges':int((counts==1).sum()),'nonmanifold_edges':int((counts>2).sum()),
            'degenerate_faces':int((mesh.area_faces<1e-10).sum()),
            'units':'mm, mm2, mm3; 1000 mm3 = 1 mL',
            'limits':'Numerical consistency is not segmentation, anatomical or physiological calibration accuracy.'}
    if not mesh.is_watertight or not mesh.is_winding_consistent or result['degenerate_faces'] or result['method_spread_mm3']>=3e-6:
        raise ValueError('Approved D2 independent volume/topology gate failed')
    return result

def freeze_d2():
    protect(True);candidate=read_json(R1/'candidate.json')
    if not candidate['geometry_valid']:raise ValueError('R1 geometry failed')
    for name,h in candidate['output_sha256'].items():
        if sha(R1/name)!=h:raise ValueError('R1 evidence hash mismatch: '+name)
    v=np.load(R1/'reference_vertices.npy');f=np.load(R1/'faces.npy');review=volume_review(v,f)
    directory=ROOT/'d2';directory.mkdir(exist_ok=True)
    for name in ['reference_vertices.npy','faces.npy','source_face_ids.npy','source_vertex_ids.npy','source_vertex_weights.npy','virtual_port_labels.npy','original_wall.bin','virtual_caps.bin','excluded_structure.bin']:
        target=directory/name
        if target.exists() and sha(target)!=sha(R1/name):raise ValueError('Frozen D2 copy changed')
        if not target.exists():shutil.copyfile(R1/name,target)
    boundaries=[]
    for cut in candidate['cuts']:
        boundaries.append({key:cut[key] for key in ['port','center_mm','normal_toward_artificial_END','selected_boundary_vertex_ids','split_source_face_ids','cap_face_ids_in_candidate','cap_triangle_vertex_ids','section_area_mm2']})
        boundaries[-1]['ring_positions_mm']=v[cut['selected_boundary_vertex_ids']].tolist()
    record={'schema':'CAPACITY_V2_D2_PROJECT_APPROVAL_V1','version':'2026-10-14-v1','date':'2026-10-14',
            'authority':'Direct explicit user approval of R1 and project measurement boundary in current conversation',
            'status':'USER_APPROVED_PROJECT_GEOMETRIC_MEASUREMENT_DOMAIN','domain_id':candidate['id'],
            'N0_closed':True,'D2_project_definition_approved':True,'independent_medical_anatomy_validation':False,
            'V_reference_D2_mm3':review['V_reference_D2_mm3'],'V_reference_D2_mL':review['V_reference_D2_mL'],
            'units':'Source RAS mesh coordinates, mm; 1000 mm3 = 1 mL; display subtracts [16,16,-81] mm only',
            'scope':{'BLADDER':'Use approved R1 cut; chamber-side space included, distal artificial extension excluded.',
                     'B_31_B_32':'Retained spaces connected to natural chambers included; no unapproved root removal.',
                     'IN_01_IN_02':'Use R1 cuts and excluded structures; do not restore C06 natural-wall loss.',
                     'T_01_T_22':'Existing closed reconstruction terminal surfaces and enclosed spaces included.',
                     'junctions':'Single oriented closed D2 boundary integral; no repeated junction or cap volume.',
                     'virtual_caps':'Measurement integral only, never inserted into P2 cavity, tissue or collision meshes.'},
            'virtual_caps':boundaries,'source_candidate_sha256':sha(R1/'candidate.json'),
            'frozen_geometry_sha256':{p.name:sha(p) for p in sorted(directory.iterdir()) if p.is_file()},
            'accepted_source_sha256':AUTHORITY,'source_obj_sha256':sha(PROJECT/'source_assets/kidney_cavity.obj'),
            'topology_sha256':sha(TOPOLOGY),
            'source_mapping':'source_face_ids.npy: -1 virtual caps; source_vertex_ids/weights: original CT vertex barycentric stencil.',
            'normal_V_min_mL':None,'normal_V_max_mL':None,'pressure_or_compliance':None,
            'limits':['User-approved engineering measurement range, not independently medically validated physiological boundaries.',
                      'BLADDER and terminal closures retain existing model conventions.',
                      'Reference is intermediate, not zero volume or guaranteed 50% capacity.',
                      'Reference volume alone cannot determine normal endpoints, pressure, or compliance.']}
    immutable(ROOT/'D2_approval_2026_10_14_v1.json',record)
    write_json(ROOT/'D2_independent_volume.json',review)
    return record

def path_station(path,s):
    p=np.asarray(path['points_mm']);arc=np.r_[0,np.cumsum(np.linalg.norm(np.diff(p,axis=0),axis=1))]
    s=float(np.clip(s,0,arc[-1]));i=min(len(p)-2,max(0,int(np.searchsorted(arc,s,side='right')-1)))
    t=(s-arc[i])/(arc[i+1]-arc[i]);return p[i]+t*(p[i+1]-p[i])

def path_tangent(path,s):
    # Symmetric 0.25 mm chord smooths control-point tangent discontinuities without moving the path.
    a=path_station(path,max(0,s-.25));b=path_station(path,min(path['length_mm'],s+.25))
    return (b-a)/np.linalg.norm(b-a)

def section_metrics(xy):
    x,y=xy.T;xx,yy=np.roll(x,-1),np.roll(y,-1);c=x*yy-xx*y
    signed=c.sum()/2;area=abs(float(signed))
    centroid=np.array([np.sum((x+xx)*c),np.sum((y+yy)*c)])/(6*signed)
    exx=np.sum((x*x+x*xx+xx*xx)*c)/(12*signed)
    eyy=np.sum((y*y+y*yy+yy*yy)*c)/(12*signed)
    exy=np.sum((2*x*y+x*yy+xx*y+2*xx*yy)*c)/(24*signed)
    covariance=np.array([[exx,exy],[exy,eyy]])-np.outer(centroid,centroid)
    eig,axes=np.linalg.eigh(covariance)
    if eig.min()<=0:raise ValueError('Non-positive section area inertia')
    minor,major=4*np.sqrt(eig)
    return {'area_mm2':area,'perimeter_mm':float(np.linalg.norm(np.roll(xy,-1,axis=0)-xy,axis=1).sum()),
            'equivalent_radius_mm':math.sqrt(area/math.pi),'major_axis_mm':float(major),'minor_axis_mm':float(minor),
            'flattening_1_minus_minor_major':float(1-minor/major),'elongation_major_minor':float(major/minor),
            'area_centroid_in_plane_mm':centroid.tolist(),'major_axis_in_plane_unit':axes[:,1].tolist(),
            'axes_definition':'Diameters of area-second-moment equivalent ellipse, not bounding-box or fitted clinical diameters.'}

def section_polygon_info(xy):
    """Vectorized finite 2D segment simplicity, no triangulation needed for measurements."""
    a=xy;b=np.roll(a,-1,axis=0);n=len(a)
    cross=lambda u,v:u[...,0]*v[...,1]-u[...,1]*v[...,0]
    d=b-a;u=cross(d[:,None,:],a[None,:,:]-a[:,None,:]);w=cross(d[:,None,:],b[None,:,:]-a[:,None,:])
    adjacency=np.eye(n,dtype=bool)|np.eye(n,k=1,dtype=bool)|np.eye(n,k=-1,dtype=bool)
    adjacency[0,-1]=adjacency[-1,0]=True
    proper=(u*w<0)&(u.T*w.T<0)
    boxes=(np.minimum(a,b)[:,None,:]<=np.maximum(a,b)[None,:,:]+1e-12).all(2)&(np.maximum(a,b)[:,None,:]>=np.minimum(a,b)[None,:,:]-1e-12).all(2)
    touch=((np.abs(u)<1e-12)|(np.abs(w)<1e-12)|(np.abs(u.T)<1e-12)|(np.abs(w.T)<1e-12))&boxes
    simple=not np.any((proper|touch)&~adjacency)
    # Touch is conservative: orientation zero must also put the relevant endpoint on the finite edge.
    if not simple and not np.any(proper&~adjacency):
        pairs=np.argwhere(touch&~adjacency);simple=True
        for i,j in pairs:
            def on(x,y,p):return abs(cross(y-x,p-x))<1e-12 and np.all(p>=np.minimum(x,y)-1e-12) and np.all(p<=np.maximum(x,y)+1e-12)
            if on(a[i],b[i],a[j]) or on(a[i],b[i],b[j]) or on(a[j],b[j],a[i]) or on(a[j],b[j],b[i]):simple=False;break
    area=abs(float(cross(a,b).sum()/2))
    test=(a[:,1]>0)!=(b[:,1]>0);intersections=a[test,0]-a[test,1]*(b[test,0]-a[test,0])/(b[test,1]-a[test,1])
    inside=bool(np.sum(intersections>0)%2)
    return area,bool(simple and area>1e-12),inside

class SectionAnalyzer:
    def __init__(self):
        self.v=np.load(ROOT/'d2/reference_vertices.npy');self.f=np.load(ROOT/'d2/faces.npy')
        self.source=np.load(ROOT/'d2/source_face_ids.npy');self.wids=np.load(ROOT/'d2/source_vertex_ids.npy');self.w=np.load(ROOT/'d2/source_vertex_weights.npy')
        self.resolved=read_json(TOPOLOGY);self.paths=self.resolved['paths'];self.by_id={p['id']:p for p in self.paths}
        self.owner=np.load(PROJECT/'deformation/p1_masks/path_owner.npy')
        self.edges=np.unique(np.sort(np.concatenate([self.f[:,[0,1]],self.f[:,[1,2]],self.f[:,[2,0]]]),axis=1),axis=0)
        self.edge_index={tuple(e):i for i,e in enumerate(self.edges)}
        self.neighbors={p['id']:{q['id'] for q in self.paths if set([p['marker_names'][0],p['marker_names'][-1]])&set([q['marker_names'][0],q['marker_names'][-1]])} for p in self.paths}

    def section(self,path,s,index):
        center=path_station(path,s);normal=path_tangent(path,s);basis=plane_basis(normal)
        row={'id':path['id']+':'+str(index),'path_id':path['id'],'station_arc_mm':float(s),'path_fraction':float(s/path['length_mm']),
             'position_mm':center.tolist(),'tangent_unit':normal.tolist(),'plane_normal_unit':normal.tolist(),
             'plane_basis_unit':basis.tolist(),'normal_method':'symmetric 0.25mm path chord; exact source polyline position',
             'status':'NO_CONTAINING_RING','metrics':None,'candidate_metrics':None,'selected_loop':None,'loops':[],
             'anatomical_semantics':'UNCONFIRMED; path ID is topology, not a clinical pelvis/calyx label.'}
        dist=(self.v-center)@normal
        if np.any(np.abs(dist[np.unique(self.f)])<1e-10):
            row['status']='VERTEX_TANGENCY_UNRESOLVED';return row
        crossing=np.flatnonzero((dist[self.f].min(1)<0)&(dist[self.f].max(1)>0))
        if not len(crossing):return row
        nodes={};positions=[];stencils=[];pairs=[];face_by_edge={}
        for fid in crossing:
            two=[]
            for a,b in zip(self.f[fid],np.roll(self.f[fid],-1)):
                if dist[a]*dist[b]>=0:continue
                edge=tuple(sorted([int(a),int(b)]))
                if edge not in nodes:
                    a,b=edge;t=dist[a]/(dist[a]-dist[b]);nodes[edge]=len(positions)
                    positions.append(self.v[a]+t*(self.v[b]-self.v[a]));stencils.append([a,b,float(t)])
                two.append(nodes[edge])
            if len(two)!=2:row['status']='NONREGULAR_TRIANGLE_SECTION';return row
            pairs.append(two);face_by_edge[tuple(sorted(two))]=int(fid)
        try:loops=ordered_loops(pairs)
        except ValueError as e:row['status']='OPEN_OR_NONMANIFOLD_SECTION';row['reason']=str(e);return row
        positions=np.asarray(positions);containing=[]
        for k,ring in enumerate(loops):
            pts=positions[ring];xy=(pts-center)@basis.T;area,simple,inside=section_polygon_info(xy)
            faceids=[face_by_edge[tuple(sorted([a,b]))] for a,b in zip(ring,np.roll(ring,-1))]
            source=self.source[faceids];lengths=np.linalg.norm(np.roll(pts,-1,axis=0)-pts,axis=1)
            votes=Counter()
            for fid,length in zip(faceids,lengths):
                for vid in self.f[fid]:
                    for original,w in zip(self.wids[vid],self.w[vid]):
                        if original>=0 and w>0:votes[self.paths[int(self.owner[original])]['id']]+=float(length*w/3)
            total=sum(votes.values());fractions={name:value/total for name,value in votes.items()}
            record={'ring_positions_mm':pts.tolist(),'segments_D2_face_ids':faceids,'segments_source_face_ids':source.tolist(),
                    'ring_D2_edge_vertex_ids_and_t':[stencils[i] for i in ring],
                    'simple':simple,'contains_station':inside,'area_mm2':area,'path_owner_boundary_length_fractions':fractions,
                    'virtual_cap_segments':int((source<0).sum()),
                    'boundary_mapping':'Each edge endpoint maps through frozen D2 source_vertex_ids/weights; source face for each ordered segment retained.'}
            row['loops'].append(record)
            if simple and inside:containing.append(k)
        if len(containing)!=1:
            row['status']='NESTED_OR_AMBIGUOUS_CONTAINING_LOOPS' if containing else 'NO_CONTAINING_RING';return row
        k=containing[0];selected=row['loops'][k];row['selected_loop']=k
        xy=(np.asarray(selected['ring_positions_mm'])-center)@basis.T
        try:metrics=section_metrics(xy)
        except ValueError:row['status']='INVALID_AREA_INERTIA';return row
        row['candidate_metrics']=metrics
        def contains_point(polygon,point):
            a=polygon-point;b=np.roll(a,-1,axis=0);test=(a[:,1]>0)!=(b[:,1]>0)
            return bool(np.sum(a[test,0]-a[test,1]*(b[test,0]-a[test,0])/(b[test,1]-a[test,1])>0)%2)
        nested=[j for j,loop in enumerate(row['loops']) if j!=k and loop['simple']
                and contains_point(xy,(np.array(loop['ring_positions_mm'][0])-center)@basis.T)]
        if nested:
            row['status']='MULTIRING_WITH_HOLE_UNRESOLVED';row['nested_loop_ids']=nested;return row
        votes=selected['path_owner_boundary_length_fractions'];own=votes.get(path['id'],0.)
        incompatible=sum(value for name,value in votes.items() if name not in self.neighbors[path['id']])
        row['topology_decision']={'own_path_fraction':own,'nonadjacent_path_fraction':incompatible,
                                  'compatible_paths':sorted(self.neighbors[path['id']]),
                                  'rule':'Unique simple ring containing station AND existing source ownership adjacency. No nearest/largest-loop fallback.'}
        if incompatible>.10 or own<.10:
            row['status']='AMBIGUOUS_TOPOLOGY';return row
        if own<.70 or selected['virtual_cap_segments']:
            row['status']='SHARED_JUNCTION_OR_INTERFACE_SECTION'
        else:row['status']='PATH_LOCAL_SECTION'
        row['metrics']=metrics
        return row

def sections_build():
    analyzer=SectionAnalyzer();records=[];summaries=[];anomalies=[]
    paths=[p for p in analyzer.paths if p['id'] not in ['BLADDER','IN_01','IN_02']]
    # Retained fixed-port collars are measured separately; excluded distal tubes are never sampled as D2 branches.
    for p in analyzer.paths:
        if p['id'] in ['IN_01','IN_02']:
            q=dict(p);q['length_mm']=1.0 if p['id']=='IN_01' else .8574169157387342
            paths.append(q)
    for path in paths:
        name=path['id'];length=path['length_mm'];high=name in ['B_11','B_27','B_31','B_32'] or (name.startswith('B_') and (12<=int(name[2:])<=18 or 28<=int(name[2:])<=30))
        step=.5 if high else 1.
        samples=np.unique(np.r_[np.arange(.1,length,step),[x for x in [.25,.5,1,2,length-2,length-1,length-.5,length-.25,length-.1] if 0<x<length]])
        local=[analyzer.section(path,float(s),i) for i,s in enumerate(samples)]
        if name=='BLADDER_TRANSITION':
            for row in local:
                if row['station_arc_mm']<length*.5:
                    row['status']='OUTSIDE_APPROVED_D2_CUTOFF';row['metrics']=None
                    row['reason']='Distal half of original BLADDER transition is excluded by user-approved R1 boundary; not a new geometry failure.'
        records.extend(local)
        good=[r for r in local if r['metrics'] is not None];core=[r for r in good if r['status']=='PATH_LOCAL_SECTION']
        points=np.asarray(path['points_mm']);directions=np.diff(points,axis=0);directions/=np.linalg.norm(directions,axis=1)[:,None]
        turns=np.arccos(np.clip((directions[:-1]*directions[1:]).sum(1),-1,1));chord=np.linalg.norm(points[-1]-points[0])
        values=np.array([r['metrics']['area_mm2'] for r in core])
        for a,b in zip(local,local[1:]):
            if a['metrics'] and b['metrics']:
                ratio=b['metrics']['area_mm2']/a['metrics']['area_mm2'];angle=math.degrees(math.acos(np.clip(np.dot(a['plane_normal_unit'],b['plane_normal_unit']),-1,1)))
                if max(ratio,1/ratio)>1.35 or angle>20:
                    why=[]
                    if angle>20:why.append('CONTROL_POLYLINE_TANGENT_CHANGE')
                    if a['status']!='PATH_LOCAL_SECTION' or b['status']!='PATH_LOCAL_SECTION':why.append('SHARED_JUNCTION_OR_INTERFACE')
                    if not why:why.append('REFERENCE_LUMEN_MORPHOLOGY_CHANGE_REQUIRES_REVIEW')
                    anomalies.append({'path_id':name,'station_ids':[a['id'],b['id']],'area_ratio_next_previous':ratio,'tangent_angle_deg':angle,
                                      'reason_candidates':why,'interpretation':'Flagged for review; not a diagnosed anatomical stenosis or solver defect.'})
        tight=min(core,key=lambda r:r['metrics']['area_mm2']) if core else None
        summaries.append({'id':name,'source_marker_names':path['marker_names'],'length_mm':length,'chord_length_mm':float(chord),
             'tortuosity_length_over_chord':float(path['length_mm']/chord),'sum_control_turn_angle_deg':float(np.degrees(turns).sum()),
             'stations':len(local),'status_counts':dict(Counter(r['status'] for r in local)),
             'local_area_min_median_max_mm2':None if not len(values) else np.quantile(values,[0,.5,1]).tolist(),
             'narrowest_valid_local_station_id':None if tight is None else tight['id'],
             'narrowest_valid_local_station_arc_mm':None if tight is None else tight['station_arc_mm'],
             'anatomical_classification':'UNCONFIRMED; geometric wide/narrow/terminal/shared labels only',
             'sampling_step_mm':step,'fixed_port_retained_subset_only':name in ['IN_01','IN_02']})
        summaries[-1]['local_metric_min_median_max']={key:np.quantile([r['metrics'][key] for r in core],[0,.5,1]).tolist() if core else None
            for key in ['area_mm2','perimeter_mm','equivalent_radius_mm','major_axis_mm','minor_axis_mm','flattening_1_minus_minor_major']}
        candidate=[r for r in local if r['candidate_metrics']]
        summaries[-1]['candidate_ring_metric_min_median_max_TOPOLOGY_NOT_CONFIRMED']={key:np.quantile([r['candidate_metrics'][key] for r in candidate],[0,.5,1]).tolist() if candidate else None
            for key in ['area_mm2','perimeter_mm','equivalent_radius_mm','major_axis_mm','minor_axis_mm','flattening_1_minus_minor_major']}
        summaries[-1]['narrowest_valid_local_position_mm']=None if tight is None else tight['position_mm']
        if name in ['IN_01','IN_02']:
            summaries[-1]['source_centerline_length_mm']=analyzer.by_id[name]['length_mm']
            short_chord=float(np.linalg.norm(path_station(path,length)-path_station(path,0)))
            summaries[-1]['chord_length_mm']=short_chord;summaries[-1]['tortuosity_length_over_chord']=length/short_chord
        print('Path',name,len(local),'sections',flush=True)
    nodes=[]
    for name,node in sorted(analyzer.resolved['nodes'].items()):
        if not name.startswith(('J_','T_')):continue
        adjacent=[p for p in paths if name in [p['marker_names'][0],p['marker_names'][-1]]]
        selected=[]
        for p in adjacent:
            for r in records:
                if r['path_id']!=p['id']:continue
                distance=r['station_arc_mm'] if p['marker_names'][0]==name else p['length_mm']-r['station_arc_mm']
                if distance<=2.00001:selected.append(r['id'])
        nodes.append({'id':name,'position_mm':node['position_mm'],'incident_paths':[p['id'] for p in adjacent],
                      'probe_station_ids':selected,'status':'SHARED_CONNECTION_PROBES' if name.startswith('J_') else 'TERMINAL_NEAR_CAP_PROBES',
                      'limits':'No unique junction/terminal planar section or anatomical calyx label inferred.'})
        probes=[r for r in records if r['id'] in selected]
        accepted=[r for r in probes if r['metrics']]
        nodes[-1]['probe_status_counts']=dict(Counter(r['status'] for r in probes))
        nodes[-1]['probe_metric_min_median_max']={key:np.quantile([r['metrics'][key] for r in accepted],[0,.5,1]).tolist() if accepted else None
            for key in ['area_mm2','perimeter_mm','equivalent_radius_mm','major_axis_mm','minor_axis_mm','flattening_1_minus_minor_major']}
    local_areas=[r['metrics']['area_mm2'] for r in records if r['status']=='PATH_LOCAL_SECTION']
    q25,q75=np.quantile(local_areas,[.25,.75])
    for row in records:
        if row['status']=='PATH_LOCAL_SECTION':
            area=row['metrics']['area_mm2'];row['geometric_class']='RELATIVE_NARROW_SECTION' if area<q25 else 'RELATIVE_WIDE_SECTION' if area>q75 else 'INTERMEDIATE_SECTION'
        else:row['geometric_class']=row['status']
    database={'schema':'N1_REFERENCE_SECTIONS_V1','domain':'D2','units':'mm, mm2',
                'stations':records,'nodes':nodes,'source_mapping_files':['d2/source_vertex_ids.npy','d2/source_vertex_weights.npy','d2/source_face_ids.npy'],
                'topology_thresholds':{'max_nonadjacent_boundary_fraction':.10,'min_own_fraction':.10,'path_local_own_fraction':.70},
                'relative_width_quantiles_mm2':[float(q25),float(q75)],
                'limits':'Accepted ring metrics are geometric section areas, NOT independent branch volumes; shared or ambiguous rings never enter a cross-section capacity sum.'}
    atomic_bytes(ROOT/'sections.json.gz',gzip.compress(json.dumps(database,ensure_ascii=False,separators=(',',':')).encode('utf8'),mtime=0))
    if (ROOT/'sections.json').exists():(ROOT/'sections.json').unlink() # Only obsolete product inside this new version directory.
    write_json(ROOT/'path_statistics.json',{'paths':summaries,'nodes':nodes,'station_status_counts':dict(Counter(r['status'] for r in records))})
    write_json(ROOT/'section_anomalies.json',{'flags':anomalies,'invalid_or_ambiguous_stations':[{'id':r['id'],'status':r['status']} for r in records if r['metrics'] is None]})
    with (ROOT/'sections.csv').open('w',encoding='utf-8-sig',newline='') as file:
        fields=['id','path_id','station_arc_mm','status','area_mm2','perimeter_mm','equivalent_radius_mm','major_axis_mm','minor_axis_mm','flattening_1_minus_minor_major']
        writer=csv.DictWriter(file,fieldnames=fields);writer.writeheader()
        for row in records:writer.writerow({**{k:row[k] for k in fields[:4]},**{k:(row['metrics'] or {}).get(k) for k in fields[4:]}})
    print('Sections',len(records),dict(Counter(r['status'] for r in records)),flush=True)
    return analyzer,records,summaries,nodes

def region_catalog(analyzer):
    names=[p['id'] for p in analyzer.paths if p['id'] not in ['BLADDER','IN_01','IN_02']]
    names+=sorted(n for n in analyzer.resolved['nodes'] if n.startswith(('J_','T_')))
    names+=['FIXED_PORT_RETAINED','AMBIGUOUS_SHARED','UNSEEDED_INTERIOR','UNASSIGNED_BOUNDARY_REMAINDER']
    return names

def classify_regions(positions,path_ids,analyzer,names,factor=1.):
    # Junction/terminal spheres are EXPLICIT candidate boundaries, restricted to incident graph owners.
    labels=np.array([names.index(analyzer.paths[i]['id']) if i>=0 and analyzer.paths[i]['id'] in names else names.index('UNSEEDED_INTERIOR') for i in path_ids],dtype=np.int32)
    hit=np.zeros(len(positions),int);first=np.full(len(positions),-1,int)
    for name,node in sorted(analyzer.resolved['nodes'].items()):
        if not name.startswith(('J_','T_')):continue
        incident=[i for i,p in enumerate(analyzer.paths) if name in [p['marker_names'][0],p['marker_names'][-1]]]
        radius=(2.5 if name.startswith('J_') else 2.)*factor
        mask=np.isin(path_ids,incident)&(np.linalg.norm(positions-node['position_mm'],axis=1)<=radius)
        first[mask]=names.index(name);hit[mask]+=1
    labels[hit==1]=first[hit==1];labels[hit>1]=names.index('AMBIGUOUS_SHARED')
    labels[np.isin(path_ids,[i for i,p in enumerate(analyzer.paths) if p['id'] in ['IN_01','IN_02','BLADDER']])]=names.index('FIXED_PORT_RETAINED')
    return labels

def voxel_partition(analyzer,h,save=False):
    v,f=analyzer.v,analyzer.f;used=v[np.unique(f)];low=np.floor(used.min(0)/h)*h-h;high=np.ceil(used.max(0)/h)*h+h
    dims=np.ceil((high-low)/h).astype(int);shape=tuple(dims.tolist())
    grid=np.indices(shape,dtype=np.int32).reshape(3,-1).T;points=low+(grid+.5)*h
    scene=ray_scene(v,f);signed=[]
    import open3d as o3d
    for start in range(0,len(points),100000):
        signed.append(scene.compute_signed_distance(o3d.core.Tensor((points[start:start+100000]-ORIGIN).astype('float32')),nsamples=3).numpy())
    signed=np.concatenate(signed)
    # Distance-to-boundary + circumscribed sphere prevents crossing thin walls at this grid resolution.
    threshold=math.sqrt(3)*h/2+2e-4
    accepted=np.flatnonzero(signed < -threshold);xyz=grid[accepted];pts=points[accepted]
    alternate=scene.compute_signed_distance(o3d.core.Tensor((pts-ORIGIN).astype('float32')),nsamples=5).numpy()
    agree=alternate < -threshold;rejected=int((~agree).sum());accepted=accepted[agree];xyz=xyz[agree];pts=pts[agree]
    lookup=np.full(len(points),-1,np.int32);lookup[accepted]=np.arange(len(accepted));a=[];b=[]
    strides=[int(dims[1]*dims[2]),int(dims[2]),1]
    for axis,stride in enumerate(strides):
        valid=xyz[:,axis]+1<dims[axis];ids=np.flatnonzero(valid);neighbors=lookup[accepted[ids]+stride];ok=neighbors>=0
        a.extend(ids[ok].tolist());b.extend(neighbors[ok].tolist())
    a=np.asarray(a);b=np.asarray(b);graph=coo_matrix((np.full(2*len(a),h),(np.r_[a,b],np.r_[b,a])),shape=(len(pts),len(pts))).tocsr()
    seed_votes={};tree=cKDTree(pts)
    for i,p in enumerate(analyzer.paths):
        for s in np.arange(.05,p['length_mm'],.25):
            c=path_station(p,s);dist,idx=tree.query(c)
            # Never snap an excluded artificial segment, or a thin path, across a wall into another lumen.
            if dist<=h*.75:seed_votes.setdefault(int(idx),set()).add(i)
    seeds=np.array(sorted(k for k,val in seed_votes.items() if len(val)==1),int)
    if not len(seeds):raise ValueError('No unambiguous interior path seeds')
    distances,predecessors,sources=dijkstra(graph,directed=False,indices=seeds,min_only=True,return_predecessors=True)
    owners=np.full(len(pts),-1,int)
    for seed in seeds:owners[sources==seed]=next(iter(seed_votes[int(seed)]))
    names=region_catalog(analyzer);labels=classify_regions(pts,owners,analyzer,names)
    exact=read_json(ROOT/'D2_independent_volume.json')['V_reference_D2_mm3'];interior=len(pts)*h**3;remainder=exact-interior
    if remainder<0:raise ValueError('Interior candidate volume exceeds exact D2')
    volumes=np.bincount(labels,minlength=len(names))*h**3;volumes[-1]+=remainder
    sensitivity=[]
    for factor in [.75,1.,1.25]:
        lab=classify_regions(pts,owners,analyzer,names,factor);vol=np.bincount(lab,minlength=len(names))*h**3;vol[-1]+=remainder
        sensitivity.append({'junction_terminal_radius_factor':factor,'region_volume_mL':dict(zip(names,(vol/1000).tolist()))})
    rows=[{'id':name,'candidate_volume_mL':float(volume/1000),'fraction_D2':float(volume/exact),
            'status':'UNASSIGNED_BOUNDARY_VOLUME' if name==names[-1] else 'CANDIDATE_GRID_ACCOUNTING_NOT_ANATOMICAL_BRANCH_VOLUME'} for name,volume in zip(names,volumes)]
    report={'schema':'N1_NONOVERLAPPING_CANDIDATE_ACCOUNTING_V1','status':'CANDIDATE_NOT_FORMAL_BRANCH_CAPACITY',
       'method':'Disjoint axis-aligned cubes, centers inside by distance > circumscribed radius+0.0002mm; two odd-ray parity checks. Six-neighbor interior geodesic multi-source path seeds; no Euclidean owner propagation across walls. Explicit J/T candidate shared regions. Exact D2 minus cube volume remains unassigned, never distributed by normalization.',
       'grid_mm':h,'grid_origin_mm':low.tolist(),'grid_dimensions':dims.tolist(),'tested_centers':len(points),'interior_cubes':len(pts),
       'parity_rejected_cubes':rejected,'cube_interior_volume_mL':interior/1000,'boundary_remainder_mL':remainder/1000,
       'unseeded_cubes':int((owners<0).sum()),'seed_collisions_not_used':sum(len(x)>1 for x in seed_votes.values()),
       'interior_graph_components':int(connected_components(graph,directed=False,return_labels=False)),
       'D2_total_mL':exact/1000,'partition_sum_mL':float(volumes.sum()/1000),'residual_mm3':float(volumes.sum()-exact),
       'regions':rows,'boundary_sensitivity':sensitivity,'junction_radius_mm':2.5,'terminal_radius_mm':2.,
       'limits':['Grid erosion may disconnect thin isthmuses; unseeded cubes stay unassigned.',
                 'Voxel ray queries use centered float32 and inherited reference surface; no claim of formal exact interior predicate.',
                 'Remainder is a set complement accounting term, not independently segmented clinical volume.',
                 'Region radii and path seed boundaries are engineering candidates pending manual review.',
                 'No section-area integration or signed per-face cone volumes are labelled branch capacity.']}
    if save:
        save_npy(ROOT/'partition_cube_centers_mm.npy',pts);save_npy(ROOT/'partition_cube_grid_indices.npy',xyz)
        save_npy(ROOT/'partition_cube_path_owner.npy',owners);save_npy(ROOT/'partition_cube_regions.npy',labels)
        save_npy(ROOT/'partition_seed_cube_ids.npy',seeds);save_npy(ROOT/'partition_geodesic_predecessor.npy',predecessors)
        closest=scene.compute_closest_points(o3d.core.Tensor((pts-ORIGIN).astype('float32')))
        faceids=closest['primitive_ids'].numpy().astype(int)
        save_npy(ROOT/'partition_nearest_D2_face_ids.npy',faceids);save_npy(ROOT/'partition_nearest_source_face_ids.npy',analyzer.source[faceids])
        save_npy(ROOT/'partition_nearest_face_uv.npy',closest['primitive_uvs'].numpy())
        write_json(ROOT/'capacity_partition_candidate.json',report)
    print('Partition',h,'interior',len(pts),'remainder mL',remainder/1000,flush=True)
    return report

def figures(records,summaries,partition):
    os.environ['MPLCONFIGDIR']=str(ROOT/'matplotlib_cache')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.family']='DejaVu Sans'
    fig,axes=plt.subplots(4,1,figsize=(12,12),constrained_layout=True)
    for ax,names,title in zip(axes,[['MAIN'],['B_%02d'%i for i in range(1,11)],['B_%02d'%i for i in range(11,21)],['B_%02d'%i for i in range(21,33)]],['MAIN','B01-B10','B11-B20','B21-B32']):
        for name in names:
            rows=[r for r in records if r['path_id']==name]
            ax.plot([r['station_arc_mm'] for r in rows],[r['metrics']['area_mm2'] if r['metrics'] else np.nan for r in rows],'.-',label=name,linewidth=.8,markersize=2)
        ax.set_title(title+' - Reference sections (shared rings included, not branch volumes)');ax.set_xlabel('Arc length (mm)');ax.set_ylabel('Area (mm2)');ax.legend(ncol=5,fontsize=8);ax.grid(alpha=.2)
    fig.savefig(ROOT/'section_area_profiles.png',dpi=150);plt.close(fig)
    rows=partition['regions'];fig,ax=plt.subplots(figsize=(14,5),constrained_layout=True)
    ax.bar(np.arange(len(rows)),[r['candidate_volume_mL'] for r in rows]);ax.set_xticks(np.arange(len(rows)));ax.set_xticklabels([r['id'] for r in rows],rotation=90,fontsize=7)
    ax.set_ylabel('Candidate volume (mL)');ax.set_title('Disjoint interior cube candidate + explicit boundary remainder; NOT formal anatomical capacities')
    fig.savefig(ROOT/'candidate_capacity_accounting.png',dpi=150);plt.close(fig)

def preview_data(analyzer,records,summaries,nodes,partition):
    names=region_catalog(analyzer);original_owner=analyzer.owner[np.maximum(analyzer.wids[:,0],0)]
    labels=classify_regions(analyzer.v,original_owner,analyzer,names)
    # Colors are a surface audit overlay; not a volume partition or revised mask.
    colors=[]
    import colorsys
    for i in range(len(names)):
        rgb=colorsys.hsv_to_rgb((i*.61803398875)%1,.55,.95);colors.append(list(rgb))
    stations=[]
    for r in records:
        item={k:r[k] for k in ['id','path_id','station_arc_mm','position_mm','plane_normal_unit','status','metrics','geometric_class']}
        loops=[];selected=None
        for i,loop in enumerate(r['loops']):
            votes=loop['path_owner_boundary_length_fractions']
            relevant=sum(v for name,v in votes.items() if name in analyzer.neighbors[r['path_id']])>.2
            if i!=r['selected_loop'] and not relevant:continue
            pts=loop['ring_positions_mm']
            if i==r['selected_loop']:selected=len(loops)
            elif len(pts)>64:pts=[pts[j] for j in np.linspace(0,len(pts)-1,64).astype(int)]
            loops.append({'ring_positions_mm':pts,'simple':loop['simple'],'contains_station':loop['contains_station'],
                          'original_loop_index':i,'area_mm2':loop['area_mm2']})
        item.update({'loops':loops,'selected_loop':selected,'all_plane_loop_count':len(r['loops']),
                     'display_limits':'Selected loop exact. Relevant other loops are decimated to <=64 points; all exact rings/mappings in sections.json.gz. Display filtering does not choose an owner.'})
        stations.append(item)
    preview={'schema':'CAPACITY_V2_N1_REVIEW_V1','D2_status':'USER_APPROVED_PROJECT_MEASUREMENT_DOMAIN',
             'approval_sha256':sha(ROOT/'D2_approval_2026_10_14_v1.json'),'V_reference_D2_mL':partition['D2_total_mL'],
             'units':'mm and mL; display origin [16,16,-81] mm','paths':summaries,'nodes':nodes,
             'used_bounds_mm':[analyzer.v[np.unique(analyzer.f)].min(0).tolist(),analyzer.v[np.unique(analyzer.f)].max(0).tolist()],
             'stations':stations,
             'region_names':names,'region_colors':colors,'wall_vertex_region_ids':labels.tolist(),'capacity':partition,
             'mesh_sha256':{name:sha(ROOT/'d2'/name) for name in ['original_wall.bin','virtual_caps.bin']},
             'limits':'Reference-only analysis. Capacity rows are engineering candidates; no N2 geometry, no normal endpoints.'}
    write_json(ROOT/'review_preview.json',preview)

def build():
    freeze_d2();analyzer,records,summaries,nodes=sections_build()
    coarse=voxel_partition(analyzer,.75);fine=voxel_partition(analyzer,.5,True)
    write_json(ROOT/'partition_resolution_sensitivity.json',{'coarse':coarse,'fine':fine,
                'interpretation':'Different eroded interior sets and geodesic boundaries; not confidence intervals or exact anatomical regional capacities.'})
    figures(records,summaries,fine);preview_data(analyzer,records,summaries,nodes,fine)
    write_json(ROOT/'build_manifest.json',{'schema':'CAPACITY_V2_N1_BUILD_V1','N2_started':False,'V_min_mL':None,'V_max_mL':None,
               'source_sha256':AUTHORITY,'D2_candidate_sha256':sha(R1/'candidate.json'),'topology_sha256':sha(TOPOLOGY),
               'analysis_input_sha256':{'path_owner.npy':sha(PROJECT/'deformation/p1_masks/path_owner.npy'),'irrigation_markers.json':sha(PROJECT/'deformation/irrigation_markers.json')},
               'script_sha256':sha(Path(__file__)),'products':{p.relative_to(ROOT).as_posix():sha(p) for p in sorted(ROOT.rglob('*')) if p.is_file() and p.name not in ['build_manifest.json','protected_before.json','protected_after.json','python_tests.json','delivery_manifest.json','candidate_capacity_accounting.csv','.gitignore'] and 'verification' not in p.parts and 'matplotlib_cache' not in p.parts and 'user_sessions' not in p.parts}})
    print('N1 build complete;',protect(),'protected files unchanged',flush=True)

if __name__=='__main__':build()
