"""N2.0 compact evidence, blockers, independent integration and figures."""
from n20_model import *
from n20_verify import independent_volume
import math,platform,shutil

def run():
    protected();a,d2,tv,tf,resolved,approval=inputs();results={};blockers=[]
    for side in ['contract','expand']:
        root=OUT/side;v=read(root/'verification.json');tr=read(root/'trajectory.json');n=len(tr['states'])
        authorized=read(OUT/'authorization_and_targets.json')
        tr.setdefault('original_float64_recomputed_target_mL',tr['target_mL'])
        tr['target_mL']=authorized['expand_target_mL' if side=='expand' else 'contract_target_mL']
        write(root/'trajectory.json',tr)
        c=np.load(root/f'cavity_{n:03}.npy');t=np.load(root/f'tissue_{n:03}.npy')
        repeat=[]
        for u in [0,.25,.5,.75,1.]:repeat.append({'u':u,**independent_volume(d2['reference_vertices']+u*map_d2(c,d2),d2['faces'])})
        write(root/'independent_reintegrals.json',repeat)
        ccd=read(root/'ccd_reference_chord.json.gz')
        stage=read(root/'stage_audit.json') if (root/'stage_audit.json').exists() else None
        levels=v['five_reference_chord_levels'];coplanar=[]
        baseline_pairs={(r['cavity_face'],r['tissue_face']) for r in read(PROJECT/'deformation/capacity_v2_n16_v1/contact_baseline.json')['results']['cavity_tissue']['rows'] if r['class']=='COPLANAR_OVERLAP'}
        for s in levels:
            full=read(OUT/s['full_finite_geometry_evidence']);ct=full['results']['cavity_tissue']
            pairs={(r['cavity_face'],r['tissue_face']) for r in ct['rows'] if r['class']=='COPLANAR_OVERLAP'}
            coplanar.append({'u':s['u'],'pairs':ct['coplanar_overlap_pairs'],'pair_area_sum_mm2':ct['coplanar_pair_area_sum_mm2'],
                'added_pair_ids':sorted(pairs-baseline_pairs),'removed_pair_ids':sorted(baseline_pairs-pairs),
                'pair_area_sum_is_not_unique_contact_area_or_penetration_area':True})
        write(root/'reference_contact_changes.json',coplanar)
        q=lambda x:{'max_mm':v[x]['endpoint_displacement_mm']['maximum'],'mean_mm':v[x]['endpoint_displacement_mm']['mean'],
            'max_gradient':v[x]['maximum_edge_gradient'],'area_min':v[x]['continuous_area']['minimum_area_ratio'],'area_max':v[x]['continuous_area']['maximum_area_ratio']}
        results[side]={'target_mL':tr['target_mL'],'sampled_endpoint_mL':v['endpoint_integral_mL'],
            'relative_change':v['endpoint_integral_mL']/approval['V_reference_D2_mL']-1,'gap_to_target_mL':abs(v['endpoint_integral_mL']-tr['target_mL']),
            'cavity':q('cavity'),'tissue':q('tissue'),'five_level_gate_passed':v['sampled_gate_passed'],
            'all_solver_checkpoint_tissue_transverse_checked':stage is not None,'all_solver_checkpoint_tissue_transverse_passed':stage['all_checkpoint_transverse_passed'] if stage else None,
            'accepted_steps':len(tr['states']),'rejected_attempts':len(tr['rejections']),
            'continuous_contact_event_crossings':len(ccd['confirmed_crossing_intervals']),
            'continuous_unresolved_pairs':len(ccd['unresolved_coplanar_or_conditioned_pairs']),
            'continuous_safety_certified':False,'global_extreme_proved':False,'production_eligible':False,
            'verified_fixed_cavity_vertices':3675,'fixed_maximum_mm':max(s['fixed_maximum_mm'] for s in levels),
            'exact139_relative_maximum_mm':max(s['exact139_relative_maximum_mm'] for s in levels),
            'remote_tissue_maximum_mm':max(s['remote_tissue_maximum_mm'] for s in levels),
            'independent_volume_max_method_spread_mL':max(s['method_spread_mL'] for s in repeat),
            'max_cap_alternative_spread_mL':max(np.ptp([x['volume_mL'] for x in s['closures']]) for s in levels),
            'endoscope_clearance_certified':False}
        for rejected in tr['rejections'][-5:]:
            r=read(OUT/rejected['attempt']/'attempt.json');q_c=r['cavity_quality'];faces=q_c['bad_faces']
            record={'side':side,'attempt':rejected['attempt'],'reason':rejected['reason'],'response_regions':rejected['blocked_regions'],
                'trial_algebraic_integral_mL':rejected['trial_integral_mL'],'cavity_source_faces':faces,
                'face_centers_RAS_mm':a['vertices'][a['faces'][faces]].mean(1).tolist() if faces else []}
            if r.get('contact_trace'):
                qp=r['contact_trace'][-1]['qp'];record['plane_fixed_conflicts']=qp.get('fixed_conflicts',[])
                record['interpretation']='Conservative halfspace/exact-correspondence conflict is NOT automatically a finite physical penetration.'
                for ci,ti,vi,gap in record['plane_fixed_conflicts']:
                    record.setdefault('constraint_locations',[]).append({'cavity_face':ci,'tissue_face':ti,'tissue_vertex':vi,
                        'position_RAS_mm':tv[vi].tolist(),'source_paths':sorted(set(resolved['paths'][i]['id'] for i in a['path_owner'][a['faces'][ci]])),
                        'halfspace_residual_mm':gap})
            blockers.append(record)
    precision=read(OUT/'float32_quality_precheck.json')
    for side in results:
        results[side]['offline_float32_quality_passed']=all(x['all_float32_quality_passed'] for x in precision if x['side']==side)
        results[side]['actual_Godot_runtime_test_performed']=False
    summary={'stage':'N2.0','status':'RESEARCH_COMPLETE_TARGETS_NOT_REACHED_CONTINUOUS_GATE_OPEN','results':results,
        'Reference_mL':approval['V_reference_D2_mL'],'goals_unchanged':True,
        'continuous_fully_certified_nonzero_range':None,'continuous_trivially_unchanged_reference_mL':approval['V_reference_D2_mL'],
        'physiological_endpoints_remain_null':True,'formal_N2_resources_created':False,
        'source_cavity_faces':len(a['faces']),'source_tissue_faces':len(tf),'fixed_cavity_vertices':3675,'exact_shared_vertices':139,
        'tangential_repair_not_in_verified_endpoint':read(OUT/'tangential_repair/experiment.json'),
        'protected_files':protected()}
    write(OUT/'summary.json',summary);write(OUT/'blocking_regions.json',blockers)
    with (OUT/'capacity_region_contributions.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['side','exclusive_response_group','source_vertices','delta_volume_mL','fraction_of_signed_delta','max_displacement_mm'])
        for side in ['contract','expand']:
            state=read(OUT/side/'trajectory.json')['states'][-1]
            for row in state['capacity_attribution']['regions']:writer.writerow([side,row['region'],row['vertices'],row['delta_volume_mL'],row['fraction_of_signed_total'],row['max_displacement_mm']])
    with (OUT/'local_quality_by_region.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['side','diagnostic_region_may_overlap','vertices','max_displacement_mm','median_mm','min_area_ratio','max_area_ratio','max_edge_gradient'])
        for side in ['contract','expand']:
            for name,row in read(OUT/side/'local_regions.json')['cavity_regions'].items():writer.writerow([side,name,row['vertices'],row['maximum_mm'],row['median_mm'],row['minimum_area_ratio'],row['maximum_area_ratio'],row['maximum_edge_gradient']])
    write(OUT/'environment.json',{'python':sys.version,'platform':platform.platform(),'numpy':np.__version__,
        'scipy':__import__('scipy').__version__,'vtk':__import__('vtk').vtkVersion.GetVTKVersion(),
        'threads':'OMP/BLAS/MKL=1','offline_only':True,'P23_runtime_performance_issue_resolved':False})
    # Static scientific plots: actual integrated volumes, never scaled display geometry.
    os.environ['MPLCONFIGDIR']=str(OUT/'.mplconfig')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    for side,color in [('contract','#286ca6'),('expand','#d97412')]:
        tr=read(OUT/side/'trajectory.json');x=np.arange(len(tr['states'])+1);vols=[approval['V_reference_D2_mL']]+[s['capacity_mL'] for s in tr['states']]
        ax[0,0].plot(x,vols,'o-',color=color,label=side);ax[0,0].axhline(tr['target_mL'],color=color,linestyle='--',label=side+' USER TARGET')
        ax[0,1].plot(vols[1:],[s['maximum_cavity_mm'] for s in tr['states']],'o-',color=color,label=side)
        ax[1,0].plot(vols[1:],[s['cavity_quality']['minimum_area_ratio'] for s in tr['states']],'o-',color=color,label=side+' minimum')
        ax[1,0].plot(vols[1:],[s['cavity_quality']['maximum_area_ratio'] for s in tr['states']],':',color=color,label=side+' maximum')
    ax[0,0].set(xlabel='Accepted predictor checkpoint',ylabel='D2 volume (mL)',title='Targets are unchanged; neither is reached')
    ax[0,1].set(xlabel='Actual D2 integral (mL)',ylabel='Maximum cavity displacement (mm)',title='No uniform scale or old-field amplification')
    ax[1,0].axhline(.8,color='red',linestyle='--');ax[1,0].axhline(1.35,color='red',linestyle='--')
    ax[1,0].set(xlabel='Actual D2 integral (mL)',ylabel='Physical triangle area ratio',title='Reference-based quality gate')
    regression=read(OUT/'regression/comparison.json')['fixtures'];xx=np.arange(3)
    ax[1,1].bar(xx-.18,[r['old_confirmed_transverse_pairs'] for r in regression],width=.36,label='N1.6 failed baseline')
    bars=ax[1,1].bar(xx+.18,[r['best_new_confirmed_transverse_pairs'] for r in regression],width=.36,label='New contact QP best endpoint')
    ax[1,1].bar_label(bars,padding=3)
    ax[1,1].set(xticks=xx,xticklabels=['+8% fixture','+15% fixture','+25% fixture'],ylabel='Finite transverse pairs',title='Zero pairs alone does not certify safety')
    for aa in ax.ravel():aa.legend(fontsize=8);aa.grid(alpha=.2)
    fig.suptitle('N2.0 NON-PRODUCTION RESEARCH / not physiological limits');fig.savefig(OUT/'capacity_contact_curves.png',dpi=170);plt.close(fig)
    # Keep readable compact summaries; archive duplicate bulky attempt details.
    for p in OUT.rglob('attempt.json'):
        dest=p.with_suffix('.json.gz')
        dest.write_bytes(gzip.compress(p.read_bytes(),mtime=0))
        if not p.resolve().is_relative_to(OUT.resolve()):raise ValueError('Archive outside N2.0')
        p.unlink()
    protected()

if __name__=='__main__':run()
