"""Prepare review metadata, source terminal-face inventory and boundary sensitivity."""
from n0_common import *
from build_n0_domains import local_cut,station,cap_validation,cap_original_validation
from scipy.spatial import cKDTree
from localize_p15_conflicts import spatial_labels

def terminal_inventory():
    _,a=verify_sources();v,f=a['cavity_reference_vertices'],a['cavity_faces'];r=read_json(PROJECT/'deformation/cavity_topology_resolved.json')
    owner=np.load(PROJECT/'deformation/p1_masks/path_owner.npy');norm=trimesh.Trimesh(v,f,process=False).face_normals;centers=v[f].mean(1);rows=[]
    for name,node in sorted(r['nodes'].items()):
        if not name.startswith('T_'):continue
        ids=[i for i,p in enumerate(r['paths']) if name in p['marker_names']]
        p=r['paths'][ids[0]];points=np.asarray(p['points_mm']);direction=points[-1]-points[-2];direction/=np.linalg.norm(direction)
        candidates=np.flatnonzero((owner[f]==ids[0]).sum(1)>=2);point=np.array(node['position_mm'])
        selected=candidates[np.argsort(np.linalg.norm(centers[candidates]-point,axis=1))[:12]]
        rows.append({'id':name,'marker_mm':point.tolist(),'path_id':p['id'],'geometric_candidate_face_ids':selected.tolist(),
           'candidate_face_centroid_distance_mm':np.linalg.norm(centers[selected]-point,axis=1).tolist(),
           'candidate_face_normal_dot_terminal_direction':(norm[selected]@direction).tolist(),
           'original_mesh_boundary_edges':0,'virtual_cap_provenance':'UNKNOWN_NO_SEGMENTATION_OR_PREPROCESSING_RECORD',
           'interpretation':'Original closed source faces near endpoint, NOT identified anatomical terminal or newly generated caps; path owner is geometric.'})
    write_json(OUT/'terminal_boundary_inventory.json',{'terminals':rows,'all_22_source_end_regions_inventoried':True,'natural_terminal_semantics':'UNCONFIRMED'})

def sensitivity():
    _,a=verify_sources();v,f=a['cavity_reference_vertices'],a['cavity_faces'];r=read_json(PROJECT/'deformation/cavity_topology_resolved.json');paths={p['id']:p for p in r['paths']}
    source=np.arange(len(f));labels=np.zeros(len(f),int);weights=[{i:1.} for i in range(len(v))];rows=[]
    for index,(port,transition) in enumerate([('BLADDER','BLADDER_TRANSITION'),('IN_01','B_31'),('IN_02','B_32')],1):
        center,n=station(paths[transition],.5);end=np.array(paths[port]['points_mm'][-1]);n=n if (end-center)@n>0 else -n
        for offset in [-.1,.1]:
            vv,ff,ss,cc,ww,info,_=local_cut(v,f,source,labels,weights,center+offset*n,n,end,index)
            check=cap_validation(vv,ff,cc);original_check=cap_original_validation(vv,ff,cc,f,{index:info});mesh=trimesh.Trimesh(vv,ff,process=False)
            valid=bool(mesh.is_watertight and mesh.is_winding_consistent and not check['cap_wall_invalid_count'] and not check['cap_cap_invalid_pairs'] and not original_check['invalid_count'])
            directory=OUT/'sensitivity'/f'{port}_{"minus" if offset<0 else "plus"}0100';directory.mkdir(parents=True,exist_ok=True)
            for key,arr in [('reference_vertices',vv),('faces',ff),('source_face_ids',ss),('virtual_port_labels',cc)]:save_npy(directory/(key+'.npy'),arr)
            wids=np.full((len(vv),3),-1,int);wval=np.zeros((len(vv),3))
            for k,w in enumerate(ww):
                for j,(idx,value) in enumerate(w.items()):wids[k,j]=idx;wval[k,j]=value
            save_npy(directory/'source_vertex_ids.npy',wids);save_npy(directory/'source_vertex_weights.npy',wval)
            row={'port':port,'offset_toward_END_mm':offset,'single_port_removed_volume_mL':info['removed_volume_mL'],'geometry_valid':valid,
                 'cut':info,'cap_validation_summary':{k:v for k,v in check.items() if k!='pairs'},'anatomical_approval':'PENDING','source_hashes':AUTHORITY}
            row['cap_original_validation']={k:v for k,v in original_check.items() if k!='pairs'}
            write_json(directory/'cap_original_contact_details.json',original_check)
            row['output_sha256']={p.name:sha(p) for p in sorted(directory.glob('*.npy'))}
            write_json(directory/'candidate.json',row);rows.append(row)
    write_json(OUT/'section_sensitivity.json',{'scope':'Each middle cut translated +/-0.1 mm independently; geometric sensitivity, not physiological confidence bounds.','variants':rows})

