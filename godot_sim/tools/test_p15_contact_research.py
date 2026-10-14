"""Regression tests for P1.5 contact research, including historical false positives."""
import unittest
import struct
import numpy as np
from scipy import sparse
from research_p15_contact_mapping import *
from localize_p15_conflicts import intersection_segment,closest_features

class ContactResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v,cls.f,cls.tv,cls.tf,cls.d=inputs()
        cls.field=np.load(ROOT/'UNACCEPTED_contact_tissue_displacement.npy')
        cls.result=read_json(ROOT/'research_result.json')
    def test_finite_positive_crossing(self):
        a=np.array([[0.,0,0],[2,0,0],[0,2,0]])
        b=np.array([[.5,.2,-1],[.5,.2,1],[.5,1,0]])
        segment=intersection_segment(a,b)
        self.assertIsNotNone(segment);self.assertAlmostEqual(np.linalg.norm(segment[1]-segment[0]),.8)
    def test_infinite_planes_straddle_but_only_point_contact(self):
        i,j=np.load(AUDIT/'proper_crossing_pairs.npy')[0]
        a,b=self.v[self.f[i]],self.tv[self.tf[j]]
        self.assertIsNone(intersection_segment(a,b));self.assertEqual(closest_features(a,b)[0],0)
    def test_disjoint_parallel_triangles_never_snap_to_intersection(self):
        i,j=np.load(AUDIT/'tissue_self_intersections.npy')[1]
        for tol in (1e-10,1e-8,1e-6,1e-4,1e-3): self.assertIsNone(intersection_segment(self.tv[self.tf[i]],self.tv[self.tf[j]],tol))
        self.assertGreater(closest_features(self.tv[self.tf[i]],self.tv[self.tf[j]])[0],.2)
    def test_coplanar_overlap_and_separation(self):
        a=np.array([[0.,0,0],[1,0,0],[0,1,0]])
        self.assertAlmostEqual(coplanar_overlap_area(a,a),.5)
        self.assertEqual(coplanar_overlap_area(a,a+np.array([2,0,0])),0)
        self.assertEqual(coplanar_overlap_area(a,a+np.array([0,0,.001])),0)
    def test_dirichlet_nonzero_rhs(self):
        graph=sparse.csr_matrix([[0.,1,0],[1,0,1],[0,1,0]])
        values=np.array([[1.,0,0],[0,0,0],[0,0,0]])
        output=constrained_follow(graph,values,np.array([True,False,True]),values)
        np.testing.assert_array_equal(output[[0,2]],values[[0,2]])
        self.assertAlmostEqual(output[1,0],5/12)
    def test_original58_and23_preserved_and_reclassified(self):
        self.assertEqual(len(np.load(AUDIT/'proper_crossing_pairs.npy')),58)
        self.assertEqual(len(np.load(AUDIT/'tissue_self_intersections.npy')),23)
        r=read_json(ROOT/'localization_report.json')['independent_review']
        self.assertEqual(r['positive_cross_segments'],0);self.assertTrue(r['old58_all_finite_feature_gap_zero'])
        self.assertGreater(r['self23_feature_distance_mm'][0],.001)
    def test_reference_index_identity(self):
        np.testing.assert_array_equal(np.load(ROOT/'tissue_reference.npy'),self.tv)
        np.testing.assert_array_equal(np.load(ROOT/'tissue_faces.npy'),self.tf)
    def test_candidate_hashes_match(self):
        for name,digest in self.result['build']['output_sha256'].items(): self.assertEqual(source_record(ROOT/name)['sha256'],digest)
    def test_magnitude_and_coincident_contact_identity(self):
        self.assertTrue(np.isfinite(self.field).all());self.assertLessEqual(np.linalg.norm(self.field,axis=1).max(),.2)
        mask=np.load(ROOT/'coincident_mask.npy');indices=np.load(ROOT/'coincident_cavity_vertex.npy')
        self.assertEqual(mask.sum(),139)
        np.testing.assert_array_equal(self.field[mask],self.d[indices[mask]])
    def test_remote_and_approved_ports_exact_zero(self):
        self.assertTrue(np.all(self.field[np.load(ROOT/'remote_anchors.npy')]==0))
        fixed=np.load(PROJECT/'deformation/p1_masks/port_fixed_masks.npy')
        self.assertTrue(np.all(self.d[fixed.any(axis=0)]==0))
    def test_contact_relative_sample_residual(self):
        self.assertLess(self.result['original_contact_samples']['maximum_relative_displacement_mm'],1e-12)
    def test_ambiguous_near_wall_points_are_flagged(self):
        self.assertEqual(self.result['tissue_field_summary']['uncertain_moving_vertex_ids'],[30663,61933,61934])
        self.assertEqual(len(self.result['failure_groups']),4)
        self.assertFalse(self.result['outer_inner_relation']['wall_thickness_validated'])
    def test_five_levels_really_scanned(self):
        self.assertEqual([r['fill'] for r in self.result['five_levels']],[0,.25,.5,.75,1])
        for level in self.result['five_levels']:
            self.assertEqual(level['cross']['positive_segment_count'],0)
            self.assertEqual(level['self']['positive_segment_count'],0)
            self.assertEqual(level['self']['coplanar_overlap_pair_count'],0)
            self.assertEqual(level['tissue_quality']['normal_reversal_count'],0)
            self.assertEqual(level['tissue_quality']['degenerate_count'],0)
    def test_cavity_five_level_baseline_reused(self):
        for level in self.result['five_levels']:
            self.assertEqual(level['approved_cavity_quality']['fill'],level['fill'])
            for port in level['approved_cavity_quality']['fixed_ports'].values(): self.assertEqual(port['maximum_displacement_mm'],0)
    def test_failed_trial_cannot_be_promoted(self):
        self.assertEqual(self.result['status'],'BLOCKED_RESEARCH_TRIAL_NOT_PROMOTED')
        self.assertTrue(self.result['violations'])
        self.assertGreater(self.result['local_regions_expanded']['B_32']['maximum_edge_gradient'],.9)
        self.assertLess(self.result['local_regions_expanded']['J_09']['area_ratio_range'][0],.8)
        self.assertFalse((ROOT/'expanded_vertices.npy').exists())
        self.assertFalse((PROJECT/'deformation/p15_tissue').exists())
    def test_diagnostic_binary_and_coordinate_origin(self):
        origin=np.array([16.,16.,-81.])
        for name,v,f in [('cavity',self.v,self.f),('tissue',self.tv,self.tf)]:
            raw=(ROOT/(name+'_reference.bin')).read_bytes();n,m=struct.unpack('<II',raw[8:16])
            self.assertEqual(raw[:8],b'KAUD0001');self.assertEqual((n,m),(len(v),len(f)))
            np.testing.assert_array_equal(np.frombuffer(raw,dtype='<f4',count=n*3,offset=16).reshape(-1,3),(v-origin).astype(np.float32))
            np.testing.assert_array_equal(np.frombuffer(raw,dtype='<u4',count=m*3,offset=16+28*n).reshape(-1,3),f[:,::-1])
    def test_unsafe_old_smoothing_is_not_hidden(self):
        for record in self.result['old_probe_reclassification']:
            if record['strength']==0: self.assertEqual(record['independent']['positive_segment_count'],0)
            else: self.assertGreaterEqual(record['independent']['positive_segment_count'],896)
    def test_no_transparency_or_failed_joint_morph_in_preview(self):
        script=(PROJECT/'scripts/p15_contact_research_preview.gd').read_text(encoding='utf8')
        shader=(PROJECT/'shaders/audit_section.gdshader').read_text(encoding='utf8')
        self.assertNotIn('ALPHA',shader);self.assertNotIn('blend_mix',shader)
        self.assertNotIn('UNACCEPTED_contact_tissue_displacement',script)
        self.assertIn('原始参考态',script)

if __name__=='__main__': unittest.main(verbosity=2)
