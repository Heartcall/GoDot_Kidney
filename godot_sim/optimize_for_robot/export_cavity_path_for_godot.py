"""Exports optimize_path_for_robot.py's result (this folder's
data/organ_1_kidney/lab_<id>/topology_robot_smoothed_stone<id>.json) into the
format Godot's endoscope_controller.gd (auto-tour mode, T key) expects:
{"points": [[x,y,z],...], "forwards": [[dx,dy,dz],...], "junctions": [...]}.

Written to godot_sim/data/organ_1_kidney/lab_<id>/cavity_path_stone<stone-id>.json
-- the same file endoscope_controller.gd's cavity_path_file default already
points at, so running this after optimize_path_for_robot.py is what makes the
next Godot run pick up the robot-constrained path.

Coordinates are passed through as-is (mm) -- no unit conversion needed, since
the Godot scene uses 1 unit = 1mm directly. "forwards" is the per-point
tangent direction (finite-difference on neighboring points).

"junctions" is optional: arc-length offsets (mm) of the real branch points
(skeleton nodes with degree >= 3 in PathPlanning's topology graph) the path
actually passes through -- read-only from PathPlanning's own
result/endoscope_simulation_v2_tree/topology_with_tree_structure.json (not
modified). This is what endoscope_controller.gd uses to only re-derive the
1DOF roll near a genuine fork in the cavity, instead of continuously chasing
tiny curvature noise while just following a single corridor -- decided in
conversation: "only re-derive the roll when there's a fork with multiple
branches". Silently omitted if that topology file isn't found for this lab.

Usage:
    python export_cavity_path_for_godot.py --lab-id 1 --stone-id 1
"""
import argparse
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
GODOT_DATA_DIR = os.path.join(HERE, '..', 'data')
PATHPLANNING_DIR = os.path.join(HERE, '..', 'PathPlanning')


def compute_tangents(points: np.ndarray) -> np.ndarray:
    n = len(points)
    tangents = np.empty_like(points)
    for i in range(n):
        prev_i = max(i - 1, 0)
        next_i = min(i + 1, n - 1)
        d = points[next_i] - points[prev_i]
        norm = np.linalg.norm(d)
        tangents[i] = d / norm if norm > 1e-9 else (tangents[i - 1] if i > 0 else np.array([1.0, 0.0, 0.0]))
    return tangents


def compute_junction_offsets(points: np.ndarray, organ: str, lab_id: str, stone_id: int,
                              merge_within_mm: float = 3.0) -> list:
    """Finds real branch points (degree>=3 skeleton nodes) that THIS SPECIFIC
    stone's path actually passes through (topology['paths'][*]['path_nodes'],
    matched by stone_id -- deliberately not just any degree>=3 node anywhere
    in the kidney, since an unrelated branch elsewhere can sit close in 3D
    space without the path actually going anywhere near it topologically),
    maps each to the nearest point on THIS (possibly resampled/smoothed)
    path, and returns their arc-length offsets (mm), with branch points that
    map within merge_within_mm of each other collapsed into one (a single
    fork can show up as 2-3 adjacent skeleton nodes)."""
    topo_path = os.path.join(PATHPLANNING_DIR, 'data', organ, f'lab_{lab_id}', 'result',
                              'endoscope_simulation_v2_tree', 'topology_with_tree_structure.json')
    if not os.path.exists(topo_path):
        print(f'({topo_path} not found, skipping junctions -- rest of the export is unaffected)')
        return []

    topology = json.load(open(topo_path, encoding='utf-8'))
    path_info = next((p for p in topology['paths'] if p['stone_id'] == stone_id), None)
    if path_info is None:
        return []

    degree = {}
    for e in topology['edges']:
        degree[e['source']] = degree.get(e['source'], 0) + 1
        degree[e['target']] = degree.get(e['target'], 0) + 1
    node_by_id = {n['node_id']: n for n in topology['nodes']}
    branch_positions = [np.asarray(node_by_id[nid]['position'], dtype=float)
                         for nid in path_info['path_nodes']
                         if nid in node_by_id and degree.get(nid, 0) >= 3]
    if not branch_positions:
        return []

    cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))])
    offsets = sorted(float(cum[np.argmin(np.linalg.norm(points - pos, axis=1))]) for pos in branch_positions)

    merged = [offsets[0]]
    for off in offsets[1:]:
        if off - merged[-1] <= merge_within_mm:
            merged[-1] = (merged[-1] + off) / 2.0  # collapse into the midpoint
        else:
            merged.append(off)
    return merged


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--organ', default='organ_1_kidney', help='organ directory name under data/, default organ_1_kidney')
    ap.add_argument('--lab-id', required=True, help='lab id, e.g. 1')
    ap.add_argument('--stone-id', required=True, type=int, help='which stone\'s path to export')
    ap.add_argument('--out', default=None,
                     help='output path (default godot_sim/data/<organ>/lab_<id>/cavity_path_stone<id>.json)')
    args = ap.parse_args()

    topo_path = os.path.join(HERE, 'data', args.organ, f'lab_{args.lab_id}',
                              f'topology_robot_smoothed_stone{args.stone_id}.json')
    if not os.path.exists(topo_path):
        raise SystemExit(f'{topo_path} not found, run optimize_path_for_robot.py first '
                          f'--organ {args.organ} --lab-id {args.lab_id} --stone-id {args.stone_id}')
    topology = json.load(open(topo_path, encoding='utf-8'))
    points = np.asarray(topology['paths'][0]['path_coordinates'], dtype=float)
    forwards = compute_tangents(points)
    junctions = compute_junction_offsets(points, args.organ, args.lab_id, args.stone_id)

    out_path = args.out or os.path.join(
        GODOT_DATA_DIR, args.organ, f'lab_{args.lab_id}', f'cavity_path_stone{args.stone_id}.json')
    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            'points': points.tolist(),
            'forwards': forwards.tolist(),
            'junctions': junctions,
        }, f)

    print(f'Exported {len(points)} points to {out_path}'
          f'{f", {len(junctions)} junctions: {[round(j,1) for j in junctions]}" if junctions else ""}')


if __name__ == '__main__':
    main()
