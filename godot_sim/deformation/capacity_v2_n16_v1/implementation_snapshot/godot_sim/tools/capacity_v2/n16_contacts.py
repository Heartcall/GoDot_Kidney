"""Finite-triangle N1.6 research scans, unchanged 1e-10 mm predicates.
Broad-phase and plane straddling are candidates, never confirmed crossings.
"""
from n16_feasibility import *
from audit_tissue_cavity import contact_pairs,classify_contacts,polydata
from diagnose_n0_contacts import classify_pair
from collections import Counter
import vtk

def self_bbox_pairs(v,f):
    """Exhaustive closed AABB queries in VTK's static cell locator.
    Shared-vertex face pairs excluded, matching the existing self-scan policy.
    Final acceptance still uses independent finite geometry, not AABBs.
    """
    poly=polydata(v,f);locator=vtk.vtkStaticCellLocator();locator.SetDataSet(poly);locator.BuildLocator()
    tri=v[f];lo=tri.min(1);hi=tri.max(1);ids=vtk.vtkIdList();pairs=[]
    for i in range(len(f)):
        bounds=(lo[i,0],hi[i,0],lo[i,1],hi[i,1],lo[i,2],hi[i,2]);locator.FindCellsWithinBounds(bounds,ids)
        pairs.extend((i,int(ids.GetId(k))) for k in range(ids.GetNumberOfIds()) if ids.GetId(k)>i)
    pairs=np.asarray(pairs,np.int64).reshape(-1,2)
    if not len(pairs):return pairs
    i,j=pairs.T;keep=(lo[i]<=hi[j]).all(1)&(lo[j]<=hi[i]).all(1)
    for x in range(3):
        for y in range(3):keep&=f[i,x]!=f[j,y]
    return pairs[keep]

def classify(v,f,w,g,pairs):
    pairs=np.unique(np.asarray(pairs,dtype=np.int64).reshape(-1,2),axis=0)
    if not len(pairs):return {'broad_candidates':0,'confirmed_transverse_crossings':0,'coplanar_overlap_pairs':0,'coplanar_pair_area_sum_mm2':0.,'rows':[]}
    proper,coplanar=classify_contacts(v,f,w,g,pairs,tolerance=1e-10)
    rows=[]
    # A transverse crossing must strictly straddle both finite face planes.
    # All such candidates undergo the independent finite-segment + support test.
    # Coplanar candidates undergo finite polygon overlap, not plane coincidence only.
    for i,j in pairs[proper|coplanar]:
        row=classify_pair(v,f,w,g,int(i),int(j),0,True,{},input_origin=np.zeros(3))
        rows.append({k:row[k] for k in ['cavity_face','tissue_face','class','center_mm','finite_segment_length_mm','coplanar_pair_overlap_area_mm2','segment_support_residual_mm']})
    confirmed=[r for r in rows if r['class']=='FINITE_TRANSVERSE_CROSSING']
    co=[r for r in rows if r['class']=='COPLANAR_OVERLAP']
    return {'broad_candidates':len(pairs),'two_plane_straddle_candidates':int(proper.sum()),
      'confirmed_transverse_crossings':len(confirmed),'coplanar_overlap_pairs':len(co),
      'coplanar_pair_area_sum_mm2':sum(r['coplanar_pair_overlap_area_mm2'] for r in co),
      'maximum_confirmed_segment_length_mm':max([r['finite_segment_length_mm'] for r in confirmed],default=0.),
      'strict_nontransverse_other_candidates':int((~(proper|coplanar)).sum()),
      'other_candidates_note':'Not labelled true contact by this accelerated scan; point/edge/tangency candidates remain distinct from transverse crossings',
      'rows':rows,'class_counts_verified_subset':dict(Counter(r['class'] for r in rows)),
      'segment_length_is_not_penetration_depth':True}

