"""
kidney_endoscope_simulator_v2_tree.py
修复版：保持树状拓扑结构的内镜回退模拟
1. 最佳观察点以新节点形式加入拓扑网络
2. 保持所有分叉点信息
3. 不截断原始路径结构
"""

import numpy as np
import vedo
import os
import json
from scipy.interpolate import interp1d
from PIL import Image, ImageDraw
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.optimize import bisect
import traceback
import time
import networkx as nx

def diagnose_stl_file(stl_path, model_name="模型"):
    """
    诊断STL文件状态（跨版本兼容版）
    返回: (bool, str, vedo.Mesh) - (是否成功, 状态信息, mesh对象或None)
    """
    print(f"\n{'='*60}")
    print(f"诊断 {model_name}: {stl_path}")
    print(f"{'='*60}")

    if not os.path.exists(stl_path):
        print(f"❌ 文件不存在")
        return False, "文件不存在", None

    abs_path = os.path.abspath(stl_path)
    print(f"📍 绝对路径: {abs_path}")

    try:
        file_size = os.path.getsize(abs_path)
        print(f"📊 文件大小: {file_size / 1024:.2f} KB")
    except Exception as e:
        print(f"📊 无法获取文件大小: {e}")

    print(f"📁 工作目录: {os.getcwd()}")

    if os.access(abs_path, os.R_OK):
        print(f"✅ 读取权限: 正常")
    else:
        print(f"❌ 读取权限: 无权限")
        return False, "无读取权限", None

    try:
        print(f"🔄 尝试使用 vedo.load() 加载...")
        mesh = vedo.load(abs_path)

        if mesh is None:
            print(f"❌ vedo.load() 返回 None")
            return False, "vedo.load() 返回 None", None

        print(f"✅ 加载成功！")

        try:
            if hasattr(mesh, 'points'):
                points = mesh.points()
                num_vertices = len(points)
            elif hasattr(mesh, 'vertices'):
                vertices = mesh.vertices
                num_vertices = len(vertices)
            elif hasattr(mesh, 'getPoints'):
                points = mesh.getPoints()
                num_vertices = len(points)
            else:
                num_vertices = "未知"

            print(f"   顶点数: {num_vertices}")
        except Exception as e:
            print(f"   无法获取顶点数: {e}")

        try:
            bounds = mesh.bounds()
            print(f"   包围盒: x[{bounds[0]:.1f}, {bounds[1]:.1f}] "
                  f"y[{bounds[2]:.1f}, {bounds[3]:.1f}] "
                  f"z[{bounds[4]:.1f}, {bounds[5]:.1f}]")
        except Exception as e:
            print(f"   无法获取包围盒: {e}")

        return True, "加载成功", mesh

    except Exception as e:
        print(f"❌ 加载失败 - 异常类型: {type(e).__name__}")
        print(f"   异常信息: {str(e)}")
        print(f"   完整堆栈:")
        traceback.print_exc()

        if "Invalid" in str(e):
            return False, "STL文件格式无效", None
        elif "Permission" in str(e):
            return False, "权限被拒绝", None
        elif "Memory" in str(e):
            return False, "内存不足", None
        elif "attribute" in str(e).lower() or "has no attribute" in str(e):
            return False, f"API不兼容: {str(e)}", None
        else:
            return False, f"未知错误: {str(e)}", None


def create_dashed_line(p1, p2, num_segments=20, **kwargs):
    """手动创建虚线效果（跨版本兼容）"""
    p1, p2 = np.array(p1, dtype=np.float64), np.array(p2, dtype=np.float64)
    points = np.linspace(p1, p2, num_segments)

    lines = []
    for i in range(0, num_segments-1, 2):
        line = vedo.Line(points[i], points[i+1], **kwargs)
        lines.append(line)

    return lines


