"""Five-level R2 checks. Reference uses cached candidates, nonzero levels are freshly scanned."""
import argparse,time
from scipy.spatial import cKDTree
from common import *
from research_p15_contact_mapping import verify_pairs
from audit_tissue_cavity import contact_pairs,summary,ORIGIN,ray_scene
from build_local_displacement import self_intersection_pairs
from localize_p15_conflicts import pair_geometry


def quality(tv,tf,field,u,edges,length):
    c0,a0,_=triangle_data(tv,tf);cross,area,q=triangle_data(tv+u*field,tf)
    cosine=np.einsum('ij,ij->i',cross,c0)/(4*a0*area)
    gradient=u*np.linalg.norm(field[edges[:,0]]-field[edges[:,1]],axis=1)/length
    normals=vertex_normals(tv+u*field,tf);nl=np.linalg.norm(normals,axis=1)
    return {'finite':bool(np.isfinite(tv+u*field).all() and np.isfinite(normals).all()),'degenerate_count':int((area<1e-10).sum()),'normal_reversal_count':int((cosine<=0).sum()),
      'area_ratio_range':[float((area/a0).min()),float((area/a0).max())],'maximum_edge_gradient':float(gradient.max()),
      'maximum_neighbor_difference_mm':float((gradient*length).max()),'normal_length_range':[float(nl.min()),float(nl.max())],
      'maximum_normal_rotation_deg':float(np.degrees(np.arccos(np.clip(cosine,-1,1))).max()),
      'volume_mm3':float(np.einsum('ij,ij->i',(tv+u*field)[tf[:,0]],np.cross((tv+u*field)[tf[:,1]],(tv+u*field)[tf[:,2]])).sum()/6),
      'maximum_displacement_mm':float(u*np.linalg.norm(field,axis=1).max()),'mean_displacement_mm':float(u*np.linalg.norm(field,axis=1).mean()),
      'moving_vertices':int((u*np.linalg.norm(field,axis=1)>1e-12).sum()),'minimum_triangle_area_mm2':float(area.min()),'minimum_triangle_quality':float(q.min())}


def check(u,self_scan=False):
    t=time.time();d=read_inputs();tv,tf,v,f,driver=d['tv'],d['tf'],d['v'],d['f'],d['driver']
    field=np.load(OUT/'research_tissue_displacement.npy');digest=source_record(OUT/'research_tissue_displacement.npy')['sha256'];tag=f'{int(u*100):03}'
    print('Scanning R2',u,'self' if self_scan else 'cross+quality',flush=True)
    if self_scan:
        pairs=np.load(AUDIT/'tissue_self_intersections.npy') if u==0 else self_intersection_pairs(tv+u*field,tf)
        result=verify_pairs(tv+u*field,tf,tv+u*field,tf,pairs);name='self'
        geom=pair_geometry(tv+u*field,tf,tv+u*field,tf,pairs)
        result['finite_feature_distances_mm']=geom['feature_distance'].tolist();result['candidate_centers_mm']=geom['centers'].tolist()
    else:
        pairs=np.load(AUDIT/'cross_contact_pairs.npy') if u==0 else contact_pairs(v+u*driver,f,tv+u*field,tf)
        result=verify_pairs(v+u*driver,f,tv+u*field,tf,pairs);name='cross'
        graph,edges,length=mesh_graph(tv,tf);result['tissue_quality']=quality(tv,tf,field,u,edges,length)
        result['R1_quality']=quality(tv,tf,d['old'],u,edges,length)
        baseline=np.load(AUDIT/'cross_contact_pairs.npy');oldset=set(map(tuple,baseline));new=np.array([p for p in pairs if tuple(p) not in oldset],int).reshape(-1,2)
        result['new_candidate_pairs']=new.tolist()
        if len(new):
            geom=pair_geometry(v+u*driver,f,tv+u*field,tf,new)
            ref=np.load(R1/'original_contact_sample_points.npy');dist=cKDTree(ref).query(geom['centers'])[0]
            result['new_candidate_centers_mm']=geom['centers'].tolist();result['new_candidate_to_reference_cloud_mm']=summary(dist)
        else: result['new_candidate_to_reference_cloud_mm']=summary(np.zeros(1))
    np.save(OUT/f'{name}_pairs_u{tag}.npy',pairs)
    result.update({'fill':u,'field_sha256':digest,'elapsed_seconds':time.time()-t,'finite_acceptance_epsilon_mm':1e-10})
    (OUT/f'{name}_check_u{tag}.json').write_bytes(json_bytes(result))
    print(name,u,'confirmed',result['positive_segment_count'],'raw',result['raw_candidate_count'],'seconds',time.time()-t,flush=True)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--fill',type=float,required=True);p.add_argument('--self-scan',action='store_true');a=p.parse_args()
    if a.fill not in (0,.25,.5,.75,1): raise ValueError('Invalid review level')
    check(a.fill,a.self_scan)
