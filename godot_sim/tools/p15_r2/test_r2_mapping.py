"""P1.5-R2 regression and acceptance gates, including real Godot data."""
import unittest,copy,hashlib
from common import *
from summarize_results import sample_gate_violations
from localize_p15_conflicts import intersection_segment,coplanar_overlap_area
from write_reports import require_engineering_candidate

class R2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d=read_inputs();cls.field=np.load(OUT/'research_tissue_displacement.npy');cls.r=read_json(OUT/'quality_report.json');cls.runtime=read_json(OUT/'godot_runtime_validation.json');cls.diag=read_json(OUT/'source_diagnosis.json')
    def test_f01_same_donor_constraint_seam_diagnosed(self):
        rows=self.diag['F01']['vertices']
        self.assertEqual([r['donor_face'] for r in rows],[8516,8516])
        self.assertEqual([r['old_effective_constraint'] for r in rows],['near_wall_or_one_ring_hard','free_solve'])
        self.assertTrue(self.diag['F01']['can_coordinate_without_changing_exact_contact'])
        self.assertLess(self.diag['F01']['donor_target_gradient'],.03)
    def test_single_vertex_fix_would_transfer_f02_distortion(self):
        record=self.diag['F02']['relative_motion_counterfactuals'][1]
        self.assertEqual(record['replace_vertex_with_other_two_mean'],30717)
        self.assertGreater(record['two_ring']['maximum_area_ratio'],1.35)
    def test_ambiguous_donors_are_not_declared_anatomy(self):
        for idx in [61933,61934,30663]:
            record=self.diag['F03_F04_alternatives'][str(idx)]
            self.assertIn('UNCONFIRMED',record['conclusion'])
            for candidate in record['candidates'][1:]:
                self.assertTrue(candidate['normal_compatible']);self.assertTrue(candidate['shared_endpoint_topology_allowed'])
                self.assertLessEqual(candidate['cavity_surface_distance_lower_bound_mm'],4)
                self.assertIn('maximum_incident_edge_gradient',candidate)
        self.assertEqual(self.r['anatomical_assignment_unconfirmed'],[61933,61934,30663])
    def test_exact_139_coincident_constraints(self):
        mask=self.d['exact'];indices=np.load(R1/'coincident_cavity_vertex.npy')
        self.assertEqual(mask.sum(),139)
        np.testing.assert_array_equal(self.field[mask],self.d['driver'][indices[mask]])
    def test_contact_faces_remain_exactly_r1(self):
        self.assertEqual(self.d['contact'].sum(),545)
        np.testing.assert_array_equal(self.field[self.d['contact']],self.d['old'][self.d['contact']])
        self.assertLess(self.r['contact_consistency']['maximum_relative_displacement_mm'],1e-12)
    def test_original_far_and_exterior_fixed(self):
        patch=np.load(OUT/'repair_patch_mask.npy')
        self.assertTrue(np.all(self.field[self.d['remote']]==0))
        np.testing.assert_array_equal(self.field[~patch],self.d['old'][~patch])
        self.assertLess(patch.sum(),1500)
    def test_no_global_laplacian_increase_or_scale_reduction(self):
        self.assertLessEqual(np.linalg.norm(self.field,axis=1).max(),.2)
        self.assertAlmostEqual(np.linalg.norm(self.field,axis=1).max(),np.linalg.norm(self.d['old'],axis=1).max())
        self.assertEqual(source_record(PROJECT/'deformation/full_cavity/field/displacement.npy')['sha256'],'fbe95cfeaf8b77d80c5aa850618ad8ce8439c8ef770719b1f9a1f1789b050573')
        self.assertGreater(self.r['regional_before_after']['J_09']['after']['maximum_displacement_mm'],.15)
    def test_fixed_cavity_ports_still_exact(self):
        for name,port in self.r['cavity_fixed_ports'].items():
            self.assertTrue(port['all_u_exactly_zero']);self.assertEqual(port['maximum_displacement_mm'],0)
    def test_five_level_checks_are_complete_and_unmodified(self):
        self.assertEqual([x['fill'] for x in self.r['five_levels']],[0,.25,.5,.75,1])
        digest=source_record(OUT/'research_tissue_displacement.npy')['sha256']
        for x in self.r['five_levels']:
            self.assertEqual(x['cross']['field_sha256'],digest);self.assertEqual(x['self']['field_sha256'],digest)
            self.assertEqual(sample_gate_violations(x['quality_after'],x['cross'],x['self']),[])
            self.assertEqual(x['cross']['finite_acceptance_epsilon_mm'],1e-10)
    def test_no_degenerate_flipped_or_confirmed_new_crosses(self):
        for x in self.r['five_levels']:
            self.assertEqual(x['quality_after']['degenerate_count'],0);self.assertEqual(x['quality_after']['normal_reversal_count'],0)
            self.assertEqual(x['cross']['positive_segment_count'],0);self.assertEqual(x['self']['positive_segment_count'],0)
            self.assertEqual(x['self']['coplanar_overlap_pair_count'],0)
    def test_all_u_area_and_orientation_bound(self):
        bound=self.r['continuous']
        self.assertGreaterEqual(bound['all_u_area_ratio_lower_bound'],.8);self.assertLessEqual(bound['all_u_area_ratio_upper_bound'],1.35)
        tv,tf=self.d['tv'],self.d['tf'];_,a0,_=triangle_data(tv,tf)
        for u in [.11,.37,.64,.91]:
            _,area,_=triangle_data(tv+u*self.field,tf)
            self.assertGreaterEqual((area/a0).min(),bound['all_u_area_ratio_lower_bound']-1e-12)
            self.assertLessEqual((area/a0).max(),bound['all_u_area_ratio_upper_bound']+1e-12)
    def test_all_natural_regions_checked(self):
        regions=self.r['regional_before_after']
        for name in ['MAIN']+[f'B_{i:02}' for i in range(1,33)]+[f'J_{i:02}' for i in range(1,10)]+[f'T_{i:02}' for i in range(1,23)]+['BLADDER','IN_01','IN_02']:
            self.assertIn(name,regions);record=regions[name]['after'];self.assertGreater(record['vertices'],0)
            self.assertLessEqual(record['maximum_edge_gradient'],.2);self.assertGreaterEqual(record['minimum_area_ratio'],.8);self.assertLessEqual(record['maximum_area_ratio'],1.35)
    def test_f01_f02_and_neighborhoods_improved(self):
        last=self.r['five_levels'][-1]['local']
        self.assertLess(last['after']['F01_gradient'],.01)
        self.assertGreater(last['after']['F02_area_ratio'],.95)
        for name in ['F01','F02','F03','F04']:
            q=self.r['regional_before_after'][name]['after'];self.assertGreaterEqual(q['minimum_area_ratio'],.8);self.assertLessEqual(q['maximum_area_ratio'],1.35)
    def test_engineering_gate_rejects_area_failure(self):
        q=copy.deepcopy(self.r['five_levels'][-1]['quality_after']);q['area_ratio_range'][0]=.79
        self.assertIn('area_ratio',sample_gate_violations(q,{'positive_segment_count':0},{'positive_segment_count':0,'coplanar_overlap_pair_count':0}))
    def test_engineering_gate_rejects_gradient_failure(self):
        q=copy.deepcopy(self.r['five_levels'][-1]['quality_after']);q['maximum_edge_gradient']=.201
        self.assertIn('edge_gradient',sample_gate_violations(q,{'positive_segment_count':0},{'positive_segment_count':0,'coplanar_overlap_pair_count':0}))
    def test_engineering_gate_rejects_actual_crossing(self):
        q=self.r['five_levels'][-1]['quality_after']
        self.assertIn('finite_cavity_tissue_crossing',sample_gate_violations(q,{'positive_segment_count':1},{'positive_segment_count':0,'coplanar_overlap_pair_count':0}))
    def test_failed_result_cannot_publish_passed_report(self):
        report=copy.deepcopy(self.r);report['status']='RESEARCH_FAILED_NOT_FOR_ACCEPTANCE';report['violations']=['test failure']
        with self.assertRaises(ValueError): require_engineering_candidate(report)
    def test_legacy_false_candidates_not_called_proper_crosses(self):
        self.assertEqual(len(np.load(AUDIT/'proper_crossing_pairs.npy')),58)
        self.assertEqual(len(np.load(AUDIT/'tissue_self_intersections.npy')),23)
        self.assertEqual(self.r['five_levels'][0]['cross']['positive_segment_count'],0)
        self.assertEqual(self.r['five_levels'][0]['self']['positive_segment_count'],0)
    def test_real_finite_cross_synthetic_is_detected(self):
        a=np.array([[0.,0,0],[2,0,0],[0,2,0]]);b=np.array([[.5,.2,-1],[.5,.2,1],[.5,1,0]])
        self.assertIsNotNone(intersection_segment(a,b))
        self.assertAlmostEqual(coplanar_overlap_area(a,a),2.)
    def test_reference_mid_expanded_same_topology(self):
        candidate=OUT/'candidate';np.testing.assert_array_equal(np.load(candidate/'faces.npy'),self.d['tf'])
        np.testing.assert_array_equal(np.load(candidate/'reference_vertices.npy'),self.d['tv'])
        np.testing.assert_array_equal(np.load(candidate/'mid_vertices.npy'),self.d['tv']+.5*self.field)
        np.testing.assert_array_equal(np.load(candidate/'expanded_vertices.npy'),self.d['tv']+self.field)
        self.assertTrue(self.r['not_final_acceptance'])
        self.assertEqual(self.r['status'],'ENGINEERING_GATES_PASSED_PENDING_HUMAN_ACCEPTANCE')
    def test_rebuild_arrays_identical(self):
        report=read_json(OUT/'rebuild_verification.json');self.assertTrue(report['all_arrays_byte_identical'])
        self.assertEqual(report['first_array_sha256'],report['second_array_sha256'])
    def test_actual_godot_20_mesh_snapshots(self):
        self.assertEqual(len(self.runtime['records']),20);self.assertTrue(self.runtime['all_position_arrays_match']);self.assertTrue(self.runtime['all_cavity_fixed_exact'])
        self.assertTrue(self.runtime['graphical_runtime']['camera_unchanged_during_before_after'])
        for row in self.runtime['records']: self.assertTrue(row['source_indices_exact']);self.assertTrue(row['normal_finite'])
    def test_actual_godot_cavity_before_after_identical(self):
        for u in [0,25,50,75,100]:
            root=OUT/'godot_validation'
            self.assertEqual((root/f'before_cavity_u{u:03}.bin').read_bytes(),(root/f'after_cavity_u{u:03}.bin').read_bytes())
    def test_actual_float32_contacts_and_geometry(self):
        self.assertEqual(len(self.runtime['float32_cross_review']),5)
        for row in self.runtime['float32_cross_review']: self.assertEqual(row['positive_segment_count'],0)
        for row in self.runtime['records']:
            if 'actual_float32_geometry_quality' in row:
                q=row['actual_float32_geometry_quality'];self.assertGreaterEqual(q['area_ratio_range'][0],.8);self.assertLessEqual(q['area_ratio_range'][1],1.35);self.assertLessEqual(q['maximum_edge_gradient'],.2)
    def test_no_unsafe_transparency(self):
        shader=(PROJECT/'shaders/audit_section.gdshader').read_text(encoding='utf8')
        self.assertNotIn('ALPHA',shader);self.assertNotIn('blend_mix',shader)
        script=(PROJECT/'scripts/p15_r2/mapping_preview.gd').read_text(encoding='utf8')
        self.assertIn('研究试验／未验收',script)
    def test_protected_sources_and_previous_results(self):
        before=read_json(OUT/'protected_before.json')
        for name,digest in before.items(): self.assertEqual(source_record(PROJECT.parent/name)['sha256'],digest,name)

if __name__=='__main__': unittest.main(verbosity=2)
