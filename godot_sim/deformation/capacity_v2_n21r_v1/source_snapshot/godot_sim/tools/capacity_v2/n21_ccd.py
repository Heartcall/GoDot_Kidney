"""Error-controlled linear-endpoint CCD research.
Fixed-axis dot products use outward IEEE binary64 intervals. Remaining finite
pairs use EXACT rational polynomial Bernstein signs and exact dyadic witnesses.
Unknown time boxes stay UNRESOLVED. This certifies no transverse crossing,
not absence of every legal contact or the acceptability of new coplanar overlap.
"""
from n21_common import *
from fractions import Fraction as F
from math import comb
import vtk
from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray

def padd(a,b):
    z=[F(0)]*max(len(a),len(b))
    for i,x in enumerate(a):z[i]+=x
    for i,x in enumerate(b):z[i]+=x
    while len(z)>1 and not z[-1]:z.pop()
    return z
def pneg(a):return [-x for x in a]
def psub(a,b):return padd(a,pneg(b))
def pmul(a,b):
    z=[F(0)]*(len(a)+len(b)-1)
    for i,x in enumerate(a):
        for j,y in enumerate(b):z[i+j]+=x*y
    while len(z)>1 and not z[-1]:z.pop()
    return z
def vsub(a,b):return [psub(x,y) for x,y in zip(a,b)]
def vcross(a,b):return [psub(pmul(a[1],b[2]),pmul(a[2],b[1])),psub(pmul(a[2],b[0]),pmul(a[0],b[2])),psub(pmul(a[0],b[1]),pmul(a[1],b[0]))]
def vdot(a,b):
    result=[F(0)]
    for x,y in zip(a,b):result=padd(result,pmul(x,y))
    return result
def bernstein(p):
    n=len(p)-1
    return [sum((p[i]*F(comb(k,i),comb(n,i)) for i in range(k+1)),F(0)) for k in range(n+1)]
def split(b):
    left=[b[0]];right=[b[-1]];row=b
    while len(row)>1:
        row=[(x+y)/2 for x,y in zip(row[:-1],row[1:])];left.append(row[0]);right.append(row[-1])
    return left,right[::-1]
def evaluate(p,t):
    value=F(0)
    for c in p[::-1]:value=value*t+c
    return value
def trajectory(start,end):
    return [[[F(float(x)),F(float(y))-F(float(x))] for x,y in zip(a,b)] for a,b in zip(start,end)]

def exact_crossing(a,b):
    sub=lambda x,y:[p-q for p,q in zip(x,y)]
    cross=lambda x,y:[x[1]*y[2]-x[2]*y[1],x[2]*y[0]-x[0]*y[2],x[0]*y[1]-x[1]*y[0]]
    dot=lambda x,y:sum((p*q for p,q in zip(x,y)),F(0))
    na=cross(sub(a[1],a[0]),sub(a[2],a[0]));nb=cross(sub(b[1],b[0]),sub(b[2],b[0]));line=cross(na,nb)
    if not any(line):return False
    da=[dot(sub(p,b[0]),nb) for p in a];db=[dot(sub(p,a[0]),na) for p in b]
    if not (min(da)<0<max(da) and min(db)<0<max(db)):return False
    axis=max(range(3),key=lambda i:abs(line[i]))
    def cut(points,distances):
        values=[]
        for i,j in [(0,1),(1,2),(2,0)]:
            if distances[i]==0:values.append(points[i][axis])
            if distances[i]*distances[j]<0:
                t=distances[i]/(distances[i]-distances[j]);values.append(points[i][axis]+t*(points[j][axis]-points[i][axis]))
        return values
    aa,bb=cut(a,da),cut(b,db)
    return bool(len(aa)>=2 and len(bb)>=2 and min(max(aa),max(bb))>max(min(aa),min(bb)))

