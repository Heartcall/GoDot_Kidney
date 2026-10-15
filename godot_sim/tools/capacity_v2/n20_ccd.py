"""Linear-motion finite-triangle event research, NOT an exact-arithmetic CCD
certificate. Exhaustive swept boxes, cubic vertex-face/edge-edge coplanarity
events, finite classification between events. Identically coplanar/ill-conditioned
events are UNRESOLVED, never 'safe'. All endpoints retain 1e-10 mm predicates.
"""
from n20_model import *
import vtk
from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray
from diagnose_n0_contacts import classify_pair

def swept_pairs(v,f,d,w,g,e,self_scan=False):
    left=np.minimum(v[f],(v+d)[f]).min(1);right=np.maximum(v[f],(v+d)[f]).max(1)
    lo=np.minimum(w[g],(w+e)[g]).min(1);hi=np.maximum(w[g],(w+e)[g]).max(1)
    bits=np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0],[0,0,1],[1,0,1],[1,1,1],[0,1,1]])
    points=(lo[:,None,:]+bits[None,:,:]*(hi-lo)[:,None,:]).reshape(-1,3)
    pts=vtk.vtkPoints();pts.SetData(numpy_to_vtk(points,deep=True));grid=vtk.vtkUnstructuredGrid();grid.SetPoints(pts)
    conn=np.column_stack([np.full(len(g),8,np.int64),np.arange(len(g)*8).reshape(-1,8)]).ravel()
    cells=vtk.vtkCellArray();cells.SetCells(len(g),numpy_to_vtkIdTypeArray(conn,deep=True));grid.SetCells(vtk.VTK_HEXAHEDRON,cells)
    loc=vtk.vtkStaticCellLocator();loc.SetDataSet(grid);loc.BuildLocator();ids=vtk.vtkIdList();pairs=[]
    for i in range(len(f)):
        loc.FindCellsWithinBounds((left[i,0],right[i,0],left[i,1],right[i,1],left[i,2],right[i,2]),ids)
        pairs.extend((i,int(ids.GetId(k))) for k in range(ids.GetNumberOfIds()) if not self_scan or ids.GetId(k)>i)
    pairs=np.asarray(pairs,np.int64).reshape(-1,2)
    if not len(pairs):return pairs
    i,j=pairs.T;keep=(left[i]<=hi[j]).all(1)&(lo[j]<=right[i]).all(1)
    if self_scan:
        # Shared mesh features have permanent events. Keep them in a separate
        # unresolved counter instead of silently certifying their neighborhood.
        pass
    return pairs[keep]

def coplanarity_coeff(a,da,b,db,c,dc,p,dp):
    x,y,z=b-a,c-a,p-a;dx,dy,dz=db-da,dc-da,dp-da
    det=lambda x,y,z:np.einsum('...i,...i->...',x,np.cross(y,z))
    return np.stack([det(x,y,z),det(dx,y,z)+det(x,dy,z)+det(x,y,dz),
        det(dx,dy,z)+det(dx,y,dz)+det(x,dy,dz),det(dx,dy,dz)],axis=-1)

def event_intervals(a,da,b,db):
    coefficients=[]
    for k in range(3):
        coefficients.append(coplanarity_coeff(a[0],da[0],a[1],da[1],a[2],da[2],b[k],db[k]))
        coefficients.append(coplanarity_coeff(b[0],db[0],b[1],db[1],b[2],db[2],a[k],da[k]))
    for i,j in [(0,1),(1,2),(2,0)]:
        for k,l in [(0,1),(1,2),(2,0)]:coefficients.append(coplanarity_coeff(a[i],da[i],a[j],da[j],b[k],db[k],b[l],db[l]))
    events=[0.,1.];unresolved=False
    for co in coefficients:
        scale=max(np.max(np.abs(co)),1e-300)
        if scale<1e-13:unresolved=True;continue
        co=co/scale
        bern=np.array([co[0],co[0]+co[1]/3,co[0]+2*co[1]/3+co[2]/3,co.sum()])
        if np.all(bern>0) or np.all(bern<0):continue
        nz=np.flatnonzero(abs(co)>1e-14)
        if not len(nz):unresolved=True;continue
        roots=np.roots(co[:nz[-1]+1][::-1])
        for root in roots:
            if abs(root.imag)<1e-8 and -1e-10<=root.real<=1+1e-10:
                t=float(np.clip(root.real,0,1));events.append(t)
                if abs(np.polynomial.polynomial.polyval(t,co))>1e-8:unresolved=True
            elif abs(root.imag)<1e-6 and 0<=root.real<=1:unresolved=True
    events=sorted(set(events));return events,unresolved

