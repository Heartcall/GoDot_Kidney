"""Pick target points on the shared cavity's skeleton (leaf tips / branch
points) to place simulated stones for a new lab experiment, then generate
the STL files run_lab.py expects.

Interactive point-picking (drag to click a 3D point) turned out unreliable
under this machine's WSLg/Xwayland setup (modifier-click events don't
register), so this renders a labeled scene you can pick from by typing the
labels, instead of clicking directly. That labeled scene is an interactive
Plotly HTML page (rotate/zoom/pan in a normal browser, sidesteps the native
3D window issue entirely) rather than a static picture -- a fixed 3-view PNG
made labels illegible wherever the skeleton got dense (see conversation).

Usage:
    # 1. generate/refresh the labeled scene (only needed once, or after
    #    the shared cavity model itself changes)
    python pick_stones.py --render-labels
    python pick_stones.py --render-labels --organ organ_2_kidney

    # 2. open cavity_labeled.html (or cavity_labeled_<organ>.html) in a
    #    browser, rotate/zoom to find labels, then place stones for a new lab:
    python pick_stones.py --lab-id 2 --labels L3,L7,B2
    python pick_stones.py --organ organ_2_kidney --lab-id 1 --labels L3,L7,B2

    # 3. (optional) also run the pipeline right after
    python pick_stones.py --lab-id 2 --labels L3,L7,B2 --run
"""
import argparse
import os
import subprocess
import sys

import numpy as np
import networkx as nx
import trimesh

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'pipeline'))

HERE = os.path.dirname(__file__)
STONE_RADIUS_MM = 3.0


def cavity_stl_path(organ):
    return os.path.join(HERE, 'data', organ, 'model', 'cavity.stl')


def labeled_html_path(organ):
    # organ_1_kidney keeps the original bare filename (no suffix) so existing
    # workflows/scripts pointing at cavity_labeled.* don't break; every
    # other organ gets its own suffixed file so they don't clobber each other.
    suffix = '' if organ == 'organ_1_kidney' else f'_{organ}'
    return os.path.join(HERE, f'cavity_labeled{suffix}.html')


def extract_skeleton_graph(organ):
    from kidney_skeleton_extractor import extract_skeleton_from_stl
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        points, edges = extract_skeleton_from_stl(
            stl_path=cavity_stl_path(organ), voxel_size=1.0, output_dir=tmp,
            visualize=False, interactive=False)

    G = nx.Graph()
    for i, p in enumerate(points):
        G.add_node(i, pos=p)
    for e in edges:
        a, b = int(e[0]), int(e[1])
        G.add_edge(a, b, length=np.linalg.norm(points[a] - points[b]))
    comps = sorted(nx.connected_components(G), key=len, reverse=True)
    return G.subgraph(comps[0]).copy()


def get_labeled_points(G):
    pos = nx.get_node_attributes(G, 'pos')
    degrees = dict(G.degree())
    leaves = sorted([n for n, d in degrees.items() if d == 1])
    branches = sorted([n for n, d in degrees.items() if d >= 3])
    labeled = {}
    for i, n in enumerate(leaves):
        labeled[f'L{i}'] = np.array(pos[n])
    for i, n in enumerate(branches):
        labeled[f'B{i}'] = np.array(pos[n])
    return labeled


