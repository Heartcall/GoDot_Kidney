"""P1.2: fixed port masks and graph-distance transition weights on the source OBJ.

No vertices move. Source OBJ row order is retained; the Godot preview reads a
separate canonical binary mesh, so imported OBJ index reordering is irrelevant.
"""
from __future__ import annotations

import argparse
import colorsys
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

from resolve_cavity_topology import PROJECT, build as resolve_build, json_bytes, read_json, source_record


MAGIC = b"KMSK0001"
REGIONS = [
    {"id": 0, "name": "fixed", "color": [0.18, 0.48, 1.0]},
    {"id": 1, "name": "transition", "color": [1.0, 0.62, 0.08]},
    {"id": 2, "name": "expandable", "color": [0.2, 0.84, 0.4]},
]
DEFAULTS = {"schema_version": "1.0", "ray_directions": 32,
            "radius_probe_fractions": [0.25, 0.5, 0.75],
            "radius_quantile": 0.95, "radius_multiplier": 1.2,
            "radius_edge_padding": 0.5, "transition_length_scale": 1.0,
            "in01_topology": {"junction_collar_fraction": 0.15,
                              "junction_collar_max_mm": 1.5, "surface_feather_mm": 2.4,
                              "smoothing_strength": 8.0}}


def load_obj(path):
    vertices, faces = [], []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        tokens = line.split()
        if not tokens or tokens[0].startswith("#"):
            continue
        if tokens[0] == "v":
            vertices.append([float(x) for x in tokens[1:4]])
        elif tokens[0] == "f":
            if len(tokens) != 4:
                raise ValueError("Canonical P1 mesh must already be triangulated")
            row = [int(x.split("/")[0]) for x in tokens[1:]]
            if any(x == 0 for x in row):
                raise ValueError("OBJ vertex indices cannot be zero")
            faces.append([x - 1 if x > 0 else len(vertices) + x for x in row])
    vertices, faces = np.asarray(vertices, dtype=np.float64), np.asarray(faces, dtype=np.int64)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or not np.isfinite(vertices).all():
        raise ValueError("Invalid source vertices")
    if faces.ndim != 2 or faces.shape[1] != 3 or faces.min() < 0 or faces.max() >= len(vertices):
        raise ValueError("Invalid source faces")
    return vertices, faces


def mesh_graph(vertices, faces):
    edges = np.unique(np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1), axis=0)
    length = np.linalg.norm(vertices[edges[:, 0]] - vertices[edges[:, 1]], axis=1)
    if np.any(length <= 1e-10):
        raise ValueError("Zero-length mesh edge")
    graph = sparse.coo_matrix((np.r_[length, length],
        (np.r_[edges[:, 0], edges[:, 1]], np.r_[edges[:, 1], edges[:, 0]])),
        shape=(len(vertices), len(vertices))).tocsr()
    return graph, edges, length


def project_path(vertices, points):
    best = np.full(len(vertices), np.inf)
    arc = np.zeros(len(vertices))
    offset = 0.0
    for a, b in zip(points[:-1], points[1:]):
        delta = b - a
        length = np.linalg.norm(delta)
        t = np.clip((vertices - a) @ delta / length**2, 0, 1)
        d = np.linalg.norm(vertices - (a + t[:, None] * delta), axis=1)
        select = d < best
        best[select], arc[select] = d[select], offset + t[select] * length
        offset += length
    return best, arc


def connected_from_seed(graph, eligible, seed):
    selected = np.zeros(len(eligible), dtype=bool)
    if not eligible[seed]:
        raise ValueError("Fixed port seed is not eligible")
    pending = [int(seed)]
    selected[seed] = True
    while pending:
        current = pending.pop()
        neighbors = graph.indices[graph.indptr[current]:graph.indptr[current + 1]]
        for neighbor in neighbors:
            if eligible[neighbor] and not selected[neighbor]:
                selected[neighbor] = True
                pending.append(int(neighbor))
    return selected


def transition_weights(graph, fixed, length_mm):
    if not np.isfinite(length_mm) or length_mm <= 0 or not fixed.any():
        raise ValueError("Transition needs a positive length and nonempty fixed mask")
    distances = csgraph.dijkstra(graph, directed=False, indices=np.flatnonzero(fixed),
                                 min_only=True, limit=length_mm)
    t = np.clip(distances / length_mm, 0.0, 1.0)
    weights = t * t * (3.0 - 2.0 * t)
    weights[fixed] = 0.0
    return weights, distances


