"""Finite VF/EE support with source ids and barycentric/edge parameters.
No constraint is attached to a vertex outside the finite projected triangle.
"""
from n21_common import *
from trimesh.triangles import points_to_barycentric
from scipy.optimize import minimize

EDGES=[(0,1),(1,2),(2,0)]

def edge_closest(a,b,c,d):
    u=b-a;v=d-c;r=a-c;aa=u@u;bb=u@v;cc=v@v;dd=u@r;ee=v@r;den=aa*cc-bb*bb
    s=float(np.clip((bb*ee-cc*dd)/den,0,1)) if den>1e-28 else 0.
    t=float(np.clip((bb*s+ee)/cc,0,1));s=float(np.clip((bb*t-dd)/aa,0,1));t=float(np.clip((bb*s+ee)/cc,0,1))
    return s,t,a+s*u,c+t*v

def finite_features(cavity,tissue,cface,tface,ci,ti,reference_cavity=None,reference_tissue=None,activation=.01):
    A=cavity[cface];B=tissue[tface];A0=A if reference_cavity is None else reference_cavity[cface];B0=B if reference_tissue is None else reference_tissue[tface]
    nA=normalize(np.cross(A[1]-A[0],A[2]-A[0])[None])[0];nB=normalize(np.cross(B[1]-B[0],B[2]-B[0])[None])[0]
    nA0=normalize(np.cross(A0[1]-A0[0],A0[2]-A0[0])[None])[0];nB0=normalize(np.cross(B0[1]-B0[0],B0[2]-B0[0])[None])[0]
    result=[];rejected=[]
    for reverse in [False,True]:
        face,points,normal,normal0,face0,point0=(B,A,nB,nB0,B0,A0) if reverse else (A,B,nA,nA0,A0,B0)
        bary=points_to_barycentric(np.repeat(face[None],3,axis=0),points)
        for k,b in enumerate(bary):
            signed=float((points[k]-face[0])@normal);signed0=float((point0[k]-face0[0])@normal0)
            key=f'{ci}:{ti}:VF:{int(reverse)}:{k}'
            if b.min() < -1e-12 or b.max()>1+1e-12:
                rejected.append({'key':key,'reason':'OUTSIDE_FINITE_FACE','barycentric':b.tolist(),'signed_plane_gap_mm':signed});continue
            if abs(signed)>activation:continue
            b=np.clip(b,0,1);b/=b.sum()
            # Separation normal points cavity -> tissue. Preserve definite
            # reference-side orientation, not the already penetrated trial sign.
            sign=1 if signed0>=-1e-10 else -1
            n=(-normal*sign) if reverse else normal*sign
            cw=np.eye(3)[k] if reverse else b;tw=b if reverse else np.eye(3)[k]
            result.append({'key':key,'kind':'VF_CAVITY_VERTEX' if reverse else 'VF_TISSUE_VERTEX','pair':[int(ci),int(ti)],
                'cavity_vertices':cface.tolist(),'tissue_vertices':tface.tolist(),'cavity_weights':cw.tolist(),'tissue_weights':tw.tolist(),
                'normal':n.tolist(),'point_cavity_mm':(cw@A).tolist(),'point_tissue_mm':(tw@B).tolist(),
                'reference_normal_gap_mm':float(n@(tw@B0-cw@A0)),'current_normal_gap_mm':float(n@(tw@B-cw@A))})
    for i,(u,v) in enumerate(EDGES):
        for j,(k,l) in enumerate(EDGES):
            s,t,p,q=edge_closest(A[u],A[v],B[k],B[l]);gap=float(np.linalg.norm(q-p))
            if gap>activation:continue
            cw=np.zeros(3);tw=np.zeros(3);cw[u]=1-s;cw[v]=s;tw[k]=1-t;tw[l]=t
            original=tw@B0-cw@A0;n=normalize(np.cross(A[v]-A[u],B[l]-B[k])[None])[0]
            if np.linalg.norm(n)<.5:n=nA.copy()
            if abs(n@original)>1e-10:
                if n@original<0:n=-n
            elif n@nA<0:n=-n
            result.append({'key':f'{ci}:{ti}:EE:{i}:{j}','kind':'EE','pair':[int(ci),int(ti)],
                'cavity_vertices':cface.tolist(),'tissue_vertices':tface.tolist(),'cavity_weights':cw.tolist(),'tissue_weights':tw.tolist(),
                'normal':n.tolist(),'point_cavity_mm':p.tolist(),'point_tissue_mm':q.tolist(),
                'reference_normal_gap_mm':float(n@original),'current_normal_gap_mm':float(n@(q-p))})
    return result,rejected

