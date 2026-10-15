"""Repeat local repair without overwriting the delivered candidate."""
from n21_common import *
from n21_robust_patch import repair

if __name__=='__main__':
    protect();a,d2,tv,tf,resolved,approval=inputs();original,_,_=fixture('contract')
    start=time.time();new,report,_=repair(a,d2,resolved,approval,original)
    delivered=np.load(ROOT/'robust_contract_r2/cavity_offset.npy')
    result={'byte_identical':new.tobytes()==delivered.tobytes(),
        'maximum_abs_error_mm':float(abs(new-delivered).max()),
        'policy':'FROZEN_GENERATOR_V1_PLUS_REQUIRED_FULL_V2_AUDIT','seconds':time.time()-start,
        'current_generator_sha256':sha(Path(__file__).with_name('n21_robust_patch.py')),
        'repeated_seed_faces':report['seed_faces_selected_by_rounding_budget'],
        'delivered_candidate_sha256':sha(ROOT/'robust_contract_r2/cavity_offset.npy')}
    write(ROOT/'repeat_patch.json',result);protect()
    if not result['byte_identical']:raise ValueError('Repeat repair differs from delivered candidate')
    print('REPEAT PATCH exact byte equality',flush=True)
