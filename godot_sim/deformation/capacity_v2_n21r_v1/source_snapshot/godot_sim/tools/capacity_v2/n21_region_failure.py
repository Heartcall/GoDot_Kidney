from n21_common import *
from n16_contacts import classify,self_bbox_pairs
from n16_closure_and_regions import closure_variants
from n20_verify import independent_volume

def run():
    protect();a,d2,tv,tf,resolved,approval=inputs();root=ROOT/'regional_sqp';c=np.load(root/'cavity_proposal.npy');t=np.load(root/'tissue_proposal.npy')
    report=read(root/'contact_report.json.gz');cross=[r for r in report['finite_crossings']['rows'] if r['class']=='FINITE_TRANSVERSE_CROSSING']
    dv=d2['reference_vertices']+map_d2(c,d2);dd=classify(dv,d2['faces'],dv,d2['faces'],self_bbox_pairs(dv,d2['faces']))
    cv=a['vertices']+c;cc=classify(cv,a['faces'],cv,a['faces'],self_bbox_pairs(cv,a['faces']));caps=closure_variants(dv,d2,approval);v=independent_volume(dv,d2['faces'])
    valid=bool(v['numerically_valid'] and not dd['confirmed_transverse_crossings'] and not cc['confirmed_transverse_crossings'] and all(x['geometrically_valid_at_sample'] for x in caps))
    write(root/'nonlinear_failure.json',{'finite_cavity_tissue_crossings':cross,'confirmed_pair_count':len(cross),
        'maximum_finite_intersection_segment_mm':max((r['finite_segment_length_mm'] for r in cross),default=0),
        'source_path_counts':dict(__import__('collections').Counter(resolved['paths'][i]['id'] for r in cross for i in a['path_owner'][a['faces'][r['cavity_face']]])),
        'endpoint_measurement_domain_valid':valid,'endpoint_actual_D2_capacity_mL':v['volume_mL'] if valid else None,
        'endpoint_signed_integral_mL':v['volume_mL'],'cavity_self':cc,'D2_self':dd,'caps':caps,
        'overall_candidate_accepted':False,'global_infeasibility_claimed':False,'partial_linear_contact_constraints_did_not_cover_all_future_finite_contacts':True})
    protect();print('REGIONAL NONLINEAR FAILURE',len(cross),'D2 domain valid',valid,flush=True)

if __name__=='__main__':run()