class ContactState:
    """Deterministic full persistence: active AND inactive pairs/features,
    parameters, normals, duals, release counters and solver stage are serialized."""
    def __init__(self):self.pairs=set();self.features={};self.iteration=0;self.stage='START';self.trust_radius=.02;self.numerical={};self.outer_index=0
    def update(self,features):
        seen=set()
        for value in sorted(features,key=lambda f:f['key']):
            key=value['key'];seen.add(key);old=self.features.get(key,{})
            self.features[key]={**value,'active':value['current_normal_gap_mm']<=.01,'release_count':0,'dual':old.get('dual',0.),'last_iteration':self.iteration}
        for key in sorted(set(self.features)-seen):
            self.features[key]['release_count']+=1
            # Never delete a feature merely because it wasn't returned by one
            # query. Retain full history and mark it inactive explicitly.
            self.features[key]['active']=False
    def save(self,path,source_hashes,settings):
        path=Path(path);arrays={}
        for name,value in sorted(self.numerical.items()):
            target=path.with_name(path.stem+'_'+name+'.npy');temp=target.with_suffix('.npy.tmp')
            with temp.open('wb') as stream:np.save(stream,value)
            os.replace(temp,target);arrays[name]={'file':target.name,'sha256':sha(target)}
        temp=path.with_suffix('.json.tmp')
        write(temp,{'schema':'N21R_CONTACT_STATE_V2','pairs':sorted(self.pairs),'features':self.features,'iteration':self.iteration,
            'stage':self.stage,'outer_index':self.outer_index,'trust_radius':self.trust_radius,'source_hashes':source_hashes,'settings':settings,
            'numerical_arrays':arrays,'resume_semantics':'Restart complete saved outer transaction, including warm and linearization arrays; never resume partial KKT factorization'})
        os.replace(temp,path)
    @classmethod
    def load(cls,path,source_hashes,settings):
        r=read(path)
        if r['source_hashes']!=source_hashes or r['settings']!=settings:raise ValueError('Checkpoint inputs/settings mismatch')
        obj=cls();obj.pairs={tuple(p) for p in r['pairs']};obj.features=r['features'];obj.iteration=r['iteration'];obj.stage=r['stage'];obj.trust_radius=r['trust_radius'];obj.outer_index=r.get('outer_index',0)
        for name,row in r.get('numerical_arrays',{}).items():
            file=Path(path).parent/row['file']
            if sha(file)!=row['sha256']:raise ValueError('Corrupt numerical checkpoint')
            obj.numerical[name]=np.load(file)
        return obj

