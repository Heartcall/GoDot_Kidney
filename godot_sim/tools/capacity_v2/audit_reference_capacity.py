"""Read-only capacity audit for the NEW requirement, not a new deformation model.

No OBJ, mask, topology, field, runtime scene, or previous result is written.
Port closures are explicit in-memory accounting proxies; not anatomical cuts.
"""
import sys,math,hashlib,json,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'p2'))
from prepare_runtime import PROJECT,REPO,verify_sources,sha,read_json,write_json,ORIGIN,AUTHORITY
sys.path.insert(0,str(PROJECT/'tools'))
from localize_p15_conflicts import intersection_segment,coplanar_overlap_area,closest_features
import numpy as np
import trimesh

OUT=PROJECT/'deformation/capacity_v2_research'


def signed_volume(v,f,origin=None):
    x=np.asarray(v,dtype=np.float64)-(np.asarray(origin) if origin is not None else np.mean(v,axis=0))
    t=x[f]
    terms=np.einsum('ij,ij->i',t[:,0],np.cross(t[:,1],t[:,2]))/6
    return float(math.fsum(terms.tolist()))


def triangulate_ring(ring,projected):
    """Ear clip a simple projected polygon; avoid overlapping centroid fans."""
    cross=lambda a,b:float(a[0]*b[1]-a[1]*b[0])
    area2=sum(cross(p,q) for p,q in zip(projected,np.roll(projected,-1,axis=0)))
    if abs(area2)<=1e-12:raise ValueError('Zero-area projected boundary')
    def on_segment(a,b,p):
        return abs(cross(b-a,p-a))<=1e-12 and np.all(p>=np.minimum(a,b)-1e-12) and np.all(p<=np.maximum(a,b)+1e-12)
    def intersects(a,b,c,d):
        p,q,r,s=cross(b-a,c-a),cross(b-a,d-a),cross(d-c,a-c),cross(d-c,b-c)
        return (p*q<0 and r*s<0) or on_segment(a,b,c) or on_segment(a,b,d) or on_segment(c,d,a) or on_segment(c,d,b)
    for i in range(len(projected)):
        for j in range(i+1,len(projected)):
            if j==i+1 or (i==0 and j==len(projected)-1):continue
            if intersects(projected[i],projected[(i+1)%len(projected)],projected[j],projected[(j+1)%len(projected)]):
                raise ValueError('Projected boundary not simple')
    orientation=1. if area2>0 else -1.
    left=list(range(len(ring)));triangles=[]
    while len(left)>3:
        found=False
        for k in range(len(left)):
            a,b,c=left[k-1],left[k],left[(k+1)%len(left)]
            A,B,C=projected[[a,b,c]]
            if orientation*cross(B-A,C-B)<=1e-12:continue
            def inside(P):
                return min(orientation*cross(B-A,P-A),orientation*cross(C-B,P-B),orientation*cross(A-C,P-C))>=-1e-12
            if any(inside(projected[j]) for j in left if j not in (a,b,c)):continue
            triangles.append([ring[a],ring[c],ring[b]]) # Opposite boundary winding.
            left.pop(k);found=True;break
        if not found:raise ValueError('Cannot safely triangulate diagnostic boundary')
    triangles.append([ring[left[0]],ring[left[2]],ring[left[1]]])
    return np.asarray(triangles,int)