def smooth_transition_field(graph, weights, fixed, domain, neutral, strength):
    """Screened graph-Laplacian of deficit, with fixed/neutral Dirichlet values.

    The target is the constrained corridor field, not unrestricted diffusion.
    Eliminating fixed and neutral nodes preserves exact 0/1 endpoints.
    """
    conductance = graph.copy()
    conductance.data = 1.0 / conductance.data
    degree = np.asarray(conductance.sum(axis=1)).ravel()
    system = sparse.diags(degree) + strength * csgraph.laplacian(conductance).tocsr()
    unknown = domain & ~fixed & ~neutral
    deficit = np.zeros(len(weights))
    deficit[fixed] = 1.0
    if unknown.any():
        rhs = (degree * (1 - weights))[unknown] - system[unknown][:, ~unknown] @ deficit[~unknown]
        deficit[unknown] = spsolve(system[unknown][:, unknown].tocsr(), rhs)
    if not np.isfinite(deficit).all() or deficit.min() < -1e-8 or deficit.max() > 1 + 1e-8:
        raise ValueError("Constrained transition solve violated the maximum principle")
    deficit = np.clip(deficit, 0, 1)
    return 1 - deficit


def surface_gate_transition_weights(graph, fixed, core, allowed, length_mm, feather_mm, neutral=None, smoothing_strength=8.0):
    """Constrained intrinsic propagation with a C1 smoothstep support gate.

    Labels choose a corridor/core, never final weights. Neighbors outside the
    core blend over surface distance; both the gate and longitudinal response
    have zero slope at endpoints. Restriction removes long graph detours.
    """
    if feather_mm <= 0 or np.any(core & ~allowed) or np.any(fixed & ~core):
        raise ValueError("Invalid transition core/allowed domain/feather")
    selected = np.flatnonzero(allowed)
    restricted = graph[selected][:, selected]
    core_distance = csgraph.dijkstra(restricted, directed=False,
        indices=np.flatnonzero(core[selected]), min_only=True, limit=feather_mm)
    distance = np.full(len(fixed), np.inf)
    distance[selected] = core_distance
    eligible = core | (allowed & (distance < feather_mm))
    domain = connected_from_seed(graph, eligible, int(np.flatnonzero(fixed)[0]))
    if np.any(fixed & ~domain):
        raise ValueError("Topology support disconnected the fixed wall")
    selected = np.flatnonzero(domain)
    restricted = graph[selected][:, selected]
    distance[:] = np.inf
    distance[selected] = csgraph.dijkstra(restricted, directed=False,
        indices=np.flatnonzero(core[selected]), min_only=True, limit=feather_mm)
    gate_t = np.clip(distance / feather_mm, 0, 1)
    support = 1 - gate_t**2 * (3 - 2 * gate_t)
    recovery_width = feather_mm
    if neutral is not None:
        # Recover toward one BEFORE reaching protected natural interiors. This
        # distance field also feathers the B_31 side of a label seam, avoiding
        # a hard clamp when a nearby natural arm has a far projection parameter.
        distance_to_neutral = csgraph.dijkstra(graph, directed=False,
            indices=np.flatnonzero(neutral), min_only=True, limit=feather_mm)
        nearest_fixed_clearance = float(distance_to_neutral[fixed].min())
        recovery_width = min(feather_mm, nearest_fixed_clearance * 0.95)
        if recovery_width <= 1e-8:
            raise ValueError("Neutral natural boundary intersects a fixed wall")
        recovery_t = np.clip(distance_to_neutral / recovery_width, 0, 1)
        recovery = recovery_t**2 * (3 - 2 * recovery_t)
        if np.any(recovery[fixed] < 1 - 1e-10):
            raise ValueError("Neutral natural boundary is too close to a fixed wall; reduce feather or inspect topology")
        support *= recovery
    local_weight, _ = transition_weights(restricted, fixed[selected], length_mm)
    weights = np.ones(len(fixed))
    weights[selected] = 1 - (1 - local_weight) * support[selected]
    weights[fixed] = 0.0
    if neutral is not None:
        weights = smooth_transition_field(graph, weights, fixed, domain, neutral, smoothing_strength)
    boundary = domain & (graph.astype(bool).astype(float) @ (~domain).astype(float) > 0)
    return weights, domain, support, boundary, int(np.sum(eligible & ~domain)), recovery_width