class FiniteTissue(TissueModel):
    def solve(self,cv,pairs=(),maximum_active_iterations=20):
        """Convex dual QP with projected bounds instead of bulk dropping all
        negative KKT multipliers. True inequality residual is never relaxed."""
        hard,rhs=self.target(cv);out=hard.copy();out[self.free]=self.factor.solve(rhs)
        if hasattr(self,'warm_cavity'):
            delta=cv-self.warm_cavity;hd,rd=self.target(delta);step=hd.copy();step[self.free]=self.factor.solve(rd)
            out=self.warm_tissue+step;out[self.exact]=cv[self.exactids[self.exact]];out[self.remote]=0
            rhs=self.Qf@out[self.free]
        C,b,keys,uncertain,conflicts=self.constraint_rows(cv,out,pairs)
        if not len(b):return out,{'qp_converged':not conflicts,'constraint_rows':0,'active_sources':[],'fixed_conflicts':conflicts}
        x0=out[self.free].T.ravel();n=len(self.ids);diagonal=np.tile(self.Qf.diagonal(),3)
        residual0=C@x0-b
        if residual0.min()>=-1e-10 and not conflicts:
            return out,{'qp_converged':True,'constraint_rows':len(b),'active_sources':[], 'fixed_conflicts':[],
                'minimum_inequality_residual_mm':float(residual0.min()),'unconstrained_minimizer_already_feasible':True}
        scale=np.sqrt(np.asarray(C.power(2)@(1/diagonal)).ravel());scale=np.maximum(scale,1e-12)
        A=sparse.diags(1/scale)@C;bb=b/scale;gradient0=bb-A@x0
        def inverse(z):
            return self.factor.solve(np.asarray(z).reshape(3,n).T).T.ravel()
        def fun(lam):
            correction=inverse(A.T@lam);h=A@correction
            return float(.5*lam@h-gradient0@lam),np.asarray(h-gradient0)
        result=minimize(fun,np.zeros(len(b)),jac=True,method='L-BFGS-B',bounds=[(0,None)]*len(b),
            options={'maxiter':1800,'gtol':1e-11,'ftol':1e-15,'maxls':40,'maxcor':25})
        x=x0+inverse(A.T@result.x);residual=C@x-b;active=np.flatnonzero(result.x>1e-9)
        # Exact sparse equality polish is only accepted if ALL inequalities and
        # dual signs pass. Otherwise retain the best convex-dual iterate as failed.
        if len(active):
            Q=sparse.block_diag([self.Qf]*3,format='csc');CC=C[active]
            K=sparse.bmat([[Q,-CC.T],[-CC,-1e-14*sparse.eye(len(active))]],format='csc')
            sol=spsolve(K,np.r_[rhs.T.ravel(),-b[active]])
            if np.isfinite(sol).all() and (C@sol[:len(x)]-b).min()>=-1e-10 and sol[len(x):].min()>=-1e-8:
                x=sol[:len(x)];residual=C@x-b
        trial=x.reshape(3,n).T;max_correction=float(np.linalg.norm(trial-out[self.free],axis=1).max())
        trust_rejected=max_correction>.05
        if not trust_rejected:out[self.free]=trial
        for k,lam in zip(keys,result.x):
            if hasattr(self,'state') and k['key'] in self.state.features:self.state.features[k['key']]['dual']=float(lam)
        return out,{'constraint_rows':len(b),'active_rows':len(active),'active_sources':[keys[i] for i in active],
            'fixed_conflicts':conflicts,'minimum_inequality_residual_mm':float(residual.min()),
            'qp_converged':bool(np.isfinite(x).all() and residual.min()>=-1e-10 and not conflicts and not trust_rejected),
            'correction_trust_radius_mm':.05,'unaccepted_proposal_correction_mm':max_correction,'trust_rejected':trust_rejected,
            'dual_optimizer_success':bool(result.success),'dual_iterations':int(result.nit),'dual_message':str(result.message)}
    def constraint_rows(self,cv,offset,pairs):
        cavity=self.a['vertices']+cv;tissue=self.v+getattr(self,'linearization_offset',offset);features=[];rejected=[]
        feature_cavity=self.a['vertices']+getattr(self,'warm_cavity',cv)
        feature_tissue=self.v+getattr(self,'warm_tissue',getattr(self,'linearization_offset',offset))
        for ci,ti in sorted(pairs):
            values,why=finite_features(feature_cavity,feature_tissue,self.a['faces'][ci],self.f[ti],ci,ti,
                feature_cavity if hasattr(self,'warm_cavity') else self.a['vertices'],feature_tissue if hasattr(self,'warm_cavity') else self.v)
            features.extend(values);rejected.extend(why)
        if hasattr(self,'state'):self.state.update(features)
        rows=[];cols=[];vals=[];rhs=[];keys=[];conflicts=[];identities=[]
        nfree=len(self.ids);seen=set()
        for value in features:
            n=np.array(value['normal']);cw=np.array(value['cavity_weights']);tw=np.array(value['tissue_weights']);ci,ti=value['pair']
            cvs=np.array(value['cavity_vertices']);tvs=np.array(value['tissue_vertices'])
            # Strict shared coordinates with the SAME finite source feature are
            # an exact kinematic identity, not a plane inequality to fight.
            material={}
            for vi,w in zip(tvs,tw):
                if w and self.exact[vi]:material[int(self.exactids[vi])]=material.get(int(self.exactids[vi]),0)+float(w)
            cdict={int(i):float(w) for i,w in zip(cvs,cw) if w}
            if all((not w or self.exact[i]) for i,w in zip(tvs,tw)) and material==cdict:
                identities.append(value['key']);continue
            b=float(n@(cw@cavity[cvs]-tw@self.v[tvs]));free_terms=[]
            for vi,w in zip(tvs,tw):
                if not w:continue
                if self.hard[vi]:b-=float(w*(n@offset[vi]))
                else:free_terms.append((int(vi),float(w)))
            if not free_terms:
                if b>1e-10:conflicts.append({'feature':value,'required_residual_mm':-b})
                continue
            dedup=tuple((i,round(w,12)) for i,w in free_terms)+tuple(np.round(n,12))+ (round(b,12),)
            if dedup in seen:continue
            seen.add(dedup);r=len(rhs)
            for vi,w in free_terms:
                for axis in range(3):rows.append(r);cols.append(int(self.index[vi])+axis*nfree);vals.append(w*n[axis])
            rhs.append(b);keys.append(value)
        self.last_features=features;self.last_rejected=rejected;self.last_identities=identities
        C=sparse.coo_matrix((vals,(rows,cols)),shape=(len(rhs),3*nfree)).tocsr()
        return C,np.array(rhs),keys,[],conflicts

    def solve_finite(self,cv,pairs=(),state=None,max_outer=6,warm_cavity=None,warm_tissue=None,checkpoint=None,checkpoint_settings=None,resume=False):
        if warm_cavity is not None:self.warm_cavity=warm_cavity.copy();self.warm_tissue=warm_tissue.copy()
        else:
            for name in ['warm_cavity','warm_tissue']:
                if hasattr(self,name):delattr(self,name)
        self.state=state or ContactState();self.state.pairs|=set(pairs);trace=[];best=None
        hard,rhs=self.target(cv);self.linearization_offset=hard.copy();self.linearization_offset[self.free]=self.factor.solve(rhs)
        start_outer=0
        source={'cavity_bytes':hashlib.sha256(cv.tobytes()).hexdigest(),'reference_cavity':hashlib.sha256(self.a['vertices'].tobytes()).hexdigest(),
            'reference_tissue':hashlib.sha256(self.v.tobytes()).hexdigest()}
        settings=checkpoint_settings or {'solver':'FINITE_TRANSACTION_V2','activation_mm':.01,'predicate_mm':1e-10,'max_outer':max_outer}
        if resume:
            if self.state.stage!='OUTER_BEGIN':raise ValueError('Only a complete outer transaction may be resumed')
            if not np.array_equal(self.state.numerical['cavity'],cv):raise ValueError('Checkpoint cavity differs')
            self.linearization_offset=self.state.numerical['linearization'].copy();start_outer=self.state.outer_index
            if 'warm_cavity' in self.state.numerical:self.warm_cavity=self.state.numerical['warm_cavity'].copy();self.warm_tissue=self.state.numerical['warm_tissue'].copy()
        for outer in range(start_outer,max_outer):
            self.state.stage='OUTER_BEGIN';self.state.outer_index=outer
            self.state.numerical={'cavity':cv.copy(),'linearization':self.linearization_offset.copy()}
            if hasattr(self,'warm_cavity'):self.state.numerical.update(warm_cavity=self.warm_cavity.copy(),warm_tissue=self.warm_tissue.copy())
            if checkpoint:self.state.save(checkpoint,source,settings)
            self.state.iteration+=1;self.state.stage='CONTACT_QP'
            # Parent QP now calls finite constraint_rows, never old halfspaces.
            t,qp=self.solve(cv,self.state.pairs,maximum_active_iterations=20)
            ct=scan_cross(self.a,self.v,self.f,cv,t);cross={(r['cavity_face'],r['tissue_face']) for r in ct['rows'] if r['class']=='FINITE_TRANSVERSE_CROSSING'}
            q=quick_quality(self.v,self.f,t,self.edges,self.length)
            trace.append({'outer':outer,'crossings':len(cross),'qp':qp,'quality':q,
                'finite_features':len(self.last_features),'outside_face_rejections':len(self.last_rejected),'shared_feature_identities':len(self.last_identities)})
            if best is None or len(cross)<best[0]:best=(len(cross),t.copy())
            print('FINITE CONTACT',outer,'cross',len(cross),'quality',q['pass'],'QP',qp['qp_converged'],flush=True)
            if not cross:break
            if qp.get('trust_rejected',False):break
            if cross<=self.state.pairs:break
            self.state.pairs|=cross
            self.linearization_offset=t.copy()
        self.state.stage='CANDIDATE_NOT_CERTIFIED'
        self.state.numerical['result_tissue']=t.copy()
        return t,{'trace':trace,'finite_crossings':ct,'static_candidate_pass':bool(not cross and q['pass'] and qp['qp_converged']),
            'continuous_safety_certified':False,'best_crossings':best[0],'outside_finite_face_diagnostics':self.last_rejected,
            'exact_feature_identities':self.last_identities}
