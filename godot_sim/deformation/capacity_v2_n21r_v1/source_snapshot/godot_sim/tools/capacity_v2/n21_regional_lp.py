"""Diagnose the failed SQP's LOCAL linearized trust-region feasibility.
An LP bound on this reduced model is never a global geometric capacity limit."""
from n21_common import *
from n21_regions import regional_rows
from scipy.optimize import linprog

def run():
    protect();a,d2,tv,tf,resolved,approval=inputs();m=CavityModel(a,resolved,d2,approval);tm=TissueModel(a,tv,tf,resolved)
    root=ROOT/'regional_sqp';state=read(root/'contact_checkpoint.json');features=list(state['features'].values());q0=np.load(root/'q_checkpoint.npy')
    B=np.array([m.response('expand',np.eye(len(m.names))[k]) for k in range(len(m.names))])
    c,Jshape,lo,hi,faces,edges=regional_rows(m,d2,q0,B)
    cw=np.array([f['cavity_weights'] for f in features]);tw=np.array([f['tissue_weights'] for f in features]);norm=np.array([f['normal'] for f in features])
    ci=np.array([f['cavity_vertices'] for f in features]);ti=np.array([f['tissue_vertices'] for f in features]);gap=np.array([f['current_normal_gap_mm'] for f in features]);J=np.zeros((len(features),len(B)))
    for k,mode in enumerate(B):
        hard,rhs=tm.target(mode);delta=hard.copy();delta[tm.free]=tm.factor.solve(rhs)
        relative=np.einsum('nv,nvi->ni',tw,delta[ti])-np.einsum('nv,nvi->ni',cw,mode[ci]);J[:,k]=np.einsum('ni,ni->n',norm,relative)
    nonzero=np.linalg.norm(J,axis=1)>1e-12;J=J[nonzero];gap=gap[nonzero]
    g=np.einsum('ni,kni->k',volume_gradient_source(c,d2),B)
    upper=np.isfinite(hi);lower=np.isfinite(lo);A=np.concatenate([Jshape[upper],-Jshape[lower],-J]);b=np.r_[hi[upper],-lo[lower],gap]
    result=linprog(-g,A_ub=A,b_ub=b,bounds=list(zip(np.maximum(-.015,-q0),np.full(len(q0),.015))),method='highs')
    current=volume(d2['reference_vertices']+map_d2(c,d2),d2['faces']);requested=1.05*TARGETS['reference_mL']-current
    report={'solver_status':int(result.status),'success':bool(result.success),'message':result.message,
        'local_linear_model_requested_increment_mL':requested,'local_linear_model_maximum_increment_mL':float(g@result.x) if result.success else None,
        'maximum_inequality_violation':float(np.maximum(A@result.x-b,0).max()) if result.success else None,
        'global_geometry_infeasibility_proved':False,'global_safe_capacity_bound':None,
        'meaning':'Only reduced coefficients, fixed tissue increment operator, current finite-feature linearization and q trust bounds. Not full joint deformation space.',
        'linear_volume_gradient':g.tolist(),'region_names':m.names,'constraint_count':len(b)}
    if result.success:
        report['delta_q']=result.x.tolist();report['active_rows']=np.flatnonzero(abs(A@result.x-b)<1e-8).tolist()
    write(root/'local_feasibility_lp.json',report);np.save(root/'finite_contact_linear_jacobian.npy',J);np.save(root/'finite_contact_linear_gaps.npy',gap)
    protect();print('LOCAL LP',report['local_linear_model_maximum_increment_mL'],'requested',requested,flush=True)

if __name__=='__main__':run()
