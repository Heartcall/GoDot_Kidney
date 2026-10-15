"""N2.0 research only: fresh regional response and unilateral contact QP.

Imports from N1.6 below are PURE geometry/read functions, never its builders.
No accepted displacement array is used as a driver. Units mm, mm2, mL.
"""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key]='1'
import sys,json,time,hashlib,csv,gzip
from pathlib import Path
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import splu,spsolve
from scipy.sparse.csgraph import dijkstra
from n16_feasibility import (PROJECT,REPO,N1,inputs,read,write,sha,map_d2,volume,
    volume_coefficients,continuous_area_bounds,quality,region_contributions,
    path_projection,normalize,smoothstep,triangle_data,mesh_graph)
from build_full_cavity_deformation import topological_candidates,endpoint_adjacency
from build_cavity_morph_states import vertex_normals
from n16_contacts import classify,self_bbox_pairs
from audit_tissue_cavity import contact_pairs

OUT=PROJECT/'deformation/capacity_v2_n20_v1'
LABEL='MORPHOLOGY_GUIDED_UNCALIBRATED_CAPACITY_ESTIMATE'
GROUPS=['FIXED','Terminals','MainCavity','J_01','Branches','OtherJunctions','InterfaceTransition']

def protected(initialize=False):
    OUT.mkdir(parents=True,exist_ok=True);p=OUT/'protected_before.json'
    if initialize and not p.exists():
        files=set()
        for root in [REPO/'docs',PROJECT/'deformation',PROJECT/'analysis/irrigation_baseline',PROJECT/'tools',PROJECT/'scripts',PROJECT/'shaders',PROJECT/'source_assets']:
            files.update(x for x in root.rglob('*') if x.is_file() and OUT not in x.parents
                and not x.name.startswith(('n20_','test_n20','kidney_irrigation_capacity_v2_n20'))
                and not any(y in x.parts for y in ('__pycache__','.mplconfig','source_cache','matplotlib_cache')))
        files.update(PROJECT.glob('*.tscn'));files.update([PROJECT/'project.godot',REPO/'README.md',REPO/'.gitignore'])
        write(p,{x.relative_to(REPO).as_posix():sha(x) for x in sorted(files)})
    before=read(p);changed=[n for n,h in before.items() if not (REPO/n).is_file() or sha(REPO/n)!=h]
    write(OUT/'protected_after.json',{'checked_files':len(before),'changed':changed})
    if changed:raise ValueError('Protected files changed: '+str(changed))
    return len(before)

def thin_penalty(v,f):
    tri=v[f];_,area,qual=triangle_data(v,f)
    lengths=np.stack([np.linalg.norm(tri[:,1]-tri[:,2],axis=1),np.linalg.norm(tri[:,2]-tri[:,0],axis=1),np.linalg.norm(tri[:,0]-tri[:,1],axis=1)],1)
    alt=2*area/lengths.max(1);selected=(qual<.2)&(alt<.25);ff=f[selected];tt=tri[selected]
    k=np.argmax(lengths[selected],1);j=(k+1)%3;l=(k+2)%3;ii=np.arange(len(k))
    axis=tt[ii,l]-tt[ii,j];r=np.clip(np.einsum('ij,ij->i',tt[ii,k]-tt[ii,j],axis)/np.einsum('ij,ij->i',axis,axis),0,1)
    cols=np.stack([ff[ii,k],ff[ii,j],ff[ii,l]],1);values=np.stack([np.ones(len(k)),r-1,-r],1)
    B=sparse.coo_matrix((values.ravel(),(np.repeat(ii,3),cols.ravel())),shape=(len(k),len(v))).tocsr()
    return B.T@sparse.diags(.05/np.maximum(alt[selected],1e-6)**2)@B,np.flatnonzero(selected)

