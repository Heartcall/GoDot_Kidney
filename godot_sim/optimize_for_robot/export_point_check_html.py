"""Unambiguous local check for whether a specific point is inside/outside the
cavity mesh -- draws the nearby mesh surface (cropped to a small radius
around the point, NOT the voxel debug view, which is easy to misread since
the voxel method is exactly what's in question), the point itself, and a
line from the point to its exact nearest surface location with the distance
labeled. Uses trimesh.proximity (ray-casting-based signed_distance +
closest_point), the method independently cross-verified earlier.

Usage:
    python export_point_check_html.py --x 10.2 --y 15.5 --z -82.8
"""
import argparse
import os
import sys

import numpy as np
import plotly.graph_objects as go
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
PATHPLANNING_DIR = os.path.join(HERE, '..', 'PathPlanning')

sys.path.insert(0, os.path.join(PATHPLANNING_DIR, 'src', 'pipeline'))
from riemann_optimizer import load_mesh  # noqa: E402 (read-only reuse, not modified)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--organ', default='organ_1_kidney', help='data/下的器官目录名，默认organ_1_kidney')
    ap.add_argument('--x', type=float, required=True)
    ap.add_argument('--y', type=float, required=True)
    ap.add_argument('--z', type=float, required=True)
    ap.add_argument('--crop-radius-mm', type=float, default=15.0, help='只画点周围这个半径内的网格面，其余裁掉')
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    cavity_stl = os.path.join(PATHPLANNING_DIR, 'data', args.organ, 'model', 'cavity.stl')
    mesh = load_mesh(cavity_stl)
    p = np.array([args.x, args.y, args.z])

    inside_val = float(trimesh.proximity.signed_distance(mesh, p[None, :])[0])  # 正=内部
    closest, dist, tri_id = trimesh.proximity.closest_point(mesh, p[None, :])
    closest = closest[0]
    print(f'点 {p.tolist()}: signed_distance={inside_val:.3f}mm ({"内部" if inside_val>0 else "外部"}), '
          f'到最近面欧氏距离={dist[0]:.3f}mm')

    verts, faces = np.asarray(mesh.vertices), np.asarray(mesh.faces)
    # 只保留三个顶点都在crop半径内的面，避免整个网格全画出来看不清局部
    d_to_p = np.linalg.norm(verts - p, axis=1)
    face_keep = d_to_p[faces].max(axis=1) <= args.crop_radius_mm
    kept_faces = faces[face_keep]
    used_vert_idx = np.unique(kept_faces)
    remap = -np.ones(len(verts), dtype=int)
    remap[used_vert_idx] = np.arange(len(used_vert_idx))
    crop_verts = verts[used_vert_idx]
    crop_faces = remap[kept_faces]
    print(f'裁剪后网格: {len(crop_verts)}个顶点, {len(crop_faces)}个面 (半径{args.crop_radius_mm}mm内)')

    fig = go.Figure()
    fig.add_trace(go.Mesh3d(
        x=crop_verts[:, 0], y=crop_verts[:, 1], z=crop_verts[:, 2],
        i=crop_faces[:, 0], j=crop_faces[:, 1], k=crop_faces[:, 2],
        color='lightgray', opacity=0.55, name='局部网格表面', flatshading=True,
    ))
    point_color = 'red' if inside_val <= 0 else 'green'
    fig.add_trace(go.Scatter3d(
        x=[p[0]], y=[p[1]], z=[p[2]], mode='markers+text',
        text=[f'查询点 ({"外部" if inside_val<=0 else "内部"} {abs(inside_val):.2f}mm)'],
        textposition='top center', marker=dict(size=7, color=point_color, symbol='diamond'), name='查询点',
    ))
    fig.add_trace(go.Scatter3d(
        x=[closest[0]], y=[closest[1]], z=[closest[2]], mode='markers+text',
        text=['最近网格面上的点'], textposition='bottom center',
        marker=dict(size=5, color='blue'), name='最近点',
    ))
    fig.add_trace(go.Scatter3d(
        x=[p[0], closest[0]], y=[p[1], closest[1]], z=[p[2], closest[2]],
        mode='lines', line=dict(color='orange', width=6, dash='dash'),
        name=f'距离 {dist[0]:.2f}mm',
    ))

    fig.update_layout(
        title=f'点 ({args.x},{args.y},{args.z}) 相对网格表面: '
              f'{"外部" if inside_val<=0 else "内部"} {abs(inside_val):.2f}mm (精确光线投射查询)',
        scene=dict(aspectmode='data', xaxis_title='X (mm)', yaxis_title='Y (mm)', zaxis_title='Z (mm)'),
        legend=dict(x=0.01, y=0.99),
        margin=dict(l=0, r=0, t=60, b=0),
    )

    safe_name = f'{args.x}_{args.y}_{args.z}'.replace('.', 'p').replace('-', 'm')
    out_path = args.out or os.path.join(HERE, f'point_check_{safe_name}.html')
    fig.write_html(out_path, include_plotlyjs=True)
    print(f'已保存到 {out_path}')


if __name__ == '__main__':
    main()