def exact_pair(a0,a1,b0,b1,max_depth=3):
    A=trajectory(a0,a1);B=trajectory(b0,b1);ea=[vsub(A[j],A[i]) for i,j in [(0,1),(1,2),(2,0)]];eb=[vsub(B[j],B[i]) for i,j in [(0,1),(1,2),(2,0)]]
    na=vcross(ea[0],pvector_neg(ea[2]));nb=vcross(eb[0],pvector_neg(eb[2]))
    def positive_normal(normal):
        squared=bernstein(vdot(normal,normal))
        def positive(coeff,depth):
            if all(x>0 for x in coeff):return True
            if coeff[0]==0 or coeff[-1]==0 or depth==0:return False
            left,right=split(coeff);return positive(left,depth-1) and positive(right,depth-1)
        return positive(squared,6)
    if not positive_normal(na) or not positive_normal(nb):
        return {'class':'UNRESOLVED_DEGENERATE_OR_CONDITIONED_FACE','witness_or_box':None,'exact_shared_trajectories':0,
            'permanent_coplanar':False,'reference_exact_transverse':False,'shared_feature_alone_used_as_certificate':False}
    # Lazy exact face-plane certificate. This is the same first separating
    # direction as below, without constructing 15 unused polynomial axes.
    # It changes cost, never arithmetic precision or acceptance thresholds.
    shared=sum(1 for x in A for y in B if x==y)
    orientA=[vdot(na,vsub(y,A[0])) for y in B]
    orientB=[vdot(nb,vsub(x,B[0])) for x in A]
    permanent_coplanar=all(not any(p) for p in orientA+orientB)
    for orient in [orientA,orientB]:
        signs=[bernstein(p) for p in orient]
        if all(all(c>=0 for c in p) for p in signs) or all(all(c<=0 for c in p) for p in signs):
            return {'class':'CERTIFIED_NO_TRANSVERSE_PERSISTENT_COPLANAR' if permanent_coplanar else ('CERTIFIED_NO_TRANSVERSE_SHARED_FEATURE' if shared else 'CERTIFIED_NO_TRANSVERSE_SEPARATING_POLYNOMIAL'),
                'witness_or_box':None,'exact_shared_trajectories':shared,'permanent_coplanar':permanent_coplanar,
                'reference_exact_transverse':False,'shared_feature_alone_used_as_certificate':False}
    # Valid arbitrary separating directions, including in-plane edge directions
    # needed by permanent coplanar/shared-feature pairs.
    axes=[na,nb]+[vcross(x,y) for x in ea for y in eb]+[vcross(n,e) for n,es in [(na,ea),(nb,eb)] for e in es]
    certificates=[]
    for axis in axes:
        if not any(any(c) for c in axis):continue
        certificates.append([bernstein(vdot(axis,vsub(y,x))) for x in A for y in B])
    normal_orients=[vdot(na,vsub(y,A[0])) for y in B]+[vdot(nb,vsub(x,B[0])) for x in A]
    permanent_coplanar=all(not any(p) for p in normal_orients)
    shared=sum(1 for x in A for y in B if x==y)
    baseline=exact_crossing([[p[0] for p in x] for x in A],[[p[0] for p in y] for y in B])
    def visit(certs,lo,hi,depth):
        for polys in certs:
            if all(all(c>=0 for c in p) for p in polys) or all(all(c<=0 for c in p) for p in polys):return 'CLEAR',None
        mid=(lo+hi)/2
        aa=[[evaluate(p,mid) for p in x] for x in A];bb=[[evaluate(p,mid) for p in y] for y in B]
        if exact_crossing(aa,bb):return 'CROSSING',str(mid)
        if depth==max_depth:return 'UNRESOLVED',str((lo,hi))
        left=[];right=[]
        for polys in certs:
            parts=[split(p) for p in polys];left.append([p[0] for p in parts]);right.append([p[1] for p in parts])
        x,w=visit(left,lo,mid,depth+1)
        if x=='CROSSING':return x,w
        y,z=visit(right,mid,hi,depth+1)
        if y=='CROSSING':return y,z
        return ('CLEAR',None) if x==y=='CLEAR' else ('UNRESOLVED',w or z)
    status,witness=visit(certificates,F(0),F(1),0)
    if status=='CLEAR':classification='CERTIFIED_NO_TRANSVERSE_PERSISTENT_COPLANAR' if permanent_coplanar else ('CERTIFIED_NO_TRANSVERSE_SHARED_FEATURE' if shared else 'CERTIFIED_NO_TRANSVERSE_SEPARATING_POLYNOMIAL')
    elif status=='CROSSING':classification='CERTIFIED_REFERENCE_TRANSVERSE_EXISTS' if baseline else 'CERTIFIED_NEW_TRANSVERSE_EXISTS'
    else:classification='UNRESOLVED_BERNSTEIN_TIME_BOX'
    return {'class':classification,'witness_or_box':witness,'exact_shared_trajectories':shared,'permanent_coplanar':permanent_coplanar,
        'reference_exact_transverse':baseline,'shared_feature_alone_used_as_certificate':False}

