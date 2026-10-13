"""Focused regression and artifact checks for P1.1/P1.2 (no rendering required)."""
from __future__ import annotations

import copy
import hashlib
import struct
import unittest

import numpy as np
from scipy import sparse
from scipy.sparse import csgraph

from resolve_cavity_topology import PROJECT, build, json_bytes, read_json, resolve
from build_cavity_surface_masks import load_obj, mesh_graph, transition_weights, connected_from_seed


class ResolvedTopologyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.markers_path = PROJECT / "deformation/irrigation_markers.json"
        cls.draft_path = PROJECT / "deformation/cavity_topology_draft.json"
        cls.markers = read_json(cls.markers_path)
        cls.draft = read_json(cls.draft_path)

    def test_current_output_is_reproducible_and_preserves_order(self):
        actual = build(self.markers_path, self.draft_path)
        self.assertEqual(json_bytes(actual), (PROJECT / "deformation/cavity_topology_resolved.json").read_bytes())
        paths = {p["id"]: p for p in actual["paths"]}
        for branch in self.draft["branches"]:
            self.assertEqual(paths[branch["id"]]["marker_names"],
                             [branch["from"], *branch["controls"], branch["to"]])
        for path in paths.values():
            samples = np.asarray(path["samples_mm"])
            self.assertLessEqual(np.linalg.norm(np.diff(samples, axis=0), axis=1).max(), 0.2500001)
            for point in path["points_mm"]:
                self.assertTrue(np.any(np.linalg.norm(samples - point, axis=1) < 1e-10))

    def test_missing_and_duplicate_markers_fail(self):
        draft = copy.deepcopy(self.draft)
        draft["branches"][0]["to"] = "J_DOES_NOT_EXIST"
        with self.assertRaisesRegex(ValueError, "Missing references"):
            resolve(self.markers, draft)
        markers = copy.deepcopy(self.markers)
        markers["markers"][1]["name"] = markers["markers"][0]["name"]
        with self.assertRaisesRegex(ValueError, "Duplicate marker"):
            resolve(markers, self.draft)

    def test_invalid_coordinates_and_cycles_fail(self):
        markers = copy.deepcopy(self.markers)
        markers["markers"][0]["cavity_local_position_mm"][0] = float("nan")
        with self.assertRaisesRegex(ValueError, "Invalid cavity-local"):
            resolve(markers, self.draft)
        draft = copy.deepcopy(self.draft)
        draft["branches"][1]["to"] = "J_01"
        with self.assertRaises(ValueError):
            resolve(self.markers, draft)


class SurfaceAlgorithmTests(unittest.TestCase):
    def test_short_interface_uses_own_length_and_has_exact_endpoints(self):
        # A surface chain, sampled at fractions of the actual short B_32 length.
        length = 2.8435287822423687
        rows = np.array([0, 1, 1, 2, 2, 3, 3, 4])
        cols = np.array([1, 0, 2, 1, 3, 2, 4, 3])
        graph = sparse.coo_matrix((np.full(8, length / 4), (rows, cols)), shape=(5, 5)).tocsr()
        weights, _ = transition_weights(graph, np.array([True, False, False, False, False]), length)
        np.testing.assert_allclose(weights, [0, 0.15625, 0.5, 0.84375, 1], atol=1e-12)

    def test_disconnected_nearby_island_is_not_fixed_or_transitioned(self):
        graph = sparse.coo_matrix(([1., 1., 1., 1.], ([0, 1, 2, 3], [1, 0, 3, 2])), shape=(4, 4)).tocsr()
        fixed = connected_from_seed(graph, np.ones(4, dtype=bool), 0)
        np.testing.assert_array_equal(fixed, [True, True, False, False])
        weights, _ = transition_weights(graph, fixed, 3.0)
        np.testing.assert_array_equal(weights, [0., 0., 1., 1.])


class GeneratedMaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = PROJECT / "deformation/p1_masks"
        cls.report = read_json(cls.root / "surface_mask_report.json")
        cls.vertices, cls.faces = load_obj(PROJECT / "source_assets/kidney_cavity.obj")
        cls.weights = np.load(cls.root / "weights.npy", allow_pickle=False)
        cls.regions = np.load(cls.root / "regions.npy", allow_pickle=False)
        cls.fixed = np.load(cls.root / "port_fixed_masks.npy", allow_pickle=False)

    def test_source_geometry_and_artifact_hashes(self):
        np.testing.assert_array_equal(self.vertices, np.load(self.root / "vertices.npy", allow_pickle=False))
        np.testing.assert_array_equal(self.faces, np.load(self.root / "faces.npy", allow_pickle=False))
        for name, digest in self.report["outputs"].items():
            self.assertEqual(hashlib.sha256((self.root / name).read_bytes()).hexdigest(), digest, name)

    def test_fixed_ports_connected_disjoint_and_zero_weight(self):
        graph, _, _ = mesh_graph(self.vertices, self.faces)
        self.assertTrue(np.all(self.fixed.sum(axis=0) <= 1))
        for i, mask in enumerate(self.fixed):
            self.assertEqual(csgraph.connected_components(graph[mask][:, mask], directed=False, return_labels=False), 1)
            np.testing.assert_array_equal(self.weights[mask], np.zeros(mask.sum()))
            self.assertEqual(int(mask.sum()), self.report["ports"][i]["fixed_vertices"])
        np.testing.assert_array_equal(self.regions == 0, self.fixed.any(axis=0))

    def test_area_partition_and_adaptive_support(self):
        self.assertEqual(sum(r["vertices"] for r in self.report["regions"]), len(self.vertices))
        self.assertLess(self.report["area_partition_error_mm2"], 1e-8)
        self.assertTrue(np.isfinite(self.weights).all())
        self.assertTrue(np.all((self.weights >= 0) & (self.weights <= 1)))
        np.testing.assert_array_equal(self.weights[self.regions == 2], np.ones(np.sum(self.regions == 2)))
        ports = {p["id"]: p for p in self.report["ports"]}
        self.assertLess(ports["IN_02"]["surface_transition_support_length_mm"], 3.0)
        self.assertGreater(ports["IN_01"]["surface_transition_support_length_mm"], 9.0)
        self.assertEqual(ports["IN_02"]["unfixed_seed_connected_port_vertices"], 0)

    def test_godot_binary_layout_and_float_precision(self):
        raw = (self.root / "mask_preview.bin").read_bytes()
        self.assertEqual(raw[:8], b"KMSK0001")
        n, m, p = struct.unpack_from("<III", raw, 8)
        self.assertEqual((n, m, p), (len(self.vertices), len(self.faces), 37))
        self.assertEqual(len(raw), 20 + n * 40 + m * 12)
        xyz = np.frombuffer(raw, dtype="<f4", count=n * 3, offset=20).reshape(n, 3)
        np.testing.assert_allclose(xyz, self.vertices, atol=1e-5, rtol=0)
        triangles = np.frombuffer(raw, dtype="<u4", count=m * 3, offset=20 + n * 40).reshape(m, 3)
        np.testing.assert_array_equal(triangles, self.faces[:, ::-1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