class VirtualEndoscopeCameraV2:
    """第二代虚拟相机 - 使用诊断版加载"""

    def __init__(self, kidney_stl_path, stone_stl_path, image_width=800, image_height=600):
        self.kidney_stl_path = kidney_stl_path
        self.stone_stl_path = stone_stl_path
        self.image_width = image_width
        self.image_height = image_height

        self.kidney_mesh = None
        self.stone_mesh = None

        self._load_models_with_diagnosis()

    def _load_models_with_diagnosis(self):
        """带诊断的模型加载（修复返回值）"""
        print("\n" + "="*80)
        print("正在诊断并加载STL模型...")
        print("="*80)

        kidney_ok, kidney_msg, kidney_mesh = diagnose_stl_file(self.kidney_stl_path, "肾脏模型")
        if kidney_ok and kidney_mesh is not None:
            self.kidney_mesh = kidney_mesh
        else:
            print(f"⚠️  肾脏模型加载失败: {kidney_msg}")
            print(f"   将使用默认替代方案（半透明红色立方体）")
            self.kidney_mesh = vedo.Box(size=(50, 100, 80)).pos(0, 0, 0)
            self.kidney_mesh.alpha(1).color('red')

        stone_ok, stone_msg, stone_mesh = diagnose_stl_file(self.stone_stl_path, "结石模型")
        if stone_ok and stone_mesh is not None:
            self.stone_mesh = stone_mesh
        else:
            print(f"⚠️  结石模型加载失败: {stone_msg}")
            print(f"   将使用默认替代方案（黄色小球体）")
            self.stone_mesh = vedo.Sphere(pos=(0,0,0), r=3.0)
            self.stone_mesh.alpha(1.0).color('yellow')
            print("\n" + "⚠️ "*20)
            print("警告：使用默认模型，结果可能不准确！")
            print("请检查真实的STL文件路径和格式")
            print("⚠️ "*20 + "\n")

        print("\n✅ 模型加载阶段完成")
        print(f"   肾脏模型: {'✓ 已加载' if self.kidney_mesh else '✗ 加载失败'}")
        print(f"   结石模型: {'✓ 已加载' if self.stone_mesh else '✗ 加载失败'}")

    def render_view(self, camera_pos, look_at, fov_degrees=70, mode='visual'):
        """
        渲染虚拟内镜视图
        mode: 'visual' (美观) 或 'analysis' (分析)
        """
        from vtkmodules.vtkRenderingCore import vtkCamera

        if self.kidney_mesh is None or self.stone_mesh is None:
            print("    ❌ 关键模型缺失，返回黑色图像")
            return Image.new('RGB', (self.image_width, self.image_height), 'black')

        plotter = vedo.Plotter(offscreen=True, size=(self.image_width, self.image_height))

        kidney = self.kidney_mesh.clone()
        kidney.color('red').alpha(0.15)

        stone = self.stone_mesh.clone()
        stone.color('yellow').alpha(1.0)

        if mode == 'analysis':
            stone.lighting('off')
            plotter.background('white')
        else:
            plotter.background('black')

        plotter.add(kidney)
        plotter.add(stone)

        vtk_camera = plotter.renderer.GetActiveCamera()
        camera_pos = np.array(camera_pos, dtype=np.float64)
        look_at = np.array(look_at, dtype=np.float64)

        forward = look_at - camera_pos
        forward_norm = np.linalg.norm(forward)
        if forward_norm < 1e-8:
            return Image.new('RGB', (self.image_width, self.image_height), 'black')
        forward = forward / forward_norm

        up_vector = np.array([0, 1, 0], dtype=np.float64)
        right = np.cross(forward, up_vector)
        right_norm = np.linalg.norm(right)
        if right_norm < 1e-8:
            right = np.array([1, 0, 0], dtype=np.float64)
        else:
            right = right / right_norm

        up = np.cross(right, forward)

        vtk_camera.SetPosition(camera_pos.tolist())
        vtk_camera.SetFocalPoint(look_at.tolist())
        vtk_camera.SetViewUp(up.tolist())
        vtk_camera.SetUseHorizontalViewAngle(True)
        vtk_camera.SetViewAngle(fov_degrees)
        vtk_camera.Modified()

        try:
            plotter.show(interactive=False, resetcam=False)
            img_array = plotter.screenshot(asarray=True)
            plotter.close()
        except Exception as e:
            print(f"    ❌ 渲染失败: {e}")
            return Image.new('RGB', (self.image_width, self.image_height), 'black')

        if img_array is None or not isinstance(img_array, np.ndarray):
            return Image.new('RGB', (self.image_width, self.image_height), 'black')

        try:
            if img_array.shape[2] == 4:
                img_array = img_array[:, :, :3]
            if img_array.dtype != np.uint8:
                img_array = (img_array * 255).astype(np.uint8) if img_array.max() <= 1.0 else img_array.astype(np.uint8)
            return Image.fromarray(img_array)
        except Exception as e:
            print(f"    ❌ 数组转图像失败: {e}")
            return Image.new('RGB', (self.image_width, self.image_height), 'black')

    def calculate_stone_ratio_by_color(self, img, target_color='yellow', mode='visual'):
        """
        通过颜色分析计算结石占比
        """
        if img is None or not isinstance(img, Image.Image):
            return 0.0, None

        try:
            img_array = np.array(img)
            threshold = 120 if mode == 'analysis' else 100

            color_map = {
                'yellow': np.array([255, 255, 0]),
                'red': np.array([255, 0, 0]),
            }
            target_rgb = color_map.get(target_color, np.array([255, 255, 0]))

            diff = np.linalg.norm(img_array.astype(np.float32) - target_rgb[:3], axis=2)
            stone_pixels = diff < threshold

            ratio = np.sum(stone_pixels) / (img_array.shape[0] * img_array.shape[1])
            return ratio, stone_pixels

        except Exception as e:
            print(f"    ❌ 颜色分析失败: {e}")
            return 0.0, None


