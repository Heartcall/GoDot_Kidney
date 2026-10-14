"""N0 feedback scope and fixed-only C11 refinement regression."""
from n0_closeout import *
import unittest,contextlib,io

class CloseoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _,cls.a=verify_sources();cls.review=read_json(OUT/'human_review_2026_10_14_v1.json');cls.proof=read_json(OUT/'refinement_proof.json')
        cls.row=read_json(OUT/'domains/C11_R1_IN02_fixed_collar/candidate.json');cls.inventory=read_json(OUT/'C11_retained_structure_inventory.json')
    def test_history_and_all_sources_unchanged(self):self.assertGreaterEqual(protect(),1917);verify_sources()
    def test_human_statuses_not_expanded_to_anatomical_acceptance(self):
        r=self.review['candidate_statuses'];self.assertEqual(r['C11_inlet_distal_control']['status'],'VISUAL_REVIEW_PASSED_D2_PENDING')
        self.assertEqual(r['C06_near_BASE']['status'],'REJECTED_BY_USER_NATURAL_WALL_REMOVAL');self.assertFalse(self.review['D2_approved'])
        for code in ['C07','C08','C09','C10']:
            record=next(value for key,value in r.items() if key.startswith(code+'_'));self.assertFalse(record['user_individual_visual_review'])
    def test_old_N0_report_and_candidates_remain_unchanged(self):
        self.assertEqual(sha(REPO/'docs/kidney_irrigation_capacity_v2_n0_result.md'),self.review['historical_n0_report_sha256'])
        for key,row in self.review['candidate_statuses'].items():self.assertEqual(sha(N0/'domains'/key/'candidate.json'),row['source_candidate_sha256'])
    def test_no_visible_anomaly_limited_to_reviewed_views(self):
        self.assertEqual(self.review['contact_review']['status'],'NO_VISIBLE_ANOMALY_IN_USER_REVIEWED_VIEWS')
        self.assertFalse(self.review['contact_review']['specific_previous_anomaly_reproduced'])
    def test_C07_to_C10_have_independent_computer_evidence(self):
        r=read_json(OUT/'C07_C10_computational_review.json')['comparisons'];self.assertEqual(len(r),4)
        for row in r:
            self.assertEqual(row['individual_user_review'],'NOT_REVIEWED')
            if row['id'].startswith('C08'):self.assertGreater(row['IN02_ring_hausdorff_mm'],0);self.assertLess(row['shift_toward_artificial_END_mm'],0)
            else:self.assertEqual(row['IN02_ring_hausdorff_mm'],0);self.assertTrue(row['IN02_removed_source_faces_identical'])
    def test_refinement_passes_all_geometry_gates(self):
        r=self.row;self.assertTrue(r['geometry_valid']);self.assertTrue(r['topology']['watertight']);self.assertTrue(r['topology']['winding_consistent'])
        self.assertEqual(r['topology']['boundary_edges']+r['topology']['nonmanifold_edges']+r['topology']['degenerate_faces'],0)
        self.assertEqual(r['cap_checks']['cap_wall_invalid_count'],0);self.assertFalse(r['cap_checks']['cap_cap_invalid_pairs']);self.assertEqual(r['cap_against_all_original_walls']['invalid_count'],0)
        self.assertLess(r['volume_checks']['spread_mm3'],3e-6)
    def test_quality_plane_uses_source_vertex_interval_not_volume_target(self):
        row=self.inventory['fixed_wall_inventory'][2]
        self.assertAlmostEqual(row['selected_quality_plane_mm'],(row['mixed_wall_triangle_max_axial_mm']+row['next_source_vertex_event_mm'])/2,places=14)
        self.assertGreater(row['selected_quality_plane_mm'],row['fixed_only_plane_lower_bound_mm']);self.assertLess(row['selected_quality_plane_mm'],1.)
    def test_near_vertex_failure_preserved_and_not_promoted(self):
        r=read_json(OUT/'failed_attempts/near_boundary_gate_failure/REJECTED.json');self.assertEqual(r['degenerate_faces'],2)
        bad=read_json(OUT/'failed_attempts/near_boundary_gate_failure/candidate/candidate.json');self.assertFalse(bad['geometry_valid']);self.assertEqual(bad['topology']['degenerate_faces'],2)
    def test_only_fully_fixed_IN02_source_wall_changed(self):
        f=self.a['cavity_faces'];mask=np.load(PROJECT/'deformation/p1_masks/port_fixed_masks.npy')[2]
        old=np.load(OUT/'C11_source_wall_area_mm2.npy');new=np.load(OUT/'R1_source_wall_area_mm2.npy');changed=np.load(OUT/'removed_fixed_collar_source_faces.npy')
        self.assertTrue(len(changed)>0);self.assertTrue(mask[f[changed]].all());self.assertTrue(np.all(old-new>=-1e-9))
        np.testing.assert_array_equal(old[~mask[f].all(1)],new[~mask[f].all(1)])
    def test_BLADDER_IN01_planes_preserved(self):
        old=read_json(N0/'domains/C11_inlet_distal_control/candidate.json')
        for i in [0,1]:
            for key in ['center_mm','normal_toward_artificial_END','split_source_face_ids','section_area_mm2']:self.assertEqual(old['cuts'][i][key],self.row['cuts'][i][key])
    def test_all_31_natural_paths_and_34_landmarks_retained(self):
        self.assertEqual(len(self.row['natural_path_samples']),31);self.assertEqual(len(self.row['landmark_signed_distances_mm']),34)
        self.assertFalse(self.row['excluded_natural_marker_ids']);self.assertFalse(self.row['natural_paths_with_outside_samples'])
    def test_reference_vertices_and_barycentric_mapping_exact(self):
        d=OUT/'domains'/self.row['id'];v=np.load(d/'reference_vertices.npy');ids=np.load(d/'source_vertex_ids.npy');w=np.load(d/'source_vertex_weights.npy');ref=self.a['cavity_reference_vertices']
        np.testing.assert_array_equal(v[:len(ref)],ref);np.testing.assert_allclose((ref[np.maximum(ids,0)]*w[:,:,None]).sum(1),v,rtol=0,atol=5e-14)
    def test_closed_differential_collar_matches_volume_difference(self):
        p=self.proof;self.assertGreater(p['certified_fixed_wall_collar_removed_mL'],0)
        self.assertAlmostEqual(p['C11_measurement_proxy_mL']-p['refined_measurement_proxy_mL'],p['independent_closed_collar_volume_mL'],places=12)
        self.assertTrue(p['shell_watertight'] and p['shell_winding_consistent']);self.assertEqual(p['shell_original_wall_checks']['invalid_count'],0)
    def test_remaining_volume_unknown_and_N1_not_started(self):
        self.assertIsNone(self.inventory['total_artificial_transition_volume_in_C11_mL']);self.assertIsNone(self.proof['remaining_artificial_transition_volume_mL'])
        r=read_json(OUT/'closeout_status.json');self.assertFalse(r['D2_approved']);self.assertFalse(r['N1_started']);self.assertFalse(r['N1_target_calibration_ready']);self.assertIsNone(r['V_reference_effective_mL'])
    def test_IN01_cannot_use_same_fixed_only_proximal_refinement(self):self.assertFalse(self.inventory['fixed_wall_inventory'][1]['unambiguously_fixed_only_proximal_refinement_possible'])
    def test_source_terminal_semantics_not_invented(self):
        self.assertEqual(len(read_json(N0/'terminal_boundary_inventory.json')['terminals']),22);self.assertFalse(self.inventory['all_natural_wall_in_C11_certified'])
    def test_3675_fixed_vertices_and_fields_unchanged(self):
        mask=np.load(PROJECT/'deformation/p2/evidence/port_fixed_masks.npy').any(0);self.assertEqual(mask.sum(),3675)
        self.assertTrue(np.all(self.a['cavity_displacement'][mask]==0));verify_sources()
    def test_actual_Godot_arrays_identical_to_accepted_data(self):
        for backend in ['compatibility','forward']:
            directory=OUT/'verification'/backend;self.assertEqual(read_json(directory/'runtime_checks.json')['failures'],0)
            for name in ['cavity','tissue']:
                for tag in ['u000','u025','u050','u075','u100','u037','restored']:
                    self.assertEqual((directory/f'{name}_{tag}.bin').read_bytes(),(N0/'verification'/backend/f'{name}_{tag}.bin').read_bytes())
    def test_repeat_build_does_not_mutate_feedback_or_change_arrays(self):
        names=['human_review_2026_10_14_v1.json','refinement_proof.json','C11_retained_structure_inventory.json','removed_fixed_collar.bin','domains/C11_R1_IN02_fixed_collar/candidate.json']
        names += [p.relative_to(OUT).as_posix() for p in (OUT/'domains/C11_R1_IN02_fixed_collar').glob('*.npy')]
        before={name:sha(OUT/name) for name in names}
        with contextlib.redirect_stdout(io.StringIO()):build()
        self.assertEqual(before,{name:sha(OUT/name) for name in names});protect()

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CloseoutTests))
    write_json(OUT/'verification/python_tests.json',{'tests':result.testsRun,'passed':result.wasSuccessful(),'failures':len(result.failures),'errors':len(result.errors),'scope':'Append-only feedback and engineering measurement refinement; not anatomical approval.'})
    raise SystemExit(0 if result.wasSuccessful() else 1)
