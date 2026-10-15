"""N2.0 real-input regression plus clearly synthetic finite-geometry fixtures."""
from n20_model import *
from n20_solve import capacity_step
from n20_verify import step_area_bounds,independent_volume
from n20_ccd import research_ccd,swept_pairs
import unittest,platform

class N20Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a,cls.d2,cls.tv,cls.tf,cls.resolved,cls.approval=inputs()
        cls.model=CavityModel(cls.a,cls.resolved,cls.d2,cls.approval)
    def test_protection(self):self.assertGreater(protected(),2400)
    def test_six_hashes(self):
        p2=PROJECT/'deformation/p2'
        for row in read(p2/'accepted_inputs.json')['arrays'].values():self.assertEqual(sha(p2/row['runtime']),row['sha256'])
    def test_targets_not_downgraded(self):
        t=read(OUT/'authorization_and_targets.json')
        self.assertAlmostEqual(t['contract_target_mL'],11.764173461201125,places=12)
        self.assertAlmostEqual(t['expand_target_mL'],21.847750713659231,places=12)
        self.assertFalse(t['production_N2_authorized'])
    def test_physiology_stays_null(self):
        self.assertTrue(all(x is None for x in read(OUT/'authorization_and_targets.json')['actual_physiological_parameters'].values()))
        self.assertEqual(sha(PROJECT/'deformation/capacity_v2_n15_m_v1/real_parameter_status.json'),'8bd479964a4ae32900aa77d5be2baca0d3afc2a1969f35fe3856e7cfe2111ca6')
    def test_exclusive_surface_mapping(self):
        m=self.model;self.assertEqual(len(m.group),25024);self.assertEqual((m.group==0).sum(),3675)
        owners=np.array([p['id'] for p in self.resolved['paths']])[self.a['path_owner']]
        self.assertTrue(np.all(owners[m.group==2]=='MAIN'))
        self.assertTrue(np.all(np.array(m.names)[m.local[m.group==3]]=='J_01'))
        self.assertTrue(np.all(np.array(m.names)[m.local[m.group==5]]!='J_01'))
        self.assertTrue(np.array_equal(m.group,np.load(OUT/'region_ids.npy')))
    def test_unresolved_sections_not_used(self):
        self.assertNotIn('B_27:25',self.model.station_ids);self.assertNotIn('B_30:4',self.model.station_ids)
    def test_priority_and_saturation_redistribution(self):
        m=self.model;mob=np.ones(len(m.names));first=m.response('expand',mob)
        mob[m.names.index('T_19')]=0;second=m.response('expand',mob)
        region=m.local==m.names.index('T_19')
        self.assertLess(np.linalg.norm(second[region]),np.linalg.norm(first[region]))
        target=.01*volume(self.d2['reference_vertices'],self.d2['faces'])
        candidate,r=capacity_step(m,self.d2,np.zeros_like(first),'expand',mob,target)
        actual=volume(self.d2['reference_vertices']+map_d2(candidate,self.d2),self.d2['faces'])
        self.assertAlmostEqual(actual,r['target_step_mL'],places=10)
        self.assertGreater(np.linalg.norm(candidate[~region]),0)
    def test_fixed_and_measurement_collars(self):
        m=self.model;d=m.response('expand',np.ones(len(m.names)))
        self.assertTrue(np.all(d[m.approved_fixed]==0));self.assertTrue(np.all(d[m.measurement_anchors]==0))
        ring=np.concatenate([c['selected_boundary_vertex_ids'] for c in self.approval['virtual_caps']])
        np.testing.assert_array_equal(map_d2(d,self.d2)[ring],0)
    def test_not_scaled_old_field(self):
        d=self.model.response('expand',np.ones(len(self.model.names)))
        old=np.load(PROJECT/'deformation/full_cavity/field/displacement.npy');factor=np.sum(old*d)/np.sum(old*old)
        self.assertGreater(np.linalg.norm(d-factor*old)/np.linalg.norm(d),.05)
        c=self.model.response('contract',np.ones(len(self.model.names)));factor=np.sum(c*d)/np.sum(d*d)
        self.assertGreater(np.linalg.norm(c-factor*d)/np.linalg.norm(c),.01)
    def test_volume_gradient(self):
        rng=np.random.default_rng(20);c=np.zeros_like(self.a['vertices']);h=rng.normal(size=c.shape)*.01
        g=volume_gradient_source(c,self.d2);epsilon=1e-4
        actual=(volume(self.d2['reference_vertices']+epsilon*map_d2(h,self.d2),self.d2['faces'])-volume(self.d2['reference_vertices']-epsilon*map_d2(h,self.d2),self.d2['faces']))/(2*epsilon)
        self.assertAlmostEqual(actual,np.sum(g*h),places=8)
    def test_reference_decimal_independent(self):
        r=independent_volume(self.d2['reference_vertices'],self.d2['faces'])
        self.assertTrue(r['numerically_valid']);self.assertAlmostEqual(r['far_origin_decimal40_mL'],16.805962087430178,places=11)
    def test_repeat_first_predictor(self):
        m=self.model;candidate,_=capacity_step(m,self.d2,np.zeros_like(m.v),'expand',np.ones(len(m.names)),.01*volume(self.d2['reference_vertices'],self.d2['faces']))
        np.testing.assert_array_equal(candidate,np.load(OUT/'expand/cavity_001.npy'))
        tm=TissueModel(self.a,self.tv,self.tf,self.resolved);t,r=tm.solve(candidate)
        np.testing.assert_array_equal(t,np.load(OUT/'expand/tissue_001.npy'))
        root=PROJECT/'deformation/capacity_v2_n16_v1/prototypes/thin_face_corrected/S1_expand'
        c=np.load(root/'research_cavity_offset.npy');old=read(root/'contacts/u100.json')['results']['cavity_tissue']
        pairs={(r['cavity_face'],r['tissue_face']) for r in old['rows'] if r['class']=='FINITE_TRANSVERSE_CROSSING'}
        t,r=tm.solve(c,pairs);self.assertTrue(r['qp_converged'])
        np.testing.assert_array_equal(t,np.load(OUT/'regression/S1_expand/best_tissue_offset_RESEARCH_ONLY.npy'))
    def test_contact_fixture_improvement_not_false_promotion(self):
        rows=read(OUT/'regression/comparison.json')['fixtures']
        self.assertEqual([r['old_confirmed_transverse_pairs'] for r in rows],[173,753,1838])
        self.assertEqual(rows[0]['best_new_confirmed_transverse_pairs'],0)
        self.assertEqual(rows[1]['best_new_confirmed_transverse_pairs'],0)
        self.assertFalse(rows[1]['iterations'][-1]['qp_converged'])
        self.assertGreater(rows[2]['best_new_confirmed_transverse_pairs'],0)
        self.assertTrue(all(not r['runtime_eligible'] for r in rows))
    def test_tangential_not_vertex_deletion(self):
        r=read(OUT/'tangential_repair/experiment.json');self.assertTrue(r['optimizer_success']);self.assertTrue(r['after']['pass'])
        self.assertEqual(len(np.load(OUT/'tangential_repair/tangential_cavity_offset_RESEARCH_ONLY.npy')),25024)
        self.assertFalse(r['used_to_raise_reported_verified_capacity'])
    def test_continuous_segment_area_dense_SYNTHETIC_TEST_ONLY(self):
        v=np.array([[0.,0,0],[1,0,0],[0,1,0]]);f=np.array([[0,1,2]])
        start=np.array([[0.,0,0],[0,.1,.1],[.05,0,.1]]);end=np.array([[0.,0,0],[0,-.1,.2],[.1,0,.2]])
        r=step_area_bounds(v,f,start,end);areas=[triangle_data(v+(1-u)*start+u*end,f)[1][0]/.5 for u in np.linspace(0,1,1001)]
        self.assertLessEqual(r['minimum_area_ratio'],min(areas)+1e-10);self.assertGreaterEqual(r['maximum_area_ratio'],max(areas)-1e-10)
    def test_ccd_between_clear_endpoints_SYNTHETIC_TEST_ONLY(self):
        a=np.array([[-1.,-1,0],[1,-1,0],[0,1,0]]);b=np.array([[-3.,-.3,-.3],[-3,-.3,.3],[-3,.3,0]]);f=np.array([[0,1,2]]);d=np.tile([6.,0,0],(3,1))
        self.assertEqual(classify(a,f,b,f,[[0,0]])['confirmed_transverse_crossings'],0)
        self.assertEqual(classify(a,f,b+d,f,[[0,0]])['confirmed_transverse_crossings'],0)
        p=swept_pairs(a,f,np.zeros_like(a),b,f,d);r=research_ccd(a,f,np.zeros_like(a),b,f,d,p)
        self.assertGreater(len(r['confirmed_crossing_intervals']),0);self.assertFalse(r['continuous_safety_certified'])
    def test_ccd_coplanar_root_SYNTHETIC_TEST_ONLY(self):
        a=np.array([[0.,0,0],[1,0,0],[0,1,0]]);b=a+[0,0,-1];d=np.tile([0.,0,2],(3,1));f=np.array([[0,1,2]])
        r=research_ccd(a,f,np.zeros_like(a),b,f,d,np.array([[0,0]]))
        self.assertTrue(any(x['class']=='COPLANAR_OVERLAP' for x in r['finite_contact_events']))
    def test_no_new_endpoints_or_runtime(self):
        for side in ['contract','expand']:
            r=read(OUT/side/'trajectory.json');self.assertFalse(r['runtime_eligible']);self.assertFalse(r['continuous_collision_certificate'])
            self.assertFalse(r['target_reached_by_discrete_predictors']);self.assertFalse(r['stop_is_global_feasibility_limit'])
    def test_five_level_full_static_checks(self):
        for side in ['contract','expand','regression_S1_expand']:
            r=read(OUT/side/'verification.json');self.assertTrue(r['sampled_gate_passed'])
            self.assertEqual([s['u'] for s in r['five_reference_chord_levels']],[0,.25,.5,.75,1.])
            for s in r['five_reference_chord_levels']:
                self.assertEqual(s['fixed_maximum_mm'],0);self.assertEqual(s['exact139_relative_maximum_mm'],0)
                for value in s['results'].values():self.assertEqual(value['confirmed_transverse_crossings'],0)
            self.assertTrue(all(x['cavity']['pass'] and x['tissue']['pass'] for x in r['accepted_segment_area_bounds']))
    def test_float32_failure_is_preserved(self):
        rows=read(OUT/'float32_quality_precheck.json');r=next(x for x in rows if x['side']=='contract' and x['mesh']=='cavity')
        self.assertFalse(r['all_float32_quality_passed']);self.assertIn(7680,r['levels'][-1]['bad_faces'])
        self.assertLess(r['levels'][-1]['minimum_area_ratio'],.8)
        self.assertFalse(r['actual_Godot_ArrayMesh_test_performed'])
    def test_ccd_unresolved_is_not_certified(self):
        for side in ['contract','expand']:
            r=read(OUT/side/'ccd_reference_chord.json.gz');self.assertFalse(r['continuous_safety_certified'])
            self.assertGreater(len(r['unresolved_coplanar_or_conditioned_pairs']),0)
    def test_finite_separating_axis_filter_keeps_crossing(self):
        from n20_stage_audit import finite_sat_filter
        a=np.array([[-1.,-1,0],[1,-1,0],[0,1,0]]);b=np.array([[0.,-.5,-1],[0,-.5,1],[0,.5,0]]);f=np.array([[0,1,2]])
        np.testing.assert_array_equal(finite_sat_filter(a,f,b,f,np.array([[0,0]])),np.array([[0,0]]))
    def test_recorded_checkpoint_replay(self):
        r=read(OUT/'trajectory_replay.json');self.assertTrue(all(x['all_replayed_within_1e_10_mm'] for x in r['records']))
        self.assertFalse(r['complete_adaptive_search_repeated'])
    def test_capacity_change_accounting_conserves(self):
        for side in ['contract','expand']:
            for state in read(OUT/side/'trajectory.json')['states']:
                r=state['capacity_attribution'];self.assertLess(abs(r['residual_mL']),1e-9)
                self.assertAlmostEqual(sum(x['delta_volume_mL'] for x in r['regions']),r['D2_actual_delta_mL'],places=10)
    def test_all_checkpoint_fixed_and_exact(self):
        fixed=self.a['port_fixed_masks'].any(0);root=PROJECT/'deformation/p2/evidence'
        exact=np.load(root/'coincident_mask.npy');ids=np.load(root/'coincident_cavity_vertex.npy');remote=np.load(root/'remote_anchors.npy')
        self.assertEqual(int(exact.sum()),139)
        for side in ['contract','expand']:
            for state in read(OUT/side/'trajectory.json')['states']:
                n=state['index'];c=np.load(OUT/side/f'cavity_{n:03}.npy');t=np.load(OUT/side/f'tissue_{n:03}.npy')
                self.assertTrue(np.all(c[fixed]==0));self.assertTrue(np.all(t[remote]==0));np.testing.assert_array_equal(t[exact],c[ids[exact]])
    def test_all_checkpoint_self_scans(self):
        for side in ['contract','expand']:
            r=read(OUT/side/'stage_audit.json');self.assertTrue(r['all_checkpoint_transverse_passed'])
            self.assertEqual(len(r['states']),len(read(OUT/side/'trajectory.json')['states']))
            for s in r['states']:self.assertEqual(s['offset_sha256'],sha(OUT/side/f"tissue_{s['index']:03}.npy"))
    def test_finite_face_risk_data_not_wall_thickness(self):
        r=read(OUT/'local_limit_diagnostics/summary.json')
        for row in r['states']:
            self.assertFalse(row['distance_is_tissue_thickness']);self.assertFalse(row['proxy_is_principal_curvature'])
            folder=OUT/'local_limit_diagnostics'/row['state'];ids=np.load(folder/'nearest_tissue_source_face_ids.npy');gap=np.load(folder/'finite_tissue_face_distance_mm.npy')
            self.assertEqual(len(ids),25024);self.assertTrue(np.isfinite(gap).all());self.assertTrue((gap>=0).all());self.assertTrue((ids<len(self.tf)).all())

if __name__=='__main__':
    start=time.time();suite=unittest.defaultTestLoader.loadTestsFromTestCase(N20Tests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    write(OUT/'python_tests.json',{'tests':result.testsRun,'passed':result.wasSuccessful(),'errors':[(str(t),e) for t,e in result.errors],
        'failures':[(str(t),e) for t,e in result.failures],'seconds':time.time()-start,'python':sys.version,'platform':platform.platform(),
        'synthetic_fixtures_used_as_actual_endpoints':False})
    sys.exit(0 if result.wasSuccessful() else 1)