class KidneyEndoscopeSimulatorV2:
    """第二代内窥镜回退模拟器 - 保持树状拓扑"""

    def __init__(self, topology_data, path_info,
                 kidney_stl_path, stone_stl_path,
                 step_mm=1.0, fine_step_mm=0.1,
                 output_dir=None):
        self.topology_data = topology_data
        self.path_info = path_info
        self.kidney_stl_path = kidney_stl_path
        self.stone_stl_path = stone_stl_path
        self.step_mm = step_mm
        self.fine_step_mm = fine_step_mm
        self.output_dir = output_dir  # 保存输出目录

        if 'path_coordinates' not in path_info:
            raise KeyError(f"❌ JSON中缺少 'path_coordinates' 键！可用键: {list(path_info.keys())}")

        self.path_coords = np.array(path_info['path_coordinates'])
        self.stone_id = path_info['stone_id']
        self.stone_center = self.path_coords[-1]

        # 提取拓扑图中的分叉点信息
        self.branch_points = self._extract_branch_points_from_topology()

        self.dense_path = self._interpolate_path(step_mm)

        self.optimal_point = None
        self.optimal_ratio = None
        self.retreat_data = []

        self.camera = VirtualEndoscopeCameraV2(
            kidney_stl_path=kidney_stl_path,
            stone_stl_path=stone_stl_path
        )

        print(f"  - 原始路径点数: {len(self.path_coords)}")
        print(f"  - 分叉点数量: {len(self.branch_points)}")
        print(f"  - 插值后路径点数: {len(self.dense_path)}")
        print(f"  - 结石ID: {self.stone_id}")

    def _extract_branch_points_from_topology(self):
        """从拓扑数据中提取分叉点信息"""
        branch_points = []

        # 首先尝试从路径信息中获取分叉点
        if 'branch_points' in self.path_info:
            branch_points = [np.array(bp) for bp in self.path_info['branch_points']]
            print(f"    从path_info中找到分叉点: {len(branch_points)}个")
            return branch_points

        # 如果没有，从原始拓扑图中提取
        if 'nodes' in self.topology_data:
            for node in self.topology_data['nodes']:
                if node.get('type') == 'branch_point' or node.get('type') == 'skeleton':
                    # 检查是否在路径上
                    position = np.array(node.get('position', node.get('pos', [0,0,0])))
                    # 找到路径上最近的点
                    distances = np.linalg.norm(self.path_coords - position, axis=1)
                    min_dist = np.min(distances)
                    if min_dist < 2.0:  # 2mm容差内认为是路径上的点
                        # 检查度数
                        node_id = node.get('node_id', '')
                        if 'branch' in node_id.lower() or self._is_branch_node_in_graph(node_id):
                            branch_points.append(position)

        print(f"    从拓扑数据中提取分叉点: {len(branch_points)}个")
        return branch_points

    def _is_branch_node_in_graph(self, node_id):
        """检查节点在拓扑图中是否为分叉点"""
        if 'edges' not in self.topology_data:
            return False

        # 统计连接到该节点的边数
        edge_count = 0
        for edge in self.topology_data['edges']:
            if edge.get('source') == node_id or edge.get('target') == node_id:
                edge_count += 1

        return edge_count >= 3  # 度数≥3为分叉点

    def _interpolate_path(self, step_mm):
        """将路径插值为固定步长的密集点序列"""
        if len(self.path_coords) < 2:
            return self.path_coords

        distances = [0.0]
        for i in range(1, len(self.path_coords)):
            dist = np.linalg.norm(self.path_coords[i] - self.path_coords[i-1])
            distances.append(distances[-1] + dist)

        total_distance = distances[-1]
        num_points = max(2, int(total_distance / step_mm) + 1)
        interp_distances = np.linspace(0, total_distance, num_points)

        coords_transposed = self.path_coords.T
        interpolated_coords = []

        for dim_coords in coords_transposed:
            interp_func = interp1d(distances, dim_coords, kind='linear')
            interpolated_dim = interp_func(interp_distances)
            interpolated_coords.append(interpolated_dim)

        return np.array(interpolated_coords).T

    def _get_path_position_by_distance(self, distance_from_stone):
        """根据距离结石的距离，获取路径上的精确位置（连续）"""
        distances_to_stone = np.array([
            np.linalg.norm(point - self.stone_center)
            for point in self.path_coords
        ])

        if distances_to_stone[0] < distances_to_stone[-1]:
            distances_to_stone = distances_to_stone[::-1]
            coords = self.path_coords[::-1]
        else:
            coords = self.path_coords

        for i in range(len(distances_to_stone) - 1):
            d1, d2 = distances_to_stone[i], distances_to_stone[i + 1]
            if min(d1, d2) <= distance_from_stone <= max(d1, d2):
                ratio = (distance_from_stone - d1) / (d2 - d1)
                position = coords[i] + ratio * (coords[i + 1] - coords[i])
                return position

        return coords[0] if distance_from_stone < distances_to_stone[-1] else coords[-1]

    def _get_stone_ratio_at_position(self, position, fov_degrees=70, save_screenshot=False, screenshot_path=None):
        """在指定位置渲染并计算结石颜色占比"""
        if self.camera.kidney_mesh is None or self.camera.stone_mesh is None:
            print("    ❌ 关键模型未加载，返回0%")
            return 0.0

        try:
            img = self.camera.render_view(
                camera_pos=position,
                look_at=self.stone_center,
                fov_degrees=fov_degrees,
                mode='analysis'
            )

            if save_screenshot and screenshot_path:
                try:
                    img.save(screenshot_path)
                    print(f"    📸 分析模式截图已保存: {screenshot_path}")
                except Exception as e:
                    print(f"    ⚠️ 截图保存失败: {e}")

            ratio, _ = self.camera.calculate_stone_ratio_by_color(
                img, target_color='yellow'
            )
            return ratio
        except Exception as e:
            print(f"    ❌ 渲染失败: {e}")
            traceback.print_exc()
            return 0.0

    def simulate_retreat_continuous(self, target_ratio=0.30, fov_degrees=70, interactive=False,
                                    capture_all_images=True):
        """
        连续路径回退模拟（精确查找临界点）- 保持树状拓扑

        参数:
            target_ratio: float, 目标结石占比（0~1）
            fov_degrees: float, 视场角（度）
            interactive: bool, 是否交互式显示每个渲染结果
            capture_all_images: bool, 是否保存所有采样点的照片（True=全过程拍照，False=仅关键帧）

        返回:
            optimal_point: ndarray, 最佳观察点坐标
            retreat_data: list, 回退数据
            topology_updates: dict, 拓扑更新信息（保持树状结构）
        """
        print("\n【开始连续回退模拟】")
        print(f"  目标结石占比: {target_ratio * 100:.1f}%")
        print(f"  视场角: {fov_degrees}°")
        print(f"  粗采样步长: {self.step_mm} mm")
        print(f"  精细搜索步长: {self.fine_step_mm} mm")
        print(f"  拍照模式: {'全过程' if capture_all_images else '仅关键帧'}")
        print(f"  拓扑保持: 树状结构（保持所有分叉点）")

        if self.camera.kidney_mesh is None or self.camera.stone_mesh is None:
            print("  ❌ 关键模型未加载，模拟终止")
            print("  📋 请查看上方的诊断信息，检查STL文件问题")
            return None, self.retreat_data, None

        # 构建截图目录：优先使用 self.output_dir，否则使用默认路径
        if self.output_dir:
            screenshot_dir = os.path.join(self.output_dir, f"screenshots_stone_{self.stone_id}")
        else:
            screenshot_dir = f"./endoscope_simulation_v2/screenshots_stone_{self.stone_id}"
        os.makedirs(screenshot_dir, exist_ok=True)

        total_path_length = self.path_info['path_length']

        # 1. 粗采样阶段
        print("\n  1. 粗采样阶段...")
        critical_interval = None

        for dist in np.arange(0, total_path_length, self.step_mm):
            position = self._get_path_position_by_distance(dist)

            # 根据 capture_all_images 决定是否保存所有照片
            save_screenshot = capture_all_images or (dist % 10 == 0)
            screenshot_path = os.path.join(screenshot_dir, f"coarse_{dist:.1f}mm.png") if save_screenshot else None

            ratio = self._get_stone_ratio_at_position(position, fov_degrees, save_screenshot, screenshot_path)

            self.retreat_data.append({
                'distance_from_stone': dist,
                'position': position.tolist(),
                'ratio': ratio,
                'stage': 'coarse'
            })

            if dist % 5 == 0 or ratio > 0:
                print(f"    距离结石{dist:5.1f}mm → 占比{ratio * 100:5.1f}%")

                if interactive and dist % 10 == 0:
                    img = self.camera.render_view(position, self.stone_center, fov_degrees)
                    img.show(title=f"Distance: {dist:.1f}mm, Ratio: {ratio * 100:.1f}%")

            # 找到临界点（占比首次低于目标值）
            if ratio <= target_ratio and ratio > 0:
                critical_interval = (max(0, dist - self.step_mm), dist)
                print(f"    ✅ 找到临界区间: [{critical_interval[0]:.1f}, {critical_interval[1]:.1f}] mm")
                break

        if critical_interval is None:
            print("    ⚠️ 未找到有效临界区间")
            return None, self.retreat_data, None

        # 2. 精细搜索阶段（二分法）
        print("\n  2. 精细搜索阶段...")

        def ratio_error(distance):
            """计算占比与目标值的差值（用于二分法）"""
            position = self._get_path_position_by_distance(distance)

            # 精细搜索阶段：根据 capture_all_images 决定是否保存照片
            save_screenshot = capture_all_images
            screenshot_path = os.path.join(screenshot_dir, f"fine_{distance:.2f}mm.png") if save_screenshot else None

            ratio = self._get_stone_ratio_at_position(position, fov_degrees, save_screenshot, screenshot_path)

            self.retreat_data.append({
                'distance_from_stone': distance,
                'position': position.tolist(),
                'ratio': ratio,
                'stage': 'fine'
            })

            if interactive:
                img = self.camera.render_view(position, self.stone_center, fov_degrees)
                img.show(title=f"Fine Search: {distance:.2f}mm, Ratio: {ratio * 100:.1f}%")

            return ratio - target_ratio

        # 二分法查找
        d1, d2 = critical_interval
        try:
            r1 = ratio_error(d1)
            r2 = ratio_error(d2)

            if r1 * r2 > 0:
                raise ValueError("端点同号，无法使用二分法")

            optimal_distance = bisect(
                f=ratio_error,
                a=d1,
                b=d2,
                xtol=self.fine_step_mm,
                maxiter=50
            )
        except Exception as e:
            print(f"    ⚠️ 二分法失败: {e}")
            # 回退到线性插值
            r1 = self.retreat_data[-2]['ratio']
            r2 = self.retreat_data[-1]['ratio']
            if abs(r2 - r1) > 1e-6:
                weight = (target_ratio - r1) / (r2 - r1)
                optimal_distance = d1 + weight * (d2 - d1)
            else:
                optimal_distance = (d1 + d2) / 2

        # 获取最佳观察点并计算实际占比
        self.optimal_point = self._get_path_position_by_distance(optimal_distance)
        self.optimal_ratio = self._get_stone_ratio_at_position(self.optimal_point, fov_degrees)

        print(f"    ✅ 最佳距离: {optimal_distance:.2f} mm")
        print(f"    ✅ 实际占比: {self.optimal_ratio * 100:.1f}%")

        # 3. 生成拓扑更新信息（保持树状结构）
        print("\n  3. 生成拓扑更新信息（树状结构）...")
        topology_updates = self._create_tree_topology_updates(optimal_distance)

        return self.optimal_point, self.retreat_data, topology_updates

    def _create_tree_topology_updates(self, optimal_distance):
        """
        创建树状拓扑更新信息 - 截断法：删除超过最佳观察点的路径点

        最佳观察点作为新终点，删除所有更靠近结石的点
        """
        print(f"    截断法：最优距离 = {optimal_distance:.2f}mm")

        # 1. 计算路径上每个点到结石的距离
        distances_to_stone = np.linalg.norm(self.path_coords - self.stone_center, axis=1)

        # 2. 找到第一个距离小于等于最优距离的点（从尿道口开始）
        # 注意：path_coords是从尿道口到结石的，距离由大到小
        optimal_idx = None
        for i, dist in enumerate(distances_to_stone):
            if dist <= optimal_distance + 0.5:  # 0.5mm容差
                optimal_idx = i
                break

        # 如果没找到，使用最后一个点
        if optimal_idx is None:
            optimal_idx = len(self.path_coords) - 1

        print(f"    原始路径长度: {len(self.path_coords)}个点")
        print(f"    截断点索引: {optimal_idx}")

        # 3. 截断路径：保留从尿道口到最佳观察点的部分
        truncated_path = self.path_coords[:optimal_idx + 1].copy()

        # 4. 将截断路径的最后一个点设置为最佳观察点
        truncated_path[-1] = self.optimal_point.copy()

        print(f"    截断后路径长度: {len(truncated_path)}个点")
        print(f"    截断路径终点（最佳观察点）: {self.optimal_point.tolist()}")

        # 5. 构建树状拓扑节点和边
        tree_nodes = []
        tree_edges = []

        # 添加截断路径的节点
        for i, point in enumerate(truncated_path):
            node_id = f"path_node_{i}_{self.stone_id}"

            # 判断节点类型
            if i == len(truncated_path) - 1:
                # 最后一个点是最佳观察点
                node_type = 'optimal_viewpoint'
            else:
                # 检查是否为分叉点
                node_type = 'skeleton'
                for branch_point in self.branch_points:
                    if np.linalg.norm(point - branch_point) < 1.0:  # 1mm容差
                        node_type = 'branch_point'
                        break

            tree_nodes.append({
                'id': node_id,
                'position': point.tolist(),
                'type': node_type,
                'stone_id': self.stone_id,
                'original_index': i,
                'distance_to_stone': float(np.linalg.norm(point - self.stone_center))
            })

            # 添加边（连接到前一个节点）
            if i > 0:
                prev_node_id = f"path_node_{i - 1}_{self.stone_id}"
                distance = float(np.linalg.norm(point - truncated_path[i - 1]))
                tree_edges.append({
                    'source': prev_node_id,
                    'target': node_id,
                    'type': 'skeleton' if node_type != 'optimal_viewpoint' else 'optimal_connection',
                    'distance': distance,
                    'stone_id': self.stone_id
                })

        # 6. 添加结石节点（作为独立节点，不连接到路径）
        stone_node = {
            'id': f"stone_{self.stone_id}",
            'position': self.stone_center.tolist(),
            'type': 'stone',
            'stone_id': self.stone_id
        }

        print(f"    树状拓扑节点数: {len(tree_nodes)} + 结石节点")
        print(f"    树状拓扑边数: {len(tree_edges)}")

        # 计算保留了哪些分叉点
        preserved_branches = []
        for node in tree_nodes:
            if node['type'] == 'branch_point':
                preserved_branches.append({
                    'position': node['position'],
                    'node_id': node['id']
                })

        return {
            'stone_id': self.stone_id,
            'optimal_node_id': tree_nodes[-1]['id'],
            'optimal_point': self.optimal_point.tolist(),
            'optimal_distance': float(optimal_distance),
            'optimal_ratio': float(self.optimal_ratio) if self.optimal_ratio else 0.0,
            'truncated_path': truncated_path.tolist(),  # 保存截断后的路径
            'truncated_indices': list(range(optimal_idx + 1)),  # 保存截断点索引
            'tree_nodes': tree_nodes,
            'tree_edges': tree_edges,
            'stone_node': stone_node,
            'preserved_branch_points': preserved_branches,
            'topology_structure': 'truncated_tree',
            'branch_points_preserved': len(preserved_branches) > 0
        }

    def plot_retreat_curve(self, output_path):
        """绘制回退曲线"""
        if not self.retreat_data:
            print("  ⚠️ 无数据可绘制")
            return

        coarse_data = [r for r in self.retreat_data if r['stage'] == 'coarse']
        fine_data = [r for r in self.retreat_data if r['stage'] == 'fine']

        fig, ax = plt.subplots(figsize=(12, 8))

        if coarse_data:
            coarse_dist = [r['distance_from_stone'] for r in coarse_data]
            coarse_ratio = [r['ratio']*100 for r in coarse_data]
            ax.plot(coarse_dist, coarse_ratio, 'b-', linewidth=1, alpha=0.5, label='Coarse Sampling')
            ax.scatter(coarse_dist, coarse_ratio, c='blue', s=30, alpha=0.6)

        if fine_data:
            fine_dist = [r['distance_from_stone'] for r in fine_data]
            fine_ratio = [r['ratio']*100 for r in fine_data]
            ax.plot(fine_dist, fine_ratio, 'r-', linewidth=2, label='Fine Search')
            ax.scatter(fine_dist, fine_ratio, c='red', s=10, alpha=0.8)

        ax.axhline(y=30, color='g', linestyle='--', linewidth=2, label='Target 30%')
        if self.optimal_point is not None:
            opt_dist = np.linalg.norm(self.optimal_point - self.stone_center)
            ax.axvline(x=opt_dist, color='orange', linestyle=':',
                      label=f'Optimal Point (dist={opt_dist:.1f}mm)')
            ax.scatter([opt_dist], [self.optimal_ratio*100],
                      c='green', s=100, marker='*', zorder=10,
                      label=f'Final: {self.optimal_ratio*100:.1f}%')

        ax.set_xlabel('Distance from Stone (mm)', fontsize=12)
        ax.set_ylabel('Stone Area Ratio (%)', fontsize=12)
        ax.set_title(f'Endoscope Retreat Curve - Stone {self.stone_id}', fontsize=14)
        ax.legend()
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()

        print(f"✅ 回退曲线已保存: {output_path}")


