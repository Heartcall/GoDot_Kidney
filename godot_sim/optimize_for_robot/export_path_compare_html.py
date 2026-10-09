"""Builds an interactive Plotly HTML comparing PathPlanning's raw
riemann_optimizer path (topology_optimized.json) against
optimize_path_for_robot.py's curvature-and-wall-constrained result
(this folder's data/organ_1_kidney/lab_<id>/topology_robot_smoothed_stone<id>.json),
and drops it into the Godot-facing data folder
(godot_sim/data/organ_1_kidney/lab_<id>/) alongside cavity_path_stone<id>.json,
so both live together as the "final" per-lab outputs.

Usage:
    python export_path_compare_html.py --lab-id 1 --stone-id 1
"""
import argparse
import json
import os
import sys

import numpy as np
import plotly.graph_objects as go

HERE = os.path.dirname(os.path.abspath(__file__))
PATHPLANNING_DIR = os.path.join(HERE, '..', 'PathPlanning')
GODOT_DATA_DIR = os.path.join(HERE, '..', 'data')

sys.path.insert(0, os.path.join(PATHPLANNING_DIR, 'src', 'pipeline'))
from riemann_optimizer import load_mesh  # noqa: E402 (read-only reuse, not modified)

from check_path_curvature import resample_by_arclength, active_violation_mask  # noqa: E402
from export_cavity_path_for_godot import compute_junction_offsets  # noqa: E402

ACTIVE_MIN_RADIUS_MM = 10.0
MIN_ACTIVE_DEVIATION_MM = 0.2  # 半径小但实际物理偏移量不到这个值，算数值抖动级假阳性，不标记


def find_active_violations(points: np.ndarray) -> np.ndarray:
    """按1mm弧长重采样后用严苛的三点法逐点检查，返回主动段超标的点坐标 (Nx3)。
    过滤掉半径小但实际物理偏移量不到 MIN_ACTIVE_DEVIATION_MM 的假阳性(重采样/平滑
    留下的数值抖动，不是真实急弯)。"""
    resampled, _ = resample_by_arclength(points, 1.0)
    bad = active_violation_mask(resampled, ACTIVE_MIN_RADIUS_MM, MIN_ACTIVE_DEVIATION_MM)
    return resampled[bad]


def point_at_offset(points: np.ndarray, offset: float) -> np.ndarray:
    """沿points的弧长走到offset(mm)处，线性插值出对应的3D坐标。"""
    seg = np.linalg.norm(np.diff(points, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    offset = float(np.clip(offset, 0.0, cum[-1]))
    j = min(np.searchsorted(cum, offset, side='right') - 1, len(points) - 2)
    j = max(j, 0)
    seg_len = cum[j + 1] - cum[j]
    t = 0.0 if seg_len < 1e-9 else (offset - cum[j]) / seg_len
    return points[j] * (1 - t) + points[j + 1] * t


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--organ', default='organ_1_kidney', help='data/下的器官目录名，默认organ_1_kidney')
    ap.add_argument('--lab-id', required=True)
    ap.add_argument('--stone-id', required=True, type=int)
    ap.add_argument('--out', default=None,
                     help='输出路径 (默认 godot_sim/data/<organ>/lab_<id>/path_compare_stone<id>.html)')
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

    fig = go.Figure()
    fig.add_trace(go.Mesh3d(
        x=verts[:, 0], y=verts[:, 1], z=verts[:, 2],
        i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
        color='lightgray', opacity=0.4, name='cavity', hoverinfo='skip', flatshading=True,
    ))
    fig.add_trace(go.Scatter3d(
        x=orig[:, 0], y=orig[:, 1], z=orig[:, 2],
        mode='lines+markers', line=dict(color='red', width=5), marker=dict(size=2, color='red'),
        name=f'原始路径 ({len(orig)}点, {_path_len(orig):.1f}mm)',
    ))
    fig.add_trace(go.Scatter3d(
        x=smoothed[:, 0], y=smoothed[:, 1], z=smoothed[:, 2],
        mode='lines+markers', line=dict(color='green', width=5), marker=dict(size=2, color='green'),
        name=f'机器人约束优化后 ({len(smoothed)}点, {_path_len(smoothed):.1f}mm)',
    ))
    for label, p, color in [('入口', orig[0], 'blue'), ('结石(原始终点)', orig[-1], 'red'),
                             ('结石(优化后终点)', smoothed[-1], 'green')]:
        fig.add_trace(go.Scatter3d(
            x=[p[0]], y=[p[1]], z=[p[2]], mode='markers+text', text=[label], textposition='top center',
            marker=dict(size=6, color=color, symbol='diamond'), name=label,
        ))

    # 主动段曲率超标点 (逐点三点法, 半径 < 10mm)，跟 check_path_curvature.py 同一套判据
    orig_bad = find_active_violations(orig)
    smoothed_bad = find_active_violations(smoothed)
    for label, pts, color in [(f'原始路径主动段超标 ({len(orig_bad)}点)', orig_bad, 'darkred'),
                               (f'优化后主动段超标 ({len(smoothed_bad)}点)', smoothed_bad, 'darkorange')]:
        if len(pts) == 0:
            continue
        fig.add_trace(go.Scatter3d(
            x=pts[:, 0], y=pts[:, 1], z=pts[:, 2], mode='markers', name=label,
            marker=dict(size=5, color=color, symbol='x'),
        ))

    # 真实岔道口 (拓扑图里度数>=3的骨架分支点, 见 export_cavity_path_for_godot.py) --
    # endoscope_controller.gd 只在这些点附近才重新计算周转角度，其余单一通道内周转保持不变
    junction_offsets = compute_junction_offsets(smoothed, args.organ, args.lab_id, args.stone_id)
    if junction_offsets:
        junction_pts = np.array([point_at_offset(smoothed, off) for off in junction_offsets])
        fig.add_trace(go.Scatter3d(
            x=junction_pts[:, 0], y=junction_pts[:, 1], z=junction_pts[:, 2],
            mode='markers+text', text=[f'岔道口 {off:.0f}mm' for off in junction_offsets],
            textposition='top center', name=f'岔道口 ({len(junction_offsets)}处)',
            marker=dict(size=8, color='purple', symbol='diamond-open', line=dict(width=3)),
        ))

    endpoint_gap = float(np.linalg.norm(orig[-1] - smoothed[-1]))
    fig.update_layout(
        title=f'lab_{args.lab_id} / stone_{args.stone_id}: 原始 vs 机器人约束优化后 (终点误差 {endpoint_gap:.3f}mm)',
        scene=dict(aspectmode='data', xaxis_title='X (mm)', yaxis_title='Y (mm)', zaxis_title='Z (mm)'),
        legend=dict(x=0.01, y=0.99),
        margin=dict(l=0, r=0, t=40, b=0),
    )

    out_path = args.out or os.path.join(
        GODOT_DATA_DIR, args.organ, f'lab_{args.lab_id}', f'path_compare_stone{args.stone_id}.html')
    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.write_html(out_path, include_plotlyjs=True)
    print(f'已保存到 {out_path} (终点误差 {endpoint_gap:.3f}mm)')


def _path_len(points: np.ndarray) -> float:
    return float(np.sum(np.linalg.norm(np.diff(points, axis=0), axis=1)))


if __name__ == '__main__':
    main()
