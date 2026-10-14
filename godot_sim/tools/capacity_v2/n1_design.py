"""Emit review-only future parameter schema. No endpoint defaults or geometry solver."""
from n1_analysis import *

def design():
    approval=read_json(ROOT/'D2_approval_2026_10_14_v1.json');stats=read_json(ROOT/'path_statistics.json')
    q=[]
    for p in stats['paths']:
        if p['id'] in ['IN_01','IN_02']:continue
        q.append({'id':'q_'+p['id'],'scope_path_id':p['id'],'type':'TRANSVERSE_LOG_RADIUS_CANDIDATE',
                  'reference_value':0.,'contracted_value':None,'expanded_value':None,'response_weight':None,
                  'limits':'Section metrics set scale only. Ambiguous/shared sections cannot independently determine response.'})
    for n in stats['nodes']:
        q.append({'id':'q_'+n['id'],'type':'SHARED_JUNCTION_BLEND' if n['id'].startswith('J_') else 'TERMINAL_SHAPE_PRESERVING_RESPONSE',
                  'reference_value':0.,'contracted_value':None,'expanded_value':None,'response_weight':None})
    record={'schema':'CAPACITY_V2_N1_TARGET_PREPARATION_V1','status':'DESIGN_ONLY_PENDING_USER_PARAMETER_APPROVAL',
            'D2_approval_sha256':sha(ROOT/'D2_approval_2026_10_14_v1.json'),'domain':approval['domain_id'],
            'V_reference_D2_mL':approval['V_reference_D2_mL'],'V_min_mL':None,'V_max_mL':None,
            'parameter_s':{'Contracted':-1,'Reference':0,'Expanded':1,'is_capacity_fraction':False,'is_time_progress':False,'symmetric_endpoints_assumed':False},
            'endpoint_origin':None,'endpoint_uncertainty':None,'pressure':None,'compliance':None,'real_flow_mL_s':None,
            'regional_parameters':q,'response_model_approved':False,'new_geometry_generated':False,
            'future_volume_constraint':'Integrate unique oriented material-mapped D2 wall and measurement-only closures, V_D2(q)=V_target. Never sum overlapping section integrals.',
            'future_selection_rule':'V_min < V_reference_D2 < V_max; select physiological or explicitly user-approved uncalibrated-demo route; no values supplied in N1.',
            'future_gates':{'unchanged_fixed_vertices':3675,'max_edge_displacement_gradient':.2,'triangle_area_ratio':[.8,1.35],
                            'new_degenerate_or_flipped_faces':0,'new_confirmed_finite_crossings':0,
                            'continuous_intermediate_checks_required':True},
            'required_approvals':['Local/shared region classification and sensitivity','Route A physiology or Route B uncalibrated demo',
                                  'Independent asymmetric endpoint targets and uncertainty','Regional response priors and safety/infeasibility handling','Separate N2 implementation authorization']}
    write_json(ROOT/'capacity_target_template.json',record)
    return record

if __name__=='__main__':design();print('N1 target schema saved; endpoints remain null')