class KidneyEndoscopeVisualizerV2:
    """第二代可视化器 - 支持树状拓扑显示"""

    def __init__(self, topology_data, camera):
        self.topology_data = topology_data
        self.camera = camera

    def create_comprehensive_visualization(self, output_path, interactive=False):
        """
        创建综合可视化 - 与kidney_path_topology.py完全一致的显示风格

        修改要点：
        1. 分叉点用显著的红点（r=8，c='red'）
        2. 路径统一用蓝色（lw=2，c='blue'，alpha=0.6）
        3. 粗细大小完全一致
        4. 最佳观察点用绿色点（r=6，c='green'）
        5. 骨架节点用灰色小点（r=2，c='gray'，alpha=0.3）
        """
        print(f"生成综合3D可视化{' - 交互模式' if interactive else ''}...")

        if self.camera.kidney_mesh is None or self.camera.stone_mesh is None:
            print("❌ 关键模型未加载，无法生成可视化")
            return

        plotter = vedo.Plotter(axes=0, bg='white', size=(1600, 1000))

        # 1. 显示肾脏模型（半透明红色）- 与kidney_path_topology.py完全一致
        kidney_clone = self.camera.kidney_mesh.clone()
        kidney_clone.alpha(0.1).color('red')
        plotter.add(kidney_clone)

        # 2. 显示结石模型（非透明黄色）- 与kidney_path_topology.py完全一致
        stone_clone = self.camera.stone_mesh.clone()
        stone_clone.alpha(1.0).color('yellow')
        plotter.add(stone_clone)

        # 3. 收集所有要显示的元素，避免重复
        all_skeleton_points = []
        all_branch_points = []
        all_optimal_points = []
        all_edges = []  # 存储边信息：(source_pos, target_pos, color, lw, alpha)

        # 4. 处理所有结石的拓扑
        all_paths = self.topology_data['paths']

        for i, path_info in enumerate(all_paths):
            stone_id = path_info['stone_id']

            # 4.1 如果有树状拓扑，使用树状拓扑数据
            if 'tree_topology' in path_info:
                tree_topology = path_info['tree_topology']

                # 收集节点
                for node in tree_topology.get('nodes', []):
                    node_type = node.get('type', '')
                    position = np.array(node.get('position', [0, 0, 0]))

                    if node_type == 'optimal_viewpoint':
                        all_optimal_points.append(position)
                    elif node_type == 'branch_point':
                        all_branch_points.append(position)
                    elif node_type == 'skeleton':
                        all_skeleton_points.append(position)

                # 收集边
                for edge in tree_topology.get('edges', []):
                    source_id = edge.get('source', '')
                    target_id = edge.get('target', '')
                    edge_type = edge.get('type', 'skeleton')

                    # 找到源节点和目标节点的位置
                    source_pos = None
                    target_pos = None

                    for node in tree_topology.get('nodes', []):
                        if node.get('id') == source_id:
                            source_pos = np.array(node.get('position', [0, 0, 0]))
                        if node.get('id') == target_id:
                            target_pos = np.array(node.get('position', [0, 0, 0]))

                    if source_pos is not None and target_pos is not None:
                        # 统一使用蓝色，线宽2，透明度0.6
                        color = 'blue'
                        lw = 4
                        alpha = 0.6

                        if edge_type == 'optimal_connection':
                            color = 'blue'  # 最佳观察点连接线用绿色
                            lw = 4
                            alpha = 0.6

                        all_edges.append((source_pos, target_pos, color, lw, alpha))

            # 4.2 向后兼容：如果没有树状拓扑，使用原始数据
            elif 'optimal_point' in path_info:
                optimal_point = np.array(path_info['optimal_point'])
                all_optimal_points.append(optimal_point)

                # 如果有截断路径，添加边
                if 'truncated_dense_path' in path_info:
                    truncated_path = np.array(path_info['truncated_dense_path'])

                    # 确保路径最后一个点精确等于optimal_point
                    if len(truncated_path) > 0 and np.linalg.norm(truncated_path[-1] - optimal_point) > 0.01:
                        truncated_path[-1] = optimal_point

                    # 添加路径上的点
                    for point in truncated_path:
                        all_skeleton_points.append(point)

                    # 添加路径边（蓝色）
                    if len(truncated_path) > 1:
                        for i in range(len(truncated_path) - 1):
                            all_edges.append((truncated_path[i], truncated_path[i + 1], 'blue', 2, 0.6))

        # 5. 批量显示所有元素 - 与kidney_path_topology.py完全一致

        # 5.1 显示骨架节点（灰色小点）- 与kidney_path_topology.py一致
        if all_skeleton_points:
            skeleton_array = np.array(all_skeleton_points)
            skeleton_viz = vedo.Points(skeleton_array, r=2, c='gray', alpha=0.3)
            plotter.add(skeleton_viz)

        # 5.2 显示分叉点（显著的红点）- 与kidney_path_topology.py完全一致
        if all_branch_points:
            branch_array = np.array(all_branch_points)
            # 使用r=8，c='red'，与kidney_path_topology.py中的分叉点显示一致
            branch_viz = vedo.Points(branch_array, r=8, c='red')
            plotter.add(branch_viz)

        # 5.3 显示最佳观察点（绿色点）- 比kidney_path_topology.py的尿道口点略小
        if all_optimal_points:
            optimal_array = np.array(all_optimal_points)
            # 使用r=6，c='green'，与kidney_path_topology.py的尿道口点风格一致但略小
            optimal_viz = vedo.Points(optimal_array, r=6, c='green')
            plotter.add(optimal_viz)

            # 添加标签
            for i, optimal_point in enumerate(all_optimal_points):
                stone_id = all_paths[i].get('stone_id', i + 1) if i < len(all_paths) else i + 1
                stone_ratio = all_paths[i].get('actual_stone_ratio', 0) * 100 if i < len(all_paths) else 0
                text_pos = optimal_point + np.array([0, 5, 0])
                vedo.Text3D(f"Opt{stone_id}:{stone_ratio:.1f}%",
                            pos=text_pos, s=2, c='green')

        # 5.4 显示所有边（蓝色实线）- 与kidney_path_topology.py完全一致
        for source_pos, target_pos, color, lw, alpha in all_edges:
            try:
                # 尝试使用dashed参数（如果edge_type有特殊要求）
                if color == 'green':
                    # 绿色最佳观察点连接线
                    line = vedo.Line(source_pos, target_pos, lw=lw, c=color, alpha=alpha)
                else:
                    # 蓝色骨架边和路径边
                    line = vedo.Line(source_pos, target_pos, lw=lw, c=color, alpha=alpha)
            except TypeError:
                # 如果不支持dashed参数，使用普通线
                line = vedo.Line(source_pos, target_pos, lw=lw, c=color, alpha=alpha)
            plotter.add(line)

        # 6. 添加结石ID标签
        for i, path_info in enumerate(all_paths):
            stone_id = path_info.get('stone_id', i + 1)
            if 'path_coordinates' in path_info:
                stone_pos = np.array(path_info['path_coordinates'][-1])
                text_pos = stone_pos + np.array([0, 10, 0])  # 比optimal点更高
                vedo.Text3D(f"Stone {stone_id}", pos=text_pos, s=3, c='black')

        # 7. 简化图例
        legend_text = (f"Total Stones: {len(all_paths)}\n"
                       f"Target Ratio: 30%\n"
                       f"Display Style: kidney_path_topology.py一致\n"
                       f"Colors:\n"
                       f"  Red: Kidney (alpha=0.15)\n"
                       f"  Yellow: Stones (STL, alpha=1.0)\n"
                       f"  Blue: Paths (lw=2, alpha=0.6)\n"
                       f"  Red dots: Branch points (r=8)\n"
                       f"  Green dots: Optimal viewpoints (r=6)")
        vedo.Text2D(legend_text, pos='top-right', c='black', font='Arial', s=0.7)

        if interactive:
            print("  🖱️  进入交互模式：左键旋转 | 中键平移 | 滚轮缩放 | 按 'q' 退出")
            plotter.show(interactive=True, zoom=1.2, viewup='z')
        else:
            plotter.show(interactive=False, zoom=1.2, viewup='z')
            plotter.screenshot(output_path)
            plotter.close()
            print(f"✅ 综合3D可视化已保存: {output_path}")

    def visualize_tree_topology_graph(self, output_path):
        """
        生成树状拓扑的2D图（NetworkX）
        """
        print(f"生成树状拓扑2D图...")

        try:
            # 创建NetworkX图
            G = nx.Graph()

            # 收集所有节点和边
            all_nodes = []
            all_edges = []

            for path_info in self.topology_data['paths']:
                if 'tree_topology' in path_info:
                    tree_topology = path_info['tree_topology']
                    all_nodes.extend(tree_topology.get('nodes', []))
                    all_edges.extend(tree_topology.get('edges', []))

            if not all_nodes:
                print("  ⚠️ 没有树状拓扑数据可显示")
                return

            # 添加到NetworkX图
            node_positions = {}
            node_colors = []
            node_sizes = []

            for node in all_nodes:
                node_id = node.get('id', 'unknown')
                node_type = node.get('type', 'unknown')
                position = node.get('position', [0, 0])

                # 使用2D坐标（忽略Z轴）
                pos_2d = (position[0], position[1]) if len(position) >= 2 else (0, 0)
                node_positions[node_id] = pos_2d

                G.add_node(node_id, **node)

                # 根据节点类型设置颜色和大小
                if node_type == 'optimal_viewpoint':
                    node_colors.append('green')
                    node_sizes.append(200)
                elif node_type == 'branch_point':
                    node_colors.append('red')
                    node_sizes.append(100)
                elif node_type == 'stone':
                    node_colors.append('yellow')
                    node_sizes.append(150)
                elif node_type == 'urethra':
                    node_colors.append('blue')
                    node_sizes.append(120)
                else:
                    node_colors.append('gray')
                    node_sizes.append(50)

            # 添加边
            for edge in all_edges:
                source = edge.get('source', '')
                target = edge.get('target', '')
                if source in node_positions and target in node_positions:
                    G.add_edge(source, target, **edge)

            # 绘制图
            plt.figure(figsize=(14, 10))

            # 使用弹簧布局
            pos = nx.spring_layout(G, seed=42, k=0.5, iterations=50)

            # 绘制边
            nx.draw_networkx_edges(G, pos, alpha=0.5, width=1.5)

            # 绘制节点
            nx.draw_networkx_nodes(G, pos,
                                  node_color=node_colors,
                                  node_size=node_sizes,
                                  alpha=0.8)

            # 绘制标签（只显示部分重要节点）
            labels = {}
            for node in G.nodes():
                node_data = G.nodes[node]
                node_type = node_data.get('type', '')
                if node_type in ['optimal_viewpoint', 'stone', 'branch_point', 'urethra']:
                    # 缩短标签
                    if node_type == 'optimal_viewpoint':
                        stone_id = node_data.get('stone_id', '?')
                        ratio = node_data.get('stone_ratio', 0) * 100
                        labels[node] = f"Opt{stone_id}\n{ratio:.1f}%"
                    elif node_type == 'stone':
                        stone_id = node_data.get('stone_id', '?')
                        labels[node] = f"Stone{stone_id}"
                    elif node_type == 'branch_point':
                        labels[node] = "Branch"
                    elif node_type == 'urethra':
                        labels[node] = "Urethra"

            nx.draw_networkx_labels(G, pos, labels, font_size=8, font_weight='bold')

            plt.title(f"Tree Topology Structure - {len(self.topology_data['paths'])} Stones",
                     fontsize=16, fontweight='bold')
            plt.axis('off')
            plt.tight_layout()
            plt.savefig(output_path, dpi=150, bbox_inches='tight')
            plt.close()

            print(f"✅ 树状拓扑2D图已保存: {output_path}")

        except Exception as e:
            print(f"❌ 生成树状拓扑图失败: {e}")
            traceback.print_exc()


