"""Compare a frozen before snapshot with the repaired P1.2 output.

Also adds a port-weight preview transport to the BEFORE COPY only, allowing
identical Godot camera/material code to display both datasets.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np

from resolve_cavity_topology import PROJECT, json_bytes, read_json
from build_cavity_surface_masks import write_port_weight_preview


def stats(values):
    return {"vertex_count": len(values), "affected_count": int(np.sum(values < 1 - 1e-8)),
            "affected_below_0_99": int(np.sum(values < .99)),
            "minimum_weight": float(values.min()), "mean_weight": float(values.mean())}


def compare(before, after):
    resolved = read_json(PROJECT / "deformation/cavity_topology_resolved.json")
    before_meta, after_meta = read_json(before / "mask_preview.json"), read_json(after / "mask_preview.json")
    before_weights = np.load(before / "port_weights.npy", allow_pickle=False)
    after_weights = np.load(after / "port_weights.npy", allow_pickle=False)
    old_fixed = np.load(before / "port_fixed_masks.npy", allow_pickle=False)
    new_fixed = np.load(after / "port_fixed_masks.npy", allow_pickle=False)
    owners = np.load(after / "path_owner.npy", allow_pickle=False)
    if not np.array_equal(owners, np.load(before / "path_owner.npy", allow_pickle=False)):
        raise ValueError("Path ownership changed; cannot compare branch statistics directly")
    port_ids = [p["id"] for p in after_meta["ports"]]
    if port_ids != [p["id"] for p in before_meta["ports"]]:
        raise ValueError("Port ordering changed")
    in01 = port_ids.index("IN_01")
    paths = [p["id"] for p in resolved["paths"]]
    branches = []
    for number in range(12, 19):
        path = f"B_{number:02}"
        selected = owners == paths.index(path)
        branches.append({"id": path, "before": stats(before_weights[in01, selected]),
                         "after": stats(after_weights[in01, selected])})
    checks = {"fixed_masks_unchanged": bool(np.array_equal(old_fixed, new_fixed)),
              "all_fixed_weights_zero": bool(np.all(np.load(after / "weights.npy")[new_fixed.any(axis=0)] == 0)),
              "bladder_port_weights_identical": bool(np.array_equal(before_weights[port_ids.index("BLADDER")], after_weights[port_ids.index("BLADDER")])),
              "b32_port_weights_identical": bool(np.array_equal(before_weights[port_ids.index("IN_02")], after_weights[port_ids.index("IN_02")]))}
    if not all(checks.values()):
        raise ValueError(f"Preservation regression: {checks}")
    geometry_checks = {}
    for name in ("vertices.npy", "faces.npy", "path_owner.npy", "port_fixed_masks.npy", "fixed_port_owner.npy"):
        old_hash = hashlib.sha256((before / name).read_bytes()).hexdigest()
        new_hash = hashlib.sha256((after / name).read_bytes()).hexdigest()
        if old_hash != new_hash:
            raise ValueError(f"Protected derived geometry/mask changed: {name}")
        geometry_checks[name] = old_hash
    # Prepare the historical snapshot for the new single-interface viewer.
    before_meta["port_weight_preview"] = write_port_weight_preview(before, before_weights)
    (before / "mask_preview.json").write_bytes(json_bytes(before_meta))
    report = {"schema_version": "1.0", "status": "P1_2_FIX_PENDING_USER_VISUAL_REVIEW",
              "affected_definition": "weight < 1 - 1e-8; column below_0_99 distinguishes visible influence",
              "branch_membership": "same nearest-polyline ownership for before and after; no marker or ownership changes",
              "checks": checks, "preserved_array_sha256": geometry_checks,
              "fixed_vertex_count": int(new_fixed.any(axis=0).sum()), "branches": branches,
              "before_total_in01_affected": int(np.sum((before_weights[in01] < 1 - 1e-8) & ~old_fixed[in01])),
              "after_total_in01_affected": int(np.sum((after_weights[in01] < 1 - 1e-8) & ~new_fixed[in01])),
              "before_in01_port_weight_sha256": hashlib.sha256(before_weights[in01].tobytes()).hexdigest(),
              "after_in01_port_weight_sha256": hashlib.sha256(after_weights[in01].tobytes()).hexdigest()}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, default=PROJECT / "analysis/irrigation_baseline/in01_transition_fix/before")
    parser.add_argument("--after", type=Path, default=PROJECT / "deformation/p1_masks")
    args = parser.parse_args()
    try:
        report = compare(args.before, args.after)
        (args.after / "in01_transition_comparison.json").write_bytes(json_bytes(report))
    except (ValueError, OSError, KeyError) as exc:
        parser.error(str(exc))
    print(json_bytes(report).decode("utf-8"))


if __name__ == "__main__":
    main()
