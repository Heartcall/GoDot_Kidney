from n21_common import *
from n21_features import finite_features
from n20_verify import independent_volume
from trimesh.triangles import points_to_barycentric,closest_point

def run():
    a,d2,tv,tf,resolved,approval=begin();c,t,sources=fixture('expand');ci,ti,vi=34852,181160,93578
    A=(a['vertices']+c)[a['faces'][ci]];p=tv[vi]+t[vi];n=normalize(np.cross(A[1]-A[0],A[2]-A[0])[None])[0]
    values,rejected=finite_features(a['vertices']+c,tv+t,a['faces'][ci],tf[ti],ci,ti,a['vertices'],tv)
    conflicts={'pair':[ci,ti],'tissue_vertex':vi,'cavity_face_vertices':a['faces'][ci].tolist(),'tissue_face_vertices':tf[ti].tolist(),
        'strict_coincident_cavity_vertex':int(np.load(PROJECT/'deformation/p2/evidence/coincident_cavity_vertex.npy')[vi]),
        'point_mm':p.tolist(),'infinite_plane_signed_gap_mm':float((p-A[0])@n),
        'projected_barycentric':points_to_barycentric(A[None],p[None])[0].tolist(),
        'finite_face_distance_mm':float(np.linalg.norm(closest_point(A[None],p[None])[0]-p)),
        'finite_features':values,'outside_finite_face':rejected,
        'interpretation':'Old inequality is attached to an off-triangle point; rejecting its infinite-plane row is not deleting a real finite contact.'}
    cc,tt,cs=fixture('contract');m=CavityModel(a,resolved,d2,approval);q64=quality(a['vertices'],a['faces'],cc)
    origin=np.array([16,16,-81]);ref=(a['vertices']-origin).astype(np.float32).astype(float)
    current=((a['vertices']-origin).astype(np.float32)+cc.astype(np.float32)).astype(float);_,ed,L=mesh_graph(ref,a['faces'])
    q32=quick_quality(ref,a['faces'],current-ref,ed,L)
    old_rejected=read(OLD/'contract/attempt_013_04/attempt.json')
    ccd={side:{'unresolved_pairs':len(read(OLD/side/'ccd_reference_chord.json.gz')['unresolved_coplanar_or_conditioned_pairs']),
        'full_certificate':False} for side in ['contract','expand']}
    write(ROOT/'reproduction.json',{'sources':{'expand':sources,'contract':cs},'finite_conflict':conflicts,
        'contract_float64':q64,'contract_float32':q32,'rejected_contract_face_quality':old_rejected['cavity_quality'],
        'old_CCD':ccd,'N16_failure_counts':[173,753,1838],'reference_volume':independent_volume(d2['reference_vertices'],d2['faces'])})
    protect();print('Reproduced finite conflict and float32 failure',q32['minimum_area_ratio'],flush=True)

if __name__=='__main__':run()
