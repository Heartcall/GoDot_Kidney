"""N1 source provenance, finite sections, conservative candidate accounting tests."""
from n1_analysis import *
import unittest

class N1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.approval=read_json(ROOT/'D2_approval_2026_10_14_v1.json')
        cls.volume=read_json(ROOT/'D2_independent_volume.json')
        cls.data=json.loads(gzip.decompress((ROOT/'sections.json.gz').read_bytes()))
        cls.records=cls.data['stations'];cls.analyzer=SectionAnalyzer()
        cls.partition=read_json(ROOT/'capacity_partition_candidate.json')

    def test_protected_and_accepted_inputs(self):self.assertGreaterEqual(protect(),2059)

    def test_approval_is_engineering_definition_not_physiology(self):
        a=self.approval;self.assertTrue(a['D2_project_definition_approved']);self.assertTrue(a['N0_closed'])
        self.assertFalse(a['independent_medical_anatomy_validation']);self.assertIsNone(a['normal_V_min_mL']);self.assertIsNone(a['normal_V_max_mL'])
        self.assertEqual(a['domain_id'],'C11_R1_IN02_fixed_collar')

    def test_frozen_R1_is_byte_identical(self):
        for name,digest in self.approval['frozen_geometry_sha256'].items():
            self.assertEqual(sha(ROOT/'d2'/name),digest);self.assertEqual(sha(R1/name),digest)

    def test_independent_volume_topology(self):
        r=volume_review(self.analyzer.v,self.analyzer.f)
        self.assertTrue(r['watertight']);self.assertTrue(r['winding_consistent']);self.assertEqual(r['boundary_edges']+r['nonmanifold_edges']+r['degenerate_faces'],0)
        self.assertLess(r['method_spread_mm3'],3e-6);self.assertAlmostEqual(r['V_reference_D2_mm3']/1000,self.approval['V_reference_D2_mL'],places=12)

    def test_all_required_paths_J_T_and_transitions_present(self):
        ids={r['path_id'] for r in self.records}
        self.assertTrue({'MAIN','BLADDER_TRANSITION','B_31','B_32'}<=ids)
        self.assertTrue({'B_%02d'%i for i in range(1,31)}<=ids)
        nodes={n['id'] for n in self.data['nodes']}
        self.assertEqual(nodes,{'J_%02d'%i for i in range(1,10)}|{'T_%02d'%i for i in range(1,23)})
        for node in self.data['nodes']:self.assertGreater(len(node['probe_station_ids']),0)

    def test_actual_stations_on_approved_polylines_and_normals(self):
        for r in self.records:
            p=self.analyzer.by_id[r['path_id']]
            np.testing.assert_allclose(r['position_mm'],path_station(p,r['station_arc_mm']),atol=1e-13,rtol=0)
            self.assertAlmostEqual(np.linalg.norm(r['plane_normal_unit']),1,places=12)

    def test_every_ring_has_source_face_and_edge_mapping(self):
        a=self.analyzer
        for r in self.records[::17]:
            for loop in r['loops']:
                edge=np.array(loop['ring_D2_edge_vertex_ids_and_t']);ids=edge[:,:2].astype(int);t=edge[:,2,None]
                pts=a.v[ids[:,0]]*(1-t)+a.v[ids[:,1]]*t
                np.testing.assert_allclose(pts,loop['ring_positions_mm'],atol=3e-14,rtol=0)
                self.assertLess(np.max(abs((pts-r['position_mm'])@r['plane_normal_unit'])),1e-10)
                np.testing.assert_array_equal(a.source[loop['segments_D2_face_ids']],loop['segments_source_face_ids'])

    def test_ambiguous_sections_never_become_valid_branch_metrics(self):
        self.assertGreater(sum(r['status']=='AMBIGUOUS_TOPOLOGY' for r in self.records),0)
        for r in self.records:
            if r['status'] not in ['PATH_LOCAL_SECTION','SHARED_JUNCTION_OR_INTERFACE_SECTION']:self.assertIsNone(r['metrics'])
            if r['metrics']:
                self.assertTrue(r['loops'][r['selected_loop']]['contains_station']);self.assertTrue(r['loops'][r['selected_loop']]['simple'])
                self.assertGreater(r['metrics']['area_mm2'],0);self.assertGreaterEqual(r['metrics']['major_axis_mm'],r['metrics']['minor_axis_mm'])

    def test_rectangle_area_moments_and_ellipse_axes(self):
        m=section_metrics(np.array([[-2,-1],[2,-1],[2,1],[-2,1]],float))
        self.assertAlmostEqual(m['area_mm2'],8);self.assertAlmostEqual(m['perimeter_mm'],12)
        self.assertAlmostEqual(m['major_axis_mm']/m['minor_axis_mm'],2);self.assertAlmostEqual(m['flattening_1_minus_minor_major'],.5)

    def test_self_crossing_polygon_rejected(self):
        self.assertFalse(section_polygon_info(np.array([[-1,-1],[1,1],[-1,1],[1,-1]],float))[1])

    def toy(self,offset):
        first=trimesh.creation.cylinder(radius=1,height=4,sections=40)
        second=trimesh.creation.cylinder(radius=2,height=4,sections=40);second.apply_translation([offset,0,0])
        a=SectionAnalyzer.__new__(SectionAnalyzer);a.v=np.vstack([first.vertices,second.vertices]);a.f=np.vstack([first.faces,second.faces+len(first.vertices)])
        a.source=np.arange(len(a.f));a.wids=np.c_[np.arange(len(a.v)),np.full((len(a.v),2),-1)];a.w=np.tile([1.,0,0],(len(a.v),1))
        a.owner=np.r_[np.zeros(len(first.vertices),int),np.ones(len(second.vertices),int)]
        p={'id':'MAIN','length_mm':4.,'points_mm':[[0,0,-2],[0,0,2]],'marker_names':['A','B']}
        a.paths=[p,{'id':'OTHER'}];a.neighbors={'MAIN':{'MAIN'}}
        return a,p

    def test_nearby_larger_disconnected_loop_not_selected(self):
        a,p=self.toy(5);r=a.section(p,2.,0)
        self.assertEqual(r['status'],'PATH_LOCAL_SECTION');self.assertEqual(len(r['loops']),2)
        self.assertAlmostEqual(r['metrics']['area_mm2'],40*math.sin(2*math.pi/40)/2,places=10)

    def test_nested_loops_not_silently_filled(self):
        a,p=self.toy(0);r=a.section(p,2.,0)
        self.assertEqual(r['status'],'NESTED_OR_AMBIGUOUS_CONTAINING_LOOPS');self.assertIsNone(r['metrics'])

    def test_offset_hole_not_silently_ignored(self):
        a,p=self.toy(0);n=len(a.v)//2;a.v[n:,:2]*=.1;a.v[n:,0]+=.6
        r=a.section(p,2.,0);self.assertEqual(r['status'],'MULTIRING_WITH_HOLE_UNRESOLVED');self.assertIsNone(r['metrics'])

    def test_candidate_cells_unique_and_conserve_with_explicit_complement(self):
        g=np.load(ROOT/'partition_cube_grid_indices.npy');labels=np.load(ROOT/'partition_cube_regions.npy')
        self.assertEqual(len(g),len(np.unique(g,axis=0)));self.assertEqual(len(g),len(labels));p=self.partition
        self.assertGreater(p['boundary_remainder_mL'],0);self.assertLess(abs(p['residual_mm3']),1e-8)
        self.assertAlmostEqual(sum(r['candidate_volume_mL'] for r in p['regions']),self.approval['V_reference_D2_mL'],places=11)
        self.assertEqual(p['status'],'CANDIDATE_NOT_FORMAL_BRANCH_CAPACITY')

    def test_candidate_cells_distance_margin_and_parity(self):
        import open3d as o3d
        points=np.load(ROOT/'partition_cube_centers_mm.npy')[::13]
        sd=ray_scene(self.analyzer.v,self.analyzer.f).compute_signed_distance(o3d.core.Tensor((points-ORIGIN).astype('float32')),nsamples=5).numpy()
        self.assertTrue(np.all(sd<-(math.sqrt(3)*.5/2+2e-4)))

    def test_geodesic_propagation_stays_on_six_neighbor_interior(self):
        g=np.load(ROOT/'partition_cube_grid_indices.npy');pred=np.load(ROOT/'partition_geodesic_predecessor.npy');owners=np.load(ROOT/'partition_cube_path_owner.npy');ok=pred>=0
        self.assertTrue(np.all(np.abs(g[ok]-g[pred[ok]]).sum(1)==1));np.testing.assert_array_equal(owners[ok],owners[pred[ok]])

    def test_resolution_and_candidate_boundary_sensitivity_are_reported(self):
        p=read_json(ROOT/'partition_resolution_sensitivity.json');self.assertEqual(p['coarse']['grid_mm'],.75);self.assertEqual(p['fine']['grid_mm'],.5)
        self.assertNotEqual(p['coarse']['boundary_remainder_mL'],p['fine']['boundary_remainder_mL'])
        for row in p['fine']['boundary_sensitivity']:self.assertAlmostEqual(sum(row['region_volume_mL'].values()),p['fine']['D2_total_mL'],places=11)

    def test_original_N0_pending_history_not_overwritten(self):
        old=read_json(PROJECT/'deformation/capacity_v2_n0_closeout/human_review_2026_10_14_v1.json')
        self.assertFalse(old['D2_approved']);self.assertTrue(self.approval['D2_project_definition_approved'])

    def test_reference_preview_separates_caps_and_candidate_classification(self):
        p=read_json(ROOT/'review_preview.json');self.assertEqual(p['approval_sha256'],sha(ROOT/'D2_approval_2026_10_14_v1.json'))
        self.assertEqual(len(p['wall_vertex_region_ids']),len(self.analyzer.v));self.assertEqual(len(p['stations']),len(self.records))
        self.assertEqual(p['capacity']['status'],'CANDIDATE_NOT_FORMAL_BRANCH_CAPACITY')

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(N1Tests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    write_json(ROOT/'python_tests.json',{'run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
                 'details':[str(x) for x in result.failures+result.errors]})
    sys.exit(0 if result.wasSuccessful() else 1)
