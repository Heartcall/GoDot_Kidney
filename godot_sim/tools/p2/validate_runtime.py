"""Recompute quality and compare REAL Godot meshes to frozen accepted geometry.

No contact tolerance change and no new collision scan: identity of both position
arrays AND indices transfers the accepted finite-triangle checks exactly.
"""
import argparse
import hashlib
import numpy as np
from prepare_runtime import *

LEVELS = (0., .25, .5, .75, 1.)


def edges_of(faces):
    return np.unique(np.sort(np.concatenate([faces[:, [0,1]], faces[:, [1,2]], faces[:, [2,0]]]), axis=1), axis=0)


def cross_of(v, f):
    return np.cross(v[f[:, 1]]-v[f[:, 0]], v[f[:, 2]]-v[f[:, 0]])


def geometry(v, f, moved, edges=None):
    edges = edges_of(f) if edges is None else edges
    c0, c = cross_of(v, f), cross_of(moved, f)
    a0, a = np.linalg.norm(c0, axis=1)/2, np.linalg.norm(c, axis=1)/2
    length = np.linalg.norm(v[edges[:, 0]]-v[edges[:, 1]], axis=1)
    d = moved-v
    cosine = np.einsum('ij,ij->i', c0, c)/(4*a0*a)
    grad = np.linalg.norm(d[edges[:, 0]]-d[edges[:, 1]], axis=1)/length
    return {'finite': bool(np.isfinite(moved).all()), 'degenerate_count': int((a<1e-10).sum()),
            'normal_reversal_count': int((cosine<=0).sum()),
            'area_ratio_range': [float((a/a0).min()), float((a/a0).max())],
            'maximum_edge_gradient': float(grad.max()),
            'maximum_normal_rotation_deg': float(np.degrees(np.arccos(np.clip(cosine, -1, 1))).max()),
            'volume_mm3': float(np.einsum('ij,ij->i', moved[f[:,0]], np.cross(moved[f[:,1]], moved[f[:,2]])).sum()/6),
            'maximum_displacement_mm': float(np.linalg.norm(d,axis=1).max())}


def barycentric(tri, p):
    e1, e2, offset = tri[:,1]-tri[:,0], tri[:,2]-tri[:,0], p-tri[:,0]
    aa=np.einsum('ij,ij->i',e1,e1);bb=np.einsum('ij,ij->i',e1,e2);cc=np.einsum('ij,ij->i',e2,e2)
    ab=np.einsum('ij,ij->i',offset,e1);ac=np.einsum('ij,ij->i',offset,e2)
    det=aa*cc-bb*bb
    x=(ab*cc-ac*bb)/det;y=(ac*aa-ab*bb)/det
    return np.column_stack([1-x-y,x,y])


