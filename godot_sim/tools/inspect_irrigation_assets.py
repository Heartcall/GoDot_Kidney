"""Read-only P0 geometry checks. Write a reproducible report, without editing meshes.

Run with the existing FURS Python environment. Requires numpy, trimesh and open3d.
Signed distances from Open3D are negative inside a closed solid, positive outside.
The tissue solid and the cavity solid have different meanings: a camera should
be inside the cavity and outside the tissue material.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import numpy as np
import open3d as o3d
import trimesh


PROJECT = Path(__file__).resolve().parents[1]


def summary(values: np.ndarray) -> dict:
    return {
        "min": float(np.min(values)),
        "p05": float(np.quantile(values, 0.05)),
        "median": float(np.median(values)),
        "p95": float(np.quantile(values, 0.95)),
        "max": float(np.max(values)),
    }


def load_mesh(name: str):
    path = PROJECT / "source_assets" / f"{name}.obj"
    mesh = trimesh.load(path, force="mesh", process=False)
    tensor_mesh = o3d.t.geometry.TriangleMesh(
        o3d.core.Tensor(np.asarray(mesh.vertices), dtype=o3d.core.Dtype.Float32),
        o3d.core.Tensor(np.asarray(mesh.faces), dtype=o3d.core.Dtype.UInt32),
    )
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(tensor_mesh)
    edges, counts = np.unique(mesh.edges_sorted, axis=0, return_counts=True)
    info = {
        "file": str(path.relative_to(PROJECT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "vertices": len(mesh.vertices),
        "triangles": len(mesh.faces),
        "bounds_mm": mesh.bounds.tolist(),
        "boundary_edges": int(np.sum(counts == 1)),
        "nonmanifold_edges": int(np.sum(counts > 2)),
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "degenerate_triangles": int(np.sum(mesh.area_faces < 1e-10)),
        "signed_volume_mm3": float(mesh.volume),
    }
    del edges
    return mesh, scene, info


def distances(scene, points: np.ndarray, signed: bool = False) -> np.ndarray:
    tensor = o3d.core.Tensor(points, dtype=o3d.core.Dtype.Float32)
    if signed:
        return scene.compute_signed_distance(tensor, nsamples=3).numpy()
    return scene.compute_distance(tensor).numpy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path-file", type=Path, help="Defaults to main.tscn cavity_path_file")
    parser.add_argument("--output", type=Path,
                        default=PROJECT / "analysis/irrigation_baseline/asset_report.json")
    args = parser.parse_args()
    if args.path_file is None:
        match = re.search(r'cavity_path_file = "res://([^"]+)"',
                          (PROJECT / "main.tscn").read_text(encoding="utf-8"))
        if match is None:
            parser.error("main.tscn has no cavity_path_file; pass --path-file")
        path_file = PROJECT / match.group(1)
    else:
        path_file = args.path_file.resolve()
    data = json.loads(path_file.read_text(encoding="utf-8"))
    points = np.asarray(data["points"], dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) < 2:
        parser.error("Expected at least two [x,y,z] path points")
    if not np.isfinite(points).all():
        parser.error("Path contains non-finite coordinates")

    cavity, cavity_scene, cavity_info = load_mesh("kidney_cavity")
    tissue, tissue_scene, tissue_info = load_mesh("kidney_tissue")
    closed = all(i["watertight"] and i["winding_consistent"]
                 for i in (cavity_info, tissue_info))
    cavity_dist = distances(cavity_scene, points, signed=closed)
    tissue_dist = distances(tissue_scene, points, signed=closed)
    surface_gap = distances(tissue_scene, np.asarray(cavity.vertices))

    # Check the interpolated path, not only its sparse source vertices.
    dense_parts = []
    for start, end in zip(points[:-1], points[1:]):
        steps = max(1, int(np.ceil(np.linalg.norm(end - start) / 0.5)))
        dense_parts.append(start + np.arange(steps)[:, None] / steps * (end - start))
    dense = np.concatenate([*dense_parts, points[-1:]], axis=0)
    dense_cavity = distances(cavity_scene, dense, signed=closed)
    dense_tissue = distances(tissue_scene, dense, signed=closed)
    by_clearance = np.argsort(np.abs(cavity_dist))[::-1]
    candidates = [{
        "point_index": int(i),
        "position_mm": points[i].tolist(),
        "forward": data.get("forwards", [None] * len(points))[i],
        "cavity_distance_mm": float(abs(cavity_dist[i])),
        "tissue_distance_mm": float(abs(tissue_dist[i])),
        "anatomical_region": "unconfirmed",
    } for i in by_clearance if (not closed or (cavity_dist[i] < 0 and tissue_dist[i] > 0))][:8]

    report = {
        "units": {"coordinates": "mm", "volume": "mm^3"},
        "meshes": {"cavity": cavity_info, "tissue": tissue_info},
        "path": {
            "file": str(path_file),
            "sha256": hashlib.sha256(path_file.read_bytes()).hexdigest(),
            "source_points": len(points),
            "junctions": data.get("junctions", []),
            "length_mm": float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum()),
            "dense_samples": len(dense),
            "sample_spacing_max_mm": 0.5,
            "signed_distances_available": closed,
            "cavity_signed_distance_mm" if closed else "cavity_distance_mm": summary(dense_cavity),
            "tissue_signed_distance_mm" if closed else "tissue_distance_mm": summary(dense_tissue),
            "outside_cavity_samples": int(np.sum(dense_cavity > 0)) if closed else None,
            "inside_tissue_samples": int(np.sum(dense_tissue < 0)) if closed else None,
            "cavity_clearance_below_tip_radius_2mm": int(np.sum(np.abs(dense_cavity) < 2)),
            "tissue_clearance_below_tip_radius_2mm": int(np.sum(np.abs(dense_tissue) < 2)),
        },
        "cavity_vertex_to_tissue_surface_distance_mm": summary(surface_gap),
        "candidate_camera_poses": candidates,
        "limits": [
            "Self-intersections and anatomical labels have not been verified.",
            "Closed-mesh parity assumes surfaces have no self-intersections.",
            "Surface distance alone is not tissue wall thickness.",
            "Camera candidates rank clearance only; view direction and region require visual review.",
            "0.5 mm path sampling is a baseline check, not continuous collision certification.",
            "Asset hashes record the loaded files; they do not prove source organ identity.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.output), "path": report["path"],
                      "cavity_to_tissue_surface_mm": summary(surface_gap),
                      "camera_candidates": candidates[:3]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
