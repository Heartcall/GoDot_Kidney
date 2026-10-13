"""P1.4: derive same-topology states from the accepted P1.3 field, read-only inputs."""
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path

import numpy as np
import trimesh

from resolve_cavity_topology import PROJECT, read_json, json_bytes, source_record
from build_local_displacement import load_approved_masks, triangle_data, self_intersection_pairs, normalize
from build_cavity_surface_masks import mesh_graph

FILL_LEVELS = (0., .25, .5, .75, 1.)
STATES = {"reference": 0., "mid": .5, "expanded": 1.}


def interpolate(reference, displacement, fill):
    if not np.isfinite(fill) or not 0 <= fill <= 1:
        raise ValueError("Filling must be finite and in [0,1]")
    return reference + float(fill) * displacement


def vertex_normals(vertices, faces):
    cross, _, _ = triangle_data(vertices, faces)
    sums = np.zeros_like(vertices, dtype=float)
    for corner in range(3):
        np.add.at(sums, faces[:, corner], cross)
    return normalize(sums)


def load_inputs(field_dir):
    masks, mask_report, _ = load_approved_masks(PROJECT / "deformation/p1_masks",
                                               PROJECT / "deformation/cavity_topology_resolved.json")
    report = read_json(field_dir / "displacement_report.json")
    for name, digest in report["output_sha256"].items():
        if source_record(field_dir / name)["sha256"] != digest:
            raise ValueError(f"Accepted P1.3 artifact changed: {name}")
    for name, digest in report["approved_mask_sha256"].items():
        if source_record(PROJECT / "deformation/p1_masks" / name)["sha256"] != digest:
            raise ValueError(f"Accepted P1.2 artifact changed: {name}")
    reference = np.load(field_dir / "reference_vertices.npy", allow_pickle=False)
    faces = np.load(field_dir / "faces.npy", allow_pickle=False)
    displacement = np.load(field_dir / "displacement.npy", allow_pickle=False)
    if not np.array_equal(reference, masks["vertices"]) or not np.array_equal(faces, masks["faces"]):
        raise ValueError("P1.3 reference topology differs from approved P1.2")
    if displacement.shape != reference.shape or not np.isfinite(displacement).all():
        raise ValueError("Invalid accepted displacement array")
    if np.any(displacement[masks["port_fixed_masks"].any(axis=0)] != 0):
        raise ValueError("Accepted fixed displacement is not exactly zero")
    if np.linalg.norm(displacement, axis=1).max() > .2 + 1e-12:
        raise ValueError("Accepted debug field exceeds 0.2 mm")
    return reference, faces, displacement, masks, mask_report


def local_domains(reference, masks, resolved, edges):
    domains = {}
    for name in ("J_01", "J_02", "J_05", "J_09", "T_01", "T_02", "T_03", "T_04"):
        domains[name] = np.linalg.norm(reference - resolved["nodes"][name]["position_mm"], axis=1) <= 8
    ids = [p["id"] for p in resolved["paths"]]
    for port, transition in zip(("BLADDER", "IN_01", "IN_02"), ("BLADDER_TRANSITION", "B_31", "B_32")):
        domain = np.isin(masks["path_owner"], [ids.index(port), ids.index(transition)])
        domain |= masks["port_fixed_masks"][("BLADDER", "IN_01", "IN_02").index(port)]
        # Include the actual one-ring seam, so fixed-to-natural continuity is checked.
        expanded = domain.copy()
        expanded[edges[domain[edges].any(axis=1)].ravel()] = True
        domains[port + "_INTERFACE"] = expanded
    path = resolved["paths"][ids.index("B_32")]
    center = (np.asarray(path["points_mm"][0]) + path["points_mm"][-1]) / 2
    domains["B_32"] = np.linalg.norm(reference - center, axis=1) <= 8
    return domains