def regions(a,resolved):
    """Exclusive source supports; endpoint collars only along incident owner paths."""
    v=a['vertices'];owner=a['path_owner'];fixed=a['port_fixed_masks'].any(0)
    group=np.full(len(v),4,np.int32);detail=np.array([resolved['paths'][i]['id'] for i in owner],dtype='<U40')
    progress=np.zeros(len(v));collar=np.zeros(len(v));mapping=[]
    for i,p in enumerate(resolved['paths']):
        ix=np.flatnonzero(owner==i)
        if not len(ix):continue
        _,_,_,arc,L=path_projection(v[ix],np.array(p['points_mm']));progress[ix]=arc
        if p['id']=='MAIN':group[ix]=2
        if p['id'] in ('B_31','B_32','BLADDER_TRANSITION','BLADDER','IN_01','IN_02'):
            group[ix]=6
        else:
            proposals=[]
            for name,distance in [(p['marker_names'][0],arc),(p['marker_names'][-1],L-arc)]:
                if name.startswith(('J_','T_')):
                    width=min(2.,.30*L);proposals.append((name,distance,width))
            for name,distance,width in sorted(proposals,key=lambda x:x[0]):
                m=distance<width
                group[ix[m]]=1 if name.startswith('T_') else (3 if name=='J_01' else 5)
                detail[ix[m]]=name;collar[ix[m]]=width
        mapping.append({'path':p['id'],'source_owner_index':i,'marker_names':p['marker_names'],'collar_mm':min(2.,.3*L)})
    group[fixed]=0;detail[fixed]='FIXED'
    names=sorted(set(detail));local=np.array([names.index(x) for x in detail],np.int32)
    return group,local,names,{'groups':GROUPS,'local_names':names,'path_rules':mapping,
        'counts':{g:int((group==i).sum()) for i,g in enumerate(GROUPS)},
        'MainCavity_definition':'Only original MAIN owner, excluding J_01 and other endpoint collars. Not the union of major branches.',
        'exclusive':True,'J01_in_other_junctions':False,'interface_transition_not_primary':True,
        'anatomical_volume_partition':False,'source_face_membership':'region_ids[original_faces]; mixed faces remain mixed, never counted twice',
        'collar_basis':'Along approved incident path arclength; min(2 mm, 0.30 path length); no Euclidean nearest junction reassignment'}

class CavityModel:
    def __init__(self,a,resolved,d2=None,approval=None):
        self.a=a;self.v=a['vertices'];self.f=a['faces'];self.fixed=a['port_fixed_masks'].any(0)
        self.approved_fixed=self.fixed.copy();self.measurement_anchors=np.zeros(len(self.v),bool)
        if d2 is not None:
            boundary=np.concatenate([r['selected_boundary_vertex_ids'] for r in approval['virtual_caps']])
            source=d2['source_vertex_ids'][boundary];weights=d2['source_vertex_weights'][boundary]
            self.measurement_anchors[source[(source>=0)&(weights>0)]]=True
            # A RESEARCH interface collar condition, not a new P1.2 mask or a
            # different D2 cut. Holding its source stencil keeps the approved
            # non-star-shaped cap triangulation exactly stationary/continuous.
            self.fixed|=self.measurement_anchors
        self.graph,self.edges,self.length=mesh_graph(self.v,self.f)
        self.group,self.local,self.names,self.mapping=regions(a,resolved)
        config={'junction_surface_support_mm':3.,'junction_axial_support_mm':5.,'wall_normal_mix':.35,'terminal_normal_mix':.8}
        direction,_,_,_,self.support=topological_candidates(a,resolved,self.graph,config)
        self.normal=normalize(a['normals'].astype(float));self.direction=direction
        rows=list(csv.DictReader((N1/'sections.csv').open(encoding='utf-8-sig',newline='')))
        self.radius=np.zeros(len(self.v));self.minor=np.zeros(len(self.v));self.confidence=np.zeros(len(self.v));used=[]
        for i,p in enumerate(resolved['paths']):
            ix=np.flatnonzero(a['path_owner']==i)
            if not len(ix):continue
            dist,_,_,arc,_=path_projection(self.v[ix],np.array(p['points_mm']))
            rr=[r for r in rows if r['path_id']==p['id'] and r['status']=='PATH_LOCAL_SECTION']
            if rr:
                rr=sorted(rr,key=lambda r:float(r['station_arc_mm']));s=np.array([float(r['station_arc_mm']) for r in rr])
                near=np.min(abs(arc[:,None]-s),axis=1);conf=.4+.6*np.exp(-(near/3)**2)
                radius=np.interp(arc,s,[float(r['equivalent_radius_mm']) for r in rr]);minor=np.interp(arc,s,[float(r['minor_axis_mm'])/2 for r in rr])
                radius[near>4]=dist[near>4];used.extend(r['id'] for r in rr)
            else:radius=dist;minor=dist;conf=np.full(len(ix),.4)
            self.radius[ix]=np.minimum(np.maximum(radius,.2),np.maximum(1.,1.5*dist));self.minor[ix]=minor;self.confidence[ix]=conf
        self.station_ids=used
        conductance=self.graph.copy();conductance.data=1/conductance.data
        degree=np.asarray(conductance.sum(1)).ravel();self.degree=degree
        penalty,self.thin_faces=thin_penalty(self.v,self.f)
        # Solve H, then D = approved_mask * H. No different mask is generated.
        W=sparse.diags(a['weights']);self.Q=sparse.diags(degree)+35*sparse.csgraph.laplacian(conductance)+W@penalty@W
        self.free=~self.fixed;self.factor=splu(self.Q[self.free][:,self.free].tocsc())

    def response(self,side,mobility):
        if side=='expand':
            priority=np.array([0,1.,1.,1.,.22,.18,.10]);nblend=.12
            scale=self.radius*self.confidence*(.6+.4*smoothstep((self.minor-.5)/3))
        else:
            priority=np.array([0,.65,1.,.55,.3,.18,.08]);nblend=.3
            scale=self.radius*self.confidence*(.15+.85*smoothstep((self.minor-.8)/3.5))
        target=((1-nblend)*self.direction+nblend*self.normal)*scale[:,None]
        target*= (priority[self.group]*mobility[self.local])[:,None]
        h=np.zeros_like(target);h[self.free]=self.factor.solve((self.degree[:,None]*target)[self.free])
        result=h*self.a['weights'][:,None];result[self.fixed]=0
        return result if side=='expand' else -result

