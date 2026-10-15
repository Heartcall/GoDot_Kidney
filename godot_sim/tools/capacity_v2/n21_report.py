"""Aggregate frozen N2.1-R evidence; never promote research to production."""
from n21_common import *
import csv, platform


def run():
    protected=protect();a,d2,tv,tf,resolved,approval=inputs()
    out=ROOT/'review';out.mkdir(exist_ok=True)
    model=CavityModel(a,resolved,d2,approval)
    np.save(out/'exclusive_source_vertex_group.npy',model.group)
    np.save(out/'source_vertex_local_mode.npy',model.local)
    write(out/'region_support_mapping.json',{'group_names':GROUPS,'local_mode_names':model.names,
        'group_counts':{name:int((model.group==k).sum()) for k,name in enumerate(GROUPS)},
        'initial_response_weights':[0,1,1,1,.22,.18,.10],
        'MainCavity':'Inherited N2.0 audited MAIN support; not all main branches',
        'source_vertex_count':len(a['vertices']),'each_source_vertex_has_exactly_one_group':True,
        'group_array_sha256':sha(out/'exclusive_source_vertex_group.npy'),
        'source_model_sha256':sha(Path(__file__).with_name('n20_model.py'))})
    reproduction=read(ROOT/'reproduction.json');patch=read(ROOT/'robust_contract_r2/repair_report.json')
    cold=read(ROOT/'contact_final/summary.json');warm=read(ROOT/'warm_contact/summary.json')
    r=read(ROOT/'regional_sqp/report.json');failure=read(ROOT/'regional_sqp/nonlinear_failure.json')
    rows=[]
    for name,folder,label in [('robust_contract_r2',ROOT/'robust_contract_r2','Contraction repaired'),
            ('S1_expand',ROOT/'warm_contact/S1_expand','Old +8% warm fixture'),
            ('S2_expand',ROOT/'warm_contact/S2_expand','Old +15% warm fixture')]:
        c=np.load(folder/'cavity_offset.npy');t=np.load(folder/'tissue_offset.npy')
        capacity=volume(d2['reference_vertices']+map_d2(c,d2),d2['faces'])
        cq=quality(a['vertices'],a['faces'],c);tq=quality(tv,tf,t)
        rows.append({'name':name,'label':label,'actual_D2_endpoint_mL':capacity,
            'relative_change_percent':100*(capacity/TARGETS['reference_mL']-1),
            'cavity_maximum_mm':float(np.linalg.norm(c,axis=1).max()),'tissue_maximum_mm':float(np.linalg.norm(t,axis=1).max()),
            'cavity_minimum_area_ratio':cq['continuous_area']['minimum_area_ratio'],
            'tissue_minimum_area_ratio':tq['continuous_area']['minimum_area_ratio'],
            'cavity_maximum_gradient':cq['five_levels'][-1]['maximum_edge_gradient'],
            'tissue_maximum_gradient':tq['five_levels'][-1]['maximum_edge_gradient'],
            'physical_quality_float64_pass':cq['quality_gate_passed'] and tq['quality_gate_passed'],
            'cavity_sha256':sha(folder/'cavity_offset.npy'),'tissue_sha256':sha(folder/'tissue_offset.npy'),
            'continuous_cavity_tissue_transverse_result':'CERTIFIED_NO_NEW_TRANSVERSE_ON_EXACT_ENDPOINT_AFFINE_TRAJECTORY',
            'whole_system_continuous_safety':'NOT_CERTIFIED','formal_N2':False})
    with (out/'candidate_comparison.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    ccd=[read(ROOT/'ccd'/name/'summary.json') for name in ['s1_n20_passed_fresh','s2_warm_fresh','robust_contract_r2_fresh']]
    self_ccd=[read(p) for p in sorted((ROOT/'ccd_self').rglob('summary.json'))]
    blockers=[
        {'id':'FINITE_COLD_MAPPING','status':'FAILED','evidence':'contact_final/summary.json',
         'reason':'Cold +8/+15/+25 candidates retain 76/822/1894 confirmed transverse pairs. Warm fixtures retain N2.0 solutions; not independent new mapping cures.'},
        {'id':'REGIONAL_NONLINEAR_CONTACT','status':'FAILED','evidence':'regional_sqp/nonlinear_failure.json',
         'reason':'LP-initialized total-coefficient proposal has 69 true finite crossings; linearized current features do not constrain all newly encountered contacts.'},
        {'id':'SELF_CCD_SCOPE','status':'UNRESOLVED','evidence':'ccd_self/',
         'reason':'Moving shared-one-vertex pairs and shared-feature coplanar overlap require completion. No complete +15 self-CCD.'},
        {'id':'FLOAT32_CONTACT_TRAJECTORY','status':'UNRESOLVED','evidence':'verification/',
         'reason':'Five float32 relative tests and whole-interval area/gradient budgets do not certify quantized trajectory contacts or all float32 self-intersections.'},
        {'id':'MEASUREMENT_CAP_CCD','status':'UNRESOLVED','evidence':'boundary/',
         'reason':'Fixed and material-moving cap templates valid at samples only; continuous cap-wall/cap-self interval gate not complete.'},
        {'id':'TARGETS_30_PERCENT','status':'NOT_ESTABLISHED','reason':'No safety-qualified path to either specified target. No inference of a global geometric capacity limit.'}]
    summary={'stage':'N2.1-R','date':'2026-10-15','status':'PARTIAL_REMEDIATION_RESEARCH_ONLY_AWAITING_USER_REVIEW',
        'targets':TARGETS,'D2_reference_independent_recomputed_mL':volume(d2['reference_vertices'],d2['faces']),
        'candidate_comparison':rows,'finite_conflict':reproduction['finite_conflict'],
        'cold_regression':cold,'warm_regression':warm,'robust_patch':patch,
        'whole_interval_float32_margin':read(ROOT/'float32_interval_margin_audit.json'),
        'continuous_cavity_tissue':ccd,'persistent_coplanar':read(ROOT/'coplanar/summary.json'),
        'self_CCD_scope':self_ccd,'boundary_sensitivity':read(ROOT/'boundary/summary.json'),
        'regional_failed_endpoint_capacity_mL':failure['endpoint_actual_D2_capacity_mL'],
        'regional_failed_finite_pairs':failure['confirmed_pair_count'],
        'regional_failed_longest_crossing_mm':failure['maximum_finite_intersection_segment_mm'],
        'regional_capacity_attribution':r['capacity_attribution'],'blockers':blockers,
        'full_continuously_verified_safe_capacity':None,'global_safe_capacity_limit':None,
        'target_30_percent_passed':False,'formal_resources_generated':False,
        'python_tests':read(ROOT/'python_tests.json'),'protected_files':protected,'historical_changed_files':[],
        'environment':{'python':sys.version,'platform':platform.platform(),'numpy':np.__version__,
            'scipy':__import__('scipy').__version__,'VTK':__import__('vtk').vtkVersion.GetVTKVersion(),
            'arithmetic_contact':'same 1e-10 mm finite static tolerance; exact rational CCD witnesses use no increased tolerance'},
        'Godot_or_performance_modifications':False,'physiological_parameters_remain_null':True}
    write(ROOT/'summary.json',summary);write(ROOT/'blocking_regions.json',blockers)
    write(ROOT/'n20_research_acceptance_record.json',{'date':'2026-10-15',
        'authority':'Current human instruction accepts N2.0 offline research delivery, not formal +/-30% geometry',
        'historical_N20_report_unchanged':True,'formal_capacity_targets_passed':False})
    # Scientific figures: measured evidence only, all captions identify scope.
    os.environ['MPLCONFIGDIR']=str(ROOT/'.mplconfig')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    ax=axes[0,0]
    for row in rows:
        folder=ROOT/'robust_contract_r2' if row['name']=='robust_contract_r2' else ROOT/'warm_contact'/row['name']
        c=np.load(folder/'cavity_offset.npy');us=np.linspace(0,1,101)
        volumes=[volume(d2['reference_vertices']+u*map_d2(c,d2),d2['faces']) for u in us]
        ax.plot(us,volumes,label=row['label'])
    ax.axhline(TARGETS['contract_mL'],c='gray',ls='--',lw=1,label='Specified -30% target')
    ax.axhline(TARGETS['expand_mL'],c='gray',ls=':',lw=1,label='Specified +30% target')
    ax.set(xlabel='Affine research trajectory parameter',ylabel='D2 oriented volume (mL)',title='Actual D2 integral; full safety NOT certified');ax.legend(fontsize=7)
    ax=axes[0,1];x=np.arange(3);old=[173,753,1838];new=[cold[i]['crossings'] for i in range(3)]
    ax.bar(x-.17,old,.34,label='N1.6 baseline');ax.bar(x+.17,new,.34,label='Finite cold mapping (still failed)')
    ax.set(xticks=x,xticklabels=['+8%','+15%','+25%'],ylabel='Confirmed endpoint transverse pairs',title='Cold regression: no blanket improvement');ax.legend(fontsize=8)
    ax=axes[1,0];values=[reproduction['contract_float32']['minimum_area_ratio'],patch['full_float32_five_levels'][-1]['minimum_area_ratio'],
        next(x['minimum_area_ratio_lower_bound'] for x in summary['whole_interval_float32_margin'] if x['candidate']=='robust_contract_r2' and x['mesh']=='cavity')]
    ax.bar(range(3),[(v-.8)*1e4 for v in values],color=['#d65a4a','#2a9d8f','#457b9d'])
    ax.axhline(0,c='black',lw=1);ax.set(xticks=range(3),xticklabels=['Old f32 endpoint','R2 f32 endpoint','R2 all-u error budget'],ylabel='Margin above 0.8 (x 1e-4)',title='All original area/gradient thresholds retained')
    ax=axes[1,1];ax.axis('off');text='RESEARCH ONLY — NO FORMAL N2\n\n'
    text+='C-T exact endpoint-affine CCD: no new transverse\n+8%, +15% warm fixtures, -7.625% repaired\n\n'
    text+='92 permanent coplanar pairs per trajectory:\n42 original area overlaps + 50 point/edge contacts\n\n'
    text+='Still blocked: full self-CCD, f32 contact path,\ncontinuous measurement caps, new joint mapping.\nNew ~+5% regional proposal: 69 true crossings.'
    ax.text(0,.96,text,va='top',fontsize=10,linespacing=1.5)
    fig.suptitle('N2.1-R remediation evidence — engineering targets, not physiological limits',fontsize=13)
    fig.savefig(out/'remediation_evidence.png',dpi=160);plt.close(fig)
    protect();print('REPORT',len(rows),'candidates; full safe capacity remains null',flush=True)

if __name__=='__main__':run()
