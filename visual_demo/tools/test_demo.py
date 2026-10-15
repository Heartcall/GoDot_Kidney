from common import *
import unittest
from validate_pipeline import glb,to_godot

class DemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.a,cls.manifest=inputs();cls.shapes=np.load(OUT/'data/shape_keys_source_RAS_mm.npz');cls.fixed=np.load(PROJECT/'deformation/p2/evidence/port_fixed_masks.npy').any(0)
    def test_accepted_reference(self):np.testing.assert_array_equal(self.shapes['Basis'],self.a['cavity_reference_vertices'])
    def test_all_same_source_topology(self):np.testing.assert_array_equal(self.shapes['faces'],self.a['cavity_faces'])
    def test_fixed_ports(self):
        self.assertEqual(self.fixed.sum(),3675)
        for name in ['Contracted','Expanded']:self.assertFalse(fixed_changes(self.shapes[name]-self.shapes['Basis'],self.fixed))
    def test_modified_fixed_vertex_reported_SYNTHETIC_TEST_ONLY(self):
        i=int(np.flatnonzero(self.fixed)[0]);d=np.zeros_like(self.shapes['Basis']);d[i,0]=.001
        self.assertEqual(fixed_changes(d,self.fixed),[{'source_vertex':i,'displacement_mm':.001}])
    def test_modified_basis_rejected_SYNTHETIC_TEST_ONLY(self):
        x=((self.shapes['Basis']-ORIGIN)*.001).astype(np.float32).astype(float);check_basis(x,self.shapes['Basis']);x[0,0]+=.0001
        with self.assertRaises(ValueError):check_basis(x,self.shapes['Basis'])
    def test_reference_transform_and_normals(self):
        d,acc=glb(PROJECT/'visual_demo/assets/kidney_visual_DRAFT.glb');m=next(m for m in d['meshes'] if m['name']=='KidneyCavity');p=m['primitives'][0]
        ids=acc(p['attributes']['_SOURCE_ID']).ravel().astype(int);pos=acc(p['attributes']['POSITION'])
        self.assertLess(np.max(abs(pos-to_godot(self.shapes['Basis'])[ids])),1e-8)
        self.assertTrue(np.isfinite(acc(p['attributes']['NORMAL'])).all())
    def test_five_samples_light_geometry(self):
        f=self.shapes['faces'];ref=self.shapes['Basis'][f];cr=np.cross(ref[:,1]-ref[:,0],ref[:,2]-ref[:,0])
        for s in [-1.,-.5,0.,.5,1.]:
            x=self.shapes['Basis']+max(-s,0)*(self.shapes['Contracted']-self.shapes['Basis'])+max(s,0)*(self.shapes['Expanded']-self.shapes['Basis'])
            self.assertTrue(np.isfinite(x).all());tri=x[f];normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
            self.assertTrue((np.linalg.norm(normal,axis=1)>1e-12).all());self.assertTrue(((normal*cr).sum(1)>0).all())
    def test_groups_exclusive_J01_not_other(self):
        g=np.load(OUT/'data/edit_inputs.npz')['groups'];self.assertEqual(len(g),25024);self.assertEqual((g==3).sum(),67);self.assertEqual((g==5).sum(),595)
        np.testing.assert_array_equal(g==0,self.fixed)
    def test_actual_runtime(self):
        r=read(OUT/'reports/godot_runtime.json');self.assertEqual(r['blend_shapes'],['Contracted','Expanded'])
        for row in r['samples']:self.assertEqual(min(row['contracted'],row['expanded']),0)
        for row in r['samples']:self.assertEqual(row['triangles'],50044);self.assertTrue(row['normals_finite'])
        self.assertEqual(len(r['samples']),5);self.assertGreater(r['frames'],0)
        for row in read(OUT/'reports/pipeline_validation.json')['Godot_actual_five_states']:self.assertLess(row['symmetric_vertex_position_error_m'],2e-7)
    def test_draft_never_final(self):self.assertFalse(read(OUT/'reports/pipeline_validation.json')['final_visual_approved'])
    def test_no_auto_lod(self):self.assertIn('meshes/generate_lods=false',(PROJECT/'visual_demo/assets/kidney_visual_DRAFT.glb.import').read_text())
    def test_protected_history(self):protect()

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DemoTests))
    write(OUT/'reports/python_tests.json',{'tests':result.testsRun,'passed':result.wasSuccessful(),'failures':[str(x) for x in result.failures],
        'errors':[str(x) for x in result.errors],'strict_continuous_collision_certification':False})
    raise SystemExit(0 if result.wasSuccessful() else 1)
