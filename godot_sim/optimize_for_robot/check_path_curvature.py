"""Diagnostic (read-only, doesn't touch the path): checks whether the SDF-
optimized path (PathPlanning's topology_optimized.json) is actually followable
by the real continuum robot, which the pure-geometry optimizer knows nothing
about.

Two separate checks, both against limits the user stated in-session (not a
manufacturer datasheet):
  - active tip (65mm constant-curvature bending segment): rated minimum bend
    radius 10mm. Checked point-by-point with the strict 3-point circumradius
    (Menger curvature) on the resampled path -- deliberately the more
    sensitive method here, since this is the segment actually being steered
    and it needs to react to sharp local features, not just the average
    turn over its own length.
  - passive shaft (rest of the scope, same material, bends passively against
    duct/tissue): rated minimum radius 35mm, checked with a 30mm sliding
    window (window, not point-wise, because a 30mm+ length of shaft only
    cares about its net turn over that span, not sub-mm zigzag in the
    resampled polyline -- a 3-point check here previously produced nonsense
    ~1mm "kinks" that had nothing to do with real bending). This check
    excludes the final `--passive-exclude-tip-mm` (default 65mm) of the
    path nearest the stone -- at full insertion that stretch is occupied by
    the active segment itself, not dragged through by the passive shaft.

Reads PathPlanning's data (read-only, that repo is not touched) -- assumes
this folder sits next to PathPlanning inside godot_sim/.

Usage:
    python check_path_curvature.py --lab-id 1 --stone-id 1
    python check_path_curvature.py --lab-id 1 --stone-id 1 --active-min-radius-mm 10 --passive-min-radius-mm 35 --passive-exclude-tip-mm 65
"""
import argparse
import json
import os

import numpy as np

HERE = os.path.dirname(__file__)
PATHPLANNING_DIR = os.path.join(HERE, '..', 'PathPlanning')