def topology_transition_weights(graph, fixed, resolved, owners, path_arcs, port, config):
    """B_31 corridor plus bounded J_05 collars, with surface-connected feather.

    Keep the existing fixed mask. Nearby but unrelated branch interiors cannot
    participate in the solve even when their Euclidean distances are small.
    """
    paths = resolved["paths"]
    ids = [p["id"] for p in paths]
    transition_index = ids.index(port["transition_path_id"])
    fixed_index = ids.index(port["fixed_path_id"])
    transition = paths[transition_index]
    junctions = [n for n in (transition["marker_names"][0], transition["marker_names"][-1])
                 if n != port["base"]]
    if len(junctions) != 1:
        raise ValueError("Expected one natural junction for the interface")
    junction = junctions[0]
    options = config["in01_topology"]
    core = fixed | np.isin(owners, [transition_index, fixed_index])
    collar_bounds, progress_by_path = {}, {}
    collar_allowed = np.zeros(len(fixed), dtype=bool)
    allowed = core.copy()
    neutral = np.zeros(len(fixed), dtype=bool)
    for i, path in enumerate(paths):
        if path["kind"] != "natural" or junction not in (path["marker_names"][0], path["marker_names"][-1]):
            continue
        distance_from_junction = path_arcs[i] if path["marker_names"][0] == junction else path["length_mm"] - path_arcs[i]
        length = min(options["junction_collar_max_mm"],
                     options["junction_collar_fraction"] * min(path["length_mm"], transition["length_mm"]))
        collar_bounds[path["id"]] = length
        progress_by_path[path["id"]] = distance_from_junction
        belongs = owners == i
        allowed |= belongs
        collar_allowed |= belongs & (distance_from_junction <= length)
        neutral |= belongs & (distance_from_junction > length + options["surface_feather_mm"])
    core |= collar_allowed
    neutral |= ~allowed
    weights, domain, support, boundary, discarded, recovery_width = surface_gate_transition_weights(
        graph, fixed, core, allowed, port["transition_length_mm"] * config["transition_length_scale"],
        options["surface_feather_mm"], neutral, options["smoothing_strength"])
    rows, cols = sparse.triu(graph, k=1).nonzero()
    jumps = abs(weights[rows] - weights[cols])
    exterior_edges = domain[rows] != domain[cols]
    ownership_edges = owners[rows] != owners[cols]
    branches = []
    for name, collar in collar_bounds.items():
        i = ids.index(name)
        selection = owners == i
        vals = weights[selection]
        far = selection & neutral
        branches.append({"id": name, "vertex_count": int(selection.sum()),
            "affected_count": int(np.sum(vals < 1 - 1e-8)),
            "affected_below_0_99": int(np.sum(vals < 0.99)),
            "minimum_weight": float(vals.min()) if len(vals) else None,
            "mean_weight": float(vals.mean()) if len(vals) else None,
            "junction_collar_mm": collar,
            "surface_feather_mm": options["surface_feather_mm"],
            "affected_branch_progress_range_mm": [float(progress_by_path[name][selection & (weights < 1 - 1e-8)].min()),
                float(progress_by_path[name][selection & (weights < 1 - 1e-8)].max())]
                if np.any(selection & (weights < 1 - 1e-8)) else [],
            "far_branch_vertices": int(far.sum()),
            "far_branch_affected_count": int(np.sum(weights[far] < 1 - 1e-8))})
    details = {"method": "topology_corridor_gate_screened_smoothing", "junction": junction,
        "domain_vertices": int(domain.sum()), "boundary_vertices": int(boundary.sum()),
        "discarded_disconnected_domain_vertices": discarded,
        "protected_natural_vertices": int(neutral.sum()),
        "neutral_recovery_width_mm": recovery_width,
        "maximum_neighbor_weight_jump": float(jumps.max()),
        "maximum_exterior_boundary_jump": float(jumps[exterior_edges].max()) if exterior_edges.any() else 0.0,
        "maximum_ownership_seam_jump": float(jumps[ownership_edges].max()) if ownership_edges.any() else 0.0,
        "hard_zero_to_one_edges": int(np.sum(jumps > 1 - 1e-8)),
        "noncorridor_blended_vertices": int(np.sum((weights > 0) & (weights < 1 - 1e-8)
            & ~np.isin(owners, [fixed_index, transition_index]))),
        "branches": branches}
    return weights, domain, support, details