def research_ccd(v,f,d,w,g,e,pairs):
    # A fixed separating axis whose projection intervals over BOTH endpoints
    # are disjoint certifies separation for linear vertex motion. This is an
    # interval bound, not a temporal sampling shortcut or inflated tolerance.
    retained=[]
    for begin in range(0,len(pairs),8192):
        pp=pairs[begin:begin+8192];a=v[f[pp[:,0]]];aa=a+d[f[pp[:,0]]];b=w[g[pp[:,1]]];bb=b+e[g[pp[:,1]]]
        ea=a[:,[1,2,0]]-a;eb=b[:,[1,2,0]]-b
        axes=[np.cross(x[:,1]-x[:,0],x[:,2]-x[:,0]) for x in [a,aa,b,bb]]
        axes.extend(np.cross(ea[:,i],eb[:,j]) for i in range(3) for j in range(3))
        clear=np.zeros(len(pp),bool)
        for axis in axes:
            axis=normalize(axis);pa=np.einsum('nki,ni->nk',np.concatenate([a,aa],1),axis);pb=np.einsum('nki,ni->nk',np.concatenate([b,bb],1),axis)
            clear|=(pa.min(1)>pb.max(1)+1e-12)|(pb.min(1)>pa.max(1)+1e-12)
        retained.append(pp[~clear])
    finite_pairs=np.concatenate(retained) if retained else np.empty((0,2),int)
    crossing=[];unresolved=[];contacts=[];event_count=0
    for count,(i,j) in enumerate(finite_pairs):
        a,da,b,db=v[f[i]],d[f[i]],w[g[j]],e[g[j]]
        events,uncertain=event_intervals(a,da,b,db);event_count+=len(events)-2
        if uncertain:unresolved.append([int(i),int(j)])
        for u in events[1:-1]:
            row=classify_pair(a+u*da,np.array([[0,1,2]]),b+u*db,np.array([[0,1,2]]),0,0,u,True,{},input_origin=np.zeros(3))
            if row['class'] in ['FINITE_TRANSVERSE_CROSSING','COPLANAR_OVERLAP','POINT_CONTACT_OR_TANGENCY','EDGE_CONTACT','EDGE_FACE_CONTACT']:
                contacts.append({'first_face':int(i),'second_face':int(j),'u':u,'class':row['class'],'center_mm':row['center_mm']})
        # A transverse finite intersection persists on an open interval; test
        # each event partition midpoint. Tangency at a root is not a transverse
        # crossing and needs separate contact analysis.
        for low,high in zip(events[:-1],events[1:]):
            if high-low<1e-12:continue
            u=(low+high)/2
            row=classify_pair(a+u*da,np.array([[0,1,2]]),b+u*db,np.array([[0,1,2]]),0,0,u,True,{},input_origin=np.zeros(3))
            if row['class']=='FINITE_TRANSVERSE_CROSSING':
                crossing.append({'first_face':int(i),'second_face':int(j),'u':u,'event_interval':[low,high],
                    'center_mm':row['center_mm'],'finite_segment_length_mm':row['finite_segment_length_mm']});break
        if count and count%10000==0:print('CCD finite pairs',count,'of',len(finite_pairs),flush=True)
    return {'pairs':len(pairs),'separating_axis_interval_proven_disjoint_pairs':len(pairs)-len(finite_pairs),'finite_event_pairs':len(finite_pairs),
        'cubic_events':event_count,'confirmed_crossing_intervals':crossing,'finite_contact_events':contacts,
        'unresolved_coplanar_or_conditioned_pairs':unresolved,'continuous_safety_certified':False,
        'method':'Swept finite boxes; 6 VF + 9 EE cubic events; finite interval midpoints; degenerate/identically coplanar events unresolved',
        'limits':'Floating roots are research diagnostics, not outward-rounded proof. Permanent contacts need a contact-manifold certificate. No exact CCD claim.'}

if __name__=='__main__':
    protected();a,d2,tv,tf,resolved,approval=inputs();side=sys.argv[1];tr=read(OUT/side/'trajectory.json');n=len(tr['states'])
    c=np.load(OUT/side/f'cavity_{n:03}.npy');t=np.load(OUT/side/f'tissue_{n:03}.npy')
    # Research the complete Reference-to-endpoint chord as well as accepted
    # states in the verifier; no claim that different chords are the same path.
    pairs=swept_pairs(a['vertices'],a['faces'],c,tv,tf,t)
    np.save(OUT/side/'swept_cavity_tissue_pairs.npy',pairs)
    r=research_ccd(a['vertices'],a['faces'],c,tv,tf,t,pairs)
    gzip_write(OUT/side/'ccd_reference_chord.json.gz',r);protected();print('CCD',side,'pairs',len(pairs),'crossings',len(r['confirmed_crossing_intervals']),'unresolved',len(r['unresolved_coplanar_or_conditioned_pairs']),flush=True)
