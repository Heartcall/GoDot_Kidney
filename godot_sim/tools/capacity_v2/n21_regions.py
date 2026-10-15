"""Reduced regional block-SQP research: optimize TOTAL coordinates, so prior
motion can retreat. Finite-contact Jacobians include an incremental tissue solve.
No +/-30 jump, no production resource, no acceptance without continuous gates.
"""
from n21_common import *
from n21_features import ContactState,FiniteTissue,finite_features
from n21_robust_patch import rounding_budget,display_quality
from audit_tissue_cavity import contact_pairs
from scipy.optimize import minimize,LinearConstraint,linprog

def regional_rows(m,d2,q,B):
    c=np.einsum('k,kni->ni',q,B);x=m.v+c;cross,area,_=triangle_data(x,m.f);a0=triangle_data(m.v,m.f)[1];ratio=area/a0
    budget=rounding_budget(m.v,m.f,c)['ratio_margin'];ids=np.flatnonzero((ratio<.84+2*budget)|(ratio>1.30-2*budget))
    nhat=normalize(cross[ids]);tri=x[m.f[ids]];grads=np.stack([.5*np.cross(nhat,tri[:,2]-tri[:,1]),.5*np.cross(nhat,tri[:,0]-tri[:,2]),.5*np.cross(nhat,tri[:,1]-tri[:,0])],1)
    J=np.einsum('fvi,kfvi->fk',grads,B[:,m.f[ids]])/a0[ids,None]
    rows=[J];lo=[.8+2*budget[ids]-ratio[ids]];hi=[1.35-2*budget[ids]-ratio[ids]]
    diff=c[m.edges[:,0]]-c[m.edges[:,1]];grad=np.linalg.norm(diff,axis=1)/m.length;ei=np.flatnonzero(grad>.17)
    if len(ei):
        de=B[:,m.edges[ei,0]]-B[:,m.edges[ei,1]];unit=normalize(diff[ei]);G=np.einsum('ei,kei->ek',unit,de)/m.length[ei,None]
        rows.append(G);lo.append(np.full(len(ei),-np.inf));hi.append(.2-grad[ei])
    return c,np.concatenate(rows),np.concatenate(lo),np.concatenate(hi),ids,ei

def propose(m,d2,B,q0,contact_J,contact_gap,requested_target):
    flat=B.reshape(len(B),-1);G=flat@flat.T;prior=[]
    for name in m.names:
        group=m.group[np.flatnonzero(m.local==m.names.index(name))[0]]
        prior.append([0,1,1,1,.22,.18,.10][group])
    penalty=.001/np.maximum(prior,.1)**2;H=G+np.diag(penalty);q=q0.copy();iterations=[]
    for step in range(3):
        c,J,lo,hi,faces,edges=regional_rows(m,d2,q,B)
        v=volume(d2['reference_vertices']+map_d2(c,d2),d2['faces']);g=volume_gradient_source(c,d2);derivative=np.einsum('ni,kni->k',g,B)
        baseline_dir=np.ones(len(q));alpha=(requested_target-v)/max(float(derivative@baseline_dir),1e-12);wish=alpha*baseline_dir
        constraints=[LinearConstraint(derivative[None],requested_target-v,requested_target-v)]
        if len(J):constraints.append(LinearConstraint(J,lo,hi))
        if len(contact_J):constraints.append(LinearConstraint(contact_J,-contact_gap-contact_J@(q-q0),np.inf))
        objective_scale=max(float(np.diag(H).max()),1.)
        objective=lambda z:(float(.5*(z-wish)@H@(z-wish)/objective_scale),H@(z-wish)/objective_scale)
        lower=np.maximum(-.015-(q-q0),-q);upper=.015-(q-q0)
        upper_rows=np.isfinite(hi);lower_rows=np.isfinite(lo)
        A=np.concatenate([J[upper_rows],-J[lower_rows],-contact_J]);bound=np.r_[hi[upper_rows],-lo[lower_rows],contact_gap+contact_J@(q-q0)]
        lp=linprog(np.zeros(len(q)),A_ub=A,b_ub=bound,A_eq=derivative[None],b_eq=[requested_target-v],bounds=list(zip(lower,upper)),method='highs')
        initial=lp.x if lp.success else np.zeros(len(q))
        result=minimize(objective,initial,jac=True,method='SLSQP',bounds=list(zip(lower,upper)),constraints=constraints,
            options={'maxiter':150,'ftol':1e-12})
        linear_feasible=bool(abs(derivative@result.x-(requested_target-v))<1e-9 and np.max(A@result.x-bound)<=1e-10)
        iterations.append({'iteration':step,'success':bool(result.success),'message':result.message,'current_volume_mL':v,
            'LP_feasible_initialization':bool(lp.success),'linear_step_feasible_at_original_tolerance':linear_feasible,
            'linear_capacity_residual_mL':float(derivative@result.x-(requested_target-v)),
            'minimum_linear_contact_residual_mm':float((contact_gap+contact_J@(q-q0+result.x)).min()) if len(contact_J) else None,
            'q_at_iteration':q.tolist(),
            'target_mL':requested_target,'quality_faces':faces.tolist(),'quality_edges':edges.tolist(),'delta_q':result.x.tolist()})
        if not linear_feasible:break
        q+=result.x
    return q,iterations