def resample_by_arclength(points: np.ndarray, ds: float) -> tuple[np.ndarray, np.ndarray]:
    seg = np.linalg.norm(np.diff(points, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]
    # np.arange(0, total, ds) doesn't reliably land exactly on `total` when it
    # isn't an integer multiple of ds -- explicitly append the true endpoint
    # instead of letting the last resampled point silently fall short of it.
    targets = np.arange(0.0, total, ds)
    if len(targets) == 0 or targets[-1] < total:
        targets = np.concatenate([targets, [total]])
    out = np.empty((len(targets), 3))
    for i, s in enumerate(targets):
        j = min(np.searchsorted(cum, s, side='right') - 1, len(points) - 2)
        j = max(j, 0)
        seg_len = cum[j + 1] - cum[j]
        t = 0.0 if seg_len < 1e-9 else (s - cum[j]) / seg_len
        out[i] = points[j] * (1 - t) + points[j + 1] * t
    out[-1] = points[-1]  # guard against any residual floating-point drift
    return out, targets


def tangent_at(points: np.ndarray, cum: np.ndarray, s: float, eps: float) -> np.ndarray:
    total = cum[-1]
    s0, s1 = max(0.0, s - eps), min(total, s + eps)
    p0 = _interp(points, cum, s0)
    p1 = _interp(points, cum, s1)
    d = p1 - p0
    n = np.linalg.norm(d)
    return d / n if n > 1e-9 else np.array([1.0, 0.0, 0.0])


def _interp(points: np.ndarray, cum: np.ndarray, s: float) -> np.ndarray:
    j = min(np.searchsorted(cum, s, side='right') - 1, len(points) - 2)
    j = max(j, 0)
    seg_len = cum[j + 1] - cum[j]
    t = 0.0 if seg_len < 1e-9 else (s - cum[j]) / seg_len
    return points[j] * (1 - t) + points[j + 1] * t


def three_point_radius(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """Circumradius of the circle through 3 points (Menger curvature) --
    strict, local, sensitive to sharp single-point features."""
    ab, bc, ca = np.linalg.norm(b - a), np.linalg.norm(c - b), np.linalg.norm(a - c)
    area2 = np.linalg.norm(np.cross(b - a, c - a))
    if area2 < 1e-9:
        return np.inf
    return (ab * bc * ca) / (2 * area2)


def point_deviation(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """Perpendicular distance (mm) of b from the a-c chord -- no matter how
    small the 3-point radius comes out, if this deviation itself is only a
    few tenths of a mm, it's physically just noise-level jitter, not a real
    sharp bend."""
    ac = c - a
    ac_norm = np.linalg.norm(ac)
    if ac_norm < 1e-9:
        return float(np.linalg.norm(b - a))
    ac_n = ac / ac_norm
    proj = a + np.dot(b - a, ac_n) * ac_n
    return float(np.linalg.norm(b - proj))


def active_violation_mask(points: np.ndarray, min_radius_mm: float, min_deviation_mm: float = 0.2) -> np.ndarray:
    """Active-segment violation test: only counts when radius < min_radius_mm
    **and** the actual physical deviation >= min_deviation_mm. A point that
    only satisfies the small-radius condition, with a deviation of just a few
    tenths of a mm, is numerical jitter left over from resampling/smoothing,
    not a real curvature problem, and isn't counted. Returns a per-point
    violation mask."""
    n = len(points)
    bad = np.zeros(n, dtype=bool)
    for i in range(1, n - 1):
        r = three_point_radius(points[i - 1], points[i], points[i + 1])
        if r < min_radius_mm and point_deviation(points[i - 1], points[i], points[i + 1]) >= min_deviation_mm:
            bad[i] = True
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--organ', default='organ_1_kidney', help='organ directory name under data/, default organ_1_kidney')
    ap.add_argument('--lab-id', required=True)
    ap.add_argument('--stone-id', required=True, type=int)
    ap.add_argument('--active-min-radius-mm', type=float, default=10.0,
                     help='rated minimum bend radius of the active bending segment (mm)')
    ap.add_argument('--passive-window-mm', type=float, default=30.0,
                     help='window length for the passive shaft local-bend check (mm) -- too small and it gets thrown off by the polyline\'s own zigzag noise')
    ap.add_argument('--passive-min-radius-mm', type=float, default=35.0,
                     help='rated minimum safe bend radius of the passive shaft (mm)')
    ap.add_argument('--passive-exclude-tip-mm', type=float, default=65.0,
                     help='length excluded from the passive check at the path\'s end (stone side) -- at full insertion that stretch is occupied by the active segment itself, not something the passive shaft has to bend through')
    ap.add_argument('--sample-spacing-mm', type=float, default=1.0, help='resampling spacing along the path (mm)')
    ap.add_argument('--min-active-deviation-mm', type=float, default=0.2,
                     help='minimum actual physical deviation an active-segment violation point must reach to count, filtering out numerical-jitter-level false positives')
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
    points, s_vals = resample_by_arclength(raw_points, args.sample_spacing_mm)
    seg = np.linalg.norm(np.diff(points, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total_len = cum[-1]
    print(f'Total path length: {total_len:.1f}mm, {len(points)} points after resampling (spacing {args.sample_spacing_mm}mm)')

    # ---- Active bending segment: strict point-by-point 3-point circle method, covers the whole path ----
    # Points with a small radius but an actual physical deviation below
    # min_active_deviation_mm are numerical-jitter-level false positives --
    # filter them out (treat their radius as inf, so they don't count toward
    # report()'s violation stats below).
    active_radii = np.full(len(points), np.inf)
    for i in range(1, len(points) - 1):
        r = three_point_radius(points[i - 1], points[i], points[i + 1])
        if r < args.active_min_radius_mm and \
                point_deviation(points[i - 1], points[i], points[i + 1]) < args.min_active_deviation_mm:
            r = np.inf
        active_radii[i] = r
    report('Active bending segment (point-by-point 3-point method)', cum, active_radii, args.active_min_radius_mm)

    # ---- Passive shaft: 30mm sliding window, excluding the final
    # passive-exclude-tip-mm (at full insertion that stretch is already
    # occupied by the active segment itself, so the passive shaft doesn't
    # need to bend through it) ----
    passive_cutoff = max(0.0, total_len - args.passive_exclude_tip_mm)
    keep = cum <= passive_cutoff
    trunc_points, trunc_cum = points[keep], cum[keep]
    trunc_total = trunc_cum[-1] if len(trunc_cum) else 0.0
    print(f'\n(Passive-segment check range: arc length 0~{trunc_total:.1f}mm, excluding final {total_len - trunc_total:.1f}mm)')
    passive_s, passive_radii = windowed_radii(trunc_points, trunc_cum, trunc_total,
                                               args.passive_window_mm, args.sample_spacing_mm)
    report(f'Passive shaft ({args.passive_window_mm:g}mm window)', passive_s, passive_radii, args.passive_min_radius_mm)


def windowed_radii(points: np.ndarray, cum: np.ndarray, total_len: float,
                    window_mm: float, sample_spacing_mm: float) -> tuple[np.ndarray, np.ndarray]:
    """Slides a window_mm-long window and computes the equivalent curvature
    radius from the angle between the tangents at its two ends
    (= window_length / turn_angle); returns each window's midpoint arc-length
    position + the corresponding radius."""
    tangent_eps = min(sample_spacing_mm * 2, window_mm / 4)
    radii, mids = [], []
    s = 0.0
    while s + window_mm <= total_len:
        t0 = tangent_at(points, cum, s, tangent_eps)
        t1 = tangent_at(points, cum, s + window_mm, tangent_eps)
        angle = np.arccos(np.clip(np.dot(t0, t1), -1.0, 1.0))
        radii.append(window_mm / angle if angle > 1e-6 else np.inf)
        mids.append(s + window_mm / 2)
        s += sample_spacing_mm
    return np.array(mids), np.array(radii)


def report(label: str, s_vals: np.ndarray, radii: np.ndarray, min_radius_mm: float) -> None:
    print()
    print(f'=== {label} check (limit radius {min_radius_mm:.1f}mm) ===')
    violations = radii < min_radius_mm
    if not violations.any():
        print('Passes throughout.')
        return
    n_bad = int(violations.sum())
    worst_idx = int(np.argmin(radii))
    print(f'Violating windows: {n_bad}/{len(radii)} ({100 * n_bad / len(radii):.1f}%)')
    print(f'Worst point: near arc length {s_vals[worst_idx]:.1f}mm, needs radius {radii[worst_idx]:.1f}mm'
          f' (exceeds limit by {min_radius_mm - radii[worst_idx]:.1f}mm)')
    bad_idx = np.where(violations)[0]
    groups = np.split(bad_idx, np.where(np.diff(bad_idx) > 1)[0] + 1)
    print(f'{len(groups)} contiguous violating region(s):')
    for g in groups:
        print(f'  arc length {s_vals[g[0]]:.1f}mm ~ {s_vals[g[-1]]:.1f}mm (min radius {radii[g].min():.1f}mm)')


if __name__ == '__main__':
    main()
