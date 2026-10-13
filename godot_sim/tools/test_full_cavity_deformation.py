"""Regression checks for topology-limited all-natural displacement and morphs."""
import hashlib
import json
import struct
import unittest

import numpy as np
import trimesh
from scipy import sparse
from scipy.sparse import csgraph

from resolve_cavity_topology import PROJECT,read_json,json_bytes
from build_full_cavity_deformation import (NATURAL_IDS,TRANSITION_IDS,ROOT,endpoint_adjacency,plain,restricted_surface_graph)
from build_local_displacement import load_approved_masks,path_projection,self_intersection_pairs
from build_cavity_morph_states import FILL_LEVELS,STATES,vertex_normals,continuous_diagnostics


class TopologyAlgorithmTests(unittest.TestCase):
    def test_excluded_surface_does_not_leave_zero_cost_shortcuts(self):
        graph=sparse.csr_matrix([[0.,1,0],[1.,0,1],[0,1.,0]])
        restricted=restricted_surface_graph(graph,np.array([True,False,True]))
        self.assertEqual(restricted.nnz,0)
        self.assertTrue(np.isinf(csgraph.dijkstra(restricted,indices=0)[2]))

    def test_spatially_close_unconnected_paths_are_not_adjacent(self):
        paths=[{"marker_names":["A","J"]},{"marker_names":["J","T1"]},
               {"marker_names":["X","T2"]}]
        matrix=endpoint_adjacency(paths)
        self.assertTrue(matrix[0,1])
        self.assertFalse(matrix[1,2])
        self.assertFalse(matrix[0,2])

    def test_removed_baseline_indices_are_json_serializable(self):
        value={"removed":[[np.int64(1856),np.int64(1862)]]}
        self.assertEqual(json.loads(json_bytes(plain(value))),{"removed":[[1856,1862]]})


class FullFieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.field=ROOT/"field";cls.morph=ROOT/"morph"
        cls.report=read_json(cls.field/"displacement_report.json")
        cls.morph_report=read_json(cls.morph/"interpolation_report.json")
        cls.arrays,_,_=load_approved_masks(PROJECT/"deformation/p1_masks",PROJECT/"deformation/cavity_topology_resolved.json")
        cls.resolved=read_json(PROJECT/"deformation/cavity_topology_resolved.json")
        cls.vertices=cls.arrays["vertices"];cls.faces=cls.arrays["faces"]
        cls.displacement=np.load(cls.field/"displacement.npy")
        cls.weights=np.load(cls.field/"candidate_weights.npy")
        cls.selected=np.load(cls.field/"candidate_path_indices.npy")
        cls.ids=[p["id"] for p in cls.resolved["paths"]]

    def test_approved_masks_reference_and_faces_unchanged(self):
        for name,digest in self.report["approved_mask_sha256"].items():
            self.assertEqual(hashlib.sha256((PROJECT/"deformation/p1_masks"/name).read_bytes()).hexdigest(),digest)
        np.testing.assert_array_equal(np.load(self.field/"approved_p12_weights.npy"),self.arrays["weights"])
        for directory in (self.field,self.morph):
            np.testing.assert_array_equal(np.load(directory/"reference_vertices.npy"),self.vertices)
            np.testing.assert_array_equal(np.load(directory/"faces.npy"),self.faces)

    def test_reference_intersection_baseline_is_current(self):
        actual=self_intersection_pairs(self.vertices,self.faces)
        self.assertEqual(actual.tolist(),self.morph_report["baseline_intersection"]["pairs"])

    def test_no_unrelated_candidate_mixing(self):
        adjacency=endpoint_adjacency(self.resolved["paths"])
        for k,index in enumerate(self.selected):
            forbidden=~adjacency[index,self.arrays["path_owner"]]
            self.assertTrue(np.all(self.weights[k,forbidden]==0))
        self.assertLessEqual(int((self.weights>0).sum(axis=0).max()),9)
        sums=self.weights.sum(axis=0)
        np.testing.assert_allclose(sums[sums>0],1,atol=1e-12)

    def test_interface_candidates_stop_at_length_adapted_collars(self):
        owners=self.arrays["path_owner"]
        paths=self.resolved["paths"]
        for name,junction,neighbors in [("B_31","J_05",range(12,19)),("B_32","J_09",range(28,31))]:
            index=self.ids.index(name);k=list(self.selected).index(index)
            transition_length=paths[index]["length_mm"]
            for branch in neighbors:
                other=self.ids.index(f"B_{branch:02}")
                _,_,_,arc,length=path_projection(self.vertices,np.asarray(paths[other]["points_mm"]))
                progress=arc if paths[other]["marker_names"][0]==junction else length-arc
                collar=min(5.,.45*min(transition_length,length))
                protected=(owners==other)&(progress>=collar)
                self.assertGreater(protected.sum(),0)
                self.assertTrue(np.all(self.weights[k,protected]==0))
                if name=="B_32":
                    self.assertLess(collar,1.3)

    def test_all_natural_paths_junctions_and_caps_move(self):
        stats=self.report["region_statistics"]
        self.assertEqual(set(stats["paths"]),set(NATURAL_IDS+TRANSITION_IDS))
        self.assertEqual(set(stats["junctions"]),{f"J_{i:02}" for i in range(1,10)})
        self.assertEqual(set(stats["terminals"]),{f"T_{i:02}" for i in range(1,23)})
        for name,entry in stats["paths"].items():
            self.assertEqual(entry["moved_over_1e_8mm"],entry["free_vertices"])
            if name in NATURAL_IDS:
                self.assertGreater(entry["mean_mm"],.02)
        for kind in ("junctions","terminals"):
            for entry in stats[kind].values():
                self.assertEqual(entry["moved_over_1e_8mm"],entry["free_vertices"])
                self.assertGreater(entry["maximum_mm"],.02)
                if kind=="terminals":
                    self.assertGreater(entry["cap_vertices"],0)
                    self.assertGreater(entry["cap_mean_axial_displacement_mm"],0)

    def test_fixed_ports_and_amplitude_for_entire_interval(self):
        magnitude=np.linalg.norm(self.displacement,axis=1)
        self.assertTrue(np.isfinite(self.displacement).all())
        self.assertAlmostEqual(float(magnitude.max()),.2,places=12)
        self.assertTrue(np.all(magnitude<=.2*self.arrays["weights"]+1e-12))
        self.assertGreaterEqual(float(np.einsum("ij,ij->i",self.displacement,self.arrays["normals"]).min()),-1e-12)
        for mask in self.arrays["port_fixed_masks"]:
            np.testing.assert_array_equal(self.displacement[mask],np.zeros((int(mask.sum()),3)))
            for u in np.linspace(0,1,101):
                np.testing.assert_array_equal((self.vertices+u*self.displacement)[mask],self.vertices[mask])

    def test_important_connections_and_short_interface_quality(self):
        links=self.report["important_connections"]
        self.assertEqual(set(links["J_05"]),{f"B_{i:02}" for i in range(11,19)}|{"B_31"})
        self.assertEqual(set(links["J_09"]),{"B_27","B_28","B_29","B_30","B_32"})
        for sample in self.morph_report["samples"]:
            for name in ("J_05","J_09","B_31_PATH","B_32_PATH","BLADDER_INTERFACE","IN_01_INTERFACE","IN_02_INTERFACE"):
                region=sample["local_regions"][name]
                self.assertLess(region["maximum_edge_gradient"],.2)
                self.assertEqual(region["degenerate_triangles"],0)
                self.assertEqual(region["normal_reversals"],0)

    def test_five_fill_quality_and_baseline_intersection_changes(self):
        report=self.morph_report
        self.assertEqual(tuple(s["fill"] for s in report["samples"]),FILL_LEVELS)
        self.assertEqual(report["baseline_intersection"]["pairs"],[[1856,1862]])
        for sample in report["samples"]+report["godot_float32_samples"]:
            self.assertEqual(sample["new_intersection_pairs"],[])
            self.assertEqual(sample["degenerate_triangles"],0)
            self.assertEqual(sample["normal_reversals"],0)
            self.assertTrue(set(map(tuple,sample["intersection_pairs"])).issubset({(1856,1862)}))
            if sample["fill"]==0:
                self.assertEqual(sample["intersection_pairs"],[[1856,1862]])
            else:
                self.assertEqual(sample["removed_baseline_pairs"],[[1856,1862]])

    def test_states_normals_and_continuous_volume(self):
        for name,u in STATES.items():
            vertices=np.load(self.morph/(name+"_vertices.npy"))
            np.testing.assert_array_equal(vertices,self.vertices+u*self.displacement)
            np.testing.assert_allclose(np.load(self.morph/(name+"_normals.npy")),vertex_normals(vertices,self.faces),atol=1e-12)
        diagnostics=continuous_diagnostics(self.vertices,self.faces,self.displacement)
        self.assertGreater(diagnostics["all_u_oriented_area_ratio_minimum"],0)
        self.assertGreater(diagnostics["all_u_minimum_volume_derivative_mm3"],0)
        coefficients=diagnostics["signed_volume_polynomial_coefficients_mm3"]
        for u in np.linspace(0,1,11):
            volume=trimesh.Trimesh(self.vertices+u*self.displacement,self.faces,process=False).volume
            self.assertAlmostEqual(volume,sum(c*u**i for i,c in enumerate(coefficients)),places=8)

    def test_output_hashes_binary_and_camera_targets(self):
        for directory,report in ((self.field,self.report),(self.morph,self.morph_report)):
            for name,digest in report["output_sha256"].items():
                self.assertEqual(hashlib.sha256((directory/name).read_bytes()).hexdigest(),digest)
            for source in report["sources"].values():
                self.assertEqual(hashlib.sha256((PROJECT/source["path"]).read_bytes()).hexdigest(),source["sha256"])
        meta=read_json(self.morph/"morph_preview.json")
        self.assertEqual(set(meta["landmarks"]),{f"J_{i:02}" for i in range(1,10)}|{f"T_{i:02}" for i in range(1,23)})
        self.assertEqual(set(meta["focus_camera"]),set(meta["landmarks"]))
        raw=(self.morph/"morph_preview.bin").read_bytes()
        self.assertEqual(raw[:8],b"KMOR0001")
        n,m=struct.unpack_from("<II",raw,8)
        self.assertEqual((n,m),(len(self.vertices),len(self.faces)))
        self.assertEqual(len(raw),16+60*n+12*m)
        blocks=np.frombuffer(raw,dtype="<f4",count=15*n,offset=16).reshape(5,n,3)
        origin=np.asarray(meta["preview_origin_mm"])
        np.testing.assert_array_equal(blocks[0],(self.vertices-origin).astype(np.float32))
        np.testing.assert_array_equal(blocks[1],self.displacement.astype(np.float32))


if __name__=="__main__":
    unittest.main(verbosity=2)
