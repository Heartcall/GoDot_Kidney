"""Append-only N0 feedback and a fixed-wall-only C11 measurement refinement.

No historical N0 file, accepted mesh, displacement, or main scene is written.
Unknown anatomical transition volumes remain unknown.
"""
from n0_common import *
import build_n0_domains as domains
from collections import Counter
N0=OUT
OUT=PROJECT/'deformation/capacity_v2_n0_closeout'

def protect(initialize=False):
    OUT.mkdir(parents=True,exist_ok=True);target=OUT/'protected_before.json'
    if initialize and not target.exists():
        names=subprocess.check_output(['git','ls-files','-z'],cwd=REPO).decode('utf8').split('\0')
        paths={REPO/n for n in names if n and (REPO/n).is_file()}
        for base in [PROJECT/'deformation',PROJECT/'analysis/irrigation_baseline']:
            paths.update(p for p in base.rglob('*') if p.is_file() and OUT not in p.parents and p.suffix in ('.npy','.bin','.json','.md','.csv','.png','.log','.import'))
        write_json(target,{p.relative_to(REPO).as_posix():sha(p) for p in sorted(paths)})
    before=read_json(target);changed=[p for p,h in before.items() if not (REPO/p).exists() or sha(REPO/p)!=h]
    write_json(OUT/'protected_after.json',{'files':len(before),'changed':changed})
    if changed:raise ValueError('Historical or accepted file changed: '+str(changed))
    return len(before)

def feedback():
    rows=read_json(N0/'domain_candidates.json')['candidates'];statuses={}
    for r in rows:
        key=r['id'];code=key.split('_')[0]
        if code=='C11':status='VISUAL_REVIEW_PASSED_D2_PENDING'
        elif code=='C06':status='REJECTED_BY_USER_NATURAL_WALL_REMOVAL'
        elif code in ['C01','C02','C03','C04','C05']:status='EXISTING_NATURAL_BRANCH_EXCLUSION_NOT_RECOMMENDED'
        elif code in ['C07','C08','C09','C10']:status='NOT_INDIVIDUALLY_REVIEWED_WIDE_CHAMBER_RISK'
        else:status='CONTROL_NOT_ANATOMICALLY_APPROVED'
        statuses[key]={'status':status,'source_candidate_sha256':sha(N0/'domains'/key/'candidate.json'),
           'user_individual_visual_review':code in ['C11','C06'],'D2_approved':False}
    record={'schema':'N0_HUMAN_REVIEW_V1','version':'2026-10-14-v1','date':'2026-10-14','authority':'Direct user feedback in this conversation',
       'candidate_statuses':statuses,'preferred_candidate':'C11_inlet_distal_control','D2_approved':False,'V_reference_effective_mL':None,
       'observations':{'C11_IN02':'Gold virtual cap is in the narrower artificial tube; excluded gray region contains artificial structures that should not be retained. Visual review passed, D2 still pending.',
       'C06_IN02':'Gold cap crosses a wider natural chamber, removes natural branch entrance, and excludes wall that must be retained. User rejected this candidate.',
       'BLADDER_IN01':'No visible abnormality in the views examined this round; not identification of a true UPJ or complete anatomical boundary.'},
       'contact_review':{'status':'NO_VISIBLE_ANOMALY_IN_USER_REVIEWED_VIEWS','specific_previous_anomaly_reproduced':False,
          'limits':'Does not mean repaired, globally collision-free, or continuously certified. New deformation requires new verification.'},
       'scope_limits':['No complete anatomy, true wall thickness, F03/F04 ownership, normal capacities or continuous collisions approved.',
          'C07-C10 are not individually user accepted/rejected; computational comparison is recorded separately.'],
       'historical_n0_report_sha256':sha(REPO/'docs/kidney_irrigation_capacity_v2_n0_result.md'),'source_arrays_sha256':AUTHORITY}
    target=OUT/'human_review_2026_10_14_v1.json'
    if target.exists() and read_json(target)!=record:raise ValueError('Immutable feedback differs; create a new version, do not overwrite')
    if not target.exists():write_json(target,record)
    return record

def face_area_by_source(directory,n):
    v=np.load(directory/'reference_vertices.npy');f=np.load(directory/'faces.npy');src=np.load(directory/'source_face_ids.npy')
    area=np.linalg.norm(np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]]),axis=1)/2
    return np.bincount(src[src>=0],weights=area[src>=0],minlength=n)

