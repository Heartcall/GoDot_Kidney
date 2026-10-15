"""Frozen failed N1.6 cavity shapes are regression fixtures ONLY, never N2.0
drivers. Can unilateral contact coordination improve their tissue crossings?
No failed fixture is promoted, even when its crossing count is reduced.
"""
from n20_model import *

def run():
    protected();a,d2,tv,tf,resolved,approval=inputs();tm=TissueModel(a,tv,tf,resolved);results=[]
    old=PROJECT/'deformation/capacity_v2_n16_v1/prototypes/thin_face_corrected'
    for name in ['S1_expand','S2_expand','S3_expand']:
        fixture=old/name;cv=np.load(fixture/'research_cavity_offset.npy');old_t=np.load(fixture/'research_tissue_offset.npy')
        baseline=read(fixture/'contacts/u100.json')['results']['cavity_tissue'];pre=read(fixture/'preassessment.json')
        root=OUT/'regression'/name;root.mkdir(parents=True,exist_ok=True)
        pairs={(r['cavity_face'],r['tissue_face']) for r in baseline['rows'] if r['class']=='FINITE_TRANSVERSE_CROSSING'}
        records=[];best=None
        for iteration in range(5):
            t,qp=tm.solve(cv,pairs);ct=scan_cross(a,tv,tf,cv,t);q=quick_quality(tv,tf,t,tm.edges,tm.length)
            count=ct['confirmed_transverse_crossings'];new={(r['cavity_face'],r['tissue_face']) for r in ct['rows'] if r['class']=='FINITE_TRANSVERSE_CROSSING'}
            gzip_write(root/f'iteration_{iteration:02}.json.gz',{'qp':qp,'cavity_tissue':ct,'tissue_quality':q})
            records.append({'iteration':iteration,'confirmed_crossings':count,'tissue_quality':q,'qp_converged':qp['qp_converged'],
                'fixed_conflicts':qp.get('fixed_conflicts',[]),'unresolved_original_straddles':len(qp.get('unresolved_original_straddles',[]))})
            if best is None or count<best[0]:best=(count,t,iteration)
            print('REGRESSION',name,iteration,'old',baseline['confirmed_transverse_crossings'],'new',count,'quality',q['pass'],'qp',qp['qp_converged'],flush=True)
            if not count or new<=pairs:break
            pairs|=new
        np.save(root/'best_tissue_offset_RESEARCH_ONLY.npy',best[1]);cq=quality(a['vertices'],a['faces'],cv)
        result={'fixture':name,'fixture_cavity_sha256':sha(fixture/'research_cavity_offset.npy'),'fixture_tissue_sha256':sha(fixture/'research_tissue_offset.npy'),
            'frozen_cavity_actual_integral_mL':pre['actual_D2_mL'],'old_confirmed_transverse_pairs':baseline['confirmed_transverse_crossings'],
            'best_new_confirmed_transverse_pairs':best[0],'best_iteration':best[2],'iterations':records,'cavity_quality':cq['quality_gate_passed'],
            'full_self_and_continuous_collision_verified':False,'runtime_eligible':False,'is_new_capacity_solver_candidate':False}
        write(root/'comparison.json',result);results.append(result)
    write(OUT/'regression/comparison.json',{'fixtures':results,'old_failure_counts_preserved':[173,753,1838],
        'endpoint_reduction_is_not_safe_full_trajectory':True});protected()

if __name__=='__main__':run()
