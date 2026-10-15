from n1_nested_review import *
import unittest

class NestedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=read_json(OUT/'review_data.json');cls.a=SectionAnalyzer()
        cls.old=json.loads(gzip.decompress((ROOT/'sections.json.gz').read_bytes()))
    def test_protected_sources_and_history_unchanged(self):self.assertGreaterEqual(protect(),2335)
    def test_human_acceptance_does_not_promote_net_area_or_partition(self):
        h=read_json(OUT/'human_review_2026_10_15_v1.json');self.assertTrue(h['N1_engineering_tools_and_existing_data_accepted'])
        self.assertFalse(h['outer_area_approved_as_effective_net_area']);self.assertFalse(h['candidate_regional_volumes_approved_as_final_anatomical_partition'])
    def test_D2_volume_and_limits_unchanged(self):
        volume=signed_volume(self.a.v,self.a.f)/1000
        self.assertAlmostEqual(volume,self.data['V_reference_D2_mL'],places=12);self.assertIsNone(self.data['normal_V_min_mL']);self.assertFalse(self.data['N2_started'])
    def test_all_exact_original_loops_and_source_ids_preserved(self):
        rows={r['id']:r for r in self.old['stations']}
        for case in self.data['cases']:
            old=rows[case['id']];self.assertEqual(len(case['loops']),len(old['loops']))
            for loop,source in zip(case['loops'],old['loops']):
                self.assertEqual(loop['ring_positions_mm'],source['ring_positions_mm']);self.assertEqual(loop['source_face_ids'],source['segments_source_face_ids'])
                np.testing.assert_array_equal(self.a.source[loop['D2_face_ids']],loop['source_face_ids'])
    def test_mesh_orientation_is_consistent_and_inner_negative(self):
        for case in self.data['cases']:
            for loop in case['loops']:
                low,high=loop['segment_orientation_cosine_min_max'];self.assertTrue(low>0 or high<0);self.assertLess(loop['plane_max_residual_mm'],1e-10)
            for item in case['nesting']:
                self.assertLess(case['loops'][item['inner_loop']]['mesh_outward_oriented_signed_area_mm2'],0)
                self.assertGreater(case['loops'][item['outer_loop']]['mesh_outward_oriented_signed_area_mm2'],0)
    def test_finite_ring_containment_without_touching(self):
        for case in self.data['cases']:
            for item in case['nesting']:
                r=item['relation'];self.assertTrue(r['second_all_vertices_inside_first']);self.assertEqual(r['finite_boundary_crossings'],0);self.assertGreater(r['minimum_boundary_distance_mm'],1e-6)
    def test_independent_winding_and_ray_classify_inner_as_exterior(self):
        for case in self.data['cases']:
            for item in case['nesting']:
                p=item['inner_probes'];self.assertTrue(p['all_winding_outside']);self.assertTrue(p['all_ray_outside']);self.assertGreater(p['minimum_absolute_distance_mm'],1e-6)
                self.assertEqual(item['classification'],'ORIENTED_D2_SLICE_EXTERIOR_POCKET_CONFIRMED')
    def test_off_plane_face_chains_are_true_surface_adjacency(self):
        graph=trimesh.Trimesh(self.a.v,self.a.f,process=False).face_adjacency
        edges={tuple(sorted(x)) for x in graph.tolist()}
        for case in self.data['cases']:
            for item in case['nesting']:
                ids=item['surface_shortest_face_chain_D2'];self.assertTrue(all(tuple(sorted(x)) in edges for x in zip(ids,ids[1:])))
                np.testing.assert_array_equal(self.a.source[ids],item['surface_shortest_face_chain_source'])
                self.assertGreater(max(abs(np.array(item['bridge_centroid_plane_distance_mm']))),1e-4)
    def test_no_branch_net_area_computed_or_promoted(self):
        for case in self.data['cases']:
            self.assertEqual(case['status'],'MULTIRING_WITH_HOLE_UNRESOLVED');self.assertIsNone(case['effective_branch_area_mm2']);self.assertFalse(case['outer_minus_inner_area_computed'])
            for row in case['neighbors']:self.assertIsNone(row['effective_branch_area_mm2'])
    def test_adjacent_planes_include_fine_offsets_and_central_match(self):
        for case in self.data['cases']:
            self.assertEqual(len(case['neighbors']),26)
            for kind in ['FIXED_NORMAL_PARALLEL','ALONG_PATH_LOCAL_NORMAL']:
                rows=[r for r in case['neighbors'] if r['kind']==kind];self.assertEqual(len(rows),13)
                zero=next(r for r in rows if r['offset_mm']==0)
                for loop,central in zip(zero['loops'],case['loops']):np.testing.assert_allclose(loop['ring_positions_mm'],central['ring_positions_mm'],atol=1e-12,rtol=0)
    def test_local_finite_crossings_and_feature_false_candidates(self):
        for case in self.data['cases']:
            r=case['local_finite_contacts'];self.assertFalse(r['confirmed_invalid_pairs']);self.assertTrue(all(v==0 for v in r['nonadjacent_positive_intersection_count_by_tolerance'].values()))
        self.assertEqual(len(self.data['cases'][0]['local_finite_contacts']['shared_point_numerical_candidates']),2)
    def test_shared_vertex_true_crossing_not_ignored(self):
        class A:pass
        a=A();a.v=np.array([[0,0,0],[2,0,0],[0,2,0],[1,1,-1],[1,1,1]],float);a.f=np.array([[0,1,2],[0,3,4]]);a.source=np.arange(2)
        self.assertGreater(len(local_crossings(a,np.arange(2))['confirmed_invalid_pairs']),0)
    def test_winding_on_closed_reference_primitive(self):
        mesh=trimesh.creation.icosphere(subdivisions=2,radius=1)
        self.assertAlmostEqual(winding(mesh.vertices,mesh.faces,np.zeros(3)),1,places=12)
        self.assertAlmostEqual(winding(mesh.vertices,mesh.faces,np.array([2,0,0.])),0,places=12)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NestedTests))
    write_json(OUT/'python_tests.json',{'run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'details':[str(x) for x in result.failures+result.errors]})
    sys.exit(0 if result.wasSuccessful() else 1)
