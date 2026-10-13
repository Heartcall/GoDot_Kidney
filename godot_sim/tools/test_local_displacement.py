"""P1.3 geometry/constraint regressions; never regenerate the approved masks."""
import hashlib
import struct
import unittest

import numpy as np
from scipy import sparse

from resolve_cavity_topology import PROJECT, read_json
from build_local_displacement import (load_approved_masks, path_projection,
    constrained_vector_smoothing, triangle_data, self_intersection_pairs)
from build_cavity_surface_masks import mesh_graph


class FieldAlgorithmTests(unittest.TestCase):
    def test_polyline_knot_tangent_has_no_90_degree_jump(self):
        epsilon = 1e-7
        points = np.array([[0., 0, 0], [1., 0, 0], [1., 1, 0]])
        query = np.array([[1 - epsilon, 0., 0], [1., epsilon, 0]])
        _, centers, tangents, _, _ = path_projection(query, points)
        np.testing.assert_allclose(centers, query, atol=1e-12)
        self.assertLess(np.linalg.norm(tangents[0] - tangents[1]), 1e-6)

    def test_vector_smoothing_preserves_constant_field_without_anchors(self):
        graph = sparse.csr_matrix([[0., 1, 0], [1., 0, 1], [0., 1, 0]])
        target = np.tile([.2, -.1, .3], (3, 1))
        result = constrained_vector_smoothing(graph, target, np.zeros(3, bool), np.ones(3, bool), 30.)
        np.testing.assert_allclose(result, target, atol=1e-12)
        result = constrained_vector_smoothing(graph, target, np.array([True, False, True]), np.ones(3, bool), 30.)
        np.testing.assert_array_equal(result[[0, 2]], np.zeros((2, 3)))

    def test_triangle_intersection_detector_catches_crossing(self):
        vertices = np.array([[0., 0, 0], [1., 0, 0], [0., 1, 0],
                             [.25, .25, -1], [.25, .25, 1], [.8, .25, 0]])
        faces = np.array([[0, 1, 2], [3, 4, 5]])
        np.testing.assert_array_equal(self_intersection_pairs(vertices, faces), [[0, 1]])
        vertices[3:, 0] += 2
        self.assertEqual(len(self_intersection_pairs(vertices, faces)), 0)


class GeneratedFieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = PROJECT / "deformation/p13_static"
        cls.arrays, _, _ = load_approved_masks(PROJECT / "deformation/p1_masks", PROJECT / "deformation/cavity_topology_resolved.json")
        cls.report = read_json(cls.root / "displacement_report.json")
        cls.reference = np.load(cls.root / "reference_vertices.npy")
        cls.displacement = np.load(cls.root / "displacement.npy")
        cls.faces = np.load(cls.root / "faces.npy")
        cls.fixed = cls.arrays["port_fixed_masks"].any(axis=0)

    def test_reference_and_approved_weights_are_exact_copies(self):
        np.testing.assert_array_equal(self.reference, self.arrays["vertices"])
        np.testing.assert_array_equal(self.faces, self.arrays["faces"])
        np.testing.assert_array_equal(np.load(self.root / "approved_p12_weights.npy"), self.arrays["weights"])
        for name, digest in self.report["approved_mask_sha256"].items():
            self.assertEqual(hashlib.sha256((PROJECT / "deformation/p1_masks" / name).read_bytes()).hexdigest(), digest)

    def test_all_three_fixed_ports_have_exact_zero_displacement(self):
        for mask in self.arrays["port_fixed_masks"]:
            np.testing.assert_array_equal(self.displacement[mask], np.zeros((int(mask.sum()), 3)))

    def test_finite_amplitude_envelope_and_directions(self):
        magnitude = np.linalg.norm(self.displacement, axis=1)
        activity = np.load(self.root / "test_region_activity.npy")
        self.assertTrue(np.isfinite(self.displacement).all())
        self.assertAlmostEqual(float(magnitude.max()), .2, places=12)
        self.assertTrue(np.all(magnitude <= .2 * activity * self.arrays["weights"] + 1e-12))
        directions = np.load(self.root / "displacement_direction.npy")
        moved = magnitude > 1e-10
        np.testing.assert_allclose(np.linalg.norm(directions[moved], axis=1), 1, atol=1e-12)
        np.testing.assert_array_equal(self.displacement[activity == 0], np.zeros((int((activity == 0).sum()), 3)))

    def test_selected_branches_and_terminal_caps_are_not_missing(self):
        self.assertEqual(self.report["selected_path_ids"], ["MAIN", "B_01", "B_02", "B_03", "B_04", "B_05"])
        resolved = read_json(PROJECT / "deformation/cavity_topology_resolved.json")
        ids = [p["id"] for p in resolved["paths"]]
        for name in self.report["selected_path_ids"]:
            selected = self.arrays["path_owner"] == ids.index(name)
            self.assertGreater(float(np.linalg.norm(self.displacement[selected], axis=1).max()), .02)
        for terminal in self.report["terminal_checks"]:
            self.assertGreater(terminal["cap_vertices_beyond_terminal_marker"], 0)
            self.assertGreater(terminal["maximum_cap_displacement_mm"], .01)
            self.assertGreater(terminal["mean_cap_axial_displacement_mm"], 0)

    def test_junction_continuity_and_b32_invariance(self):
        _, edges, lengths = mesh_graph(self.reference, self.faces)
        difference = np.linalg.norm(self.displacement[edges[:, 0]] - self.displacement[edges[:, 1]], axis=1)
        self.assertLess(float((difference / lengths).max()), .2)
        for name in ["J_01", "J_02"]:
            self.assertLess(self.report["neighborhoods"][name]["maximum_edge_displacement_gradient"], .2)
        self.assertEqual(self.report["neighborhoods"]["B_32"]["maximum_displacement_mm"], 0)

    def test_mesh_quality_and_outward_orientation(self):
        c0, area0, _ = triangle_data(self.reference, self.faces)
        c1, area1, _ = triangle_data(self.reference + self.displacement, self.faces)
        self.assertTrue(np.all(area1 > 1e-10))
        self.assertTrue(np.all(np.einsum("ij,ij->i", c0, c1) > 0))
        self.assertGreater(float((area1 / area0).min()), .8)
        self.assertLess(float((area1 / area0).max()), 1.35)
        normals = np.load(self.root / "reference_normals.npy")
        self.assertGreaterEqual(float(np.einsum("ij,ij->i", normals, self.displacement).min()), -1e-12)

    def test_baseline_intersection_is_preserved_without_new_pairs(self):
        before = np.load(self.root / "reference_self_intersection_pairs.npy")
        after = np.load(self.root / "deformed_self_intersection_pairs.npy")
        np.testing.assert_array_equal(before, after)
        self.assertEqual(self.report["self_intersection"]["new_pair_count"], 0)
        if len(before):
            vertices = np.unique(self.faces[before.ravel()].ravel())
            np.testing.assert_array_equal(self.displacement[vertices], np.zeros((len(vertices), 3)))

    def test_output_hashes_and_godot_binary_layout(self):
        for name, digest in self.report["output_sha256"].items():
            self.assertEqual(hashlib.sha256((self.root / name).read_bytes()).hexdigest(), digest)
        raw = (self.root / "displacement_preview.bin").read_bytes()
        self.assertEqual(raw[:8], b"KDSP0001")
        n, m = struct.unpack_from("<II", raw, 8)
        self.assertEqual((n, m), (len(self.reference), len(self.faces)))
        self.assertEqual(len(raw), 16 + n * 60 + m * 12)
        vectors = np.frombuffer(raw, dtype="<f4", count=n * 3, offset=16 + n * 12).reshape(n, 3)
        np.testing.assert_allclose(vectors, self.displacement, atol=1e-8, rtol=0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
