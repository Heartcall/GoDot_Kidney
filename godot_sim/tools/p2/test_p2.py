"""P2 packaging, geometry and actual-engine regression. Run after Godot captures."""
import contextlib
import io
import unittest
from unittest.mock import patch
from prepare_runtime import *
from validate_runtime import run


class P2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths,cls.a=verify_sources()
        cls.manifest=read_json(ROOT/'accepted_inputs.json')
    def test_01_six_hashes_from_authority_guide(self):
        guide=(REPO/'docs/kidney_irrigation_p2_guide.md').read_text(encoding='utf8')
        for key,digest in AUTHORITY.items():
            self.assertIn(digest,guide);self.assertEqual(sha(self.paths[key]),digest)
    def test_02_human_acceptance_record(self):
        self.assertEqual(self.manifest['human_acceptance']['date'],'2026-10-14')
        self.assertEqual(self.manifest['human_acceptance']['status'],'USER_ACCEPTED_ENGINEERING_GEOMETRY')
    def test_03_rebuild_twice_is_byte_identical(self):
        files=[ROOT/'accepted_inputs.json']+list(RUNTIME.glob('*'))
        before={p.name:sha(p) for p in files if p.is_file()}
        with contextlib.redirect_stdout(io.StringIO()): build();build()
        after={p.name:sha(p) for p in files if p.is_file()}
        self.assertEqual(before,after)
        write_json(DIAG/'rebuild_verification.json',{'byte_identical':True,'sha256':before,'builds':2})
    def test_04_missing_or_changed_authority_stops(self):
        with patch('prepare_runtime.approved_path',return_value=DIAG/'__missing_authority.npy'):
            with self.assertRaisesRegex(ValueError,'STOP'): verify_sources(True)
        with patch('prepare_runtime.sha',return_value='0'*64):
            with self.assertRaisesRegex(ValueError,'STOP'): verify_sources(False)
    def test_05_binary_layout_exact(self):
        for mesh in ('cavity','tissue'):
            raw=(RUNTIME/(mesh+'.bin')).read_bytes();n,m=struct.unpack('<II',raw[8:16])
            self.assertEqual(raw[:8],b'P2DG0001');self.assertEqual(len(raw),16+n*24+m*12)
            ref=np.frombuffer(raw,dtype='<f4',offset=16,count=n*3).reshape(-1,3)
            field=np.frombuffer(raw,dtype='<f4',offset=16+n*12,count=n*3).reshape(-1,3)
            faces=np.frombuffer(raw,dtype='<i4',offset=16+n*24).reshape(-1,3)
            np.testing.assert_array_equal(ref,(self.a[mesh+'_reference_vertices']-ORIGIN).astype('float32'))
            np.testing.assert_array_equal(field,self.a[mesh+'_displacement'].astype('float32'))
            np.testing.assert_array_equal(faces,self.a[mesh+'_faces'][:,::-1])
    def test_06_no_accumulated_vertex_drift(self):
        for mesh in ('cavity','tissue'):
            ref=self.a[mesh+'_reference_vertices'];field=self.a[mesh+'_displacement']
            for _ in range(8):
                for u in (0,.17,.5,1,.64,.25,0):
                    current=ref+u*field
                np.testing.assert_array_equal(current,ref)
    def test_07_godot_controller_real_tests(self):
        result=read_json(DIAG/'controller_tests.json')
        self.assertFalse(result['failures']);self.assertGreaterEqual(len(result['checks']),70)
        self.assertTrue(all(r['passed'] for r in result['checks']))
    def test_08_no_ignored_input_or_r1_in_player(self):
        source=(PROJECT/'scripts/p2/deformation_player.gd').read_text(encoding='utf8')
        self.assertNotIn('analysis/',source);self.assertNotIn('R1',source)
        self.assertNotIn('_physics_process',source)
        self.assertIn('value == filling',source)
    def test_09_safe_opaque_shader(self):
        source=(PROJECT/'shaders/audit_section.gdshader').read_text(encoding='utf8')
        self.assertNotIn('ALPHA',source);self.assertNotIn('blend_mix',source)
    def test_10_all_runtime_geometry_contacts_and_fixed(self):
        dirs=[DIAG/'godot_forward']
        if (DIAG/'godot_compatibility/runtime_checks.json').exists(): dirs.append(DIAG/'godot_compatibility')
        with contextlib.redirect_stdout(io.StringIO()): report=run(dirs)
        self.assertTrue(report['six_arrays_frozen_byte_exact']);self.assertFalse(report['unapproved_protected_changes'])
        self.assertEqual(report['protected_changed'],report['authorized_user_visibility_changes'])
        self.assertEqual(len(report['five_levels']),5)
        self.assertEqual(report['fixed_ports']['unique_total'],3675)
    def test_11_runtime_assets_not_git_ignored(self):
        result=subprocess.run(['git','check-ignore','--stdin'],cwd=REPO,
                              input='\n'.join(str(p.relative_to(REPO)) for p in RUNTIME.iterdir()),text=True,capture_output=True)
        self.assertEqual(result.returncode,1,result.stdout)
    def test_12_frozen_evidence_identity(self):
        for name,digest in self.manifest['evidence_sha256'].items():
            self.assertEqual(sha(ROOT/'evidence'/name),digest)
    def test_13_real_process_live_playback(self):
        report=read_json(DIAG/'live/live_smoke.json')
        self.assertTrue(report['passed']);self.assertTrue(report['automatic_process_used'])
        self.assertTrue(report['pause_u_stable_and_no_mesh_update'])
        self.assertTrue(all(x['u']==x['player_u'] for x in report['observations']))
        for name in ('cavity','tissue'):
            n=len(self.a[name+'_reference_vertices'])
            actual=np.frombuffer((DIAG/'live'/f'{name}_live_restored.bin').read_bytes(),dtype='<f4',count=n*3).reshape(-1,3)
            np.testing.assert_array_equal(actual,(self.a[name+'_reference_vertices']-ORIGIN).astype('float32'))
    def test_14_isolated_project_without_analysis_cache(self):
        report=read_json(DIAG/'clean_checkout/verification/runtime_checks.json')
        self.assertTrue(report['camera_unchanged'])
        self.assertTrue(report['no_update_without_geometry_change'])
        self.assertFalse((DIAG/'clean_checkout/analysis').exists())
        inputs=read_json(DIAG/'clean_checkout_inputs.json')
        self.assertFalse(inputs['source_analysis_files_copied'])
        for name in inputs['files']:
            result=subprocess.run(['git','check-ignore',name],cwd=PROJECT,capture_output=True)
            self.assertEqual(result.returncode,1,name)


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(P2Tests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    write_json(DIAG/'python_tests.json',{'tests_run':result.testsRun,'successful':result.wasSuccessful(),
                                      'failures':len(result.failures),'errors':len(result.errors)})
    raise SystemExit(0 if result.wasSuccessful() else 1)