def closed_patch_proxy(v,f,selected):
    """Close the ALL-selected-vertex face patch, using reversed boundary fans.

    A diagnostic mathematical construction only. Retains source vertices/faces.
    No synthetic mesh is exported or substituted for the accepted Reference.
    """
    ids=np.flatnonzero(selected[f].all(axis=1));ff=f[ids]
    directed=np.concatenate([ff[:,[0,1]],ff[:,[1,2]],ff[:,[2,0]]])
    _,inverse,counts=np.unique(np.sort(directed,axis=1),axis=0,return_inverse=True,return_counts=True)
    boundary=directed[counts[inverse]==1]
    outgoing={int(a):int(b) for a,b in boundary}
    incoming={int(b):int(a) for a,b in boundary}
    if len(outgoing)!=len(boundary) or len(incoming)!=len(boundary):raise ValueError('Not a simple oriented boundary')
    start=int(boundary.min());ring=[start]
    while outgoing[ring[-1]]!=start:
        ring.append(outgoing[ring[-1]])
        if len(ring)>len(boundary):raise ValueError('Unclosed boundary')
    if len(ring)!=len(boundary):raise ValueError('More than one boundary loop: do not silently cap')
    center=np.mean(v[ring],axis=0)
    _,_,basis=np.linalg.svd(v[ring]-center,full_matrices=False)
    projected=(v[ring]-center)@basis[:2].T
    cross=projected[:,0]*np.roll(projected[:,1],-1)-projected[:,1]*np.roll(projected[:,0],-1)
    star=bool(np.all(cross>1e-12) or np.all(cross<-1e-12))
    # Test a nonoverlapping projected cap, but never conceal index conflicts with
    # the jagged source patch. A failure is evidence that a proper plane cut is needed.
    ear_status={}
    try:
        ear_cap=triangulate_ring(ring,projected)
        trial=trimesh.Trimesh(v,np.concatenate([ff,ear_cap]),process=False)
        ear_status={'projected_polygon_triangulated':True,'watertight':bool(trial.is_watertight),
                    'winding_consistent':bool(trial.is_winding_consistent),
                    'status':'TOPOLOGY_ONLY_PASSED_NOT_ANATOMICALLY_APPROVED' if trial.is_watertight and trial.is_winding_consistent else 'REJECTED_SOURCE_CAP_INDEX_CONFLICT',
                    'signed_algebraic_volume_mL':signed_volume(v,np.concatenate([ff,ear_cap]))/1000}
    except ValueError as error:
        ear_status={'status':'REJECTED_BOUNDARY_TRIANGULATION','reason':str(error)}
    # Retain the explicitly labelled fan SUM for sensitivity/accounting only.
    # When star=False this is not a certified nonoverlapping spatial cap.
    cap=np.column_stack([boundary[:,1],boundary[:,0],np.full(len(boundary),len(v),int)])
    derived_v=np.concatenate([v,center[None]])
    derived_f=np.concatenate([ff,cap])
    mesh=trimesh.Trimesh(derived_v,derived_f,process=False)
    volume=signed_volume(derived_v,derived_f)
    assert mesh.is_watertight and mesh.is_winding_consistent and volume>0
    assert abs(signed_volume(derived_v,derived_f,[0,0,0])-volume)<1e-7
    return {'faces_in_source':len(ids),'face_ids_sha256':hashlib.sha256(ids.astype('<i8').tobytes()).hexdigest(),
        'boundary_vertex_ids':ring,'boundary_center_mm':center.tolist(),'boundary_edges':len(boundary),
        'closure_triangles':cap.tolist(),'closure_method':'Explicit centroid fan algebraic accounting only; may overlap in projection and is NOT accepted for effective capacity.',
        'signed_proxy_volume_mm3':volume,'signed_proxy_volume_mL':volume/1000,
        'cap_planarity_max_residual_mm':float(np.abs((v[ring]-center)@basis[2]).max()),
        'centroid_fan_would_be_star_shaped':star,'projected_cap_nonoverlapping':star,'closed_winding_consistent':True,
        'alternative_ear_cap_test':ear_status,'effective_capacity_use_allowed':False,
        'interpretation':'Artificial distal fixed-wall accounting proxy only; not approved effective PCS capacity.'},ids,cap,center


def snapshot():
    OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'protected_before.json'
    if target.exists():return
    names=subprocess.check_output(['git','ls-files','-z'],cwd=REPO).decode('utf8').split('\0')
    paths={REPO/n for n in names if n and (REPO/n).is_file()}
    for name in ['deformation/p15_audit','analysis/irrigation_baseline/p15_r2','analysis/irrigation_baseline/p2','analysis/irrigation_baseline/p23']:
        base=PROJECT/name
        paths.update(p for p in base.rglob('*') if p.is_file() and p.suffix in ['.json','.npy','.bin','.csv','.md'])
    write_json(target,{p.relative_to(REPO).as_posix():sha(p) for p in sorted(paths)})


