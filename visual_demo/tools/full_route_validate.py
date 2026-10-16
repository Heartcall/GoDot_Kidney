"""Certify the full polyline against every s in [-0.4,1], independent of playback phase."""
from full_route_common import *
from scipy.ndimage import gaussian_filter1d

def certify():
    protect();g=Geometry();candidate=np.load(ROOT/'data/candidate_route.npz');p=candidate['points'];source_offsets=candidate['original_offsets'];arc=lengths(p)
    states=np.round(np.arange(-.4,1.00001,.025),8)
    d=np.array([g.clearance(p,s) for s in states])
    outside=[]
    for i,s in enumerate(states):
        mask=~g.enclosed(p,s)
        if mask.any():outside.append({'s':float(s),'point_indices':np.flatnonzero(mask).tolist()})
    # Each cell represents one path segment x one linear Shape Key interval.
    # Hausdorff wall movement <= max vertex displacement * state delta.
    # Distance is 1-Lipschitz in camera position. Every point in the cell is
    # within half a path segment and half a state interval of a sampled corner.
    spatial=np.diff(arc)/2
    motion=np.where(states[:-1]<0,g.max_motion['contracted'],g.max_motion['expanded'])*np.diff(states)/2
    lower=np.minimum.reduce([d[:-1,:-1],d[1:,:-1],d[:-1,1:],d[1:,1:]])-spatial[None,:]-motion[:,None]
    index=np.unravel_index(np.argmin(lower),lower.shape)
    assert not outside and lower.min()>1.0,'Do not approve or drive an uncertified path'
    # Forward directions derive from the new route, never from stale source tangents.
    # A symmetric arc-length window anticipates corners without an abrupt look-at jump.
    forward=normalized(sample(p,np.minimum(arc+1.8,arc[-1]))-sample(p,np.maximum(arc-.9,0)))
    forward=normalized(gaussian_filter1d(forward,5,axis=0,mode='nearest'))
    angular=np.arccos(np.clip(np.sum(forward[1:]*forward[:-1],axis=1),-1,1))
    curvature=np.r_[angular[0]/np.diff(arc)[0],angular/np.diff(arc)]
    curvature=gaussian_filter1d(curvature,6)
    speed=np.minimum(2.3, np.deg2rad(11)/np.maximum(curvature,1e-6))
    junctions=np.interp(read(SOURCE)['junctions'],source_offsets,arc)
    # Smooth speed reduction around each preserved junction; positive everywhere.
    for j in junctions:speed=np.minimum(speed,2.3-1.15*np.exp(-.5*((arc-j)/3.0)**2))
    speed=gaussian_filter1d(np.clip(speed,.5,2.3),5)
    time=np.r_[0,np.cumsum(np.diff(arc)/((speed[1:]+speed[:-1])/2))]
    # Choose an even number of 30 fps intervals, preserving the exact peak frame.
    duration=float(np.ceil(time[-1]*30/2)*2/30);time*=duration/time[-1]
    speed=np.r_[speed[0],np.diff(arc)/np.diff(time)]
    original=np.array(read(SOURCE)['points']);deviation=np.linalg.norm(p-sample(original,source_offsets),axis=1)
    report={'status':'FEASIBLE_WITH_DEMO_PATH_ONLY_NO_V4_REQUIRED','state_range':[-.4,1.],'state_samples':states.tolist(),'path_nodes':len(p),'original_length_mm':float(lengths(original)[-1]),'optimized_length_mm':float(arc[-1]),'sampled_min_clearance_mm':float(d.min()),'continuous_certified_min_clearance_mm':float(lower.min()),'proof':'For each path/state cell: minimum corner distance minus half segment length minus max vertex displacement times half state interval. Positive lower bound plus inside samples excludes wall crossings between samples. Triangle positions interpolate linearly within each half of the state range.','max_segment_mm':float(np.diff(arc).max()),'max_state_step':.025,'wall_motion_bound_per_state':g.max_motion,'bottleneck_original_offsets_mm':[float(source_offsets[index[1]]),float(source_offsets[index[1]+1])],'bottleneck_states':[float(states[index[0]]),float(states[index[0]+1])],'outside_samples':outside,'start_shift_mm':float(np.linalg.norm(p[0]-original[0])),'end_shift_mm':float(np.linalg.norm(p[-1]-original[-1])),'max_route_deviation_mm':float(deviation.max()),'source_junctions_mm':read(SOURCE)['junctions'],'optimized_junctions_mm':junctions.tolist(),'original_progress_monotonic':bool((np.diff(source_offsets)>0).all()),'duration_seconds':duration,'speed_range_mm_s':[float(speed.min()),float(speed.max())],'state_minima':{str(s):float(d[i].min()) for i,s in enumerate(states)}}
    route={'schema':'V_DEMO_FULL_ROUTE_C04_PREVIEW_1','purpose':'Demonstration-only candidate; user approval required before final MP4','units':'RAS_mm','source_path':str(SOURCE.relative_to(PROJECT)).replace('\\','/'),'source_path_sha256':sha(SOURCE),'source_blend_sha256':sha(BLEND),'state_range':[-.4,1.],'points':p.tolist(),'forwards':forward.tolist(),'junctions':junctions.tolist(),'speeds':(speed/2.3).tolist(),'speed_mm_s':speed.tolist(),'arc_lengths_mm':arc.tolist(),'times_seconds':time.tolist(),'duration_seconds':duration,'original_arc_offsets_mm':source_offsets.tolist(),'clearance_certified_mm':lower.min(axis=0).tolist(),'original_junctions_mm':read(SOURCE)['junctions'],'endpoint_shift_mm':report['end_shift_mm']}
    write(DEMO_PATH,route);write(ROOT/'reports/feasibility.json',report)
    np.savez(ROOT/'data/validation_grid.npz',states=states,clearance=d,continuous_lower_bound=lower,original_offsets=source_offsets,arc=arc,points=p)
    print(json.dumps({k:v for k,v in report.items() if k not in ['state_samples','state_minima','proof']},indent=2),flush=True)
    protect()

if __name__=='__main__':certify()
