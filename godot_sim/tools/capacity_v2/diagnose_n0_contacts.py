"""Fresh finite contact classification of accepted P2.3 actual ArrayMeshes.

Option --u permits additional levels; exact previously exported positions are
used when present, otherwise approved float32 formula is explicitly labelled.
"""
from n0_common import *
import argparse,time
from collections import Counter
from audit_tissue_cavity import contact_pairs,ray_scene
import open3d as o3d
from trimesh.triangles import closest_point

PRIORITY=['J_05','J_09','B_32','IN_02','F01','F02','F03','F04']

def load_pose(a,name,u):
    ref,field,faces=[a[name+'_'+k] for k in ['reference_vertices','displacement','faces']]
    expected=(ref-ORIGIN).astype(np.float32)+np.float32(u)*field.astype(np.float32)
    path=PROJECT/'analysis/irrigation_baseline/p23/final_regression_forward'/f'{name}_u{round(u*100):03}.bin'
    if abs(u*100-round(u*100))<1e-12 and path.exists():
        raw=path.read_bytes();actual=np.frombuffer(raw,'<f4',count=3*len(ref)).reshape(-1,3)
        idx=np.frombuffer(raw,'<i4',offset=24*len(ref)).reshape(-1,3)
        if not np.array_equal(actual,expected) or not np.array_equal(idx,faces[:,::-1]):raise ValueError('P2.3 actual export mismatch')
        return actual.astype(float),{'kind':'ACTUAL_P23_ARRAYMESH_EXPORT','path':path.relative_to(REPO).as_posix(),'sha256':sha(path),'positions_bit_equal':True}
    return expected.astype(float),{'kind':'APPROVED_FLOAT32_FORMULA_PENDING_NEW_RUNTIME_EXPORT','positions_bit_equal':None}

def classify_pair(v,f,tv,tf,i,j,u,broad,locations,input_origin=ORIGIN):
    a,b=v[f[i]],tv[tf[j]];seg=intersection_segment(a,b);area=coplanar_overlap_area(a,b)
    an=np.cross(a[1]-a[0],a[2]-a[0]);an/=np.linalg.norm(an)
    bn=np.cross(b[1]-b[0],b[2]-b[0]);bn/=np.linalg.norm(bn)
    plane_residual=max(np.max(np.abs((b-a[0])@an)),np.max(np.abs((a-b[0])@bn)))
    raw_area=area
    if plane_residual>1e-10:area=0.
    gap,point=closest_features(a,b);length=0. if seg is None else float(np.linalg.norm(seg[1]-seg[0]))
    raw_length=length;support_residual=0.;boundary=[]
    if seg is not None:
        point=seg.mean(0);kind='FINITE_INTERSECTION_REQUIRES_REVIEW'
        samples=np.vstack([seg,point]);residuals=[]
        for tri in [a,b]:
            residuals.append(np.linalg.norm(closest_point(np.repeat(tri[None],3,axis=0),samples)-samples,axis=1))
            edge_distance=[]
            for x,y in zip(tri,np.roll(tri,-1,axis=0)):
                axis=y-x;t=np.clip((point-x)@axis/(axis@axis),0.,1.)
                edge_distance.append(np.linalg.norm(point-(x+t*axis)))
            boundary.append(bool(min(edge_distance)<=1e-10))
        support_residual=float(np.max(residuals))
        aa=np.cross(a[1]-a[0],a[2]-a[0]);bb=np.cross(b[1]-b[0],b[2]-b[0])
        da=(b-a[0])@aa/np.linalg.norm(aa);db=(a-b[0])@bb/np.linalg.norm(bb)
        if support_residual>1e-10:kind='FINITE_SEGMENT_ALGORITHM_FALSE_POSITIVE';length=0.
        elif boundary[0] and boundary[1]:kind='EDGE_CONTACT';gap=0.
        elif any(boundary):kind='EDGE_FACE_CONTACT';gap=0.
        elif da.min()<-1e-10 and da.max()>1e-10 and db.min()<-1e-10 and db.max()>1e-10:kind='FINITE_TRANSVERSE_CROSSING';gap=0.
    elif area>1e-12:kind='COPLANAR_OVERLAP'
    elif gap<=1e-10:
        common=[p for p in a if np.linalg.norm(b-p,axis=1).min()<=1e-10]
        kind='EDGE_CONTACT' if len(common)>=2 and np.linalg.norm(common[0]-common[1])>1e-10 else 'POINT_CONTACT_OR_TANGENCY'
    elif gap<=.1:kind='NEAR_DISJOINT'
    else:kind='BROAD_PHASE_FALSE_POSITIVE'
    xyz=point+input_origin;world_point=xyz-ORIGIN
    nearest=sorted(((key,float(np.linalg.norm(xyz-np.array(rec['center_mm'])))) for key,rec in locations.items()),key=lambda x:x[1])[:3]
    return {'cavity_face':int(i),'tissue_face':int(j),'u':float(u),'class':kind,'center_mm':xyz.tolist(),
       'godot_world_center_mm':world_point.tolist(),'finite_segment_length_mm':length,'finite_segment_world_mm':None if seg is None else (seg+input_origin-ORIGIN).tolist(),
       'two_sided_coplanarity_residual_mm':float(plane_residual),'one_sided_raw_coplanar_candidate_area_mm2':float(raw_area),
       'raw_segment_candidate_length_mm':raw_length,'segment_support_residual_mm':support_residual,'segment_midpoint_on_triangle_boundary':boundary,
       'finite_feature_gap_mm':float(gap),'coplanar_pair_overlap_area_mm2':float(area),'vtk_candidate':bool(broad),'nearest_locations':nearest}

