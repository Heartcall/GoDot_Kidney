"""Persistent coplanar pairs: exact affine embedding proves contact topology
invariant without forcibly separating legal contacts. Other sliding stays unknown."""
from n21_common import *
from fractions import Fraction as F

def coplanar_embedding(a0,a1,b0,b1):
    A=[[F(float(x)) for x in p] for p in a0];AA=[[F(float(x)) for x in p] for p in a1]
    B=[[F(float(x)) for x in p] for p in b0];BB=[[F(float(x)) for x in p] for p in b1]
    sub=lambda a,b:[x-y for x,y in zip(a,b)]
    e1,e2=sub(A[1],A[0]),sub(A[2],A[0]);n=[e1[1]*e2[2]-e1[2]*e2[1],e1[2]*e2[0]-e1[0]*e2[2],e1[0]*e2[1]-e1[1]*e2[0]]
    if not any(n):return {'class':'UNRESOLVED_DEGENERATE_REFERENCE'}
    drop=max(range(3),key=lambda i:abs(n[i]));axes=[i for i in range(3) if i!=drop];i,j=axes
    determinant=e1[i]*e2[j]-e1[j]*e2[i];weights=[]
    for p in B:
        r=sub(p,A[0]);u=(r[i]*e2[j]-r[j]*e2[i])/determinant;v=(e1[i]*r[j]-e1[j]*r[i])/determinant;weights.append([1-u-v,u,v])
    reference_exact=all(sum((w[k]*A[k][axis] for k in range(3)),F(0))==B[l][axis] for l,w in enumerate(weights) for axis in range(3))
    endpoint_exact=all(sum((w[k]*AA[k][axis] for k in range(3)),F(0))==BB[l][axis] for l,w in enumerate(weights) for axis in range(3))
    # Exact 2D finite polygon clipping at Reference, including zero-area touch.
    polygon=[[p[i],p[j]] for p in B];clip=[[p[i],p[j]] for p in A]
    cross=lambda a,b:a[0]*b[1]-a[1]*b[0];minus=lambda a,b:[x-y for x,y in zip(a,b)]
    sign=1 if determinant>0 else -1
    for k in range(3):
        start,end=clip[k],clip[(k+1)%3];edge=minus(end,start);old=polygon;polygon=[]
        for p,q in zip(old,old[1:]+old[:1]):
            dp=sign*cross(edge,minus(p,start));dq=sign*cross(edge,minus(q,start))
            if dp>=0:polygon.append(p)
            if dp*dq<0:
                t=dp/(dp-dq);polygon.append([p[c]+t*(q[c]-p[c]) for c in range(2)])
    area=abs(sum((cross(p,q) for p,q in zip(polygon,polygon[1:]+polygon[:1])),F(0)))/2 if len(polygon)>=3 else F(0)
    kind='POSITIVE_AREA_OVERLAP' if area>0 else ('POINT_OR_EDGE_CONTACT' if polygon else 'DISJOINT')
    return {'class':'CERTIFIED_COPLANAR_CONTACT_TOPOLOGY_INVARIANT' if reference_exact and endpoint_exact else 'UNRESOLVED_COPLANAR_SLIDING',
        'reference_relation':kind,'reference_projected_overlap_area_exact':str(area),
        'constant_barycentric_embedding':[[str(x) for x in w] for w in weights],
        'reference_exact':reference_exact,'endpoint_exact':endpoint_exact,
        'precondition':'Triangle A remains nondegenerate; guaranteed for these selected pairs by fresh CCD exact normal-polynomial guard.'}

def run():
    protect();a,d2,tv,tf,resolved,approval=inputs();all_results=[]
    for name in ['s1_n20_passed','s2_warm','robust_contract_r2']:
        if name=='s1_n20_passed':c=np.load(OLD/'regression_S1_expand/cavity_001.npy');t=np.load(OLD/'regression_S1_expand/tissue_001.npy')
        elif name=='s2_warm':c=np.load(ROOT/'warm_contact/S2_expand/cavity_offset.npy');t=np.load(ROOT/'warm_contact/S2_expand/tissue_offset.npy')
        else:c=np.load(ROOT/name/'cavity_offset.npy');t=np.load(ROOT/name/'tissue_offset.npy')
        endpoint=a['vertices']+c;tend=tv+t;certs=read(ROOT/'ccd'/(name+'_fresh')/'pair_certificates.json.gz')
        rows=[]
        for row in certs:
            if not row['permanent_coplanar']:continue
            ci,ti=row['cavity_face'],row['tissue_face'];r=coplanar_embedding(a['vertices'][a['faces'][ci]],endpoint[a['faces'][ci]],tv[tf[ti]],tend[tf[ti]])
            rows.append({'cavity_face':ci,'tissue_face':ti,**r})
        from collections import Counter
        result={'name':name,'pairs':rows,'class_counts':dict(Counter(x['class'] for x in rows)),
            'reference_relations':dict(Counter(x['reference_relation'] for x in rows)),'finite_positive_overlap_not_equal_to_permanent_plane_pair_count':True}
        write(ROOT/'coplanar'/f'{name}.json',result);all_results.append({k:v for k,v in result.items() if k!='pairs'})
        print('COPLANAR',name,result['class_counts'],result['reference_relations'],flush=True)
    write(ROOT/'coplanar/summary.json',all_results);protect()

if __name__=='__main__':run()
