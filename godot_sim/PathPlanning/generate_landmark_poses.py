"""Generate jittered camera poses around a lab's key landmarks -- skeleton
branch points, per-stone optimal viewing points, and (2026-08-12, per user
direction) points sampled every path-sample-spacing-mm directly along the
*riemann-optimized* path itself, since that's the actual curve the robot
follows -- for a Godot --photo-set capture.

For each landmark, samples a roll(0..360deg) x bend(0..max deg) grid of look
directions -- roll spins the tip around its own forward axis (rotates the
'up' vector, so the captured image itself rotates), bend deflects the tip
off that forward axis by up to bend-max-deg, with roll setting which radial
direction it deflects toward. Together they sweep a forward-facing cone,
the way a real endoscope tip steers (deflect + roll the shaft), never
panning to look sideways/backward. Position is sampled from the solid
backward hemisphere (radius hemisphere-radius-mm) around the landmark --
only the half opposing its own tangent direction, matching the robot's
1-DOF insertion/retraction (it can only pull back along its own path, never
push forward or move sideways on its own) -- and is rejected/resampled if
either check fails:
  1) the cavity's SDF interior margin (reusing riemann_optimizer.py's SDF
     grid), kept strictly above Camera3D's near-clip distance so nearby
     tissue can never fall inside the near-clip plane and get sliced away;
  2) a visibility check that raycasts the view center plus the 4 frustum
     corners and requires every one to hit the mesh within max-ray-check-mm
     -- catches the camera peeking through a thin/open edge of the cavity
     mesh at a grazing frustum-corner angle (seeing the void background)
     even when the camera position itself has plenty of SDF clearance.

Requires the lab's topology_optimized.json to already exist (run
pick_stones.py + run_lab.py for the lab first).

Usage:
    python generate_landmark_poses.py --lab-id 3
    python generate_landmark_poses.py --lab-id 3 --path-sample-spacing-mm 15 --bend-max-deg 20

Writes poses to ../data/lab<id>_landmark_poses.json (meters, matching what
EndoscopeController's --photo-set expects), ready for:
    godot --path . -- --photo-set=res://data/lab3_landmark_poses.json,captures_lab3
"""
import argparse
import json
import os
import sys

import networkx as nx
import numpy as np
import trimesh
from scipy.interpolate import RegularGridInterpolator

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, 'src', 'pipeline'))
from riemann_optimizer import load_mesh, create_sdf_grid

rng = np.random.default_rng(0)


def unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def frame_is_sealed(intersector, pos_mm, direction, up_r, right_r, fov_half_deg, max_ray_mm):
    """Casts the view-center ray plus the 4 true frustum-corner rays (not
    just the edge midpoints -- for a square-aspect perspective camera the
    diagonal corners sit at a wider angle than a single-axis half-fov
    rotation would reach, e.g. ~68deg vs 60deg for a 120deg fov, so corners
    are built in the camera's own tangent-plane: dir + tan(half_fov)*(+-right
    +-up)) and requires every one to hit the cavity mesh within max_ray_mm --
    catches the camera peeking past a thin/open edge of the mesh at a
    grazing frustum-corner angle (seeing the void background through a gap)
    even when the camera position itself has plenty of SDF clearance, since
    SDF only bounds the *nearest* surface in *some* direction, not what's
    actually in view."""
    view_right = unit(right_r - np.dot(right_r, direction) * direction)
    view_up = unit(up_r - np.dot(up_r, direction) * direction)
    t = np.tan(np.deg2rad(fov_half_deg))
    corner_dirs = [direction]
    for su in (-1.0, 1.0):
        for sv in (-1.0, 1.0):
            corner_dirs.append(unit(direction + su * t * view_right + sv * t * view_up))
    origins = np.tile(pos_mm, (len(corner_dirs), 1))
    dirs = np.array(corner_dirs)
    locations, index_ray, _ = intersector.intersects_location(origins, dirs, multiple_hits=False)
    if len(index_ray) < len(corner_dirs):
        return False  # some ray never hit the mesh at all
    hit_dist = np.linalg.norm(locations - origins[index_ray], axis=1)
    per_ray_min = np.full(len(corner_dirs), np.inf)
    for i, d in zip(index_ray, hit_dist):
        per_ray_min[i] = min(per_ray_min[i], d)
    return bool(np.all(per_ray_min <= max_ray_mm))


