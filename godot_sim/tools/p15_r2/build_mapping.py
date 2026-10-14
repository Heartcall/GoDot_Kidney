"""One deterministic local solve: tiered constraints and short-edge metric protection."""
import argparse
from scipy import sparse
from scipy.sparse.csgraph import dijkstra
from scipy.sparse.linalg import spsolve
from common import *
from build_cavity_morph_states import minimum_oriented_area_ratio

PARAMETERS={'patch_radius_mm':6.,'feather_start_mm':3.,'metric_regularizer_mm2':.05,
 'engineering_gradient_limit':.2,'area_ratio_limits':[.8,1.35],
 'data_weights':{'C':1.,'D':.25,'unconfirmed_C':.1}}


def build():
    if not (OUT/'source_diagnosis.json').exists(): raise ValueError('Run diagnosis before the solve')
    d=read_inputs();tv,tf,old=d['tv'],d['tf'],d['old']
    graph,edges,length=mesh_graph(tv,tf);seeds=np.array(sorted(set(sum(FOCUS.values(),[]))))
    geo=dijkstra(graph,indices=seeds,min_only=True,limit=PARAMETERS['patch_radius_mm'])
    feather=1-smoothstep((geo-PARAMETERS['feather_start_mm'])/(PARAMETERS['patch_radius_mm']-PARAMETERS['feather_start_mm']))
    patch=geo<PARAMETERS['patch_radius_mm'];hard=d['exact']|d['contact']|d['remote']
    free=patch&~hard;free_ids=np.flatnonzero(free);lut=np.full(len(tv),-1,int);lut[free_ids]=np.arange(len(free_ids))
    selected=free[edges].any(axis=1);ed=edges[selected];le=length[selected]
    row=np.repeat(np.arange(len(ed)),2);col=lut[ed].ravel();values=np.tile([1.,-1.],len(ed))/np.repeat(le,2);keep=col>=0
    A=sparse.coo_matrix((values[keep],(row[keep],col[keep])),shape=(len(ed),len(free_ids))).tocsr()
    constant=np.zeros((len(ed),3))
    for side,sign in [(0,1),(1,-1)]:
        mask=~free[ed[:,side]];constant[mask]+=sign*old[ed[mask,side]]/le[mask,None]
    weights=np.where(d['classes'][free_ids]=='D',.25,1.)
    uncertain=np.isin(free_ids,[61933,61934,30663]);weights[uncertain]=.1
    weights/=np.maximum(feather[free_ids]**2,1e-8)
    # Only local edges receive the new metric term. The fixed exterior preserves R1 exactly.
    ew=PARAMETERS['metric_regularizer_mm2']*np.maximum(feather[ed].mean(axis=1),1e-8)
    Q=sparse.diags(weights)+A.T@sparse.diags(ew)@A
    rhs=weights[:,None]*old[free_ids]-A.T@(ew[:,None]*constant)
    x=spsolve(Q.tocsc(),rhs)
    field=old.copy();field[free_ids]=x
    delta=np.linalg.norm(field-old,axis=1);magnitude=np.linalg.norm(field,axis=1)
    c0,a0,_=triangle_data(tv,tf);cross,area,_=triangle_data(tv+field,tf)
    gradient=np.linalg.norm(field[edges[:,0]]-field[edges[:,1]],axis=1)/length
    ratio=area/a0;cos=np.einsum('ij,ij->i',c0,cross)/(4*a0*area)
    report={'status':'RESEARCH_TRIAL_PENDING_FULL_FIVE_LEVEL_REVIEW','parameters':PARAMETERS,'solver':'Local screened inverse-edge-length-squared metric quadratic; nonzero A/B/exterior constraints eliminated exactly. Global engineering limits are rejection gates, not relaxed optimization penalties.',
       'free_vertices':len(free_ids),'patch_vertices':int(patch.sum()),'changed_vertices_above_1e_minus12':int((delta>1e-12).sum()),'maximum_change_from_R1_mm':float(delta.max()),
       'all_outside_patch_exactly_R1':bool(np.array_equal(field[~patch],old[~patch])),
       'A_exact_coincident_count':int(d['exact'].sum()),'B_contact_count':int((d['contact']&~d['exact']).sum()),
       'A_B_values_exactly_preserved':bool(np.array_equal(field[hard],old[hard])),'remote_E_exact_zero':bool(np.all(field[d['remote']]==0)),
       'maximum_displacement_mm':float(magnitude.max()),'mean_displacement_mm':float(magnitude.mean()),'moving_vertices_above_1e_minus12':int((magnitude>1e-12).sum()),
       'maximum_edge_gradient':float(gradient.max()),'area_ratio_range':[float(ratio.min()),float(ratio.max())],
       'maximum_normal_rotation_deg':float(np.degrees(np.arccos(np.clip(cos,-1,1))).max()),
       'continuous_oriented_area_ratio_minimum':minimum_oriented_area_ratio(tv,tf,field),
       'normal_uncertain_vertices_still_unconfirmed':[61933,61934,30663],
       'sources':{'R1_field':source_record(R1/'UNACCEPTED_contact_tissue_displacement.npy'),'diagnosis':source_record(OUT/'source_diagnosis.json'),'approved_cavity_driver':source_record(PROJECT/'deformation/full_cavity/field/displacement.npy')}}
    arrays={'research_tissue_displacement':field,'repair_patch_mask':patch,'repair_free_mask':free,'repair_feather':feather,'constraint_classes':d['classes'],
      'reference_vertices':tv,'faces':tf,'reference_normals':vertex_normals(tv,tf),'displacement_gradient_per_vertex':np.zeros(len(tv)),'area_ratio_per_face':ratio}
    np.maximum.at(arrays['displacement_gradient_per_vertex'],edges[:,0],gradient);np.maximum.at(arrays['displacement_gradient_per_vertex'],edges[:,1],gradient)
    for name,array in arrays.items(): np.save(OUT/(name+'.npy'),array)
    report['output_sha256']={name+'.npy':source_record(OUT/(name+'.npy'))['sha256'] for name in arrays}
    (OUT/'build_report.json').write_bytes(json_bytes(report));print({k:val for k,val in report.items() if k not in ['sources','output_sha256']},flush=True)
    # Stop after this one configuration. Quality failure remains research-only.
    return report

if __name__=='__main__': build()