def volume_gradient_source(cv,d2):
    x=d2['reference_vertices']+map_d2(cv,d2);tri=(x-np.array([16,16,-81]))[d2['faces']];g=np.zeros_like(x)
    for i,j,k in [(0,1,2),(1,2,0),(2,0,1)]:np.add.at(g,d2['faces'][:,i],np.cross(tri[:,j],tri[:,k])/6000)
    result=np.zeros_like(cv)
    for k in range(3):
        ids=d2['source_vertex_ids'][:,k];valid=ids>=0
        np.add.at(result,ids[valid],d2['source_vertex_weights'][valid,k,None]*g[valid])
    return result

class TissueModel:
    """Screened shape objective; active finite-pair plane inequalities.

    Only strict coordinate coincidences are material equalities. Contact planes
    are one-sided geometric constraints, not a claim of anatomical homology.
    """
    def __init__(self,a,tv,tf,resolved):
        self.a=a;self.v=tv;self.f=tf
        root=PROJECT/'deformation/p15_audit'
        self.donor=np.load(root/'tissue_to_cavity_face.npy');self.bary=np.load(root/'mapping_barycentric.npy').astype(float)
        gap=np.load(root/'tissue_to_cavity_distance_mm.npy')
        root=PROJECT/'deformation/p2/evidence'
        self.exact=np.load(root/'coincident_mask.npy');self.exactids=np.load(root/'coincident_cavity_vertex.npy');self.remote=np.load(root/'remote_anchors.npy')
        self.hard=self.exact|self.remote;self.free=~self.hard;self.ids=np.flatnonzero(self.free);self.index=np.full(len(tv),-1);self.index[self.ids]=np.arange(len(self.ids))
        graph,self.edges,self.length=mesh_graph(tv,tf)
        normal=normalize(np.cross(a['vertices'][a['faces'][:,1]]-a['vertices'][a['faces'][:,0]],a['vertices'][a['faces'][:,2]]-a['vertices'][a['faces'][:,0]]))
        tn=vertex_normals(tv,tf);point=np.einsum('ni,nij->nj',self.bary,a['vertices'][a['faces'][self.donor]])
        facing=np.einsum('ij,ij->i',tn,normal[self.donor])<-.5
        side=np.einsum('ij,ij->i',tv-point,normal[self.donor])>=-1e-5
        near=(gap<=1)&facing&side
        geo=dijkstra(graph,indices=np.flatnonzero(near|self.exact),min_only=True,limit=8.)
        self.fade=(1-smoothstep((gap-1)/11))*(1-smoothstep(geo/8));self.fade[~(facing&side)]=0
        adj=endpoint_adjacency(resolved['paths']);owner=a['path_owner'][a['faces'][self.donor]]
        self.fade[~(adj[owner[:,0],owner[:,1]]&adj[owner[:,0],owner[:,2]]&adj[owner[:,1],owner[:,2]])]=0
        w=np.where(near,1.,.25);w[[61933,61934,30663]]=.1;self.w=w
        ew=1/self.length+.08/self.length**2
        G=sparse.coo_matrix((np.r_[ew,ew],(np.r_[self.edges[:,0],self.edges[:,1]],np.r_[self.edges[:,1],self.edges[:,0]])),shape=graph.shape).tocsr()
        penalty,self.thin_faces=thin_penalty(tv,tf)
        self.Q=(sparse.diags(w)+5*sparse.csgraph.laplacian(G)+penalty).tocsr();self.Qf=self.Q[self.free][:,self.free].tocsc()
        self.factor=splu(self.Qf);self.active_pairs=set()

    def target(self,cv):
        donor=np.einsum('ni,nij->nj',self.bary,cv[self.a['faces'][self.donor]])
        hard=np.zeros_like(self.v);hard[self.exact]=cv[self.exactids[self.exact]]
        rhs=(self.w[:,None]*donor*self.fade[:,None])[self.free]-self.Q[self.free][:,self.hard]@hard[self.hard]
        return hard,rhs

    def constraint_rows(self,cv,offset,pairs):
        """Conservative cavity face halfspace only when original tissue face
        lies wholly on a definite side. Finite detection chooses local pairs.
        Ambiguous original straddles are explicitly unresolved, never forced.
        """
        rows=[];cols=[];vals=[];b=[];keys=[];unresolved=[];fixed_conflicts=[]
        nfree=len(self.ids);seen={}
        for ci,ti in sorted(pairs):
            src=self.a['vertices'][self.a['faces'][ci]];dst=(self.a['vertices']+cv)[self.a['faces'][ci]]
            n0=normalize(np.cross(src[1]-src[0],src[2]-src[0])[None])[0]
            distances=(self.v[self.f[ti]]-src[0])@n0
            if distances.min()>=-1e-10:sign=1
            elif distances.max()<=1e-10:sign=-1
            else:unresolved.append([ci,ti]);continue
            n=sign*normalize(np.cross(dst[1]-dst[0],dst[2]-dst[0])[None])[0]
            for vi in self.f[ti]:
                rhs=float(n@(dst[0]-self.v[vi]));gap=float(n@offset[vi]-rhs)
                if self.hard[vi]:
                    if gap < -1e-10:fixed_conflicts.append([ci,ti,int(vi),gap])
                    continue
                # Identical directional constraints at same point are deduped;
                # keep the stricter plane, not the average of conflicting planes.
                key=(int(vi),*np.round(n,10));old=seen.get(key)
                if old is not None:
                    if rhs>b[old]:b[old]=rhs;keys[old]=[ci,ti,int(vi)]
                    continue
                row=len(b);seen[key]=row
                for axis in range(3):rows.append(row);cols.append(int(self.index[vi])+axis*nfree);vals.append(n[axis])
                b.append(rhs);keys.append([ci,ti,int(vi)])
        C=sparse.coo_matrix((vals,(rows,cols)),shape=(len(b),3*nfree)).tocsr()
        return C,np.array(b),keys,unresolved,fixed_conflicts

    def solve(self,cv,pairs=(),maximum_active_iterations=12):
        hard,rhs=self.target(cv);out=hard.copy();out[self.free]=self.factor.solve(rhs)
        C,b,keys,uncertain,conflicts=self.constraint_rows(cv,out,pairs)
        if not len(b):return out,{'constraint_rows':0,'unresolved_original_straddles':uncertain,'fixed_conflicts':conflicts,'qp_converged':not conflicts}
        x=out[self.free].T.ravel();active=list(np.flatnonzero(C@x < b-1e-11));Q=sparse.block_diag([self.Qf]*3,format='csc');r=rhs.T.ravel()
        history=[];converged=False
        for iteration in range(maximum_active_iterations):
            if not active:converged=True;break
            CC=C[active];K=sparse.bmat([[Q,-CC.T],[-CC,-1e-14*sparse.eye(len(active))]],format='csc')
            # Tiny diagonal only handles redundant constraints numerically; the
            # true inequality residual is checked below at the ORIGINAL tolerance.
            sol=spsolve(K,np.r_[r,-b[active]]);x=sol[:len(r)];lam=sol[len(r):]
            residual=C@x-b;bad=np.flatnonzero(residual < -1e-10);negative=np.flatnonzero(lam < -1e-9)
            history.append({'iteration':iteration,'active':len(active),'minimum_gap_mm':float(residual.min()),'negative_multipliers':len(negative)})
            if not np.isfinite(x).all():break
            if len(negative):active=[a for k,a in enumerate(active) if k not in set(negative)];continue
            new=sorted(set(active)|set(bad.tolist()))
            if not len(bad):converged=True;break
            if new==active:break
            active=new
        out[self.free]=x.reshape(3,-1).T
        return out,{'constraint_rows':len(b),'active_rows':len(active),'active_sources':[keys[i] for i in active],
            'unresolved_original_straddles':uncertain,'fixed_conflicts':conflicts,'qp_converged':bool(converged and not conflicts),
            'minimum_inequality_residual_mm':float((C@x-b).min()),'history':history,
            'contact_is_geometric_not_material':True}

