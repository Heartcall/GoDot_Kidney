"""One diagnosed local fixed-topology tangential quality repair experiment.
No vertex deletion or edge collapse. Not a new accepted solver endpoint.
"""
from n20_model import *
from n20_solve import capacity_step
from scipy.optimize import minimize

def run():
    protected();a,d2,tv,tf,resolved,approval=inputs();m=CavityModel(a,resolved,d2,approval)
    tr=read(OUT/'contract/trajectory.json');n=len(tr['states']);current=np.load(OUT/'contract'/f'cavity_{n:03}.npy')
    last=tr['rejections'][-1];mob=np.array([tr['mobility'][name] for name in m.names])
    for name in last['blocked_regions']:mob[m.names.index(name)]/=.25
    r=read(OUT/last['attempt']/'attempt.json');desired=abs(r['prediction']['target_step_mL']-r['from_capacity_mL'])
    candidate,pred=capacity_step(m,d2,current,'contract',mob,desired);before=quick_quality(m.v,m.f,candidate,m.edges,m.length)
    bad=np.array(before['bad_faces'],int);mask=np.zeros(len(m.v),bool);mask[np.unique(m.f[bad])]=True
    for _ in range(1):mask[m.edges[mask[m.edges].any(1)].ravel()]=True
    mask[m.fixed]=False;ids=np.flatnonzero(mask);faces=np.flatnonzero(mask[m.f].any(1));edge_ids=np.flatnonzero(mask[m.edges].any(1))
    v=m.v+candidate;normal=vertex_normals(v,m.f)[ids];axis=np.eye(3)[np.argmin(abs(normal),axis=1)]
    b0=normalize(np.cross(normal,axis));b1=normalize(np.cross(normal,b0));basis=np.stack([b0,b1],1)
    area0=triangle_data(m.v,m.f[faces])[1];edges=m.edges[edge_ids];length=m.length[edge_ids];c0=triangle_data(m.v,m.f[faces])[0]
    def field(x):
        result=candidate.copy();result[ids]+=np.einsum('ni,nij->nj',x.reshape(-1,2),basis);return result
    def constraints(x):
        d=field(x);cross,area,_=triangle_data(m.v+d,m.f[faces]);ratio=area/area0
        gradient=np.linalg.norm(d[edges[:,0]]-d[edges[:,1]],axis=1)/length
        orient=np.einsum('ij,ij->i',cross,c0)/(4*area0**2)
        return np.r_[ratio-.80001,1.34999-ratio,.19999-gradient,orient-1e-5]
    def energy(x):
        correction=field(x)-candidate;diff=correction[edges[:,0]]-correction[edges[:,1]]
        return float(x@x+np.sum(diff**2/length[:,None]**2)*.01)
    result=minimize(energy,np.zeros(len(ids)*2),method='SLSQP',bounds=[(-.03,.03)]*(len(ids)*2),
        constraints=[{'type':'ineq','fun':constraints}],options={'maxiter':100,'ftol':1e-13})
    corrected=field(result.x);after=quick_quality(m.v,m.f,corrected,m.edges,m.length)
    root=OUT/'tangential_repair';root.mkdir(exist_ok=True)
    np.save(root/'rejected_cavity_offset.npy',candidate);np.save(root/'tangential_cavity_offset_RESEARCH_ONLY.npy',corrected);np.save(root/'patch_source_vertex_ids.npy',ids)
    write(root/'experiment.json',{'status':'LOCAL_QUALITY_EXPERIMENT_NOT_FULL_GEOMETRIC_VALIDATION','diagnosed_source_face_ids':bad.tolist(),
        'method':'Two tangent DOFs per free patch vertex; SQP minimum correction and edge regularization; constraints on all patch-incident faces and edges; outside patch fixed',
        'source_topology_unchanged':True,'source_reference_unchanged':True,'approved_fixed_unchanged':True,'patch_vertices':len(ids),
        'optimizer_success':bool(result.success),'message':result.message,'iterations':int(result.nit),
        'before':before,'after':after,'maximum_correction_mm':float(np.linalg.norm(corrected-candidate,axis=1).max()),
        'capacity_before_mL':volume(d2['reference_vertices']+map_d2(candidate,d2),d2['faces']),
        'capacity_after_mL':volume(d2['reference_vertices']+map_d2(corrected,d2),d2['faces']),
        'minimum_constraint_residual':float(constraints(result.x).min()),'contact_and_tissue_and_continuous_collision_verified':False,
        'used_to_raise_reported_verified_capacity':False,'true_topological_simplification_performed':False})
    protected();print('Tangential patch',len(ids),'success',result.success,'physical quality',after['pass'],flush=True)

if __name__=='__main__':run()
