import numpy as np
import trimesh
from scipy import ndimage
from scipy.interpolate import interp1d, RegularGridInterpolator
from scipy.optimize import minimize
import logging
import json
import os
import vedo


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def load_mesh(stl_path):
    """加载 STL 网格，失败时抛出 FileNotFoundError"""
    if not os.path.exists(stl_path):
        raise FileNotFoundError(f"网格文件不存在: {stl_path}")
    mesh = trimesh.load(stl_path)
    logging.info(f"网格加载成功，顶点数: {len(mesh.vertices)}，面数: {len(mesh.faces)}")
    return mesh


def create_sdf_grid(mesh, resolution=1.0, padding=5.0):
    """体素化 + 形态学填充，返回有符号距离场和网格参数"""
    bounds = mesh.bounds
    min_b = bounds[0] - padding
    max_b = bounds[1] + padding
    nx = int(np.ceil((max_b[0] - min_b[0]) / resolution)) + 1
    ny = int(np.ceil((max_b[1] - min_b[1]) / resolution)) + 1
    nz = int(np.ceil((max_b[2] - min_b[2]) / resolution)) + 1
    origin = min_b
    step = resolution
    logging.info(f"体素网格尺寸: {nx} x {ny} x {nz}")

    vox = mesh.voxelized(pitch=resolution)
    surf_matrix = vox.matrix
    vox_origin = vox.bounds[0]

    offset = ((vox_origin - origin) / resolution).round().astype(int)
    binary_surface = np.zeros((nx, ny, nz), dtype=bool)
    i0, j0, k0 = offset
    i1 = i0 + surf_matrix.shape[0]
    j1 = j0 + surf_matrix.shape[1]
    k1 = k0 + surf_matrix.shape[2]
    i1 = min(i1, nx)
    j1 = min(j1, ny)
    k1 = min(k1, nz)
    binary_surface[i0:i1, j0:j1, k0:k1] = surf_matrix[:i1 - i0, :j1 - j0, :k1 - k0]

    interior = ndimage.binary_fill_holes(binary_surface)
    logging.info(f"填充后内部体素数: {np.sum(interior)} / {interior.size}")

    dt_inside = ndimage.distance_transform_edt(~interior) * step
    dt_outside = ndimage.distance_transform_edt(interior) * step
    sdf = np.where(interior, -dt_outside, dt_inside)
    return sdf, origin, step


def project_to_interior(points, sdf, origin, step):
    """将点投影到内部（SDF<0）"""
    def world_to_voxel(p):
        return ((p - origin) / step).astype(int)

    projected = []
    for p in points:
        idx = world_to_voxel(p)
        if (0 <= idx[0] < sdf.shape[0] and 0 <= idx[1] < sdf.shape[1] and 0 <= idx[2] < sdf.shape[2]
                and sdf[tuple(idx)] < 0):
            projected.append(p)
        else:
            best_dist = np.inf
            best_pos = p
            for di in [-1, 0, 1]:
                for dj in [-1, 0, 1]:
                    for dk in [-1, 0, 1]:
                        ni, nj, nk = idx[0] + di, idx[1] + dj, idx[2] + dk
                        if 0 <= ni < sdf.shape[0] and 0 <= nj < sdf.shape[1] and 0 <= nk < sdf.shape[2]:
                            if sdf[ni, nj, nk] < 0:
                                pos_candidate = origin + (np.array([ni, nj, nk]) + 0.5) * step
                                dist = np.linalg.norm(pos_candidate - p)
                                if dist < best_dist:
                                    best_dist = dist
                                    best_pos = pos_candidate
            projected.append(best_pos)
    return np.array(projected)


def compute_riemann_cost(points, sdf_interp, alpha=0.5, beta=100.0):
    segs = points[1:] - points[:-1]
    mids = 0.5 * (points[1:] + points[:-1])
    sdf_vals = sdf_interp(mids)
    weights = 1.0 + beta * np.exp(alpha * sdf_vals)
    seg_lens_sq = np.sum(segs ** 2, axis=1)
    cost = np.sum(np.sqrt(weights * seg_lens_sq))
    return cost


def compute_smooth_cost(points):
    """二阶差分平方和，惩罚曲率"""
    if len(points) < 3:
        return 0.0
    second_diff = points[2:] - 2 * points[1:-1] + points[:-2]
    return np.mean(np.sum(second_diff ** 2, axis=1))