def audit():
    _,arrays=verify_sources()  # All six accepted hashes must still match.
    snapshot()
    v,f,d=[arrays['cavity_'+k] for k in ['reference_vertices','faces','displacement']]
    mesh=trimesh.Trimesh(v,f,process=False)
    center=v.mean(axis=0)
    origins=[np.zeros(3),center,ORIGIN,np.array([1000.,-1000.,500.])]
    volumes=[signed_volume(v,f,x) for x in origins]
    tri=(v-center)[f];normal2=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    independent_flux=[float(np.einsum('ij,i->',tri[:,:,axis],normal2[:,axis])/6) for axis in range(3)]
    edges=np.sort(mesh.edges,axis=1);_,counts=np.unique(edges,axis=0,return_counts=True)
    area=np.linalg.norm(normal2,axis=1)/2
    pair=intersection_segment(v[f[1856]],v[f[1862]])
    gap,_=closest_features(v[f[1856]],v[f[1862]])
    historical_review={'pair':[1856,1862],'finite_feature_distance_mm':gap,
        'positive_finite_segment_mm':0. if pair is None else float(np.linalg.norm(pair[1]-pair[0])),
        'coplanar_overlap_area_mm2':coplanar_overlap_area(v[f[1856]],v[f[1862]]),
        'tolerance_sensitivity':{str(e):intersection_segment(v[f[1856]],v[f[1862]],epsilon=e) is not None for e in [1e-12,1e-10,1e-8,1e-6]},
        'scope':'Targeted independent recheck of cached B_24 candidate only; not a new global self-intersection scan. Historical reports unchanged.'}
    fixed=np.load(PROJECT/'deformation/p1_masks/port_fixed_masks.npy')
    resolved=read_json(PROJECT/'deformation/cavity_topology_resolved.json')
    pathmap={p['id']:p for p in resolved['paths']}
    proxies=[];patchids=[];caps=[];capcenters=[]
    # Neighbors for one-ring boundary-definition sensitivity; no masks are saved/changed.
    unique_edges=np.unique(edges,axis=0)
    for name,mask in zip(['BLADDER','IN_01','IN_02'],fixed):
        record,ids,cap,c=closed_patch_proxy(v,f,mask)
        record['id']=name;record['fixed_vertices']=int(mask.sum())
        record['declared_path_length_mm']=pathmap[name]['length_mm']
        base,end=np.asarray(pathmap[name]['points_mm'])[[0,-1]]
        direction=(end-base)/np.linalg.norm(end-base)
        offsets=(v[record['boundary_vertex_ids']]-base)@direction
        record['boundary_axial_offset_from_BASE_mm']=[float(offsets.min()),float(offsets.max())]
        variants=[]
        for label in ['one_ring_eroded','original_fixed_mask','one_ring_dilated']:
            if label=='original_fixed_mask':variant=mask.copy()
            else:
                mixed=unique_edges[mask[unique_edges].sum(axis=1)==1]
                variant=mask.copy()
                if label=='one_ring_eroded':variant[mixed.ravel()]=False
                else:variant[mixed.ravel()]=True
            q,_,_,_=closed_patch_proxy(v,f,variant)
            variants.append({'boundary_definition':label,'proxy_mL':q['signed_proxy_volume_mL'],
                             'projected_cap_nonoverlapping':q['projected_cap_nonoverlapping']})
        record['boundary_sensitivity_not_physiological_uncertainty']=variants
        proxies.append(record);patchids.append(ids);caps.append(cap);capcenters.append(c)
    allpatch=np.concatenate(patchids)
    assert len(np.unique(allpatch))==len(allpatch)
    # Accounting complement uses exact opposite virtual caps, so additivity is testable.
    keep=np.ones(len(f),bool);keep[allpatch]=False
    complement_caps=[]
    for i,cap in enumerate(caps):
        cap=cap.copy();cap[cap==len(v)]=len(v)+i
        complement_caps.append(cap[:,::-1])
    compv=np.concatenate([v,np.asarray(capcenters)])
    compf=np.concatenate([f[keep],*complement_caps])
    complement=signed_volume(compv,compf)
    assert trimesh.Trimesh(compv,compf,process=False).is_watertight
    proxy_total=sum(p['signed_proxy_volume_mm3'] for p in proxies)
    assert abs(complement+proxy_total-volumes[0])<1e-7
    assert np.all(d[fixed.any(axis=0)]==0)
    oldlevels=[{'legacy_u':u,'closed_mesh_volume_mm3':signed_volume(v+u*d,f),
                'closed_mesh_volume_mL':signed_volume(v+u*d,f)/1000} for u in [0,.25,.5,.75,1]]
    # Multilinearity of the determinant: exact cubic, not a linear-volume assumption.
    A,B,C=tri[:,0],tri[:,1],tri[:,2];D,E,F=d[f[:,0]],d[f[:,1]],d[f[:,2]]
    det=lambda x,y,z:float(np.einsum('ij,ij->',x,np.cross(y,z))/6)
    coefficients=[det(A,B,C),det(D,B,C)+det(A,E,C)+det(A,B,F),det(D,E,C)+det(D,B,F)+det(A,E,F),det(D,E,F)]
    path=read_json(PROJECT/'data/organ_2_kidney/lab_6/cavity_path_stone1.json')
    points=np.asarray(path['points'])
    result={'scope':'Requirement impact analysis only. No Contracted or new Expanded field generated.',
        'user_provided_case':{'adult':True,'stone_obstruction_or_hydronephrosis':False,'CT_excretory_phase':'UNKNOWN','paired_images':False,'pressure_volume_data':False},
        'unit':'mm, mm^3; 1000 mm^3=1mL','coordinate_system':'Original cavity-local RAS, accepted unit convention; source DICOM spacing not independently revalidated.',
        'sources':{'six_authority_hashes':AUTHORITY,'cavity_obj_sha256':sha(PROJECT/'source_assets/kidney_cavity.obj'),
                   'fixed_masks_sha256':sha(PROJECT/'deformation/p1_masks/port_fixed_masks.npy'),'resolved_sha256':sha(PROJECT/'deformation/cavity_topology_resolved.json')},
        'reference_closed_mesh':{'vertices':len(v),'triangles':len(f),'signed_volume_mm3':volumes[0],
            'signed_volume_mL':volumes[0]/1000,'independent_trimesh_volume_mm3':float(mesh.volume),'three_axis_flux_volumes_mm3':independent_flux,
            'translated_origin_volumes_mm3':volumes,'numerical_spread_mm3':float(np.ptp(volumes+independent_flux+[float(mesh.volume)])),
            'watertight':bool(mesh.is_watertight),'winding_consistent':bool(mesh.is_winding_consistent),'boundary_edges':int((counts==1).sum()),
            'nonmanifold_edges':int((counts>2).sum()),'face_components':len(mesh.split(only_watertight=False)),
            'euler_number':int(mesh.euler_number),'degenerate_triangles':int((area<1e-10).sum()),'area_mm2':float(area.sum()),
            'bounds_mm':mesh.bounds.tolist(),'meaning':'Whole sealed computational mesh volume, including artificial ports; NOT an established physiological capacity.'},
        'historical_B24_targeted_review':historical_review,'artificial_distal_proxies':proxies,
        'artificial_distal_proxy_total_mL':proxy_total/1000,'complement_proxy_mL':complement/1000,
        'proxy_additivity_error_mm3':float(complement+proxy_total-volumes[0]),
        'proxy_limit':'Algebraic fan bookkeeping only, not certified spatial capacities. Non-star-shaped fans and alternative cap index conflicts are explicitly reported and prohibit effective-capacity use. Complement still includes B_31/B_32/BLADDER_TRANSITION. Proper anatomical plane cuts/closures require approval. No meshes or source masks exported/changed.',
        'legacy_debug_volume_levels':oldlevels,'legacy_debug_volume_polynomial_mm3':coefficients,
        'legacy_debug_expansion_mL':oldlevels[-1]['closed_mesh_volume_mL']-oldlevels[0]['closed_mesh_volume_mL'],
        'endoscope_inventory':{'path_points':len(points),'polyline_length_mm':float(np.linalg.norm(np.diff(points,axis=0),axis=1).sum()),
            'source': 'godot_sim/data/organ_2_kidney/lab_6/cavity_path_stone1.json','current_collision_sphere_radius_mm':2.0,
            'clearance_verified':False,'note':'Read-only inventory, no new path/pose/collision safety acceptance.'},
        'target_status':{'V_reference_mesh_mL':volumes[0]/1000,'V_reference_effective_mL':None,'V_min_physiological_mL':None,
                         'V_max_physiological_mL':None,'delta_contract_mL':None,'delta_expand_mL':None},
        'limits':['Numerical precision is not segmentation or clinical accuracy.','Cached B24 candidate was rechecked; no new exhaustive mesh scan.',
                  'No artificial-port anatomical cut has been approved. No normal individual capacity bounds can be inferred from reference volume alone.']}
    write_json(OUT/'reference_capacity_audit.json',result)
    before=read_json(OUT/'protected_before.json')
    changed=[name for name,digest in before.items() if not (REPO/name).is_file() or sha(REPO/name)!=digest]
    write_json(OUT/'protected_after.json',{'files':len(before),'changed':changed})
    assert not changed,changed
    print('Reference sealed volume mL:',result['reference_closed_mesh']['signed_volume_mL'])
    print('Distal port accounting proxies mL:',[(p['id'],p['signed_proxy_volume_mL']) for p in proxies])
    print('Complement proxy mL:',result['complement_proxy_mL'],'NOT physiological capacity')
    print('Protected files unchanged:',len(before))
    return result


if __name__=='__main__':audit()
