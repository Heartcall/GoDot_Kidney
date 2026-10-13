"""P1.3: one small static displacement field using the APPROVED P1.2 arrays.

No mask generation, topology resolution, source mesh edits or time animation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

import numpy as np
import open3d as o3d
import trimesh
from scipy import sparse
from scipy.sparse import csgraph
from scipy.sparse.linalg import spsolve

from resolve_cavity_topology import PROJECT, read_json, json_bytes, source_record
from build_cavity_surface_masks import mesh_graph


SELECTED_PATHS = ["MAIN", "B_01", "B_02", "B_03", "B_04", "B_05"]


def smoothstep(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def normalize(vectors):
    length = np.linalg.norm(vectors, axis=1)
    return np.divide(vectors, length[:, None], out=np.zeros_like(vectors), where=length[:, None] > 1e-12)


def load_approved_masks(directory, resolved_path):
    report = read_json(directory / "surface_mask_report.json")
    for name, digest in report["outputs"].items():
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Approved mask artifact hash mismatch: {name}")
    if source_record(resolved_path)["sha256"] != report["sources"]["resolved"]["sha256"]:
        raise ValueError("Resolved topology differs from the approved mask input")
    mesh_path = PROJECT / report["sources"]["cavity_mesh"]["path"]
    if source_record(mesh_path)["sha256"] != report["sources"]["cavity_mesh"]["sha256"]:
        raise ValueError("Source OBJ differs from the approved mask input")
    arrays = {name: np.load(directory / f"{name}.npy", allow_pickle=False) for name in
              ("vertices", "faces", "normals", "weights", "regions", "path_owner", "port_fixed_masks")}
    n = len(arrays["vertices"])
    if arrays["weights"].shape != (n,) or arrays["port_fixed_masks"].shape != (3, n):
        raise ValueError("Invalid approved mask shapes")
    fixed = arrays["port_fixed_masks"].any(axis=0)
    if np.any(arrays["weights"][fixed] != 0) or not np.isfinite(arrays["weights"]).all():
        raise ValueError("Approved fixed weights are not exactly zero or finite")
    return arrays, report, mesh_path


def path_projection(vertices, points):
    """Closest positions with interpolated knot tangents on a preserved polyline."""
    segments = np.diff(points, axis=0)
    lengths = np.linalg.norm(segments, axis=1)
    tangents = segments / lengths[:, None]
    knots = np.vstack([tangents[0], normalize(tangents[:-1] + tangents[1:]), tangents[-1]])
    best = np.full(len(vertices), np.inf)
    centers, direction = np.zeros_like(vertices), np.zeros_like(vertices)
    arcs = np.zeros(len(vertices))
    offset = 0.0
    for i, (a, segment, length) in enumerate(zip(points[:-1], segments, lengths)):
        t = np.clip((vertices - a) @ segment / length**2, 0, 1)
        closest = a + t[:, None] * segment
        distance = np.linalg.norm(vertices - closest, axis=1)
        take = distance < best
        best[take], centers[take] = distance[take], closest[take]
        direction[take] = normalize((1 - t[take, None]) * knots[i] + t[take, None] * knots[i + 1])
        arcs[take] = offset + t[take] * length
        offset += length
    return best, centers, direction, arcs, float(offset)


def region_activity(graph, owners, selected_indices, fixed, feather_mm):
    """Test-region envelope only; DOES NOT replace any approved material mask."""
    seeds = np.isin(owners, selected_indices) & ~fixed
    distance = csgraph.dijkstra(graph, directed=False, indices=np.flatnonzero(seeds),
                                 min_only=True, limit=feather_mm)
    activity = 1 - smoothstep(distance / feather_mm)
    return activity, distance


def candidate_field(vertices, normals, owners, paths, selected_indices):
    candidates, kernel, path_details = [], [], []
    for index in selected_indices:
        path = paths[index]
        distance, center, tangent, arc, length = path_projection(vertices, np.asarray(path["points_mm"]))
        radial = vertices - center
        radial -= np.einsum("ij,ij->i", radial, tangent)[:, None] * tangent
        # Local cavity geometry supplies both scale and outward orientation.
        radius = max(0.5, float(np.median(distance[owners == index])))
        radial -= np.minimum(np.einsum("ij,ij->i", radial, normals), 0)[:, None] * normals
        radial = normalize(radial)
        normal_mix = np.full(len(vertices), .35)
        if path["marker_names"][-1].startswith("T_"):
            cap = smoothstep((arc - max(0, length - 2 * radius)) / min(length, 2 * radius))
            normal_mix += .45 * cap
        vector = (1 - normal_mix[:, None]) * radial + normal_mix[:, None] * normals
        candidates.append(vector)
        kernel.append(-0.5 * (distance / radius)**2)
        path_details.append({"id": path["id"], "median_wall_distance_mm": radius,
                             "terminal_normal_blend": path["marker_names"][-1].startswith("T_")})
    log_weights = np.asarray(kernel)
    log_weights -= log_weights.max(axis=0, keepdims=True)
    blend = np.exp(log_weights)
    blend /= blend.sum(axis=0, keepdims=True)
    return np.einsum("pn,pni->ni", blend, np.asarray(candidates)), path_details


def constrained_vector_smoothing(graph, target, fixed, active, strength):
    conductance = graph.copy()
    conductance.data = 1 / conductance.data
    degree = np.asarray(conductance.sum(axis=1)).ravel()
    matrix = sparse.diags(degree) + strength * csgraph.laplacian(conductance).tocsr()
    free = active & ~fixed
    result = np.zeros_like(target)
    if free.any():
        result[free] = spsolve(matrix[free][:, free].tocsc(), (degree[:, None] * target)[free])
    return result


def make_displacement(arrays, resolved, config):
    vertices, faces = arrays["vertices"], arrays["faces"]
    normals = normalize(arrays["normals"].astype(float))
    fixed = arrays["port_fixed_masks"].any(axis=0)
    graph, edges, edge_lengths = mesh_graph(vertices, faces)
    paths = resolved["paths"]
    selected_indices = [[p["id"] for p in paths].index(name) for name in config["selected_path_ids"]]
    activity, distance = region_activity(graph, arrays["path_owner"], selected_indices, fixed,
                                          config["test_region_feather_mm"])
    target, details = candidate_field(vertices, normals, arrays["path_owner"], paths, selected_indices)
    smoothed = constrained_vector_smoothing(graph, target, fixed, activity > 0, config["vector_smoothing_strength"])
    # Smoothing may mix directions at a concavity: remove only inward normal
    # components, leaving a continuous outward/tangential candidate field.
    smoothed -= np.minimum(np.einsum("ij,ij->i", smoothed, normals), 0)[:, None] * normals
    scale = config["maximum_displacement_mm"] / np.linalg.norm(smoothed, axis=1).max()
    displacement = smoothed * (scale * arrays["weights"] * activity)[:, None]
    displacement[fixed] = 0.0
    magnitude = np.linalg.norm(displacement, axis=1)
    generated = {"reference_vertices": vertices.copy(), "faces": faces.copy(),
                 "displacement": displacement, "displacement_magnitude_mm": magnitude,
                 "displacement_direction": normalize(displacement), "candidate_direction": normalize(target),
                 "test_region_activity": activity, "test_region_distance_mm": np.where(np.isfinite(distance), distance, -1.0),
                 "approved_p12_weights": arrays["weights"].copy(), "reference_normals": normals}
    return generated, details, graph, edges, edge_lengths


def self_intersection_pairs(vertices, faces):
    mesh = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(vertices),
                                    o3d.utility.Vector3iVector(faces.astype(np.int32)))
    pairs = np.asarray(mesh.get_self_intersecting_triangles(), dtype=np.int64).reshape(-1, 2)
    return np.asarray(sorted(tuple(sorted(row)) for row in pairs), dtype=np.int64).reshape(-1, 2)


def triangle_data(vertices, faces):
    triangles = vertices[faces]
    cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    area = np.linalg.norm(cross, axis=1) * .5
    squared_edges = sum(np.sum((triangles[:, a] - triangles[:, b])**2, axis=1)
                        for a, b in ((0, 1), (1, 2), (2, 0)))
    quality = 4 * np.sqrt(3) * area / squared_edges
    return cross, area, quality


def numerical_report(generated, arrays, resolved, config, edges, edge_lengths):
    reference, displacement, faces = generated["reference_vertices"], generated["displacement"], generated["faces"]
    deformed = reference + displacement
    fixed = arrays["port_fixed_masks"].any(axis=0)
    magnitude = generated["displacement_magnitude_mm"]
    cross0, area0, quality0 = triangle_data(reference, faces)
    cross1, area1, quality1 = triangle_data(deformed, faces)
    cos_angle = np.einsum("ij,ij->i", cross0, cross1) / (4 * area0 * area1)
    area_ratio = area1 / area0
    reference_pairs = self_intersection_pairs(reference, faces)
    deformed_pairs = self_intersection_pairs(deformed, faces)
    old_set, new_set = set(map(tuple, reference_pairs)), set(map(tuple, deformed_pairs))
    added_pairs, removed_pairs = sorted(new_set - old_set), sorted(old_set - new_set)
    difference = np.linalg.norm(displacement[edges[:, 0]] - displacement[edges[:, 1]], axis=1)
    gradient = difference / edge_lengths
    neighborhoods = {}
    for name in ("J_01", "J_02", "B_32"):
        if name in resolved["nodes"]:
            center = np.asarray(resolved["nodes"][name]["position_mm"])
        else:
            path = next(p for p in resolved["paths"] if p["id"] == name)
            center = (np.asarray(path["points_mm"][0]) + path["points_mm"][-1]) / 2
        selected = np.linalg.norm(reference - center, axis=1) <= config["diagnostic_neighborhood_mm"]
        local_edges = selected[edges[:, 0]] & selected[edges[:, 1]]
        neighborhoods[name] = {"vertex_count": int(selected.sum()),
            "maximum_displacement_mm": float(magnitude[selected].max()) if selected.any() else 0,
            "maximum_neighbor_displacement_difference_mm": float(difference[local_edges].max()) if local_edges.any() else 0,
            "maximum_edge_displacement_gradient": float(gradient[local_edges].max()) if local_edges.any() else 0}
    reference_mesh = trimesh.Trimesh(reference, faces, process=False)
    deformed_mesh = trimesh.Trimesh(deformed, faces, process=False)
    terminal_checks = []
    path_ids = [p["id"] for p in resolved["paths"]]
    for path in resolved["paths"]:
        if path["id"] not in config["selected_path_ids"] or not path["marker_names"][-1].startswith("T_"):
            continue
        points = np.asarray(path["points_mm"])
        tangent = (points[-1] - points[-2]) / np.linalg.norm(points[-1] - points[-2])
        cap = (arrays["path_owner"] == path_ids.index(path["id"])) & ((reference - points[-1]) @ tangent >= 0)
        terminal_checks.append({"path": path["id"], "terminal": path["marker_names"][-1],
            "cap_vertices_beyond_terminal_marker": int(cap.sum()),
            "maximum_cap_displacement_mm": float(magnitude[cap].max()) if cap.any() else 0,
            "mean_cap_axial_displacement_mm": float((displacement[cap] @ tangent).mean()) if cap.any() else 0})
    report = {"schema_version": "1.0", "status": "P1_3_STATIC_FIELD_PENDING_VISUAL_REVIEW",
        "unit": "mm", "coordinate_system": "cavity_mesh_local", "configuration": config,
        "vertex_count": len(reference), "triangle_count": len(faces), "selected_path_ids": config["selected_path_ids"],
        "finite_displacement": bool(np.isfinite(displacement).all()),
        "fixed_vertex_count": int(fixed.sum()), "fixed_maximum_displacement_mm": float(magnitude[fixed].max()),
        "maximum_displacement_mm": float(magnitude.max()),
        "moved_vertices_over_1e_8mm": int(np.sum(magnitude > 1e-8)),
        "outward_normal_component_min_mm": float(np.einsum("ij,ij->i", displacement, generated["reference_normals"]).min()),
        "maximum_neighbor_displacement_difference_mm": float(difference.max()),
        "maximum_edge_displacement_gradient": float(gradient.max()),
        "neighborhoods": neighborhoods,
        "terminal_checks": terminal_checks,
        "mesh_quality": {
            "reference_degenerate_triangles": int(np.sum(area0 < 1e-10)),
            "deformed_degenerate_triangles": int(np.sum(area1 < 1e-10)),
            "normal_reversal_candidates": int(np.sum(cos_angle <= 0)),
            "minimum_reference_normal_cosine": float(cos_angle.min()),
            "maximum_normal_rotation_deg": float(np.degrees(np.arccos(np.clip(cos_angle, -1, 1))).max()),
            "minimum_triangle_area_mm2": float(area1.min()),
            "area_ratio_range": [float(area_ratio.min()), float(area_ratio.max())],
            "area_ratio_p01_p99": [float(np.quantile(area_ratio, .01)), float(np.quantile(area_ratio, .99))],
            "minimum_quality_reference": float(quality0.min()), "minimum_quality_deformed": float(quality1.min()),
            "reference_watertight": bool(reference_mesh.is_watertight), "deformed_watertight": bool(deformed_mesh.is_watertight),
            "reference_volume_mm3": float(reference_mesh.volume), "deformed_volume_mm3": float(deformed_mesh.volume),
            "volume_change_mm3": float(deformed_mesh.volume - reference_mesh.volume),
            "triangle_indices_unchanged": bool(np.array_equal(faces, arrays["faces"]))},
        "self_intersection": {
            "method": "Open3D 0.19 get_self_intersecting_triangles, reference and static endpoint",
            "reference_pair_count": len(reference_pairs), "deformed_pair_count": len(deformed_pairs),
            "new_pair_count": len(added_pairs), "removed_pair_count": len(removed_pairs),
            "reference_pairs": reference_pairs.tolist(), "deformed_pairs": deformed_pairs.tolist(), "new_pairs": added_pairs,
            "limits": "Floating-point triangle test; no continuous collision certificate, tissue-wall clearance or tool contact check."},
        "methods": {
            "mask": "Read approved P1.2 weights/regions/fixed arrays, validate hashes; never regenerate them.",
            "activity": "Additional test-region amplitude envelope on selected paths with intrinsic surface feather; not a replacement material mask.",
            "direction": "Soft blend of path radial directions, interpolated tangents, outward wall normals and stronger terminal normal response.",
            "smoothing": "Screened graph Laplacian on vector displacement candidates, zero at fixed and inactive vertices.",
            "amplitude": "Global scale then multiply approved P1.2 weight and test-region envelope; no vertex-position smoothing."},
        "debug_acceptance_bounds": {"area_ratio": [.8, 1.35], "maximum_edge_displacement_gradient": .2},
        "limits": ["One static debug field, not a calibrated tissue mechanics simulation.",
                   "Reference mesh already has a B_24 self-intersection; source geometry is preserved.",
                   "No state machine, three-state mesh library, filling slider, collision update or tissue mapping.",
                   "Endpoint normal changes are a reversal diagnostic; intersection tests are reported separately."]}
    if (not report["finite_displacement"] or report["fixed_maximum_displacement_mm"] != 0
            or report["maximum_displacement_mm"] > config["maximum_displacement_mm"] + 1e-12
            or report["mesh_quality"]["deformed_degenerate_triangles"]
            or report["mesh_quality"]["normal_reversal_candidates"] or added_pairs
            or area_ratio.min() < .8 or area_ratio.max() > 1.35 or gradient.max() > .2):
        raise ValueError("Static field failed finite/fixed/amplitude/degeneracy/reversal/new-intersection checks")
    generated["deformed_normals"] = np.asarray(deformed_mesh.vertex_normals)
    generated["reference_self_intersection_pairs"] = reference_pairs
    generated["deformed_self_intersection_pairs"] = deformed_pairs
    return report


def write_results(directory, generated, report, arrays, resolved, masks_dir, resolved_path, config_path):
    directory.mkdir(parents=True, exist_ok=True)
    for name, values in generated.items():
        np.save(directory / f"{name}.npy", values, allow_pickle=False)
    n, m = len(generated["reference_vertices"]), len(generated["faces"])
    raw = bytearray(b"KDSP0001" + struct.pack("<II", n, m))
    for name in ("reference_vertices", "displacement", "reference_normals", "deformed_normals",
                 "approved_p12_weights", "test_region_activity", "displacement_magnitude_mm"):
        raw.extend(np.asarray(generated[name], dtype="<f4").tobytes())
    raw.extend(np.asarray(generated["faces"][:, ::-1], dtype="<u4").tobytes())
    (directory / "displacement_preview.bin").write_bytes(raw)
    report["sources"] = {"resolved": source_record(resolved_path), "config": source_record(config_path),
                          "builder": source_record(__file__), "mask_report": source_record(masks_dir / "surface_mask_report.json")}
    report["approved_mask_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in sorted(masks_dir.iterdir()) if p.is_file()}
    report["output_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted(directory.glob("*.npy"))}
    report["output_sha256"]["displacement_preview.bin"] = hashlib.sha256(raw).hexdigest()
    (directory / "displacement_report.json").write_bytes(json_bytes(report))
    nodes = {name: resolved["nodes"][name]["position_mm"] for name in ("J_01", "J_02")}
    meta = {"schema_version": "1.0", "binary_file": "displacement_preview.bin", "binary_sha256": hashlib.sha256(raw).hexdigest(),
        "vertex_count": n, "triangle_count": m, "maximum_displacement_mm": report["maximum_displacement_mm"],
        "bounds_mm": [generated["reference_vertices"].min(axis=0).tolist(), generated["reference_vertices"].max(axis=0).tolist()],
        "paths": [{"id": p["id"], "points_mm": p["points_mm"]} for p in resolved["paths"]],
        "landmarks": nodes, "selected_path_ids": report["selected_path_ids"],
        "approved_weight_source": source_record(masks_dir / "weights.npy"),
        "source_mesh": read_json(masks_dir / "surface_mask_report.json")["sources"]["cavity_mesh"],
        "fixed_vertices": report["fixed_vertex_count"], "self_intersection": report["self_intersection"]}
    (directory / "displacement_preview.json").write_bytes(json_bytes(meta))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--masks-dir", type=Path, default=PROJECT / "deformation/p1_masks")
    parser.add_argument("--resolved", type=Path, default=PROJECT / "deformation/cavity_topology_resolved.json")
    parser.add_argument("--config", type=Path, default=PROJECT / "deformation/local_displacement_config.json")
    parser.add_argument("--output-dir", type=Path, default=PROJECT / "deformation/p13_static")
    args = parser.parse_args()
    try:
        config = read_json(args.config)
        if config["selected_path_ids"] != SELECTED_PATHS:
            raise ValueError("P1.3 scope is MAIN and B_01 through B_05")
        for name in ("maximum_displacement_mm", "test_region_feather_mm", "vector_smoothing_strength", "diagnostic_neighborhood_mm"):
            if not isinstance(config[name], (int, float)) or not np.isfinite(config[name]) or config[name] <= 0:
                raise ValueError(f"Invalid configuration: {name}")
        if config["maximum_displacement_mm"] > .2:
            raise ValueError("P1.3 debug limit is 0.2 mm")
        arrays, _, _ = load_approved_masks(args.masks_dir, args.resolved)
        resolved = read_json(args.resolved)
        generated, paths, _, edges, edge_lengths = make_displacement(arrays, resolved, config)
        report = numerical_report(generated, arrays, resolved, config, edges, edge_lengths)
        report["path_geometry"] = paths
        write_results(args.output_dir, generated, report, arrays, resolved, args.masks_dir, args.resolved, args.config)
    except (ValueError, OSError, KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps({k: report[k] for k in ("maximum_displacement_mm", "fixed_vertex_count", "fixed_maximum_displacement_mm",
        "moved_vertices_over_1e_8mm", "neighborhoods", "mesh_quality", "self_intersection")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