def radius_probe(scene, base, end, config):
    axis = end - base
    axis /= np.linalg.norm(axis)
    helper = np.eye(3)[np.argmin(abs(axis))]
    u = np.cross(axis, helper)
    u /= np.linalg.norm(u)
    v = np.cross(axis, u)
    angle = np.arange(config["ray_directions"]) * (2 * np.pi / config["ray_directions"])
    directions = np.cos(angle)[:, None] * u + np.sin(angle)[:, None] * v
    rays = np.concatenate([np.c_[np.tile(base + fraction * (end - base), (len(angle), 1)), directions]
                           for fraction in config["radius_probe_fractions"]])
    hits = scene.cast_rays(o3d.core.Tensor(rays, dtype=o3d.core.Dtype.Float32))["t_hit"].numpy()
    if not np.isfinite(hits).all() or np.any(hits <= 0):
        raise ValueError("Port radius probe failed; inspect the confirmed base/end coordinates")
    return float(np.quantile(hits, config["radius_quantile"])), hits


def area_totals(values, vertex_area):
    return float(vertex_area[values].sum())


def validate_resolved_input(resolved_path):
    resolved = read_json(resolved_path)
    rebuilt = resolve_build(PROJECT / resolved["sources"]["markers"]["path"],
        PROJECT / resolved["sources"]["topology"]["path"],
        resolved["validation"]["resampling"]["maximum_spacing_mm"])
    if json_bytes(rebuilt) == Path(resolved_path).read_bytes():
        return resolved, {"geometry_and_provenance_match": True}
    # A re-export may change diagnostics/formatting while leaving every resolved
    # coordinate, name, connection and reference transform byte-identical.
    geometry_matches = {k: v for k, v in resolved.items() if k != "sources"} == {
        k: v for k, v in rebuilt.items() if k != "sources"}
    changed_sources = [k for k in resolved["sources"] if resolved["sources"][k] != rebuilt["sources"][k]]
    if not geometry_matches or changed_sources != ["markers"]:
        raise ValueError("Resolved geometry or non-marker provenance is stale; rebuild the resolved input")
    return resolved, {"geometry_and_provenance_match": False,
        "resolved_geometry_matches_current_export": True,
        "note": "Marker export metadata/hash changed; every resolved geometric field is unchanged. Resolved source file preserved.",
        "current_markers": rebuilt["sources"]["markers"]}


