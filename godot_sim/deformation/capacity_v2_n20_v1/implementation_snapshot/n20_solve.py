"""Adaptive predictor, unilateral tissue contact solve, reject/backtrack and
regional mobility redistribution. Every product is NON_PRODUCTION_RESEARCH.
No claim that a reduced solver's stop is the global feasible-volume limit.
"""
from n20_model import *
from scipy.optimize import brentq
from n16_closure_and_regions import closure_variants

def block_regions(model,quality_c,quality_t,ct,tm,trace=()):
    vertices=set()
    for face in quality_c.get('bad_faces',[]):vertices.update(model.f[face].tolist())
    for edge in quality_c.get('bad_edges',[]):vertices.update(edge)
    tissue=set()
    for face in quality_t.get('bad_faces',[]):tissue.update(tm.f[face].tolist())
    for edge in quality_t.get('bad_edges',[]):tissue.update(edge)
    if tissue:vertices.update(model.f[tm.donor[list(tissue)]].ravel().tolist())
    for r in ct.get('rows',[]):
        if r['class']=='FINITE_TRANSVERSE_CROSSING':vertices.update(model.f[r['cavity_face']].tolist())
    # A conservative contact halfspace can conflict with an exact shared point
    # even when no finite crossing survives. Do not falsely call it penetration;
    # reduce its local cavity response and let other regions carry the volume.
    if trace:
        qp=trace[-1]['qp']
        for ci,ti,vi,gap in qp.get('fixed_conflicts',[]):vertices.update(model.f[ci].tolist())
        if not qp.get('qp_converged',True) and not qp.get('fixed_conflicts'):
            for ci,ti,vi in qp.get('active_sources',[]):vertices.update(model.f[ci].tolist())
    if not vertices:return []
    return sorted(set(model.local[list(vertices)].tolist())-{model.names.index('FIXED')})

def capacity_step(model,d2,current,side,mobility,requested):
    direction=model.response(side,mobility);gradient=volume_gradient_source(current,d2)
    derivative=float(np.einsum('ij,ij->',gradient,direction));vnow=volume(d2['reference_vertices']+map_d2(current,d2),d2['faces'])
    signed=1 if side=='expand' else -1
    if signed*derivative<=1e-12:return None,{'reason':'NO_USABLE_CAPACITY_GRADIENT','derivative':derivative}
    target=vnow+signed*requested;dv=map_d2(direction,d2)
    co=volume_coefficients(d2['reference_vertices']+map_d2(current,d2),d2['faces'],dv)
    q0=requested/abs(derivative);hi=2*q0
    fun=lambda q:np.polynomial.polynomial.polyval(q,co)-target
    while fun(0)*fun(hi)>0 and hi<10:hi*=2
    q=brentq(fun,0,hi,xtol=1e-13)
    return current+q*direction,{'linear_prediction_q':q0,'actual_integral_q':q,'derivative_mL_per_q':derivative,'target_step_mL':target,'coefficients_mL':co.tolist()}

