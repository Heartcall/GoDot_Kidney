"""P1.4 interpolation, preserved inputs, mesh quality and preview regressions."""
import hashlib
import struct
import unittest

import numpy as np
import trimesh

from resolve_cavity_topology import PROJECT, read_json
from build_cavity_morph_states import (FILL_LEVELS, STATES, load_inputs, interpolate,
    vertex_normals, minimum_oriented_area_ratio, continuous_diagnostics)


class InterpolationAlgorithmTests(unittest.TestCase):
    def test_invalid_filling_is_rejected(self):
        for fill in (-.1, 1.1, np.nan, np.inf):
            with self.assertRaises(ValueError):
                interpolate(np.zeros((3,3)), np.ones((3,3)), fill)

    def test_fixed_coordinates_and_vertex_identity(self):
        reference = np.arange(15, dtype=float).reshape(5,3)
        displacement = np.full((5,3), .2)
        displacement[[0,3]] = 0
        for fill in np.linspace(0,1,101):
            actual = interpolate(reference, displacement, fill)
            np.testing.assert_array_equal(actual[[0,3]], reference[[0,3]])
            np.testing.assert_array_equal(actual, reference + fill*displacement)

    def test_continuous_area_catches_collapse_between_valid_endpoints(self):
        vertices = np.array([[0.,0,0],[1.,0,0],[0.,1,0]])
        displacement = np.array([[0.,0,0],[-2.,0,0],[0.,-2,0]])
        faces = np.array([[0,1,2]])
        # Both endpoints have the original positive normal, yet u=0.5 collapses.
        self.assertEqual(minimum_oriented_area_ratio(vertices, faces, displacement), 0)

    def test_recomputed_normals_follow_current_geometry(self):
        vertices = np.array([[0.,0,0],[1.,0,0],[0.,1,0]])
        faces = np.array([[0,1,2]])
        normals = vertex_normals(vertices, faces)
        np.testing.assert_allclose(normals, np.tile([0,0,1],(3,1)))
        vertices[2,2] = 1
        expected = np.tile([0,-1/np.sqrt(2),1/np.sqrt(2)],(3,1))
        np.testing.assert_allclose(vertex_normals(vertices,faces), expected)


class ExportedMorphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = PROJECT/"deformation/p14_morph"
        cls.reference, cls.faces, cls.displacement, cls.masks, _ = load_inputs(PROJECT/"deformation/p13_static")
        cls.report = read_json(cls.root/"interpolation_report.json")
        cls.meta = read_json(cls.root/"morph_preview.json")

    def test_states_reuse_accepted_field_and_identical_topology(self):
        np.testing.assert_array_equal(np.load(self.root/"displacement.npy"), self.displacement)
        np.testing.assert_array_equal(np.load(self.root/"faces.npy"), self.faces)
        for name, fill in STATES.items():
            vertices = np.load(self.root/(name+"_vertices.npy"))
            np.testing.assert_array_equal(vertices, interpolate(self.reference,self.displacement,fill))
            normals = np.load(self.root/(name+"_normals.npy"))
            np.testing.assert_allclose(normals,vertex_normals(vertices,self.faces),atol=1e-12)

    def test_five_samples_are_complete_and_quality_valid(self):
        self.assertEqual(tuple(s["fill"] for s in self.report["samples"]), FILL_LEVELS)
        for sample in self.report["samples"]:
            self.assertTrue(sample["finite_vertices_and_normals"])
            self.assertEqual(sample["degenerate_triangles"],0)
            self.assertEqual(sample["normal_reversals"],0)
            self.assertTrue(sample["watertight"] and sample["winding_consistent"])
            self.assertLessEqual(sample["maximum_displacement_mm"],.2+1e-12)
            self.assertLess(sample["maximum_edge_gradient"],.2)
            for port in sample["fixed_ports"].values():
                self.assertEqual(port["maximum_displacement_mm"],0)
                self.assertTrue(port["coordinates_exactly_unchanged"])

    def test_all_requested_local_regions_are_present(self):
        required = {"J_01","J_02","J_05","J_09","T_01","T_02","T_03","T_04",
                    "BLADDER_INTERFACE","IN_01_INTERFACE","IN_02_INTERFACE","B_32"}
        for sample in self.report["samples"]:
            self.assertEqual(set(sample["local_regions"]),required)
            for name, region in sample["local_regions"].items():
                self.assertGreater(region["vertex_count"],0)
                self.assertEqual(region["degenerate_triangles"],0)
                self.assertEqual(region["normal_reversals"],0)
                self.assertEqual(region["new_intersection_pairs"],[])
                self.assertLess(region["maximum_edge_gradient"],.2)
            self.assertEqual(sample["local_regions"]["B_32"]["maximum_displacement_mm"],0)

    def test_baseline_and_godot_precision_intersections(self):
        baseline = self.report["baseline_intersection"]["pairs"]
        self.assertEqual(baseline,[[1856,1862]])
        for sample in self.report["samples"]:
            stored = np.load(self.root/f"intersections_u{int(sample['fill']*100):03}.npy")
            self.assertEqual(stored.tolist(),baseline)
            self.assertEqual(sample["new_intersection_pairs"],[])
        for sample in self.report["godot_float32_samples"]:
            self.assertEqual(sample["intersection_pairs"],baseline)
            self.assertEqual(sample["new_intersection_pairs"],[])
            self.assertEqual(sample["degenerate_triangles"],0)
            self.assertEqual(sample["normal_reversals"],0)
            self.assertTrue(sample["fixed_coordinates_exactly_unchanged"])
            self.assertLess(sample["maximum_coordinate_roundoff_mm"],1e-5)

    def test_continuous_volume_and_area_diagnostics(self):
        diagnostics = continuous_diagnostics(self.reference,self.faces,self.displacement)
        self.assertGreater(diagnostics["all_u_oriented_area_ratio_minimum"],0)
        self.assertGreater(diagnostics["all_u_minimum_volume_derivative_mm3"],0)
        coefficients = diagnostics["signed_volume_polynomial_coefficients_mm3"]
        for fill in np.linspace(0,1,19):
            mesh = trimesh.Trimesh(interpolate(self.reference,self.displacement,fill),self.faces,process=False)
            self.assertAlmostEqual(sum(c*fill**i for i,c in enumerate(coefficients)),mesh.volume,places=8)
        volumes = [s["volume_mm3"] for s in self.report["samples"]]
        self.assertTrue(np.all(np.diff(volumes)>0))

    def test_outputs_sources_and_fixed_index_hashes(self):
        for name,digest in self.report["output_sha256"].items():
            self.assertEqual(hashlib.sha256((self.root/name).read_bytes()).hexdigest(),digest)
        for source in self.report["sources"].values():
            self.assertEqual(hashlib.sha256((PROJECT/source["path"]).read_bytes()).hexdigest(),source["sha256"])
        expected = np.flatnonzero(self.masks["port_fixed_masks"].any(axis=0)).tolist()
        self.assertEqual(read_json(self.root/"fixed_vertex_indices.json"),expected)

    def test_godot_binary_centered_positions_and_vertex_order(self):
        raw = (self.root/"morph_preview.bin").read_bytes()
        self.assertEqual(raw[:8],b"KMOR0001")
        n,m = struct.unpack_from("<II",raw,8)
        self.assertEqual((n,m),(len(self.reference),len(self.faces)))
        self.assertEqual(len(raw),16+n*60+m*12)
        data = np.frombuffer(raw,dtype="<f4",count=n*15,offset=16).reshape(5,n,3)
        origin = np.asarray(self.meta["preview_origin_mm"])
        np.testing.assert_array_equal(data[0],(self.reference-origin).astype(np.float32))
        np.testing.assert_array_equal(data[1],self.displacement.astype(np.float32))
        for i,name in enumerate(STATES):
            np.testing.assert_array_equal(data[i+2],np.load(self.root/(name+"_normals.npy")).astype(np.float32))
        faces = np.frombuffer(raw,dtype="<u4",offset=16+n*60).reshape(m,3)
        np.testing.assert_array_equal(faces,self.faces[:,::-1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
