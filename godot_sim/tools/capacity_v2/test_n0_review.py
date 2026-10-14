"""N0 source-preservation, local-cut, finite-contact and actual-runtime tests."""
from n0_common import *
import unittest,contextlib,io
import build_n0_domains as domains
from diagnose_n0_contacts import classify_pair

class N0Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _,cls.a=verify_sources();cls.report=read_json(OUT/'domain_candidates.json');cls.rows=cls.report['candidates'];cls.meta=read_json(OUT/'review_preview.json')
    def test_all_protected_files_unchanged(self):self.assertGreaterEqual(protected(),1157)
    def test_six_inputs_and_fixed_3675_exact(self):
        verify_sources();mask=np.load(PROJECT/'deformation/p2/evidence/port_fixed_masks.npy').any(0)
        self.assertEqual(mask.sum(),3675);self.assertTrue(np.all(self.a['cavity_displacement'][mask]==0))
    def test_missing_original_provenance_not_fabricated(self):
        r=read_json(OUT/'source_inventory.json');self.assertEqual(len(r['geometry_or_segmentation_files']),2)
        self.assertFalse(r['pre_artificial_natural_geometry_found']);self.assertFalse(r['original_segmentation_found']);self.assertFalse(r['reversible_preprocessing_recipe_found'])
    def test_effective_capacity_remains_null_and_all_pending(self):
        self.assertIsNone(self.report['V_reference_effective_mL']);self.assertIsNone(self.meta['V_reference_effective_mL'])
        for r in self.rows:self.assertIsNone(r['V_reference_effective_mL']);self.assertEqual(r['review_status'],'PENDING_USER_ANATOMICAL_REVIEW')
    def test_all_12_main_candidates_closed_and_consistent(self):
        self.assertEqual(len(self.rows),12)
        for r in self.rows:
            t=r['topology'];self.assertTrue(r['geometry_valid']);self.assertTrue(t['watertight'] and t['winding_consistent'])
            self.assertEqual(t['boundary_edges']+t['nonmanifold_edges']+t['degenerate_faces'],0);self.assertEqual(t['face_components'],1)
    def test_cap_finite_intersections_none_except_boundary_contacts(self):
        for r in self.rows:
            self.assertEqual(r['cap_checks']['cap_wall_invalid_count'],0);self.assertFalse(r['cap_checks']['cap_cap_invalid_pairs'])
            self.assertEqual(r['cap_against_all_original_walls']['invalid_count'],0)
            for cut in r['cuts']:self.assertLess(cut['maximum_section_nonplanarity_mm'],1e-10)
    def test_multi_method_volume_and_additivity(self):
        for r in self.rows:
            self.assertLess(r['volume_checks']['spread_mm3'],3e-6);self.assertLess(r['volume_checks']['sum_cut_additivity_error_mm3'],1e-7)
            self.assertLess(r['candidate_measurement_volume_mL'],self.report['D0_volume_mL'])
    def test_all_source_vertices_exact_and_new_vertices_barycentric(self):
        ref=self.a['cavity_reference_vertices']
        for r in self.rows:
            d=OUT/'domains'/r['id'];v=np.load(d/'reference_vertices.npy');ids=np.load(d/'source_vertex_ids.npy');w=np.load(d/'source_vertex_weights.npy')
            np.testing.assert_array_equal(v[:len(ref)],ref);self.assertTrue((w>=-1e-14).all());np.testing.assert_allclose(w.sum(1),1,atol=1e-14,rtol=0)
            reconstructed=np.sum(ref[np.maximum(ids,0)]*w[:,:,None],axis=1);np.testing.assert_allclose(v,reconstructed,atol=5e-14,rtol=0)
    def test_real_faces_have_valid_parent_and_caps_explicit(self):
        original=self.a['cavity_faces']
        for r in self.rows:
            d=OUT/'domains'/r['id'];f=np.load(d/'faces.npy');source=np.load(d/'source_face_ids.npy');cap=np.load(d/'virtual_port_labels.npy')
            self.assertTrue(np.all(source[cap>0]==-1));self.assertTrue(np.all(source[cap==0]>=0));self.assertEqual(int((cap>0).sum()),r['virtual_cap_triangles'])
            split=set(i for c in r['cuts'] for i in c['split_source_face_ids']);unchanged=(cap==0)&~np.isin(source,list(split))
            np.testing.assert_array_equal(f[unchanged],original[source[unchanged]])
    def test_rejected_anatomical_cuts_never_promoted(self):
        lookup={r['id']:r for r in self.rows};bad=lookup['C01_transition_mid']
        self.assertIn('T_09',bad['excluded_natural_marker_ids']);self.assertIn('B_13',bad['natural_paths_with_outside_samples']);self.assertTrue(bad['anatomical_recommendation'].startswith('REJECT'))
        for name in ['C00_distal_control','C06_near_BASE','C07_IN01_collar','C08_IN02_collar','C09_UPJ_proximal_unconfirmed','C10_UPJ_distal_unconfirmed','C11_inlet_distal_control']:
            self.assertFalse(lookup[name]['excluded_natural_marker_ids']);self.assertFalse(lookup[name]['natural_paths_with_outside_samples'])
    def test_centerline_retention_not_anatomical_wall_certification(self):
        lookup={r['id']:r for r in self.rows};self.assertIn('IN_02',lookup['C06_near_BASE']['wide_chamber_cut_warning'])
        self.assertFalse(lookup['C11_inlet_distal_control']['wide_chamber_cut_warning'])
    def test_terminals_all_22_have_source_faces_unknown_semantics(self):
        r=read_json(OUT/'terminal_boundary_inventory.json');self.assertEqual(len(r['terminals']),22)
        for t in r['terminals']:self.assertTrue(t['geometric_candidate_face_ids']);self.assertTrue(t['virtual_cap_provenance'].startswith('UNKNOWN'))
    def test_six_small_plane_offset_variants_auditable(self):
        r=read_json(OUT/'section_sensitivity.json');self.assertEqual(len(r['variants']),6)
        for row in r['variants']:self.assertTrue(row['geometry_valid']);self.assertEqual(row['anatomical_approval'],'PENDING');self.assertTrue(row['output_sha256'])
    def test_box_cut_has_known_volume(self):
        mesh=trimesh.creation.box(extents=[1,1,1]);v,f=np.array(mesh.vertices),np.array(mesh.faces)
        vv,ff,ss,cc,ww,info,_=domains.local_cut(v,f,np.arange(len(f)),np.zeros(len(f),int),[{i:1.} for i in range(len(v))],np.array([0,0,.13]),np.array([0,0,1.]),np.array([0,0,.5]),1)
        self.assertAlmostEqual(signed_volume(vv,ff),.63,places=12);self.assertAlmostEqual(info['additivity_error_mm3'],0,places=12)
    def test_local_plane_keeps_other_u_tube_arm(self):
        centers=np.array([[-3,0,2],[-3,0,-2],[3,0,-2],[3,0,2]],float);rings=[];n=16
        for i,p in enumerate(centers):
            tangent=centers[min(i+1,3)]-centers[max(0,i-1)];tangent/=np.linalg.norm(tangent);e=np.array([0,1,0.]);b=np.cross(tangent,e)
            rings.extend(p+.2*(np.cos(k*2*np.pi/n)*e+np.sin(k*2*np.pi/n)*b) for k in range(n))
        v=np.array(rings);faces=[]
        for i in range(3):
            for k in range(n):
                a,b,c,d=i*n+k,i*n+(k+1)%n,(i+1)*n+k,(i+1)*n+(k+1)%n;faces.extend([[a,b,d],[a,d,c]])
        # End fans only in synthetic topology test, never in measurement construction.
        v=np.vstack([v,centers[0],centers[-1]])
        for k in range(n):faces.extend([[len(v)-2,(k+1)%n,k],[len(v)-1,3*n+k,3*n+(k+1)%n]])
        f=np.array(faces);m=trimesh.Trimesh(v,f,process=False)
        if m.volume<0:f=f[:,::-1]
        vv,ff,ss,cc,ww,info,_=domains.local_cut(v,f,np.arange(len(f)),np.zeros(len(f),int),[{i:1.} for i in range(len(v))],np.array([-3,0,.13]),np.array([0,0,1.]),centers[0],1)
        self.assertEqual(len(info['all_plane_loops']),2);self.assertTrue(set(range(3*n,4*n)).issubset(set(ff.ravel())))
    def primitive(self,a,b):
        return classify_pair(np.array(a,float),np.array([[0,1,2]]),np.array(b,float),np.array([[0,1,2]]),0,0,0,True,{'test':{'center_mm':ORIGIN.tolist()}})
    def test_finite_transverse_crossing_primitive_detected(self):
        r=self.primitive([[-1,-1,0],[1,-1,0],[0,1,0]],[[0,0,-1],[0,0,1],[.5,0,0]])
        self.assertEqual(r['class'],'FINITE_TRANSVERSE_CROSSING');self.assertGreater(r['finite_segment_length_mm'],0)
    def test_edge_contact_is_not_transverse_crossing(self):
        r=self.primitive([[0,0,0],[1,0,0],[0,1,0]],[[0,0,0],[1,0,0],[0,0,1]])
        self.assertEqual(r['class'],'EDGE_CONTACT');self.assertAlmostEqual(r['finite_segment_length_mm'],1)
    def test_point_coplanar_and_near_disjoint_primitives(self):
        a=[[0,0,0],[1,0,0],[0,1,0]]
        self.assertEqual(self.primitive(a,[[0,0,0],[-1,0,1],[0,-1,1]])['class'],'POINT_CONTACT_OR_TANGENCY')
        self.assertEqual(self.primitive(a,a)['class'],'COPLANAR_OVERLAP')
        self.assertEqual(self.primitive(a,np.array(a)+[0,0,.001])['class'],'NEAR_DISJOINT')
    def test_all_five_contact_levels_classified_without_unresolved_cross(self):
        rows=read_json(OUT/'contact_summary.json')['levels'];self.assertEqual(len(rows),10)
        for r in rows:
            self.assertEqual(r['confirmed_transverse_crossings'],0);self.assertEqual(r['counts'].get('FINITE_INTERSECTION_REQUIRES_REVIEW',0),0)
            self.assertEqual(r['finite_epsilon_mm'],1e-10);self.assertGreater(r['counts'].get('COPLANAR_OVERLAP',0),0)
    def test_actual_float32_contact_scan_has_real_p23_exports(self):
        for r in read_json(OUT/'contact_summary.json')['levels']:
            if r['coordinate_space']=='actual_float32':
                for key in ['cavity_positions_source','tissue_positions_source']:self.assertEqual(r[key]['kind'],'ACTUAL_P23_ARRAYMESH_EXPORT');self.assertTrue(r[key]['positions_bit_equal'])
    def test_visual_issue_left_open_for_user(self):
        self.assertFalse(read_json(OUT/'contact_summary.json')['user_visual_anomaly_reproduced']);self.assertEqual(self.meta['user_visual_anomaly_status'],'NOT_SPECIFICALLY_REPRODUCED_NEEDS_USER_CAMERA_OR_LOCATION')
    def test_new_contact_indices_rechecked_in_reference_geometry(self):
        for r in read_json(OUT/'contact_changes.json')['records']:
            self.assertEqual(r['new_confirmed_transverse_crossings'],0)
            self.assertTrue(set(r['new_pair_reference_classes']).issubset({'POINT_CONTACT_OR_TANGENCY','EDGE_CONTACT'}))
            self.assertLess(r['max_distance_to_original_contact_sample_cloud_mm'],.2)
    def test_coplanar_groups_available_in_review_menu(self):
        groups=read_json(OUT/'contact_groups.json')['groups'];self.assertTrue(groups)
        self.assertTrue(any(r['class']=='COPLANAR_OVERLAP' for r in self.meta['review_pairs']))
    def test_graphical_runtime_and_exact_accepted_arrays_both_backends(self):
        for backend in ['compatibility','forward']:
            directory=OUT/'verification'/backend;r=read_json(directory/'runtime_checks.json');self.assertEqual(r['failures'],0)
            for name,n,m in [('cavity',25024,50044),('tissue',155904,311844)]:
                for tag,u in [(f'u{x:03}',x/100) for x in [0,25,50,75,100,37]]+[('restored',0)]:
                    raw=(directory/f'{name}_{tag}.bin').read_bytes();self.assertEqual(len(raw),n*24+m*12)
                    p=np.frombuffer(raw,'<f4',count=n*3).reshape(-1,3);ids=np.frombuffer(raw,'<i4',offset=n*24).reshape(-1,3)
                    expected=(self.a[name+'_reference_vertices']-ORIGIN).astype(np.float32)+np.float32(u)*self.a[name+'_displacement'].astype(np.float32)
                    np.testing.assert_array_equal(p,expected);np.testing.assert_array_equal(ids,self.a[name+'_faces'][:,::-1])
                    old=PROJECT/'analysis/irrigation_baseline/p23/final_regression_forward'/f'{name}_{tag}.bin'
                    self.assertEqual(raw,old.read_bytes())
    def test_repeat_measurement_arrays_and_binaries_identical(self):
        original=domains.OUT
        try:
            domains.OUT=OUT/'verification/rebuild'
            with contextlib.redirect_stdout(io.StringIO()):row=domains.build_candidate('C06_near_BASE',{'BLADDER':.5,'IN_01':.98,'IN_02':.98})
            source=OUT/'domains/C06_near_BASE'
            for p in source.iterdir():
                if p.suffix in ('.npy','.bin') or p.name in ['cap_contact_details.json','cap_original_contact_details.json']:self.assertEqual(sha(p),sha(domains.OUT/'domains/C06_near_BASE'/p.name))
        finally:domains.OUT=original

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(N0Tests))
    write_json(OUT/'verification/python_tests.json',{'tests':result.testsRun,'passed':result.wasSuccessful(),'failures':len(result.failures),'errors':len(result.errors),'scope':'N0 engineering review only; no anatomical capacity acceptance.'})
    raise SystemExit(0 if result.wasSuccessful() else 1)
