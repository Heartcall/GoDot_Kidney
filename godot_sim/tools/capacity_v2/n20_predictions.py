"""Unconstrained initial-basis algebraic projections, NOT feasible capacities."""
from n20_model import *
from n20_solve import capacity_step

def run():
    protected();a,d2,tv,tf,resolved,approval=inputs();m=CavityModel(a,resolved,d2,approval);tm=TissueModel(a,tv,tf,resolved)
    ref=volume(d2['reference_vertices'],d2['faces']);rows=[]
    for side in ['contract','expand']:
        c,p=capacity_step(m,d2,np.zeros_like(m.v),side,np.ones(len(m.names)),.3*ref);t,_=tm.solve(c)
        cq=quality(m.v,m.f,c);tq=quality(tv,tf,t)
        rows.append({'side':side,'prediction':p,'algebraic_integral_mL':volume(d2['reference_vertices']+map_d2(c,d2),d2['faces']),
            'cavity':cq,'tissue':tq,'D2_validity':'NOT_ESTABLISHED','not_a_verified_capacity':True,
            'purpose':'Show why solving the scalar volume equation alone is insufficient. New regional basis only, no old displacement amplification.'})
        print('Unconstrained',side,'cavity gate',cq['quality_gate_passed'],'max mm',cq['endpoint_displacement_mm']['maximum'],flush=True)
    write(OUT/'unconstrained_predictions.json',rows);protected()

if __name__=='__main__':run()
