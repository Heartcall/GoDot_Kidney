"""
肾结石STL分析器（体素分割版）
对STL进行体素化，利用体素连通性分割多个结石，再对每个部分进行骨架提取，得到内部中心点。
"""

import numpy as np
import pyvista as pv
import trimesh
import os
from scipy import ndimage

# 尝试导入骨架化相关库
try:
    from skimage.morphology import skeletonize
    SKELETON_AVAILABLE = True
except ImportError:
    SKELETON_AVAILABLE = False
    print("Warning: scikit-image not available, skeleton-based center calculation will fallback to centroid.")


class KidneyStoneExtractor:
    """
    肾结石STL分析器（体素分割版）
    功能：体素化、连通组件分离、骨架提取、计算每个结石的内部中心点、尺寸、可选可视化
    """

    def __init__(self, stl_path, safe_margin=2.0, voxel_size=0.5, min_voxel_ratio=0.01,
                 auto_process=True, force_interactive=False, visualize=False):
        """
        初始化肾结石分析器

        参数:
        -----------
        stl_path: str
            结石STL文件路径
        safe_margin: float
            安全距离（毫米），内镜应停留在结石外部这个距离
        voxel_size: float
            体素大小（毫米），用于体素化及连通性分析
        min_voxel_ratio: float
            最小体素比例（相对于总前景体素），用于过滤过小的噪声组件
        auto_process: bool
            初始化时是否立即执行体素化+分割+中心点提取（供其他模块直接调用 get_stone_centers()）。
            设为 False 可配合 interactive_analysis() 做分步调试。
        force_interactive: bool
            是否强制使用交互式窗口（可能因环境问题崩溃），默认False，将使用截图方式。
        visualize: bool
            是否进行可视化（截图），如果设为False，将完全不调用任何渲染函数。
        """
        self.stl_path = stl_path
        self.safe_margin = safe_margin
        self.voxel_size = voxel_size
        self.min_voxel_ratio = min_voxel_ratio
        self.force_interactive = force_interactive
        self.visualize = visualize
        self.mesh = None
        self.trimesh_mesh = None
        self.voxelized = None
        self.voxel_matrix = None
        self.components = []
        self.component_masks = []
        self.stone_centers = []
        self.stone_radii = []
        self.stone_safe_radii = []
        self.stone_extents = []

        if stl_path and os.path.exists(stl_path):
            self.load_mesh()
            if auto_process:
                self.voxelize_and_segment()
                self.process_components()

    def get_stone_centers(self):
        """返回所有结石中心点列表（numpy数组）"""
        return self.stone_centers

    def load_mesh(self):
        """加载STL网格，并转换为 trimesh 对象"""
        print("加载肾结石STL文件...")
        try:
            self.mesh = pv.read(self.stl_path)
            print(f"STL文件信息:")
            print(f"  顶点数: {self.mesh.n_points}")
            print(f"  面片数: {self.mesh.n_cells}")

            vertices = self.mesh.points
            faces = self.mesh.faces.reshape(-1, 4)[:, 1:]
            self.trimesh_mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
            print("转换 trimesh 成功")
        except Exception as e:
            print(f"❌ 加载STL失败: {e}")
            import traceback
            traceback.print_exc()
            raise

    def voxelize_and_segment(self):
        """
        体素化网格，并对体素进行连通组件分析，分离多个结石
        """
        if self.trimesh_mesh is None:
            print("❌ 未加载网格")
            return

        print(f"开始体素化 (体素大小: {self.voxel_size}mm)...")
        try:
            self.voxelized = self.trimesh_mesh.voxelized(pitch=self.voxel_size)
            if self.voxelized is None or self.voxelized.matrix is None:
                raise ValueError("体素化失败")
            self.voxel_matrix = self.voxelized.matrix.astype(bool)
            print(f"体素网格形状: {self.voxel_matrix.shape}, 前景体素数: {np.sum(self.voxel_matrix)}")

            labeled, num_features = ndimage.label(self.voxel_matrix)
            print(f"连通组件数量: {num_features}")

            total_voxels = np.sum(self.voxel_matrix)
            min_voxels = int(self.min_voxel_ratio * total_voxels)

            self.components = []
            self.component_masks = []
            for i in range(1, num_features + 1):
                mask = (labeled == i)
                count = np.sum(mask)
                if count >= min_voxels:
                    self.components.append(np.argwhere(mask))
                    self.component_masks.append(mask)
                    print(f"  组件 {len(self.components)}: {count} 个体素 ({count/total_voxels*100:.1f}%)")
                else:
                    print(f"  忽略小组件 {i}: {count} 个体素 (小于 {min_voxels})")

            print(f"保留 {len(self.components)} 个结石组件")
            return len(self.components)

        except Exception as e:
            print(f"❌ 体素化/分割失败: {e}")
            import traceback
            traceback.print_exc()
            return 0

    def _extract_skeleton_center(self, component_mask):
        """
        对单个组件的体素掩码进行骨架提取，返回内部中心点（骨架点平均）
        """
        if not SKELETON_AVAILABLE:
            return None

        try:
            skeleton = skeletonize(component_mask)
            skeleton_indices = np.argwhere(skeleton)
            if len(skeleton_indices) == 0:
                return None

            if hasattr(self.voxelized, 'transform'):
                transform = self.voxelized.transform
                indices_homogeneous = np.hstack([skeleton_indices, np.ones((len(skeleton_indices), 1))])
                skeleton_points = (transform @ indices_homogeneous.T).T[:, :3]
            else:
                skeleton_points = skeleton_indices * self.voxel_size

            center = np.mean(skeleton_points, axis=0)
            return center

        except Exception as e:
            print(f"  骨架提取失败: {e}")
            return None

    def calculate_dimensions(self, component_mask):
        """
        从体素掩码计算尺寸（包围盒、半径）
        """
        indices = np.argwhere(component_mask)
        if len(indices) == 0:
            return None, None, None

        if hasattr(self.voxelized, 'transform'):
            transform = self.voxelized.transform
            indices_homogeneous = np.hstack([indices, np.ones((len(indices), 1))])
            world_coords = (transform @ indices_homogeneous.T).T[:, :3]
        else:
            world_coords = indices * self.voxel_size

        min_coords = world_coords.min(axis=0)
        max_coords = world_coords.max(axis=0)
        extents = max_coords - min_coords
        radius = np.max(extents) / 2.0
        centroid = np.mean(world_coords, axis=0)
        distances = np.linalg.norm(world_coords - centroid, axis=1)
        max_distance = np.max(distances)
        radius = max(radius, max_distance)
        safe_radius = radius + self.safe_margin
        return extents, radius, safe_radius

    def process_components(self):
        """
        对每个组件提取中心点，计算尺寸
        """
        if not self.components:
            print("❌ 无组件可处理")
            return

        self.stone_centers = []
        self.stone_extents = []
        self.stone_radii = []
        self.stone_safe_radii = []

        for idx, mask in enumerate(self.component_masks):
            print(f"处理组件 {idx+1}...")

            extents, radius, safe_radius = self.calculate_dimensions(mask)
            if extents is None:
                print(f"  组件 {idx+1} 尺寸计算失败")
                continue

            center = self._extract_skeleton_center(mask)
            if center is None:
                print(f"  组件 {idx+1} 骨架提取失败，使用体素质心")
                indices = np.argwhere(mask)
                if hasattr(self.voxelized, 'transform'):
                    transform = self.voxelized.transform
                    indices_homogeneous = np.hstack([indices, np.ones((len(indices), 1))])
                    world_coords = (transform @ indices_homogeneous.T).T[:, :3]
                else:
                    world_coords = indices * self.voxel_size
                center = np.mean(world_coords, axis=0)

            self.stone_centers.append(center)
            self.stone_extents.append(extents)
            self.stone_radii.append(radius)
            self.stone_safe_radii.append(safe_radius)

            print(f"  中心点: {center}")
            print(f"  尺寸: {extents}, 半径: {radius:.2f}mm, 安全半径: {safe_radius:.2f}mm")

        print(f"成功处理 {len(self.stone_centers)} 个结石")

    # ========== 安全可视化函数（无窗口模式） ==========
    def _safe_viz(self, func):
        """
        装饰器，捕获可视化异常并打印警告，不中断流程
        """
        try:
            func()
        except Exception as e:
            print(f"⚠️ 可视化失败: {e}")

    def _get_plotter(self):
        """根据设置创建合适的 Plotter"""
        if self.force_interactive:
            return pv.Plotter()
        else:
            # 无头模式，使用 off_screen
            return pv.Plotter(off_screen=True)

    def visualize_mesh(self):
        """可视化原始网格（截图）"""
        if not self.visualize:
            return
        if self.mesh is None:
            return
        plotter = self._get_plotter()
        plotter.add_mesh(self.mesh, color='lightblue', opacity=0.7, show_edges=False)
        plotter.add_axes()
        self._save_or_show(plotter, "Original_Mesh")

    def visualize_voxelization(self):
        """可视化体素化结果（显示体素中心点云）"""
        if not self.visualize:
            return
        if self.voxel_matrix is None:
            return
        indices = np.argwhere(self.voxel_matrix)
        if len(indices) == 0:
            return

        if hasattr(self.voxelized, 'transform'):
            transform = self.voxelized.transform
            indices_homogeneous = np.hstack([indices, np.ones((len(indices), 1))])
            world_coords = (transform @ indices_homogeneous.T).T[:, :3]
        else:
            world_coords = indices * self.voxel_size

        plotter = self._get_plotter()
        if self.mesh:
            plotter.add_mesh(self.mesh, color='lightblue', opacity=0.2, label='Surface')
        points = pv.PolyData(world_coords)
        plotter.add_mesh(points, color='green', point_size=2, render_points_as_spheres=True, label='Voxels')
        plotter.add_legend()
        plotter.add_axes()
        self._save_or_show(plotter, "Voxelization")

    def visualize_components(self):
        """用不同颜色可视化每个组件（体素中心点云）"""
        if not self.visualize:
            return
        if not self.component_masks:
            return

        plotter = self._get_plotter()
        if self.mesh:
            plotter.add_mesh(self.mesh, color='lightblue', opacity=0.1, label='Surface')
        colors = ['red', 'green', 'blue', 'yellow', 'orange', 'purple', 'cyan', 'magenta']
        for i, mask in enumerate(self.component_masks):
            indices = np.argwhere(mask)
            if len(indices) == 0:
                continue
            if hasattr(self.voxelized, 'transform'):
                transform = self.voxelized.transform
                indices_homogeneous = np.hstack([indices, np.ones((len(indices), 1))])
                world_coords = (transform @ indices_homogeneous.T).T[:, :3]
            else:
                world_coords = indices * self.voxel_size
            points = pv.PolyData(world_coords)
            color = colors[i % len(colors)]
            plotter.add_mesh(points, color=color, point_size=3, render_points_as_spheres=True,
                             label=f"Stone {i+1}")
        plotter.add_legend()
        plotter.add_axes()
        self._save_or_show(plotter, "Components")

    def visualize_centers(self):
        """可视化所有结石中心点"""
        if not self.visualize:
            return
        if not self.stone_centers:
            return
        plotter = self._get_plotter()
        if self.mesh:
            plotter.add_mesh(self.mesh, color='lightblue', opacity=0.3, label='Surface')
        centers = np.array(self.stone_centers)
        plotter.add_points(centers, color='red', point_size=12, render_points_as_spheres=True, label='Centers')
        plotter.add_legend()
        plotter.add_axes()
        self._save_or_show(plotter, "Stone_Centers")

    def _save_or_show(self, plotter, name):
        """截图或交互显示"""
        try:
            if self.force_interactive:
                plotter.show(title=name)
            else:
                if not os.path.exists('./temp_viz'):
                    os.makedirs('./temp_viz')
                img_path = f"./temp_viz/{name}.png"
                # 先渲染再截图
                plotter.show(interactive=False, auto_close=False, window_size=[800,600])
                plotter.screenshot(img_path)
                print(f"  可视化保存到: {img_path}")
        except Exception as e:
            print(f"  可视化失败 ({name}): {e}")
        finally:
            plotter.close()

    # ========== 交互式流程（简化版） ==========
    def interactive_analysis(self):
        """
        交互式分析：逐步展示，用户按任意键继续（使用截图保存）
        """
        print("\n========== 交互式分析 ==========")
        input("按 Enter 开始...")
        print("步骤1: 显示原始STL网格")
        self.visualize_mesh()
        input("按 Enter 继续...")

        print("步骤2: 体素化")
        num_components = self.voxelize_and_segment()
        if num_components == 0:
            print("❌ 体素化/分割失败，退出")
            return
        input("按 Enter 继续...")

        print("步骤3: 显示体素化结果")
        self.visualize_voxelization()
        input("按 Enter 继续...")

        print("步骤4: 显示分割后的组件（不同颜色）")
        self.visualize_components()
        input("按 Enter 继续...")

        print("步骤5: 提取每个组件的中心点")
        self.process_components()
        input("按 Enter 继续...")

        print("步骤6: 显示最终中心点")
        self.visualize_centers()
        print("交互式分析完成。")

    def save_results(self, output_dir):
        """保存所有结果到文件"""
        os.makedirs(output_dir, exist_ok=True)
        if self.stone_centers:
            np.savetxt(os.path.join(output_dir, 'stone_centers.txt'), self.stone_centers,
                       header='x y z', comments='')
            print(f"中心点保存到: {os.path.join(output_dir, 'stone_centers.txt')}")
        import json
        data = {
            'num_stones': len(self.stone_centers),
            'centers': [c.tolist() for c in self.stone_centers],
            'radii': self.stone_radii,
            'safe_radii': self.stone_safe_radii,
            'extents': [e.tolist() for e in self.stone_extents]
        }
        with open(os.path.join(output_dir, 'stone_analysis.json'), 'w') as f:
            json.dump(data, f, indent=2)
        print(f"分析数据保存到: {os.path.join(output_dir, 'stone_analysis.json')}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Interactive step-by-step kidney stone STL analyzer")
    parser.add_argument("--stone-stl", default="RenalPelvis/KidneyStone.stl")
    parser.add_argument("--no-interactive", action="store_true",
                         help="不打开交互窗口，改为截图保存到 ./temp_viz/")
    args = parser.parse_args()

    if not os.path.exists(args.stone_stl):
        print(f"文件不存在: {args.stone_stl}")
        print("请通过 --stone-stl 指定您的结石STL文件路径")
    else:
        extractor = KidneyStoneExtractor(
            args.stone_stl,
            safe_margin=2.0,
            voxel_size=0.5,
            min_voxel_ratio=0.01,
            force_interactive=not args.no_interactive,
            visualize=True
        )
        extractor.interactive_analysis()
        # extractor.save_results("./stone_results")