"""Independent N2.0 five-level, all physical self scans and volume audit.
Passing sampled geometry never promotes research data to production.
"""
from n20_model import *
from n16_closure_and_regions import closure_variants,local_quality,centerline_clearance
import trimesh
import math
from decimal import Decimal,localcontext

def independent_volume(v,f):
    """Far-origin float64 cancellation is NOT a geometric failure. Recompute
    that independent integral in Decimal(40), without relaxing any geometry
    predicate or changing the D2 surface."""
    mesh=trimesh.Trimesh(v,f,process=False);origin=v[np.unique(f)].mean(0);tri=(v-origin)[f]
    cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    flux=[math.fsum((tri[:,:,axis].mean(1)*cross[:,axis]/2).tolist())/1000 for axis in range(3)]
    with localcontext() as ctx:
        ctx.prec=40
        origin_d=[Decimal(1000),Decimal(-1000),Decimal(500)]
        vertices=[[Decimal.from_float(float(x))-o for x,o in zip(row,origin_d)] for row in v]
        total=Decimal(0)
        for i,j,k in f:
            a,b,c=vertices[i],vertices[j],vertices[k]
            total+=a[0]*(b[1]*c[2]-b[2]*c[1])+a[1]*(b[2]*c[0]-b[0]*c[2])+a[2]*(b[0]*c[1]-b[1]*c[0])
        high_precision=float(total/6000)
    values=[volume(v,f),mesh.volume/1000,high_precision]+flux
    _,counts=np.unique(mesh.edges_sorted,axis=0,return_counts=True)
    result={'volume_mL':values[0],'trimesh_mL':values[1],'far_origin_decimal40_mL':values[2],'axis_flux_mL':flux,
        'method_spread_mL':float(np.ptp(values)),'watertight':bool(mesh.is_watertight),'winding_consistent':bool(mesh.is_winding_consistent),
        'boundary_edges':int((counts==1).sum()),'nonmanifold_edges':int((counts>2).sum()),'minimum_area_mm2':float(mesh.area_faces.min()),
        'far_origin_float64_mL':volume(v-np.array([1000,-1000,500]),f),'source_face_indices_unchanged':True,
        'units':'mm, mm2, mL; 1000 mm3 = 1 mL'}
    result['numerically_valid']=bool(result['watertight'] and result['winding_consistent'] and result['minimum_area_mm2']>1e-10 and result['method_spread_mL']<1e-9)
    return result

def step_area_bounds(ref,f,start,end):
    """Exact floating-polynomial extrema on an accepted segment, normalized
    to ORIGINAL reference areas and oriented normals, not the last step."""
    tri=(ref+start)[f];dd=(end-start)[f];orig=ref[f]
    c0=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    e1,e2=tri[:,1]-tri[:,0],tri[:,2]-tri[:,0];h1,h2=dd[:,1]-dd[:,0],dd[:,2]-dd[:,0]
    c1=np.cross(h1,e2)+np.cross(e1,h2);c2=np.cross(h1,h2)
    normal=np.cross(orig[:,1]-orig[:,0],orig[:,2]-orig[:,0]);dot=lambda a,b:np.einsum('ij,ij->i',a,b)
    den=dot(normal,normal);co=np.stack([dot(c0,c0),2*dot(c0,c1),dot(c1,c1)+2*dot(c0,c2),2*dot(c1,c2),dot(c2,c2)],1)/den[:,None]
    lo=np.minimum(co[:,0],co.sum(1));hi=np.maximum(co[:,0],co.sum(1));der=co[:,1:]*np.arange(1,5)
    p0,p1,p2,p3=der.T;bern=np.stack([p0,p0+p1/3,p0+2*p1/3+p2/3,p0+p1+p2+p3],1)
    for i in np.flatnonzero(~((bern>=0).all(1)|(bern<=0).all(1))):
        r=np.roots(der[i,::-1]);t=r.real[(abs(r.imag)<1e-9)&(r.real>0)&(r.real<1)]
        if len(t):values=np.polynomial.polynomial.polyval(t,co[i]);lo[i]=min(lo[i],values.min());hi[i]=max(hi[i],values.max())
    oc=np.stack([dot(c0,normal),dot(c1,normal),dot(c2,normal)],1)/den[:,None];oriented=np.minimum(oc[:,0],oc.sum(1))
    t=np.divide(-oc[:,1],2*oc[:,2],out=np.zeros(len(f)),where=abs(oc[:,2])>1e-30);valid=(t>0)&(t<1)
    oriented[valid]=np.minimum(oriented[valid],np.sum(oc[valid]*np.stack([np.ones(valid.sum()),t[valid],t[valid]**2],1),1))
    return {'minimum_area_ratio':float(np.sqrt(np.maximum(0,lo.min()))),'maximum_area_ratio':float(np.sqrt(hi.max())),
        'minimum_reference_oriented_area_ratio':float(oriented.min()),'minimum_face':int(np.argmin(lo)),
        'pass':bool(lo.min()>=.8**2 and hi.max()<=1.35**2 and oriented.min()>0),
        'edge_gradient_note':'Norm of linear relative displacement is convex; both endpoint tests suffice for the 0.2 edge gate.'}

