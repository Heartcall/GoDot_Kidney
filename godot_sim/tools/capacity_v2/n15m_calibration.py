"""Synthetic-only calibration prototypes. Never imports or edits P1/P2 resources.

All numeric example inputs and fitted outputs are SYNTHETIC_TEST_ONLY.
The project reference is read only by the separate evidence/status builder.
"""
import json, math, os
from pathlib import Path
import numpy as np
from scipy.interpolate import PchipInterpolator
from n15m_sources import OUT, write, read, protect

TAG='SYNTHETIC_TEST_ONLY'

def volume_mL(value,unit):
    x=float(value)
    if not math.isfinite(x) or x<0:raise ValueError('Invalid volume')
    factors={'mL':1.,'mm3':.001,'cm3':1.}
    if unit not in factors:raise ValueError('Explicit supported volume unit required')
    return x*factors[unit]

def pressure_Pa(value,unit):
    x=float(value)
    if not math.isfinite(x):raise ValueError('Invalid pressure')
    # Conventional conversion only; not a clinical pressure recommendation.
    factors={'Pa':1.,'mmHg':133.322387415,'cmH2O':98.0665}
    if unit not in factors:raise ValueError('Explicit supported pressure unit required')
    return x*factors[unit]

def rank_report(matrix):
    a=np.asarray(matrix,dtype=float)
    if a.ndim!=2 or not np.isfinite(a).all():raise ValueError('Finite matrix required')
    sv=np.linalg.svd(a,compute_uv=False);rank=int(np.linalg.matrix_rank(a))
    return {'rank':rank,'parameters':a.shape[1],'nullity':a.shape[1]-rank,
      'singular_values':sv.tolist(),'identifiable':rank==a.shape[1]}

def fit_synthetic_imaging(data):
    if data.get('label')!=TAG:raise ValueError('This prototype accepts explicitly labelled synthetic data only')
    obs=data['observations']
    if not obs:raise ValueError('No observations')
    if any(r.get('state') is None for r in obs):raise ValueError('Unknown operational state')
    if any(r.get('domain_bias_mL') is None for r in obs):raise ValueError('Domain mapping is not identified')
    x=np.array([r['state'] for r in obs],float)
    if not np.isfinite(x).all() or (np.abs(x)>1).any():raise ValueError('States outside declared synthetic support')
    if not all(any(v==s for v in x) for s in [-1.,0.,1.]):raise ValueError('Both endpoint conditions and reference must be observed; no extrapolation')
    bias=np.array([r['domain_bias_mL'] for r in obs],float)
    if not np.isfinite(bias).all():raise ValueError('Finite signed domain corrections required')
    y=np.array([volume_mL(r['observed_volume'],r['unit']) for r in obs])-bias
    if (y<=0).any():raise ValueError('Nonpositive corrected lumen volume')
    sd=np.array([r['independent_sd_mL'] for r in obs],float)
    if not np.isfinite(sd).all() or (sd<=0).any():raise ValueError('Positive measurement uncertainties required')
    a=np.column_stack([np.ones(len(x)),x,x*x]);aw=a/sd[:,None]
    if not rank_report(aw)['identifiable']:raise ValueError('Rank deficient')
    coef=np.linalg.lstsq(aw,y/sd,rcond=None)[0];pred=np.array([[1,-1,1],[1,0,0],[1,1,1]])@coef
    return {'label':TAG,'model':'Quadratic illustrative observation model; not physiological law',
      'coefficients':coef.tolist(),'test_endpoint_values_mL':pred.tolist(),
      'reference_bracketed':bool(pred[0]<pred[1]<pred[2]),'rank':rank_report(aw),
      'residual_mL':(y-a@coef).tolist()}

def integrate_balance(t,q_in,q_out,q_leak,q_urine,q_external_storage,*,V_initial_mL=None,label,flow_unit='mL/s'):
    if label!=TAG:raise ValueError('Synthetic-only prototype')
    if flow_unit!='mL/s':raise ValueError('No silent mL/min versus mL/s conversion')
    t=np.asarray(t,float)
    if t.ndim!=1 or len(t)<2 or not np.isfinite(t).all() or (np.diff(t)<=0).any():raise ValueError('Strictly increasing finite seconds required')
    arrays=[]
    for v in [q_in,q_out,q_leak,q_urine,q_external_storage]:
        if v is None:return {'label':TAG,'identified':False,'reason':'Unmeasured flow component cannot be assumed zero','delta_volume_mL':None,'absolute_volume_mL':None}
        v=np.asarray(v,float)
        if v.shape!=t.shape or not np.isfinite(v).all():raise ValueError('Finite aligned flow arrays required')
        arrays.append(v)
    for v in arrays[:4]:
        if (v<0).any():raise ValueError('Direction is encoded by channel, not negative inflow/outflow rates')
    qi,qo,ql,qu,qs=arrays;net=qi+qu-qo-ql-qs
    delta=np.r_[0.,np.cumsum(.5*(net[1:]+net[:-1])*np.diff(t))]
    absolute=None if V_initial_mL is None else (volume_mL(V_initial_mL,'mL')+delta).tolist()
    if absolute is not None and min(absolute)<0:raise ValueError('Negative fluid volume')
    return {'label':TAG,'identified':V_initial_mL is not None,'delta_volume_mL':delta.tolist(),
      'absolute_volume_mL':absolute,'reason':'Absolute initial fluid volume missing' if V_initial_mL is None else None}

