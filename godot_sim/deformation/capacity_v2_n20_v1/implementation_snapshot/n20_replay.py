"""Replay recorded accepted regional predictors and binding contact solves.
This is NOT a second complete adaptive search. Resume schedules can change
conservative inactive halfspaces; the exact recorded schedule is explicit.
"""
from n20_model import *
from n20_solve import capacity_step

def run():
    protected();a,d2,tv,tf,resolved,approval=inputs();m=CavityModel(a,resolved,d2,approval);tm=TissueModel(a,tv,tf,resolved);records=[]
    for side in ['contract','expand']:
        root=OUT/side;tr=read(root/'trajectory.json');rows=[]
        for state in tr['states']:
            index=state['index'];step=OUT/state['attempt'];r=read(step/'attempt.json')
            iteration,retry=[int(x) for x in step.name.split('_')[1:]];mob=np.ones(len(m.names))
            for rejection in tr['rejections']:
                if (rejection['iteration'],rejection['retry'])<(iteration,retry):
                    for name in rejection['blocked_regions']:mob[m.names.index(name)]*=.25
            start=np.load(root/f'cavity_{index-1:03}.npy');expected=np.load(root/f'cavity_{index:03}.npy')
            desired=abs(r['prediction']['target_step_mL']-r['from_capacity_mL'])
            actual,_=capacity_step(m,d2,start,side,mob,desired)
            pairs=set()
            for trace in r['contact_trace']:pairs.update((x[0],x[1]) for x in trace['qp'].get('active_sources',[]))
            tissue,qp=tm.solve(expected,pairs);target_t=np.load(root/f'tissue_{index:03}.npy')
            err_c=float(abs(actual-expected).max());err_t=float(abs(tissue-target_t).max())
            rows.append({'index':index,'cavity_maximum_abs_replay_error_mm':err_c,'tissue_maximum_abs_replay_error_mm':err_t,'qp_converged':qp['qp_converged']})
        records.append({'side':side,'states':rows,'all_replayed_within_1e_10_mm':all(x['cavity_maximum_abs_replay_error_mm']<1e-10 and x['tissue_maximum_abs_replay_error_mm']<1e-10 for x in rows)})
    write(OUT/'trajectory_replay.json',{'records':records,'complete_adaptive_search_repeated':False,
        'replay_uses_recorded_mobility_and_binding_constraint_schedule':True,
        'original_run_restart_schedule':{'expand':'4 accepted checkpoints, then --resume','contract':'3 accepted checkpoints, then --resume'},
        'limits':'Resume restores binding source pairs rather than every previous conservative plane; uninterrupted and resumed search may follow different local paths. Formal solver needs frozen persistence semantics.'})
    protected();print('Recorded sequence replay',[(r['side'],r['all_replayed_within_1e_10_mm']) for r in records],flush=True)

if __name__=='__main__':run()