def attempt(model,tm,d2,approval,cv,tt,candidate,active_pairs,step_dir):
    """Rejected predictors may intersect. No such trial becomes an accepted
    trajectory state, and no penetrating state is 'repaired after acceptance'.
    Continuous collision certification is a separate mandatory promotion gate.
    """
    q_c=quick_quality(model.v,model.f,candidate,model.edges,model.length)
    report={'cavity_quality':q_c,'status':'REJECTED','predictor_is_not_accepted_geometry':True}
    if not q_c['pass']:
        report['reason']='CAVITY_REFERENCE_QUALITY'
        return None,report,active_pairs
    pairs=set(active_pairs);last_ct={};trace=[]
    for iteration in range(5):
        tissue,qp=tm.solve(candidate,pairs)
        q_t=quick_quality(tm.v,tm.f,tissue,tm.edges,tm.length)
        ct=scan_cross(model.a,tm.v,tm.f,candidate,tissue)
        new={(r['cavity_face'],r['tissue_face']) for r in ct['rows'] if r['class']=='FINITE_TRANSVERSE_CROSSING'}
        trace.append({'iteration':iteration,'crossings':len(new),'qp':qp,'tissue_quality':q_t})
        last_ct=ct
        if not new:
            if q_t['pass'] and qp['qp_converged']:
                # Guard nonlinear quality over the proposed increment, normalized
                # to REFERENCE, not merely the last accepted step.
                continuous_c=continuous_area_bounds(model.v,model.f,candidate)
                continuous_t=continuous_area_bounds(tm.v,tm.f,tissue)
                if any(r['minimum_area_ratio']<.8 or r['maximum_area_ratio']>1.35 or r['minimum_oriented_area_ratio']<=0 for r in [continuous_c,continuous_t]):
                    report['reason']='CONTINUOUS_REFERENCE_CHORD_QUALITY';break
                dv=d2['reference_vertices']+map_d2(candidate,d2)
                variants=closure_variants(dv,d2,approval)
                if not all(r['geometrically_valid_at_sample'] for r in variants):
                    report['reason']='MEASUREMENT_CAP_OR_WALL_INVALID';report['closure_variants']=variants;break
                # Fixed approved cap faces are authoritative. Alternative legal
                # ear order is sensitivity only, no per-state template switching.
                dc=classify(dv,d2['faces'],dv,d2['faces'],self_bbox_pairs(dv,d2['faces']))
                cc=classify(model.v+candidate,model.f,model.v+candidate,model.f,self_bbox_pairs(model.v+candidate,model.f))
                report.update({'D2_self':dc,'cavity_self':cc,'closure_variants':variants})
                if dc['confirmed_transverse_crossings'] or cc['confirmed_transverse_crossings']:
                    report['reason']='SELF_OR_MEASUREMENT_CROSSING';break
                report.update({'status':'DISCRETE_PREDICTOR_PASSED_NOT_CONTINUOUSLY_CERTIFIED','cavity_continuous_area_reference_chord':continuous_c,
                    'tissue_continuous_area_reference_chord':continuous_t,'actual_D2_mL':volume(dv,d2['faces'])})
                report['reason']='DISCRETE_GATES_PASSED';report['contact_trace']=trace;report['cavity_tissue']=ct
                write(step_dir/'attempt.json',report)
                return tissue,report,pairs
            report['reason']='TISSUE_QUALITY_OR_ACTIVE_QP';break
        if new<=pairs:
            report['reason']='FINITE_CONTACT_NOT_RESOLVED_BY_LOCAL_HALFSPACES';break
        pairs|=new
    report.update({'contact_trace':trace,'cavity_tissue':last_ct,'tissue_quality':q_t})
    report.setdefault('reason','CONTACT_ACTIVE_ITERATION_LIMIT')
    write(step_dir/'attempt.json',report)
    return None,report,pairs

