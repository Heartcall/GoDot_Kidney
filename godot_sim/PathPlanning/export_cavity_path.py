"""Export one stone's optimized path from topology_optimized.json into the
format Godot's endoscope_controller.gd (auto-tour mode, T key) expects:
{"points": [[x,y,z],...], "forwards": [[dx,dy,dz],...]}.

Written to ../data/<organ>/lab_<id>/cavity_path_stone<stone-id>.json,
mirroring the same organ/lab layout PathPlanning's own data/ uses -- lets
multiple stones' routes coexist as separate files instead of one shared
cavity_path.json getting overwritten each time (endoscope_controller.gd's
cavity_path_file still needs to be pointed at whichever one you want to test;
switching between them isn't automated yet).

Coordinates are passed through as-is (mm) -- no unit conversion needed, since
the Godot scene now uses 1 unit = 1mm directly. "forwards" is the per-point
tangent direction (finite-difference on neighboring points).

Usage:
    python export_cavity_path.py --lab-id 1 --stone-id 1
    python export_cavity_path.py --organ organ_2_kidney --lab-id 1 --stone-id 1
    python export_cavity_path.py --lab-id 1 --stone-id 1 --out ../data/cavity_path.json
"""
import argparse
import json
import os

import numpy as np

HERE = os.path.dirname(__file__)


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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--organ', default='organ_1_kidney', help='data/下的器官目录名，默认organ_1_kidney')
    ap.add_argument('--lab-id', required=True, help='实验编号, 如 1')
    ap.add_argument('--stone-id', required=True, type=int, help='要导出哪颗结石的路径')
    ap.add_argument('--out', default=None,
                     help='输出路径 (默认 ../data/<organ>/lab_<id>/cavity_path_stone<id>.json)')
    args = ap.parse_args()

    topo_path = os.path.join(HERE, 'data', args.organ, f'lab_{args.lab_id}', 'result',
                              'topology_optimized', 'topology_optimized.json')
    if not os.path.exists(topo_path):
        raise SystemExit(f'未找到 {topo_path}，先跑 pick_stones.py + run_lab.py --organ {args.organ} --lab-id {args.lab_id}')
    topology = json.load(open(topo_path, encoding='utf-8'))

    path_info = next((p for p in topology['paths'] if p['stone_id'] == args.stone_id), None)
    if path_info is None:
        available = [p['stone_id'] for p in topology['paths']]
        raise SystemExit(f'lab_{args.lab_id} 里没有 stone_id={args.stone_id}，可选: {available}')

    points = np.asarray(path_info['path_coordinates'], dtype=float)
    forwards = compute_tangents(points)

    out_path = args.out or os.path.join(
        HERE, '..', 'data', args.organ, f'lab_{args.lab_id}', f'cavity_path_stone{args.stone_id}.json')
    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            'points': points.tolist(),
            'forwards': forwards.tolist(),
        }, f)

    print(f'{len(points)} 个点已导出到 {out_path}')


if __name__ == '__main__':
    main()
