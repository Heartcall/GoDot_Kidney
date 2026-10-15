"""N1.6 isolated morphology-guided feasibility prototype, NOT production N2.
No approved displacement is scaled or imported as the new driver.
"""
import os
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='1'
import sys,json,csv,hashlib,subprocess,time,math,argparse,gzip
from pathlib import Path
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import spsolve
from scipy.sparse.csgraph import dijkstra
from scipy.optimize import brentq
PROJECT=Path(__file__).resolve().parents[2];REPO=PROJECT.parent
sys.path.insert(0,str(PROJECT/'tools'))
from build_local_displacement import load_approved_masks,path_projection,normalize,smoothstep,constrained_vector_smoothing,triangle_data,self_intersection_pairs
from build_full_cavity_deformation import topological_candidates,endpoint_adjacency
from build_cavity_surface_masks import mesh_graph
from build_cavity_morph_states import vertex_normals,minimum_oriented_area_ratio
OUT=PROJECT/'deformation/capacity_v2_n16_v1'
N1=PROJECT/'deformation/capacity_v2_n1_v1'
LABEL='MORPHOLOGY_GUIDED_UNCALIBRATED_CAPACITY_ESTIMATE'
TARGETS={'S1':(.95,1.08),'S2':(.90,1.15),'S3':(.85,1.25)}
LEVELS=[0,.25,.5,.75,1]

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):
    p=Path(p)
    if not p.exists() and p.with_suffix(p.suffix+'.gz').exists():p=p.with_suffix(p.suffix+'.gz')
    return json.loads(gzip.decompress(p.read_bytes()).decode('utf8') if p.suffix=='.gz' else p.read_text(encoding='utf8'))