def prepare():
    freeze();terminal_inventory();sensitivity()
    domains=read_json(OUT/'domain_candidates.json');contacts=read_json(OUT/'contact_summary.json')
    r=read_json(PROJECT/'deformation/cavity_topology_resolved.json');locations=read_json(PROJECT/'deformation/p23/focus_locations.json')['locations']
    review_pairs=list(contacts['review_pairs']);groups=[]
    for u in [0,.25,.5,.75,1]:
        report=read_json(OUT/'contacts'/f'u{round(u*1000000):06}_actual_float32.json');coplanar=[p for p in report['pairs'] if p['class']=='COPLANAR_OVERLAP']
        labels=spatial_labels(np.array([p['center_mm'] for p in coplanar]),2.)
        for label in np.unique(labels):
            members=[p for p,k in zip(coplanar,labels) if k==label];group_id=f'COPLANAR_u{round(u*100):03}_{label:02}'
            representative=max(members,key=lambda p:p['coplanar_pair_overlap_area_mm2'])
            review_pairs.append(dict(representative,id=group_id,region=group_id))
            groups.append({'id':group_id,'u':u,'pair_count':len(members),'center_mm':np.mean([p['center_mm'] for p in members],axis=0).tolist(),
               'source_face_pairs':[[p['cavity_face'],p['tissue_face']] for p in members],
               'coplanar_pair_area_sum_mm2':sum(p['coplanar_pair_overlap_area_mm2'] for p in members),'representative':representative,
               'limits':'2 mm single-link spatial group; extent may exceed threshold. Pair area sum is not unique contact/penetration area.'})
    write_json(OUT/'contact_groups.json',{'groups':groups,'kind':'COPLANAR_OVERLAP_SPATIAL_REVIEW_NOT_PHYSIOLOGICAL_ACCEPTANCE'})
    meta={'schema':'CAPACITY_V2_N0_REVIEW_V1','date':'2026-10-14','D2_approval':'PENDING_USER_REVIEW','V_reference_effective_mL':None,
       'origin_mm':ORIGIN.tolist(),'sources':AUTHORITY,'D0_volume_mL':domains['D0_volume_mL'],
       'candidates':[{k:value for k,value in row.items() if k in ['id','geometry_valid','used_surface_bounds_mm','candidate_measurement_volume_mL','removed_volume_mL','review_status','cuts','excluded_natural_marker_ids','natural_paths_with_outside_samples','anatomical_recommendation','output_sha256','wide_chamber_cut_warning','cap_area_vs_distal_control']} for row in domains['candidates']],
       'locations':locations,'review_pairs':review_pairs,'paths':[{k:p[k] for k in ['id','points_mm','kind']} for p in r['paths']],
       'junction_neighbors':{key:node['neighbors'] for key,node in r['nodes'].items() if key.startswith('J_')},
       'source_obj_sha256':sha(PROJECT/'source_assets/kidney_cavity.obj'),'p2_manifest_sha256':sha(PROJECT/'deformation/p2/accepted_inputs.json'),
       'legacy_volume_polynomial_mm3':read_json(PROJECT/'deformation/capacity_v2_research/reference_capacity_audit.json')['legacy_debug_volume_polynomial_mm3'],
       'user_visual_anomaly_status':'NOT_SPECIFICALLY_REPRODUCED_NEEDS_USER_CAMERA_OR_LOCATION','no_new_deformation':True}
    write_json(OUT/'review_preview.json',meta);protected();print('Prepared N0 review:',len(meta['candidates']),'domains',len(meta['review_pairs']),'pair locations')

if __name__=='__main__':prepare()
