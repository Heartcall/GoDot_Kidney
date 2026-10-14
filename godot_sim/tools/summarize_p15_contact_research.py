"""Summarize the one P1.5 research trial; gate failure never exports formal states."""
import numpy as np
from scipy.spatial import cKDTree
from trimesh.triangles import points_to_barycentric
from research_p15_contact_mapping import *
from localize_p15_conflicts import spatial_labels


def write_group_index(result):
    localization=read_json(ROOT/'localization_report.json')
    lines=['# P1.5 原始候选空间分组与人工检查索引','',
      '零基原始 OBJ 三角面编号；2 mm 单链聚类。位置为有限交线或最近有限特征中点。路径／接点仅是空间关联，不证明解剖归属。',
      'C：旧58对穿越候选，复核为点接触；S：旧23对自交候选，复核相离；P：643对近共面候选。', '',
      '|组|配对|两侧面数|中心 mm|关联路径|最近标记／距离 mm|关联面面积 mm²|剖切截图|',
      '|---|---:|---|---|---|---|---|---|']
    for g in localization['groups']:
        center=', '.join(f'{x:.2f}' for x in g['center_mm']);area='/'.join(f'{x:.3f}' for x in g['incident_support_area_mm2']);mark=g['nearest_landmarks_mm'][0]
        lines.append(f"|{g['id']}|{g['pair_count']}|{g['first_unique_faces']}/{g['second_unique_faces']}|{center}|{', '.join(g['nearest_path_vertex_votes'])}|{mark[0]} / {mark[1]:.2f}|{area}|[查看](screenshots/{g['id']}_section.png)|")
    lines+=['','关联面面积不是穿透面积。原 C 组正长度交线与共面重叠面积均为0；原 S 组有限距离为0.001278～1.047199 mm。',
        '原始共面重叠配对面积和12.073980 mm²，可能重复计数，不是穿透面积。','',
        'F01、F02只标记失败映射对应的原始组织面位置，仍显示原始参考态：',
        '- [F01](screenshots/F01_section.png)：组织边[34757,34758]，原长度0.025704 mm，u=1位移梯度0.988045。',
        '- [F02](screenshots/F02_section.png)：组织面53208，u=1面积比0.712839。','',
        '完整面索引、包围盒、最近标记、路径票数、聚类敏感性见localization_report.json；失败位置见research_result.json。']
    for group in result['failure_groups'][2:]:
        lines.append(f"- [{group['id']}](screenshots/{group['id']}_section.png)：{group['reason']}")
    (ROOT/'conflict_groups.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def summarize():
    v,f,tv,tf,d=inputs();field=np.load(ROOT/'UNACCEPTED_contact_tissue_displacement.npy')
    morph_path=PROJECT/'deformation/full_cavity/morph/interpolation_report.json'
    morph=read_json(morph_path)
    for name,digest in morph['output_sha256'].items():
        if source_record(morph_path.parent/name)['sha256']!=digest: raise ValueError('Approved cavity morph changed '+name)
    build_report=read_json(ROOT/'mapping_build_report.json')
    for name,digest in build_report['output_sha256'].items():
        if source_record(ROOT/name)['sha256']!=digest: raise ValueError('Research data mismatch '+name)
    ids=np.load(AUDIT/'tissue_to_cavity_face.npy');bary=np.load(AUDIT/'mapping_barycentric.npy')
    gap=np.load(AUDIT/'tissue_to_cavity_distance_mm.npy');owners=np.load(PROJECT/'deformation/p1_masks/path_owner.npy')
    resolved=read_json(PROJECT/'deformation/cavity_topology_resolved.json');path_names=[p['id'] for p in resolved['paths']]
    donor=np.einsum('ni,nij->nj',bary,d[f[ids]]);q=np.einsum('ni,nij->nj',bary,v[f[ids]])
    cavity_normals=normalize(np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]]))
    normal_dot=np.einsum('ij,ij->i',vertex_normals(tv,tf),cavity_normals[ids])
    magnitude=np.linalg.norm(field,axis=1)
    proxies={}
    for name,mask in [('outward_facing_proxy',normal_dot>.5),('remote_distance_proxy',gap>=12),('uncertain_near',(gap<1)&(normal_dot>=-.5)),('inner_near',(gap<=1)&(normal_dot<-.5))]:
        proxies[name]={'vertices':int(mask.sum()),'moving_above_1e_minus12_mm':int((magnitude[mask]>1e-12).sum()),'maximum_mm':float(magnitude[mask].max()),'mean_mm':float(magnitude[mask].mean())}
    uncertain=np.flatnonzero((gap<1)&(normal_dot>=-.5)&(magnitude>1e-12))
    _,edges,length=mesh_graph(tv,tf);gradient=np.linalg.norm(field[edges[:,0]]-field[edges[:,1]],axis=1)/length
    baseline=np.load(AUDIT/'cross_contact_pairs.npy');base_set=set(map(tuple,baseline))
    baseline_geom=pair_geometry(v,f,tv,tf,baseline);base_tree=cKDTree(baseline_geom['centers'])
    old_self=np.load(AUDIT/'tissue_self_intersections.npy');self_set=set(map(tuple,old_self))
    self_geom=pair_geometry(tv,tf,tv,tf,old_self);self_tree=cKDTree(self_geom['centers'])
    valid=baseline_geom['feature_distance']<=1e-8;cp=baseline[valid];points=baseline_geom['centers'][valid]
    bc=points_to_barycentric(v[f[cp[:,0]]],points);bt=points_to_barycentric(tv[tf[cp[:,1]]],points)
    relative=np.einsum('ni,nij->nj',bt,field[tf[cp[:,1]]])-np.einsum('ni,nij->nj',bc,d[f[cp[:,0]]])
    np.save(ROOT/'original_contact_sample_points.npy',points);np.save(ROOT/'original_contact_relative_displacement.npy',relative)
    c0,a0,_=triangle_data(tv,tf);cc,aa,_=triangle_data(tv+field,tf);ratios=aa/a0
    thresholds={'minimum_area_ratio':.8,'maximum_area_ratio':1.35,'maximum_edge_displacement_gradient':.2,
      'reason':'Conservative engineering screen inherited from the accepted cavity tooling; not validated biological tissue strain limits. Thresholds are not relaxed to promote this trial.'}
    regions={}
    for name in ['J_05','J_09','B_31','B_32','BLADDER','IN_01','IN_02']:
        if name.startswith('J_'): domain=np.linalg.norm(tv-resolved['nodes'][name]['position_mm'],axis=1)<=8
        else:
            wanted=[path_names.index(name)]
            if name in ('BLADDER','IN_01','IN_02'): wanted += [path_names.index({'BLADDER':'BLADDER_TRANSITION','IN_01':'B_31','IN_02':'B_32'}[name])]
            domain=np.isin(owners[f[ids]],wanted).any(axis=1)&(gap<2)
        local_edges=domain[edges].any(axis=1);local_faces=domain[tf].any(axis=1);near=domain&(gap<=1)
        regions[name]={'tissue_vertices':int(domain.sum()),'near_vertices':int(near.sum()),
          'maximum_displacement_mm':float(np.linalg.norm(field[domain],axis=1).max()),
          'maximum_relative_to_cached_donor_mm':float(np.linalg.norm(field[near]-donor[near],axis=1).max()) if near.any() else None,
          'maximum_edge_gradient':float(gradient[local_edges].max()),'area_ratio_range':[float(ratios[local_faces].min()),float(ratios[local_faces].max())]}
    levels=[]
    for u in (0,.25,.5,.75,1):
        tag=f'{int(u*100):03}';cross=read_json(ROOT/f'cross_check_u{tag}.json');slf=read_json(ROOT/f'self_check_u{tag}.json')
        digest=source_record(ROOT/'UNACCEPTED_contact_tissue_displacement.npy')['sha256']
        if cross['field_sha256']!=digest or slf['field_sha256']!=digest: raise ValueError('Stale scan')
        cpairs=np.load(ROOT/f'cross_pairs_u{tag}.npy');spairs=np.load(ROOT/f'tissue_self_pairs_u{tag}.npy')
        # No repeat expensive scan: reclassify saved finite candidate triangles.
        cverify=verify_pairs(v+u*d,f,tv+u*field,tf,cpairs);sverify=verify_pairs(tv+u*field,tf,tv+u*field,tf,spairs)
        added=np.array([p for p in cpairs if tuple(p) not in base_set],dtype=int).reshape(-1,2)
        geom=pair_geometry(v+u*d,f,tv+u*field,tf,added) if len(added) else None
        distances=base_tree.query(geom['centers'])[0] if geom is not None else np.zeros(1)
        newself=np.array([p for p in spairs if tuple(p) not in self_set],dtype=int).reshape(-1,2)
        sg=pair_geometry(tv+u*field,tf,tv+u*field,tf,newself) if len(newself) else None
        nt=normalize(np.cross((v+u*d)[f[ids,1]]-(v+u*d)[f[ids,0]],(v+u*d)[f[ids,2]]-(v+u*d)[f[ids,0]]))
        sep=np.einsum('ij,ij->i',tv+u*field-q-u*donor,nt)
        scene=__import__('audit_tissue_cavity').ray_scene(tv+u*field,tf)
        o3d=__import__('open3d');cast=scene.compute_closest_points(o3d.core.Tensor((v+u*d-__import__('audit_tissue_cavity').ORIGIN).astype(np.float32)))
        fid=cast['primitive_ids'].numpy();uv=cast['primitive_uvs'].numpy().astype(float);weights=np.column_stack([1-uv.sum(axis=1),uv])
        closest=np.einsum('ni,nij->nj',weights,(tv+u*field)[tf[fid]])
        cv_gap=np.linalg.norm(v+u*d-closest,axis=1)
        local={}
        for name,record in regions.items():
            local[name]={'maximum_displacement_mm':u*record['maximum_displacement_mm'],'maximum_edge_gradient':u*record['maximum_edge_gradient'],'maximum_relative_to_cached_donor_mm':u*record['maximum_relative_to_cached_donor_mm'] if record['maximum_relative_to_cached_donor_mm'] is not None else None}
        levels.append({'fill':u,'tissue_quality':cross['tissue_quality'],'approved_cavity_quality':morph['samples'][len(levels)],'cross':cverify,'self':sverify,
           'contact_changes':{'added_raw_pair_count':len(added),'removed_raw_pair_count':len(base_set-set(map(tuple,cpairs))),
             'added_pair_distance_to_original_contact_cloud_mm':summary(distances),
             'added_pair_feature_gap_mm':summary(geom['feature_distance']) if geom is not None else None,
             'added_pairs':added.tolist(),'added_pair_centers_mm':geom['centers'].tolist() if geom is not None else [],
             'added_self_raw_pairs':newself.tolist(),'new_self_feature_gap_mm':sg['feature_distance'].tolist() if sg is not None else [],
             'new_self_distance_to_old_cloud_mm':self_tree.query(sg['centers'])[0].tolist() if sg is not None else [],
             'interpretation':'Pair changes alone are not crossing. Positive finite segments and planar overlap reviewed independently; contact-cloud distances localize movement, not prove safety.'},
           'relative_geometry':{'original_contact_sample_maximum_relative_motion_mm':float(u*np.linalg.norm(relative,axis=1).max()),
              'cavity_vertex_to_tissue_closest_surface_gap_mm':summary(cv_gap),
              'near_tissue_cached_donor_signed_plane_separation_mm':summary(sep[gap<=1]),
              'limits':'Gap is closest-surface separation, NOT wall thickness or penetration depth; cached-donor plane separation is a local kinematic indicator, NOT a solid occupancy proof.'},'local_regions':local})
    regressions=[]
    old_probes=PROJECT/'analysis/irrigation_baseline/p15_mapping_probe'
    for strength in (0,5,30):
        fld=np.load(old_probes/f'UNACCEPTED_tissue_displacement_strength{strength}.npy')
        for u in (.25,1):
            pairs=np.load(old_probes/f'proper_strength{strength}_u{int(u*100):03}.npy')
            review=verify_pairs(v+u*d,f,tv+u*fld,tf,pairs)
            regressions.append({'strength':strength,'fill':u,'old_claimed_cross_count':len(pairs),'independent':review})
    # Reference location markers only; no failed deformation rendered as accepted states.
    failure_groups=[]
    locations=[(1,tv[edges[np.argmax(gradient)]].mean(axis=0),np.flatnonzero(np.isin(tf,edges[np.argmax(gradient)]).any(axis=1)),'Maximum local displacement gradient, B_29/B_32 nearest-donor switch near IN_02/J_09.'),
          (2,tv[tf[np.argmin(ratios)]].mean(axis=0),np.array([np.argmin(ratios)]),'Minimum area ratio 0.712839, tissue face 53208 near B_26/IN_02.')]
    if len(uncertain):
        for label in np.unique(spatial_labels(tv[uncertain])):
            points=uncertain[spatial_labels(tv[uncertain])==label]
            locations.append((len(locations)+1,tv[points].mean(axis=0),np.flatnonzero(np.isin(tf,points).any(axis=1)),'Normal-facing ambiguous one-ring tissue vertices: '+','.join(map(str,points))))
    for number,center,faces,reason in locations:
        vertices=tv[tf[faces]].reshape(-1,3);normal=np.cross(tv[tf[faces,1]]-tv[tf[faces,0]],tv[tf[faces,2]]-tv[tf[faces,0]]).mean(axis=0);normal/=np.linalg.norm(normal)
        mapped=ids[np.unique(tf[faces])];votes={path_names[int(o)]:int(np.sum(owners[f[mapped]]==o)) for o in np.unique(owners[f[mapped]])}
        failure_groups.append({'id':f'F{number:02}','kind':'FAILED_MAPPING_REFERENCE_LOCATION_ONLY','pair_count':len(faces),'pairs':[[int(i),int(i)] for i in faces],
             'center_mm':center.tolist(),'extent_mm':(vertices.max(axis=0)-vertices.min(axis=0)).tolist(),'view_normal':normal.tolist(),
             'nearest_path_vertex_votes':votes,'independent_positive_segments':0,'reason':reason,
             'reason_cn':('组织边梯度0.988045，需核对归属' if number==1 else '组织面53208面积比0.712839' if number==2 else '法线归属不明确的近壁点受到一环约束；需人工检查')})
    meta=read_json(ROOT/'audit_preview.json');meta['groups']=[g for g in meta['groups'] if not g['id'].startswith('F')]+failure_groups
    (ROOT/'audit_preview.json').write_bytes(json_bytes(meta))
    fixed=np.load(PROJECT/'deformation/p1_masks/port_fixed_masks.npy');ports={}
    for name,mask in zip(('BLADDER','IN_01','IN_02'),fixed): ports[name]={'vertices':int(mask.sum()),'maximum_cavity_displacement_mm':float(np.linalg.norm(d[mask],axis=1).max()),'all_u_exact_zero':bool(np.all(d[mask]==0))}
    violations=[]
    for level in levels:
        quality=level['tissue_quality']
        if quality['area_ratio_range'][0]<thresholds['minimum_area_ratio']: violations.append({'fill':level['fill'],'reason':'Tissue area compression exceeds conservative screen','value':quality['area_ratio_range'][0]})
        if quality['area_ratio_range'][1]>thresholds['maximum_area_ratio']: violations.append({'fill':level['fill'],'reason':'Tissue area expansion exceeds conservative screen','value':quality['area_ratio_range'][1]})
        if quality['maximum_edge_gradient']>thresholds['maximum_edge_displacement_gradient']: violations.append({'fill':level['fill'],'reason':'Tissue edge gradient exceeds conservative screen','value':quality['maximum_edge_gradient']})
        if quality['normal_reversal_count'] or quality['degenerate_count'] or not quality['finite'] or level['cross']['positive_segment_count'] or level['self']['positive_segment_count'] or level['self']['coplanar_overlap_pair_count']: violations.append({'fill':level['fill'],'reason':'Hard geometry failure'})
    report={'date':'2026-10-14','status':'BLOCKED_RESEARCH_TRIAL_NOT_PROMOTED' if violations else 'NUMERICAL_SCREEN_ONLY_PENDING_REVIEW','thresholds':thresholds,'violations':violations,
      'build':build_report,'approved_cavity_report':source_record(morph_path),'local_regions_expanded':regions,'fixed_cavity_ports':ports,'five_levels':levels,'old_probe_reclassification':regressions,
      'tissue_field_summary':{'maximum_mm':float(magnitude.max()),'mean_mm':float(magnitude.mean()),'geometrical_proxy_regions':proxies,'uncertain_moving_vertex_ids':uncertain.tolist(),'uncertain_positions_mm':tv[uncertain].tolist(),'limits':'Facing and distance are geometric proxies, not anatomical surface labels; the three ambiguous vertices are explicitly flagged rather than assumed valid.'},
      'original_contact_samples':{'count':int(valid.sum()),'maximum_relative_displacement_mm':float(np.linalg.norm(relative,axis=1).max()),'relative_displacement_mm':summary(np.linalg.norm(relative,axis=1))},
      'failure_groups':failure_groups,'all_u_oriented_area_ratio_minimum':minimum_oriented_area_ratio(tv,tf,field),
      'outer_inner_relation':{'far_anchored_vertices':int(np.load(ROOT/'remote_anchors.npy').sum()),'far_exact_zero':bool(np.all(field[np.load(ROOT/'remote_anchors.npy')]==0)),
          'source_bounds_unchanged_at_five_levels':all(np.max(abs(np.asarray(level['tissue_quality']['bounds_change_mm'])))==0 for level in levels),
          'anatomical_inner_outer_labels_available':False,'wall_thickness_validated':False,'limits':'Normal-facing inner-near proxy only; neither an anatomical partition nor a volumetric tissue material map. Outer bounding-box stability alone does not certify outer shape.'},
      'limits':['Five discrete collision checks plus analytic continuous face-orientation bound; no continuous collision certificate.',
          'Contact clouds, pairing residuals and plane separation do not define physiological contact permission, penetrated volume or true wall thickness.',
          'Self-intersection candidates from Open3D are independently reviewed; near-parallel disjoint pairs must not be called confirmed intersections.',
          'No accepted tissue states or synchronized joint morph preview is generated because the conservative geometry screen failed.'],
      'next_decision':'Review F01/F02 near IN_02/J_09 first, then contact groups. A derived reference is not justified by the old58/23 alone; consider a separately reviewed local mesh-quality candidate only if inspection confirms source discretization/segmentation ambiguity. Never replace original OBJ.'}
    (ROOT/'research_result.json').write_bytes(json_bytes(report));print('GATE',report['status'],'violations',len(violations),'contact residual max',report['original_contact_samples']['maximum_relative_displacement_mm'],flush=True)
    for level in levels: print(level['fill'],'cross',level['cross']['positive_segment_count'],'self',level['self']['positive_segment_count'],'new raw',level['contact_changes']['added_raw_pair_count'],'clouddist',level['contact_changes']['added_pair_distance_to_original_contact_cloud_mm']['max'],flush=True)
    write_group_index(report)
    return report

if __name__=='__main__': summarize()