def pvector_neg(v):return [pneg(x) for x in v]

def interval_projection(points,axis):
    values=points*axis[:,None,:];lower=np.nextafter(values,-np.inf);upper=np.nextafter(values,np.inf)
    lo=np.nextafter(np.nextafter(lower[:,:,0]+lower[:,:,1],-np.inf)+lower[:,:,2],-np.inf)
    hi=np.nextafter(np.nextafter(upper[:,:,0]+upper[:,:,1],np.inf)+upper[:,:,2],np.inf)
    return lo,hi

def interval_filter(a0,f,a1,b0,g,b1,pairs):
    keep=[]
    for offset in range(0,len(pairs),4096):
        pp=pairs[offset:offset+4096];a=a0[f[pp[:,0]]];aa=a1[f[pp[:,0]]];b=b0[g[pp[:,1]]];bb=b1[g[pp[:,1]]]
        ea=a[:,[1,2,0]]-a;eb=b[:,[1,2,0]]-b;na=np.cross(ea[:,0],-ea[:,2]);nb=np.cross(eb[:,0],-eb[:,2])
        axes=[na,nb,np.cross(aa[:,1]-aa[:,0],aa[:,2]-aa[:,0]),np.cross(bb[:,1]-bb[:,0],bb[:,2]-bb[:,0])]
        axes.extend(np.cross(x,y) for x in ea.transpose(1,0,2) for y in eb.transpose(1,0,2))
        axes.extend(np.cross(n,e[:,i]) for n,e in [(na,ea),(nb,eb)] for i in range(3))
        clear=np.zeros(len(pp),bool)
        for axis in axes:
            loA,hiA=interval_projection(np.concatenate([a,aa],1),axis);loB,hiB=interval_projection(np.concatenate([b,bb],1),axis)
            clear|=(loA.min(1)>hiB.max(1))|(loB.min(1)>hiA.max(1))
        keep.append(pp[~clear])
    return np.concatenate(keep) if keep else np.empty((0,2),np.int64)

def swept(a0,f,a1,b0,g,b1,self_scan=False):
    left=np.nextafter(np.minimum(a0[f],a1[f]).min(1),-np.inf);right=np.nextafter(np.maximum(a0[f],a1[f]).max(1),np.inf)
    lo=np.nextafter(np.minimum(b0[g],b1[g]).min(1),-np.inf);hi=np.nextafter(np.maximum(b0[g],b1[g]).max(1),np.inf)
    bits=np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0],[0,0,1],[1,0,1],[1,1,1],[0,1,1]])
    points=np.where(bits[None,:,:],hi[:,None,:],lo[:,None,:]).reshape(-1,3);pts=vtk.vtkPoints();pts.SetData(numpy_to_vtk(points,deep=True))
    grid=vtk.vtkUnstructuredGrid();grid.SetPoints(pts);cells=vtk.vtkCellArray()
    cells.SetData(numpy_to_vtkIdTypeArray(np.arange(0,len(g)*8+1,8,dtype=np.int64),deep=True),numpy_to_vtkIdTypeArray(np.arange(len(g)*8,dtype=np.int64),deep=True));grid.SetCells(vtk.VTK_HEXAHEDRON,cells)
    locator=vtk.vtkStaticCellLocator();locator.SetDataSet(grid);locator.BuildLocator();ids=vtk.vtkIdList();pairs=[]
    for i in range(len(f)):
        locator.FindCellsWithinBounds((left[i,0],right[i,0],left[i,1],right[i,1],left[i,2],right[i,2]),ids)
        pairs.extend((i,int(ids.GetId(k))) for k in range(ids.GetNumberOfIds()) if not self_scan or ids.GetId(k)>i)
    pairs=np.array(pairs,np.int64).reshape(-1,2);i,j=pairs.T
    return pairs[(left[i]<=hi[j]).all(1)&(lo[j]<=right[i]).all(1)]