def compare_risk():
    rows={r['id']:r for r in read_json(N0/'domain_candidates.json')['candidates']};base=rows['C06_near_BASE']['cuts'][2]
    vb=np.load(N0/'domains/C06_near_BASE/reference_vertices.npy');bpoints=vb[base['selected_boundary_vertex_ids']]
    result=[]
    for name in ['C07_IN01_collar','C08_IN02_collar','C09_UPJ_proximal_unconfirmed','C10_UPJ_distal_unconfirmed']:
        cut=rows[name]['cuts'][2];v=np.load(N0/'domains'/name/'reference_vertices.npy');pts=v[cut['selected_boundary_vertex_ids']]
        from scipy.spatial import cKDTree
        hausdorff=max(cKDTree(bpoints).query(pts)[0].max(),cKDTree(pts).query(bpoints)[0].max())
        split_same=set(base['split_source_face_ids'])==set(cut['split_source_face_ids'])
        removed_same=set(base['removed_source_face_ids'])==set(cut['removed_source_face_ids'])
        shift=(np.array(cut['center_mm'])-base['center_mm'])@np.array(base['normal_toward_artificial_END'])
        result.append({'id':name,'individual_user_review':'NOT_REVIEWED','computer_evidence':'SAME_IN02_CUT_AS_REJECTED_C06' if hausdorff<1e-10 and split_same and removed_same else 'DIFFERENT_NEARBY_WIDE_IN02_CUT_REQUIRES_OWN_REVIEW',
          'IN02_ring_hausdorff_mm':float(hausdorff),'IN02_split_source_faces_identical':split_same,'IN02_removed_source_faces_identical':removed_same,
          'shift_toward_artificial_END_mm':float(shift),'IN02_area_mm2':cut['section_area_mm2'],
          'recommendation':'DO_NOT_PROMOTE_TO_D2','limits':'Geometry comparison is not an additional user observation or an anatomical material classification.'})
    write_json(OUT/'C07_C10_computational_review.json',{'comparisons':result})
    return result

