"""Complete static tissue self-crossing audit at EVERY predictor checkpoint.
Finite separating axes only accelerate broad candidates; final finite predicates
and tolerances remain unchanged. Also checks shared-one-vertex transverse pairs.
"""
from n20_model import *
from audit_tissue_cavity import classify_contacts

def finite_sat_filter(v,f,w,g,pairs):
    kept=[]
    for begin in range(0,len(pairs),8192):
        pp=pairs[begin:begin+8192];a=v[f[pp[:,0]]];b=w[g[pp[:,1]]]
        ea=a[:,[1,2,0]]-a;eb=b[:,[1,2,0]]-b
        na=np.cross(ea[:,0],-ea[:,2]);nb=np.cross(eb[:,0],-eb[:,2])
        axes=[na,nb]+[np.cross(ea[:,i],eb[:,j]) for i in range(3) for j in range(3)]
        # These extra fixed axes are valid for ANY triangles; particularly useful
        # for disjoint coplanar triangles with overlapping Cartesian boxes.
        axes.extend(np.cross(n,e[:,i]) for n,e in [(na,ea),(nb,eb)] for i in range(3))
        clear=np.zeros(len(pp),bool)
        for axis in axes:
            axis=normalize(axis);pa=np.einsum('nki,ni->nk',a,axis);pb=np.einsum('nki,ni->nk',b,axis)
            clear|=(pa.min(1)>pb.max(1)+1e-10)|(pb.min(1)>pa.max(1)+1e-10)
        kept.append(pp[~clear])
    return np.concatenate(kept) if kept else np.empty((0,2),np.int64)

def fast_classify(v,f,w,g,pairs):
    filtered=finite_sat_filter(v,f,w,g,pairs);r=classify(v,f,w,g,filtered)
    r['original_broad_candidates']=len(pairs);r['finite_separating_axis_disjoint']=len(pairs)-len(filtered)
    return r

def shared_one_pairs(f,n):
    I=sparse.coo_matrix((np.ones(f.size,np.int8),(np.repeat(np.arange(len(f)),3),f.ravel())),shape=(len(f),n)).tocsr()
    adjacent=(I@I.T).tocoo();mask=(adjacent.row<adjacent.col)&(adjacent.data==1)
    return np.column_stack([adjacent.row[mask],adjacent.col[mask]])

def run(side):
    protected();a,d2,tv,tf,resolved,approval=inputs();root=OUT/side;tr=read(root/'trajectory.json');shared=shared_one_pairs(tf,len(tv));rows=[]
    def compact(x):
        return {**x,'nonadjacent':{k:v for k,v in x['nonadjacent'].items() if k!='rows'},
            'shared_one_vertex_transverse':{k:v for k,v in x['shared_one_vertex_transverse'].items() if k!='rows'}}
    for k in range(1,len(tr['states'])+1):
        dest=root/f'stage_{k:03}_tissue_self.json.gz'
        if dest.exists():
            cached=read(dest)
            if cached['offset_sha256']!=sha(root/f'tissue_{k:03}.npy'):raise ValueError('Stale checkpoint self-scan')
            rows.append(compact(cached));continue
        t=np.load(root/f'tissue_{k:03}.npy');v=tv+t;start=time.time()
        r=fast_classify(v,tf,v,tf,self_bbox_pairs(v,tf))
        proper,_=classify_contacts(v,tf,v,tf,shared,tolerance=1e-10)
        adjacent=classify(v,tf,v,tf,shared[proper])
        report={'index':k,'offset_sha256':sha(root/f'tissue_{k:03}.npy'),'nonadjacent':r,'shared_one_vertex_transverse':adjacent,
            'seconds':time.time()-start,'continuous_collision_certified':False}
        gzip_write(dest,report);rows.append(compact(report))
        print('STAGE',side,k,'tissue self',r['confirmed_transverse_crossings'],'shared',adjacent['confirmed_transverse_crossings'],'seconds',round(time.time()-start,2),flush=True)
    write(root/'stage_audit.json',{'states':rows,'all_checkpoint_transverse_passed':all(not x['nonadjacent']['confirmed_transverse_crossings'] and not x['shared_one_vertex_transverse']['confirmed_transverse_crossings'] for x in rows),
        'no_continuous_collision_certificate':True,'shared_feature_coplanar_overlap_not_exhaustively_certified':True})
    protected()

if __name__=='__main__':run(sys.argv[1])