def sample_quality(reference, faces, displacement, fill, baseline_pairs, masks, domains, edges, lengths):
    vertices = interpolate(reference, displacement, fill)
    delta = float(fill) * displacement
    magnitude = np.linalg.norm(delta, axis=1)
    c0, a0, _ = triangle_data(reference, faces)
    cross, area, quality = triangle_data(vertices, faces)
    cosine = np.einsum("ij,ij->i", c0, cross) / (4 * a0 * area)
    ratios = area / a0
    normals = vertex_normals(vertices, faces)
    difference = np.linalg.norm(delta[edges[:, 0]] - delta[edges[:, 1]], axis=1)
    gradient = difference / lengths
    pairs = baseline_pairs if fill == 0 else self_intersection_pairs(vertices, faces)
    old, current = set(map(tuple, baseline_pairs)), set(map(tuple, pairs))
    added = sorted(current - old)
    mesh = trimesh.Trimesh(vertices, faces, process=False)
    fixed_ports = {}
    for name, mask in zip(("BLADDER", "IN_01", "IN_02"), masks["port_fixed_masks"]):
        fixed_ports[name] = {"vertices": int(mask.sum()), "maximum_displacement_mm": float(magnitude[mask].max()),
                             "coordinates_exactly_unchanged": bool(np.array_equal(vertices[mask], reference[mask]))}
    local = {}
    for name, domain in domains.items():
        local_edges = domain[edges].any(axis=1)
        local_faces = domain[faces].any(axis=1)
        local[name] = {"vertex_count": int(domain.sum()), "incident_triangle_count": int(local_faces.sum()),
            "maximum_displacement_mm": float(magnitude[domain].max()),
            "maximum_neighbor_difference_mm": float(difference[local_edges].max()),
            "maximum_edge_gradient": float(gradient[local_edges].max()),
            "degenerate_triangles": int(np.sum(area[local_faces] < 1e-10)),
            "normal_reversals": int(np.sum(cosine[local_faces] <= 0)),
            "area_ratio_range": [float(ratios[local_faces].min()), float(ratios[local_faces].max())],
            "new_intersection_pairs": [list(pair) for pair in added if local_faces[list(pair)].any()]}
    result = {"fill": fill, "finite_vertices_and_normals": bool(np.isfinite(vertices).all() and np.isfinite(normals).all()),
        "maximum_displacement_mm": float(magnitude.max()), "fixed_ports": fixed_ports,
        "normal_length_range": [float(np.linalg.norm(normals, axis=1).min()), float(np.linalg.norm(normals, axis=1).max())],
        "degenerate_triangles": int(np.sum(area < 1e-10)), "normal_reversals": int(np.sum(cosine <= 0)),
        "maximum_face_normal_rotation_deg": float(np.degrees(np.arccos(np.clip(cosine, -1, 1))).max()),
        "minimum_triangle_area_mm2": float(area.min()), "minimum_triangle_quality": float(quality.min()),
        "area_ratio_range": [float(ratios.min()), float(ratios.max())],
        "watertight": bool(mesh.is_watertight), "winding_consistent": bool(mesh.is_winding_consistent),
        "volume_mm3": float(mesh.volume), "maximum_edge_gradient": float(gradient.max()),
        "maximum_neighbor_difference_mm": float(difference.max()),
        "intersection_pairs": pairs.tolist(), "new_intersection_pairs": [list(p) for p in added],
        "removed_baseline_pairs": [list(p) for p in sorted(old - current)], "local_regions": local}
    if (not result["finite_vertices_and_normals"] or result["degenerate_triangles"] or result["normal_reversals"]
            or added or not result["watertight"] or not result["winding_consistent"]
            or ratios.min() < .8 or ratios.max() > 1.35 or gradient.max() > .2
            or any(p["maximum_displacement_mm"] != 0 for p in fixed_ports.values())
            or np.max(np.abs(np.linalg.norm(normals, axis=1) - 1)) > 1e-10):
        raise ValueError(f"Geometry validation failed at filling {fill}")
    return result, normals, pairs


def minimum_oriented_area_ratio(reference, faces, displacement):
    # A moving triangle's cross product is quadratic in u. Its projection onto
    # its original oriented normal must stay positive for every u in [0,1].
    tri, d = reference[faces], displacement[faces]
    e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    h1, h2 = d[:, 1] - d[:, 0], d[:, 2] - d[:, 0]
    c0 = np.cross(e1, e2)
    denominator = np.einsum("ij,ij->i", c0, c0)
    b = np.einsum("ij,ij->i", np.cross(h1, e2) + np.cross(e1, h2), c0) / denominator
    a = np.einsum("ij,ij->i", np.cross(h1, h2), c0) / denominator
    u = np.clip(np.divide(-b, 2*a, out=np.zeros_like(b), where=np.abs(a) > 1e-15), 0, 1)
    minimum = np.minimum(1, np.minimum(1+a+b, 1+b*u+a*u*u))
    return float(minimum.min())


