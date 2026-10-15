"""Measurement-closure sensitivity and local risk metrics; frozen D2 untouched."""
from n16_feasibility import *
from audit_reference_capacity import triangulate_ring
from audit_tissue_cavity import contact_pairs,ray_scene
from n16_contacts import classify
import trimesh,open3d as o3d

def oriented_rings(d2,approval):
    wall=d2['faces'][d2['source_face_ids']>=0]
    ed=np.concatenate([wall[:,[0,1]],wall[:,[1,2]],wall[:,[2,0]]]);_,iv,ct=np.unique(np.sort(ed,1),axis=0,return_inverse=True,return_counts=True)
    ed=ed[ct[iv]==1];out={int(x):int(y) for x,y in ed};rings=[]
    for cut in approval['virtual_caps']:
        start=min(cut['selected_boundary_vertex_ids']);r=[start]
        while out[r[-1]]!=start:
            r.append(out[r[-1]])
            if len(r)>len(ed):raise ValueError('Open measurement boundary')
        if set(r)!=set(cut['selected_boundary_vertex_ids']):raise ValueError('Boundary changed')
        rings.append((cut['port'],np.array(r),np.array(cut['normal_toward_artificial_END'])))
    return rings,wall

def closure_variants(v,d2,approval):
    rings,wall=oriented_rings(d2,approval);variants=[]
    for variant in [0,1,2]:
        caps=[];records=[]
        for port,ring,normal in rings:
            r=np.roll(ring,-(len(ring)*variant//3));xyz=v[r];center=xyz.mean(0)
            _,_,basis=np.linalg.svd(xyz-center,full_matrices=False)
            projected=(xyz-center)@basis[:2].T
            ff=triangulate_ring(r.tolist(),projected);caps.append(ff)
            records.append({'port':port,'ring_D2_vertex_ids':r.tolist(),'cap_faces_D2_vertex_ids':ff.tolist(),
              'best_fit_plane_max_residual_mm':float(np.abs((xyz-center)@basis[2]).max()),
              'original_plane_max_residual_mm':float(np.abs((xyz-center)@normal).max()),
              'closure':'Nonoverlapping projected ear clipping of same MATERIAL boundary, different ear order; NO centroid fan; no boundary moved'})
        cap=np.concatenate(caps);faces=np.concatenate([wall,cap]);mesh=trimesh.Trimesh(v,faces,process=False)
        wc=classify(v,cap,v,wall,contact_pairs(v,cap,v,wall))
        pairs=contact_pairs(v,cap,v,cap);pairs=pairs[pairs[:,0]<pairs[:,1]];cc=classify(v,cap,v,cap,pairs)
        _,area,_=triangle_data(v,faces)
        valid=bool(mesh.is_watertight and mesh.is_winding_consistent and (area>1e-10).all() and wc['confirmed_transverse_crossings']==0 and cc['confirmed_transverse_crossings']==0 and cc['coplanar_overlap_pairs']==0 and wc['coplanar_overlap_pairs']==0)
        variants.append({'variant':variant,'volume_mL':volume(v,faces),'watertight':bool(mesh.is_watertight),'winding_consistent':bool(mesh.is_winding_consistent),
          'minimum_area_mm2':float(area.min()),'cap_wall_crossings':wc['confirmed_transverse_crossings'],
          'cap_cap_crossings':cc['confirmed_transverse_crossings'],'cap_wall_coplanar_overlaps':wc['coplanar_overlap_pairs'],
          'cap_cap_coplanar_overlaps':cc['coplanar_overlap_pairs'],'geometrically_valid_at_sample':valid,
          'caps':records,'failed_cap_wall_rows':[r for r in wc['rows'] if r['class'] in ['FINITE_TRANSVERSE_CROSSING','COPLANAR_OVERLAP']],
          'failed_cap_cap_rows':[r for r in cc['rows'] if r['class'] in ['FINITE_TRANSVERSE_CROSSING','COPLANAR_OVERLAP']]})
    return variants

def local_quality(a,resolved,cv,tv,tf,tt):
    v,f=a['vertices'],a['faces'];own=a['path_owner'];paths=resolved['paths'];_,edges,length=mesh_graph(v,f)
    c0,ar0,_=triangle_data(v,f);cross,ar,_=triangle_data(v+cv,f);ratio=ar/ar0
    grad=np.linalg.norm(cv[edges[:,0]]-cv[edges[:,1]],axis=1)/length;mag=np.linalg.norm(cv,axis=1)
    masks={p['id']:own==i for i,p in enumerate(paths)}
    for name,node in resolved['nodes'].items():
        if name.startswith(('J_','T_')):
            adjacent=[i for i,p in enumerate(paths) if name in [p['marker_names'][0],p['marker_names'][-1]]]
            masks[name]=np.isin(own,adjacent)&(np.linalg.norm(v-np.array(node['position_mm']),axis=1)<5)
    result={}
    for name,mask in masks.items():
        faces=mask[f].any(1);ee=mask[edges].any(1)
        if not mask.any():continue
        result[name]={'vertices':int(mask.sum()),'maximum_mm':float(mag[mask].max()),'median_mm':float(np.median(mag[mask])),
          'moved_vertices':int((mag[mask]>1e-8).sum()),'minimum_area_ratio':float(ratio[faces].min()),'maximum_area_ratio':float(ratio[faces].max()),
          'maximum_edge_gradient':float(grad[ee].max()),'area_failure_source_faces':np.flatnonzero(faces&((ratio<.8)|(ratio>1.35))).tolist()}
    focus={'F01':[34757,34758],'F02':[30717,30718,30719],'F03':[61933,61934],'F04':[30663]}
    tissue={};_,te,tl=mesh_graph(tv,tf);_,ta0,_=triangle_data(tv,tf);_,ta,_=triangle_data(tv+tt,tf);tr=ta/ta0;tgrad=np.linalg.norm(tt[te[:,0]]-tt[te[:,1]],axis=1)/tl
    for name,ids in focus.items():
        m=np.isin(np.arange(len(tv)),ids)
        for _ in range(2):m[te[m[te].any(1)].ravel()]=True
        ff=m[tf].any(1);ee=m[te].any(1)
        tissue[name]={'two_ring_vertex_count':int(m.sum()),'area_ratio_range':[float(tr[ff].min()),float(tr[ff].max())],
          'maximum_edge_gradient':float(tgrad[ee].max()),'anatomical_donor_assignment':'UNCONFIRMED' if name in ['F03','F04'] else 'No new anatomical claim'}
    return {'cavity_regions':result,'tissue_focus':tissue,'diagnostic_regions_may_overlap':True,'capacity_accounting_uses_separate_disjoint_supports':True}

def centerline_clearance(a,resolved,cv):
    # Real finite surface distance, but only sampled centerline points; not instrument envelope clearance.
    with (N1/'sections.csv').open(encoding='utf-8-sig',newline='') as s:rows=list(csv.DictReader(s))
    from n1_analysis import path_station
    by={p['id']:p for p in resolved['paths']};rows=[r for r in rows if r['status']=='PATH_LOCAL_SECTION' and (r['path_id']=='MAIN' or r['path_id'].startswith('B_'))]
    p=np.array([path_station(by[r['path_id']],float(r['station_arc_mm'])) for r in rows]);scene=ray_scene(a['vertices']+cv,a['faces'])
    signed=scene.compute_signed_distance(o3d.core.Tensor((p-np.array([16.,16.,-81.])).astype(np.float32))).numpy()
    answer={}
    for name in sorted({r['path_id'] for r in rows}):
        ii=np.array([i for i,r in enumerate(rows) if r['path_id']==name]);distance=np.abs(signed[ii]);k=ii[np.argmin(distance)]
        answer[name]={'samples':len(ii),'minimum_sampled_centerline_surface_distance_mm':float(distance.min()),
          'minimum_station_id':rows[k]['id'],'positive_sign_outside_samples':int((signed[ii]>0).sum()),
          'not_instrument_clearance':True}
    return {'paths':answer,'scope':'Float32 centered RaycastingScene signed-distance sampling at trusted N1 local stations. No new section areas computed; unresolved stations excluded. Sign near baseline defects is not certified.',
      'endoscope_radius_or_selected_path_assumed':False,'no_route_safety_certificate':True}

def run(selected=None):
    protect();a,d2,tv,tf,resolved,approval=inputs();baseline=closure_variants(d2['reference_vertices'],d2,approval)
    write(OUT/'closure_reference_check.json',baseline)
    names=selected or [f'{p}_{s}' for p in ['S2','S1','S3'] for s in ['contract','expand']]
    for name in names:
            plan,side=name.split('_',1)
            directory=OUT/'prototypes/thin_face_corrected'/name;cv=np.load(directory/'research_cavity_offset.npy');tt=np.load(directory/'research_tissue_offset.npy')
            write(directory/'local_risk_metrics.json',local_quality(a,resolved,cv,tv,tf,tt))
            write(directory/'centerline_distance_probes.json',centerline_clearance(a,resolved,cv))
            result=[]
            for u in [.25,.5,.75,1.]:
                variants=closure_variants(d2['reference_vertices']+u*map_d2(cv,d2),d2,approval)
                valid=[x['volume_mL'] for x in variants if x['geometrically_valid_at_sample']]
                result.append({'u':u,'material_mapped_R1_volume_mL':volume(d2['reference_vertices']+u*map_d2(cv,d2),d2['faces']),
                  'valid_alternative_volumes_mL':valid,'valid_alternative_spread_mL':float(np.ptp(valid)) if valid else None,'variants':variants})
                print('Closure',plan,side,u,'valid',len(valid),'volumes',valid,flush=True)
            write(directory/'closure_sensitivity.json',{'status':'MEASUREMENT_ONLY_DERIVED_CLOSURES_NOT_APPROVED_NEW_DOMAIN',
              'D2_reference_changed':False,'measurement_boundary_material_stencils_changed':False,
              'caps_used_as_physical_walls':False,'sampled_levels':result,'continuous_closure_certificate':False})
    protect()

if __name__=='__main__':run(sys.argv[1:] or None)