def build_refinement():
    _,a=verify_sources();v,f=a['cavity_reference_vertices'],a['cavity_faces'];masks=np.load(PROJECT/'deformation/p1_masks/port_fixed_masks.npy')
    c11=read_json(N0/'domains/C11_inlet_distal_control/candidate.json');paths={p['id']:p for p in read_json(PROJECT/'deformation/cavity_topology_resolved.json')['paths']}
    original_area=trimesh.Trimesh(v,f,process=False).area_faces;area11=face_area_by_source(N0/'domains/C11_inlet_distal_control',len(f));inventory=[]
    guard=max(1e-6,float(np.linalg.norm(np.ptp(v,axis=0)))*1e-8)
    for i,port in enumerate(['BLADDER','IN_01','IN_02']):
        base,end=np.asarray(paths[port]['points_mm'])[[0,-1]];n=(end-base)/np.linalg.norm(end-base);axial=(v-base)@n
        mixed=masks[i][f].any(1)&~masks[i][f].all(1);fully=masks[i][f].all(1);upper=float(axial[f[mixed]].max())
        cut=c11['cuts'][i];station=float((np.array(cut['center_mm'])-base)@n)
        inventory.append({'port':port,'C11_cut_axial_from_BASE_mm':station,'mixed_wall_triangle_max_axial_mm':upper,
           'numerical_guard_mm':guard,'fixed_only_plane_lower_bound_mm':upper+guard,
           'C11_retained_fully_fixed_source_faces':int(((area11>1e-10)&fully).sum()),
           'C11_retained_fully_fixed_wall_area_mm2':float(area11[fully].sum()),
           'C11_cut_source_faces_not_fully_fixed':int((~masks[i][f[np.asarray(cut['split_source_face_ids'])]].all(1)).sum()),
           'unambiguously_fixed_only_proximal_refinement_possible':bool(port!='BLADDER' and upper+guard<station),
           'total_retained_artificial_transition_volume_mL':None})
    record=inventory[2];lower=record['mixed_wall_triangle_max_axial_mm']
    if not record['unambiguously_fixed_only_proximal_refinement_possible']:raise ValueError('No justified IN02 fixed-only refinement; stop')
    base,end=np.asarray(paths['IN_02']['points_mm'])[[0,-1]];axis=(end-base)/np.linalg.norm(end-base)
    axial=(v-base)@axis;fixed_faces=masks[2][f].all(1)
    events=np.unique(axial[np.unique(f[fixed_faces])]);events=events[(events>lower+guard)&(events<1.)]
    upper=float(events.min()) if len(events) else 1.
    target=(lower+upper)/2
    record['next_source_vertex_event_mm']=upper;record['selected_quality_plane_mm']=target
    record['quality_plane_rule']='Midpoint of first source-vertex event interval above all mixed fixed/nonfixed triangles, inside the original C11 cut; chosen for stable clipping, not desired volume.'
    old_out=domains.OUT
    try:
        domains.OUT=OUT
        row=domains.build_candidate('C11_R1_IN02_fixed_collar',{'BLADDER':.5,'IN_01':None,'IN_02':None},{'IN_02':target-1.})
    finally:domains.OUT=old_out
    if not row['geometry_valid'] or row['excluded_natural_marker_ids'] or row['natural_paths_with_outside_samples']:raise ValueError('Refinement geometry/natural-path gate failed; do not publish as reviewable candidate')
    directory=OUT/'domains'/row['id'];area1=face_area_by_source(directory,len(f));delta=area11-area1;changed=np.flatnonzero(delta>1e-9)
    if not np.all(masks[2][f[changed]].all(1)) or delta.min()<-1e-9:raise ValueError('Refinement alters wall outside approved fixed IN02 patch')
    save_npy(OUT/'C11_source_wall_area_mm2.npy',area11);save_npy(OUT/'R1_source_wall_area_mm2.npy',area1);save_npy(OUT/'removed_fixed_collar_source_faces.npy',changed)
    # Independently cut C11 itself, close the differential collar and integrate it.
    d11=N0/'domains/C11_inlet_distal_control';vv=np.load(d11/'reference_vertices.npy');ff=np.load(d11/'faces.npy');ss=np.load(d11/'source_face_ids.npy');cc=np.load(d11/'virtual_port_labels.npy')
    wi=np.load(d11/'source_vertex_ids.npy');wv=np.load(d11/'source_vertex_weights.npy');weights=[{int(k):float(w) for k,w in zip(ids,vals) if k>=0 and w!=0} for ids,vals in zip(wi,wv)]
    base,end=np.asarray(paths['IN_02']['points_mm'])[[0,-1]];n=(end-base)/np.linalg.norm(end-base);center=base+target*n
    new_v,new_f,new_s,new_c,new_w,info,removed=domains.local_cut(vv,ff,ss,cc,weights,center,n,base+((target+1)/2)*n,3)
    shell_faces=np.vstack([removed,np.array(info['cap_triangle_vertex_ids'])[:,::-1]])
    shell_labels=np.zeros(len(shell_faces),int);oldplane=(new_v[shell_faces]-np.array(c11['cuts'][2]['center_mm']))@n
    shell_labels[np.abs(oldplane).max(1)<1e-10]=1;shell_labels[len(removed):]=2
    lookup={tuple(sorted(face)):i for i,face in enumerate(f)};shell_source=[]
    for face,label in zip(shell_faces,shell_labels):
        support=sorted({k for idx in face for k,value in new_w[int(idx)].items() if value>1e-14})
        shell_source.append(-1 if label else lookup.get(tuple(support),-2))
    if -2 in shell_source:raise ValueError('Differential shell source provenance unresolved')
    shell=trimesh.Trimesh(new_v,shell_faces,process=False);shell_volume=signed_volume(new_v,shell_faces)/1000
    shell_checks=domains.cap_validation(new_v,shell_faces,shell_labels)
    source_checks=domains.cap_original_validation(new_v,shell_faces,shell_labels,f,{1:c11['cuts'][2],2:info})
    volume_difference=c11['candidate_measurement_volume_mL']-row['candidate_measurement_volume_mL']
    if not shell.is_watertight or not shell.is_winding_consistent or abs(shell_volume-volume_difference)>1e-10 or shell_checks['cap_wall_invalid_count'] or source_checks['invalid_count']:raise ValueError('Differential collar verification failed')
    for key,value in [('collar_reference_vertices',new_v),('collar_faces',shell_faces),('collar_source_face_ids',np.array(shell_source)),('collar_virtual_cap_labels',shell_labels)]:save_npy(OUT/(key+'.npy'),value)
    binary_mesh(OUT/'removed_fixed_collar.bin',new_v,shell_faces)
    proof={'C11_measurement_proxy_mL':c11['candidate_measurement_volume_mL'],'refined_measurement_proxy_mL':row['candidate_measurement_volume_mL'],
       'certified_fixed_wall_collar_removed_mL':volume_difference,'independent_closed_collar_volume_mL':shell_volume,
       'collar_length_mm':1-target,'source_face_ids':changed.tolist(),'removed_wall_area_mm2':float(delta[changed].sum()),
       'all_changed_wall_faces_fully_in_approved_IN02_fixed_mask':True,'nonfixed_source_wall_area_change_max_mm2':float(np.abs(delta[~masks[2][f].all(1)]).max()),
       'original_reference_vertex_coordinates_unchanged':bool(np.array_equal(np.load(directory/'reference_vertices.npy')[:len(v)],v)),
       'ring_comparison_mm':{'C11':vv[c11['cuts'][2]['selected_boundary_vertex_ids']].tolist(),
          'R1':np.load(directory/'reference_vertices.npy')[row['cuts'][2]['selected_boundary_vertex_ids']].tolist()},
       'shell_watertight':bool(shell.is_watertight),'shell_winding_consistent':bool(shell.is_winding_consistent),
       'shell_cap_checks':{k:value for k,value in shell_checks.items() if k!='pairs'},'shell_original_wall_checks':{k:value for k,value in source_checks.items() if k!='pairs'},
       'derivation':'IN02 plane = midpoint between the maximum mixed-triangle axial position and the next fully-fixed source vertex event. No capacity target, no threshold relaxation or deletion of degenerate faces.',
       'remaining_artificial_transition_volume_mL':None,'V_reference_effective_mL':None,
       'limits':'Only this closed collar is quantified as removable engineering artificial geometry. Remaining B31/B32/BLADDER transition volume is not identifiable from current inputs. C11 itself is not thereby certified as complete natural anatomy.'}
    write_json(OUT/'refinement_proof.json',proof)
    row['cap_area_vs_distal_control']={q['port']:q['section_area_mm2']/read_json(N0/'domains/C00_distal_control/candidate.json')['cuts'][i]['section_area_mm2'] for i,q in enumerate(row['cuts'])}
    row['wide_chamber_cut_warning']=[];row['review_status']='ENGINEERING_REFINEMENT_PENDING_USER_REVIEW';row['display_dataset']='N0_CLOSEOUT';row['preferred_parent']='C11_inlet_distal_control'
    write_json(directory/'candidate.json',row)
    transitions=[{'id':'BLADDER_TRANSITION','full_centerline_length_mm':paths['BLADDER_TRANSITION']['length_mm'],'nominal_retained_centerline_length_mm':paths['BLADDER_TRANSITION']['length_mm']/2,'volume_mL':None},
       {'id':'B_31','full_centerline_length_mm':paths['B_31']['length_mm'],'nominal_retained_centerline_length_mm':paths['B_31']['length_mm'],'volume_mL':None},
       {'id':'B_32','full_centerline_length_mm':paths['B_32']['length_mm'],'nominal_retained_centerline_length_mm':paths['B_32']['length_mm'],'volume_mL':None}]
    report={'fixed_wall_inventory':inventory,'retained_transition_centerlines':transitions,
       'C11_minus_rejected_C06_mL':c11['candidate_measurement_volume_mL']-read_json(N0/'domains/C06_near_BASE/candidate.json')['candidate_measurement_volume_mL'],
       'C11_minus_C06_interpretation':'Includes user-confirmed natural-wall removal; cannot estimate retained artificial volume.',
       'terminal_boundary_semantics':'T01-T22 retain source closed surfaces; anatomical termination and segmentation/virtual-cap provenance remain unknown.',
       'total_artificial_transition_volume_in_C11_mL':None,'all_natural_wall_in_C11_certified':False,'source_arrays_sha256':AUTHORITY}
    write_json(OUT/'C11_retained_structure_inventory.json',report)
    return row,proof,report

