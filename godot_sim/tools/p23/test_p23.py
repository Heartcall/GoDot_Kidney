"""P2.3 regression tests. All results are written to the new P2.3 directory."""
import unittest
from check_results import *
from summarize_performance import summarize


class P23Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result=check_results();cls.perf=summarize()
    def test_accepted_stage_is_recorded_separately(self):
        r=read_json(STAGE/'p21_p22_acceptance.json')
        self.assertEqual(r['date'],'2026-10-14')
        self.assertEqual(r['status'],'USER_ACCEPTED_FUNCTIONAL_BASELINE')
        self.assertIn('no obvious stutter',r['subjective_experience'])
        self.assertIn('NOT_YET_PROVEN',r['quantitative_30fps_status'])
    def test_all_six_authorities_and_old_manifest(self):
        _,a=verify_sources();self.assertEqual(len(a),6)
        self.assertTrue(self.result['manifest_unchanged'])
    def test_controller_reused_exactly(self):
        self.assertTrue(self.result['controller_unchanged'])
        self.assertEqual(self.result['controller_checks'],74)
    def test_panel_separated_from_geometry(self):
        source=(PROJECT/'scripts/p2/irrigation_panel.gd').read_text(encoding='utf8')
        for forbidden in ['ArrayMesh','ARRAY_VERTEX','set_filling','var filling','displacement']:
            self.assertNotIn(forbidden,source)
        self.assertIn('set_value_no_signal',source)
    def test_complete_panel_state_and_layout_checks(self):
        self.assertEqual(len(self.result['ui_runs']),2)
        for r in self.result['ui_runs']:
            self.assertGreaterEqual(r['checks'],83);self.assertFalse(r['failures'])
            self.assertEqual(len(r['layout']),4);self.assertTrue(all(x['valid'] for x in r['layout']))
    def test_actual_32_meshes_exact_and_fixed(self):
        self.assertEqual(len(self.result['actual_mesh_records']),32)
        self.assertEqual(self.result['fixed_cavity_vertices'],3675)
        self.assertTrue(all(x['position_bits_exact'] and x['indices_exact'] for x in self.result['actual_mesh_records']))
    def test_all_five_levels_and_contact_constraints(self):
        self.assertEqual([r['u'] for r in self.result['five_levels']],[0,.25,.5,.75,1])
        self.assertEqual(self.result['contact_samples'],3840)
        self.assertEqual(self.result['coincident_vertices'],139)
        self.assertLess(self.result['contact_relative_displacement_max_mm'],1e-10)
    def test_normal_algorithm_is_unchanged(self):
        a=(PROJECT/'scripts/p2/deformation_player.gd').read_text(encoding='utf8')
        b=(STAGE/'baseline/deformation_player.gd').read_text(encoding='utf8')
        def normals(s):return s[s.index('func _normals('):s.index('func set_filling(')]
        self.assertEqual(normals(a),normals(b))
    def test_readback_removed_only_from_normal_playback(self):
        source=(PROJECT/'scripts/p2/deformation_player.gd').read_text(encoding='utf8')
        update=source[source.index('func set_filling('):source.index('func set_section(')]
        self.assertNotIn('surface_get_arrays',update)
        self.assertIn('surface_get_arrays',source[source.index('func export_actual('):])
        self.assertIn('data[name]["colors"]',update)
    def test_actual_continuous_legs_and_components(self):
        for name in ['final_forward','final_compatibility']:
            raw=read_json(OUT/name/'continuous_raw.json')
            self.assertEqual(raw['readbacks_during_measured_legs'],0)
            self.assertEqual([l['phase'] for l in raw['legs']],['fill','drain'])
            self.assertEqual(raw['player_code_sha256'],sha(PROJECT/'scripts/p2/deformation_player.gd'))
            for leg in raw['legs']:
                self.assertAlmostEqual(leg['game_seconds'],6)
                self.assertGreater(len(leg['frames']),100)
                for frame in leg['frames']:
                    self.assertTrue(frame['sync']);self.assertGreater(frame['wall_frame_ms'],0)
                    self.assertLessEqual(sum(frame['update_phases_ms'].values()),frame['update_ms']+.1)
    def test_baseline_and_early_optimized_measurements_preserved(self):
        names=[r['name'] for r in self.perf['runs']]
        for name in ['baseline_forward','baseline_compatibility','optimized_forward','optimized_compatibility','final_forward','final_compatibility']:
            self.assertIn(name,names)
        for name in ['baseline_forward','baseline_compatibility']:
            self.assertGreater(read_json(OUT/name/'continuous_raw.json')['readbacks_during_measured_legs'],0)
    def test_performance_failure_is_not_mislabeled_pass(self):
        self.assertFalse(self.perf['all_final_runs_meet_stable_30fps'])
        self.assertIn('PERFORMANCE_BELOW_30FPS',self.result['status'])
    def test_protected_sources_and_authorized_visibility(self):
        self.assertFalse(self.result['protected']['unexpected_changes'])
        self.assertTrue(self.result['protected']['user_visibility_setting_preserved'])
        self.assertEqual(set(self.result['protected']['authorized_code_changes']),set(ALLOWED))


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(P23Tests))
    write_json(OUT/'python_tests.json',{'tests':result.testsRun,'passed':result.wasSuccessful(),'failures':len(result.failures),'errors':len(result.errors)})
    raise SystemExit(0 if result.wasSuccessful() else 1)