def fluid_to_lumen(fluid,device,gas,stone,label):
    if label!=TAG:raise ValueError('Synthetic only')
    if any(v is None for v in [fluid,device,gas,stone]):return None
    return sum(volume_mL(v,'mL') for v in [fluid,device,gas,stone])

def pressure_branch(pressure,volume,query,*,label,branch):
    if label!=TAG:raise ValueError('Synthetic only')
    if branch not in ['LOADING','UNLOADING']:raise ValueError('Separate history branches required')
    p=np.asarray(pressure,float);v=np.asarray(volume,float);q=np.asarray(query,float)
    if p.ndim!=1 or p.shape!=v.shape or len(p)<3 or not all(np.isfinite(a).all() for a in [p,v,q]):raise ValueError('Finite branch data required')
    order=np.argsort(p);p=p[order];v=v[order]
    if (np.diff(p)<=0).any() or (np.diff(v)<0).any():raise ValueError('Repeated pressures/history or monotonicity conflict requires analysis, not silent pooling')
    if (q<p[0]).any() or (q>p[-1]).any():raise ValueError('Unsupported extrapolation')
    return PchipInterpolator(p,v,extrapolate=False)(q)

def approval_gate(candidate):
    """Advisory gate only. Returns reasons; cannot authorize or save clinical endpoints."""
    reasons=[]
    if candidate.get('label')==TAG:reasons.append('Synthetic evidence forbidden for real endpoint approval')
    for key in ['domain_mapping_verified','operational_conditions_approved','endpoint_coverage_verified',
      'uncertainty_reviewed','source_provenance_verified','legal_data_access_verified','medical_review_signed','user_review_signed']:
        if candidate.get(key) is not True:reasons.append('Missing '+key)
    if candidate.get('evidence_grade') not in ['E1','E2']:reasons.append('Endpoint applicability not established')
    if candidate.get('evidence_grade')=='E2' and candidate.get('conditional_gaps_resolved') is not True:reasons.append('E2 conditions unresolved')
    if candidate.get('inferential_target') not in ['INDIVIDUAL_OPERATIONAL_ENDPOINTS','APPROVED_POPULATION_PREDICTION']:
        reasons.append('Population static quantiles cannot become individual dynamic endpoints')
    values=[candidate.get(k) for k in ['V_min_mL','V_reference_D2_mL','V_max_mL']]
    valid=all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) and x>0 for x in values)
    if not valid:reasons.append('Positive finite capacity estimates missing')
    elif not values[0]<values[1]<values[2]:reasons.append('Reference not strictly bracketed: revisit endpoint/state definition, do not force fit')
    if candidate.get('interval_type') not in ['CONFIDENCE','PREDICTION','POSTERIOR','FEASIBILITY']:reasons.append('Uncertainty interpretation missing')
    if not candidate.get('source_hashes') or not candidate.get('model_version'):reasons.append('Versioned source/model identifiers missing')
    return {'eligible_for_human_review':not reasons,'approved':False,'reasons':reasons,
      'note':'Human medical/user approval and subsequent N2 authorization are external; no endpoint config writer exists.'}

def write_synthetic_result(path,result):
    path=Path(path).resolve();root=(OUT/'synthetic').resolve()
    if root not in path.parents or result.get('label')!=TAG:raise ValueError('Synthetic output sink restriction')
    write(path,result)