def build():
    verify_sources();protect(True);review=feedback();risk=compare_risk();row,proof,inventory=build_refinement()
    meta=read_json(N0/'review_preview.json');meta['candidates'].append(row);meta['closeout_feedback']=review;meta['closeout_refinement']=proof
    meta['historical_preview_sha256']=sha(N0/'review_preview.json');meta['no_new_deformation']=True
    meta['closeout_collar_binary_sha256']=sha(OUT/'removed_fixed_collar.bin')
    write_json(OUT/'review_preview.json',meta)
    write_json(OUT/'closeout_status.json',{'status':'N0_BOUNDARY_CLOSEOUT_PENDING_USER_DOMAIN_CONFIRMATION','D2_approved':False,'V_reference_effective_mL':None,
       'normal_V_min_mL':None,'normal_V_max_mL':None,'N1_started':False,'N1_target_calibration_ready':False,
       'N1_reference_only_descriptive_work_possible_after_user_approval':True,'remaining_transition_volume_identifiable':False,
       'user_contact_status':review['contact_review']['status'],'old_finite_checks_preserved':[0,.25,.5,.75,1,.37],
       'recommended_engineering_proxy_parent':'C11_inlet_distal_control','refinement_candidate':row['id'],
       'required_evidence':['Pre-artificial segmented natural cavity or reversible preprocessing with labeled wall ancestry.',
       'Approved UPJ/ureter cut boundary and artificial port aperture curves tied to source faces.',
       'Anatomical/segmentation meaning of T01-T22 terminal caps.']})
    print('C11',proof['C11_measurement_proxy_mL'],'R1',proof['refined_measurement_proxy_mL'],'certified collar mL',proof['certified_fixed_wall_collar_removed_mL'],'protected',protect())
    return row

if __name__=='__main__':build()