def check(u,space='actual_float32'):
    freeze();_,a=verify_sources();f=a['cavity_faces'];tf=a['tissue_faces'];start=time.time()
    if space=='actual_float32':
        v,cv_source=load_pose(a,'cavity',u);tv,tv_source=load_pose(a,'tissue',u);input_origin=ORIGIN
    else:
        v=a['cavity_reference_vertices']+u*a['cavity_displacement']
        tv=a['tissue_reference_vertices']+u*a['tissue_displacement'];input_origin=np.zeros(3)
        cv_source=tv_source={'kind':'SOURCE_FLOAT64_ACCEPTED_ARRAYS_ORIGINAL_COORDINATES'}
    print('N0 scanning',u,space,flush=True)
    pairs=contact_pairs(v,f,tv,tf);pairs=np.unique(pairs,axis=0);broadset=set(map(tuple,pairs))
    locations=read_json(PROJECT/'deformation/p23/focus_locations.json')['locations']
    # Near-contact search is a face-centroid sample diagnostic, not an exhaustive minimum-distance proof.
    centers=v[f].mean(1);scene=ray_scene(tv+input_origin,tf);query_centers=centers+input_origin-ORIGIN
    nearest=scene.compute_closest_points(o3d.core.Tensor(query_centers.astype('float32')))
    points=nearest['points'].numpy();ids=nearest['primitive_ids'].numpy();distances=np.linalg.norm(points-query_centers,axis=1)
    near=set();near_summary=[]
    for name,record in locations.items():
        mask=np.linalg.norm(centers+input_origin-np.array(record['center_mm']),axis=1)<(6. if name.startswith(('J_','B_')) else 4.)
        indices=np.flatnonzero(mask);order=indices[np.argsort(distances[indices])[:12]]
        near.update((int(i),int(ids[i])) for i in order if distances[i]<=.1)
        near_summary.append({'id':name,'sample_count':len(indices),'minimum_centroid_surface_distance_mm':None if len(indices)==0 else float(distances[indices].min())})
    allpairs=sorted(broadset|near);rows=[]
    for k,(i,j) in enumerate(allpairs):
        rows.append(classify_pair(v,f,tv,tf,i,j,u,(i,j) in broadset,locations,input_origin))
        if k and k%1500==0:print(' finite pairs',k,'/',len(allpairs),flush=True)
    baseline=set(map(tuple,np.load(PROJECT/'deformation/p2/evidence/contact_pairs.npy')))
    for row in rows:row['reference_pair_present']=(row['cavity_face'],row['tissue_face']) in baseline
    counts=Counter(row['class'] for row in rows)
    priority=[]
    for name in PRIORITY:
        p=np.array(locations[name]['center_mm']);local=[r for r in rows if np.linalg.norm(np.array(r['center_mm'])-p)<=6.]
        priority.append({'id':name,'counts':dict(Counter(r['class'] for r in local)),'pairs':len(local),
            'maximum_finite_segment_mm':max([r['finite_segment_length_mm'] for r in local],default=0.),
            'minimum_finite_feature_gap_mm':min([r['finite_feature_gap_mm'] for r in local],default=None)})
    directory=OUT/'contacts';directory.mkdir(exist_ok=True);tag=f'u{round(u*1000000):06}_{space}'
    save_npy(directory/(tag+'_pairs.npy'),np.asarray(allpairs,int).reshape(-1,2))
    report={'u':u,'coordinate_space':space,'source_arrays_sha256':AUTHORITY,'cavity_positions_source':cv_source,'tissue_positions_source':tv_source,
        'finite_epsilon_mm':1e-10,'coplanar_overlap_positive_area_mm2':1e-12,'vtk_box_and_cell_tolerance':0.,
        'counts':dict(counts),'vtk_pairs':len(pairs),'additional_near_sample_pairs':len(near-broadset),'pairs':rows,'priority_regions':priority,
        'near_surface_samples':near_summary,'seconds':time.time()-start,'confirmed_transverse_crossings':counts['FINITE_TRANSVERSE_CROSSING'],
        'all_positive_finite_intersections':sum(r['finite_segment_length_mm']>0 for r in rows),
        'coplanar_pair_area_sum_mm2':sum(r['coplanar_pair_overlap_area_mm2'] for r in rows),
        'limits':['Pair area sums may double count; not penetration area.','No physical penetration depth or true wall thickness established.',
        'Additional near search samples cavity face centroids; not exhaustive distance or continuous collision certification.',
        'Classification does not establish physiological acceptability of contact. User-observed visual anomaly may remain unlocalized.']}
    write_json(directory/(tag+'.json'),report)
    print('DONE',u,space,dict(counts),'seconds',time.time()-start,flush=True);protected();return report