def generate(resolved, mesh_path, config):
    vertices, faces = load_obj(mesh_path)
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    if not mesh.is_watertight or not mesh.is_winding_consistent or np.any(mesh.area_faces < 1e-10):
        raise ValueError("Source cavity must be closed, consistently wound, and nondegenerate")
    graph, edges, edge_lengths = mesh_graph(vertices, faces)
    if csgraph.connected_components(graph, directed=False, return_labels=False) != 1:
        raise ValueError("Expected the confirmed connected cavity surface")
    tensor_mesh = o3d.t.geometry.TriangleMesh(
        o3d.core.Tensor(vertices, dtype=o3d.core.Dtype.Float32),
        o3d.core.Tensor(faces, dtype=o3d.core.Dtype.UInt32))
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(tensor_mesh)
    paths = resolved["paths"]
    path_distances, path_arcs = zip(*(project_path(vertices, np.asarray(p["points_mm"])) for p in paths))
    path_distances, path_arcs = np.asarray(path_distances), np.asarray(path_arcs)
    owners = path_distances.argmin(axis=0).astype(np.uint32)
    owner_arc = path_arcs[owners, np.arange(len(vertices))]
    all_fixed = np.zeros(len(vertices), dtype=bool)
    weights = np.ones(len(vertices))
    fixed_owner = np.full(len(vertices), -1, dtype=np.int32)
    port_details, per_port_fixed, per_port_weights = [], [], []
    topology_arrays = {}
    vertex_area = np.zeros(len(vertices))
    np.add.at(vertex_area, faces.ravel(), np.repeat(mesh.area_faces / 3.0, 3))
    median_edge = float(np.median(edge_lengths))
    for port_index, port in enumerate(resolved["artificial_ports"]):
        path_index = next(i for i, p in enumerate(paths) if p["id"] == port["fixed_path_id"])
        base = np.asarray(resolved["nodes"][port["base"]]["position_mm"])
        end = np.asarray(resolved["nodes"][port["end"]]["position_mm"])
        length = np.linalg.norm(end - base)
        axis = (end - base) / length
        axial = (vertices - base) @ axis
        radial = np.linalg.norm(vertices - base - axial[:, None] * axis, axis=1)
        measured_radius, hits = radius_probe(scene, base, end, config)
        distal_owned = (owners == path_index) & (axial >= 0)
        if not distal_owned.any():
            raise ValueError(f"No distal surface seeds for {port['id']}")
        core_seed = int(np.argmax(np.where(distal_owned, axial, -np.inf)))
        # Voronoi ownership can jump onto a nearby, disconnected branch. Only
        # the distal seed-connected core may widen the measured tube envelope.
        core = connected_from_seed(graph, distal_owned, core_seed)
        envelope_radius = max(measured_radius * config["radius_multiplier"],
                              float(radial[core].max())) + median_edge * config["radius_edge_padding"]
        adjacent_indices = [path_index] + [i for i, p in enumerate(paths)
            if p["id"] == port["transition_path_id"]]
        eligible = ((axial >= 0) & (axial <= length + envelope_radius) & (radial <= envelope_radius)
                    & np.isin(owners, adjacent_indices))
        if not eligible.any():
            raise ValueError(f"No eligible artificial wall for {port['id']}")
        seed = int(np.argmax(np.where(eligible, axial, -np.inf)))
        fixed = connected_from_seed(graph, eligible, seed)
        if np.any(fixed & all_fixed):
            raise ValueError("Artificial fixed masks overlap; inspect the envelopes")
        missed = int(np.sum(core & ~fixed))
        if missed:
            raise ValueError(f"{port['id']}: {missed} seed-connected port wall vertices are not fixed")
        all_fixed |= fixed
        fixed_owner[fixed] = port_index
        support_length = port["transition_length_mm"] * config["transition_length_scale"]
        topology_details = None
        if port["id"] == "IN_01":
            port_weight, domain, support, topology_details = topology_transition_weights(
                graph, fixed, resolved, owners, path_arcs, port, config)
            topology_arrays = {"in01_transition_domain": domain, "in01_surface_support": support,
                              "in01_unconstrained_weights": transition_weights(graph, fixed, support_length)[0]}
        else:
            port_weight, _ = transition_weights(graph, fixed, support_length)
        weights = np.minimum(weights, port_weight)
        per_port_fixed.append(fixed)
        per_port_weights.append(port_weight)
        boundary = fixed[edges[:, 0]] != fixed[edges[:, 1]]
        influenced = ~fixed & (port_weight < 1)
        port_details.append({
            "id": port["id"], "fixed_path_id": port["fixed_path_id"],
            "transition_path_id": port["transition_path_id"],
            "transition_centerline_length_mm": port["transition_length_mm"],
            "surface_transition_support_length_mm": support_length,
            "radius_probe_p95_mm": measured_radius,
            "radius_probe_range_mm": [float(hits.min()), float(hits.max())],
            "fixed_envelope_radius_mm": envelope_radius,
            "seed_vertex": seed, "fixed_vertices": int(fixed.sum()),
            "fixed_area_mm2": area_totals(fixed, vertex_area),
            "discarded_disconnected_eligible_vertices": int(np.sum(eligible & ~fixed)),
            "distal_seed_core_vertices": int(core.sum()),
            "disconnected_distal_voronoi_vertices": int(np.sum(distal_owned & ~core)),
            "unfixed_seed_connected_port_vertices": missed,
            "boundary_edges": int(boundary.sum()),
            "transition_vertices_before_overlap": int(influenced.sum()),
            "transition_area_before_overlap_mm2": area_totals(influenced, vertex_area),
            "fixed_axial_range_mm": [float(axial[fixed].min()), float(axial[fixed].max())],
            "maximum_transition_neighbor_weight_jump": float(np.abs(port_weight[edges[:, 0]] - port_weight[edges[:, 1]]).max()),
        })
        if topology_details is not None:
            port_details[-1]["topology_constraint"] = topology_details
    weights[all_fixed] = 0.0
    regions = np.where(all_fixed, 0, np.where(weights < 1.0, 1, 2)).astype(np.uint32)
    if not np.isfinite(weights).all() or weights.min() != 0 or weights.max() != 1:
        raise ValueError("Invalid weight range")
    if not all((regions == i).any() for i in range(3)):
        raise ValueError("Expected nonempty fixed, transition and expandable regions")
    # Each fixed component is port seeded, and all its vertices have exactly zero weight.
    for fixed in per_port_fixed:
        if np.any(weights[fixed] != 0):
            raise ValueError("Fixed wall has nonzero expansion weights")
    normals = np.asarray(mesh.vertex_normals, dtype=np.float32)
    by_region = [{**region, "vertices": int(np.sum(regions == region["id"])),
                  "area_mm2": area_totals(regions == region["id"], vertex_area)} for region in REGIONS]
    report = {
        "schema_version": "1.1", "status": "P1_2_TOPOLOGY_TRANSITION_FIX_PENDING_VISUAL_REVIEW",
        "coordinate_system": "cavity_mesh_local", "unit": "mm",
        "vertex_count": len(vertices), "triangle_count": len(faces),
        "total_area_mm2": float(mesh.area), "area_method": "one third of triangle area per incident vertex",
        "regions": by_region, "ports": port_details,
        "weight_range": [float(weights.min()), float(weights.max())],
        "fixed_weight_max_abs": float(abs(weights[all_fixed]).max()),
        "maximum_neighbor_weight_jump": float(np.abs(weights[edges[:, 0]] - weights[edges[:, 1]]).max()),
        "area_partition_error_mm2": abs(sum(r["area_mm2"] for r in by_region) - float(mesh.area)),
        "surface_components": 1, "source_geometry_modified": False,
        "review_notes": [
            "B_32 uses its 2.84 mm local support; inspect the coarse-mesh weight gradient before deformation.",
            "IN_02 has disconnected nearest-path islands; they are excluded from the port fixed seed component.",
        ],
        "methods": {
            "fixed": "Distal seed flood fill on mesh edges, constrained by BASE plane, adjacent path ownership and ray/core-adaptive radial envelope; includes distal cap and rejects disconnected Voronoi islands.",
            "transition": "IN_01: topology-connected B_31/J_05 corridor, restricted geodesic propagation times intrinsic smoothstep support feather. Other ports: unchanged surface-geodesic smoothstep. Minimum across constrained fields.",
            "expandable": "All remaining surface vertices; weight exactly one.",
            "path_owner": "Nearest declared polyline, diagnostic only; not certified anatomical segmentation.",
        },
        "limits": ["Masks require user visual review at port cut planes and J_05/J_09.",
                   "Edge-graph distance approximates continuous surface geodesic distance.",
                   "No deformation, pressure model, wall-thickness mapping or collision update is performed.",
                   "Region area uses lumped vertex area; mixed triangles are split equally among their vertex labels.",
                   "Fixed wall extent is inferred from the manually placed BASE/END plus local radius probes; review that BASE is the intended cut plane."],
    }
    arrays = {"vertices": vertices, "faces": faces, "normals": normals, "weights": weights,
              "regions": regions, "path_owner": owners, "path_arc_mm": owner_arc,
              "fixed_port_owner": fixed_owner, "vertex_area_mm2": vertex_area,
              "port_fixed_masks": np.asarray(per_port_fixed), "port_weights": np.asarray(per_port_weights),
              **topology_arrays}
    return arrays, report