def quick_quality(v,f,d,edges,length):
    c0,a0,_=triangle_data(v,f);cross,area,_=triangle_data(v+d,f);ratio=area/a0
    grad=np.linalg.norm(d[edges[:,0]]-d[edges[:,1]],axis=1)/length;orient=np.einsum('ij,ij->i',c0,cross)
    bad=np.flatnonzero((ratio<.8)|(ratio>1.35)|(area<1e-10)|(orient<=0));be=np.flatnonzero(grad>.2)
    return {'pass':bool(not len(bad) and not len(be) and np.isfinite(d).all()),'minimum_area_ratio':float(ratio.min()),
        'maximum_area_ratio':float(ratio.max()),'maximum_edge_gradient':float(grad.max()),'bad_faces':bad.tolist(),'bad_edges':edges[be].tolist(),
        'minimum_face':int(np.argmin(ratio)),'maximum_face':int(np.argmax(ratio))}

def scan_cross(a,tv,tf,cv,tt):
    return classify(a['vertices']+cv,a['faces'],tv+tt,tf,contact_pairs(a['vertices']+cv,a['faces'],tv+tt,tf))

def gzip_write(path,value):
    data=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8')
    Path(path).parent.mkdir(parents=True,exist_ok=True);Path(path).write_bytes(gzip.compress(data,mtime=0))

