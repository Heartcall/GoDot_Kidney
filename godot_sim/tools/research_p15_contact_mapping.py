"""P1.5 contact-consistent RESEARCH. Never writes accepted deformation artifacts."""
from pathlib import Path
import argparse
import time
import numpy as np
from scipy import sparse
from scipy.sparse.csgraph import dijkstra,laplacian
from scipy.sparse.linalg import spsolve
from scipy.spatial import cKDTree
from audit_tissue_cavity import ROOT as AUDIT,contact_pairs,classify_contacts,summary
from localize_p15_conflicts import ROOT,pair_geometry,coplanar_overlap_area
from build_cavity_surface_masks import load_obj,mesh_graph
from build_cavity_morph_states import vertex_normals,minimum_oriented_area_ratio
from build_local_displacement import triangle_data,self_intersection_pairs,smoothstep,normalize
from resolve_cavity_topology import PROJECT,read_json,json_bytes,source_record


def inputs():
    audit=read_json(AUDIT/'audit_report.json')
    for name in ('cavity','tissue','approved_cavity_driver'):
        r=audit['sources'][name]
        if source_record(PROJECT/r['path'])['sha256']!=r['sha256']: raise ValueError('Immutable input changed: '+name)
    for name,digest in audit['output_sha256'].items():
        if source_record(AUDIT/name)['sha256']!=digest: raise ValueError('Cached audit changed: '+name)
    v,f=load_obj(PROJECT/'source_assets/kidney_cavity.obj');tv,tf=load_obj(PROJECT/'source_assets/kidney_tissue.obj')
    d=np.load(PROJECT/'deformation/full_cavity/field/displacement.npy')
    return v,f,tv,tf,d


def constrained_follow(graph,target,anchors,values,strength=5.):
    conductance=graph.copy();conductance.data=1/conductance.data
    degree=np.asarray(conductance.sum(axis=1)).ravel()
    matrix=sparse.diags(degree)+strength*laplacian(conductance).tocsr()
    free=~anchors;result=values.copy()
    result[free]=spsolve(matrix[free][:,free].tocsc(),(degree[:,None]*target)[free]-matrix[free][:,anchors]@values[anchors])
    return result


def build():
    ROOT.mkdir(parents=True,exist_ok=True)
    v,f,tv,tf,d=inputs();ids=np.load(AUDIT/'tissue_to_cavity_face.npy');bary=np.load(AUDIT/'mapping_barycentric.npy').astype(float)
    gap=np.load(AUDIT/'tissue_to_cavity_distance_mm.npy')
    q=np.einsum('ni,nij->nj',bary,v[f[ids]])
    donor=np.einsum('ni,nij->nj',bary,d[f[ids]])
    normals=normalize(np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]]))
    facing=np.einsum('ij,ij->i',vertex_normals(tv,tf),normals[ids])<-.5
    side=np.einsum('ij,ij->i',tv-q,normals[ids])>=-1e-5
    graph,edges,length=mesh_graph(tv,tf)
    contact=np.zeros(len(tv),bool);contact[np.unique(tf[np.load(AUDIT/'cross_contact_pairs.npy')[:,1]])]=True
    near=(gap<=1)&facing&side
    # Actual intersecting/contact triangles are local pair evidence, not an anatomical assumption.
    near|=contact
    ring=near.copy();ring[edges[near[edges].any(axis=1)].ravel()]=True
    geodesic=dijkstra(graph,indices=np.flatnonzero(near),min_only=True,limit=8.)
    remote=(gap>=12)|~np.isfinite(geodesic)
    target=donor*(1-smoothstep((gap-1)/11))[:,None]*(1-smoothstep(geodesic/8))[:,None]
    target[~(facing&side)]=0
    target[ring]=donor[ring]
    values=np.zeros_like(tv);values[ring]=donor[ring]
    # Equality only for 139 provably coincident source coordinates, not generic nearest vertices.
    exact_distance,exact_index=cKDTree(v).query(tv)
    coincident=exact_distance<1e-10
    values[coincident]=d[exact_index[coincident]]
    anchors=ring|remote|coincident
    field=constrained_follow(graph,target,anchors,values)
    if not np.isfinite(field).all() or np.linalg.norm(field,axis=1).max()>.2+1e-10: raise ValueError('Invalid research field')
    data={'UNACCEPTED_contact_tissue_displacement':field,'tissue_reference':tv,'tissue_faces':tf,'contact_anchors':ring,
          'remote_anchors':remote,'coincident_mask':coincident,'coincident_cavity_vertex':exact_index,'geodesic_support_mm':geodesic}
    for name,array in data.items(): np.save(ROOT/(name+'.npy'),array)
    report={'status':'RESEARCH_ONLY_NOT_ACCEPTED','sources':read_json(AUDIT/'audit_report.json')['sources'],
      'method':'Barycentric approved surface driver; pair-supported contact patch and normal-facing <=1mm inner-near vertices plus one ring as nonzero Dirichlet constraints. Exact equality only at identical source coordinates. Screened surface Laplacian outside anchors; intrinsic support <=8mm and Euclidean distance >=12mm fixed. No anatomical inner/outer claim.',
      'parameters':{'inner_anchor_gap_mm':1,'intrinsic_support_mm':8,'remote_gap_mm':12,'smoothing_strength':5,'coincidence_epsilon_mm':1e-10},
      'counts':{'contact_vertices':int(contact.sum()),'near_vertices':int(near.sum()),'one_ring_anchors':int(ring.sum()),'remote_anchors':int(remote.sum()),'coincident_vertices':int(coincident.sum()),'free_solve_vertices':int((~anchors).sum()),'moving_vertices':int((np.linalg.norm(field,axis=1)>1e-12).sum())},
      'displacement_mm':summary(np.linalg.norm(field,axis=1)),
      'exact_contact_relative_displacement_max_mm':float(np.linalg.norm(field[coincident]-d[exact_index[coincident]],axis=1).max()),
      'remote_maximum_mm':float(np.linalg.norm(field[remote],axis=1).max()),
      'continuous_minimum_oriented_area_ratio':minimum_oriented_area_ratio(tv,tf,field),
      'output_sha256':{name+'.npy':source_record(ROOT/(name+'.npy'))['sha256'] for name in data}}
    (ROOT/'mapping_build_report.json').write_bytes(json_bytes(report));print(report,flush=True)


