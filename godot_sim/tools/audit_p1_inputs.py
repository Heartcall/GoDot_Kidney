"""Audit saved P0 inputs for P1; never alter markers, topology or source meshes.

Uses the FURS Python environment (numpy, trimesh, open3d). Geometry checks sample
the declared piecewise linear paths, not an unprovided smoothed centerline.
"""
from __future__ import annotations

import collections
import hashlib
import json
import re
from pathlib import Path

import numpy as np
import open3d as o3d
import trimesh


ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    marker_path = ROOT / "deformation/irrigation_markers.json"
    topology_path = ROOT / "deformation/cavity_topology_draft.json"
    scene_path = ROOT / "irrigation_asset_check.tscn"
    markers_data, topology = read_json(marker_path), read_json(topology_path)
    records = markers_data["markers"]
    markers = {m["name"]: m for m in records}
    chains = [
        ("MAIN", "natural", topology["main_cavity"]["centerline"]),
        ("BLADDER_TRANSITION", "interface_transition", topology["main_cavity"]["bladder_transition"]),
        *[(p["id"], p["geometry_role"], [p["base"], p["end"]])
          for p in topology["artificial_ports"]],
        *[(b["id"], b["kind"], [b["from"], *b.get("controls", []), b["to"]])
          for b in topology["branches"]],
    ]
    references = {n for _, _, names in chains for n in names}
    missing, unused = sorted(references - markers.keys()), sorted(markers.keys() - references)
    if missing or len(markers) != len(records):
        raise ValueError(f"Missing markers: {missing}; duplicate marker names: {len(records)-len(markers)}")
    positions = {n: np.asarray(m["cavity_local_position_mm"], dtype=float)
                 for n, m in markers.items()}
    if any(p.shape != (3,) or not np.isfinite(p).all() for p in positions.values()):
        raise ValueError("Expected finite cavity-local [x,y,z] marker positions")

    # Saved scene check: compare explicit transforms only after confirming that
    # all non-marker nodes and marker bases have identity transforms.
    scene_positions, nonidentity_nodes, marker_nonidentity_bases = {}, [], []
    identity = np.asarray([1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0], dtype=float)
    for block in re.split(r"(?=\[node )", scene_path.read_text(encoding="utf-8"))[1:]:
        header = block.splitlines()[0]
        name = re.search(r'name="([^"]+)"', header).group(1)
        kind = re.search(r'type="([^"]+)"', header).group(1)
        match = re.search(r"^transform = Transform3D\(([^)]+)\)", block, re.M)
        values = np.asarray([float(v) for v in match.group(1).split(",")]) if match else identity.copy()
        if kind == "Marker3D":
            scene_positions[name] = values[-3:]
            if not np.allclose(values[:9], identity[:9], atol=1e-7, rtol=0):
                marker_nonidentity_bases.append(name)
        elif not np.allclose(values, identity, atol=1e-7, rtol=0):
            nonidentity_nodes.append(name)
    same_scene_names = set(scene_positions) == set(markers)
    scene_comparison_valid = same_scene_names and not nonidentity_nodes
    scene_error = (max(float(np.linalg.norm(scene_positions[n] - positions[n])) for n in markers)
                   if scene_comparison_valid else None)

    graph = collections.defaultdict(set)
    edge_counts = collections.Counter()
    for _, _, names in chains:
        for a, b in zip(names[:-1], names[1:]):
            graph[a].add(b)
            graph[b].add(a)
            edge_counts[tuple(sorted((a, b)))] += 1
    components, remaining = [], set(graph)
    while remaining:
        pending, visited = [min(remaining)], set()
        while pending:
            node = pending.pop()
            if node not in visited:
                visited.add(node)
                pending.extend(graph[node] - visited)
        remaining -= visited
        components.append(sorted(visited))

    mesh_path = ROOT / "source_assets/kidney_cavity.obj"
    mesh = trimesh.load(mesh_path, force="mesh", process=False)
    if not mesh.is_watertight or not mesh.is_winding_consistent:
        raise ValueError("Signed distance audit requires closed, consistently wound cavity")
    tensor_mesh = o3d.t.geometry.TriangleMesh(
        o3d.core.Tensor(np.asarray(mesh.vertices), dtype=o3d.core.Dtype.Float32),
        o3d.core.Tensor(np.asarray(mesh.faces), dtype=o3d.core.Dtype.UInt32))
    ray_scene = o3d.t.geometry.RaycastingScene()
    ray_scene.add_triangles(tensor_mesh)
    geometry = []
    for name, kind, names in chains:
        xyz = np.asarray([positions[n] for n in names])
        lengths = np.linalg.norm(np.diff(xyz, axis=0), axis=1)
        dense = []
        for a, b, length in zip(xyz[:-1], xyz[1:], lengths):
            steps = max(1, int(np.ceil(length / 0.25)))
            dense.append(a + np.arange(steps)[:, None] / steps * (b - a))
        dense = np.concatenate([*dense, xyz[-1:]])
        signed = ray_scene.compute_signed_distance(
            o3d.core.Tensor(dense, dtype=o3d.core.Dtype.Float32), nsamples=5).numpy()
        worst = int(np.argmax(signed))
        geometry.append({
            "id": name, "kind": kind, "marker_names": names,
            "length_mm": float(lengths.sum()), "min_segment_mm": float(lengths.min()),
            "sample_count": len(dense), "sample_spacing_max_mm": 0.25,
            "outside_samples_over_0_05mm": int(np.sum(signed > 0.05)),
            "outside_samples_strict": int(np.sum(signed > 0)),
            "signed_distance_range_mm": [float(signed.min()), float(signed.max())],
            "worst_position_mm": dense[worst].tolist(),
        })
    report = {
        "inputs": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in (marker_path, topology_path, scene_path, mesh_path)},
        "resolved_file_present": (ROOT / "deformation/cavity_topology_resolved.json").is_file(),
        "marker_schema": markers_data["schema_version"], "topology_schema": topology["schema_version"],
        "topology_status_unmodified": topology["status"],
        "coordinate_field": "cavity_local_position_mm", "unit": markers_data["unit"],
        "marker_count": len(records), "declared_count": markers_data["count"],
        "marker_types": dict(collections.Counter(n.split("_")[0] for n in markers)),
        "branch_count": len(topology["branches"]),
        "branch_kinds": dict(collections.Counter(b["kind"] for b in topology["branches"])),
        "missing_references": missing, "unused_markers": unused,
        "coordinate_world_local_max_difference_mm": max(
            float(np.linalg.norm(positions[n] - markers[n]["position_mm"])) for n in markers),
        "saved_scene_marker_count": len(scene_positions),
        "saved_scene_marker_names_match": same_scene_names,
        "nonidentity_scene_parent_or_mesh_nodes": nonidentity_nodes,
        "marker_nonidentity_bases": marker_nonidentity_bases,
        "saved_scene_json_position_max_error_mm": scene_error,
        "graph": {"vertices": len(graph), "edges": len(edge_counts),
                  "components": len(components), "cycle_rank": len(edge_counts) - len(graph) + len(components),
                  "duplicate_edges": [list(e) for e, count in edge_counts.items() if count > 1],
                  "junction_degrees": {n: len(graph[n]) for n in topology["junctions"]},
                  "terminal_degrees": {n: len(graph[n]) for n in topology["terminals"]}},
        "geometry": geometry,
        "limits": [
            "Manual topology and visual validation are retained; no source data is modified.",
            "Geometry samples the polyline from the present JSON, not a fitted spline.",
            "Signed distance assumes no mesh self-intersections; self-intersection is not checked here.",
            "Sampling is not a guarantee of continuous clearance or tool-radius clearance.",
            "P0 centerline markers do not define surface-region masks or fixed vertex boundaries.",
            "Text scene audit supports the current explicit Transform3D Node3D hierarchy; arbitrary scenes need Godot evaluation.",
        ],
    }
    output = ROOT / "analysis/irrigation_baseline/p1_input_audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    compact = {k: v for k, v in report.items() if k not in ("inputs", "geometry", "limits")}
    compact["geometry_exceptions"] = [g for g in geometry if g["outside_samples_over_0_05mm"] > 0]
    compact["polylines_checked"] = len(geometry)
    compact["output"] = str(output)
    print(json.dumps(compact, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
