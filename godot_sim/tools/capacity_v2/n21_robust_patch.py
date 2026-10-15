"""Geometry-selected multi-face tangent patch with float32 error-budget margin.
No hardcoded source face, vertex deletion, or change to material topology.
"""
from n21_common import *
from n21_features import FiniteTissue
from build_cavity_morph_states import vertex_normals
from scipy.optimize import minimize
from scipy.sparse.csgraph import connected_components

ORIGIN=np.array([16.,16.,-81.])

def rounding_budget(v,f,d,policy='FULL_OPERATION_AUDIT_V2'):
    ref=v-ORIGIN;r32=ref.astype(np.float32);d32=d.astype(np.float32);position=r32+d32
    # Endpoint magnitude bounds every linear interpolation value. Include both
    # reference and displacement casts, addition ULP/2, and float64 arithmetic.
    maxabs=np.maximum(abs(r32),abs(position));ulp=abs(np.spacing(maxabs)).astype(float)
    eref=abs(r32.astype(float)-ref)+2*abs(np.spacing(ref))
    multiplication=abs(np.spacing(d32)).astype(float)/2
    parameter_rounding=(2**-24)*abs(d32.astype(float))
    displacement_error=abs(d32.astype(float)-d)+multiplication+parameter_rounding+ulp/2+2*abs(np.spacing(ref+d))
    displacement_error[np.all(d==0,axis=1)]=0
    error=eref+displacement_error
    if policy=='FROZEN_GENERATOR_V1':
        # Frozen trial-generation policy with a 2x reserve. The independently
        # executed FULL_OPERATION_AUDIT_V2 includes ALL operations and must pass
        # before this candidate has any robustness claim. Never use V1 alone as
        # a runtime certificate.
        error=eref+abs(d32.astype(float)-d)+ulp/2+2*abs(np.spacing(ref+d))
    eta=np.linalg.norm(error,axis=1);eta0=np.linalg.norm(eref,axis=1)
    x=v[f];y=(v+d)[f];e1=x[:,1]-x[:,0];e2=x[:,2]-x[:,0]
    E1=np.maximum(np.linalg.norm(e1,axis=1),np.linalg.norm(y[:,1]-y[:,0],axis=1));E2=np.maximum(np.linalg.norm(e2,axis=1),np.linalg.norm(y[:,2]-y[:,0],axis=1))
    def cross_error(e):
        p=e[f[:,1]]+e[f[:,0]];q=e[f[:,2]]+e[f[:,0]]
        return np.nextafter((E1*q+E2*p+p*q)*(1+64*np.finfo(float).eps),np.inf)
    ref_cross=np.linalg.norm(np.cross(e1,e2),axis=1);Eref=cross_error(eta0);Ecur=cross_error(eta)
    margin=np.divide(Ecur+1.35*Eref,ref_cross-Eref,out=np.full(len(f),np.inf),where=ref_cross>Eref)
    margin[np.all(d[f]==0,axis=(1,2))]=0
    return {'eta_mm':eta,'eta_reference_mm':eta0,'eta_displacement_mm':np.linalg.norm(displacement_error,axis=1),'ratio_margin':margin,'reference_cross_error':Eref,'current_cross_error':Ecur,
        'ratio_budget_rule':'(||e1||*delta_e2 + ||e2||*delta_e1 + delta_e1*delta_e2 + 1.35*reference_error)/(reference_cross-reference_error)',
        'internal_margin_multiplier':2.,'float32_addition_error_is_bounded_not_measured_only_at_one_endpoint':True}

def display_quality(v,f,d):
    r=(v-ORIGIN).astype(np.float32);_,edges,length=mesh_graph(r.astype(float),f);rows=[]
    for u in [0,.25,.5,.75,1.]:
        current=(r+np.float32(u)*d.astype(np.float32)).astype(float)
        rows.append({'u':u,**quick_quality(r.astype(float),f,current-r.astype(float),edges,length)})
    return rows

