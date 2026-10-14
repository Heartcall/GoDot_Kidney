"""Unit/consistency checks for the read-only analysis, not physiological validation."""
import unittest,contextlib,io
from audit_reference_capacity import *


class CapacityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r=read_json(OUT/'reference_capacity_audit.json');_,cls.a=verify_sources()
    def test_unit_cube_translation_and_sign(self):
        m=trimesh.creation.box(extents=[1.,1.,1.])
        self.assertAlmostEqual(signed_volume(m.vertices,m.faces),1.,places=12)
        self.assertAlmostEqual(signed_volume(m.vertices+1000,m.faces),1.,places=12)
        self.assertAlmostEqual(signed_volume(m.vertices,m.faces[:,::-1]),-1.,places=12)
    def test_tetrahedron_known_volume(self):
        v=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]],float)
        f=np.array([[0,2,1],[0,1,3],[0,3,2],[1,2,3]])
        self.assertAlmostEqual(signed_volume(v,f),1/6,places=12)
    def test_length_scale_cubes_volume(self):
        m=trimesh.creation.box();self.assertAlmostEqual(signed_volume(m.vertices*1.3,m.faces),1.3**3,places=12)
    def test_reference_closed_winding_and_units(self):
        q=self.r['reference_closed_mesh']
        self.assertTrue(q['watertight'] and q['winding_consistent'])
        self.assertEqual(q['boundary_edges']+q['nonmanifold_edges']+q['degenerate_triangles'],0)
        self.assertEqual(q['face_components'],1)
        self.assertAlmostEqual(q['signed_volume_mm3']/1000,q['signed_volume_mL'],places=12)
    def test_independent_flux_and_origin_invariance(self):
        q=self.r['reference_closed_mesh']
        self.assertLess(q['numerical_spread_mm3'],3e-6)
        np.testing.assert_allclose(q['three_axis_flux_volumes_mm3'],q['signed_volume_mm3'],atol=1e-8,rtol=0)
    def test_legacy_volume_is_cubic_and_not_physiological_max(self):
        c=self.r['legacy_debug_volume_polynomial_mm3'];self.assertGreater(abs(c[2]),1)
        for row in self.r['legacy_debug_volume_levels']:
            u=row['legacy_u'];self.assertAlmostEqual(sum(c[k]*u**k for k in range(4)),row['closed_mesh_volume_mm3'],places=7)
        self.assertIsNone(self.r['target_status']['V_max_physiological_mL'])
    def test_artificial_additivity_is_not_anatomical_capacity(self):
        self.assertLess(abs(self.r['proxy_additivity_error_mm3']),1e-7)
        self.assertTrue(all(not p['effective_capacity_use_allowed'] for p in self.r['artificial_distal_proxies']))
        self.assertIsNone(self.r['target_status']['V_reference_effective_mL'])
    def test_bad_port_closure_is_reported_not_promoted(self):
        ports={p['id']:p for p in self.r['artificial_distal_proxies']}
        self.assertFalse(ports['BLADDER']['centroid_fan_would_be_star_shaped'])
        self.assertEqual(ports['IN_01']['alternative_ear_cap_test']['status'],'REJECTED_SOURCE_CAP_INDEX_CONFLICT')
        self.assertIsNone(self.r['target_status']['V_min_physiological_mL'])
    def test_simple_concave_ear_clipping_and_crossed_ring_rejection(self):
        xy=np.array([[0,0],[2,0],[2,2],[1,1],[0,2]],float)
        triangles=triangulate_ring(list(range(5)),xy);self.assertEqual(len(triangles),3)
        with self.assertRaises(ValueError):triangulate_ring(list(range(4)),np.array([[0,0],[2,2],[0,2],[2,0]],float))
    def test_cached_b24_has_finite_gap_not_a_confirmed_cross(self):
        b=self.r['historical_B24_targeted_review']
        self.assertGreater(b['finite_feature_distance_mm'],.12)
        self.assertEqual(b['positive_finite_segment_mm'],0)
        self.assertFalse(any(b['tolerance_sensitivity'].values()))
    def test_all_accepted_input_hashes_and_protected_files(self):
        verify_sources()
        self.assertFalse(read_json(OUT/'protected_after.json')['changed'])
        for name,digest in read_json(OUT/'protected_before.json').items():self.assertEqual(sha(REPO/name),digest,name)
    def test_repeat_audit_is_byte_identical(self):
        before=sha(OUT/'reference_capacity_audit.json')
        with contextlib.redirect_stdout(io.StringIO()):audit()
        self.assertEqual(sha(OUT/'reference_capacity_audit.json'),before)


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CapacityTests))
    write_json(OUT/'tests.json',{'tests':result.testsRun,'passed':result.wasSuccessful(),'failures':len(result.failures),'errors':len(result.errors),
                              'scope':'Numerical accounting and source preservation only, not physiological validation.'})
    raise SystemExit(0 if result.wasSuccessful() else 1)