def run(name,fresh=False):
    protect();a,d2,tv,tf,resolved,approval=inputs()
    if name=='s1_n20_passed':c=np.load(OLD/'regression_S1_expand/cavity_001.npy');t=np.load(OLD/'regression_S1_expand/tissue_001.npy')
    elif name=='s2_warm':c=np.load(ROOT/'warm_contact/S2_expand/cavity_offset.npy');t=np.load(ROOT/'warm_contact/S2_expand/tissue_offset.npy')
    elif name.startswith('robust_contract'):c=np.load(ROOT/name/'cavity_offset.npy');t=np.load(ROOT/name/'tissue_offset.npy')
    else:c,t,_=fixture(name)
    end=a['vertices']+c;tend=tv+t;root=ROOT/'ccd'/(name+'_fresh' if fresh else name);root.mkdir(parents=True,exist_ok=True)
    pairs=swept(a['vertices'],a['faces'],end,tv,tf,tend);remaining=interval_filter(a['vertices'],a['faces'],end,tv,tf,tend,pairs)
    np.save(root/'candidate_pairs.npy',remaining);rows=[];start=time.time()
    source={'cavity':hashlib.sha256(end.tobytes()).hexdigest(),'tissue':hashlib.sha256(tend.tobytes()).hexdigest(),
        'cavity_faces':hashlib.sha256(a['faces'].tobytes()).hexdigest(),'tissue_faces':hashlib.sha256(tf.tobytes()).hexdigest(),
        'settings':{'depth':3,'version':'EXACT_INTERVAL_V2','kernel_sha256':sha(__file__)}}
    partial=root/'partial_certificates.json.gz'
    if partial.exists():
        cached=read(partial)
        if cached['sources']!=source:raise ValueError('CCD checkpoint source/settings mismatch')
        rows=cached['rows']
    for k,(i,j) in enumerate(remaining):
        if k<len(rows):continue
        row=exact_pair(a['vertices'][a['faces'][i]],end[a['faces'][i]],tv[tf[j]],tend[tf[j]])
        rows.append({'cavity_face':int(i),'tissue_face':int(j),**row})
        if k and k%500==0:
            gzip_write(partial,{'sources':source,'rows':rows})
            print('EXACT CCD',name,k,'/',len(remaining),'seconds',round(time.time()-start,1),flush=True)
    from collections import Counter
    counts=dict(Counter(x['class'] for x in rows));gzip_write(root/'pair_certificates.json.gz',rows)
    write(root/'summary.json',{'name':name,'trajectory_definition':'Exact affine interpolation between supplied IEEE binary64 vertex ENDPOINTS; not float32 quantized runtime motion',
        'sources_and_settings':source,
        'broad_pairs':len(pairs),'certified_fixed_axis_separation_pairs':len(pairs)-len(remaining),'exact_pair_counts':counts,
        'full_continuous_safe':False,'scope':'Complete cavity-tissue transverse analysis; self-CCD and new-overlap acceptability require separate gates',
        'unresolved_never_passed':True,'max_time_depth':3,'exact_witness_uses_no_increased_contact_tolerance':True,
        'source_endpoint_sha256':{'cavity':hashlib.sha256(end.tobytes()).hexdigest(),'tissue':hashlib.sha256(tend.tobytes()).hexdigest()},
        'arithmetic':'Outward nextafter fixed-axis projection intervals; Fraction exact rational Bernstein sign tests and dyadic finite witnesses',
        'seconds_exact_stage':time.time()-start});protect();print('CCD RESULT',name,counts,flush=True)

