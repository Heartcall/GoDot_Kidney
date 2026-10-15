"""N2.1-R actual-data and exact-geometry tests. No synthetic patient endpoints."""
from n21_common import *
from n21_features import finite_features,FiniteTissue,ContactState
from n21_ccd import exact_pair,interval_projection,bernstein,split,F,evaluate
from n21_robust_patch import rounding_budget,display_quality
from n20_verify import independent_volume
from n21_coplanar import coplanar_embedding
import unittest

class N21Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.a,cls.d2,cls.tv,cls.tf,cls.resolved,cls.approval=inputs();cls.art=ROOT/'test_artifacts';cls.art.mkdir(exist_ok=True)
    def test_historical_protection(self):self.assertGreater(protect(),2900)
    def test_original_N20_manifest(self):
        for name,row in read(OLD/'delivery_manifest.json')['files'].items():self.assertEqual(sha(REPO/name),row['sha256'])
    def test_authorized_targets_unchanged(self):
        self.assertEqual(read(ROOT/'authorization.json')['targets'],TARGETS)
        self.assertFalse(read(ROOT/'authorization.json')['formal_N2_resources_authorized'])
    def test_medical_null_preserved(self):
        self.assertEqual(sha(PROJECT/'deformation/capacity_v2_n15_m_v1/real_parameter_status.json'),'8bd479964a4ae32900aa77d5be2baca0d3afc2a1969f35fe3856e7cfe2111ca6')
    def test_false_infinite_plane_constraint_reproduced(self):
        r=read(ROOT/'reproduction.json')['finite_conflict'];self.assertLess(min(r['projected_barycentric']),-.9)
        self.assertGreater(r['finite_face_distance_mm'],.9);self.assertEqual(r['strict_coincident_cavity_vertex'],17717)
        self.assertTrue(any(x['reason']=='OUTSIDE_FINITE_FACE' and x['key'].endswith('VF:0:0') for x in r['outside_finite_face']))
    def test_finite_feature_weights(self):
        r=read(ROOT/'reproduction.json')['finite_conflict']['finite_features']
        for value in r:
            for name in ['cavity_weights','tissue_weights']:
                self.assertGreaterEqual(min(value[name]),0);self.assertLessEqual(max(value[name]),1);self.assertAlmostEqual(sum(value[name]),1,places=12)
    def test_shared_point_never_hard_bound_outside_triangle(self):
        c,t,_=fixture('expand');tm=FiniteTissue(self.a,self.tv,self.tf,self.resolved)
        tm.linearization_offset=t;C,b,keys,_,conflicts=tm.constraint_rows(c,t,{(34852,181160)})
        self.assertFalse(conflicts)
        self.assertTrue(all(x['kind']!='VF_TISSUE_VERTEX' or x['tissue_weights'][0]!=1 for x in keys))
    def test_warm_start_is_not_claimed_cold_cure(self):
        for row in read(ROOT/'warm_contact/summary.json'):
            self.assertTrue(row['not_a_new_independent_mapping_cure']);self.assertTrue(row['static_candidate_pass']);self.assertEqual(row['max_tissue_change_mm'],0)
    def test_original_float32_failure_reproduced(self):
        r=read(ROOT/'reproduction.json');self.assertFalse(r['contract_float32']['pass']);self.assertIn(7680,r['contract_float32']['bad_faces'])
    def test_generic_multi_patch_no_topology_change(self):
        r=read(ROOT/'robust_contract_r2/repair_report.json');self.assertFalse(r['hardcoded_special_face']);self.assertFalse(r['topology_changed'])
        self.assertIn(7680,r['seed_faces_selected_by_rounding_budget']);self.assertGreater(len(r['seed_faces_selected_by_rounding_budget']),1)
        self.assertGreater(sum(p['status']=='PATCH_UPDATED' for p in r['patches']),1)
    def test_all_float32_physical_faces_pass(self):
        r=read(ROOT/'verification/robust_contract_r2/summary.json')
        self.assertTrue(all(x['pass'] for x in r['cavity_float32_quality']));self.assertTrue(all(x['pass'] for x in r['tissue_float32_quality']))
    def test_complete_operation_margin(self):
        rows=read(ROOT/'float32_interval_margin_audit.json')
        for r in rows:
            if r['candidate']=='robust_contract_r2':
                self.assertTrue(r['includes_u_rounding_and_multiply_add']);self.assertTrue(r['hard_gate_protected_by_bound']);self.assertGreaterEqual(r['minimum_area_ratio_lower_bound'],.8)
    def test_original_candidate_volume_not_silently_lowered(self):
        c=np.load(ROOT/'robust_contract_r2/cavity_offset.npy');v=volume(self.d2['reference_vertices']+map_d2(c,self.d2),self.d2['faces'])
        self.assertAlmostEqual(v,15.524507478263565,places=9)
        self.assertGreater(v,TARGETS['contract_mL'])
    def test_independent_D2_volume(self):
        c=np.load(ROOT/'robust_contract_r2/cavity_offset.npy');r=independent_volume(self.d2['reference_vertices']+map_d2(c,self.d2),self.d2['faces'])
        self.assertTrue(r['numerically_valid']);self.assertLess(r['method_spread_mL'],1e-9)
    def test_fixed_exact_remote_all_five_levels(self):
        root=PROJECT/'deformation/p2/evidence';exact=np.load(root/'coincident_mask.npy');ids=np.load(root/'coincident_cavity_vertex.npy');remote=np.load(root/'remote_anchors.npy');fixed=self.a['port_fixed_masks'].any(0)
        self.assertEqual(fixed.sum(),3675);self.assertEqual(exact.sum(),139)
        for folder in [ROOT/'robust_contract_r2',ROOT/'warm_contact/S1_expand',ROOT/'warm_contact/S2_expand']:
            c=np.load(folder/'cavity_offset.npy');t=np.load(folder/'tissue_offset.npy')
            self.assertTrue(np.all(c[fixed]==0));self.assertTrue(np.all(t[remote]==0));np.testing.assert_array_equal(t[exact],c[ids[exact]])
    def test_five_states_are_complete_not_endpoint_only(self):
        for name in ['robust_contract_r2','S2_expand']:
            r=read(ROOT/'verification'/name/'summary.json');self.assertEqual([x['u'] for x in r['five_levels']],[0,.25,.5,.75,1.])
            self.assertTrue(r['all_float64_sampled_crossings_zero']);self.assertTrue(r['all_float32_relative_crossings_zero'])
    def test_boundary_material_stencil_semantics(self):
        rows=read(ROOT/'boundary/summary.json');self.assertEqual(len(rows),4)
        for row in rows:
            self.assertTrue(row['sampled_domain_valid']);self.assertTrue(row['physical_quality'])
            if row['strategy']=='FIXED_97':self.assertEqual(row['max_boundary_motion_mm'],0)
            else:self.assertGreater(row['max_boundary_motion_mm'],.001)
    def test_real_patch_repeat(self):self.assertTrue(read(ROOT/'repeat_patch.json')['byte_identical'])
    def test_total_regional_reoptimization_and_failure_retained(self):
        r=read(ROOT/'regional_sqp/report.json');self.assertTrue(r['total_q_optimized_not_increment_only']);self.assertTrue(r['full_contact_state_restart_bitwise_q_equal'])
        self.assertFalse(r['progressive_target_reached']);self.assertFalse(r['static_candidate_pass']);self.assertFalse(r['returned_field_is_baseline'])
        # Retreat is allowed and attempted in relinearization. The failed second
        # step is NOT applied merely to make a negative update appear accepted.
        self.assertLess(min(min(x['delta_q']) for x in r['iterations']),0)
        old=read(ROOT/'attempts/regional_sqp_ill_conditioned/report.json')
        self.assertTrue(old['returned_field_is_baseline']);self.assertFalse(old['static_candidate_pass'])
    def test_capacity_attribution_conserved(self):
        r=read(ROOT/'regional_sqp/report.json')['capacity_attribution'];self.assertLess(abs(r['residual_mL']),1e-9)
    def test_atomic_full_contact_state(self):
        c,t,_=fixture('expand');state=ContactState();state.pairs={(34852,181160)};state.features={'inactive':{'active':False,'release_count':2,'dual':.125}}
        state.numerical={'warm_cavity':c,'warm_tissue':t,'linearization':t.copy()};state.stage='OUTER_BEGIN';state.outer_index=2
        p=self.art/'roundtrip.json';source={'a':'hash'};settings={'rho':.02};state.save(p,source,settings);restored=ContactState.load(p,source,settings)
        self.assertEqual(restored.features,state.features);self.assertEqual(restored.pairs,state.pairs);self.assertEqual(restored.outer_index,2)
        np.testing.assert_array_equal(restored.numerical['warm_tissue'],t)
        with self.assertRaises(ValueError):ContactState.load(p,source,{'rho':.03})
    def test_real_contact_transaction_resume_bitwise(self):
        c,t,_=fixture('expand');tm=FiniteTissue(self.a,self.tv,self.tf,self.resolved);checkpoint=self.art/'real_transaction.json'
        settings={'solver':'FINITE_TRANSACTION_TEST','max_outer':1};first,r=tm.solve_finite(c,{(34852,181160)},max_outer=1,warm_cavity=c,warm_tissue=t,checkpoint=checkpoint,checkpoint_settings=settings)
        source={'cavity_bytes':hashlib.sha256(c.tobytes()).hexdigest(),'reference_cavity':hashlib.sha256(self.a['vertices'].tobytes()).hexdigest(),'reference_tissue':hashlib.sha256(self.tv.tobytes()).hexdigest()}
        state=ContactState.load(checkpoint,source,settings);second,rr=tm.solve_finite(c,state=state,max_outer=1,resume=True)
        np.testing.assert_array_equal(first,second)
    def test_interval_dot_contains_exact_values_SYNTHETIC_TEST_ONLY(self):
        p=np.array([[[1e10,1e10,1.],[.125,-.25,.5]]]);axis=np.array([[1.,-1.,.125]])
        lo,hi=interval_projection(p,axis)
        for k,point in enumerate(p[0]):
            exact=sum((F(float(x))*F(float(y)) for x,y in zip(point,axis[0])),F(0));self.assertLessEqual(F(float(lo[0,k])),exact);self.assertGreaterEqual(F(float(hi[0,k])),exact)
    def test_between_sample_collision_certified_SYNTHETIC_TEST_ONLY(self):
        a=np.array([[-1.,-1,0],[1,-1,0],[0,1,0]]);b=np.array([[-2.,-.3,-.3],[-2,-.3,.3],[-2,.3,0]]);end=b+[16,0,0]
        r=exact_pair(a,a,b,end);self.assertEqual(r['class'],'CERTIFIED_NEW_TRANSVERSE_EXISTS')
    def test_unresolved_not_safe_SYNTHETIC_TEST_ONLY(self):
        a=np.array([[-1.,-1,0],[1,-1,0],[0,1,0]]);b=np.array([[-2.,-.3,-.3],[-2,-.3,.3],[-2,.3,0]])
        r=exact_pair(a,a,b,b+[16,0,0],max_depth=0);self.assertEqual(r['class'],'UNRESOLVED_BERNSTEIN_TIME_BOX')
    def test_persistent_coplanar_sliding_SYNTHETIC_TEST_ONLY(self):
        a=np.array([[0.,0,0],[1,0,0],[0,1,0]]);b=a*.3+[.1,.1,0];r=exact_pair(a,a,b,b+[.1,0,0])
        self.assertEqual(r['class'],'CERTIFIED_NO_TRANSVERSE_PERSISTENT_COPLANAR')
    def test_shared_vertex_is_not_automatic_pass_SYNTHETIC_TEST_ONLY(self):
        a=np.array([[0.,0,0],[1,0,0],[0,1,0]]);b=np.array([[0.,0,0],[.25,.25,-.5],[.25,.25,.5]])
        r=exact_pair(a,a,b,b);self.assertEqual(r['class'],'CERTIFIED_REFERENCE_TRANSVERSE_EXISTS');self.assertFalse(r['shared_feature_alone_used_as_certificate'])
    def test_Bernstein_exact_subdivision_SYNTHETIC_TEST_ONLY(self):
        p=[F(1),F(-2),F(2)];b=bernstein(p);left,right=split(b);self.assertEqual(left[-1],evaluate(p,F(1,2)));self.assertEqual(right[0],left[-1])
    def test_CCD_scope_never_overpromoted(self):
        for name in ['s1_n20_passed_fresh','s2_warm_fresh','robust_contract_r2_fresh']:
            r=read(ROOT/'ccd'/name/'summary.json');self.assertFalse(r['full_continuous_safe'])
            self.assertFalse(any('UNRESOLVED' in k or 'NEW_TRANSVERSE_EXISTS' in k for k in r['exact_pair_counts']))
            self.assertEqual(r['sources_and_settings']['settings']['kernel_sha256'],sha(Path(__file__).with_name('n21_ccd.py')))
    def test_coplanar_real_contact_topology_invariant(self):
        for r in read(ROOT/'coplanar/summary.json'):
            self.assertEqual(r['class_counts'],{'CERTIFIED_COPLANAR_CONTACT_TOPOLOGY_INVARIANT':92})
            self.assertEqual(r['reference_relations'],{'POSITIVE_AREA_OVERLAP':42,'POINT_OR_EDGE_CONTACT':50})
    def test_coplanar_embedding_or_sliding_unknown_SYNTHETIC_TEST_ONLY(self):
        a=np.array([[0.,0,0],[1,0,0],[0,1,0]]);b=a*.25+[.1,.1,0]
        self.assertEqual(coplanar_embedding(a,a+[0,0,1],b,b+[0,0,1])['class'],'CERTIFIED_COPLANAR_CONTACT_TOPOLOGY_INVARIANT')
        self.assertEqual(coplanar_embedding(a,a,b,b+[.1,0,0])['class'],'UNRESOLVED_COPLANAR_SLIDING')
    def test_self_CCD_missing_scope_blocks_full_pass(self):
        for name in ['s1_n20_passed','robust_contract_r2']:
            r=read(ROOT/'ccd_self'/name/'tissue/summary.json')
            self.assertFalse(r['full_self_continuous_safety_certified']);self.assertGreater(r['unprocessed_shared_one_vertex_pairs'],280000)
    def test_sampled_feature_tracking_full_resume(self):
        r=read(ROOT/'feature_tracking/summary.json');self.assertEqual(len(r['frames']),9)
        self.assertTrue(r['uninterrupted_vs_resumed_history_exactly_equal']);self.assertTrue(r['all_active_and_inactive_history_retained'])
        self.assertFalse(r['continuous_feature_manifold_tracking_certified'])
    def test_local_LP_not_global_geometric_limit(self):
        r=read(ROOT/'regional_sqp/local_feasibility_lp.json');self.assertTrue(r['success'])
        self.assertGreater(r['local_linear_model_maximum_increment_mL'],r['local_linear_model_requested_increment_mL'])
        self.assertFalse(r['global_geometry_infeasibility_proved']);self.assertIsNone(r['global_safe_capacity_bound'])
    def test_cold_contact_regression_failures_preserved(self):
        r=read(ROOT/'contact_final/summary.json');self.assertEqual(len(r),4)
        self.assertTrue(all(not x['static_candidate_pass'] for x in r))
    def test_failed_regional_candidate_not_promoted(self):
        r=read(ROOT/'regional_sqp/nonlinear_failure.json');self.assertEqual(r['confirmed_pair_count'],69)
        self.assertFalse(r['overall_candidate_accepted']);self.assertFalse(r['global_infeasibility_claimed'])
    def test_no_formal_resources(self):self.assertFalse(read(ROOT/'verification/robust_contract_r2/summary.json')['formal_N2'])
    def test_degenerate_motion_not_certified_SYNTHETIC_TEST_ONLY(self):
        a=np.array([[0.,0,0],[1,0,0],[0,1,0]]);end=a.copy();end[1]=[-1,0,0];b=a+[0,0,1]
        self.assertEqual(exact_pair(a,end,b,b)['class'],'UNRESOLVED_DEGENERATE_OR_CONDITIONED_FACE')

if __name__=='__main__':
    start=time.time();result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(N21Tests))
    write(ROOT/'python_tests.json',{'tests':result.testsRun,'passed':result.wasSuccessful(),'failures':[(str(t),v) for t,v in result.failures],
        'errors':[(str(t),v) for t,v in result.errors],'seconds':time.time()-start,'synthetic_values_never_used_as_real_targets':True})
    sys.exit(0 if result.wasSuccessful() else 1)
