"""Resolve the confirmed marker graph without editing its geometry or topology.

Outputs are deterministic (no timestamps or machine-specific absolute paths).
Run with --check to verify an existing output without writing it.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
COORDINATE_FIELD = "cavity_local_position_mm"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True,
                       allow_nan=False) + "\n").encode("utf-8")


def source_record(path):
    path = Path(path).resolve()
    try:
        name = path.relative_to(PROJECT).as_posix()
    except ValueError:
        name = path.name
    return {"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def resolve(markers_data, draft, spacing_mm=0.25):
    if not math.isfinite(spacing_mm) or spacing_mm <= 0:
        raise ValueError("Sampling spacing must be finite and positive")
    if markers_data.get("unit") != "mm" or draft.get("unit") != "mm":
        raise ValueError("Both input units must be mm")
    if markers_data.get("schema_version") != "2.0":
        raise ValueError("Use the v2 marker export with explicit cavity-local coordinates")
    records = markers_data["markers"]
    if markers_data["count"] != len(records):
        raise ValueError("Declared marker count does not match records")
    nodes = {}
    for record in records:
        name = record["name"]
        if name in nodes:
            raise ValueError(f"Duplicate marker name: {name}")
        xyz = record.get(COORDINATE_FIELD)
        if not isinstance(xyz, list) or len(xyz) != 3 or not all(
                isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in xyz):
            raise ValueError(f"Invalid cavity-local coordinate: {name}")
        nodes[name] = {"position_mm": xyz, "marker_path": record["path"],
                       "marker_role": name.split("_")[0]}
    if len(nodes) != 72:
        raise ValueError(f"This confirmed dataset requires 72 markers; found {len(nodes)}")
    if {b["id"] for b in draft["branches"]} != {f"B_{i:02}" for i in range(1, 33)}:
        raise ValueError("Expected the confirmed B_01 through B_32 branch IDs")
    if len(draft["branches"]) != 32:
        raise ValueError("Expected 32 unique branches")
    definitions = [
        ("MAIN", "natural", draft["main_cavity"]["centerline"]),
        ("BLADDER_TRANSITION", "interface_transition", draft["main_cavity"]["bladder_transition"]),
        *[(p["id"], p["geometry_role"], [p["base"], p["end"]]) for p in draft["artificial_ports"]],
        *[(b["id"], b["kind"], [b["from"], *b.get("controls", []), b["to"]]) for b in draft["branches"]],
    ]
    if len(definitions) != 37 or len({p[0] for p in definitions}) != 37:
        raise ValueError("Expected 37 uniquely named ordered paths")
    references = {name for _, _, names in definitions for name in names}
    missing, unused = sorted(references - nodes.keys()), sorted(nodes.keys() - references)
    if missing or unused:
        raise ValueError(f"Missing references: {missing}; unused markers: {unused}")
    graph = {name: set() for name in nodes}
    edge_counts = collections.Counter()
    paths = []
    for path_id, kind, names in definitions:
        if kind not in ("natural", "interface_transition", "artificial_fixed"):
            raise ValueError(f"Unknown path kind: {path_id}: {kind}")
        if len(names) < 2 or len(set(names)) != len(names):
            raise ValueError(f"Repeated nodes or too few nodes: {path_id}")
        xyz = [nodes[name]["position_mm"] for name in names]
        cumulative = [0.0]
        samples, sample_arcs = [], []
        for a_name, b_name, a, b in zip(names[:-1], names[1:], xyz[:-1], xyz[1:]):
            length = math.dist(a, b)
            if length <= 1e-8:
                raise ValueError(f"Zero-length segment: {path_id}: {a_name}->{b_name}")
            count = max(1, math.ceil(length / spacing_mm))
            for step in range(count):
                t = step / count
                samples.append([a[k] + t * (b[k] - a[k]) for k in range(3)])
                sample_arcs.append(cumulative[-1] + t * length)
            cumulative.append(cumulative[-1] + length)
            graph[a_name].add(b_name)
            graph[b_name].add(a_name)
            edge_counts[tuple(sorted((a_name, b_name)))] += 1
        samples.append(xyz[-1])
        sample_arcs.append(cumulative[-1])
        paths.append({"id": path_id, "kind": kind, "marker_names": names,
                      "points_mm": xyz, "cumulative_length_mm": cumulative,
                      "length_mm": cumulative[-1], "samples_mm": samples,
                      "sample_arc_length_mm": sample_arcs})
    duplicate_edges = [list(e) for e, count in edge_counts.items() if count > 1]
    if duplicate_edges:
        raise ValueError(f"Duplicate graph edges: {duplicate_edges}")
    seen, pending = set(), [next(iter(nodes))]
    while pending:
        current = pending.pop()
        if current not in seen:
            seen.add(current)
            pending.extend(graph[current] - seen)
    if len(seen) != len(nodes) or len(edge_counts) != len(nodes) - 1:
        raise ValueError("Expected one connected acyclic confirmed graph")
    if any(len(graph[n]) != 1 for n in draft["terminals"]):
        raise ValueError("A confirmed terminal is not degree one")
    if any(len(graph[n]) < 3 for n in draft["junctions"]):
        raise ValueError("A confirmed junction has degree below three")
    port_ids = {p["id"] for p in draft["artificial_ports"]}
    if port_ids != {"BLADDER", "IN_01", "IN_02"}:
        raise ValueError("Expected the three confirmed artificial ports")
    paths_by_id = {p["id"]: p for p in paths}
    ports = []
    for port in draft["artificial_ports"]:
        candidates = [p for p in paths if p["kind"] == "interface_transition"
                      and port["base"] in (p["marker_names"][0], p["marker_names"][-1])]
        if len(candidates) != 1 or port["geometry_role"] != "artificial_fixed":
            raise ValueError(f"Expected one transition and fixed role for {port['id']}")
        transition = candidates[0]
        ports.append({**port, "fixed_path_id": port["id"],
                      "transition_path_id": transition["id"],
                      "transition_length_mm": transition["length_mm"],
                      "fixed_length_mm": paths_by_id[port["id"]]["length_mm"]})
    for path in paths:
        endpoint_set = {path["marker_names"][0], path["marker_names"][-1]}
        path["adjacent_path_ids"] = sorted(p["id"] for p in paths if p["id"] != path["id"]
            and endpoint_set.intersection((p["marker_names"][0], p["marker_names"][-1])))
    return {
        "schema_version": "1.0", "status": "P1_1_RESOLVED_STRUCTURALLY_VALID",
        "unit": "mm", "coordinate_system": "cavity_mesh_local",
        "coordinate_field_in_source": COORDINATE_FIELD,
        "reference_mesh": markers_data["reference_mesh"],
        "source_topology_status": draft["status"],
        "validation": {
            "manual_confirmation": "User confirmed markers, connectivity and in-cavity center paths; definitions preserved.",
            "structural": {"marker_count": len(nodes), "branch_count": 32,
                "ordered_path_count": len(paths), "edge_count": len(edge_counts),
                "connected_components": 1, "cycle_rank": 0,
                "missing_references": missing, "unused_markers": unused,
                "junction_degrees": {n: len(graph[n]) for n in draft["junctions"]}},
            "resampling": {"method": "piecewise_linear_preserving_control_points",
                           "maximum_spacing_mm": spacing_mm,
                           "sample_count_with_shared_endpoints": sum(len(p["samples_mm"]) for p in paths)},
            "geometry_scope": "No new curve fitting, tool-radius clearance or self-intersection certification.",
        },
        "nodes": {n: {**nodes[n], "neighbors": sorted(graph[n])} for n in sorted(nodes)},
        "paths": paths, "artificial_ports": ports,
    }


def build(marker_path, topology_path, spacing_mm=0.25):
    markers, draft = read_json(marker_path), read_json(topology_path)
    if draft.get("marker_file") != Path(marker_path).name:
        raise ValueError("Draft marker_file does not match the selected marker input")
    result = resolve(markers, draft, spacing_mm)
    mesh_resource = markers["reference_mesh"]["mesh_resource_path"]
    if not mesh_resource.startswith("res://"):
        raise ValueError("Expected a project-relative reference mesh")
    mesh_path = (PROJECT / mesh_resource[6:]).resolve()
    if not mesh_path.is_relative_to(PROJECT):
        raise ValueError("Reference mesh must remain inside the project")
    result["sources"] = {"markers": source_record(marker_path), "topology": source_record(topology_path),
                         "cavity_mesh": source_record(mesh_path), "resolver": source_record(__file__)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markers", type=Path, default=PROJECT / "deformation/irrigation_markers.json")
    parser.add_argument("--topology", type=Path, default=PROJECT / "deformation/cavity_topology_draft.json")
    parser.add_argument("--output", type=Path, default=PROJECT / "deformation/cavity_topology_resolved.json")
    parser.add_argument("--spacing-mm", type=float, default=0.25)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        result = build(args.markers, args.topology, args.spacing_mm)
        encoded = json_bytes(result)
        if args.check:
            if not args.output.is_file() or args.output.read_bytes() != encoded:
                raise ValueError("Resolved output is missing or stale; rebuild it")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(encoded)
    except (KeyError, ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps({"result": "checked" if args.check else "built",
                      **result["validation"]["structural"],
                      "output": str(args.output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
