"""Run the full 4-stage PathPlanning pipeline for one lab experiment.

Auto-discovers every stone STL under data/<organ>/lab_<id>/ (files
named 1.stl, 2.stl, ...), merges them into one combined stone mesh (the
pipeline's own KidneyStoneExtractor already splits a multi-body STL into
separate stones via connected components, so one merged file = N stones),
and runs skeleton extraction -> topology -> endoscope simulation -> SDF
optimization against the shared cavity model. Results and the final
cavity+stones+path screenshot are saved into the same lab_<id>/ folder,
alongside the stone STLs.

Usage:
    python run_lab.py --lab-id 1                        # organ_1_kidney (default)
    python run_lab.py --lab-id 1 --organ organ_2_kidney
"""
import argparse
import os
import subprocess
import sys

import numpy as np
import trimesh

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'pipeline'))

HERE = os.path.dirname(__file__)

# The cavity is shared across all labs of a given organ; its true entry point
# (urethra) is a fixed anatomical landmark. For organ_1_kidney this was
# established once by hand (kidney_path_topology.py's own "min-Y skeleton
# point" auto-detection is wrong for that particular mesh - see README).
# organ_2_kidney/organ_3_kidney were confirmed by visual inspection of the
# skeleton (leaf node at the end of an isolated stem reaching away from the
# branching calyx cluster) using min-Z instead of min-Y -- see
# entry_check_minz.png in each organ's data dir. Other organs don't have a
# manually-verified entry point yet -- ENTRY_POINTS_MM falls back to the
# min-Y auto-detection for anything not listed here, but that fallback is
# UNVERIFIED for a new mesh (and min-Z looked like the better heuristic for
# the two organs checked so far, not min-Y); check skeleton_results'
# visualization and confirm the picked point is really the ureteral entry
# before trusting downstream results, then add the confirmed coordinate here.
ENTRY_POINTS_MM = {
    'organ_1_kidney': np.array([-11.0, 20.0, -133.0]),
    'organ_2_kidney': np.array([-10.0, 22.0, -139.0]),
    'organ_3_kidney': np.array([-101.0, 25.0, -150.0]),
}


def discover_stone_files(data_dir, lab_id):
    """Stone files are named by skeleton label (pick_stones.py's L3.stl,
    B2.stl, ...). Internal merge artifacts (_merged_*.stl) are skipped.
    """
    stone_dir = os.path.join(data_dir, f'lab_{lab_id}')
    if not os.path.isdir(stone_dir):
        raise SystemExit(f'未找到 {stone_dir}，先用 pick_stones.py 生成结石STL (如 L3.stl)')

    files = []
    for fn in sorted(os.listdir(stone_dir)):
        if not fn.endswith('.stl') or fn.startswith('_'):
            continue
        files.append((fn[:-4], os.path.join(stone_dir, fn)))
    files.sort(key=lambda x: x[0])
    if not files:
        raise SystemExit(f'{stone_dir} 下没有找到结石文件')
    return stone_dir, [f for _, f in files]


def merge_stones(stone_paths, out_path):
    meshes = [trimesh.load(p, process=False, force='mesh') for p in stone_paths]
    merged = trimesh.util.concatenate(meshes)
    merged.export(out_path)
    return out_path


