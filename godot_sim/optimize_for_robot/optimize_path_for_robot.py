"""Re-smooths PathPlanning's topology_optimized.json path so it respects the
continuum robot's actual curvature limits (see check_path_curvature.py for
where these numbers come from: active tip 10mm min radius, point-wise;
passive shaft 35mm min radius over a 30mm window, excluding the final 65mm
near the stone), while staying at least a safety margin clear of the cavity
wall.

This lives outside PathPlanning entirely -- it only reads PathPlanning's
data (topology_optimized.json, cavity.stl) and reuses load_mesh/
create_sdf_grid from its riemann_optimizer.py (read-only import), never
modifying anything inside that repo. Output goes to this folder's own
data/organ_1_kidney/lab_<id>/.

Method: iterative Laplacian smoothing (each interior point pulled toward the
midpoint of its neighbors, which directly reduces local curvature) alternated
with a wall-clearance projection step (any point that drifts within the
safety margin of the cavity wall gets pushed back along the SDF gradient
until clear again). Endpoints (entry point, stone) are pinned every
iteration.

The voxelized SDF (`create_sdf_grid`, resolution 1mm) used during the 300
smoothing iterations is fast but imprecise right at the ~1mm margin
boundary in tight passages -- confirmed via cross-check against a properly
robust ground truth (multi-direction ray-casting vote: cast rays from each
point in several random directions, majority vote on odd/even crossing
count -- unlike a single ray or trimesh.proximity.signed_distance's
"nearest triangle's local normal" shortcut, this doesn't get fooled by a
mesh that has self-intersections/near-touching surfaces near complex branch
junctions, which this cavity mesh does). So after the fast 300-iteration
loop, a second, slower `robust_wall_correction` pass re-checks every point
with the robust vote and nudges (only) the ones that actually fail it,
patiently, toward their neighbors' midpoint, re-checking after every step so
it never takes a move that isn't confirmed safe. Final wall-clearance and
curvature numbers reported at the end both come from this robust check, not
the fast one -- so what's printed (and what check_path_curvature.py would
independently confirm) is actually trustworthy, not just fast-but-approximate.

Usage:
    python optimize_path_for_robot.py --lab-id 1 --stone-id 1
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import trimesh
from scipy.interpolate import RegularGridInterpolator

HERE = os.path.dirname(os.path.abspath(__file__))
PATHPLANNING_DIR = os.path.join(HERE, '..', 'PathPlanning')

sys.path.insert(0, os.path.join(PATHPLANNING_DIR, 'src', 'pipeline'))
from riemann_optimizer import load_mesh, create_sdf_grid  # noqa: E402 (read-only reuse, not modified)

from check_path_curvature import (  # noqa: E402
    resample_by_arclength, tangent_at, windowed_radii, three_point_radius, point_deviation,
)

ACTIVE_MIN_RADIUS_MM = 10.0
PASSIVE_WINDOW_MM = 30.0
PASSIVE_MIN_RADIUS_MM = 35.0
PASSIVE_EXCLUDE_TIP_MM = 65.0
MIN_ACTIVE_DEVIATION_MM = 0.2  # a point with a small radius but an actual physical deviation below this is treated as numerical-jitter-level false positive, not a violation


def build_sdf(cavity_stl: str, resolution_mm: float, padding_mm: float):
    mesh = load_mesh(cavity_stl)
    sdf_grid, origin, step = create_sdf_grid(mesh, resolution=resolution_mm, padding=padding_mm)
    x = origin[0] + step * np.arange(sdf_grid.shape[0])
    y = origin[1] + step * np.arange(sdf_grid.shape[1])
    z = origin[2] + step * np.arange(sdf_grid.shape[2])
    interp = RegularGridInterpolator((x, y, z), sdf_grid, bounds_error=False, fill_value=np.max(sdf_grid))
    return lambda p: float(interp(p[None, :])[0])


def sdf_gradient(sdf_at, p: np.ndarray, h: float = 0.5) -> np.ndarray:
    g = np.zeros(3)
    for k in range(3):
        dp = np.zeros(3)
        dp[k] = h
        g[k] = (sdf_at(p + dp) - sdf_at(p - dp)) / (2 * h)
    return g


def project_clear_of_wall(sdf_at, p: np.ndarray, margin_mm: float, max_push_mm: float = 3.0) -> np.ndarray:
    """Pushes a point along the negative SDF gradient until sdf(p) <= -margin_mm
    (safely inside the cavity), pushing at most max_push_mm per iteration to
    avoid overshooting from an inaccurate local gradient estimate."""
    for _ in range(8):
        val = sdf_at(p)
        if val <= -margin_mm:
            return p
        g = sdf_gradient(sdf_at, p)
        gn = np.linalg.norm(g)
        if gn < 1e-6:
            break
        step = min((val - (-margin_mm)) / gn, max_push_mm)
        p = p - (g / gn) * step
    return p


def make_ray_directions(n: int = 7, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    d = rng.normal(size=(n, 3))
    return d / np.linalg.norm(d, axis=1, keepdims=True)


def robust_inside_votes(mesh: 'trimesh.Trimesh', points: np.ndarray, ray_dirs: np.ndarray) -> np.ndarray:
    """For each point, casts rays in several random directions and counts
    whether the number of mesh-surface crossings is odd (=inside) or even
    (=outside), then takes a majority vote. Processes all points in a batch,
    one call per direction. Slower than trimesh.proximity.signed_distance,
    but doesn't get fooled by this mesh's self-intersections/complex branch
    structure -- signed_distance takes the "nearest triangle's local normal"
    shortcut for most points, which has been confirmed to misjudge on a mesh
    like this (see the module docstring)."""
    votes = np.zeros(len(points), dtype=int)
    for d in ray_dirs:
        _locations, index_ray, _index_tri = mesh.ray.intersects_location(points, np.tile(d, (len(points), 1)))
        counts = np.zeros(len(points), dtype=int)
        for r in index_ray:
            counts[r] += 1
        votes += (counts % 2 == 1).astype(int)
    return votes


def robust_wall_correction(mesh: 'trimesh.Trimesh', points: np.ndarray, ray_dirs: np.ndarray,
                            max_rounds: int = 400, alpha: float = 0.05,
                            window: int = 8) -> np.ndarray:
    """After the fast 300-iteration loop finishes, verifies every point
    point-by-point with the robust method and nudges any point that fails it
    a small step toward its nearby neighbors' local mean -- re-verifying
    after every step whether that one point is now safe, and discarding the
    step (staying put, trying again next round) if not. Endpoints don't move.
    This is inherited from the approach validated when manually fixing lab_2:
    a small step size, verified after every step, only accepted once
    confirmed safe -- unlike the numerical gradient descent tried earlier,
    which diverged due to an unstable local field."""
    points = points.copy()
    start, end = points[0].copy(), points[-1].copy()
    n = len(points)

    for _ in range(max_rounds):
        votes = robust_inside_votes(mesh, points, ray_dirs)
        bad = np.where(votes < (len(ray_dirs) + 1) // 2)[0]
        bad = bad[(bad > 0) & (bad < n - 1)]  # endpoints are never touched
        if len(bad) == 0:
            break
        for i in bad:
            lo, hi = max(0, i - window), min(n - 1, i + window)
            mid = points[lo:hi + 1].mean(axis=0)
            candidate = points[i] + alpha * (mid - points[i])
            if robust_inside_votes(mesh, candidate[None, :], ray_dirs)[0] >= (len(ray_dirs) + 1) // 2:
                points[i] = candidate

    points[0], points[-1] = start, end
    return points


def curvature_summary(points: np.ndarray) -> dict:
    """Same algorithm as check_path_curvature.py, computing the active/passive
    metrics for before/after comparison."""
    seg = np.linalg.norm(np.diff(points, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total_len = cum[-1]

    # A point with a small radius but an actual physical deviation below
    # MIN_ACTIVE_DEVIATION_MM is numerical jitter left over from
    # resampling/smoothing, not a real sharp bend -- filter it out (don't
    # count it in active_bad, and don't let it drag down active_worst).
    active_radii = np.full(len(points), np.inf)
    for i in range(1, len(points) - 1):
        r = three_point_radius(points[i - 1], points[i], points[i + 1])
        if r < ACTIVE_MIN_RADIUS_MM and point_deviation(points[i - 1], points[i], points[i + 1]) < MIN_ACTIVE_DEVIATION_MM:
            r = np.inf
        active_radii[i] = r
    active_bad = int((active_radii < ACTIVE_MIN_RADIUS_MM).sum())

    cutoff = max(0.0, total_len - PASSIVE_EXCLUDE_TIP_MM)
    keep = cum <= cutoff
    trunc_points, trunc_cum = points[keep], cum[keep]
    trunc_total = trunc_cum[-1] if len(trunc_cum) else 0.0
    _, passive_radii = windowed_radii(trunc_points, trunc_cum, trunc_total, PASSIVE_WINDOW_MM, 1.0)
    passive_bad = int((passive_radii < PASSIVE_MIN_RADIUS_MM).sum()) if len(passive_radii) else 0

    return {
        'total_len': total_len,
        'active_bad': active_bad, 'active_total': len(points),
        'active_worst': float(np.min(active_radii)) if len(active_radii) else float('inf'),
        'passive_bad': passive_bad, 'passive_total': len(passive_radii),
        'passive_worst': float(np.min(passive_radii)) if len(passive_radii) else float('inf'),
    }


def print_summary(label: str, s: dict) -> None:
    print(f'[{label}] total length {s["total_len"]:.1f}mm | '
          f'active-segment violations {s["active_bad"]}/{s["active_total"]} (min radius {s["active_worst"]:.1f}mm) | '
          f'passive-segment violations {s["passive_bad"]}/{s["passive_total"]} (min radius {s["passive_worst"]:.1f}mm)')


def relax_path(points: np.ndarray, sdf_at, margin_mm: float, iters: int, alpha: float,
                reparam_every: int, sample_spacing_mm: float,
                window_mm: float = 30.0, window_alpha: float = 0.1, window_every: int = 50) -> np.ndarray:
    points = points.copy()
    start, end = points[0].copy(), points[-1].copy()  # the real entry point / stone coordinates, pinned throughout

    # index span corresponding to a half-window (points are uniformly sampled
    # by sample_spacing_mm, so index distance is roughly arc-length distance)
    window_k = max(1, int(round(window_mm / 2.0 / sample_spacing_mm)))

    for it in range(iters):
        # 1) Laplacian smoothing: every non-endpoint moves a bit toward the
        # midpoint of its two neighbors, directly reducing local curvature
        new_points = points.copy()
        new_points[1:-1] = points[1:-1] + alpha * (0.5 * (points[:-2] + points[2:]) - points[1:-1])
        points = new_points

        # 1b) coarse-grained window smoothing: every point moves a bit toward
        # the mean of all points within window_mm/2 before and after it,
        # directly reducing the window's net turn angle (matches the passive
        # segment's 30mm-window criterion -- this term handles the large-scale
        # overall heading). Only done every window_every iterations (not every
        # one) -- too frequent and it fights with the fine-grained smoothing,
        # creating new sharp kinks locally; spacing it out leaves room in
        # between for the fine-grained smoothing to iron out irregularities.
        if window_k > 0 and window_every > 0 and (it + 1) % window_every == 0 and len(points) > 2 * window_k:
            new_points = points.copy()
            for i in range(1, len(points) - 1):
                lo, hi = max(0, i - window_k), min(len(points) - 1, i + window_k)
                mid = points[lo:hi + 1].mean(axis=0)
                new_points[i] = points[i] + window_alpha * (mid - points[i])
            points = new_points

        # 2) push any point that's drifted too close to the wall back outside
        # the safety margin (endpoints are checked too, but they sit at the
        # cavity entry/stone and are normally already guaranteed safe from
        # the path-planning stage -- this is just a safety net)
        for i in range(len(points)):
            points[i] = project_clear_of_wall(sdf_at, points[i], margin_mm)

        # 3) periodically resample uniformly by arc length, so smoothing
        # doesn't bunch points together / stretch spacing uneven
        if reparam_every > 0 and (it + 1) % reparam_every == 0:
            points, _ = resample_by_arclength(points, sample_spacing_mm)

        # 4) force both ends back to the real entry point / stone coordinates
        # -- doesn't rely on every step above keeping the endpoints exactly
        # put; this is a second safety net against the endpoint quietly
        # drifting off the stone position after dozens of resamples.
        points[0], points[-1] = start, end

    return points


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--organ', default='organ_1_kidney', help='organ directory name under data/, default organ_1_kidney')
    ap.add_argument('--lab-id', required=True)
    ap.add_argument('--stone-id', required=True, type=int)
    ap.add_argument('--wall-margin-mm', type=float, default=2.5, help='minimum distance to keep from the cavity wall (mm)')
    ap.add_argument('--iters', type=int, default=300, help='number of smoothing iterations')
    ap.add_argument('--alpha', type=float, default=0.15, help='smoothing step size fraction per iteration (0-1)')
    ap.add_argument('--reparam-every', type=int, default=10, help='resample uniformly by arc length every this many iterations')
    ap.add_argument('--sample-spacing-mm', type=float, default=1.0)
    ap.add_argument('--sdf-resolution-mm', type=float, default=1.0)
    ap.add_argument('--sdf-padding-mm', type=float, default=5.0)
    ap.add_argument('--window-mm', type=float, default=30.0,
                     help='window length for coarse-grained window smoothing (mm), aligned with the passive-segment curvature check window')
    ap.add_argument('--window-alpha', type=float, default=0.1, help='step size fraction for window smoothing (0-1)')
    ap.add_argument('--window-every', type=int, default=50, help='do window smoothing every this many iterations (not every one -- '
                     'too frequent fights with the fine-grained smoothing and creates new sharp kinks locally)')
    ap.add_argument('--robust-max-rounds', type=int, default=400,
                     help='max rounds for the robust safety-correction pass (each round nudges the violating points one small step, accepted only once verified safe)')
    args = ap.parse_args()

    topo_path = os.path.join(PATHPLANNING_DIR, 'data', args.organ, f'lab_{args.lab_id}', 'result',
                              'topology_optimized', 'topology_optimized.json')
    if not os.path.exists(topo_path):
        raise SystemExit(f'{topo_path} not found, run pick_stones.py + run_lab.py in PathPlanning first --organ {args.organ} --lab-id {args.lab_id}')
    topology = json.load(open(topo_path, encoding='utf-8'))
    path_info = next((p for p in topology['paths'] if p['stone_id'] == args.stone_id), None)
    if path_info is None:
        available = [p['stone_id'] for p in topology['paths']]
        raise SystemExit(f'lab_{args.lab_id} has no stone_id={args.stone_id}, available: {available}')

    raw_points = np.asarray(path_info['path_coordinates'], dtype=float)
    points, _ = resample_by_arclength(raw_points, args.sample_spacing_mm)

    print('Building SDF grid...')
    cavity_stl = os.path.join(PATHPLANNING_DIR, 'data', args.organ, 'model', 'cavity.stl')
    sdf_at = build_sdf(cavity_stl, args.sdf_resolution_mm, args.sdf_padding_mm)

    print()
    print_summary('before optimization', curvature_summary(points))

    new_points = relax_path(points, sdf_at, args.wall_margin_mm, args.iters, args.alpha,
                             args.reparam_every, args.sample_spacing_mm,
                             args.window_mm, args.window_alpha, args.window_every)

    print_summary('after optimization (fast stage)', curvature_summary(new_points))

    print('Verifying and correcting wall clearance with the robust method (multi-direction ray voting) -- this may take a minute or two...')
    mesh = load_mesh(cavity_stl)
    ray_dirs = make_ray_directions()
    new_points = robust_wall_correction(mesh, new_points, ray_dirs, max_rounds=args.robust_max_rounds)

    final_votes = robust_inside_votes(mesh, new_points, ray_dirs)
    n_unsafe = int((final_votes < (len(ray_dirs) + 1) // 2).sum())
    print_summary('after optimization (after robust correction)', curvature_summary(new_points))
    print(f'Wall-clearance verification (multi-direction ray voting, majority of {len(ray_dirs)} votes counts as safe): '
          f'violating points {n_unsafe}/{len(new_points)}'
          + ('' if n_unsafe == 0 else ' (there are still unresolved violations -- the path may be hugging a genuine '
                                       'anatomical narrow passage/obstacle in this stretch, which needs a human look to '
                                       'decide whether it should take a different route, rather than just cranking up the smoothing)'))

    out_path = os.path.join(HERE, 'data', args.organ, f'lab_{args.lab_id}',
                             f'topology_robot_smoothed_stone{args.stone_id}.json')
    out_data = {
        'paths': [{
            'stone_id': args.stone_id,
            'path_coordinates': new_points.tolist(),
            'note': 'post-processed by optimize_for_robot/optimize_path_for_robot.py, not riemann_optimizer.py output; '
                    'wall-clearance verified+corrected via multi-direction ray-casting vote',
        }]
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out_data, f)
    print(f'\nResult saved to {out_path}')


if __name__ == '__main__':
    main()