def optimize_segment(src_pos, tgt_pos, sdf_interp, step_mm=0.5, n_ctrl=5,
                     alpha=0.3, beta=5000.0, smooth_weight=0.3, riemann_weight=80.0,
                     max_iter=200, verbose=False, original_segment_points=None,
                     min_seg_len=2.0, endpoint_margin=0.1,
                     sdf_grid=None, origin=None, step=None, interior_margin=0.5):
    """
    优化一段路径，使用 trust-constr 优化器，约束路径上所有采样点位于内部 (SDF <= -interior_margin)。
    """
    # 如果没有原始段点，直接返回直线并投影
    if original_segment_points is None or len(original_segment_points) < 2:
        line = np.linspace(src_pos, tgt_pos, int(np.linalg.norm(tgt_pos - src_pos) / step_mm) + 2)
        if sdf_grid is not None:
            line = project_to_interior(line, sdf_grid, origin, step)
        return line

    # 将原始段点投影到内部，确保初始点都在腔道内
    if sdf_grid is not None:
        seg_points = project_to_interior(np.array(original_segment_points), sdf_grid, origin, step)
    else:
        seg_points = np.array(original_segment_points)

    total_len = np.sum(np.linalg.norm(seg_points[1:] - seg_points[:-1], axis=1))
    if total_len < min_seg_len:
        line = np.linspace(src_pos, tgt_pos, int(total_len / step_mm) + 2)
        if sdf_grid is not None:
            line = project_to_interior(line, sdf_grid, origin, step)
        return line

    # 动态调整控制点数量：长段适当增加
    if total_len > 30.0 and n_ctrl < 7:
        n_ctrl = 7
    elif total_len > 50.0 and n_ctrl < 9:
        n_ctrl = 9
    elif total_len > 80.0 and n_ctrl < 12:
        n_ctrl = 12

    # 采样内部控制点（避开端点）
    cumlen = np.insert(np.cumsum(np.linalg.norm(np.diff(seg_points, axis=0), axis=1)), 0, 0)
    margin = endpoint_margin * total_len
    start_margin = margin
    end_margin = total_len - margin

    ctrl_init = []
    for i in range(1, n_ctrl + 1):
        target_len = i * total_len / (n_ctrl + 1)
        if target_len < start_margin or target_len > end_margin:
            continue
        idx = np.searchsorted(cumlen, target_len) - 1
        idx = np.clip(idx, 0, len(seg_points) - 2)
        t = (target_len - cumlen[idx]) / (cumlen[idx + 1] - cumlen[idx] + 1e-10)
        pt = seg_points[idx] * (1 - t) + seg_points[idx + 1] * t
        ctrl_init.append(pt)

    if not ctrl_init:
        line = np.linspace(src_pos, tgt_pos, int(total_len / step_mm) + 2)
        if sdf_grid is not None:
            line = project_to_interior(line, sdf_grid, origin, step)
        return line
    ctrl_init = np.array(ctrl_init)

    # 目标函数
    def objective(ctrl_flat):
        ctrl = ctrl_flat.reshape(-1, 3)
        path = np.vstack([src_pos, ctrl, tgt_pos])
        riemann = riemann_weight * compute_riemann_cost(path, sdf_interp, alpha, beta)
        smooth = smooth_weight * compute_smooth_cost(path)
        return riemann + smooth

    # 约束函数：返回路径上所有采样点与表面距离的**最大值**，要求 <= 0（即所有点都在内部 margin 内）
    def constraint_func(ctrl_flat):
        ctrl = ctrl_flat.reshape(-1, 3)
        path = np.vstack([src_pos, ctrl, tgt_pos])
        seg_lens = np.linalg.norm(path[1:] - path[:-1], axis=1)
        cumlen_path = np.insert(np.cumsum(seg_lens), 0, 0)
        total_len_path = cumlen_path[-1]
        # 动态采样：每 0.5 mm 一个点，最少 50 个点
        num_samples = max(50, int(total_len_path / step_mm) + 1)
        sample_lens = np.linspace(0, total_len_path, num_samples)
        sample_points = []
        for s in sample_lens:
            idx = np.searchsorted(cumlen_path, s) - 1
            idx = np.clip(idx, 0, len(path) - 2)
            t = (s - cumlen_path[idx]) / (cumlen_path[idx + 1] - cumlen_path[idx] + 1e-10)
            pt = path[idx] * (1 - t) + path[idx + 1] * t
            sample_points.append(pt)
        sample_points = np.array(sample_points)
        sdf_vals = sdf_interp(sample_points)
        # 约束：所有点必须满足 sdf_vals <= -interior_margin
        # 等价于 max(sdf_vals + interior_margin) <= 0
        violation = np.max(sdf_vals + interior_margin)
        return violation   # 应 <= 0

    # 边界约束
    if sdf_grid is not None:
        bounds_min = origin
        bounds_max = origin + step * (np.array(sdf_grid.shape) - 1)
    else:
        bounds_min = np.minimum(src_pos, tgt_pos) - 50
        bounds_max = np.maximum(src_pos, tgt_pos) + 50

    flat_lb = []
    flat_ub = []
    for _ in range(len(ctrl_init)):
        flat_lb.extend([bounds_min[0], bounds_min[1], bounds_min[2]])
        flat_ub.extend([bounds_max[0], bounds_max[1], bounds_max[2]])

    from scipy.optimize import Bounds, NonlinearConstraint
    bounds = Bounds(flat_lb, flat_ub)

    nonlinear_constraint = NonlinearConstraint(constraint_func, -np.inf, 0)
    x0 = ctrl_init.flatten()
    res = minimize(objective, x0, method='trust-constr',
                   bounds=bounds, constraints=[nonlinear_constraint],
                   options={'maxiter': max_iter, 'verbose': verbose, 'gtol': 1e-6, 'xtol': 1e-6})

    if not res.success:
        logging.warning(f"优化未收敛: {res.message}")

    opt_ctrl = res.x.reshape(-1, 3)
    opt_path = np.vstack([src_pos, opt_ctrl, tgt_pos])

    # 重采样均匀间距
    total_len_opt = np.sum(np.linalg.norm(opt_path[1:] - opt_path[:-1], axis=1))
    num = max(2, int(total_len_opt / step_mm) + 1)
    if len(opt_path) > 1:
        distances = np.cumsum(np.linalg.norm(np.diff(opt_path, axis=0), axis=1))
        distances = np.insert(distances, 0, 0)
        interp_dist = np.linspace(0, total_len_opt, num)
        new_path = np.zeros((num, 3))
        for dim in range(3):
            f = interp1d(distances, opt_path[:, dim], kind='linear', fill_value='extrapolate')
            new_path[:, dim] = f(interp_dist)
        opt_path = new_path

    return opt_path