def write_outputs(output, arrays, report, resolved_path, config_path, mesh_path, resolved, config):
    output.mkdir(parents=True, exist_ok=True)
    for name, array in arrays.items():
        np.save(output / f"{name}.npy", array, allow_pickle=False)
    # Little-endian: magic; uint32 counts; xyz, normals, weights; region/owner IDs;
    # owner arclength; triangle indices. Faces reverse winding for Godot CW fronts.
    binary = bytearray(MAGIC + struct.pack("<III", len(arrays["vertices"]), len(arrays["faces"]), len(resolved["paths"])))
    for name, dtype in [("vertices", "<f4"), ("normals", "<f4"), ("weights", "<f4"),
                        ("regions", "<u4"), ("path_owner", "<u4"), ("path_arc_mm", "<f4")]:
        binary.extend(np.asarray(arrays[name], dtype=dtype).tobytes(order="C"))
    binary.extend(np.asarray(arrays["faces"][:, ::-1], dtype="<u4").tobytes(order="C"))
    (output / "mask_preview.bin").write_bytes(binary)
    port_preview = write_port_weight_preview(output, arrays["port_weights"])
    path_palette = [{"id": p["id"], "kind": p["kind"],
                     "color": list(colorsys.hsv_to_rgb((i * 0.61803398875) % 1, 0.65, 0.95)),
                     "points_mm": p["points_mm"]} for i, p in enumerate(resolved["paths"])]
    report["sources"] = {"resolved": source_record(resolved_path), "cavity_mesh": source_record(mesh_path),
                         "configuration": source_record(config_path), "builder": source_record(__file__)}
    report["configuration"] = config
    report["outputs"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sorted(output.glob("*.npy"))}
    report["outputs"]["mask_preview.bin"] = hashlib.sha256(binary).hexdigest()
    report["outputs"]["port_weights.bin"] = port_preview["sha256"]
    (output / "surface_mask_report.json").write_bytes(json_bytes(report))
    meta = {"schema_version": "1.0", "binary_file": "mask_preview.bin", "binary_sha256": hashlib.sha256(binary).hexdigest(),
            "source_mesh": report["sources"]["cavity_mesh"], "vertex_count": len(arrays["vertices"]),
            "triangle_count": len(arrays["faces"]), "regions": report["regions"],
            "ports": report["ports"], "paths": path_palette,
            "port_weight_preview": port_preview,
            "bounds_mm": [arrays["vertices"].min(axis=0).tolist(), arrays["vertices"].max(axis=0).tolist()],
            "report_file": "surface_mask_report.json", "area_method": report["area_method"]}
    (output / "mask_preview.json").write_bytes(json_bytes(meta))