def build_frame(forward, ref_axis=np.array([0.0, 0.0, 1.0])):
    """Right-handed (forward, up, right) basis, Gram-Schmidt against ref_axis
    (falls back to the X axis if forward is nearly parallel to it)."""
    forward = unit(forward)
    if abs(np.dot(forward, ref_axis)) > 0.95:
        ref_axis = np.array([1.0, 0.0, 0.0])
    up = unit(ref_axis - np.dot(ref_axis, forward) * forward)
    right = unit(np.cross(forward, up))
    return forward, up, right


def resample_by_arclength(points, ds):
    points = np.asarray(points, dtype=float)
    seg = np.linalg.norm(np.diff(points, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]
    targets = np.arange(0.0, total, ds)
    out = np.empty((len(targets), 3))
    for i, s in enumerate(targets):
        j = np.searchsorted(cum, s, side='right') - 1
        j = min(max(j, 0), len(points) - 2)
        t = 0.0 if cum[j + 1] == cum[j] else (s - cum[j]) / (cum[j + 1] - cum[j])
        out[i] = points[j] * (1 - t) + points[j + 1] * t
    return out


def extract_landmarks(topology, cluster_dist_mm, path_sample_spacing_mm=None, path_sample_skip_first=0):
    """Skeleton branch points (degree>=3 over 'skeleton'-type edges only,
    excluding the synthetic urethra/stone connector edges), each path's
    optimal viewing point, and -- if path_sample_spacing_mm is given -- points
    sampled at that fixed arc-length spacing directly along the *riemann-
    optimized* path itself (the actual curve the robot follows, not just the
    pre-optimization skeleton topology). Any landmark closer than
    cluster_dist_mm to one already picked is dropped (branch-point voxel
    near-duplicates, or a path sample landing right next to a branch/optimal
    point)."""
    nodes = {n['node_id']: np.array(n['position']) for n in topology['nodes']}

    G = nx.Graph()
    for n in topology['nodes']:
        G.add_node(n['node_id'])
    for e in topology['edges']:
        if e['type'] == 'skeleton':
            G.add_edge(e['source'], e['target'])
    deg = dict(G.degree())
    branch_ids = [n for n, dg in deg.items() if dg >= 3]

    clusters = []
    for bid in branch_ids:
        p = nodes[bid]
        placed = False
        for c in clusters:
            if np.linalg.norm(p - nodes[c[0]]) < cluster_dist_mm:
                c.append(bid)
                placed = True
                break
        if not placed:
            clusters.append([bid])

    landmarks = []
    for c in clusters:
        pos = np.mean([nodes[n] for n in c], axis=0)
        neighbor_dirs = []
        for n in c:
            for nb in G.neighbors(n):
                if nb not in c:
                    neighbor_dirs.append(unit(nodes[nb] - nodes[n]))
        forward = np.mean(neighbor_dirs, axis=0) if neighbor_dirs else np.array([1.0, 0.0, 0.0])
        landmarks.append({'name': 'branch_' + c[0], 'kind': 'branch', 'pos': pos, 'forward': unit(forward)})

    for p in topology['paths']:
        pts = np.array(p['path_coordinates'])
        forward = unit(pts[-1] - pts[-2])
        landmarks.append({
            'name': f"optimal_stone{p['stone_id']}", 'kind': 'optimal_point',
            'pos': np.array(p['optimal_point']), 'forward': forward,
        })

    if path_sample_spacing_mm:
        for p in topology['paths']:
            pts = np.array(p['path_coordinates'])
            resampled = resample_by_arclength(pts, path_sample_spacing_mm)
            for i in range(1 + path_sample_skip_first, len(resampled) - 1):
                pos = resampled[i]
                if any(np.linalg.norm(pos - lm['pos']) < cluster_dist_mm for lm in landmarks):
                    continue
                forward = unit(resampled[min(i + 1, len(resampled) - 1)] - resampled[max(i - 1, 0)])
                landmarks.append({
                    'name': f"path_stone{p['stone_id']}_{i:03d}", 'kind': 'path_sample',
                    'pos': pos, 'forward': forward,
                })
    return landmarks


def sample_poses(landmarks, sdf_at, intersector, hemisphere_radius_mm, interior_margin_mm,
                  roll_steps, bend_steps, bend_max_deg, fov_deg, max_ray_mm):
    """roll = spin around the forward axis, 0..360deg (rotates the 'up'
    vector -> rotates the captured image itself). bend = how far the tip
    deflects off the forward axis, 0..bend_max_deg; which radial direction
    it deflects toward is set by roll, so (roll x bend) sweeps a forward-
    facing cone -- never looking sideways/backward -- matching a real
    endoscope tip (steerable deflection + shaft roll), instead of panning
    the look direction across a full equator. Position is sampled from the
    solid *backward* hemisphere of radius hemisphere_radius_mm around the
    landmark (i.e. only the half where the offset points against the
    landmark's own forward/tangent direction) -- matching the robot's 1-DOF
    insertion/retraction (it can only pull back along its own path, never
    push forward past the landmark or move sideways on its own), while still
    giving the SDF/visibility retry loop a 3D volume to search instead of a
    single line (2026-08-12: a pure 1D retreat line had ~20% fallback rate;
    this hemisphere keeps the same "backward only" physical constraint but
    with much better odds of finding a valid point)."""
    rolls = np.linspace(0, 2 * np.pi, roll_steps, endpoint=False)
    bends = np.deg2rad(np.linspace(0, bend_max_deg, bend_steps))
    fov_half_deg = fov_deg / 2.0

    poses = []
    rejected_fallback = 0
    for lm in landmarks:
        forward, up0, right0 = build_frame(lm['forward'])
        for roll in rolls:
            right_r = np.cos(roll) * right0 + np.sin(roll) * up0
            up_r = -np.sin(roll) * right0 + np.cos(roll) * up0
            for bend in bends:
                direction = np.cos(bend) * forward + np.sin(bend) * right_r
                pos_mm = None
                for _attempt in range(40):
                    offset = unit(rng.normal(size=3))
                    if np.dot(offset, forward) > 0:
                        offset = -offset  # reflect into the backward hemisphere
                    r = hemisphere_radius_mm * rng.uniform(0, 1) ** (1 / 3)  # uniform-in-volume
                    cand = lm['pos'] + offset * r
                    if sdf_at(cand) > -interior_margin_mm:
                        continue
                    if not frame_is_sealed(intersector, cand, direction, up_r, right_r, fov_half_deg, max_ray_mm):
                        continue
                    pos_mm = cand
                    break
                if pos_mm is None:
                    pos_mm = lm['pos']
                    rejected_fallback += 1
                pos_m = pos_mm / 1000.0  # topology/cavity STLs are in mm, Godot poses are in meters
                poses.append({
                    'pos': pos_m.tolist(),
                    'dir': direction.tolist(),
                    'up': up_r.tolist(),
                    'landmark': lm['name'],
                    'kind': lm['kind'],
                })
    return poses, rejected_fallback


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--organ', default='organ_1_kidney', help='data/下的器官目录名，默认organ_1_kidney')
    ap.add_argument('--lab-id', required=True, help='实验编号, 如 3')
    ap.add_argument('--hemisphere-radius-mm', type=float, default=1.0,
                     help='后撤活动范围: 地标后方半球体的半径 (mm), 只在切线反方向的半球内采样位置')
    ap.add_argument('--path-sample-spacing-mm', type=float, default=10.0,
                     help='额外沿黎曼优化后的路径本身每隔多少mm取一个地标 (0 关闭, 只用分叉点+最佳观测点)')
    ap.add_argument('--path-sample-skip-first', type=int, default=5,
                     help='每条路径跳过最前面几个均匀间隔的采样点 (靠近尿道口入口, 2026-08-12 起去掉)')
    ap.add_argument('--interior-margin', type=float, default=1.2,
                     help='SDF 安全边距 (mm). 必须大于 Camera3D 的 near clip (main.tscn 里是 0.001m=1mm), '
                          '否则墙面比近裁剪面还近, 会被裁掉产生穿模 -- 比 run_lab.py 路径优化用的 0.5mm 更严格, '
                          '那个是给路径中心线保安全距离用的, 不受近裁剪面约束')
    ap.add_argument('--roll-steps', type=int, default=10, help='镜头绕自身光轴周转 360 度的采样步数')
    ap.add_argument('--bend-steps', type=int, default=10, help='镜头弯曲角度 (0..bend-max-deg) 的采样步数')
    ap.add_argument('--bend-max-deg', type=float, default=30.0, help='镜头相对中心轴最大弯曲角度 (度)')
    ap.add_argument('--fov-deg', type=float, default=120.0, help='Camera3D 的 fov (main.tscn 里也是 120), 用于取景可见性检查')
    ap.add_argument('--max-ray-check-mm', type=float, default=20.0,
                     help='中心+4个画面边角方向的射线必须在这个距离内打到网格上, 否则判定为穿过薄壁/缝隙看到了背景, 重新采样位置')
    ap.add_argument('--cluster-dist-mm', type=float, default=3.0, help='相邻分叉点合并阈值 (mm)')
    ap.add_argument('--sdf-resolution-mm', type=float, default=1.0, help='SDF 体素分辨率, 与 riemann_optimizer.py 默认一致')
    ap.add_argument('--sdf-padding-mm', type=float, default=5.0)
    ap.add_argument('--out', default=None, help='输出路径 (默认 ../data/lab<id>_landmark_poses.json)')
    ap.add_argument('--split-by-landmark', action='store_true',
                     help='不写单个合并文件, 而是每个地标单独写一个 poses 文件到 '
                          '../data/lab<id>_landmark_poses/<landmark>.json, 方便分开拍/分开存')
    args = ap.parse_args()

    topo_path = os.path.join(HERE, 'data', args.organ, f'lab_{args.lab_id}', 'result', 'topology_optimized', 'topology_optimized.json')
    if not os.path.exists(topo_path):
        raise SystemExit(f'未找到 {topo_path}，先跑 pick_stones.py + run_lab.py --organ {args.organ} --lab-id {args.lab_id}')
    topology = json.load(open(topo_path, encoding='utf-8'))

    cavity_stl = os.path.join(HERE, 'data', args.organ, 'model', 'cavity.stl')

    landmarks = extract_landmarks(topology, args.cluster_dist_mm, args.path_sample_spacing_mm, args.path_sample_skip_first)
    print(f'{len(landmarks)} landmarks: ' + ', '.join(l['name'] for l in landmarks))

    print('building SDF grid (mm) from', cavity_stl, '...')
    mesh = load_mesh(cavity_stl)
    sdf_grid, origin, step = create_sdf_grid(mesh, resolution=args.sdf_resolution_mm, padding=args.sdf_padding_mm)
    x = origin[0] + step * np.arange(sdf_grid.shape[0])
    y = origin[1] + step * np.arange(sdf_grid.shape[1])
    z = origin[2] + step * np.arange(sdf_grid.shape[2])
    sdf_interp = RegularGridInterpolator((x, y, z), sdf_grid, bounds_error=False, fill_value=np.max(sdf_grid))
    sdf_at = lambda p: float(sdf_interp(p[None, :])[0])
    intersector = trimesh.ray.ray_triangle.RayMeshIntersector(mesh)

    poses, rejected_fallback = sample_poses(
        landmarks, sdf_at, intersector, args.hemisphere_radius_mm, args.interior_margin,
        args.roll_steps, args.bend_steps, args.bend_max_deg, args.fov_deg, args.max_ray_check_mm)
    print(f'generated {len(poses)} poses ({rejected_fallback} fell back to exact landmark position after 40 failed attempts)')

    # organ_1_kidney keeps the original bare filename (no organ prefix) for
    # backward compatibility with existing invocations; any other organ gets
    # its own subfolder so labs of the same id across organs don't collide.
    organ_prefix = '' if args.organ == 'organ_1_kidney' else f'{args.organ}_'

    if args.split_by_landmark:
        out_dir = args.out or os.path.join(HERE, '..', 'data', f'{organ_prefix}lab{args.lab_id}_landmark_poses')
        out_dir = os.path.abspath(out_dir)
        os.makedirs(out_dir, exist_ok=True)
        by_landmark = {}
        for p in poses:
            by_landmark.setdefault(p['landmark'], []).append(p)
        print()
        for name, plist in by_landmark.items():
            out_path = os.path.join(out_dir, f'{name}.json')
            with open(out_path, 'w') as f:
                json.dump({'poses': plist}, f)
            rel = os.path.relpath(out_path, os.path.join(HERE, '..'))
            print(f'wrote {len(plist)} poses to {out_path}')
            print(f'  godot --path . -- --photo-set=res://{rel},captures_lab{args.lab_id}/{name}')
    else:
        out_path = args.out or os.path.join(HERE, '..', 'data', f'{organ_prefix}lab{args.lab_id}_landmark_poses.json')
        out_path = os.path.abspath(out_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'w') as f:
            json.dump({'poses': poses}, f)
        print('wrote', out_path)
        print(f'capture with: godot --path . -- --photo-set=res://data/{os.path.basename(out_path)},captures_lab{args.lab_id}')


if __name__ == '__main__':
    main()