if __name__=='__main__':
    protected(True)
    a,d2,tv,tf,resolved,approval=inputs();m=CavityModel(a,resolved,d2,approval)
    for name,array in [('region_ids',m.group),('local_region_ids',m.local),('source_owner_ids',a['path_owner']),('source_faces',a['faces']),('local_radius_mm',m.radius)]:np.save(OUT/f'{name}.npy',array)
    np.save(OUT/'measurement_collar_source_anchors.npy',m.measurement_anchors)
    write(OUT/'support_mapping.json',{**m.mapping,'topological_candidate_audit':m.support,'trusted_station_ids':m.station_ids,
        'measurement_collar_source_anchors':int(m.measurement_anchors.sum()),'extra_anchor_vertices':int((m.measurement_anchors&~m.approved_fixed).sum()),
        'excluded_net_areas':['B_27:25','B_30:4'],'thin_source_faces':m.thin_faces.tolist()})
    ref=volume(d2['reference_vertices'],d2['faces'])
    write(OUT/'authorization_and_targets.json',{'stage':'N2.0','date':'2026-10-15','authority':'Explicit user authorization in current conversation',
        'label':LABEL,'domain':approval['domain_id'],'reference_mL':approval['V_reference_D2_mL'],
        'independently_recomputed_float64_reference_mL':ref,'contract_target_mL':11.764173461201125,'expand_target_mL':21.847750713659231,
        'user_target_decimal_strings':{'contract':'11.764173461201125','expand':'21.847750713659231'},
        'engineering_targets_not_physiological':True,'production_N2_authorized':False,'N16_A1_superseded_as_final_target':True,
        'N16_failure_evidence_preserved':True,'protected_source_hashes':approval['accepted_source_sha256'],'frozen_D2_hashes':approval['frozen_geometry_sha256'],
        'actual_physiological_parameters':{'V_min_mL':None,'V_max_mL':None,'pressure':None,'compliance':None,'real_flow_mL_s':None}})
    protected();print('N2.0 exclusive regions frozen',m.mapping['counts'],flush=True)