def build():
    records=[]
    for u in [0,.25,.5,.75,1]:
        for space in ['actual_float32','source_float64']:records.append(check(u,space))
    compact=[];focus=[]
    for report in records:
        compact.append({k:v for k,v in report.items() if k!='pairs'})
        if report['coordinate_space']!='actual_float32':continue
        rows=report['pairs']
        for name in PRIORITY:
            p=np.array(read_json(PROJECT/'deformation/p23/focus_locations.json')['locations'][name]['center_mm'])
            selected=sorted(rows,key=lambda r:np.linalg.norm(np.array(r['center_mm'])-p))
            for kind in ['FINITE_TRANSVERSE_CROSSING','FINITE_INTERSECTION_REQUIRES_REVIEW','COPLANAR_OVERLAP','EDGE_CONTACT','EDGE_FACE_CONTACT','POINT_CONTACT_OR_TANGENCY','NEAR_DISJOINT']:
                match=next((r for r in selected if r['class']==kind and np.linalg.norm(np.array(r['center_mm'])-p)<6),None)
                if match:focus.append(dict(match,id=f'{name}_{round(report["u"]*100):03}_{kind}',region=name))
    write_json(OUT/'contact_summary.json',{'levels':compact,'review_pairs':focus,'user_visual_anomaly_reproduced':False,
       'conclusion':'Finite geometric classification only. Specific user-observed appearance has not been identified without camera/location information; do not interpret zero confirmed crossings as closure of the visual issue.'})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--u',type=float);p.add_argument('--session',type=Path);p.add_argument('--space',default='actual_float32',choices=['actual_float32','source_float64']);args=p.parse_args()
    if args.session:
        session=read_json(args.session)
        if session.get('source_manifest_sha256')!=sha(PROJECT/'deformation/p2/accepted_inputs.json'):raise ValueError('User session input manifest mismatch')
        u=float(session['u'])
        if not np.isfinite(u) or not 0<=u<=1:raise ValueError('Session u invalid')
        result=check(u,args.space);_,a=verify_sources()
        if args.space=='actual_float32':v,_=load_pose(a,'cavity',u);tv,_=load_pose(a,'tissue',u);session_origin=ORIGIN
        else:v=a['cavity_reference_vertices']+u*a['cavity_displacement'];tv=a['tissue_reference_vertices']+u*a['tissue_displacement'];session_origin=np.zeros(3)
        selected=session.get('selected_pair',{})
        pair=None
        if 'cavity_face' in selected and 'tissue_face' in selected:
            i,j=int(selected['cavity_face']),int(selected['tissue_face'])
            if not 0<=i<len(a['cavity_faces']) or not 0<=j<len(a['tissue_faces']):raise ValueError('Session face index invalid')
            pair=classify_pair(v,a['cavity_faces'],tv,a['tissue_faces'],i,j,u,False,read_json(PROJECT/'deformation/p23/focus_locations.json')['locations'],session_origin)
        write_json(OUT/'contacts'/('session_'+args.session.stem+'.json'),{'source_session_sha256':sha(args.session),'session':session,'selected_pair_classification':pair,'full_level_counts':result['counts'],'scope':'Geometric classification; visual appearance still requires same camera/section review.'})
    elif args.u is None:build()
    elif not np.isfinite(args.u) or not 0<=args.u<=1:raise ValueError('u must be finite and in [0,1]')
    else:check(args.u,args.space)
