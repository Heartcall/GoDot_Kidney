"""N1.6 tests: actual integrals, preserved inputs, rejection policy and finite geometry."""
import unittest
from n16_feasibility import *
from n16_contacts import classify,self_bbox_pairs
import trimesh

class N16Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.a,cls.d2,cls.tv,cls.tf,cls.resolved,cls.approval=inputs();cls.root=OUT/'prototypes/thin_face_corrected'
    def reports(self):return [read(p/'preassessment.json') for p in sorted(self.root.iterdir()) if p.is_dir()]
    def test_reference_volume(self):self.assertAlmostEqual(volume(self.d2['reference_vertices'],self.d2['faces']),16.805962087430178,places=11)
    def test_D2_source_mapping(self):
        ids=np.unique(self.d2['faces']);np.testing.assert_allclose(map_d2(self.a['vertices'],self.d2)[ids],self.d2['reference_vertices'][ids],atol=1e-9,rtol=0)
    def test_source_hashes(self):
        self.assertGreater(protect(),2400)
        p2=PROJECT/'deformation/p2'
        for row in read(p2/'accepted_inputs.json')['arrays'].values():self.assertEqual(sha(REPO/row['source']),row['sha256'])
    def test_target_actual_integral(self):
        for r in self.reports():
            p=self.root/r['id'];d=np.load(p/'research_cavity_offset.npy');actual=volume(self.d2['reference_vertices']+map_d2(d,self.d2),self.d2['faces'])
            self.assertAlmostEqual(actual,r['target_mL'],places=9)
    def test_region_conservation(self):
        for r in self.reports():self.assertLess(abs(r['capacity_contribution']['residual_mL']),1e-9)
    def test_fixed_3675_vertices(self):
        fixed=self.a['port_fixed_masks'].any(0);self.assertEqual(int(fixed.sum()),3675)
        for r in self.reports():
            d=np.load(self.root/r['id']/'research_cavity_offset.npy')
            for u in LEVELS:np.testing.assert_array_equal((self.a['vertices']+u*d)[fixed],self.a['vertices'][fixed])
    def test_exact_tissue_coincidence_and_remote(self):
        exact=np.load(OUT/'tissue_exact_mask.npy');remote=np.load(OUT/'tissue_remote_mask.npy');ids=np.load(PROJECT/'deformation/p2/evidence/coincident_cavity_vertex.npy')
        self.assertEqual(exact.sum(),139)
        for r in self.reports():
            p=self.root/r['id'];c=np.load(p/'research_cavity_offset.npy');t=np.load(p/'research_tissue_offset.npy')
            np.testing.assert_array_equal(t[exact],c[ids[exact]]);self.assertTrue(np.all(t[remote]==0))
    def test_fresh_not_scaled_old_fields(self):
        old=np.load(PROJECT/'deformation/full_cavity/field/displacement.npy');new=np.load(OUT/'attempts/thin_face_corrected/research_expand_cavity_unit_response.npy')
        factor=float(np.sum(new*old)/np.sum(old*old));self.assertGreater(np.linalg.norm(new-factor*old)/np.linalg.norm(new),.05)
        ot=np.load(PROJECT/'deformation/p2/runtime/tissue_displacement.npy');nt=np.load(OUT/'attempts/thin_face_corrected/research_expand_tissue_unit_response.npy')
        factor=float(np.sum(nt*ot)/np.sum(ot*ot));self.assertGreater(np.linalg.norm(nt-factor*ot)/np.linalg.norm(nt),.05)
    def test_directions_independent(self):
        e=np.load(OUT/'attempts/thin_face_corrected/research_expand_cavity_unit_response.npy');c=np.load(OUT/'attempts/thin_face_corrected/research_contract_cavity_unit_response.npy')
        factor=-float(np.sum(c*e)/np.sum(e*e));self.assertGreater(np.linalg.norm(c+factor*e)/np.linalg.norm(c),.01)
    def test_unresolved_net_areas_not_used(self):
        r=read(OUT/'response_design.json');self.assertFalse(r['unresolved_sections_used_as_net_area'])
        for p in r['paths']:self.assertNotIn('B_27:25',p['trusted_station_ids']);self.assertNotIn('B_30:4',p['trusted_station_ids'])
    def test_all_natural_paths_move(self):
        field=np.load(OUT/'attempts/thin_face_corrected/research_expand_cavity_unit_response.npy')
        names=[p['id'] for p in self.resolved['paths']]
        for name in ['MAIN']+[f'B_{i:02}' for i in range(1,31)]:
            mask=self.a['path_owner']==names.index(name);self.assertGreater(np.linalg.norm(field[mask],axis=1).max(),1e-8)
    def test_cubic_integral_not_linear_capacity(self):
        for name in ['expand','contract']:
            field=map_d2(np.load(OUT/f'attempts/thin_face_corrected/research_{name}_cavity_unit_response.npy'),self.d2);co=volume_coefficients(self.d2['reference_vertices'],self.d2['faces'],field)
            self.assertGreater(abs(co[2]),1e-4)
            for q in [.01,.04,.09]:self.assertAlmostEqual(np.polynomial.polynomial.polyval(q,co),volume(self.d2['reference_vertices']+q*field,self.d2['faces']),places=10)
    def test_continuous_area_bounds_dense_fixture(self):
        v=np.array([[0.,0,0],[1,0,0],[0,1,0]]);f=np.array([[0,1,2]]);d=np.array([[0.,0,0],[0,.3,.1],[.2,-.1,.2]])
        r=continuous_area_bounds(v,f,d);values=[triangle_data(v+u*d,f)[1][0]/.5 for u in np.linspace(0,1,1001)]
        self.assertLessEqual(r['minimum_area_ratio'],min(values)+1e-10);self.assertGreaterEqual(r['maximum_area_ratio'],max(values)-1e-10)
    def test_finite_crossing_and_infinite_plane_false_candidate(self):
        a=np.array([[-1.,-1,0],[1,-1,0],[0,1,0]]);b=np.array([[0.,-.5,-1],[0,-.5,1],[0,.5,0]])
        r=classify(a,np.array([[0,1,2]]),b,np.array([[0,1,2]]),[[0,0]]);self.assertEqual(r['confirmed_transverse_crossings'],1)
        b[:,1]+=5;r=classify(a,np.array([[0,1,2]]),b,np.array([[0,1,2]]),[[0,0]]);self.assertEqual(r['confirmed_transverse_crossings'],0)
    def test_self_broad_phase_toy_coverage(self):
        v=np.array([[-1.,-1,0],[1,-1,0],[0,1,0],[0,-.5,-1],[0,-.5,1],[0,.5,0]]);f=np.array([[0,1,2],[3,4,5]])
        np.testing.assert_array_equal(self_bbox_pairs(v,f),np.array([[0,1]]))
    def test_reject_original_candidates(self):
        r=read(OUT/'comparison.json')['trials'];by={x['id']:x for x in r}
        self.assertEqual(by['S2_expand']['status'],'REJECTED_CURRENT_PROTOTYPE');self.assertEqual(by['S1_expand']['status'],'REJECTED_CURRENT_PROTOTYPE')
        self.assertFalse(by['S3_contract']['quality_pass']);self.assertFalse(by['S3_expand']['quality_pass'])
    def test_adjusted_sample_gate(self):
        r=read(OUT/'comparison.json')['trials'];by={x['id']:x for x in r}
        for name in ['S1_contract','A1_expand_contact_margin']:
            self.assertTrue(by[name]['quality_pass']);self.assertTrue(by[name]['sampled_contact_pass'])
            for s in by[name]['contact_samples']:self.assertEqual(s['cavity_tissue_confirmed'],0)
    def test_no_new_coplanar_overlaps_in_recommended_pair(self):
        baseline=read(OUT/'contact_baseline.json')['results'];pairs=lambda r:{(x['cavity_face'],x['tissue_face']) for x in r.get('rows',[]) if x['class']=='COPLANAR_OVERLAP'}
        for name in ['S1_contract','A1_expand_contact_margin']:
            for u in [.25,.5,.75,1.]:
                z=read(self.root/name/'contacts'/f'u{round(u*100):03}.json')['results']
                self.assertEqual(pairs(z['cavity_tissue']),pairs(baseline['cavity_tissue']))
                for k in ['cavity_self','D2_self','tissue_self']:self.assertFalse(pairs(z[k]))
    def test_closure_variants_audit(self):
        for name in ['S1_contract','A1_expand_contact_margin']:
            r=read(self.root/name/'closure_sensitivity.json');self.assertFalse(r['D2_reference_changed'])
            for s in r['sampled_levels']:
                self.assertEqual(len(s['valid_alternative_volumes_mL']),3)
                self.assertLess(s['valid_alternative_spread_mL'],.0002)
    def test_recommendation_not_promoted_or_physiological(self):
        r=read(OUT/'engineering_capacity_estimate.json');self.assertEqual(r['label'],LABEL);self.assertFalse(r['runtime_eligible']);self.assertFalse(r['N2_authorized'])
        self.assertLess(r['V_min_estimated_mL'],r['V_reference_mL']);self.assertGreater(r['V_max_estimated_mL'],r['V_reference_mL'])
        m=read(PROJECT/'deformation/capacity_v2_n15_m_v1/real_parameter_status.json')
        for key in ['V_min_mL','V_max_mL','pressure','compliance','real_flow_mL_s']:self.assertIsNone(m[key])
    def test_state_from_reference_zero_drift(self):
        v=self.a['vertices'];c=np.load(self.root/'S1_contract/research_cavity_offset.npy');e=np.load(self.root/'A1_expand_contact_margin/research_cavity_offset.npy')
        for s in [-1,-.5,0,.5,1,0]:pose=v+(-s*c if s<0 else s*e)
        np.testing.assert_array_equal(pose,v)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(N16Tests))
    write(OUT/'python_tests.json',{'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'passed':result.wasSuccessful(),'protected_files':protect()})
    raise SystemExit(0 if result.wasSuccessful() else 1)