def continuous_diagnostics(reference, faces, displacement):
    minimum = minimum_oriented_area_ratio(reference, faces, displacement)
    tri, d = reference[faces], displacement[faces]
    # Signed enclosed volume is cubic for a linear vertex trajectory.
    x, y, z = tri[:, 0], tri[:, 1], tri[:, 2]
    dx, dy, dz = d[:, 0], d[:, 1], d[:, 2]
    det = lambda p, q, r: float(np.einsum("ij,ij->i", p, np.cross(q, r)).sum() / 6)
    coefficients = [det(x,y,z), det(dx,y,z)+det(x,dy,z)+det(x,y,dz),
                    det(dx,dy,z)+det(dx,y,dz)+det(x,dy,dz), det(dx,dy,dz)]
    _, v1, v2, v3 = coefficients
    candidates = [0., 1.]
    if abs(v3) > 1e-15 and 0 < -v2 / (3*v3) < 1:
        candidates.append(-v2 / (3*v3))
    min_derivative = min(v1 + 2*v2*t + 3*v3*t*t for t in candidates)
    if minimum <= 0 or min_derivative <= 0:
        raise ValueError("Continuous oriented-area or monotonic-volume diagnostic failed")
    return {"all_u_oriented_area_ratio_minimum": minimum,
            "all_u_no_degenerate_or_reversed_faces": True,
            "signed_volume_polynomial_coefficients_mm3": coefficients,
            "all_u_minimum_volume_derivative_mm3": min_derivative,
            "all_u_fixed_displacement_exactly_zero": True,
            "scope": "Analytic polynomials evaluated in float64; NOT a continuous self-intersection certificate."}