def run(cmd):
    print('$', ' '.join(cmd))
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--organ', default='organ_1_kidney', help='data/下的器官目录名，默认organ_1_kidney')
    ap.add_argument('--lab-id', required=True, help='实验编号, 如 1')
    ap.add_argument('--interior-margin', type=float, default=0.5)
    args = ap.parse_args()

    data_dir = os.path.join(HERE, 'data', args.organ)

    stone_dir, stone_paths = discover_stone_files(data_dir, args.lab_id)
    print('发现 %d 颗结石: %s' % (len(stone_paths), [os.path.basename(p) for p in stone_paths]))

    kidney_stl = os.path.join(data_dir, 'model', 'cavity.stl')
    merged_stone_stl = os.path.join(stone_dir, '_merged_native.stl')
    merge_stones(stone_paths, merged_stone_stl)

    case_id = f'lab_{args.lab_id}/result'
    case_dir = os.path.join(data_dir, f'lab_{args.lab_id}', 'result')
    os.makedirs(case_dir, exist_ok=True)

    # ---- stage 1: skeleton ----
    from kidney_skeleton_extractor import extract_skeleton_from_stl
    skeleton_dir = os.path.join(case_dir, 'skeleton_results')
    skeleton_points, skeleton_edges = extract_skeleton_from_stl(
        stl_path=kidney_stl, voxel_size=1.0, output_dir=skeleton_dir,
        visualize=False, interactive=False)
    print('骨架: %d点 %d边' % (len(skeleton_points), len(skeleton_edges)))

    # ---- stage 2: topology (bypassing the wrong min-Y urethra auto-detection) ----
    from kidney_path_topology import KidneyPathTopology, load_skeleton_data
    from kidney_stone_extractor import KidneyStoneExtractor

    skeleton_file = os.path.join(skeleton_dir, 'kidney_skeleton_raw.npz')
    skeleton_points, skeleton_edges = load_skeleton_data(skeleton_file)

    if args.organ in ENTRY_POINTS_MM:
        dists = np.linalg.norm(skeleton_points - ENTRY_POINTS_MM[args.organ], axis=1)
        urethra_point = skeleton_points[np.argmin(dists)]
        print('入口点(距目标%.2fmm): %s' % (dists.min(), urethra_point))
    else:
        # No manually-verified entry point for this organ yet -- fall back to
        # the min-Y skeleton point (known wrong for organ_1_kidney's mesh,
        # unverified for this one). Check the skeleton visualization and
        # confirm this is really the ureteral entry before trusting the
        # resulting path; once confirmed, add the coordinate to
        # ENTRY_POINTS_MM above so future runs skip this guess.
        urethra_point = skeleton_points[np.argmin(skeleton_points[:, 1])]
        print(f'警告: {args.organ} 没有手动标定过的入口点，回退到min-Y自动检测'
              f'(对organ_1_kidney已知是错的，这个mesh尚未验证): {urethra_point}')
        print('        请检查骨架可视化结果，确认这个点确实是尿道入口，'
              '确认后把坐标加进ENTRY_POINTS_MM')

    extractor = KidneyStoneExtractor(merged_stone_stl, safe_margin=2.0, voxel_size=0.5, min_voxel_ratio=0.01)
    stone_points = np.array(extractor.get_stone_centers())
    print('检测到 %d 颗结石中心点' % len(stone_points))

    topology = KidneyPathTopology(skeleton_points=skeleton_points, skeleton_edges=skeleton_edges,
                                   urethra_point=urethra_point, stone_points=stone_points)
    for p in topology.get_all_paths():
        print('到结石%s: %.1fmm, %d个节点' % (p['stone_id'], p['path_length'], p['num_nodes']))

    topology_dir = os.path.join(case_dir, 'topology_results')
    os.makedirs(topology_dir, exist_ok=True)
    topology_json = os.path.join(topology_dir, 'topology_result.json')
    topology.save_topology_data(topology_json)

    # ---- stage 3: endoscope retreat simulation (subprocess - unmodified CLI is fine here;
    # only pass explicit --topology-file/--output-dir since its own default still assumes
    # the old result/<case-id>/... layout, not our new data/organ_1_kidney/lab_<id>/ one) ----
    endoscope_sim_dir = os.path.join(case_dir, 'endoscope_simulation_v2_tree')
    run([sys.executable, os.path.join('src', 'pipeline', 'kidney_endoscope_simulator.py'),
         '--case-id', case_id, '--kidney-stl', kidney_stl, '--stone-stl', merged_stone_stl,
         '--topology-file', topology_json, '--output-dir', endoscope_sim_dir,
         '--no-interactive'])

    # ---- stage 4: SDF path smoothing (same story: explicit --input-json/--output-json) ----
    run([sys.executable, os.path.join('src', 'pipeline', 'riemann_optimizer.py'),
         '--case-id', case_id, '--kidney-stl', kidney_stl, '--stone-stl', merged_stone_stl,
         '--input-json', os.path.join(endoscope_sim_dir, 'topology_with_tree_structure.json'),
         '--output-json', os.path.join(case_dir, 'topology_optimized', 'topology_optimized.json'),
         '--interior-margin', str(args.interior_margin), '--no-visualize'])

    # ---- final cavity + stones + path screenshot, saved into lab_<id>/ ----
    save_visualization(kidney_stl, merged_stone_stl, case_dir, stone_dir)


def save_visualization(kidney_stl, stone_stl, case_dir, stone_dir):
    import json
    import plotly.graph_objects as go

    kidney = trimesh.load(kidney_stl, process=False, force='mesh')
    stones = trimesh.load(stone_stl, process=False, force='mesh')

    opt_path = os.path.join(case_dir, 'topology_optimized', 'topology_optimized.json')
    with open(opt_path, encoding='utf-8') as f:
        data = json.load(f)

    # Cavity surface has tens of thousands of vertices; subsample the point
    # cloud so the page stays snappy to rotate/zoom in a browser.
    kv = kidney.vertices
    if len(kv) > 8000:
        idx = np.random.default_rng(0).choice(len(kv), 8000, replace=False)
        kv = kv[idx]

    traces = [
        go.Scatter3d(
            x=kv[:, 0], y=kv[:, 1], z=kv[:, 2], mode='markers',
            marker=dict(size=1.5, color='lightgray', opacity=0.35),
            name='cavity', hoverinfo='skip',
        ),
        go.Scatter3d(
            x=stones.vertices[:, 0], y=stones.vertices[:, 1], z=stones.vertices[:, 2], mode='markers',
            marker=dict(size=3, color='gold'),
            name='stones', hoverinfo='skip',
        ),
    ]
    for path_info in data['paths']:
        pts = np.array(path_info['path_coordinates']) if 'path_coordinates' in path_info else None
        if pts is None:
            continue
        traces.append(go.Scatter3d(
            x=pts[:, 0], y=pts[:, 1], z=pts[:, 2], mode='lines',
            line=dict(color='blue', width=5),
            name=f"path -> stone {path_info.get('stone_id', '?')}",
        ))

    fig = go.Figure(data=traces)
    fig.update_layout(
        scene=dict(aspectmode='data', xaxis_title='x (mm)', yaxis_title='y (mm)', zaxis_title='z (mm)'),
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(itemsizing='constant'),
    )

    out_path = os.path.join(stone_dir, 'visualization.html')
    fig.write_html(out_path, include_plotlyjs=True)
    print('可视化已保存:', out_path)


if __name__ == '__main__':
    main()
