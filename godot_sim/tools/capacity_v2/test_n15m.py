"""Offline N1.5-M regression: identifiability, conservation, provenance and no promotion."""
import unittest, json, math
import numpy as np
from n15m_sources import OUT, REPO, read, sha, protect, write
from n15m_calibration import (TAG,volume_mL,pressure_Pa,rank_report,fit_synthetic_imaging,
  integrate_balance,fluid_to_lumen,pressure_branch,approval_gate,write_synthetic_result)

class CalibrationTests(unittest.TestCase):
    def fixture(self):return read(OUT/'synthetic/fixture.json')
    def candidate(self):
        return dict(label='NOT_PATIENT_TEST_CANDIDATE',domain_mapping_verified=True,operational_conditions_approved=True,
          endpoint_coverage_verified=True,uncertainty_reviewed=True,source_provenance_verified=True,legal_data_access_verified=True,
          medical_review_signed=True,user_review_signed=True,evidence_grade='E1',inferential_target='INDIVIDUAL_OPERATIONAL_ENDPOINTS',
          V_min_mL=90.,V_reference_D2_mL=100.,V_max_mL=115.,interval_type='CONFIDENCE',source_hashes=['synthetic-test-hash'],model_version='test-only')
    def test_volume_units(self):
        self.assertEqual(volume_mL(1000,'mm3'),1);self.assertEqual(volume_mL(1,'cm3'),1)
    def test_units_not_guessed(self):
        for x,u in [(float('nan'),'mL'),(-1,'mL'),(1,'cc'),(1,'m3')]:
            with self.assertRaises(ValueError):volume_mL(x,u)
    def test_pressure_conversion_only(self):
        self.assertAlmostEqual(pressure_Pa(1,'mmHg')/pressure_Pa(1,'cmH2O'),1.35951,places=4)
        with self.assertRaises(ValueError):pressure_Pa(1,'mm H20')
    def test_single_reference_unidentifiable(self):
        r=rank_report([[1,0,0]]);self.assertEqual(r['nullity'],2);self.assertFalse(r['identifiable'])
    def test_two_states_not_enough_for_quadratic(self):
        self.assertFalse(rank_report([[1,-1,1],[1,1,1]])['identifiable'])
    def test_three_known_states(self):self.assertTrue(rank_report([[1,-1,1],[1,0,0],[1,1,1]])['identifiable'])
    def test_unknown_domain_bias_confounds_absolute_offset(self):
        self.assertEqual(rank_report([[1,-1,1,1],[1,0,0,1],[1,1,1,1]])['nullity'],1)
    def test_synthetic_fit_asymmetric(self):
        r=fit_synthetic_imaging(self.fixture());np.testing.assert_allclose(r['coefficients'],[100,12,3],atol=1e-10)
        lo,ref,hi=r['test_endpoint_values_mL'];self.assertNotAlmostEqual((lo+hi)/2,ref)
    def test_unknown_state_rejected(self):
        f=self.fixture();f['observations'][0]['state']=None
        with self.assertRaises(ValueError):fit_synthetic_imaging(f)
    def test_unknown_domain_mapping_rejected(self):
        f=self.fixture();f['observations'][0]['domain_bias_mL']=None
        with self.assertRaises(ValueError):fit_synthetic_imaging(f)
    def test_invalid_domain_correction_rejected(self):
        for value in [float('nan'),1000.]:
            f=self.fixture();f['observations'][0]['domain_bias_mL']=value
            with self.assertRaises(ValueError):fit_synthetic_imaging(f)
    def test_no_unobserved_endpoint_extrapolation(self):
        f=self.fixture();f['observations']=[r for r in f['observations'] if r['state']!=1]
        with self.assertRaises(ValueError):fit_synthetic_imaging(f)
    def test_non_synthetic_rejected_by_fitter(self):
        f=self.fixture();f['label']='REAL'
        with self.assertRaises(ValueError):fit_synthetic_imaging(f)
    def balance(self,**kw):
        args=dict(t=[0,1,3],q_in=[3]*3,q_out=[2]*3,q_leak=[.2]*3,q_urine=[.1]*3,q_external_storage=[.1]*3,label=TAG)
        args.update(kw);return integrate_balance(**args)
    def test_mass_conservation_irregular_time(self):
        r=self.balance(V_initial_mL=100);np.testing.assert_allclose(r['delta_volume_mL'],[0,.8,2.4]);self.assertAlmostEqual(r['absolute_volume_mL'][-1],102.4)
    def test_missing_initial_only_difference_identified(self):
        r=self.balance();self.assertIsNone(r['absolute_volume_mL']);self.assertIsNotNone(r['delta_volume_mL'])
    def test_missing_leak_not_zero(self):
        r=self.balance(q_leak=None);self.assertFalse(r['identified']);self.assertIsNone(r['delta_volume_mL'])
    def test_flow_time_and_units(self):
        for kwargs in [dict(t=[0,0,3]),dict(t=[0,float('nan'),3]),dict(flow_unit='mL/min'),dict(q_out=[2,3]),dict(q_in=[-1]*3)]:
            with self.assertRaises(ValueError):self.balance(**kwargs)
    def test_device_occupancy(self):
        self.assertEqual(fluid_to_lumen(100,2,0,0,TAG),102);self.assertIsNone(fluid_to_lumen(100,None,0,0,TAG))
    def test_history_separated_and_no_extrapolation(self):
        p=[0,1,2];load=pressure_branch(p,[100,101,102],[1],label=TAG,branch='LOADING')
        unload=pressure_branch(p,[100,101.5,102],[1],label=TAG,branch='UNLOADING');self.assertNotEqual(load[0],unload[0])
        with self.assertRaises(ValueError):pressure_branch(p,[100,101,102],[3],label=TAG,branch='LOADING')
    def test_mixed_branch_rejected(self):
        with self.assertRaises(ValueError):pressure_branch([0,1,1,2],[100,101,101.5,102],[1],label=TAG,branch='LOADING')
    def test_synthetic_cannot_be_approved(self):
        c=self.candidate();c['label']=TAG;self.assertFalse(approval_gate(c)['eligible_for_human_review'])
    def test_gate_never_grants_approval(self):
        r=approval_gate(self.candidate());self.assertTrue(r['eligible_for_human_review']);self.assertFalse(r['approved'])
    def test_reference_outside_requires_review(self):
        c=self.candidate();c['V_reference_D2_mL']=120;self.assertFalse(approval_gate(c)['eligible_for_human_review'])
    def test_static_population_quantiles_not_dynamic_endpoints(self):
        c=self.candidate();c['inferential_target']='STATIC_POPULATION_QUANTILES';self.assertFalse(approval_gate(c)['eligible_for_human_review'])
    def test_mechanistic_evidence_and_unresolved_E2_blocked(self):
        for grade in ['E2','E3','E4']:
            c=self.candidate();c['evidence_grade']=grade;self.assertFalse(approval_gate(c)['eligible_for_human_review'])
    def test_unverified_source_or_missing_medical_review(self):
        for field in ['domain_mapping_verified','legal_data_access_verified','medical_review_signed','endpoint_coverage_verified']:
            c=self.candidate();c[field]=False;self.assertFalse(approval_gate(c)['eligible_for_human_review'])
    def test_synthetic_sink_isolated(self):
        for path in [OUT/'real_parameter_status.json',REPO/'godot_sim/main.tscn']:
            with self.assertRaises(ValueError):write_synthetic_result(path,{'label':TAG})
    def test_real_fields_null_and_reference_unchanged(self):
        r=read(OUT/'real_parameter_status.json')
        for key in ['V_min_mL','V_max_mL','pressure','compliance','real_flow_mL_s','patient_interval']:self.assertIsNone(r[key])
        self.assertEqual(r['V_reference_D2_mL'],16.805962087430178)
        self.assertEqual(sha(REPO/r['D2_approval_path']),r['D2_approval_sha256'])
    def test_shared_mapping_error_not_averaged_away(self):
        r=read(OUT/'synthetic/result.json')['uncertainty'];self.assertTrue(min(r['absolute_sd_mL'])>1.9);self.assertLess(r['paired_change_sd_mL'],.5)
    def test_evidence_fields_and_provenance(self):
        matrix=read(OUT/'evidence_matrix.json');self.assertEqual(len(matrix['studies']),28)
        fields=['title','authors','year','journal','DOI','url','population','sample_size','measured_domain','ureter_cutoff',
          'method','boundary_conditions','capacity_definition','capacity_unit','measurement_times','capacity_distribution',
          'paired_change','absolute_initial_capacity_obtained','inflow_data_obtained','outflow_data_obtained','leakage_data_obtained',
          'hysteresis_information','measurement_uncertainty','grade','grade_reason','locator','access','supplement_status']
        for r in matrix['studies']:
            for f in fields:self.assertIn(f,r)
            self.assertFalse(r['patient_endpoint_usable_now'])
            self.assertIn(r['grade'],['E1','E2','E3','E4'])
            if r.get('metadata_file'):self.assertEqual(sha(OUT/r['metadata_file']),r['metadata_sha256'])
        byid={r['id']:r for r in matrix['studies']}
        self.assertEqual(byid['M22']['DOI'],'10.1177/17562872251314809')
        self.assertIn('sinus',byid['M10']['measured_domain'])
        self.assertEqual(byid['M20']['population'],'PORCINE_IN_VIVO')
    def test_search_dedup_counts(self):
        d=read(OUT/'literature/deduplication.json');s=read(OUT/'literature/supplement_log.json')
        self.assertEqual(d['retrieved_query_records'],231);self.assertEqual(d['unique_PMIDs'],220)
        self.assertEqual(len(set(d['PMIDs'])|set(s['new_PMIDs'])),234)
        c=read(OUT/'literature/citation_followup_log.json');self.assertEqual(len(set(d['PMIDs'])|set(s['new_PMIDs'])|set(c['PMIDs'])),236)
    def test_protected_inputs(self):
        self.assertGreaterEqual(protect(),2487)
        approval=read(REPO/'godot_sim/deformation/capacity_v2_n1_v1/D2_approval_2026_10_14_v1.json')
        for name,h in approval['frozen_geometry_sha256'].items():
            self.assertEqual(sha(REPO/'godot_sim/deformation/capacity_v2_n1_v1/d2'/name),h)
        p2=REPO/'godot_sim/deformation/p2';accepted=read(p2/'accepted_inputs.json')
        for name,r in accepted['arrays'].items():
            self.assertEqual(r['sha256'],approval['accepted_source_sha256'][name])
            self.assertEqual(sha(p2/r['runtime']),r['sha256'])
            self.assertEqual(sha(REPO/r['source']),r['sha256'])

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(CalibrationTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    write(OUT/'tests.json',{'stage':'N1.5-M','tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
      'passed':result.wasSuccessful(),'protected_files':protect(),'synthetic_only':True})
    raise SystemExit(0 if result.wasSuccessful() else 1)
