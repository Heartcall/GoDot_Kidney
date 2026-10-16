"""Ordered corridor search, then smooth and certify against the full morph interval."""
from full_route_common import *
from scipy.spatial.distance import cdist
from scipy.interpolate import CubicSpline
from scipy.ndimage import gaussian_filter1d

def frames_at(points,offsets):
    total=lengths(points)[-1];centers=sample(points,offsets)
    tangents=normalized(sample(points,np.minimum(offsets+.5,total))-sample(points,np.maximum(offsets-.5,0)))
    axes=[];last=np.cross(tangents[0],[1.,0,0]);last/=np.linalg.norm(last)
    for t in tangents:
        last=last-t*np.dot(last,t);last/=np.linalg.norm(last);axes.append(last.copy())
    a=np.array(axes);return centers,tangents,a,np.cross(tangents,a)

def search():
    protect(True);g=Geometry();source=read(SOURCE);original=np.array(source['points']);total=lengths(original)[-1]
    offsets=np.unique(np.r_[np.linspace(0,total,int(np.ceil(total/.75))+1),source['junctions']])
    centers,tangents,a,b=frames_at(original,offsets)
    grid=np.arange(-3.5,3.5001,.5);xy=np.array(np.meshgrid(grid,grid)).reshape(2,-1).T
    points=centers[:,None,:]+xy[None,:,0,None]*a[:,None,:]+xy[None,:,1,None]*b[:,None,:]
    all_clear=[]
    for s in [-.4,0.,1.]:
        d=g.clearance(points.reshape(-1,3),s).reshape(points.shape[:2]);all_clear.append(d)
        print('Corridor state',s,'done',flush=True)
    clearance=np.min(all_clear,axis=0)
    np.savez(ROOT/'data/corridor_grid.npz',offsets=offsets,centers=centers,tangents=tangents,a=a,b=b,xy=xy,points=points,clearance=clearance)
    print('Bottleneck maximum sampled clearance:',[(round(float(offsets[i]),2),round(float(clearance[i].max()),3)) for i in range(len(offsets)) if clearance[i].max()<1.2],flush=True)
    # All original longitudinal stations are retained, including both branch gates.
    # Exclude crossings into remote lobes by a 3.5 mm transverse corridor and local edges.
    node_cost=12*np.maximum(1.6-clearance,0)**2+.055*(xy**2).sum(axis=1)[None,:]
    node_cost[clearance<.65]=np.inf
    origin=int(np.argmin((xy**2).sum(axis=1)))
    cost=np.full(len(xy),np.inf);cost[origin]=node_cost[0,origin]
    parents=[]
    for i in range(1,len(offsets)):
        # Track lateral displacement in transported cross-sectional coordinates.
        lateral=cdist(xy,xy)
        edge=1.5*lateral**2/max(offsets[i]-offsets[i-1],.2)
        edge[lateral>1.25]=np.inf
        combined=cost[:,None]+edge
        parent=np.argmin(combined,axis=0);cost=combined[parent,np.arange(len(xy))]+node_cost[i]
        parents.append(parent)
        if not np.isfinite(cost).any():raise RuntimeError(f'No continuous candidate with 0.65 mm clearance at original station {offsets[i]:.3f}; investigate, do not force through wall')
    # Avoid the original endpoint's 0.2 mm wall clearance while staying in its end plane.
    best=int(np.argmin(cost+1.0*(xy**2).sum(axis=1)))
    ids=[best]
    for parent in parents[::-1]:best=int(parent[best]);ids.append(best)
    ids=np.array(ids[::-1]);selected=points[np.arange(len(offsets)),ids]
    lateral=xy[ids].copy()
    smooth=gaussian_filter1d(lateral,2.2,axis=0,mode='nearest');smooth[0]=0
    selected=centers+smooth[:,0,None]*a+smooth[:,1,None]*b
    fine_offsets=np.unique(np.r_[np.linspace(0,total,int(np.ceil(total/.1))+1),source['junctions']])
    curve=CubicSpline(offsets,selected,bc_type='natural');candidate=curve(fine_offsets)
    np.savez(ROOT/'data/candidate_route.npz',points=candidate,original_offsets=fine_offsets,station_offsets=offsets,station_points=selected)
    print('Smoothed candidate worst clearance',g.worst(candidate).min(),'end shift',np.linalg.norm(candidate[-1]-original[-1]),flush=True)
    write(ROOT/'reports/corridor_search.json',{'cross_section_search_radius_mm':3.5,'cross_section_grid_step_mm':.5,'station_step_max_mm':.75,'states':[-.4,0,1.],'minimum_candidate_threshold_mm':.65,'preferred_clearance_mm':1.6,'station_original_offsets_mm':offsets.tolist(),'station_max_grid_clearance_mm':clearance.max(axis=1).tolist(),'candidate_end_shift_mm':float(np.linalg.norm(candidate[-1]-original[-1])),'source_end':original[-1].tolist(),'candidate_end':candidate[-1].tolist(),'source_start':original[0].tolist(),'candidate_start':candidate[0].tolist()})

if __name__=='__main__':search()