def solve(side,max_steps=20):
    protected();a,d2,tv,tf,resolved,approval=inputs();model=CavityModel(a,resolved,d2,approval);tm=TissueModel(a,tv,tf,resolved)
    directory=OUT/(side+'_redistributed' if '--redistributed' in sys.argv else side);directory.mkdir(parents=True,exist_ok=True)
    cv=np.zeros_like(model.v);tt=np.zeros_like(tv);mobility=np.ones(len(model.names));pairs=set();ref=volume(d2['reference_vertices'],d2['faces'])
    authorized=read(OUT/'authorization_and_targets.json')
    target=authorized['expand_target_mL' if side=='expand' else 'contract_target_mL'];states=[];rejections=[];step_size=.01*ref
    np.save(directory/'cavity_000.npy',cv);np.save(directory/'tissue_000.npy',tt)
    if '--resume' in sys.argv and (directory/'trajectory.json').exists():
        old=read(directory/'trajectory.json');states=old['states'];rejections=old['rejections'];mobility=np.array([old['mobility'][n] for n in model.names])
        index=len(states);cv=np.load(directory/f'cavity_{index:03}.npy');tt=np.load(directory/f'tissue_{index:03}.npy')
        for state in states:
            r=read(OUT/state['attempt']/'attempt.json')
            for trace in r.get('contact_trace',[]):
                pairs.update((x[0],x[1]) for x in trace['qp'].get('active_sources',[]))
    for iteration in range(len(states),max_steps):
        vnow=volume(d2['reference_vertices']+map_d2(cv,d2),d2['faces']);remaining=abs(target-vnow)
        if remaining<1e-6:break
        desired=min(step_size,remaining);accepted=False
        for retry in range(5):
            candidate,pred=capacity_step(model,d2,cv,side,mobility,desired)
            if candidate is None:break
            stepdir=directory/f'attempt_{iteration:03}_{retry:02}';stepdir.mkdir(exist_ok=True)
            start=time.time();tissue,r,pair_candidate=attempt(model,tm,d2,approval,cv,tt,candidate,pairs,stepdir)
            print(side,iteration,retry,'V',round(volume(d2['reference_vertices']+map_d2(candidate,d2),d2['faces']),6),r['reason'],'seconds',round(time.time()-start,1),flush=True)
            r['prediction']=pred;r['from_capacity_mL']=vnow
            if tissue is not None:
                cv=candidate;tt=tissue;pairs=pair_candidate;accepted=True
                index=len(states)+1;np.save(directory/f'cavity_{index:03}.npy',cv);np.save(directory/f'tissue_{index:03}.npy',tt)
                contributions=region_contributions(a,d2,cv,model.group,GROUPS)
                states.append({'index':index,'capacity_mL':r['actual_D2_mL'],'ratio':r['actual_D2_mL']/ref,'attempt':stepdir.relative_to(OUT).as_posix(),
                    'maximum_cavity_mm':float(np.linalg.norm(cv,axis=1).max()),'maximum_tissue_mm':float(np.linalg.norm(tt,axis=1).max()),
                    'cavity_quality':r['cavity_quality'],'tissue_quality':r['contact_trace'][-1]['tissue_quality'],
                    'active_pairs':len(pairs),'capacity_attribution':contributions,'wall_clock_seconds':time.time()-start})
                write(stepdir/'attempt.json',r);break
            blocked=block_regions(model,r['cavity_quality'],r.get('tissue_quality',{}),r.get('cavity_tissue',{}),tm,r.get('contact_trace',[]))
            for region in blocked:mobility[region]*=.25
            rejections.append({'iteration':iteration,'retry':retry,'reason':r['reason'],'trial_integral_mL':volume(d2['reference_vertices']+map_d2(candidate,d2),d2['faces']),
                'blocked_regions':[model.names[k] for k in blocked],'mobility_after':{model.names[k]:float(mobility[k]) for k in blocked},'attempt':stepdir.relative_to(OUT).as_posix()})
            write(stepdir/'attempt.json',r)
            # Activate finite pairs for the next independent predictor. They are
            # conservative constraints, not permission to keep the failed shape.
            pairs|=pair_candidate
            desired*=.5
        write(directory/'trajectory.json',{'direction':side,'target_mL':target,'reference_mL':ref,'states':states,'rejections':rejections,
            'target_reached_by_discrete_predictors':bool(states and abs(states[-1]['capacity_mL']-target)<1e-6),
            'continuous_collision_certificate':False,'runtime_eligible':False,
            'stop_is_global_feasibility_limit':False,'stop_reason':'ITERATION_RESEARCH_BUDGET' if accepted else 'LOCAL_CONSTRAINT_LINESEARCH_STALLED',
            'mobility':dict(zip(model.names,mobility.tolist()))})
        if not accepted:break
    protected()

if __name__=='__main__':solve(sys.argv[1] if len(sys.argv)>1 else 'expand',int(sys.argv[2]) if len(sys.argv)>2 else 20)