def render_labels(organ):
    import plotly.graph_objects as go

    G = extract_skeleton_graph(organ)
    labeled = get_labeled_points(G)
    pos = nx.get_node_attributes(G, 'pos')
    cavity = trimesh.load(cavity_stl_path(organ), process=False, force='mesh')

    # Cavity surface has tens of thousands of vertices; subsample the point
    # cloud so the page stays snappy to rotate/zoom in a browser (same
    # approach as run_lab.py's save_visualization).
    cv = cavity.vertices
    if len(cv) > 8000:
        idx = np.random.default_rng(0).choice(len(cv), 8000, replace=False)
        cv = cv[idx]

    # One Scatter3d trace for every skeleton edge, segments separated by
    # None so it's a single trace instead of one per edge (hundreds of
    # separate traces gets sluggish in the browser).
    edge_x, edge_y, edge_z = [], [], []
    for a, b in G.edges():
        pa, pb = pos[a], pos[b]
        edge_x += [pa[0], pb[0], None]
        edge_y += [pa[1], pb[1], None]
        edge_z += [pa[2], pb[2], None]

    leaf_labels = sorted([l for l in labeled if l.startswith('L')], key=lambda s: int(s[1:]))
    branch_labels = sorted([l for l in labeled if l.startswith('B')], key=lambda s: int(s[1:]))

    def label_trace(labels, color, name):
        pts = np.array([labeled[l] for l in labels])
        return go.Scatter3d(
            x=pts[:, 0], y=pts[:, 1], z=pts[:, 2], mode='markers+text',
            marker=dict(size=4, color=color),
            text=labels, textposition='top center', textfont=dict(size=10, color=color),
            name=name,
        )

    fig = go.Figure(data=[
        go.Scatter3d(x=cv[:, 0], y=cv[:, 1], z=cv[:, 2], mode='markers',
                      marker=dict(size=1.5, color='lightgray', opacity=0.25),
                      name='cavity', hoverinfo='skip'),
        go.Scatter3d(x=edge_x, y=edge_y, z=edge_z, mode='lines',
                      line=dict(color='steelblue', width=3),
                      name='skeleton', hoverinfo='skip'),
        label_trace(leaf_labels, 'green', 'leaves (L)'),
        label_trace(branch_labels, 'red', 'branches (B)'),
    ])
    fig.update_layout(
        scene=dict(aspectmode='data', xaxis_title='x (mm)', yaxis_title='y (mm)', zaxis_title='z (mm)'),
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(itemsizing='constant'),
        title=f'{organ}: cavity skeleton labels (rotate/zoom to disambiguate crowded areas)',
    )

    out_html = labeled_html_path(organ)
    fig.write_html(out_html, include_plotlyjs=True)
    print('已保存标签图:', out_html)
    print('绿色=端点(L0..Ln)  红色=分叉点(B0..Bn)  蓝色线=骨架')
    print('可选标签:', ', '.join(sorted(labeled.keys(), key=lambda s: (s[0], int(s[1:])))))


def place_stones(organ, lab_id, labels):
    G = extract_skeleton_graph(organ)
    labeled = get_labeled_points(G)

    stone_dir = os.path.join(HERE, 'data', organ, f'lab_{lab_id}')
    os.makedirs(stone_dir, exist_ok=True)

    for label in labels:
        if label not in labeled:
            print('警告: 标签 "%s" 不存在，跳过' % label)
            continue
        pos_mm_native = labeled[label]

        native_stl = os.path.join(stone_dir, f'{label}.stl')

        sphere_native = trimesh.creation.icosphere(subdivisions=2, radius=STONE_RADIUS_MM)
        sphere_native.apply_translation(pos_mm_native)
        sphere_native.export(native_stl)

        print('结石 %s: 原生坐标=%s' % (label, pos_mm_native.round(1)))

    print('已生成 %d 颗结石到 %s' % (len(labels), stone_dir))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--organ', default='organ_1_kidney', help='data/下的器官目录名，默认organ_1_kidney')
    ap.add_argument('--render-labels', action='store_true', help='生成/刷新标签图 cavity_labeled.png')
    ap.add_argument('--lab-id', help='要放结石的实验编号')
    ap.add_argument('--labels', help='逗号分隔的标签列表，如 L3,L7,B2')
    ap.add_argument('--run', action='store_true', help='生成结石后立即跑 run_lab.py (native)')
    ap.add_argument('--interior-margin', type=float, default=0.5)
    args = ap.parse_args()

    if args.render_labels:
        render_labels(args.organ)
        return

    if not args.lab_id or not args.labels:
        print('可选标签: ', end='')
        render_labels(args.organ)
        raw = input('输入这次实验要放的结石标签(逗号分隔, 如 L3,L7,B2): ')
        labels = [t.strip() for t in raw.split(',') if t.strip()]
        lab_id = args.lab_id or input('实验编号(lab-id): ').strip()
    else:
        labels = [t.strip() for t in args.labels.split(',') if t.strip()]
        lab_id = args.lab_id

    place_stones(args.organ, lab_id, labels)

    if args.run:
        subprocess.run([sys.executable, os.path.join(HERE, 'run_lab.py'),
                         '--organ', args.organ, '--lab-id', lab_id,
                         '--interior-margin', str(args.interior_margin)], check=True)


if __name__ == '__main__':
    main()