def update_topology_with_smooth_paths(topology_data, mesh, resolution=1.0, step_mm=0.5,
                                      alpha=0, beta=5000.0, smooth_weight=0.1, riemann_weight=20.0,
                                      n_ctrl=5, max_iter=100, min_seg_len=2.0, endpoint_margin=0.1,
                                      interior_margin=0.5):
    """
    主函数：基于控制点优化的分段平滑，控制点从原始路径采样。
    """
    # 构建 SDF 体素网格和插值器
    sdf_grid, origin, step = create_sdf_grid(mesh, resolution=resolution)
    x = np.linspace(origin[0], origin[0] + step * (sdf_grid.shape[0] - 1), sdf_grid.shape[0])
    y = np.linspace(origin[1], origin[1] + step * (sdf_grid.shape[1] - 1), sdf_grid.shape[1])
    z = np.linspace(origin[2], origin[2] + step * (sdf_grid.shape[2] - 1), sdf_grid.shape[2])
    sdf_interp = RegularGridInterpolator((x, y, z), sdf_grid, bounds_error=False, fill_value=np.max(sdf_grid))

    global_nodes = {node['node_id']: node for node in topology_data.get('nodes', [])}

    updated_paths = []
    for path_info in topology_data['paths']:
        stone_id = path_info.get('stone_id', '?')
        tree_nodes = path_info.get('tree_topology', {}).get('nodes', [])
        if not tree_nodes:
            logging.warning(f"结石 {stone_id} 缺少 tree_topology.nodes，跳过")
            updated_paths.append(path_info)
            continue

        # 辅助函数
        def get_node_id(node):
            return node.get('id', node.get('node_id'))

        def get_node_pos(node):
            return node.get('position', node.get('pos'))

        # 查找尿道口
        urethra_node = None
        for node in tree_nodes:
            if node.get('type') == 'urethra':
                urethra_node = node
                break
        if urethra_node is None and 'urethra_entry' in global_nodes:
            global_urethra = global_nodes['urethra_entry']
            urethra_node = global_urethra.copy()
            if 'id' not in urethra_node:
                urethra_node['id'] = urethra_node.get('node_id')
            if 'position' not in urethra_node and 'pos' in urethra_node:
                urethra_node['position'] = urethra_node['pos']
            tree_nodes.append(urethra_node)

        if urethra_node is None:
            logging.warning(f"结石 {stone_id} 未找到尿道口节点，跳过")
            updated_paths.append(path_info)
            continue

        # 查找最佳观察点
        opt_node = None
        for node in tree_nodes:
            if node.get('type') == 'optimal_viewpoint':
                opt_node = node
                break
        if opt_node is None:
            logging.warning(f"结石 {stone_id} 未找到最佳观察点节点，跳过")
            updated_paths.append(path_info)
            continue

        # 构建固定节点映射
        fixed_node_map = {}
        fixed_node_map[get_node_id(urethra_node)] = urethra_node
        for node in tree_nodes:
            if node.get('type') == 'branch_point':
                fixed_node_map[get_node_id(node)] = node
        fixed_node_map[get_node_id(opt_node)] = opt_node

        # 获取 path_nodes 序列
        path_nodes_seq = path_info.get('path_nodes', [])
        if not path_nodes_seq:
            logging.warning(f"结石 {stone_id} 缺少 path_nodes，跳过")
            updated_paths.append(path_info)
            continue

        coords = np.array(path_info['path_coordinates'])
        if len(coords) != len(path_nodes_seq):
            logging.warning(f"结石 {stone_id} path_coordinates 与 path_nodes 长度不匹配，跳过")
            updated_paths.append(path_info)
            continue

        # 建立路径节点 ID 到坐标的映射
        path_node_coords = {nid: coords[i] for i, nid in enumerate(path_nodes_seq)}

        # 收集固定节点顺序（通过坐标匹配）
        ordered_fixed = []
        for nid in path_nodes_seq:
            if nid in fixed_node_map:
                ordered_fixed.append((nid, fixed_node_map[nid]))
            else:
                pos = path_node_coords.get(nid)
                if pos is not None:
                    matched = None
                    for fid, fnode in fixed_node_map.items():
                        fpos = np.array(get_node_pos(fnode))
                        if np.linalg.norm(fpos - pos) < 1.0:
                            matched = (fid, fnode)
                            break
                    if matched:
                        ordered_fixed.append(matched)

        # 去重
        seen = set()
        unique_ordered = []
        for nid, node in ordered_fixed:
            if nid not in seen:
                seen.add(nid)
                unique_ordered.append((nid, node))
        ordered_fixed = unique_ordered

        # 确保尿道口在第一，最佳观察点在最后
        if ordered_fixed and ordered_fixed[0][0] != get_node_id(urethra_node):
            ordered_fixed.insert(0, (get_node_id(urethra_node), urethra_node))
        if ordered_fixed and ordered_fixed[-1][0] != get_node_id(opt_node):
            ordered_fixed.append((get_node_id(opt_node), opt_node))

        if len(ordered_fixed) < 2:
            logging.warning(f"结石 {stone_id} 固定节点少于2，跳过")
            updated_paths.append(path_info)
            continue

        # 获取每个固定节点的位置
        fixed_positions = []
        for nid, node in ordered_fixed:
            pos = np.array(get_node_pos(node))
            fixed_positions.append(pos)

        logging.info(f"结石 {stone_id}: 分段数 {len(ordered_fixed) - 1}, 节点序列: {[nid for nid, _ in ordered_fixed]}")

        # 为每段提取原始路径点（通过坐标最近邻获取索引）
        fixed_indices = []
        for nid, node in ordered_fixed:
            pos = np.array(get_node_pos(node))
            dists = np.linalg.norm(coords - pos, axis=1)
            idx = np.argmin(dists)
            if dists[idx] > 2.0:
                logging.warning(f"固定节点 {nid} 与原始路径点距离 {dists[idx]:.2f} mm，可能不匹配")
            fixed_indices.append(idx)

        segment_paths = []
        for i in range(len(ordered_fixed) - 1):
            src_idx = fixed_indices[i]
            tgt_idx = fixed_indices[i + 1]
            orig_seg = coords[min(src_idx, tgt_idx):max(src_idx, tgt_idx) + 1]
            if len(orig_seg) < 2:
                orig_seg = np.array([fixed_positions[i], fixed_positions[i + 1]])

            src_nid = ordered_fixed[i][0]
            tgt_nid = ordered_fixed[i + 1][0]

            # 所有段都使用控制点优化
            logging.info(f"  第 {i + 1} 段: [{src_nid}] -> [{tgt_nid}], 原始点数 {len(orig_seg)}")
            seg = optimize_segment(
                fixed_positions[i], fixed_positions[i + 1], sdf_interp,
                step_mm=step_mm, n_ctrl=n_ctrl,
                alpha=alpha, beta=beta,
                smooth_weight=smooth_weight, riemann_weight=riemann_weight,
                max_iter=max_iter, verbose=False,
                original_segment_points=orig_seg,
                min_seg_len=min_seg_len, endpoint_margin=endpoint_margin,
                sdf_grid=sdf_grid, origin=origin, step=step,
                interior_margin=interior_margin,  # 新增
            )
            segment_paths.append(seg)

        # 拼接
        full_path = segment_paths[0]
        for seg in segment_paths[1:]:
            full_path = np.vstack([full_path, seg[1:]])


        path_info['path_coordinates'] = full_path.tolist()
        path_info['segments'] = [
            {
                'from': ordered_fixed[i][0],
                'to': ordered_fixed[i + 1][0],
                'points': seg.tolist()
            }
            for i, seg in enumerate(segment_paths)
        ]
        if 'tree_topology' not in path_info:
            path_info['tree_topology'] = {}
        path_info['tree_topology']['smooth_method'] = 'control_point_optimization_on_path'
        path_info['tree_topology']['smooth_params'] = {
            'resolution': resolution,
            'alpha': alpha,
            'beta': beta,
            'smooth_weight': smooth_weight,
            'riemann_weight': riemann_weight,
            'n_ctrl': n_ctrl,
            'min_seg_len': min_seg_len,
            'endpoint_margin': endpoint_margin
        }
        updated_paths.append(path_info)

    topology_data['paths'] = updated_paths
    topology_data['metadata']['smooth_processing'] = '分段控制点优化（所有段均使用控制点优化）'
    return topology_data