def run(directories):
    _, arrays=verify_sources()
    manifest=read_json(ROOT/'accepted_inputs.json')
    for name,digest in manifest['evidence_sha256'].items():
        assert sha(ROOT/'evidence'/name)==digest, name
    evidence=ROOT/'evidence'
    accepted=read_json(evidence/'r2_quality_report.json')
    hashes=read_json(evidence/'r2_actual_array_hashes.json')
    previous_runtime=read_json(evidence/'r2_runtime_validation.json')
    assert not accepted['violations']
    fixed=np.load(evidence/'port_fixed_masks.npy')
    assert fixed.sum(axis=1).tolist()==[2793,397,485]
    assert fixed.any(axis=0).sum()==3675
    v, f, d = [arrays['cavity_'+item] for item in ('reference_vertices','faces','displacement')]
    tv, tf, td = [arrays['tissue_'+item] for item in ('reference_vertices','faces','displacement')]
    assert np.all(d[fixed.any(axis=0)]==0)
    exact=np.load(evidence/'coincident_mask.npy');idx=np.load(evidence/'coincident_cavity_vertex.npy')
    remote=np.load(evidence/'remote_anchors.npy')
    assert exact.sum()==139
    np.testing.assert_array_equal(td[exact],d[idx[exact]])
    assert np.all(td[remote]==0)
    pairs=np.load(evidence/'contact_pairs.npy');samples=np.load(evidence/'contact_sample_points.npy')
    bc=barycentric(v[f[pairs[:,0]]],samples);bt=barycentric(tv[tf[pairs[:,1]]],samples)
    relative=np.einsum('ni,nij->nj',bt,td[tf[pairs[:,1]]])-np.einsum('ni,nij->nj',bc,d[f[pairs[:,0]]])
    relative_max=float(np.linalg.norm(relative,axis=1).max())
    assert relative_max<1e-10
    ef=edges_of(tf);five=[]
    for u, baseline in zip(LEVELS,accepted['five_levels']):
        q=geometry(tv,tf,tv+u*td,ef)
        b=baseline['quality_after']
        np.testing.assert_allclose(q['area_ratio_range'],b['area_ratio_range'],rtol=0,atol=2e-12)
        assert abs(q['maximum_edge_gradient']-b['maximum_edge_gradient'])<2e-12
        assert q['finite'] and q['degenerate_count']==0 and q['normal_reversal_count']==0
        assert q['area_ratio_range'][0]>=.8 and q['area_ratio_range'][1]<=1.35 and q['maximum_edge_gradient']<=.2
        assert baseline['cross']['positive_segment_count']==0 and baseline['self']['positive_segment_count']==0
        five.append({'u':u,'tissue_geometry_recomputed':q,'finite_contact_results':{
            'method':'Accepted exhaustive finite-triangle result transferred by exact six-array identity; not a new scan.',
            'cross_positive_segment_count':baseline['cross']['positive_segment_count'],
            'self_positive_segment_count':baseline['self']['positive_segment_count'],
            'self_coplanar_overlap_pair_count':baseline['self']['coplanar_overlap_pair_count'],
            'epsilon_mm':baseline['cross']['finite_acceptance_epsilon_mm']}})
    records=[];runs=[]
    for directory in directories:
        directory=Path(directory).resolve()
        runtime=read_json(directory/'runtime_checks.json')
        assert runtime['camera_unchanged'] and runtime['no_update_without_geometry_change'] and runtime['pause_no_mesh_submission']
        assert runtime['repeated_actual_mesh_restore_exact']
        assert runtime['independent_visibility_ui_verified']
        assert all(r['controller_u']==r['player_u'] for r in runtime['runtime_rows'])
        rows=[]
        for mesh, ref, faces, field in [('cavity',v,f,d),('tissue',tv,tf,td)]:
            n,m=len(ref),len(faces);ref32=(ref-ORIGIN).astype(np.float32)
            for tag,u in [(f'u{int(100*u):03}',u) for u in LEVELS]+[('u037',.37),('reset',0.),('driven',.15625),('restored',0.),('repeat_restored',0.)]:
                raw=(directory/f'{mesh}_{tag}.bin').read_bytes()
                assert len(raw)==n*24+m*12
                p=np.frombuffer(raw,dtype='<f4',count=n*3).reshape(-1,3)
                normals=np.frombuffer(raw,dtype='<f4',offset=n*12,count=n*3).reshape(-1,3)
                ids=np.frombuffer(raw,dtype='<i4',offset=n*24).reshape(-1,3)
                expected=ref32+np.float32(u)*field.astype(np.float32)
                np.testing.assert_array_equal(p,expected)
                if u==0.0:
                    initial=(directory/f'{mesh}_u000.bin').read_bytes()
                    assert raw[:n*12]==initial[:n*12], 'Reference reset differs in float32 bits'
                np.testing.assert_array_equal(ids,faces[:,::-1])
                assert np.isfinite(normals).all()
                assert np.abs(np.linalg.norm(normals,axis=1)-1).max()<2e-6
                sums=np.zeros((n,3));c=cross_of(p.astype(float),faces)
                for corner in range(3): np.add.at(sums,faces[:,corner],c)
                sums/=np.linalg.norm(sums,axis=1)[:,None]
                cosine=np.einsum('ij,ij->i',sums,normals)/np.linalg.norm(normals,axis=1)
                angle=float(np.degrees(np.arccos(np.clip(cosine,-1,1))).max())
                assert angle<.05
                row={'renderer':runtime['renderer'],'mesh':mesh,'tag':tag,'u':u,'positions_bit_exact':True,
                     'indices_exact':True,'maximum_normal_angle_deg':angle}
                if mesh=='cavity':
                    np.testing.assert_array_equal(p[fixed.any(axis=0)],ref32[fixed.any(axis=0)])
                    row['fixed_3675_bit_exact']=True
                if tag.startswith('u') and tag!='u037':
                    before=hashes[f'{mesh}_{tag}']
                    assert hashlib.sha256(raw[:n*12]).hexdigest()==before['positions_sha256']
                    assert hashlib.sha256(raw[n*24:]).hexdigest()==before['indices_sha256']
                    row['bit_exact_to_actual_approved_R2']=True
                    if mesh=='tissue':
                        q=geometry(ref32.astype(float),faces,p.astype(float),ef)
                        assert q['maximum_edge_gradient']<=.2 and .8<=q['area_ratio_range'][0]<=q['area_ratio_range'][1]<=1.35
                        assert q['degenerate_count']==0 and q['normal_reversal_count']==0
                        row['actual_float32_quality']=q
                records.append(row);rows.append(row)
        # Original Float32 contact results remain identical; include existing contact, not just crossings.
        inherited=[]
        for review in previous_runtime['float32_cross_review']:
            assert review['positive_segment_count']==0
            inherited.append({k:review[k] for k in ('fill','positive_segment_count','coplanar_overlap_pair_count','coplanar_pair_area_sum_mm2','raw_candidate_count')})
        timing=np.array([r['update_ms'] for r in runtime['timing_samples']])
        runs.append({'directory':str(directory.relative_to(PROJECT)),'renderer':runtime['renderer'],
                     'device':runtime['device'],'snapshot_count':len(rows),
                     'single_update_ms':{'minimum':float(timing.min()),'mean':float(timing.mean()),'maximum':float(timing.max())},
                     'exceeds_30fps_frame_budget':bool(timing.mean()>1000/30),
                     'float32_contact_review_inherited_by_actual_array_identity':inherited})
    protected=[];authorized=[];unapproved=[]
    acknowledgement_path=ROOT/'verification/authorized_workspace_changes.json'
    acknowledgements=read_json(acknowledgement_path)['changes'] if acknowledgement_path.exists() else {}
    if (DIAG/'protected_before.json').exists():
        for name,digest in read_json(DIAG/'protected_before.json').items():
            if not (REPO/name).is_file() or sha(REPO/name)!=digest:
                protected.append(name)
                acknowledgement=acknowledgements.get(name,{})
                if acknowledgement.get('before_sha256')==digest and acknowledgement.get('after_sha256')==sha(REPO/name):
                    # Only the separately user-confirmed exact visibility edit is recognized.
                    import re
                    reconstructed,count=re.subn(rb'(\[node name="TissueReference"[^\r\n]*\]\r?\n)visible = false\r?\n',rb'\1',(REPO/name).read_bytes())
                    if name=='godot_sim/irrigation_asset_check.tscn' and count==1 and hashlib.sha256(reconstructed).hexdigest()==digest:
                        authorized.append(name)
                    else: unapproved.append(name)
                else: unapproved.append(name)
    report={'status':('P2_1_P2_2_BLOCKED_PROTECTED_FILE_DIFF' if unapproved else 'P2_1_P2_2_CORRECTNESS_VERIFIED_PERFORMANCE_UNRESOLVED'),'authority_hashes':AUTHORITY,
            'six_arrays_frozen_byte_exact':True,'five_levels':five,'runtime_records':records,'runs':runs,
            'contact_constraints':{'original_samples':len(samples),'maximum_relative_displacement_mm':relative_max,
                'exact_coincident_vertices':int(exact.sum()),'remote_vertices':int(remote.sum()),'remote_exact_zero':True},
            'fixed_ports':{'BLADDER':2793,'IN_01':397,'IN_02':485,'unique_total':3675,'all_u_exact_zero':True},
            'protected_changed':protected,'authorized_user_visibility_changes':authorized,'unapproved_protected_changes':unapproved,
            'protected_files_checked':len(read_json(DIAG/'protected_before.json')) if (DIAG/'protected_before.json').exists() else None,
            'continuous_geometry':accepted['continuous'],
            'limitations':['Not a fresh all-pairs collision scan. Six authoritative arrays and actual five-level Godot positions/indices exactly match accepted R2; its finite checks therefore transfer unchanged.',
                           'Original B_24 cavity history remains; no new topology or field is introduced.',
                           'Existing float32 coplanar contact pairs are preserved, not declared new penetrations or erased.',
                           'No full FPS/P95 benchmark. CPU updates exceed 33.3ms; smooth 30fps is NOT achieved.',
                           'No proven anatomical assignments for F03/F04, true wall thickness or physiological calibration.']}
    DIAG.mkdir(parents=True,exist_ok=True)
    write_json(DIAG/'validation_report.json',report)
    print(json.dumps({'status':report['status'],'snapshots':len(records),'runs':runs,'protected_changes':protected},indent=2))
    assert not unapproved,unapproved
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directories',nargs='+',type=Path)
    run(parser.parse_args().directories)
