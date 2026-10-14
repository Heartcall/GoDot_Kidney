"""Summarize actual continuous frame samples; never infer FPS from mesh-only timing."""
from freeze_baseline import *


def stats(values):
    values=np.asarray(values,float)
    return {'mean':float(values.mean()),'median':float(np.median(values)),
            'minimum':float(values.min()),'p95':float(np.percentile(values,95)),'maximum':float(values.max())}


def summarize():
    runs=[]
    for name in ['baseline_forward','baseline_compatibility','optimized_forward','optimized_compatibility','final_forward','final_compatibility']:
        path=OUT/name/'continuous_raw.json'
        if not path.exists():continue
        raw=read_json(path);legs=[]
        for leg in raw['legs']:
            frames=leg['frames'];dt=np.array([x['wall_frame_ms'] for x in frames])
            assert np.all(dt>0) and all(x['sync'] for x in frames)
            assert abs(leg['game_seconds']-6)<1e-9
            phase={k:stats([x['update_phases_ms'][k] for x in frames]) for k in frames[0]['update_phases_ms']}
            long=[{k:x[k] for k in ['frame','wall_since_start_s','u','wall_frame_ms','update_ms','update_phases_ms','state']} for x in frames if x['wall_frame_ms']>50.]
            frame_stats=stats(dt)
            aggregate=len(frames)/leg['wall_seconds']
            legs.append({'phase':leg['phase'],'sample_count':len(frames),'fps_instantaneous':stats(1000/dt),
                'fps_time_weighted':aggregate,'wall_frame_ms':frame_stats,
                'dual_mesh_update_ms':stats([x['update_ms'] for x in frames]),'update_components_ms':phase,
                'six_game_seconds_wall_s':leg['wall_seconds'],'long_frame_threshold_ms':50.,'long_frame_count':len(long),
                'long_frame_locations':long,'stable_30fps_screen':bool(aggregate>=30 and frame_stats['p95']<=1000/30 and not long)})
        runs.append({'name':name,'metadata':{k:v for k,v in raw.items() if k!='legs'},'legs':legs})
    result={'scope':'P2.3 actual continuous playback measurement, not final P2.5 certification',
        'fps_mean_definition':'Arithmetic mean of instantaneous reciprocal wall intervals; time-weighted frames/total wall seconds also provided.',
        'frame_definition':'Successive late-priority _process monotonic timestamps. Includes current CPU update and previous rendering interval, not GPU timestamps or a displayed-present trace.',
        'long_frame_definition':'Measured wall interval >50ms; all samples including first and last retained. Positions are temporal (phase, u), not anatomical hotspots.',
        'runs':runs,'all_final_runs_meet_stable_30fps':all(l['stable_30fps_screen'] for r in runs if r['name'].startswith('final') for l in r['legs']) if any(r['name'].startswith('final') for r in runs) else False,
        'limits':['One fill and one drain per configuration. Not a three-cycle feature, long-duration stability test, GPU profiler, or final P2.5 performance acceptance.']}
    write_json(OUT/'performance_report.json',result)
    for r in runs:
        for l in r['legs']:
            print(r['name'],l['phase'],'FPS mean/median/min',*[round(l['fps_instantaneous'][k],2) for k in ['mean','median','minimum']],
                  'frame p95',round(l['wall_frame_ms']['p95'],3),'update mean',round(l['dual_mesh_update_ms']['mean'],3),
                  'wall_s',round(l['six_game_seconds_wall_s'],3),'readbacks',r['metadata']['readbacks_during_measured_legs'])
    return result


if __name__=='__main__':summarize()