def repair(a,d2,resolved,approval,initial):
    model=CavityModel(a,resolved,d2,approval);v,f=model.v,model.f;d=initial.copy();_,base_area,_=triangle_data(v,f)
    budget=rounding_budget(v,f,d,policy='FROZEN_GENERATOR_V1');margin=budget['ratio_margin'];_,area,_=triangle_data(v+d,f);ratio=area/base_area
    seeds=np.flatnonzero((ratio<.8+2*margin)|(ratio>1.35-2*margin))
    movable=~model.fixed;seed_vertices=np.unique(f[seeds]);mask=np.zeros(len(v),bool);mask[seed_vertices]=True
    for _ in range(3):mask[model.edges[mask[model.edges].any(1)].ravel()]=True
    mask&=movable
    sub=model.graph[mask][:,mask];count,labels=connected_components(sub,directed=False);all_ids=np.flatnonzero(mask)
    target_volume=volume(d2['reference_vertices']+map_d2(d,d2),d2['faces']);reports=[]
    for component in range(count):
        ids=all_ids[labels==component]
        if len(ids)>180:
            reports.append({'vertices':len(ids),'status':'PATCH_TOO_LARGE_FOR_THIS_LOCAL_SQP'});continue
        active=np.zeros(len(v),bool);active[ids]=True;faceids=np.flatnonzero(active[f].any(1));edgeids=np.flatnonzero(active[model.edges].any(1));edges=model.edges[edgeids];length=model.length[edgeids]
        normal=vertex_normals(v+d,f)[ids];axis=np.eye(3)[np.argmin(abs(normal),axis=1)];b0=normalize(np.cross(normal,axis));b1=normalize(np.cross(normal,b0));basis=np.stack([b0,b1],1)
        start=d.copy();weights=np.ones(len(ids))
        # Boundary rings get a stronger shape penalty; they remain degrees of
        # freedom so a smooth feather replaces a one-face displacement impulse.
        inside_edges=model.edges[active[model.edges].any(1)];boundary=np.unique(inside_edges[~active[inside_edges].all(1)])
        weights[np.isin(ids,boundary)]=25
        def field(x):
            value=start.copy();value[ids]+=np.einsum('ni,nij->nj',x.reshape(-1,2),basis);return value
        local_target=volume(d2['reference_vertices']+map_d2(start,d2),d2['faces'])
        def constraints(x):
            value=field(x);cr,ar,_=triangle_data(v+value,f[faceids]);ratio=ar/base_area[faceids]
            grad=np.linalg.norm(value[edges[:,0]]-value[edges[:,1]],axis=1)/length
            grad_margin=(budget['eta_mm'][edges[:,0]]+budget['eta_mm'][edges[:,1]])/length
            return np.r_[ratio-(.8+2*margin[faceids]),(1.35-2*margin[faceids])-ratio,.2-2*grad_margin-grad]
        def equal(x):return (volume(d2['reference_vertices']+map_d2(field(x),d2),d2['faces'])-local_target)*1000
        def energy(x):
            delta=field(x)-start;diff=delta[edges[:,0]]-delta[edges[:,1]]
            return float(np.sum(x.reshape(-1,2)**2*weights[:,None])+np.sum(diff**2/length[:,None]**2)*.05+1e4*equal(x)**2)
        result=minimize(energy,np.zeros(len(ids)*2),method='SLSQP',bounds=[(-.03,.03)]*(len(ids)*2),
            constraints=[{'type':'ineq','fun':constraints}],options={'maxiter':150,'ftol':1e-13})
        candidate=field(result.x)
        # A feasible trust-region iterate need not be an objective optimum.
        # Accept only against the ORIGINAL hard gates and a freshly recomputed
        # conservative roundoff bound, never by relaxing the 0.8/1.35 limits.
        final_budget=rounding_budget(v,f,candidate,policy='FROZEN_GENERATOR_V1');C0=2*base_area;C=2*triangle_data(v+candidate,f)[1]
        lower=(C-final_budget['current_cross_error'])/(C0+final_budget['reference_cross_error'])
        upper=(C+final_budget['current_cross_error'])/(C0-final_budget['reference_cross_error'])
        qhard=quick_quality(v,f,candidate,model.edges,model.length)
        valid=bool(lower[faceids].min()>=.8 and upper[faceids].max()<=1.35 and abs(equal(result.x))<1e-6
            and not qhard['bad_edges'] and not (set(qhard['bad_faces'])&set(faceids.tolist())) and np.linalg.norm(candidate-start,axis=1).max()<=.05)
        reports.append({'vertices':len(ids),'source_vertex_ids':ids.tolist(),'source_incident_faces':faceids.tolist(),
            'optimizer_success':bool(result.success),'status':'PATCH_UPDATED' if valid else 'PATCH_REJECTED','message':result.message,
            'minimum_internal_margin_residual':float(constraints(result.x).min()),'volume_residual_mL':float(equal(result.x)/1000),
            'maximum_correction_mm':float(np.linalg.norm(candidate-start,axis=1).max()),'iterations':int(result.nit)})
        if valid:d=candidate
    final_budget=rounding_budget(v,f,d,policy='FROZEN_GENERATOR_V1');C0=2*base_area;C=2*triangle_data(v+d,f)[1]
    lower=(C-final_budget['current_cross_error'])/(C0+final_budget['reference_cross_error']);upper=(C+final_budget['current_cross_error'])/(C0-final_budget['reference_cross_error'])
    return d,{'seed_faces_selected_by_rounding_budget':seeds.tolist(),'patches':reports,
        'generation_margin_policy':'FROZEN_GENERATOR_V1_WITH_DOUBLE_RESERVE','mandatory_independent_margin_audit':'FULL_OPERATION_AUDIT_V2',
        'endpoint_roundoff_bound_minimum_area_ratio':float(lower.min()),'endpoint_roundoff_bound_maximum_area_ratio':float(upper.max()),
        'maximum_ratio_margin':float(margin.max()),'budget_margin_on_seed_faces':margin[seeds].tolist(),
        'target_research_candidate_volume_mL':target_volume,'actual_repaired_volume_mL':volume(d2['reference_vertices']+map_d2(d,d2),d2['faces']),
        'full_float64_quality':quality(v,f,d),'full_float32_five_levels':display_quality(v,f,d),
        'hardcoded_special_face':False,'topology_changed':False,'maximum_correction_mm':float(np.linalg.norm(d-initial,axis=1).max())},budget

def run():
    protect();a,d2,tv,tf,resolved,approval=inputs();c,old_t,sources=fixture('contract');new,r,b=repair(a,d2,resolved,approval,c)
    root=ROOT/('robust_contract_r2' if '--r2' in sys.argv else 'robust_contract');root.mkdir(exist_ok=True)
    np.save(root/'cavity_offset.npy',new);np.save(root/'ratio_roundoff_budget.npy',b['ratio_margin']);np.save(root/'vertex_roundoff_budget_mm.npy',b['eta_mm'])
    tm=FiniteTissue(a,tv,tf,resolved);t,contact=tm.solve_finite(new)
    np.save(root/'tissue_offset.npy',t);gzip_write(root/'contact_report.json.gz',contact)
    r['tissue_quality']=quality(tv,tf,t);r['tissue_float32_five_levels']=display_quality(tv,tf,t);r['sources']=sources
    r['continuous_collision_certified']=False;r['formal_N2']=False
    write(root/'repair_report.json',r);protect();print('ROBUST PATCH',r['maximum_correction_mm'],'seeds',r['seed_faces_selected_by_rounding_budget'],'f32pass',all(s['pass'] for s in r['full_float32_five_levels']),flush=True)

if __name__=='__main__':run()