def self_scope(name,mesh_name):
    protect();a,d2,tv,tf,resolved,approval=inputs()
    if name=='s1_n20_passed':c=np.load(OLD/'regression_S1_expand/cavity_001.npy');t=np.load(OLD/'regression_S1_expand/tissue_001.npy')
    else:c=np.load(ROOT/name/'cavity_offset.npy');t=np.load(ROOT/name/'tissue_offset.npy')
    v,f,offset=(a['vertices'],a['faces'],c) if mesh_name=='cavity' else (tv,tf,t)
    end=v+offset;root=ROOT/'ccd_self'/name/mesh_name;root.mkdir(parents=True,exist_ok=True)
    pairs=swept(v,f,end,v,f,end,self_scan=True)
    shared=np.zeros(len(pairs),np.int8)
    for start in range(0,len(pairs),65536):
        pp=pairs[start:start+65536];shared[start:start+len(pp)]=(f[pp[:,0],:,None]==f[pp[:,1],None,:]).sum(axis=(1,2))
    stationary=np.all(offset[f]==0,axis=(1,2));invariant=stationary[pairs[:,0]]&stationary[pairs[:,1]]
    if mesh_name=='cavity':
        original,_old,_=fixture('contract');changed=np.linalg.norm(offset-original,axis=1)>1e-12;focus_faces=np.flatnonzero(changed[f].any(1))
    else:
        focus=np.unique(np.r_[tf[53208],34757,34758,61933,61934,30663,93578]);focus_faces=np.flatnonzero(np.isin(f,focus).any(1))
    selected=(shared==0)|((shared==1)&(np.isin(pairs[:,0],focus_faces)|np.isin(pairs[:,1],focus_faces)))
    selected&=~invariant
    subset=pairs[selected];retained=interval_filter(v,f,end,v,f,end,subset);rows=[]
    for k,(i,j) in enumerate(retained):
        rows.append({'first_face':int(i),'second_face':int(j),**exact_pair(v[f[i]],end[f[i]],v[f[j]],end[f[j]])})
        if k and k%1000==0:print('SELF CCD',name,mesh_name,k,'/',len(retained),flush=True)
    from collections import Counter
    counts=dict(Counter(x['class'] for x in rows));gzip_write(root/'pair_certificates.json.gz',rows)
    write(root/'summary.json',{'mesh':mesh_name,'name':name,'broad_pairs':len(pairs),'invariant_reference_pairs':int(invariant.sum()),
        'shared_edge_pairs_no_transverse_by_common_edge_identity':int(((shared>=2)&~invariant).sum()),
        'unprocessed_shared_one_vertex_pairs':int(((shared==1)&~selected&~invariant).sum()),
        'selected_pairs':len(subset),'certified_interval_separated_selected_pairs':len(subset)-len(retained),'exact_class_counts':counts,
        'full_self_continuous_safety_certified':False,'shared_feature_coplanar_overlap_not_certified':True,
        'scope':'All nonadjacent moving pairs plus critical one-vertex neighborhoods. Remaining shared-one-vertex pairs explicitly unresolved by scope; no silent exclusion.'})
    protect();print('SELF CCD RESULT',name,mesh_name,counts,flush=True)

if __name__=='__main__':
    if '--fresh' in sys.argv:run(sys.argv[1],fresh=True)
    elif len(sys.argv)>2:self_scope(sys.argv[1],sys.argv[2])
    else:run(sys.argv[1])