def visualize_optimization(topology_data, kidney_mesh, stone_mesh, output_html=None, interactive=True):
    """
    完全参照 visualize.py 的可视化方式，显示优化后的路径。
    """


    # 创建绘图窗口
    plotter = vedo.Plotter(axes=0, bg='white', size=(1600, 1000))

    # 加载肾脏网格（将 trimesh 转为 vedo.Mesh）
    if kidney_mesh is not None:
        try:
            vertices = kidney_mesh.vertices
            faces = kidney_mesh.faces
            vedo_kidney = vedo.Mesh([vertices, faces])
            vedo_kidney.alpha(0.1).color('red')
            plotter.add(vedo_kidney)
        except Exception as e:
            logging.warning(f"肾脏网格可视化失败: {e}")

    # 加载结石网格（将 trimesh 转为 vedo.Mesh）
    if stone_mesh is not None:
        try:
            vertices = stone_mesh.vertices
            faces = stone_mesh.faces
            vedo_stone = vedo.Mesh([vertices, faces])
            vedo_stone.alpha(1.0).color('yellow')
            plotter.add(vedo_stone)
        except Exception as e:
            logging.warning(f"结石网格可视化失败: {e}")

    # 收集元素
    all_skeleton_points = []
    all_original_branch_points = []
    all_projected_points = []
    all_optimal_points = []
    all_urethra_points = []

    paths = topology_data.get('paths', [])
    if not paths:
        logging.warning("未找到任何路径数据，请检查 JSON 文件。")
        return

    for path_info in paths:
        # 绘制平滑路径线
        if 'path_coordinates' in path_info:
            coords = np.array(path_info['path_coordinates'])
            if len(coords) > 1:
                line = vedo.Line(coords, lw=2, c='blue', alpha=0.8)
                plotter.add(line)
                all_skeleton_points.extend(coords)

        # 从 tree_topology 提取节点信息
        tree = path_info.get('tree_topology', {})
        nodes = tree.get('nodes', [])

        for node in nodes:
            node_type = node.get('type', '')
            pos = node.get('position', node.get('pos', [0, 0, 0]))
            if isinstance(pos, list):
                pos_array = np.array(pos)
            else:
                pos_array = np.array([0, 0, 0])

            if node_type == 'branch_point':
                all_original_branch_points.append(pos_array)
            elif node_type == 'optimal_viewpoint':
                all_optimal_points.append(pos_array)
            elif node_type == 'urethra':
                all_urethra_points.append(pos_array)

        # 如果 tree_topology 中没有最佳观察点，尝试从 path_info 中获取
        if 'optimal_point' in path_info and not any(
                n.get('type') == 'optimal_viewpoint' for n in nodes
        ):
            opt_pos = np.array(path_info['optimal_point'])
            all_optimal_points.append(opt_pos)

    # 计算投影点（路径上距离原始分叉点最近的点）
    if all_skeleton_points and all_original_branch_points:
        all_path_points_array = np.array(all_skeleton_points)
        for orig in all_original_branch_points:
            dists = np.linalg.norm(all_path_points_array - orig, axis=1)
            min_idx = np.argmin(dists)
            proj = all_path_points_array[min_idx]
            all_projected_points.append(proj)

    # 绘制骨架点（灰色小点）
    if all_skeleton_points:
        skeleton_array = np.array(all_skeleton_points)
        skeleton_viz = vedo.Points(skeleton_array, r=2, c='gray', alpha=0.3)
        plotter.add(skeleton_viz)

    # 绘制原始分叉点（红色大点）
    if all_original_branch_points:
        branch_array = np.array(all_original_branch_points)
        branch_array = np.unique(branch_array, axis=0)
        branch_viz = vedo.Points(branch_array, r=10, c='red')
        plotter.add(branch_viz)
        logging.info(f"原始分叉点数量: {len(branch_array)}")

    # 绘制投影点（橙色小点）
    if all_projected_points:
        projected_array = np.array(all_projected_points)
        projected_array = np.unique(projected_array, axis=0)
        projected_viz = vedo.Points(projected_array, r=6, c='orange', alpha=0.7)
        plotter.add(projected_viz)
        logging.info(f"路径投影点数量: {len(projected_array)}")

    # 绘制最佳观察点（绿色大点）
    if all_optimal_points:
        optimal_array = np.array(all_optimal_points)
        optimal_array = np.unique(optimal_array, axis=0)
        optimal_viz = vedo.Points(optimal_array, r=8, c='green')
        plotter.add(optimal_viz)
        logging.info(f"最佳观察点数量: {len(optimal_array)}")

    # 绘制尿道口（紫色大点）
    if all_urethra_points:
        urethra_array = np.array(all_urethra_points)
        urethra_array = np.unique(urethra_array, axis=0)
        urethra_viz = vedo.Points(urethra_array, r=10, c='purple')
        plotter.add(urethra_viz)
        logging.info(f"尿道口数量: {len(urethra_array)}")

    # 添加图例（使用 Text2D）
    legend_text = (
        f"Total Stones: {len(paths)}\n"
        f"Red: Kidney (alpha=0.1)\n"
        f"Yellow: Stone\n"
        f"Blue: Optimized Paths\n"
        f"Red dots: Original Branch Points\n"
        f"Orange dots: Projected Points on Path\n"
        f"Green dots: Optimal Viewpoints\n"
        f"Purple dots: Urethra Entry\n"
        f"Gray dots: Path points"
    )
    vedo.Text2D(legend_text, pos='top-right', c='black', font='Arial', s=0.7)

    # 添加说明文字
    if all_projected_points:
        note_text = "Note: Red=original anatomy, Orange=path projection\nDistance shows smoothing deviation"
        vedo.Text2D(note_text, pos='bottom-left', c='darkred', font='Arial', s=0.6)

    # 显示或保存
    if interactive:
        print("\n🖱️  进入交互模式：")
        print("   - 左键拖动：旋转视图")
        print("   - 中键拖动：平移视图")
        print("   - 滚轮：缩放")
        print("   - 按 'q' 键退出\n")
        plotter.show(interactive=True, zoom=1.2, viewup='z')
    else:
        plotter.show(interactive=False, zoom=1.2, viewup='z')
        if output_html:
            # 保存 PNG 截图
            plotter.screenshot(output_html + ".png")
            # 尝试保存 HTML，若缺少 k3d 则仅提示
            try:
                plotter.export(output_html)
                logging.info(f"可视化已保存至 {output_html} (HTML)")
            except Exception as e:
                logging.warning(f"导出 HTML 失败（可能需要安装 k3d）: {e}")
                logging.info(f"已保存 PNG 截图至 {output_html}.png")
        plotter.close()


