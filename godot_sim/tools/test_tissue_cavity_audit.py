"""P1.5 audit gate regressions. These do not certify a tissue deformation."""
import hashlib
import struct
import unittest
import numpy as np
from audit_tissue_cavity import ROOT,ORIGIN,contact_pairs,classify_contacts
from resolve_cavity_topology import PROJECT,read_json
from build_cavity_surface_masks import load_obj


class ContactPredicateTests(unittest.TestCase):
    def setUp(self):
        self.a=np.array([[0.,0,0],[2.,0,0],[0.,2,0]])
        self.faces=np.array([[0,1,2]],dtype=np.int64)

    def test_vtk_finds_true_triangle_crossing(self):
        b=np.array([[.5,.2,-1],[.5,.2,1],[.5,1.,0]])
        pairs=contact_pairs(self.a,self.faces,b,self.faces)
        self.assertEqual(pairs.tolist(),[[0,0]])
        proper,coplanar=classify_contacts(self.a,self.faces,b,self.faces,pairs)
        self.assertTrue(proper[0]);self.assertFalse(coplanar[0])

    def test_coplanar_overlap_is_not_counted_as_proper_crossing(self):
        b=self.a+np.array([.2,.1,0])
        proper,coplanar=classify_contacts(self.a,self.faces,b,self.faces,np.array([[0,0]]))
        self.assertFalse(proper[0]);self.assertTrue(coplanar[0])

    def test_tangential_contact_is_not_counted_as_proper_crossing(self):
        b=np.array([[.5,.2,0],[.5,.2,1],[.5,1.,1]])
        proper,_=classify_contacts(self.a,self.faces,b,self.faces,np.array([[0,0]]))
        self.assertFalse(proper[0])

    def test_separated_triangles_have_no_contacts(self):
        b=self.a+np.array([0,0,2.])
        self.assertEqual(len(contact_pairs(self.a,self.faces,b,self.faces)),0)


class AuditGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=read_json(ROOT/"audit_report.json")

    def test_input_and_output_hashes(self):
        for source in self.report["sources"].values():
            self.assertEqual(hashlib.sha256((PROJECT/source["path"]).read_bytes()).hexdigest(),source["sha256"])
        for name,digest in self.report["output_sha256"].items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest)

    def test_original_issues_are_recorded_despite_vertex_sampling(self):
        self.assertEqual(self.report["meshes"]["cavity"]["self_intersection_pair_count"],1)
        self.assertEqual(self.report["meshes"]["tissue"]["self_intersection_pair_count"],23)
        self.assertGreater(self.report["relation"]["proper_crossing_pairs"],0)
        self.assertEqual(self.report["relation"]["cavity_vertices_inside_tissue_parity_below_minus_1e_4"],0)
        self.assertIn("NOT tissue wall thickness",self.report["relation"]["wall_thickness"])

    def test_barycentric_mapping_is_finite_and_not_vertex_identity(self):
        bary=np.load(ROOT/"mapping_barycentric.npy")
        ids=np.load(ROOT/"tissue_to_cavity_face.npy")
        self.assertEqual(bary.shape,(155904,3));self.assertEqual(ids.shape,(155904,))
        self.assertTrue(np.isfinite(bary).all())
        np.testing.assert_allclose(bary.sum(axis=1),1,atol=1e-6)
        self.assertGreaterEqual(float(bary.min()),-1e-5)
        self.assertLessEqual(float(bary.max()),1+1e-5)
        self.assertLess(int(ids.max()),50044)

    def test_failed_probes_are_not_promoted_to_accepted_states(self):
        self.assertEqual(self.report["status"],"P1_5_AUDIT_BLOCKED_NO_ACCEPTED_TISSUE_FIELD")
        probes=self.report["diagnostic_probes"]
        self.assertEqual(len(probes),6)
        self.assertEqual({p["smoothing_strength"] for p in probes},{0,5,30})
        for probe in probes:
            self.assertFalse(probe["accepted"])
            self.assertGreater(probe["new_proper_crossing_pair_count"],0)
            self.assertLessEqual(probe["tissue_maximum_displacement_mm"],.2)
        self.assertFalse((ROOT/"tissue_displacement.npy").exists())
        self.assertFalse((ROOT/"expanded_vertices.npy").exists())

    def test_preview_contains_only_reference_geometry_with_shared_origin(self):
        meta=read_json(ROOT/"audit_preview.json")
        self.assertTrue(meta["reference_only"])
        self.assertEqual(meta["preview_origin_mm"],ORIGIN.tolist())
        for name in ("cavity","tissue"):
            vertices,faces=load_obj(PROJECT/"source_assets"/f"kidney_{name}.obj")
            raw=(ROOT/(name+"_reference.bin")).read_bytes()
            self.assertEqual(raw[:8],b"KAUD0001")
            n,m=struct.unpack_from("<II",raw,8)
            self.assertEqual((n,m),(len(vertices),len(faces)))
            self.assertEqual(len(raw),16+28*n+12*m)
            positions=np.frombuffer(raw,dtype="<f4",offset=16,count=3*n).reshape(n,3)
            np.testing.assert_array_equal(positions,(vertices-ORIGIN).astype(np.float32))
            indices=np.frombuffer(raw,dtype="<u4",offset=16+28*n).reshape(m,3)
            np.testing.assert_array_equal(indices,faces[:,::-1])

    def test_audit_shader_avoids_historical_transparency_path(self):
        shader=(PROJECT/"shaders/audit_section.gdshader").read_text()
        self.assertIn("discard",shader)
        self.assertNotIn("ALPHA",shader)
        self.assertNotIn("blend_mix",shader)
        self.assertNotIn("CameraAttributesPractical",(PROJECT/"irrigation_geometry_audit_preview.tscn").read_text())


if __name__=="__main__":
    unittest.main(verbosity=2)
