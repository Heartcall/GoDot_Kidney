"""Summarize measured N1.6 prototype evidence, not accepted runtime states."""
from n16_feasibility import *
from n16_closure_and_regions import centerline_clearance
from scipy.spatial import cKDTree
from scipy.sparse.csgraph import connected_components
from collections import Counter

def collect():
    protect();a,d2,tv,tf,resolved,approval=inputs();root=OUT/'prototypes/thin_face_corrected'
    names=[f'{p}_{s}' for p in ['S1','S2','S3'] for s in ['contract','expand']]+['A1_expand_contact_margin']
    records=[];clusters={};pathids=[p['id'] for p in resolved['paths']];baseline=read(OUT/'contact_baseline.json')['results']
    overlap_pairs=lambda r:{(x['cavity_face'],x['tissue_face']) for x in r.get('rows',[]) if x['class']=='COPLANAR_OVERLAP'}
    for name in names:
        directory=root/name;r=read(directory/'preassessment.json');samples=[]
        for u in [.25,.5,.75,1.]:
            s=read(directory/'contacts'/f'u{round(u*100):03}.json');z=s['results']
            samples.append({'u':u,'cavity_self_confirmed':z['cavity_self']['confirmed_transverse_crossings'],
              'D2_self_confirmed':z['D2_self']['confirmed_transverse_crossings'],
              'tissue_self_confirmed':z['tissue_self'].get('confirmed_transverse_crossings'),
              'cavity_tissue_confirmed':z['cavity_tissue']['confirmed_transverse_crossings'],
              'maximum_crossing_segment_mm':z['cavity_tissue']['maximum_confirmed_segment_length_mm'],
              'new_self_coplanar_overlap_pairs':sum(len(overlap_pairs(z[k])-overlap_pairs(baseline[k])) for k in ['cavity_self','tissue_self','D2_self']),
              'new_cross_coplanar_overlap_pairs':len(overlap_pairs(z['cavity_tissue'])-overlap_pairs(baseline['cavity_tissue'])),
              'retained_cross_coplanar_overlap_pairs':len(overlap_pairs(z['cavity_tissue'])&overlap_pairs(baseline['cavity_tissue'])),
              'cross_coplanar_pair_area_sum_mm2':z['cavity_tissue']['coplanar_pair_area_sum_mm2']})
        last=read(directory/'contacts/u100.json')['results']['cavity_tissue'];rows=[x for x in last['rows'] if x['class']=='FINITE_TRANSVERSE_CROSSING']
        if rows:
            centers=np.array([x['center_mm'] for x in rows]);pairs=list(cKDTree(centers).query_pairs(2.))
            if pairs:
                pp=np.array(pairs);g=sparse.coo_matrix((np.ones(2*len(pp)),(np.r_[pp[:,0],pp[:,1]],np.r_[pp[:,1],pp[:,0]])),shape=(len(rows),len(rows)))
            else:g=sparse.coo_matrix((len(rows),len(rows)))
            count,group=connected_components(g,directed=False);groups=[]
            for k in range(count):
                rr=[row for i,row in enumerate(rows) if group[i]==k];xyz=centers[group==k];cf=np.array([x['cavity_face'] for x in rr]);tfids=[x['tissue_face'] for x in rr]
                owners=[pathids[int(np.bincount(a['path_owner'][a['faces'][i]]).argmax())] for i in cf]
                groups.append({'group':k,'pair_count':len(rr),'cavity_face_ids':sorted(set(cf.tolist())),'tissue_face_ids':sorted(set(tfids)),
                  'center_mm':xyz.mean(0).tolist(),'godot_centered_mm':(xyz.mean(0)-np.array([16.,16.,-81.])).tolist(),
                  'bounds_mm':[xyz.min(0).tolist(),xyz.max(0).tolist()],'path_votes':dict(Counter(owners)),
                  'maximum_finite_segment_mm':max(x['finite_segment_length_mm'] for x in rr),'not_penetration_depth':True})
            clusters[name]=groups
        else:clusters[name]=[]
        closure=read(directory/'closure_sensitivity.json');valid=[v['volume_mL'] for s in closure['sampled_levels'] if s['u']==1 for v in s['variants'] if v['geometrically_valid_at_sample']]
        qpassed=r['cavity']['quality_gate_passed'] and r['tissue']['quality_gate_passed']
        crossfree=not any(x['cavity_self_confirmed'] or x['D2_self_confirmed'] or x['cavity_tissue_confirmed'] or (x['tissue_self_confirmed'] or 0) or x['new_self_coplanar_overlap_pairs'] or x['new_cross_coplanar_overlap_pairs'] for x in samples)
        record={'id':name,'actual_material_D2_integral_mL':r['actual_D2_mL'],'relative_capacity_change':r['relative_capacity_change'],
          'cavity_displacement_mm':r['cavity']['endpoint_displacement_mm'],'tissue_displacement_mm':r['tissue']['endpoint_displacement_mm'],
          'cavity_max_gradient':r['cavity']['maximum_edge_gradient'],'tissue_max_gradient':r['tissue']['maximum_edge_gradient'],
          'cavity_continuous_area':r['cavity']['continuous_area'],'tissue_continuous_area':r['tissue']['continuous_area'],
          'quality_pass':qpassed,'sampled_contact_pass':crossfree,'contact_samples':samples,
          'valid_endpoint_closure_volume_range_mL':[min(valid),max(valid)] if valid else None,
          'valid_endpoint_closure_spread_mL':float(np.ptp(valid)) if valid else None,
          'failed_alternative_closures':[{'u':s['u'],'variant':v['variant'],'cap_wall_crossings':v['cap_wall_crossings'],'cap_cap_crossings':v['cap_cap_crossings']} for s in closure['sampled_levels'] for v in s['variants'] if not v['geometrically_valid_at_sample']],
          'fixed_maximum_mm':r['fixed_maximum_mm'],'response_amplitude':r['response_amplitude'],
          'capacity_accounting_residual_mL':r['capacity_contribution']['residual_mL'],
          'status':'SAMPLED_PREASSESSMENT_PASS_NOT_N2_ACCEPTED' if qpassed and crossfree else 'REJECTED_CURRENT_PROTOTYPE',
          'remaining':['Full continuous finite collision detection','Intermediate tissue self-intersection scans','Godot float32/runtime export consistency','Selected endoscope path and envelope clearance','User review and formal N2 solve']}
        records.append(record)
    write(OUT/'crossing_clusters.json',clusters);write(OUT/'comparison.json',{'label':LABEL,'trials':records,'reference_mL':approval['V_reference_D2_mL']})
    write(OUT/'reference_centerline_distance_probes.json',centerline_clearance(a,resolved,np.zeros_like(a['vertices'])))
    low=next(r for r in records if r['id']=='S1_contract');high=next(r for r in records if r['id']=='A1_expand_contact_margin')
    if not (low['quality_pass'] and low['sampled_contact_pass'] and high['quality_pass'] and high['sampled_contact_pass']):raise ValueError('Adjusted range not even sample-feasible; no recommendation written')
    medical=PROJECT/'deformation/capacity_v2_n15_m_v1/real_parameter_status.json'
    config={'schema':'N16_ENGINEERING_ESTIMATE_V1','label':LABEL,'date':'2026-10-15','status':'PENDING_USER_CAPACITY_SELECTION',
      'D2':'C11_R1_IN02_fixed_collar','V_reference_mL':approval['V_reference_D2_mL'],
      'V_min_estimated_mL':low['actual_material_D2_integral_mL'],'V_max_estimated_mL':high['actual_material_D2_integral_mL'],
      'relative_contract':low['relative_capacity_change'],'relative_expand':high['relative_capacity_change'],
      'lower_trial':'S1_contract','upper_trial':'A1_expand_contact_margin',
      'evidence_level':'G2_SAMPLED_NUMERICAL_PREASSESSMENT_WITH_G1_CONTINUOUS_AREA_BOUNDS',
      'clinical_evidence_grade':None,'normal_physiological_limits_claimed':False,'runtime_eligible':False,'N2_authorized':False,
      'rationale':'S2/S1 expansions cross nearby B30 tissue under provisional mapping; contraction kept S1 for margin to area gates; expansion 0.8 times observed clean contact-transition amplitude',
      'display_precision':'Six decimals or fewer in UI; extra digits only reproducibility, not clinical certainty',
      'signed_geometry_parameter':{'Contracted':-1,'Reference':0,'Expanded':1,'not_volume_fraction':True,'reference_not_capacity_midpoint':True},
      'medical_parameter_record':{'path':medical.relative_to(REPO).as_posix(),'sha256':sha(medical),'V_min_mL':None,'V_max_mL':None,'pressure':None,'compliance':None,'real_flow_mL_s':None},
      'limits':low['remaining']+['Mapping-specific numerical example, not proof that S2/S3 are globally impossible','The 20% amplitude margin is an engineering choice, not clinical calibration','Closure variant spread is a limited sensitivity study, not a clinical or universal volume error bound']}
    write(OUT/'engineering_capacity_estimate.json',config)
    os.environ['MPLCONFIGDIR']=str(OUT/'.mplconfig');import matplotlib
    matplotlib.use('Agg');import matplotlib.pyplot as plt
    fig,axs=plt.subplots(1,3,figsize=(14,4.7),layout='constrained');ref=approval['V_reference_D2_mL']
    for i,plan in enumerate(['S1','S2','S3','A1']):
        l=next(r for r in records if r['id']==('S1_contract' if plan=='A1' else plan+'_contract'));h=next(r for r in records if r['id']==('A1_expand_contact_margin' if plan=='A1' else plan+'_expand'))
        color='seagreen' if plan=='A1' else 'firebrick'
        axs[0].plot([l['actual_material_D2_integral_mL'],h['actual_material_D2_integral_mL']],[i,i],'o-',color=color)
        axs[1].bar(i-.17,l['cavity_displacement_mm']['maximum'],.34,color='steelblue');axs[1].bar(i+.17,h['cavity_displacement_mm']['maximum'],.34,color='darkorange')
        axs[2].bar(i,h['contact_samples'][-1]['cavity_tissue_confirmed'],color=color)
    axs[0].axvline(ref,color='black',linestyle='--');axs[0].set(yticks=range(4),yticklabels=['S1','S2','S3','A1 adjusted'],xlabel='D2 integral (mL)',title='Candidate capacities; Reference dashed')
    axs[1].set(xticks=range(4),xticklabels=['S1','S2','S3','A1'],ylabel='Maximum cavity displacement (mm)',title='Fresh fields: contract blue / expand orange')
    axs[2].set(xticks=range(4),xticklabels=['S1','S2','S3','A1'],ylabel='Confirmed transverse triangle pairs',title='Expanded cavity–tissue crossings')
    fig.suptitle('MORPHOLOGY-GUIDED ENGINEERING ESTIMATES — NOT PHYSIOLOGICAL LIMITS',fontsize=12,color='darkred')
    fig.savefig(OUT/'candidate_comparison.png',dpi=160);plt.close(fig)
    protect();print('Recommended pending review',config['V_min_estimated_mL'],config['V_max_estimated_mL'],flush=True)
    return config

if __name__=='__main__':collect()