def plain(v):
    if isinstance(v,dict):return {str(k):plain(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [plain(x) for x in v]
    if isinstance(v,np.ndarray):return v.tolist()
    if isinstance(v,np.generic):return v.item()
    return v
def write(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(plain(v),ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n',encoding='utf8')
def protect(initialize=False):
    OUT.mkdir(parents=True,exist_ok=True);p=OUT/'protected_before.json'
    if initialize and not p.exists():
        paths=set()
        for root in [REPO/'docs',PROJECT/'deformation',PROJECT/'analysis/irrigation_baseline',PROJECT/'tools',PROJECT/'scripts',PROJECT/'shaders',PROJECT/'source_assets']:
            paths.update(x for x in root.rglob('*') if x.is_file() and OUT not in x.parents and not x.name.startswith(('n16_','test_n16','kidney_irrigation_capacity_v2_n16_')) and not any(z in x.parts for z in ['__pycache__','source_cache','.mplconfig','matplotlib_cache']))
        paths.update(PROJECT.glob('*.tscn'));paths.update([PROJECT/'project.godot',REPO/'README.md',REPO/'.gitignore'])
        write(p,{x.relative_to(REPO).as_posix():sha(x) for x in sorted(paths)})
    before=read(p);changed=[name for name,h in before.items() if not (REPO/name).is_file() or sha(REPO/name)!=h]
    write(OUT/'protected_after.json',{'files':len(before),'changed':changed})
    if changed:raise ValueError('Protected files changed: '+str(changed))
    return len(before)
def inputs():
    approval=read(N1/'D2_approval_2026_10_14_v1.json')
    for name,h in approval['frozen_geometry_sha256'].items():
        if sha(N1/'d2'/name)!=h:raise ValueError('Frozen D2 hash mismatch')
    p2=PROJECT/'deformation/p2';accepted=read(p2/'accepted_inputs.json')
    for name,row in accepted['arrays'].items():
        if sha(p2/row['runtime'])!=row['sha256'] or row['sha256']!=approval['accepted_source_sha256'][name]:raise ValueError('Accepted arrays mismatch')
    a,report,_=load_approved_masks(PROJECT/'deformation/p1_masks',PROJECT/'deformation/cavity_topology_resolved.json')
    d2={n:np.load(N1/'d2'/f'{n}.npy') for n in ['reference_vertices','faces','source_vertex_ids','source_vertex_weights','source_face_ids']}
    tv=np.load(p2/'runtime/tissue_reference_vertices.npy');tf=np.load(p2/'runtime/tissue_faces.npy')
    return a,d2,tv,tf,read(PROJECT/'deformation/cavity_topology_resolved.json'),approval
def map_d2(field,d2):
    ids=d2['source_vertex_ids'];w=d2['source_vertex_weights']
    if np.any(w[ids<0]!=0):raise ValueError('Negative source ID with nonzero weight')
    return np.einsum('ni,nij->nj',w,field[np.maximum(ids,0)])
def volume(v,f):
    tri=(v-np.array([16.,16.,-81.]))[f]
    return float(np.einsum('ij,ij->i',tri[:,0],np.cross(tri[:,1],tri[:,2])).sum()/6000)
def volume_coefficients(v,f,d):
    tri=(v-np.array([16.,16.,-81.]))[f];z=d[f]
    x,y,w=tri[:,0],tri[:,1],tri[:,2];dx,dy,dw=z[:,0],z[:,1],z[:,2]
    det=lambda a,b,c:float(np.einsum('ij,ij->i',a,np.cross(b,c)).sum()/6000)
    return np.array([det(x,y,w),det(dx,y,w)+det(x,dy,w)+det(x,y,dw),
      det(dx,dy,w)+det(dx,y,dw)+det(x,dy,dw),det(dx,dy,dw)])
def amplitude_for_target(v,f,field,target):
    coeff=volume_coefficients(v,f,field);fun=lambda q:float(np.polynomial.polynomial.polyval(q,coeff)-target)
    high=.025
    while fun(0)*fun(high)>0 and high<1:high*=2
    if fun(0)*fun(high)>0:raise ValueError('Target not bracketed; no guaranteed reachability')
    q=brentq(fun,0,high,xtol=1e-13)
    if abs(volume(v+q*field,f)-target)>1e-9:raise ValueError('Actual D2 integral misses target')
    return q,coeff

def morphology_response(a,resolved):
    v,f=a['vertices'],a['faces'];fixed=a['port_fixed_masks'].any(0);graph,edges,length=mesh_graph(v,f)
    base={'junction_surface_support_mm':3.,'junction_axial_support_mm':5.,'wall_normal_mix':.35,'terminal_normal_mix':.8}
    candidate,mix,selected,details,support=topological_candidates(a,resolved,graph,base)
    paths=resolved['paths'];owners=a['path_owner'];normal=normalize(a['normals'].astype(float))
    with (N1/'sections.csv').open(encoding='utf-8-sig',newline='') as stream:stations=list(csv.DictReader(stream))
    station_rows={p['id']:[r for r in stations if r['path_id']==p['id'] and r['status']=='PATH_LOCAL_SECTION'] for p in paths}
    scale=np.zeros(len(v));confidence=np.zeros(len(v));thin=np.zeros(len(v));records=[];region=np.array([p['id'] for p in paths],dtype='<U32')[owners]
    region[fixed]='FIXED_ARTIFICIAL'
    for i,p in enumerate(paths):
        mask=owners==i
        if not mask.any() or p['id'] in ['BLADDER','IN_01','IN_02']:continue
        dist,center,tangent,arc,L=path_projection(v[mask],np.asarray(p['points_mm']))
        rows=station_rows[p['id']];rr=np.array([float(r['equivalent_radius_mm']) for r in rows]);ss=np.array([float(r['station_arc_mm']) for r in rows])
        if len(rows):
            order=np.argsort(ss);ss,rr=ss[order],rr[order]
            radius=np.interp(arc,ss,rr);halfminor=np.interp(arc,ss,np.array([float(r['minor_axis_mm']) for r in rows])[order]/2)
            nearest=np.min(np.abs(arc[:,None]-ss[None,:]),axis=1);conf=.45+.55*np.exp(-(nearest/3.)**2)
            # No trusted local cross section: local wall-distance fallback is conservative geometry, NOT net section area.
            far=nearest>4.;radius[far]=np.minimum(radius[far],np.maximum(dist[far],.2));halfminor[far]=np.minimum(halfminor[far],radius[far])
        else:
            radius=np.maximum(dist,.2);halfminor=radius.copy();conf=np.full(len(dist),.45)
        # Cap scale is local and bounded by own path wall geometry; no nearest unrelated branch mixing.
        radius=np.minimum(radius,np.maximum(1.,1.5*dist));scale[mask]=radius;thin[mask]=halfminor;confidence[mask]=conf
        if p['id'] in ['B_27','B_30']:
            unresolved_arc=9.689064331 if p['id']=='B_27' else 1.
            confidence[mask]*=1-.5*np.exp(-((arc-unresolved_arc)/2.)**2)
        # Unique response labels are accounting supports, not approved anatomical capacities.
        idx=np.flatnonzero(mask)
        for end,progress in [(p['marker_names'][0],arc),(p['marker_names'][-1],L-arc)]:
            if end.startswith('J_'):region[idx[progress<min(2.,.3*L)]]=end+'_SHARED'
            if end.startswith('T_'):region[idx[progress<min(2.,.3*L)]]=end+'_CAP'
        records.append({'path_id':p['id'],'trusted_station_ids':[r['id'] for r in rows],
          'radius_mm_quantiles':np.quantile(radius,[0,.5,1]),'confidence_quantiles':np.quantile(conf,[0,.5,1]),
          'fallback':'Own centerline-to-wall geometry where trusted same-path local stations absent/distant; never unresolved ring outer area'})
    # Independently chosen response laws for two directions, not negation/amplification of old fields.
    expand_scale=scale*confidence*(.55+.45*smoothstep((thin-.6)/3.))
    contract_scale=scale*confidence*(.25+.75*smoothstep((thin-.8)/3.5))
    fields={}
    for name,sign,amplitude,normal_mix in [('expand',1,expand_scale,.10),('contract',-1,contract_scale,.25)]:
        direction=(1-normal_mix)*candidate+normal_mix*normal
        target=direction*amplitude[:,None]
        solved=constrained_vector_smoothing(graph,target,fixed,~fixed,120.)
        solved-=np.minimum(np.einsum('ij,ij->i',solved,normal),0)[:,None]*normal
        field=sign*solved*a['weights'][:,None];field[fixed]=0
        fields[name]=field
    names=sorted(set(region));labels=np.array([names.index(x) for x in region],np.int32)
    np.save(OUT/'response_region_ids.npy',labels);np.save(OUT/'local_radius_mm.npy',scale);np.save(OUT/'local_confidence.npy',confidence)
    write(OUT/'response_design.json',{'label':LABEL,'status':'NON_PRODUCTION_PROTOTYPE',
      'algorithm':'Fresh topology-restricted centerline radial + wall-normal directions, N1 trusted local radii, independent thin-region suppression, shared surface solve and unchanged P1.2 mask',
      'smoothing_strength':120.,'expand_radial_gate':'.55+.45*smoothstep((minor_half-.6)/3)',
      'contract_radial_gate':'.25+.75*smoothstep((minor_half-.8)/3.5)',
      'response_constants_are_engineering_assumptions':True,'not_biological_compliance':True,
      'region_names':names,'paths':records,'topological_support':support,'candidate_details':details,
      'unresolved_sections_used_as_net_area':False,'old_displacement_used_as_driver':False,
      'fixed_vertices':int(fixed.sum()),'narrow_definition':'N1 geometric minor scale only; not clinical stenosis'})
    return fields,labels,names

def protect_thin_faces(a,fields):
    """One geometry-derived correction of the diagnosed sliver, not parameter searching.
    Penalize displacement residual at a thin triangle's opposite vertex relative
    to its long-edge interpolation. Measurement caps are NOT physical tissues.
    """
    v,f=a['vertices'],a['faces'];tri=v[f];_,area,qual=triangle_data(v,f)
    side=np.stack([np.linalg.norm(tri[:,1]-tri[:,2],axis=1),np.linalg.norm(tri[:,2]-tri[:,0],axis=1),np.linalg.norm(tri[:,0]-tri[:,1],axis=1)],1)
    opposite=np.argmax(side,1);alt=2*area/side.max(1);selected=(qual<.2)&(alt<.25)
    faces=f[selected];tris=tri[selected];k=opposite[selected];j=(k+1)%3;l=(k+2)%3;ii=np.arange(len(k))
    p0,p1,p2=tris[ii,k],tris[ii,j],tris[ii,l];axis=p2-p1;t=np.clip(np.einsum('ij,ij->i',p0-p1,axis)/np.einsum('ij,ij->i',axis,axis),0,1)
    cols=np.stack([faces[ii,k],faces[ii,j],faces[ii,l]],1)
    vals=np.stack([np.ones(len(k)),-(1-t),-t],1)
    A=sparse.coo_matrix((vals.ravel(),(np.repeat(np.arange(len(k)),3),cols.ravel())),shape=(len(k),len(v))).tocsr()
    weights=a['weights'];B=A@sparse.diags(weights);fixed=a['port_fixed_masks'].any(0);free=~fixed
    lam=.05/np.maximum(alt[selected],1e-6)**2
    Q=sparse.diags(weights**2+.001)+B.T@sparse.diags(lam)@B
    result={}
    for name,d in fields.items():
        h=np.zeros_like(d);h[free]=spsolve(Q[free][:,free].tocsc(),(weights[:,None]*d)[free])
        corrected=h*weights[:,None];corrected[fixed]=0;result[name]=corrected
    write(OUT/'thin_face_correction.json',{'attempt':'ONE_LOCAL_GEOMETRY_DERIVED_CORRECTION','physical_source_face_ids':np.flatnonzero(selected),
      'selected_faces':int(selected.sum()),'selection':'reference quality<0.2 and minimum altitude<0.25mm',
      'energy':'Weighted data term + .05 mm2 / altitude2 times long-edge interpolation displacement residual squared; D=approved_mask*H; fixed values eliminated',
      'original_OBJ_or_faces_changed':False,'new_mask_generated':False,'measurement_caps_used_as_material_constraints':False,
      'parameter_search_performed':False})
    return result

def provisional_tissue(a,tv,tf,resolved,fields):
    audit=PROJECT/'deformation/p15_audit';ids=np.load(audit/'tissue_to_cavity_face.npy');bary=np.load(audit/'mapping_barycentric.npy').astype(float)
    gap=np.load(audit/'tissue_to_cavity_distance_mm.npy');f=a['faces'];v=a['vertices']
    exact=np.load(PROJECT/'deformation/p2/evidence/coincident_mask.npy');exactids=np.load(PROJECT/'deformation/p2/evidence/coincident_cavity_vertex.npy')
    remote=np.load(PROJECT/'deformation/p2/evidence/remote_anchors.npy')
    cached=read(PROJECT/'deformation/capacity_v2_n0_research/contacts/u000000_source_float64.json')
    contact_faces=sorted({r['tissue_face'] for r in cached['pairs'] if r['class']=='COPLANAR_OVERLAP'})
    contact=np.zeros(len(tv),bool);contact[np.unique(tf[contact_faces])]=True
    normal=normalize(np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]]));tn=vertex_normals(tv,tf)
    point=np.einsum('ni,nij->nj',bary,v[f[ids]]);facing=np.einsum('ij,ij->i',tn,normal[ids])<-.5
    side=np.einsum('ij,ij->i',tv-point,normal[ids])>=-1e-5
    graph,edges,length=mesh_graph(tv,tf);near=(gap<=1)&facing&side
    geo=dijkstra(graph,indices=np.flatnonzero(near|exact|contact),min_only=True,limit=8.)
    fade=(1-smoothstep((gap-1)/11))*(1-smoothstep(geo/8));fade[~(facing&side)]=0
    # Reject cross-owner nonadjacent face donors; this does not establish anatomical ownership.
    own=a['path_owner'][f[ids]];adj=endpoint_adjacency(resolved['paths'])
    compatible=adj[own[:,0],own[:,1]]&adj[own[:,0],own[:,2]]&adj[own[:,1],own[:,2]]
    fade[~compatible]=0
    hard=remote|exact|contact;free=~hard
    # Edge metric penalizes relative motion at short edges, independent of old R2 field values.
    weights=np.where(near,1.,.25);weights[[61933,61934,30663]]=.1
    edge_weights=1./length+.05/length**2
    conductance=sparse.coo_matrix((np.r_[edge_weights,edge_weights],(np.r_[edges[:,0],edges[:,1]],np.r_[edges[:,1],edges[:,0]])),shape=graph.shape).tocsr()
    matrix=sparse.diags(weights)+5.*sparse.csgraph.laplacian(conductance).tocsr()
    result={}
    for name,field in fields.items():
        donor=np.einsum('ni,nij->nj',bary,field[f[ids]])
        target=donor*fade[:,None];values=np.zeros_like(tv);values[contact]=donor[contact];values[exact]=field[exactids[exact]]
        # Remote zero overrides no true coincident support; audit contradictions rather than silently resolving them.
        if (remote&exact).any():raise ValueError('Conflicting remote and exact constraints')
        values[remote]=0
        values[free]=spsolve(matrix[free][:,free].tocsc(),(weights[:,None]*target)[free]-matrix[free][:,hard]@values[hard])
        result[name]=values
    write(OUT/'tissue_prototype_design.json',{'status':'PREASSESSMENT_NOT_ACCEPTED_N3_MAPPING','exact_coincident_vertices':int(exact.sum()),
      'verified_reference_coplanar_contact_vertices':int(contact.sum()),'remote_fixed_vertices':int(remote.sum()),
      'normal_compatible_near_vertices':int(near.sum()),'incompatible_donor_triangles':int((~compatible).sum()),
      'support_mm':8.,'distance_decay_end_mm':12.,'local_metric_mm2':.05,'screened_strength':5.,
      'old_tissue_displacement_used':False,'constraints':'Exact shared coordinates hard; verified reference coplanar tissue faces provisional donor hard; C near-wall soft; D continuity; E remote zero',
      'limits':['Nearest surface barycentric mapping is a geometric starting hypothesis, not anatomy','F03/F04 remain unconfirmed','Reference contacts do not prove finite deformation contact preservation','No tissue wall-thickness claim']})
    np.save(OUT/'tissue_exact_mask.npy',exact);np.save(OUT/'tissue_remote_mask.npy',remote)
    return result

def continuous_area_bounds(v,f,d):
    tri=v[f];dd=d[f];e1=tri[:,1]-tri[:,0];e2=tri[:,2]-tri[:,0];h1=dd[:,1]-dd[:,0];h2=dd[:,2]-dd[:,0]
    c0=np.cross(e1,e2);c1=np.cross(h1,e2)+np.cross(e1,h2);c2=np.cross(h1,h2)
    dot=lambda a,b:np.einsum('ij,ij->i',a,b)
    den=dot(c0,c0);co=np.stack([den,2*dot(c0,c1),dot(c1,c1)+2*dot(c0,c2),2*dot(c1,c2),dot(c2,c2)],axis=1)/den[:,None]
    end=co.sum(1);lo=np.minimum(1.,end);hi=np.maximum(1.,end)
    derivative=co[:,1:]*np.arange(1,5)[None,:]
    p0,p1,p2,p3=derivative.T;bern=np.stack([p0,p0+p1/3,p0+2*p1/3+p2/3,p0+p1+p2+p3],1)
    ids=np.flatnonzero(~((bern>=0).all(1)|(bern<=0).all(1)))
    for i in ids:
        roots=np.roots(derivative[i,::-1])
        t=roots.real[(np.abs(roots.imag)<1e-9)&(roots.real>0)&(roots.real<1)]
        if len(t):
            y=np.polynomial.polynomial.polyval(t,co[i]);lo[i]=min(lo[i],y.min());hi[i]=max(hi[i],y.max())
    return {'minimum_area_ratio':float(np.sqrt(max(0,lo.min()))),'maximum_area_ratio':float(np.sqrt(max(0,hi.max()))),
      'minimum_face':int(np.argmin(lo)),'maximum_face':int(np.argmax(hi)),
      'method':'Exact quartic squared-area extrema; derivative Bernstein sign screen, then real cubic roots on [0,1]',
      'critical_candidate_faces':len(ids),'minimum_oriented_area_ratio':minimum_oriented_area_ratio(v,f,d)}

def quality(v,f,d,levels=LEVELS):
    _,edges,length=mesh_graph(v,f);c0,a0,_=triangle_data(v,f);gradient=np.linalg.norm(d[edges[:,0]]-d[edges[:,1]],axis=1)/length
    records=[]
    for u in levels:
        cross,area,q=triangle_data(v+u*d,f);ratios=area/a0;cos=np.einsum('ij,ij->i',cross,c0)/(4*area*a0)
        records.append({'u':u,'finite':bool(np.isfinite(v+u*d).all()),'minimum_area_ratio':float(ratios.min()),'maximum_area_ratio':float(ratios.max()),
          'area_fail_faces':int(((ratios<.8)|(ratios>1.35)).sum()),'degenerate_faces':int((area<1e-10).sum()),'reversed_faces':int((cos<=0).sum()),
          'maximum_normal_rotation_deg':float(np.degrees(np.arccos(np.clip(cos,-1,1))).max()),
          'maximum_edge_gradient':float(u*gradient.max()),'volume_mL':volume(v+u*d,f)})
    continuous=continuous_area_bounds(v,f,d)
    mag=np.linalg.norm(d,axis=1)
    passed=(gradient.max()<=.2 and continuous['minimum_area_ratio']>=.8 and continuous['maximum_area_ratio']<=1.35 and continuous['minimum_oriented_area_ratio']>0
      and not any(r['degenerate_faces'] or r['reversed_faces'] or not r['finite'] for r in records))
    return {'endpoint_displacement_mm':{'mean':float(mag.mean()),'median':float(np.median(mag)),'p95':float(np.quantile(mag,.95)),'maximum':float(mag.max())},
      'maximum_edge_gradient':float(gradient.max()),'worst_edge':edges[np.argmax(gradient)].tolist(),'gradient_fail_edges':int((gradient>.2).sum()),
      'five_levels':records,'continuous_area':continuous,'quality_gate_passed':bool(passed)}

def region_contributions(a,d2,d,labels,names):
    delta=map_d2(d,d2);f=d2['faces'];v=d2['reference_vertices'];contribution=np.zeros(len(names))
    for t,w in [(0,1/6),(.5,4/6),(1,1/6)]:
        tri=(v+t*delta-np.array([16.,16.,-81.]))[f];g=np.zeros_like(v)
        for i,j,k in [(0,1,2),(1,2,0),(2,0,1)]:np.add.at(g,f[:,i],np.cross(tri[:,j],tri[:,k])/6000)
        src=np.zeros_like(d)
        for k in range(3):
            valid=d2['source_vertex_ids'][:,k]>=0
            np.add.at(src,d2['source_vertex_ids'][valid,k],d2['source_vertex_weights'][valid,k,None]*g[valid])
        contribution+=w*np.bincount(labels,weights=np.einsum('ij,ij->i',src,d),minlength=len(names))
    actual=volume(v+delta,f)-volume(v,f)
    rows=[{'region':n,'delta_volume_mL':float(c),'fraction_of_signed_total':float(c/actual) if actual else 0,
      'vertices':int((labels==i).sum()),'max_displacement_mm':float(np.linalg.norm(d[labels==i],axis=1).max(initial=0))} for i,(n,c) in enumerate(zip(names,contribution))]
    return {'interpretation':'Nonoverlapping source-vertex response supports integrated along this trial trajectory, NOT baseline anatomical region capacities',
      'regions':rows,'sum_delta_mL':float(contribution.sum()),'D2_actual_delta_mL':actual,'residual_mL':float(contribution.sum()-actual)}

def build(corrected=False):
    protect(True);a,d2,tv,tf,resolved,approval=inputs();fixed=a['port_fixed_masks'].any(0)
    if fixed.sum()!=3675:raise ValueError('Fixed count changed')
    if np.linalg.norm(map_d2(a['vertices'],d2)[np.unique(d2['faces'])]-d2['reference_vertices'][np.unique(d2['faces'])],axis=1).max()>1e-9:raise ValueError('D2 barycentric reconstruction mismatch')
    write(OUT/'authorization.json',{'stage':'N1.6','date':'2026-10-15','label':LABEL,'authority':'User explicitly authorized S1/S2/S3 engineering exploration and isolated numerical prototypes',
      'physiological_parameters_remain_null':True,'N15M_conclusion_preserved':True,'production_N2_authorized':False,'preferred':'S2','fallback':'S1','stress_case':'S3'})
    write(OUT/'targets.json',{'V_reference_mL':approval['V_reference_D2_mL'],'candidates':{name:{'lower_ratio':r[0],'upper_ratio':r[1],
      'V_min_target_mL':r[0]*approval['V_reference_D2_mL'],'V_max_target_mL':r[1]*approval['V_reference_D2_mL']} for name,r in TARGETS.items()},
      'source':'Direct user-specified engineering exploration, NOT medical evidence'})
    fields,labels,names=morphology_response(a,resolved)
    if corrected:fields=protect_thin_faces(a,fields)
    print('Fresh cavity responses constructed; corrected',corrected,flush=True)
    tissue=provisional_tissue(a,tv,tf,resolved,fields);print('Fresh provisional tissue responses constructed',flush=True)
    attempt='thin_face_corrected' if corrected else 'initial'
    response_dir=OUT/'attempts'/attempt;response_dir.mkdir(parents=True,exist_ok=True)
    for name in fields:
        np.save(response_dir/f'research_{name}_cavity_unit_response.npy',fields[name]);np.save(response_dir/f'research_{name}_tissue_unit_response.npy',tissue[name])
    trials=[]
    for plan in ['S2','S1','S3']:
        for side,k in [('contract',0),('expand',1)]:
            target=TARGETS[plan][k]*approval['V_reference_D2_mL'];q,coeff=amplitude_for_target(d2['reference_vertices'],d2['faces'],map_d2(fields[side],d2),target)
            cv=fields[side]*q;tt=tissue[side]*q;trial=OUT/'prototypes'/attempt/f'{plan}_{side}';trial.mkdir(parents=True,exist_ok=True)
            np.save(trial/'research_cavity_offset.npy',cv);np.save(trial/'research_tissue_offset.npy',tt)
            cq=quality(a['vertices'],a['faces'],cv);tq=quality(tv,tf,tt);dq=quality(d2['reference_vertices'],d2['faces'],map_d2(cv,d2))
            contribution=region_contributions(a,d2,cv,labels,names)
            report={'id':f'{plan}_{side}','plan':plan,'direction':side,'status':'NUMERICAL_PREASSESSMENT_NOT_ACCEPTED_N2',
              'label':LABEL,'target_mL':target,'actual_D2_mL':volume(d2['reference_vertices']+map_d2(cv,d2),d2['faces']),
              'relative_capacity_change':target/approval['V_reference_D2_mL']-1,'response_amplitude':q,
              'volume_polynomial_mL':coeff.tolist(),'reference_sensitivity_mL_per_unit':float(coeff[1]),
              'cavity':cq,'tissue':tq,'D2_measurement_mesh':dq,'fixed_maximum_mm':float(np.linalg.norm(cv[fixed],axis=1).max()),
              'coincident_relative_motion_maximum_mm':float(np.linalg.norm(tt[np.load(OUT/'tissue_exact_mask.npy')]-cv[np.load(PROJECT/'deformation/p2/evidence/coincident_cavity_vertex.npy')[np.load(OUT/'tissue_exact_mask.npy')]],axis=1).max()),
              'remote_tissue_maximum_mm':float(np.linalg.norm(tt[np.load(OUT/'tissue_remote_mask.npy')],axis=1).max()),
              'capacity_contribution':contribution,'finite_intersections_status':'PENDING_SEPARATE_CONTACT_SCAN',
              'endoscope_clearance_status':'NOT_COMPUTED_NEEDS_SELECTED_STATE_PATH_AND_INSTRUMENT_ENVELOPE'}
            write(trial/'preassessment.json',report);trials.append(report)
            print(plan,side,'V',report['actual_D2_mL'],'max',cq['endpoint_displacement_mm']['maximum'],'cavity',cq['quality_gate_passed'],'tissue',tq['quality_gate_passed'],flush=True)
    write(response_dir/'preassessment.json',{'trials':trials,'all_trial_products_non_production':True})
    protect()

if __name__=='__main__':build('--corrected' in sys.argv)