def run():
    protect();a,d2,tv,tf,resolved,approval=inputs();m=CavityModel(a,resolved,d2,approval);tm=FiniteTissue(a,tv,tf,resolved)
    base_c,base_t,sources=fixture('expand');root=ROOT/'regional_sqp';root.mkdir(exist_ok=True)
    B=np.array([m.response('expand',np.eye(len(m.names))[k]) for k in range(len(m.names))]);flat=B.reshape(len(B),-1)
    q0=np.linalg.lstsq(flat@flat.T,flat@base_c.ravel(),rcond=1e-12)[0]
    reconstruction=np.einsum('k,kni->ni',q0,B);err=float(abs(reconstruction-base_c).max())
    pairs=contact_pairs(m.v+base_c,m.f,tv+base_t,tf);features=[]
    for ci,ti in pairs:
        ff,_=finite_features(m.v+base_c,tv+base_t,m.f[ci],tf[ti],int(ci),int(ti),m.v+base_c,tv+base_t)
        features.extend(ff)
    state=ContactState();state.pairs={tuple(p) for p in pairs.tolist()};state.update(features);state.stage='READY_TO_PROPOSE'
    cw=np.array([f['cavity_weights'] for f in features]);tw=np.array([f['tissue_weights'] for f in features]);normals=np.array([f['normal'] for f in features]);cids=np.array([f['cavity_vertices'] for f in features]);tids=np.array([f['tissue_vertices'] for f in features]);gap=np.array([f['current_normal_gap_mm'] for f in features])
    J=np.zeros((len(features),len(B)))
    for k,mode in enumerate(B):
        hard,rhs=tm.target(mode);delta=hard.copy();delta[tm.free]=tm.factor.solve(rhs)
        rel=np.einsum('nv,nvi->ni',tw,delta[tids])-np.einsum('nv,nvi->ni',cw,mode[cids]);J[:,k]=np.einsum('ni,ni->n',normals,rel)
    # Kinematic identities / zero response rows are retained in the state. Only
    # exact-zero inactive equations are absent from numerical SQP linear algebra.
    nonzero=np.linalg.norm(J,axis=1)>1e-12;zero_conflicts=np.flatnonzero(~nonzero&(gap < -1e-10))
    active_J=J[nonzero];active_gap=gap[nonzero]
    settings={'solver':'N21R_TOTAL_REGIONAL_BLOCK_SQP_V1','trust_q':.015,'requested_ratio':1.05,'source_solver_sha256':sha(__file__)}
    state.numerical={'q':q0.copy(),'cavity':base_c.copy(),'tissue':base_t.copy(),'contact_J':active_J.copy(),'contact_gap':active_gap.copy()}
    initial_pairs_snapshot=state.pairs.copy()
    state.save(root/'contact_checkpoint.json',sources,settings)
    np.save(root/'q_checkpoint.npy',q0);np.save(root/'cavity_checkpoint.npy',base_c);np.save(root/'tissue_checkpoint.npy',base_t)
    q,trace=propose(m,d2,B,q0,active_J,active_gap,1.05*TARGETS['reference_mL']);c=np.einsum('k,kni->ni',q,B)
    candidate_t,contact=tm.solve_finite(c,state.pairs,state,max_outer=3,warm_cavity=base_c,warm_tissue=base_t)
    cq=quality(m.v,m.f,c);tq=quality(tv,tf,candidate_t);fp=display_quality(m.v,m.f,c)
    np.save(root/'cavity_proposal.npy',c);np.save(root/'tissue_proposal.npy',candidate_t);gzip_write(root/'contact_report.json.gz',contact)
    # Full contact state, inactive history and all numerical inputs survive
    # restart; recompute exactly the same proposal from the transaction boundary.
    restored=ContactState.load(root/'contact_checkpoint.json',sources,settings)
    q_saved=restored.numerical['q'];q_replay,retrace=propose(m,d2,B,q_saved,restored.numerical['contact_J'],restored.numerical['contact_gap'],1.05*TARGETS['reference_mL'])
    replay_equal=np.array_equal(q,q_replay)
    report={'status':'ISOLATED_RESEARCH_PROPOSAL_NOT_PRODUCTION','target_global_mL':TARGETS['expand_mL'],'this_progressive_probe_target_mL':1.05*TARGETS['reference_mL'],
        'actual_D2_oriented_integral_mL':volume(d2['reference_vertices']+map_d2(c,d2),d2['faces']),
        'source_basis_reconstruction_max_error_mm':err,'total_q_optimized_not_increment_only':True,'q_before':q0.tolist(),'q_after':q.tolist(),
        'negative_adjustment_regions':[m.names[i] for i in np.flatnonzero(q-q0 < -1e-8)],'iterations':trace,'contact_features':len(features),
        'zero_response_conflicts':zero_conflicts.tolist(),'cavity':cq,'tissue':tq,'float32':fp,'full_contact_state_restart_bitwise_q_equal':replay_equal,
        'all_pairs_restored':restored.pairs==initial_pairs_snapshot,'full_continuous_safety_certified':False,'formal_N2':False,
        'progressive_target_reached':bool(abs(volume(d2['reference_vertices']+map_d2(c,d2),d2['faces'])-1.05*TARGETS['reference_mL'])<1e-6),
        'returned_field_is_baseline':bool(np.linalg.norm(c-base_c)<1e-9),
        'static_candidate_pass':bool(trace[-1]['linear_step_feasible_at_original_tolerance'] and cq['quality_gate_passed'] and tq['quality_gate_passed'] and contact['static_candidate_pass'] and all(x['pass'] for x in fp)),
        'capacity_attribution':region_contributions(a,d2,c,m.group,GROUPS),
        'physical_interface_fixed_maximum_mm':float(np.linalg.norm(c[a['port_fixed_masks'].any(0)],axis=1).max())}
    write(root/'report.json',report);protect();print('REGIONAL SQP',report['actual_D2_oriented_integral_mL'],report['static_candidate_pass'],'restart',replay_equal,flush=True)

if __name__=='__main__':run()