def added_shared_vertex_crossings(v,f):
    """Existing N1.6 self scans excluded shared vertices. Supplement strict
    transverse tests for shared-one-vertex pairs. Shared-edge triangles cannot
    have transverse intersection beyond their common line if nondegenerate.
    Their coplanar overlap remains explicitly a separate validation limitation.
    """
    graph=[[] for _ in range(len(v))]
    for i,face in enumerate(f):
        for vi in face:graph[vi].append(i)
    pairs=set()
    for incident in graph:
        for k,i in enumerate(incident):
            for j in incident[k+1:]:
                if len(set(f[i])&set(f[j]))==1:pairs.add((min(i,j),max(i,j)))
    pairs=np.asarray(sorted(pairs),np.int64).reshape(-1,2)
    from audit_tissue_cavity import classify_contacts
    proper,_=classify_contacts(v,f,v,f,pairs,tolerance=1e-10)
    result=classify(v,f,v,f,pairs[proper])
    result['shared_vertex_pairs_tested_for_transverse']=len(pairs)
    result['shared_feature_coplanar_overlap_exhaustively_certified']=False
    return result

def verify(side):
    protected();a,d2,tv,tf,resolved,approval=inputs();root=OUT/side;tr=read(root/'trajectory.json');n=len(tr['states'])
    cv=np.load(root/f'cavity_{n:03}.npy');tt=np.load(root/f'tissue_{n:03}.npy');baseline=read(PROJECT/'deformation/capacity_v2_n16_v1/contact_baseline.json')['results']
    fixed=a['port_fixed_masks'].any(0);remote=np.load(PROJECT/'deformation/p2/evidence/remote_anchors.npy');exact=np.load(PROJECT/'deformation/p2/evidence/coincident_mask.npy');ids=np.load(PROJECT/'deformation/p2/evidence/coincident_cavity_vertex.npy')
    levels=[]
    def compact(record,path):
        return {**{k:v for k,v in record.items() if k!='results'},'results':{k:{a:b for a,b in value.items() if a!='rows'} for k,value in record['results'].items()},
            'full_finite_geometry_evidence':path.relative_to(OUT).as_posix(),'evidence_sha256':sha(path)}
    for u in [0,.25,.5,.75,1.]:
        dest=root/f'verify_u{round(100*u):03}.json.gz'
        if dest.exists():
            cached=read(dest)
            if cached['cavity_offset_sha256']!=sha(root/f'cavity_{n:03}.npy') or cached['tissue_offset_sha256']!=sha(root/f'tissue_{n:03}.npy'):
                raise ValueError('Stale geometry verification; use a new version directory')
            levels.append(compact(cached,dest));continue
        print('FULL VERIFY',side,u,flush=True);v=a['vertices']+u*cv;t=tv+u*tt;dv=d2['reference_vertices']+u*map_d2(cv,d2);r={}
        for name,x,f,y,g in [('cavity_self',v,a['faces'],v,a['faces']),('tissue_self',t,tf,t,tf),('D2_self',dv,d2['faces'],dv,d2['faces']),('cavity_tissue',v,a['faces'],t,tf)]:
            if u==0:result=baseline[name]
            else:
                pairs=self_bbox_pairs(x,f) if name.endswith('self') else contact_pairs(x,f,y,g)
                result=classify(x,f,y,g,pairs)
            r[name]=result
            print(name,'cross',result['confirmed_transverse_crossings'],flush=True)
        if u>0:
            r['cavity_shared_vertex_transverse']=added_shared_vertex_crossings(v,a['faces'])
            r['tissue_shared_vertex_transverse']=added_shared_vertex_crossings(t,tf)
        cap=closure_variants(dv,d2,approval);integral=independent_volume(dv,d2['faces'])
        report={'u':u,'cavity_offset_sha256':sha(root/f'cavity_{n:03}.npy'),'tissue_offset_sha256':sha(root/f'tissue_{n:03}.npy'),
            'results':r,'integral':integral,'closures':cap,'fixed_maximum_mm':float(np.linalg.norm(u*cv[fixed],axis=1).max()),
            'exact139_relative_maximum_mm':float(np.linalg.norm(u*(tt[exact]-cv[ids[exact]]),axis=1).max()),
            'remote_tissue_maximum_mm':float(np.linalg.norm(u*tt[remote],axis=1).max())}
        gzip_write(dest,report);levels.append(compact(report,dest))
    segments=[];previous_c=np.zeros_like(cv);previous_t=np.zeros_like(tt)
    for k in range(1,n+1):
        c=np.load(root/f'cavity_{k:03}.npy');t=np.load(root/f'tissue_{k:03}.npy')
        segments.append({'from_index':k-1,'to_index':k,'cavity':step_area_bounds(a['vertices'],a['faces'],previous_c,c),
            'tissue':step_area_bounds(tv,tf,previous_t,t),'continuous_collision_certified':False})
        previous_c=c;previous_t=t
    cq=quality(a['vertices'],a['faces'],cv);tq=quality(tv,tf,tt)
    true_crossings=sum(r['confirmed_transverse_crossings'] for s in levels for r in s['results'].values())
    sampled_pass=bool(cq['quality_gate_passed'] and tq['quality_gate_passed'] and not true_crossings and all(x['geometrically_valid_at_sample'] for s in levels for x in s['closures'])
        and all(s['integral'].get('numerically_valid',True) for s in levels))
    local=local_quality(a,resolved,cv,tv,tf,tt);write(root/'local_regions.json',local)
    probes={'reference':centerline_clearance(a,resolved,np.zeros_like(cv)),'endpoint':centerline_clearance(a,resolved,cv)}
    write(root/'channel_probes.json',probes)
    mesh=trimesh.Trimesh(a['vertices']+cv,a['faces'],process=False)
    report={'side':side,'endpoint_index':n,'target_mL':tr['target_mL'],'endpoint_integral_mL':volume(d2['reference_vertices']+map_d2(cv,d2),d2['faces']),
        'five_reference_chord_levels':levels,'cavity':cq,'tissue':tq,'accepted_segment_area_bounds':segments,
        'sampled_gate_passed':sampled_pass,'continuous_collision_certified':False,
        'unchanged_faces_and_owners':True,'watertight_physical_cavity':bool(mesh.is_watertight),'winding_consistent':bool(mesh.is_winding_consistent),
        'branch_continuity_status':'Approved graph and physical mesh connectivity unchanged; sampled centerline clearance compared; not full swept instrument clearance or all possible channel cross-sections',
        'shared_feature_coplanar_overlap_certified':False,'runtime_eligible':False,
        'endpoint_is_global_maximum_or_minimum':False,'new_formal_endpoints_created':False}
    write(root/'verification.json',report);protected();print('VERIFIED SAMPLES',side,sampled_pass,flush=True)

if __name__=='__main__':verify(sys.argv[1])
