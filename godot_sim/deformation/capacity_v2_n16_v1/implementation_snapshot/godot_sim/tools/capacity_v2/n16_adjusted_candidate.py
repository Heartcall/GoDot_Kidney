"""One contact-derived conservative expansion alternative; no field retuning."""
from n16_feasibility import *
from n16_contacts import classify
from audit_tissue_cavity import contact_pairs

def build():
    protect();a,d2,tv,tf,resolved,approval=inputs();unit=OUT/'attempts/thin_face_corrected'
    c=np.load(unit/'research_expand_cavity_unit_response.npy');t=np.load(unit/'research_expand_tissue_unit_response.npy')
    low=read(OUT/'prototypes/thin_face_corrected/S1_expand/preassessment.json')['response_amplitude']*.25
    high=read(OUT/'prototypes/thin_face_corrected/S2_expand/preassessment.json')['response_amplitude']*.25
    observations=[]
    def observe(q):
        r=classify(a['vertices']+q*c,a['faces'],tv+q*t,tf,contact_pairs(a['vertices']+q*c,a['faces'],tv+q*t,tf))
        row={'amplitude':q,'actual_D2_volume_mL':volume(d2['reference_vertices']+q*map_d2(c,d2),d2['faces']),
          'confirmed_transverse_crossings':r['confirmed_transverse_crossings'],'crossing_rows':[x for x in r['rows'] if x['class']=='FINITE_TRANSVERSE_CROSSING']}
        observations.append(row);print('Contact bracket',q,row['actual_D2_volume_mL'],row['confirmed_transverse_crossings'],flush=True)
        return r['confirmed_transverse_crossings']
    if observe(low)!=0 or observe(high)==0:raise ValueError('Expected observed clean/failing bracket not reproduced')
    for _ in range(6):
        mid=(low+high)/2
        if observe(mid):high=mid
        else:low=mid
    # Engineering margin only. No claim of clinically safe pressure or full CCD.
    q=.8*low;cv=q*c;tt=q*t;directory=OUT/'prototypes/thin_face_corrected/A1_expand_contact_margin';directory.mkdir(parents=True,exist_ok=True)
    np.save(directory/'research_cavity_offset.npy',cv);np.save(directory/'research_tissue_offset.npy',tt)
    labels=np.load(OUT/'response_region_ids.npy');names=read(OUT/'response_design.json')['region_names']
    actual=volume(d2['reference_vertices']+map_d2(cv,d2),d2['faces'])
    report={'id':'A1_expand_contact_margin','label':LABEL,'status':'ADJUSTED_NON_PRODUCTION_PREASSESSMENT',
      'plan':'A1','direction':'expand','actual_D2_mL':actual,'target_mL':actual,'relative_capacity_change':actual/approval['V_reference_D2_mL']-1,
      'response_amplitude':q,'cavity':quality(a['vertices'],a['faces'],cv),'tissue':quality(tv,tf,tt),
      'D2_measurement_mesh':quality(d2['reference_vertices'],d2['faces'],map_d2(cv,d2)),
      'fixed_maximum_mm':float(np.linalg.norm(cv[a['port_fixed_masks'].any(0)],axis=1).max()),
      'capacity_contribution':region_contributions(a,d2,cv,labels,names),
      'contact_bracket':{'observations':observations,'last_observed_clean_amplitude':low,'last_observed_failing_amplitude':high,
        'margin_factor':.8,'reason':'Keep 20% amplitude margin below this experimentally bracketed onset for the fixed provisional mapping',
        'not_a_global_first_collision_proof':True,'not_a_clinical_margin':True,'field_geometry_parameters_changed_during_search':False},
      'still_requires_N2_N3_and_user_approval':True}
    write(directory/'preassessment.json',report);write(OUT/'contact_transition_bracket.json',report['contact_bracket']);protect()

if __name__=='__main__':build()