def verify_pairs(a,fa,b,fb,pairs):
    if not len(pairs): return {'raw_candidate_count':0,'proper_pairs':[],'positive_segment_count':0,'coplanar_overlap_pair_count':0,'coplanar_pair_area_sum_mm2':0.,'maximum_segment_mm':0.,'segment_sum_mm':0.}
    proper,co=classify_contacts(a,fa,b,fb,pairs,tolerance=1e-10)
    candidates=pairs[proper]
    geometry=pair_geometry(a,fa,b,fb,candidates) if len(candidates) else None
    positive=candidates[geometry['verified']] if geometry is not None else np.empty((0,2),int)
    areas=np.array([coplanar_overlap_area(a[fa[i]],b[fb[j]]) for i,j in pairs[co]])
    return {'raw_candidate_count':len(pairs),'old_plane_straddle_count':int(proper.sum()),'proper_pairs':positive.tolist(),
       'positive_segment_count':len(positive),'coplanar_overlap_pair_count':int((areas>1e-12).sum()),
       'coplanar_pair_area_sum_mm2':float(areas.sum()),'maximum_segment_mm':float(geometry['length'].max()) if geometry is not None and len(candidates) else 0.,
       'segment_sum_mm':float(geometry['length'].sum()) if geometry is not None else 0.,
       'proper_centers_mm':geometry['centers'][geometry['verified']].tolist() if geometry is not None else []}


def check(fill,self_scan=False):
    start=time.time();v,f,tv,tf,d=inputs();field=np.load(ROOT/'UNACCEPTED_contact_tissue_displacement.npy')
    cv=v+fill*d;tt=tv+fill*field
    print('Checking',fill,'self' if self_scan else 'cross+quality',flush=True)
    if self_scan:
        pairs=np.load(AUDIT/'tissue_self_intersections.npy') if fill==0 else self_intersection_pairs(tt,tf)
        np.save(ROOT/f'tissue_self_pairs_u{int(fill*100):03}.npy',pairs)
        result=verify_pairs(tt,tf,tt,tf,pairs)
    else:
        pairs=np.load(AUDIT/'cross_contact_pairs.npy') if fill==0 else contact_pairs(cv,f,tt,tf)
        np.save(ROOT/f'cross_pairs_u{int(fill*100):03}.npy',pairs)
        result=verify_pairs(cv,f,tt,tf,pairs)
        c0,a0,_=triangle_data(tv,tf);cross,area,quality=triangle_data(tt,tf)
        cos=np.einsum('ij,ij->i',c0,cross)/(4*a0*area)
        normals=vertex_normals(tt,tf);normal_lengths=np.linalg.norm(normals,axis=1)
        _,edges,lengths=mesh_graph(tv,tf)
        difference=np.linalg.norm(fill*(field[edges[:,0]]-field[edges[:,1]]),axis=1)
        result['tissue_quality']={'finite':bool(np.isfinite(tt).all() and np.isfinite(normals).all()),'degenerate_count':int((area<1e-10).sum()),
          'normal_reversal_count':int((cos<=0).sum()),'area_ratio_range':[float((area/a0).min()),float((area/a0).max())],
          'normal_length_range':[float(normal_lengths.min()),float(normal_lengths.max())],
          'maximum_face_normal_rotation_deg':float(np.degrees(np.arccos(np.clip(cos,-1,1))).max()),
          'minimum_triangle_area_mm2':float(area.min()),'same_source_faces_and_vertex_order':True,
          'minimum_triangle_quality':float(quality.min()),'maximum_neighbor_difference_mm':float(difference.max()),
          'maximum_edge_gradient':float((difference/lengths).max()),'bounds_change_mm':(np.stack([tt.min(axis=0),tt.max(axis=0)])-np.stack([tv.min(axis=0),tv.max(axis=0)])).tolist(),
          'signed_volume_mm3':float(np.einsum('ij,ij->i',tt[tf[:,0]],np.cross(tt[tf[:,1]],tt[tf[:,2]])).sum()/6)}
    result.update({'fill':fill,'elapsed_seconds':time.time()-start,'field_sha256':source_record(ROOT/'UNACCEPTED_contact_tissue_displacement.npy')['sha256']})
    suffix='self' if self_scan else 'cross'
    (ROOT/f'{suffix}_check_u{int(fill*100):03}.json').write_bytes(json_bytes(result))
    print(suffix,fill,{k:val for k,val in result.items() if k not in ('proper_pairs','proper_centers_mm')},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',action='store_true');p.add_argument('--fill',type=float);p.add_argument('--self-scan',action='store_true');args=p.parse_args()
    if args.build: build()
    if args.fill is not None:
        if args.fill not in (0,.25,.5,.75,1): raise ValueError('Only the five review levels')
        check(args.fill,args.self_scan)
