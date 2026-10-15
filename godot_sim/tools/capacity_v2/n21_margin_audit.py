"""Whole interval conservative float32 area/gradient bounds. Distinct from CCD.
Includes reference cast, displacement cast, parameter rounding, multiplication
and addition; retains the original hard thresholds.
"""
from n21_common import *
from n21_robust_patch import rounding_budget,display_quality

def audit(v,f,d):
    tri=v[f];z=d[f];e1=tri[:,1]-tri[:,0];e2=tri[:,2]-tri[:,0];h1=z[:,1]-z[:,0];h2=z[:,2]-z[:,0]
    c0=np.cross(e1,e2);c1=np.cross(h1,e2)+np.cross(e1,h2);c2=np.cross(h1,h2);den=np.einsum('ij,ij->i',c0,c0)
    q1=np.einsum('ij,ij->i',c0,c1)/den;q2=np.einsum('ij,ij->i',c0,c2)/den
    controls=np.stack([c0,c0+c1/2,c0+c1+c2],1)
    condition=(np.linalg.norm(e1,axis=1)+np.linalg.norm(h1,axis=1))*(np.linalg.norm(e2,axis=1)+np.linalg.norm(h2,axis=1))/np.sqrt(den)
    arithmetic=128*np.finfo(float).eps*np.maximum(1,condition)
    projected_lower=np.minimum.reduce([np.ones(len(f)),1+q1/2,1+q1+q2])-arithmetic
    norm_upper=np.linalg.norm(controls,axis=2).max(1)+arithmetic*np.sqrt(den)
    b=rounding_budget(v,f,d);base=np.sqrt(den)
    lower=(projected_lower*base-b['current_cross_error'])/(base+b['reference_cross_error'])
    upper=(norm_upper+b['current_cross_error'])/(base-b['reference_cross_error'])
    stationary=np.all(d[f]==0,axis=(1,2));lower[stationary]=1;upper[stationary]=1
    _,edges,length=mesh_graph(v,f);eta=b['eta_displacement_mm'];eta_ref=b['eta_reference_mm'];safe_length=length-eta_ref[edges[:,0]]-eta_ref[edges[:,1]]
    gradient=(np.linalg.norm(d[edges[:,0]]-d[edges[:,1]],axis=1)+eta[edges[:,0]]+eta[edges[:,1]])/safe_length
    return {'minimum_area_ratio_lower_bound':float(lower.min()),'maximum_area_ratio_upper_bound':float(upper.max()),'minimum_bound_face':int(lower.argmin()),
        'maximum_edge_gradient_upper_bound':float(gradient.max()),'hard_gate_protected_by_bound':bool(lower.min()>=.8 and upper.max()<=1.35 and gradient.max()<=.2),
        'area_bound_fail_source_faces':np.flatnonzero((lower<.8)|(upper>1.35)).tolist(),
        'whole_interval_not_only_five_samples':True,'includes_u_rounding_and_multiply_add':True,
        'arithmetic_guard':'128*binary64_epsilon times cross-product condition proxy; separate exact rational CCD is not implied',
        'scope':'Conservative IEEE float32 rendering area/gradient error budget; not a formal interval-arithmetic proof of all CPU implementations or finite contacts'},lower,upper,gradient

def run():
    protect();a,d2,tv,tf,resolved,approval=inputs();rows=[]
    for name in ['robust_contract','robust_contract_r2']:
        root=ROOT/name
        for mesh,v,f in [('cavity',a['vertices'],a['faces']),('tissue',tv,tf)]:
            d=np.load(root/f'{mesh}_offset.npy');r,lo,hi,g=audit(v,f,d)
            rows.append({'candidate':name,'mesh':mesh,**r});np.save(root/f'{mesh}_area_ratio_interval_lower.npy',lo)
            np.save(root/f'{mesh}_area_ratio_interval_upper.npy',hi);np.save(root/f'{mesh}_gradient_interval_upper.npy',g)
            print('MARGIN',name,mesh,r['hard_gate_protected_by_bound'],r['minimum_area_ratio_lower_bound'],flush=True)
    write(ROOT/'float32_interval_margin_audit.json',rows);protect()

if __name__=='__main__':run()