def build(field_dir, output_dir):
    reference, faces, displacement, masks, mask_report = load_inputs(field_dir)
    resolved = read_json(PROJECT / "deformation/cavity_topology_resolved.json")
    _, edges, lengths = mesh_graph(reference, faces)
    domains = local_domains(reference, masks, resolved, edges)
    # Keep high-precision exports in the original cavity coordinates. Center
    # ONLY the preview's float32 positions to avoid avoidable rounding contact.
    preview_origin = np.rint((reference.min(axis=0) + reference.max(axis=0)) * .5)
    baseline = self_intersection_pairs(reference, faces)
    accepted = np.load(field_dir / "reference_self_intersection_pairs.npy")
    if not np.array_equal(baseline, accepted):
        raise ValueError("Reference intersection baseline differs from P1.3")
    output_dir.mkdir(parents=True, exist_ok=True)
    arrays = {"faces": faces, "displacement": displacement, "reference_vertices": reference}
    samples, preview_checks = [], []
    for fill in FILL_LEVELS:
        print(f"Checking filling {fill:.2f} (float64 and Godot float32)...", flush=True)
        result, normals, pairs = sample_quality(reference, faces, displacement, fill, baseline, masks, domains, edges, lengths)
        samples.append(result)
        arrays[f"intersections_u{int(fill*100):03}"] = pairs
        for state, value in STATES.items():
            if fill == value:
                arrays[state + "_vertices"] = interpolate(reference, displacement, fill)
                arrays[state + "_normals"] = normals
        # Match the preview's float32 addition/multiplication, then run the
        # triangle intersection test on those actual representable positions.
        quantized = ((reference-preview_origin).astype(np.float32) + np.float32(fill) * displacement.astype(np.float32)).astype(float)
        quant_pairs = self_intersection_pairs(quantized, faces)
        cq, aq, _ = triangle_data(quantized, faces)
        c0, _, _ = triangle_data(reference, faces)
        check = {"fill": fill, "maximum_coordinate_roundoff_mm": float(np.abs(quantized+preview_origin-interpolate(reference,displacement,fill)).max()),
                 "degenerate_triangles": int(np.sum(aq < 1e-10)),
                 "normal_reversals": int(np.sum(np.einsum("ij,ij->i", cq, c0) <= 0)),
                 "intersection_pairs": quant_pairs.tolist(),
                 "new_intersection_pairs": sorted(set(map(tuple,quant_pairs))-set(map(tuple,baseline))),
                 "fixed_coordinates_exactly_unchanged": bool(np.array_equal(quantized[masks["port_fixed_masks"].any(axis=0)], (reference-preview_origin).astype(np.float32)[masks["port_fixed_masks"].any(axis=0)]))}
        if check["degenerate_triangles"] or check["normal_reversals"] or check["new_intersection_pairs"] or not check["fixed_coordinates_exactly_unchanged"]:
            raise ValueError(f"Godot float32 geometry failed at {fill}")
        preview_checks.append(check)
    volumes = [s["volume_mm3"] for s in samples]
    if not np.all(np.diff(volumes) > 0):
        raise ValueError("Sample volumes are not strictly increasing")
    for name, array in arrays.items():
        np.save(output_dir / (name + ".npy"), array, allow_pickle=False)
    raw = bytearray(b"KMOR0001" + struct.pack("<II", len(reference), len(faces)))
    for name in ("reference_vertices", "displacement", "reference_normals", "mid_normals", "expanded_normals"):
        values = arrays[name] - preview_origin if name == "reference_vertices" else arrays[name]
        raw.extend(np.asarray(values, dtype="<f4").tobytes())
    raw.extend(np.asarray(faces[:, ::-1], dtype="<u4").tobytes())
    (output_dir / "morph_preview.bin").write_bytes(raw)
    (output_dir / "fixed_vertex_indices.json").write_bytes(json_bytes(np.flatnonzero(masks["port_fixed_masks"].any(axis=0)).tolist()))
    output_hashes = {name + ".npy": source_record(output_dir / (name + ".npy"))["sha256"] for name in arrays}
    output_hashes["morph_preview.bin"] = hashlib.sha256(raw).hexdigest()
    output_hashes["fixed_vertex_indices.json"] = source_record(output_dir / "fixed_vertex_indices.json")["sha256"]
    sources = {"p13_report": source_record(field_dir / "displacement_report.json"),
               "p13_displacement": source_record(field_dir / "displacement.npy"),
               "p12_report": source_record(PROJECT / "deformation/p1_masks/surface_mask_report.json"),
               "resolved": source_record(PROJECT / "deformation/cavity_topology_resolved.json"),
               "builder": source_record(__file__)}
    report = {"schema_version":"1.0", "status":"P1_4_VALIDATED_PENDING_USER_REVIEW", "unit":"mm",
        "coordinate_system":"cavity_mesh_local", "vertex_count":len(reference), "triangle_count":len(faces),
        "formula":"x(u) = reference + u * accepted_P1.3_displacement; Mid = x(0.5)",
        "states":STATES, "same_topology_all_states":True, "sources":sources, "output_sha256":output_hashes,
        "user_accepted_input":"P1.3 accepted by user for MAIN, J_01/J_02, T_01..T_04; B_32 remains inactive.",
        "baseline_intersection":{"location":"B_24", "pairs":baseline.tolist(), "source_issue_preserved":True},
        "samples":samples, "godot_float32_samples":preview_checks, "volume_strictly_increasing_at_samples":True,
        "godot_preview_origin_mm":preview_origin.tolist(),
        "continuous_diagnostics":continuous_diagnostics(reference, faces, displacement),
        "normal_method":"Area-weighted incident face normals recomputed for each state/fill; not linearly blended normals.",
        "local_region_definition":"8 mm reference-space balls for markers/B_32; approved port+transition ownership plus one edge ring for interfaces.",
        "limits":["Self-intersection tested at five fillings, in float64 and Godot float32; unsampled times are not certified.",
                  "Existing B_24 intersection and source skinny faces retained. Volume is geometric debug data, not physiology.",
                  "Same local P1.3 field only; B_32 and IN_01 remain inactive. No tissue, pressure, flow, collision update or video."]}
    (output_dir / "interpolation_report.json").write_bytes(json_bytes(report))
    landmarks = {name:resolved["nodes"][name]["position_mm"] for name in ("J_01","J_02","T_01","T_02","T_03","T_04")}
    meta = {"schema_version":"1.0", "binary_file":"morph_preview.bin", "binary_sha256":hashlib.sha256(raw).hexdigest(),
        "vertex_count":len(reference), "triangle_count":len(faces), "maximum_displacement_mm":float(np.linalg.norm(displacement,axis=1).max()),
        "states":STATES, "sample_fills":FILL_LEVELS, "landmarks":landmarks, "sources":sources,
        "preview_origin_mm":preview_origin.tolist(),
        "bounds_mm":[reference.min(axis=0).tolist(),reference.max(axis=0).tolist()],
        "fixed_vertices":int(masks["port_fixed_masks"].any(axis=0).sum()),
        "fixed_indices_sha256":output_hashes["fixed_vertex_indices.json"],
        "paths":[{"id":p["id"],"points_mm":p["points_mm"]} for p in resolved["paths"]],
        "selected_path_ids":read_json(field_dir/"displacement_report.json")["selected_path_ids"],
        "source_mesh":mask_report["sources"]["cavity_mesh"],
        "approved_weight_source":source_record(PROJECT/"deformation/p1_masks/weights.npy")}
    (output_dir / "morph_preview.json").write_bytes(json_bytes(meta))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--field-dir",type=Path,default=PROJECT/"deformation/p13_static")
    parser.add_argument("--output-dir",type=Path,default=PROJECT/"deformation/p14_morph")
    args = parser.parse_args()
    try:
        report = build(args.field_dir,args.output_dir)
    except (ValueError,OSError,KeyError) as exc:
        parser.error(str(exc))
    for sample in report["samples"]:
        print(f"u={sample['fill']:.2f}: max={sample['maximum_displacement_mm']:.6f} mm; "
              f"volume={sample['volume_mm3']:.6f} mm3; new_intersections={len(sample['new_intersection_pairs'])}")
