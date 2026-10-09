"""Renders a static PNG (3 viewing angles side by side: front/side/top) of
the same original-vs-robot-constrained path comparison that
export_path_compare_html.py builds interactively, for quick visual review
without opening a browser. Saved into the Godot-facing data folder alongside
cavity_path_stone<id>.json and path_compare_stone<id>.html.

Usage:
    python export_path_compare_image.py --lab-id 1 --stone-id 1
"""
import argparse
import json
import os
import sys

import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

HERE = os.path.dirname(os.path.abspath(__file__))
PATHPLANNING_DIR = os.path.join(HERE, '..', 'PathPlanning')
GODOT_DATA_DIR = os.path.join(HERE, '..', 'data')

sys.path.insert(0, os.path.join(PATHPLANNING_DIR, 'src', 'pipeline'))
from riemann_optimizer import load_mesh  # noqa: E402 (read-only reuse, not modified)

VIEWS = [
    ('front (looking along Z)', 0, -90),
    ('side (looking along X)', 0, 0),
    ('top (looking down Y)', 90, -90),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--organ', default='organ_1_kidney', help='data/下的器官目录名，默认organ_1_kidney')
    ap.add_argument('--lab-id', required=True)
    ap.add_argument('--stone-id', required=True, type=int)
    ap.add_argument('--out', default=None,
                     help='输出路径 (默认 godot_sim/data/<organ>/lab_<id>/path_compare_stone<id>.png)')
    args = ap.parse_args()

    topo_path = os.path.join(PATHPLANNING_DIR, 'data', args.organ, f'lab_{args.lab_id}', 'result',
                              'topology_optimized', 'topology_optimized.json')
    smoothed_path = os.path.join(HERE, 'data', args.organ, f'lab_{args.lab_id}',
                                  f'topology_robot_smoothed_stone{args.stone_id}.json')
    cavity_stl = os.path.join(PATHPLANNING_DIR, 'data', args.organ, 'model', 'cavity.stl')

    if not os.path.exists(topo_path):
        raise SystemExit(f'未找到 {topo_path}，先在 PathPlanning 里跑 pick_stones.py + run_lab.py --organ {args.organ} --lab-id {args.lab_id}')
    if not os.path.exists(smoothed_path):
        raise SystemExit(f'未找到 {smoothed_path}，先跑 optimize_path_for_robot.py '
                          f'--lab-id {args.lab_id} --stone-id {args.stone_id}')

    topology = json.load(open(topo_path, encoding='utf-8'))
    path_info = next((p for p in topology['paths'] if p['stone_id'] == args.stone_id), None)
    if path_info is None:
        available = [p['stone_id'] for p in topology['paths']]
        raise SystemExit(f'lab_{args.lab_id} 里没有 stone_id={args.stone_id}，可选: {available}')
    orig = np.asarray(path_info['path_coordinates'], dtype=float)
    smoothed = np.asarray(json.load(open(smoothed_path, encoding='utf-8'))['paths'][0]['path_coordinates'],
                           dtype=float)

    mesh = load_mesh(cavity_stl)
    verts, faces = np.asarray(mesh.vertices), np.asarray(mesh.faces)
    tris = verts[faces]  # (n_faces, 3, 3)

    endpoint_gap = float(np.linalg.norm(orig[-1] - smoothed[-1]))
    orig_len = float(np.sum(np.linalg.norm(np.diff(orig, axis=0), axis=1)))
    smoothed_len = float(np.sum(np.linalg.norm(np.diff(smoothed, axis=0), axis=1)))

    all_pts = np.vstack([verts, orig, smoothed])
    center = all_pts.mean(axis=0)
    radius = np.max(np.linalg.norm(all_pts - center, axis=1)) * 1.05

    fig = plt.figure(figsize=(21, 7))
    for i, (title, elev, azim) in enumerate(VIEWS):
        ax = fig.add_subplot(1, 3, i + 1, projection='3d')
        poly = Poly3DCollection(tris, alpha=0.12, facecolor='lightgray', edgecolor='none')
        ax.add_collection3d(poly)

        ax.plot(orig[:, 0], orig[:, 1], orig[:, 2], color='red', linewidth=2, label='Original path')
        ax.plot(smoothed[:, 0], smoothed[:, 1], smoothed[:, 2], color='green', linewidth=2, label='Robot-constrained')
        ax.scatter(*orig[0], color='blue', s=40, label='Entry')
        ax.scatter(*orig[-1], color='red', s=40, marker='D', label='Stone (original)')
        ax.scatter(*smoothed[-1], color='green', s=40, marker='D', label='Stone (optimized)')

        ax.set_xlim(center[0] - radius, center[0] + radius)
        ax.set_ylim(center[1] - radius, center[1] + radius)
        ax.set_zlim(center[2] - radius, center[2] + radius)
        ax.set_box_aspect([1, 1, 1])
        ax.view_init(elev=elev, azim=azim)
        ax.set_title(title, fontsize=11)
        ax.set_xlabel('X (mm)')
        ax.set_ylabel('Y (mm)')
        ax.set_zlabel('Z (mm)')
        if i == 0:
            ax.legend(loc='upper left', fontsize=8)

    fig.suptitle(f'lab_{args.lab_id} / stone_{args.stone_id}: original {orig_len:.1f}mm vs '
                 f'robot-constrained {smoothed_len:.1f}mm (endpoint gap {endpoint_gap:.3f}mm)', fontsize=13)
    fig.tight_layout()

    out_path = args.out or os.path.join(
        GODOT_DATA_DIR, args.organ, f'lab_{args.lab_id}', f'path_compare_stone{args.stone_id}.png')
    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=150)
    print(f'已保存到 {out_path}')


if __name__ == '__main__':
    main()