def compare(result,baseline):
    key=lambda r:(r['cavity_face'],r['tissue_face'])
    old={key(r):r for r in baseline['rows'] if r['class']=='FINITE_TRANSVERSE_CROSSING'}
    now={key(r):r for r in result['rows'] if r['class']=='FINITE_TRANSVERSE_CROSSING'}
    result['new_confirmed_crossing_pairs']=[list(x) for x in sorted(set(now)-set(old))]
    result['baseline_confirmed_pairs_still_present']=[list(x) for x in sorted(set(now)&set(old))]
    result['baseline_pair_spatial_changes']=[{'pair':list(x),'center_shift_mm':float(np.linalg.norm(np.array(now[x]['center_mm'])-old[x]['center_mm'])),
      'segment_change_mm':now[x]['finite_segment_length_mm']-old[x]['finite_segment_length_mm']} for x in sorted(set(now)&set(old))]
    result['baseline_missing_pairs']=[list(x) for x in sorted(set(old)-set(now))]
    return result

def scan_one(v,f,tv,tf,dv,df,baseline=None,tissue_self=True,reference=False):
    results={}
    for name,x,faces,y,other in [('cavity_self',v,f,v,f),('tissue_self',tv,tf,tv,tf),('D2_self',dv,df,dv,df),('cavity_tissue',v,f,tv,tf)]:
        if name=='tissue_self' and not tissue_self:
            results[name]={'status':'NOT_SCANNED_AT_THIS_INTERMEDIATE_LEVEL','reason':'N1.6 preassessment; endpoints scanned, full intermediate/continuous self-collision belongs to N2/N3 verification'};continue
        start=time.time()
        if reference and name=='cavity_self':pairs=np.load(PROJECT/'deformation/p13_static/reference_self_intersection_pairs.npy')
        elif reference and name=='tissue_self':pairs=np.load(PROJECT/'deformation/p15_audit/tissue_self_intersections.npy')
        elif reference and name=='cavity_tissue':pairs=np.load(PROJECT/'deformation/capacity_v2_n0_research/contacts/u000000_source_float64_pairs.npy')
        else:pairs=self_bbox_pairs(x,faces) if name.endswith('self') else contact_pairs(x,faces,y,other)
        r=classify(x,faces,y,other,pairs)
        if baseline is not None:r=compare(r,baseline[name])
        results[name]=r;print(name,'raw',r['broad_candidates'],'confirmed',r['confirmed_transverse_crossings'],'seconds',round(time.time()-start,2),flush=True)
    return results

def run(selected=None):
    protect();a,d2,tv,tf,resolved,approval=inputs();basepath=OUT/'contact_baseline.json'
    if basepath.exists():baseline=read(basepath)['results']
    else:
        results=scan_one(a['vertices'],a['faces'],tv,tf,d2['reference_vertices'],d2['faces'],reference=True)
        baseline=results;write(basepath,{'status':'SOURCE_FLOAT64_REFERENCE_BASELINE','finite_tolerance_mm':1e-10,'results':results,
          'limits':'Existing confirmed defects are recorded; contact is not automatically physiologically acceptable.'})
    ids=selected or [f'{p}_{s}' for p in ['S2','S1','S3'] for s in ['contract','expand']]
    for name in ids:
        directory=OUT/'prototypes/thin_face_corrected'/name
        cv=np.load(directory/'research_cavity_offset.npy');tt=np.load(directory/'research_tissue_offset.npy')
        output=directory/'contacts';output.mkdir(exist_ok=True)
        for u in [.25,.5,.75,1.]:
            path=output/f'u{round(u*100):03}.json'
            if path.exists() or path.with_suffix('.json.gz').exists():
                cached=read(path)['sources']
                if cached['cavity_offset_sha256']!=sha(directory/'research_cavity_offset.npy') or cached['tissue_offset_sha256']!=sha(directory/'research_tissue_offset.npy'):
                    raise ValueError('Stale contact cache; preserve evidence and build a new version rather than silently reusing it')
                print('Cached verified',name,u,flush=True);continue
            print('SCANNING',name,u,flush=True)
            r=scan_one(a['vertices']+u*cv,a['faces'],tv+u*tt,tf,d2['reference_vertices']+u*map_d2(cv,d2),d2['faces'],baseline,tissue_self=(u==1))
            write(path,{'trial':name,'u':u,'status':'OFFLINE_FLOAT64_TEMPORARY_PROTOTYPE','results':r,
              'sources':{'cavity_offset_sha256':sha(directory/'research_cavity_offset.npy'),'tissue_offset_sha256':sha(directory/'research_tissue_offset.npy')},
              'finite_tolerance_mm':1e-10,'continuous_collision_certificate':False})
        protect()

if __name__=='__main__':run(sys.argv[1:] or None)