def write_port_weight_preview(output, weights):
    port_count, vertex_count = weights.shape
    binary = b"KPRT0001" + struct.pack("<II", vertex_count, port_count) + np.asarray(weights, dtype="<f4").tobytes()
    (Path(output) / "port_weights.bin").write_bytes(binary)
    return {"file": "port_weights.bin", "sha256": hashlib.sha256(binary).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resolved", type=Path, default=PROJECT / "deformation/cavity_topology_resolved.json")
    parser.add_argument("--config", type=Path, default=PROJECT / "deformation/surface_mask_config.json")
    parser.add_argument("--output-dir", type=Path, default=PROJECT / "deformation/p1_masks")
    args = parser.parse_args()
    try:
        resolved, input_validation = validate_resolved_input(args.resolved)
        config = read_json(args.config)
        if set(config) != set(DEFAULTS):
            raise ValueError("Surface configuration keys do not match the supported schema")
        if config["schema_version"] != "1.0" or not isinstance(config["ray_directions"], int) or not 8 <= config["ray_directions"] <= 256:
            raise ValueError("Invalid surface mask configuration")
        numeric_keys = ["radius_quantile", "radius_multiplier", "radius_edge_padding", "transition_length_scale"]
        if not all(isinstance(config[k], (int, float)) and np.isfinite(config[k]) for k in numeric_keys):
            raise ValueError("Surface configuration values must be finite numbers")
        if (not 0 < config["radius_quantile"] <= 1 or not 0 < config["transition_length_scale"]
                or config["radius_multiplier"] < 1 or config["radius_edge_padding"] < 0):
            raise ValueError("Invalid radius quantile or transition scale")
        fractions = config["radius_probe_fractions"]
        if not isinstance(fractions, list) or not fractions or not all(
                isinstance(f, (int, float)) and np.isfinite(f) and 0 < f < 1 for f in fractions):
            raise ValueError("Radius probe fractions must be nonempty and inside (0,1)")
        options = config["in01_topology"]
        if (not isinstance(options, dict) or set(options) != set(DEFAULTS["in01_topology"])
                or not all(isinstance(v, (int, float)) and np.isfinite(v) and v > 0 for v in options.values())
                or options["junction_collar_fraction"] > 1):
            raise ValueError("Invalid IN_01 topology collar/feather parameters")
        mesh_path = PROJECT / resolved["sources"]["cavity_mesh"]["path"]
        arrays, report = generate(resolved, mesh_path, config)
        report["input_validation"] = input_validation
        write_outputs(args.output_dir, arrays, report, args.resolved, args.config, mesh_path, resolved, config)
    except (KeyError, ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps({"vertices": report["vertex_count"], "triangles": report["triangle_count"],
                      "regions": report["regions"], "ports": report["ports"],
                      "report": str(args.output_dir / "surface_mask_report.json")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
