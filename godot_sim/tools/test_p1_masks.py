"""Focused regression and artifact checks for P1.1/P1.2 (no rendering required)."""
from __future__ import annotations

import copy
import hashlib
import struct
import tempfile
import unittest

import numpy as np
from scipy import sparse
from scipy.sparse import csgraph

from resolve_cavity_topology import PROJECT, build, json_bytes, read_json, resolve
from build_cavity_surface_masks import (load_obj, mesh_graph, transition_weights, connected_from_seed,
                                      surface_gate_transition_weights, validate_resolved_input)


class ResolvedTopologyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.markers_path = PROJECT / "deformation/irrigation_markers.json"
        cls.draft_path = PROJECT / "deformation/cavity_topology_draft.json"
        cls.markers = read_json(cls.markers_path)
        cls.draft = read_json(cls.draft_path)

    def test_current_output_is_reproducible_and_preserves_order(self):
        actual = build(self.markers_path, self.draft_path)
        validated, _ = validate_resolved_input(PROJECT / "deformation/cavity_topology_resolved.json")
        self.assertEqual({k: v for k, v in actual.items() if k != "sources"},
                         {k: v for k, v in validated.items() if k != "sources"})
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

    def test_metadata_reexport_does_not_hide_geometric_changes(self):
        original = read_json(PROJECT / "deformation/cavity_topology_resolved.json")
        with tempfile.TemporaryDirectory(dir=PROJECT / "analysis/irrigation_baseline") as directory:
            path = PROJECT / directory / "resolved.json"
            altered = copy.deepcopy(original)
            altered["sources"]["markers"]["sha256"] = "0" * 64
            path.write_bytes(json_bytes(altered))
            validated, note = validate_resolved_input(path)
            self.assertTrue(note["resolved_geometry_matches_current_export"])
            self.assertEqual(validated["nodes"], original["nodes"])
            altered["nodes"]["J_05"]["position_mm"][0] += 1.0
            path.write_bytes(json_bytes(altered))
            with self.assertRaisesRegex(ValueError, "Resolved geometry"):
                validate_resolved_input(path)

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
    def test_connected_unrelated_branch_does_not_receive_interface_diffusion(self):
        edges = np.asarray([(0, 1), (1, 2), (2, 3), (3, 4), (4, 5),
                            (4, 6), (6, 7), (7, 8), (8, 9), (9, 10), (10, 11)])
        graph = sparse.coo_matrix((np.ones(len(edges) * 2),
            (np.r_[edges[:, 0], edges[:, 1]], np.r_[edges[:, 1], edges[:, 0]])), shape=(12, 12)).tocsr()
        fixed = np.arange(12) == 0
        core = np.arange(12) <= 6
        neutral = np.arange(12) >= 8
        old, _ = transition_weights(graph, fixed, 12.)
        new, *_ = surface_gate_transition_weights(graph, fixed, core, np.ones(12, bool), 12., 2., neutral)
        self.assertLess(old[9], 1)  # A connected Y branch reproduces the old leak.
        np.testing.assert_array_equal(new[8:], np.ones(4))
        self.assertEqual(new[0], 0)
        self.assertGreater(new[6], 0)
        self.assertLess(new[6], 1)  # A noncorridor junction retains a blended field.
        self.assertLess(abs(new[edges[:, 0]] - new[edges[:, 1]]).max(), 1)

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

    def test_in01_cannot_leak_into_natural_branch_interiors(self):
        info = next(p for p in self.report["ports"] if p["id"] == "IN_01")["topology_constraint"]
        self.assertEqual(info["hard_zero_to_one_edges"], 0)
        self.assertLess(info["maximum_exterior_boundary_jump"], .01)
        self.assertLess(info["maximum_neighbor_weight_jump"], .5)
        self.assertGreater(info["noncorridor_blended_vertices"], 0)
        branches = {b["id"]: b for b in info["branches"]}
        for i in range(12, 19):
            branch = branches[f"B_{i:02}"]
            self.assertEqual(branch["far_branch_affected_count"], 0)
            self.assertGreater(branch["minimum_weight"], .90)
            self.assertGreater(branch["mean_weight"], .998)
            self.assertLess(branch["affected_count"], .08 * branch["vertex_count"])
        self.assertEqual(branches["B_13"]["affected_count"], 0)
        self.assertEqual(branches["B_17"]["affected_count"], 0)

    def test_other_ports_match_original_kernel_and_fixed_masks_stay_identical(self):
        graph, _, _ = mesh_graph(self.vertices, self.faces)
        port_weights = np.load(self.root / "port_weights.npy")
        for i, port in enumerate(self.report["ports"]):
            if port["id"] != "IN_01":
                expected, _ = transition_weights(graph, self.fixed[i], port["surface_transition_support_length_mm"])
                np.testing.assert_array_equal(port_weights[i], expected)
        comparison = read_json(self.root / "in01_transition_comparison.json")
        for name, digest in comparison["preserved_array_sha256"].items():
            self.assertEqual(hashlib.sha256((self.root / name).read_bytes()).hexdigest(), digest)

    def test_single_interface_preview_binary(self):
        raw = (self.root / "port_weights.bin").read_bytes()
        self.assertEqual(raw[:8], b"KPRT0001")
        n, p = struct.unpack_from("<II", raw, 8)
        self.assertEqual((n, p), (len(self.vertices), 3))
        values = np.frombuffer(raw, dtype="<f4", offset=16).reshape(p, n)
        np.testing.assert_allclose(values, np.load(self.root / "port_weights.npy"), atol=3e-8, rtol=0)

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