def run():
    protect();root=OUT/'synthetic';root.mkdir(exist_ok=True)
    # Deliberately unrelated to this kidney. Exactly one method fixture, not endpoint scanning.
    data={'label':TAG,'not_patient_data':True,'seed':1515,'observations':[]}
    for x in [-1.,-.5,0.,.5,1.]:
        for offset in [-.3,0.,.3]:
            data['observations'].append({'state':x,'observed_volume':100+12*x+3*x*x+2+offset,
              'unit':'mL','domain_bias_mL':2.,'independent_sd_mL':.3})
    fit=fit_synthetic_imaging(data)
    rng=np.random.default_rng(1515);draws=10000
    # Common mapping bias does not average away; shared bias cancels in paired differences only if state invariant.
    mapping=rng.normal(0,2,(draws,1));noise=rng.normal(0,.3,(draws,3))
    endpoint_draws=np.array(fit['test_endpoint_values_mL'])[None,:]+mapping+noise
    delta_draws=endpoint_draws[:,2]-endpoint_draws[:,0]
    t=np.array([0.,.3,1.,2.5,4.]);q=lambda x:np.full(t.shape,x)
    balance=integrate_balance(t,q(3),q(2),q(.2),q(.1),q(.1),V_initial_mL=100,label=TAG)
    rank_cases={'single_known_reference_quadratic':rank_report([[1,0,0]]),
      'two_known_states_quadratic':rank_report([[1,-1,1],[1,1,1]]),
      'three_known_states_quadratic':rank_report([[1,-1,1],[1,0,0],[1,1,1]]),
      'unknown_shared_domain_bias':rank_report([[1,-1,1,1],[1,0,0,1],[1,1,1,1]]),
      'unknown_initial_volume_and_offset':rank_report([[1,1],[1,1],[1,1]])}
    p=np.array([0.,1.,2.,3.,4.]);load=100+2*np.log1p(p);unload=100+2*np.log1p(p)+.6*np.sin(np.pi*p/4)
    report={'label':TAG,'not_patient_data':True,'fixture_count':1,'seed':1515,'imaging_fit':fit,
      'rank_cases':rank_cases,'uncertainty':{'method':'Synthetic shared mapping bias + independent error Monte Carlo',
        'draws':draws,'test_absolute_intervals_95_mL':np.quantile(endpoint_draws,[.025,.975],axis=0).tolist(),
        'test_paired_change_interval_95_mL':np.quantile(delta_draws,[.025,.975]).tolist(),
        'absolute_sd_mL':np.std(endpoint_draws,axis=0).tolist(),'paired_change_sd_mL':float(np.std(delta_draws)),
        'not_a_patient_interval':True},'mass_balance':balance,
      'missing_initial_volume':integrate_balance(t,q(3),q(2),q(.2),q(.1),q(.1),label=TAG),
      'missing_leak':integrate_balance(t,q(3),q(2),None,q(.1),q(.1),label=TAG),
      'pressure_history':{'pressure_arbitrary_test_units':p.tolist(),'loading_volume_mL':load.tolist(),'unloading_volume_mL':unload.tolist(),
        'extrapolation_allowed':False,'not_physiological_coefficients':True},
      'current_real_patient_estimates':{'V_min_mL':None,'V_max_mL':None,'patient_interval':None}}
    write_synthetic_result(root/'fixture.json',data);write_synthetic_result(root/'result.json',report)
    os.environ['MPLCONFIGDIR']=str(OUT/'.mplconfig')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axs=plt.subplots(1,3,figsize=(14,4.8),layout='constrained')
    x=np.array([-1,0,1]);y=np.array(fit['test_endpoint_values_mL'])
    axs[0].errorbar(x,y,yerr=1.96*np.std(endpoint_draws,axis=0),fmt='o',capsize=5,label='Shared mapping + noise')
    axs[0].set(xlabel='Known synthetic operational state',ylabel='Test volume (mL)',title='Absolute uncertainty remains');axs[0].legend(fontsize=8)
    axs[1].bar(['1 state','2 states','3 states','+ unknown\ndomain bias'],[1,2,3,3]);axs[1].plot([0,1,2,3],[3,3,3,4],'r_',markersize=30,label='Unknown parameter count')
    axs[1].set(ylabel='Rank / parameter count',title='Identifiability depends on observations',ylim=(0,5));axs[1].legend(fontsize=8)
    grid=np.linspace(0,4,100)
    axs[2].plot(grid,pressure_branch(p,load,grid,label=TAG,branch='LOADING'),label='Loading')
    axs[2].plot(grid,pressure_branch(p,unload,grid,label=TAG,branch='UNLOADING'),label='Unloading')
    axs[2].set(xlabel='Arbitrary test pressure units',ylabel='Test fluid volume (mL)',title='Do not pool loading and unloading');axs[2].legend(fontsize=8)
    fig.suptitle('SYNTHETIC_TEST_ONLY — NOT THIS KIDNEY — NO CLINICAL ENDPOINTS',color='darkred',fontsize=14)
    fig.savefig(root/'method_validation.png',dpi=160);plt.close(fig)
    print('Synthetic method checks written; real endpoints remain null');protect()

if __name__=='__main__':run()
