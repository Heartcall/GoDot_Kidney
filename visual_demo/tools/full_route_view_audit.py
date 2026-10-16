"""Optical-space audit, pose continuity and imported-shape verification."""
from full_route_common import *
from scipy.spatial import cKDTree

def hit_distance(locator,p,d,max_range=60):
    t=vtk.mutable(0.);x=[0.,0.,0.];pcoords=[0.,0.,0.];sub=vtk.mutable(0)
    hit=locator.IntersectWithLine(p,p+max_range*d,1e-8,t,x,pcoords,sub)
    return float(t)*max_range if hit else max_range

def run():
    g=Geometry();route=read(DEMO_PATH);points=np.array(route['points']);fw=np.array(route['forwards']);arc=np.array(route['arc_lengths_mm'])
    locations=np.unique(np.r_[np.arange(0,len(points),10),len(points)-1]).astype(int)
    result={'probe_spacing_approx_mm':1,'states':{},'near_clip_mm':.05,'scope':'camera centre and central optical ray; no physical instrument-radius claim'}
    for s in [-.4,0.,1.]:
        locator=vtk.vtkStaticCellLocator();locator.SetDataSet(g.mesh(s));locator.BuildLocator()
        distance=np.array([hit_distance(locator,points[i],fw[i]) for i in locations])
        result['states'][str(s)]={'min_forward_wall_mm':float(distance.min()),'median_forward_wall_mm':float(np.median(distance)),'end_forward_wall_mm':float(distance[-1]),'min_at_arc_mm':float(arc[locations[distance.argmin()]]),'arc_mm':arc[locations].tolist(),'forward_wall_mm':distance.tolist()}
    rows=np.genfromtxt(ROOT/'preview/frames.csv',delimiter=',',names=True)
    p=np.column_stack([rows[k] for k in ['x','y','z']]);actual_arc=rows['arc_mm'];expected=sample(points,actual_arc)
    delta=np.linalg.norm(p-expected,axis=1)
    q=np.column_stack([rows[k] for k in ['qx','qy','qz','qw']]);q/=np.linalg.norm(q,axis=1)[:,None]
    angle=2*np.rad2deg(np.arccos(np.clip(abs((q[:-1]*q[1:]).sum(axis=1)),0,1)))
    result['runtime']={'samples':len(rows),'time_first':float(rows['time'][0]),'time_last':float(rows['time'][-1]),'start_position':p[0].tolist(),'end_position':p[-1].tolist(),'max_path_sampling_error_mm':float(delta.max()),'arc_first':float(actual_arc[0]),'arc_last':float(actual_arc[-1]),'monotonic_arc':bool((np.diff(actual_arc)>=-1e-5).all()),'max_rotation_deg_per_frame':float(angle.max()),'max_forward_error_deg':float(rows['forward_error_deg'].max()),'first_weights':[float(rows['contracted'][0]),float(rows['expanded'][0])],'peak_weights':[float(rows['contracted'][np.argmax(rows['s'])]),float(rows['expanded'][np.argmax(rows['s'])])],'last_weights':[float(rows['contracted'][-1]),float(rows['expanded'][-1])]}
    result['imported_shape_max_error_mm']={}
    for s in [-.4,0.,1.]:
        baked=np.fromfile(ROOT/f'preview/imported_{s}.bin',dtype='<f4').reshape(-1,3)
        result['imported_shape_max_error_mm'][str(s)]=float(cKDTree(g.vertices(s)).query(baked)[0].max())
    assert delta.max()<.001 and angle.max()<1.4
    assert np.allclose(result['runtime']['first_weights'],[.4,0]) and np.allclose(result['runtime']['peak_weights'],[0,1]) and np.allclose(result['runtime']['last_weights'],[.4,0])
    # Continuous route certification already covers any position/time pairing.
    lower=read(ROOT/'reports/feasibility.json')['continuous_certified_min_clearance_mm']-float(delta.max())
    # FOV 90 vertical, 16:9: farthest near-plane corner from optical centre.
    corner=.05*np.sqrt(1+1+(16/9)**2)
    result['runtime_continuous_clearance_lower_bound_mm']=lower
    result['near_plane_corner_radius_mm']=float(corner)
    result['near_plane_clearance_lower_bound_mm']=float(lower-corner)
    assert lower-corner>1
    result['v4_needed_for_geometric_passage']=False
    write(ROOT/'reports/view_validation.json',result);protect()
    print(json.dumps({k:v for k,v in result.items() if k!='states'},indent=2),flush=True)

if __name__=='__main__':run()
