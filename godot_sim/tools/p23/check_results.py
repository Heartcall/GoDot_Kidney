"""P2.3 geometry/state/protected-input regression; no writes to P2 history."""
from freeze_baseline import *
from validate_runtime import geometry,edges_of,barycentric


def freeze_normal_hashes():
    path=STAGE/'baseline/accepted_normal_hashes.json'
    if path.exists():return
    result={}
    for mesh,n in [('cavity',25024),('tissue',155904)]:
        for tag in [0,25,50,75,100]:
            raw=(DIAG/'godot_forward'/f'{mesh}_u{tag:03}.bin').read_bytes()
            result[f'{mesh}_u{tag:03}']=hashlib.sha256(raw[n*12:n*24]).hexdigest()
    write_json(path,result)


def check_results():
    _,a=verify_sources()
    acceptance=read_json(STAGE/'p21_p22_acceptance.json')
    assert sha(ROOT/'accepted_inputs.json')==acceptance['input_manifest_sha256']
    for name,digest in acceptance['baseline_sha256'].items():assert sha(STAGE/'baseline'/name)==digest
    assert sha(PROJECT/'scripts/p2/irrigation_controller.gd')==acceptance['baseline_sha256']['irrigation_controller.gd']
    evidence=ROOT/'evidence'
    oldquality=read_json(evidence/'r2_quality_report.json');runtime_hashes=read_json(evidence/'r2_actual_array_hashes.json')
    normal_hashes=read_json(STAGE/'baseline/accepted_normal_hashes.json')
    fixed=np.load(evidence/'port_fixed_masks.npy').any(axis=0)
    assert fixed.sum()==3675
    v,f,d=[a['cavity_'+x] for x in ('reference_vertices','faces','displacement')]
    tv,tf,td=[a['tissue_'+x] for x in ('reference_vertices','faces','displacement')]
    exact=np.load(evidence/'coincident_mask.npy');idx=np.load(evidence/'coincident_cavity_vertex.npy');remote=np.load(evidence/'remote_anchors.npy')
    np.testing.assert_array_equal(td[exact],d[idx[exact]])
    assert exact.sum()==139 and np.all(td[remote]==0) and np.all(d[fixed]==0)
    pairs=np.load(evidence/'contact_pairs.npy');points=np.load(evidence/'contact_sample_points.npy')
    bc=barycentric(v[f[pairs[:,0]]],points);bt=barycentric(tv[tf[pairs[:,1]]],points)
    relative=np.einsum('ni,nij->nj',bt,td[tf[pairs[:,1]]])-np.einsum('ni,nij->nj',bc,d[f[pairs[:,0]]])
    relative_max=float(np.linalg.norm(relative,axis=1).max());assert relative_max<1e-10
    ef=edges_of(tf);levels=[]
    for u,old in zip([0,.25,.5,.75,1],oldquality['five_levels']):
        q=geometry(tv,tf,tv+u*td,ef)
        np.testing.assert_allclose(q['area_ratio_range'],old['quality_after']['area_ratio_range'],atol=2e-12,rtol=0)
        assert q['maximum_edge_gradient']<=.2 and .8<=q['area_ratio_range'][0] and q['area_ratio_range'][1]<=1.35
        assert q['degenerate_count']==0 and q['normal_reversal_count']==0
        assert old['cross']['positive_segment_count']==0 and old['self']['positive_segment_count']==0
        levels.append({'u':u,'recomputed_tissue_quality':q,'inherited_confirmed_crossings':0,'inherited_confirmed_self_crossings':0})
    records=[];ui=[]
    for folder in ['final_regression_forward','final_regression_compatibility']:
        directory=OUT/folder;reg=read_json(directory/'ui_regression.json');assert not reg['failures']
        ui.append({'run':folder,'checks':len(reg['checks']),'failures':reg['failures'],'layout':reg['layout']})
        for mesh,ref,faces,field in [('cavity',v,f,d),('tissue',tv,tf,td)]:
            n=len(ref);ref32=(ref-ORIGIN).astype('float32')
            for tag,u in [(f'u{x:03}',x/100) for x in [0,25,50,75,100,37]]+[('reset',0),('restored',0)]:
                raw=(directory/f'{mesh}_{tag}.bin').read_bytes()
                p=np.frombuffer(raw,dtype='<f4',count=n*3).reshape(-1,3)
                normals=np.frombuffer(raw,dtype='<f4',count=n*3,offset=n*12).reshape(-1,3)
                ids=np.frombuffer(raw,dtype='<i4',offset=n*24).reshape(-1,3)
                expected=ref32+np.float32(u)*field.astype('float32')
                np.testing.assert_array_equal(p,expected);np.testing.assert_array_equal(ids,faces[:,::-1])
                assert np.isfinite(normals).all() and np.abs(np.linalg.norm(normals,axis=1)-1).max()<2e-6
                if mesh=='cavity':np.testing.assert_array_equal(p[fixed],ref32[fixed])
                record={'run':folder,'mesh':mesh,'tag':tag,'u':u,'position_bits_exact':True,'indices_exact':True,'fixed_exact':True if mesh=='cavity' else None}
                if tag in [f'u{x:03}' for x in [0,25,50,75,100]]:
                    baseline=runtime_hashes[f'{mesh}_{tag}']
                    assert hashlib.sha256(raw[:n*12]).hexdigest()==baseline['positions_sha256']
                    assert hashlib.sha256(raw[n*24:]).hexdigest()==baseline['indices_sha256']
                    assert hashlib.sha256(raw[n*12:n*24]).hexdigest()==normal_hashes[f'{mesh}_{tag}']
                    record['actual_positions_indices_normals_match_accepted']=True
                    if mesh=='tissue':
                        q=geometry(ref32.astype(float),faces,p.astype(float),ef)
                        assert q['maximum_edge_gradient']<=.2 and .8<=q['area_ratio_range'][0] and q['area_ratio_range'][1]<=1.35
                        assert not q['degenerate_count'] and not q['normal_reversal_count']
                        record['actual_float32_quality']=q
                if u==0:assert raw[:n*12]==(directory/f'{mesh}_u000.bin').read_bytes()[:n*12]
                records.append(record)
    before=read_json(STAGE/'protected_before.json');changed=[];metadata_changes=[];unexpected=[]
    visibility=read_json(STAGE/'visibility_preservation.json')
    for name,digest in before.items():
        if not (REPO/name).is_file() or sha(REPO/name)!=digest:
            if name in acceptance['allowed_p23_code_changes']:
                changed.append(name)
            elif name==visibility['path'] and digest==visibility['before_sha256'] and sha(REPO/name)==visibility['after_sha256']:
                import re
                reconstructed,count=re.subn(rb'(\[node name="TissueReference"[^\r\n]*\]\r?\n)visible = false\r?\n',rb'\1',(REPO/name).read_bytes())
                assert count==1 and hashlib.sha256(reconstructed).hexdigest()==digest
                metadata_changes.append(name)
            else:unexpected.append(name)
    assert not unexpected,unexpected
    protected={'files':len(before),'unchanged':len(before)-len(changed)-len(metadata_changes),'authorized_code_changes':changed,
               'authorized_visibility_restoration':metadata_changes,'unexpected_changes':unexpected,
               'user_visibility_setting_preserved':sha(PROJECT/'irrigation_asset_check.tscn')==visibility['after_sha256']}
    assert protected['user_visibility_setting_preserved']
    controller=read_json(OUT/'controller_tests.json');assert not controller['failures']
    result={'status':'P23_FUNCTION_AND_GEOMETRY_PASSED_PERFORMANCE_BELOW_30FPS_PENDING_HUMAN_ACCEPTANCE',
        'six_authority_hashes':AUTHORITY,'manifest_unchanged':True,'controller_unchanged':True,'ui_runs':ui,
        'controller_checks':len(controller['checks']),'actual_mesh_records':records,'five_levels':levels,
        'fixed_cavity_vertices':3675,'coincident_vertices':139,'remote_vertices':int(remote.sum()),
        'contact_samples':len(points),'contact_relative_displacement_max_mm':relative_max,'protected':protected,
        'finite_contact_validation_method':'Same six authoritative arrays AND five-level actual ArrayMesh position/index hashes equal accepted R2. Inherited finite-triangle scan unchanged; no new all-pairs scan or tolerance change.',
        'inherited_continuous_area_orientation':oldquality['continuous'],
        'limits':['Continuous collision freedom, F03/F04 anatomy, true wall thickness and physiological calibration remain unverified.',
                  'B_24 original cavity record retained. Actual float32 coplanar contacts remain baseline contacts, not reclassified or removed.']}
    write_json(OUT/'regression_report.json',result)
    print('P23 regression passed;',len(records),'actual meshes;',len(before),'protected files;',changed)
    return result


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--freeze-normal-hashes',action='store_true');args=p.parse_args()
    if args.freeze_normal_hashes:freeze_normal_hashes()
    else:check_results()