def main(input_json_path, mesh_stl_path, stone_stl_path, output_json_path, visualize=True,
         interior_margin=0.5):
    # ================= 调优参数（算法参数，非路径，保持硬编码） =================
    step_mm = 0.5
    alpha = 1
    resolution = 0.5
    beta = 50.0
    riemann_weight = 2.0  # per ablation_riemann_weights.py's NEW_RIEMANN_WEIGHT (joint sweep result), synced back here
    smooth_weight = 30.0  # per ablation_riemann_weights.py's NEW_SMOOTH_WEIGHT (joint sweep result), synced back here
    n_ctrl = 9
    endpoint_margin = 0.05
    max_iter = 500
    min_seg_len = 1.0
    # interior_margin (强制路径距离表面至少多少mm) 现在是可调参数, 见 --interior-margin
    # ==============================================

    # 读取原始数据
    with open(input_json_path, 'r') as f:
        topology_data = json.load(f)

    # 加载肾脏网格
    mesh = load_mesh(mesh_stl_path)

    # 加载肾结石（可选，如果不存在则跳过）
    stone_mesh = None
    if os.path.exists(stone_stl_path):
        try:
            stone_mesh = trimesh.load(stone_stl_path)
            logging.info(f"肾结石加载成功，顶点数: {len(stone_mesh.vertices)}，面数: {len(stone_mesh.faces)}")
        except Exception as e:
            logging.warning(f"肾结石加载失败: {e}")
    else:
        logging.warning(f"肾结石文件不存在: {stone_stl_path}，将不显示结石")



    topology_optimized = update_topology_with_smooth_paths(
        topology_data, mesh,
        resolution=resolution,
        step_mm=step_mm,
        alpha=alpha,
        beta=beta,
        smooth_weight=smooth_weight,
        riemann_weight=riemann_weight,
        n_ctrl=n_ctrl,
        max_iter=max_iter,
        min_seg_len=min_seg_len,
        endpoint_margin=endpoint_margin,
        interior_margin=interior_margin,  # 新增
    )

    # 提取优化后的路径
    optimized_paths = []
    for path_info in topology_optimized['paths']:
        if 'path_coordinates' in path_info:
            optimized_paths.append(np.array(path_info['path_coordinates']))
        else:
            optimized_paths.append(None)

    # 创建输出目录（如果不存在）
    output_dir = os.path.dirname(output_json_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # 保存结果
    with open(output_json_path, 'w') as f:
        json.dump(topology_optimized, f, indent=2)
    logging.info(f"优化完成，结果已保存至 {output_json_path}")

    if visualize:
        visualize_optimization(
            topology_optimized,
            mesh,  # 肾脏网格（trimesh）
            stone_mesh,  # 结石网格（trimesh）
            output_html="path_optimized.html",
            interactive=True
        )


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Smooth/optimize tree-topology paths against an SDF of the kidney mesh")
    parser.add_argument("--case-id", default="1", help="Case number; determines result/<case-id>/...")
    parser.add_argument("--kidney-stl", default="RenalPelvis/RenalPelvis.stl")
    parser.add_argument("--stone-stl", default="RenalPelvis/KidneyStone.stl")
    parser.add_argument("--input-json", default=None,
                         help="默认: result/<case-id>/endoscope_simulation_v2_tree/topology_with_tree_structure.json")
    parser.add_argument("--output-json", default=None,
                         help="默认: result/<case-id>/topology_optimized/topology_optimized.json")
    parser.add_argument("--no-visualize", action="store_true", help="跳过优化后的可视化窗口")
    parser.add_argument("--interior-margin", type=float, default=0.5,
                         help="强制路径距离网格表面至少多少mm (默认0.5)")
    args = parser.parse_args()

    main(
        input_json_path=args.input_json or f"result/{args.case_id}/endoscope_simulation_v2_tree/topology_with_tree_structure.json",
        mesh_stl_path=args.kidney_stl,
        stone_stl_path=args.stone_stl,
        output_json_path=args.output_json or f"result/{args.case_id}/topology_optimized/topology_optimized.json",
        visualize=not args.no_visualize,
        interior_margin=args.interior_margin,
    )