# =======================================================================


def process_all_stones_endoscope_retreat(interactive_final_view=True, capture_all_images=True,
                                         kidney_stl_path=None, stone_stl_path=None,
                                         topology_file=None, output_dir=None):
    """
    批量处理所有结石的端到端函数 - 保持树状拓扑

    参数:
        interactive_final_view: bool, 是否显示交互式3D窗口
        capture_all_images: bool, 是否为每个采样点拍照（True=全过程拍照）
        output_dir: str, 输出目录路径，若为None则使用默认路径
    """
    print("=" * 80)
    print("批量处理所有结石 - 内窥镜最佳观察点计算（树状拓扑）")
    print("=" * 80)


    print("\n📋 文件验证阶段：")
    print("-" * 80)

    kidney_ok, kidney_msg, kidney_mesh = diagnose_stl_file(kidney_stl_path, "肾脏模型")
    if not kidney_ok:
        print(f"⚠️  肾脏模型诊断失败: {kidney_msg}")

    stone_ok, stone_msg, stone_mesh = diagnose_stl_file(stone_stl_path, "结石模型")
    if not stone_ok:
        print(f"⚠️  结石模型诊断失败: {stone_msg}")

    if not kidney_ok and not stone_ok:
        print("\n❌ 所有关键模型都诊断失败，无法继续")
        return None

    print("-" * 80)

    if not os.path.exists(topology_file):
        print(f"❌ 拓扑图文件不存在: {topology_file}")
        return None

    with open(topology_file, 'r', encoding='utf-8') as f:
        topology_data = json.load(f)

    if not topology_data['paths']:
        print("❌ 没有可用的路径数据")
        return None

    print(f"\n✅ 发现 {len(topology_data['paths'])} 个结石，开始批量处理...")

    # 确定输出目录
    if output_dir is None:
        output_dir = "./result/5/endoscope_simulation_v2_tree"
    os.makedirs(output_dir, exist_ok=True)

    updated_paths = []

    shared_camera = VirtualEndoscopeCameraV2(
        kidney_stl_path=kidney_stl_path,
        stone_stl_path=stone_stl_path
    )

    for i, path_info in enumerate(topology_data['paths']):
        stone_id = path_info['stone_id']

        print(f"\n【处理结石 {i+1}/{len(topology_data['paths'])}】")
        print(f"  结石ID: {stone_id}")

        try:
            simulator = KidneyEndoscopeSimulatorV2(
                topology_data=topology_data,
                path_info=path_info,
                kidney_stl_path=kidney_stl_path,
                stone_stl_path=stone_stl_path,
                output_dir=output_dir  # 传入统一输出目录
            )

            simulator.camera = shared_camera

            # 传入capture_all_images参数，接收拓扑更新信息
            optimal_point, retreat_data, topology_updates = simulator.simulate_retreat_continuous(
                target_ratio=0.30,
                fov_degrees=70,
                interactive=False,
                capture_all_images=capture_all_images
            )

            if optimal_point is None or topology_updates is None:
                print(f"  ⚠️ 结石 {stone_id} 模拟失败，跳过")
                continue

            # 计算距离
            stone_center = np.array(path_info['path_coordinates'][-1])
            distance = np.linalg.norm(optimal_point - stone_center)

            # 更新path_info，保存树状拓扑
            path_info['optimal_point'] = optimal_point.tolist()
            path_info['distance_to_stone_mm'] = float(distance)
            path_info['actual_stone_ratio'] = float(simulator.optimal_ratio)
            path_info['target_stone_ratio'] = 0.30
            path_info['precision_mm'] = simulator.fine_step_mm
            path_info['insertion_depth_mm'] = float(path_info['path_length'] - distance)
            path_info['retreat_data'] = retreat_data
            path_info['topology_updates'] = topology_updates

            # 保存树状拓扑结构
            path_info['tree_topology'] = {
                'nodes': topology_updates['tree_nodes'],
                'edges': topology_updates['tree_edges'],
                'topology_structure': 'tree',
                'branch_points_preserved': topology_updates['branch_points_preserved']
            }

            updated_paths.append(path_info)

            print(f"  ✅ 完成: 距离结石 {distance:.2f}mm, 占比 {simulator.optimal_ratio*100:.1f}%")
            print(f"     树状节点数: {len(topology_updates['tree_nodes'])}")
            print(f"     保留分叉点: {topology_updates['branch_points_preserved']}")

        except Exception as e:
            print(f"  ❌ 结石 {stone_id} 处理失败: {e}")
            traceback.print_exc()
            continue

    topology_data['paths'] = updated_paths
    topology_data['metadata']['processing_timestamp'] = '2024-12-10'
    topology_data['metadata']['num_processed_stones'] = len(updated_paths)
    topology_data['metadata']['stone_stl_type'] = 'single_file_all_stones'
    topology_data['metadata']['capture_all_images'] = capture_all_images
    topology_data['metadata']['topology_structure'] = 'tree_preserved'

    # 在保存JSON之前，添加一个转换函数调用
    def convert_to_python_types(obj):
        """递归地将所有numpy类型转换为Python内置类型"""
        import numpy as np

        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {key: convert_to_python_types(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [convert_to_python_types(item) for item in obj]
        elif isinstance(obj, tuple):
            return tuple(convert_to_python_types(item) for item in obj)
        else:
            return obj

    # 转换所有numpy类型
    topology_data = convert_to_python_types(topology_data)

    updated_topology_path = os.path.join(output_dir, "topology_with_tree_structure.json")
    with open(updated_topology_path, 'w', encoding='utf-8') as f:
        json.dump(topology_data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 更新后的拓扑数据已保存: {updated_topology_path}")

    # 生成可视化
    visualizer = KidneyEndoscopeVisualizerV2(topology_data, shared_camera)

    # 3D可视化
    visualizer.create_comprehensive_visualization(
        output_path=os.path.join(output_dir, "all_stones_tree_view.png"),
        interactive=interactive_final_view
    )

    # 2D树状拓扑图
    visualizer.visualize_tree_topology_graph(
        output_path=os.path.join(output_dir, "tree_topology_graph.png")
    )

    generate_summary_report(updated_paths, output_dir)

    return topology_data


def generate_summary_report(updated_paths, output_dir):
    """生成批量处理汇总报告"""
    if not updated_paths:
        return

    print("\n" + "=" * 80)
    print("批量处理汇总报告")
    print("=" * 80)

    summary_data = []
    for path_info in updated_paths:
        summary_data.append({
            'stone_id': path_info['stone_id'],
            'path_length_mm': path_info['path_length'],
            'distance_to_stone_mm': path_info['distance_to_stone_mm'],
            'insertion_depth_mm': path_info['insertion_depth_mm'],
            'target_ratio': path_info['target_stone_ratio'],
            'actual_ratio': path_info['actual_stone_ratio'],
            'precision_mm': path_info['precision_mm'],
            'optimal_point': path_info['optimal_point'],
            'topology_structure': 'tree',
            'branch_points_preserved': path_info.get('tree_topology', {}).get('branch_points_preserved', False),
            'tree_nodes_count': len(path_info.get('tree_topology', {}).get('nodes', [])),
            'tree_edges_count': len(path_info.get('tree_topology', {}).get('edges', []))
        })

        print(f"结石 {path_info['stone_id']:2d}: "
              f"路径长度 {path_info['path_length']:5.1f}mm, "
              f"最佳距离 {path_info['distance_to_stone_mm']:5.1f}mm, "
              f"插入深度 {path_info['insertion_depth_mm']:5.1f}mm, "
              f"实际占比 {path_info['actual_stone_ratio']*100:5.1f}%, "
              f"树状节点 {len(path_info.get('tree_topology', {}).get('nodes', [])):3d}个")

    import pandas as pd

    summary_df = pd.DataFrame(summary_data)
    excel_path = os.path.join(output_dir, "stones_endoscope_summary_tree.xlsx")

    with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
        summary_df.to_excel(writer, sheet_name='Summary', index=False)

        stats_df = pd.DataFrame({
            'Metric': [
                'Total Stones Processed',
                'Average Optimal Distance (mm)',
                'Average Insertion Depth (mm)',
                'Average Actual Ratio (%)',
                'Processing Precision (mm)',
                'Topology Structure',
                'Branch Points Preserved',
                'Average Tree Nodes per Stone'
            ],
            'Value': [
                len(summary_data),
                summary_df['distance_to_stone_mm'].mean(),
                summary_df['insertion_depth_mm'].mean(),
                summary_df['actual_ratio'].mean() * 100,
                summary_df['precision_mm'].iloc[0],
                'Tree (preserved)',
                summary_df['branch_points_preserved'].all(),
                summary_df['tree_nodes_count'].mean()
            ]
        })
        stats_df.to_excel(writer, sheet_name='Statistics', index=False)

    print(f"\n✅ 汇总报告已保存: {excel_path}")

    json_path = os.path.join(output_dir, "stones_endoscope_summary_tree.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=2)

    print(f"✅ 汇总JSON已保存: {json_path}")


# =======================================================================


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Simulate endoscope retreat to find optimal viewpoints")
    parser.add_argument("--case-id", default="1", help="Case number; determines result/<case-id>/...")
    parser.add_argument("--kidney-stl", default="RenalPelvis/RenalPelvis.stl")
    parser.add_argument("--stone-stl", default="RenalPelvis/KidneyStone.stl")
    parser.add_argument("--topology-file", default=None,
                         help="默认: result/<case-id>/topology_results/topology_result.json")
    parser.add_argument("--output-dir", default=None,
                         help="默认: result/<case-id>/endoscope_simulation_v2_tree")
    parser.add_argument("--no-interactive", action="store_true", help="跳过最终交互式3D窗口")
    args = parser.parse_args()

    kidney_stl_path = args.kidney_stl
    stone_stl_path = args.stone_stl
    topology_file = args.topology_file or f"result/{args.case_id}/topology_results/topology_result.json"
    output_dir = args.output_dir or f"result/{args.case_id}/endoscope_simulation_v2_tree"

    print("\n" + "=" * 80)
    print("开始执行内窥镜模拟程序（树状拓扑版）...")
    print("=" * 80)
    start_time = time.perf_counter()

    updated_topology = process_all_stones_endoscope_retreat(
        interactive_final_view=not args.no_interactive,
        capture_all_images=True,
        kidney_stl_path=kidney_stl_path,
        stone_stl_path=stone_stl_path,
        topology_file=topology_file,
        output_dir=output_dir
    )

    if updated_topology:
        print("\n" + "="*80)
        print("✅ 所有操作成功完成！")
        print("="*80)
        print(f"   处理结石数: {len(updated_topology['paths'])}")
        print(f"   输出目录: {output_dir}/")
        print(f"   关键文件: topology_with_tree_structure.json")
        print(f"   综合可视化: all_stones_tree_view.png")
        print(f"   树状拓扑图: tree_topology_graph.png")
        print(f"   汇总报告: stones_endoscope_summary_tree.xlsx")
        print(f"   学术截图: screenshots_stone_*/ 目录下（包含所有采样点）")
        print("\n🖱️  在交互窗口中使用：")
        print("   - 左键拖动：旋转视图")
        print("   - 中键拖动：平移视图")
        print("   - 滚轮：缩放")
        print("   - 按 'q' 键退出")
        print("="*80)
    else:
        print("\n" + "="*80)
        print("❌ 程序执行失败")
        print("="*80)
        print("   请查看上方的详细诊断信息，修复STL文件问题后重试")
        print("="*80)

    end_time = time.perf_counter()
    print(f"\n⏱ 程序总耗时: {end_time - start_time:.2f} 秒")