import numpy as np
import trimesh
import networkx as nx
import vedo
import os
import time

# 使用 3D 骨架化算法
try:
    from skimage.morphology import skeletonize
    SKELETON_3D_AVAILABLE = True
except Exception:
    SKELETON_3D_AVAILABLE = False


class KidneySkeletonExtractor:
    """
    从肾脏STL文件直接提取骨架（不进行简化）
    """

    def __init__(self, stl_path, voxel_size=1.0):
        """
        初始化骨架提取器

        Parameters:
        -----------
        stl_path : str
            STL文件路径
        voxel_size : float
            体素大小（毫米）
        """
        self.stl_path = stl_path
        self.voxel_size = float(voxel_size)

        # 加载网格
        print(f"Loading STL file: {stl_path}")
        try:
            self.mesh = trimesh.load(stl_path)
            if isinstance(self.mesh, trimesh.Scene):
                self.mesh = trimesh.util.concatenate(self.mesh.dump())

            print(f"  Vertices: {len(self.mesh.vertices)}")
            print(f"  Faces: {len(self.mesh.faces)}")
            print(f"  Volume: {self.mesh.volume:.2f} mm³")
            print(f"  Bounds: {self.mesh.bounds}")
        except Exception as e:
            print(f"Failed to load STL: {e}")
            raise

        # 体素数据
        self.voxel_grid = None
        self.voxel_matrix = None
        self.skeleton_matrix = None

        # 骨架数据 - 原始结构，不简化
        self.skeleton_points = None  # 骨架节点坐标
        self.skeleton_edges = []  # 骨架边列表 [(node1_idx, node2_idx, length)]
        self.skeleton_graph = nx.Graph()  # 骨架图（原始连接）

        # 处理标志
        self.is_voxelized = False
        self.is_skeletonized = False

    def visualize_mesh(self, interactive=True):
        """
        可视化原始网格

        Parameters:
        -----------
        interactive : bool
            是否交互式显示
        """
        print("\nVisualizing original mesh...")

        try:
            # 创建绘图器 - 不显示坐标轴
            plotter = vedo.Plotter(axes=0, bg='white', size=(1200, 900))

            # 显示原始网格 - 透明红色
            v_mesh = vedo.Mesh([self.mesh.vertices, self.mesh.faces])
            v_mesh.color('#FF6666').alpha(0.3).lighting('glossy')
            plotter.add(v_mesh)

            if interactive:
                print("  Mesh visualization opened. Press 'q' in the visualization window to continue...")
                plotter.show(interactive=True, viewup='z')
            else:
                output_path = os.path.join('./temp_results', 'mesh_visualization.png')
                os.makedirs('./temp_results', exist_ok=True)
                plotter.show(interactive=False, zoom=1.2)
                plotter.screenshot(output_path)
                print(f"  Mesh visualization saved: {output_path}")

            plotter.close()

        except Exception as e:
            print(f"Mesh visualization failed: {e}")
            import traceback
            traceback.print_exc()

    def voxelize_mesh(self, padding=5, interactive=True):
        """
        体素化网格

        Parameters:
        -----------
        padding: int
            边界填充（体素数）
        interactive: bool
            是否交互式显示体素化结果
        """
        print(f"\nVoxelizing mesh (voxel size: {self.voxel_size}mm)")

        try:
            # 使用trimesh体素化
            voxelized = self.mesh.voxelized(pitch=self.voxel_size)
            self.voxel_grid = voxelized.fill()
            self.voxel_matrix = self.voxel_grid.matrix.astype(bool)

            print(f"  Voxel grid shape: {self.voxel_matrix.shape}")
            print(f"  Foreground voxels: {int(np.sum(self.voxel_matrix))}")

            self.is_voxelized = True

            # 交互式可视化体素化结果
            if interactive:
                self.visualize_voxelization()

            return self.voxel_matrix

        except Exception as e:
            print(f"Voxelization failed: {e}")
            raise

    def visualize_voxelization(self):
        """可视化体素化结果"""
        print("\nVisualizing voxelization results...")

        try:
            if self.voxel_grid is None:
                print("  No voxel grid available")
                return

            # 创建绘图器 - 不显示坐标轴
            plotter = vedo.Plotter(axes=0, bg='white', size=(1200, 900))

            # 获取体素网格的角点
            voxel_corners = self.voxel_grid.as_boxes()

            # 创建体素网格的可视化 - 使用红色
            v_voxels = vedo.Mesh([voxel_corners.vertices, voxel_corners.faces])
            v_voxels.color('#FF6666').alpha(0.5).lighting('ambient')
            plotter.add(v_voxels)

            # 可选：显示原始网格更透明的红色
            v_mesh = vedo.Mesh([self.mesh.vertices, self.mesh.faces])
            v_mesh.color('#FF6666').alpha(0.1).wireframe()
            plotter.add(v_mesh)

            print("  Voxelization visualization opened. Press 'q' in the visualization window to continue...")
            plotter.show(interactive=True, viewup='z')
            plotter.close()

        except Exception as e:
            print(f"Voxelization visualization failed: {e}")
            import traceback
            traceback.print_exc()

    def extract_skeleton(self, method='skeletonize', interactive=True):
        """
        提取3D骨架（不进行简化）

        Parameters:
        -----------
        method : str
            骨架提取方法，默认'skeletonize'
        interactive : bool
            是否交互式显示骨架提取结果
        """
        print(f"\nExtracting 3D skeleton")

        if not self.is_voxelized:
            print("Please call voxelize_mesh() first")
            return None

        if not SKELETON_3D_AVAILABLE:
            print("scikit-image skeletonize is not available")
            print("Please install: pip install -U scikit-image")
            return None

        try:
            start_time = time.time()

            # 提取骨架
            print(f"  Using {method} method...")
            self.skeleton_matrix = skeletonize(self.voxel_matrix.astype(np.uint8))

            dt = time.time() - start_time
            print(f"  Skeleton extraction completed, time: {dt:.2f} s")
            print(f"  Skeleton voxels: {int(np.sum(self.skeleton_matrix))}")

            # 提取骨架点坐标
            self._extract_skeleton_points()

            # 构建骨架连接（原始连接，不简化）
            self._build_raw_skeleton()

            self.is_skeletonized = True

            # 交互式可视化骨架提取结果
            if interactive:
                self.visualize_skeleton_extraction()

            return self.skeleton_points

        except Exception as e:
            print(f"Skeleton extraction failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def visualize_skeleton_extraction(self):
        """可视化骨架提取结果"""
        print("\nVisualizing skeleton extraction results...")

        try:
            if self.skeleton_matrix is None:
                print("  No skeleton matrix available")
                return

            # 创建绘图器 - 不显示坐标轴
            plotter = vedo.Plotter(axes=0, bg='white', size=(1200, 900))

            # 1. 显示原始网格（半透明红色）
            v_mesh = vedo.Mesh([self.mesh.vertices, self.mesh.faces])
            v_mesh.color('#FF6666').alpha(0.2).lighting('ambient')
            plotter.add(v_mesh)

            # 2. 显示骨架体素
            # 获取骨架体素坐标
            skeleton_indices = np.argwhere(self.skeleton_matrix)
            if len(skeleton_indices) > 0:
                # 转换为世界坐标
                if hasattr(self.voxel_grid, 'transform'):
                    transform = self.voxel_grid.transform
                    indices_homogeneous = np.hstack([skeleton_indices, np.ones((len(skeleton_indices), 1))])
                    skeleton_points = (transform @ indices_homogeneous.T).T[:, :3]
                else:
                    skeleton_points = skeleton_indices * self.voxel_size

                # 显示骨架点 - 使用绿色
                v_skeleton_points = vedo.Points(skeleton_points, r=5, c='darkgreen', alpha=0.8)
                plotter.add(v_skeleton_points)

            # 3. 显示骨架边
            if self.skeleton_edges and self.skeleton_points is not None:
                # 显示部分边（避免过多）
                max_edges_to_show = min(200, len(self.skeleton_edges))
                step = max(1, len(self.skeleton_edges) // max_edges_to_show)

                for i, (node1_idx, node2_idx, distance) in enumerate(self.skeleton_edges[::step]):
                    if node1_idx < len(self.skeleton_points) and node2_idx < len(self.skeleton_points):
                        p1 = self.skeleton_points[node1_idx]
                        p2 = self.skeleton_points[node2_idx]
                        line = vedo.Line(p1, p2, lw=2, c='blue', alpha=0.5)
                        plotter.add(line)

            print("  Skeleton extraction visualization opened. Press 'q' in the visualization window to continue...")
            plotter.show(interactive=True, viewup='z')
            plotter.close()

        except Exception as e:
            print(f"Skeleton extraction visualization failed: {e}")
            import traceback
            traceback.print_exc()

    def _extract_skeleton_points(self):
        """从骨架矩阵提取骨架点坐标"""
        if self.skeleton_matrix is None:
            return None

        # 获取骨架体素索引
        skeleton_indices = np.argwhere(self.skeleton_matrix)

        if len(skeleton_indices) == 0:
            print("No skeleton voxels found")
            return None

        print(f"  Skeleton voxels: {len(skeleton_indices)}")

        # 使用变换矩阵获取世界坐标
        if hasattr(self.voxel_grid, 'transform'):
            transform = self.voxel_grid.transform

            # 骨架体素索引转换为齐次坐标
            indices_homogeneous = np.hstack([skeleton_indices, np.ones((len(skeleton_indices), 1))])

            # 应用变换矩阵：将体素索引转换为世界坐标
            self.skeleton_points = (transform @ indices_homogeneous.T).T[:, :3]
        else:
            # 简单转换：体素坐标 × 体素大小
            self.skeleton_points = skeleton_indices * self.voxel_size

        print(f"  Skeleton points: {len(self.skeleton_points)}")
        return self.skeleton_points

    def _build_raw_skeleton(self):
        """构建原始骨架连接（不简化）"""
        if self.skeleton_points is None or len(self.skeleton_points) == 0:
            return

        print(f"\nBuilding raw skeleton connections")

        # 清空图
        self.skeleton_graph.clear()
        self.skeleton_edges = []

        # 添加所有节点
        for i, point in enumerate(self.skeleton_points):
            self.skeleton_graph.add_node(i, pos=point)

        # 基于26邻域连接骨架点
        print("  Connecting skeleton points using 26-neighborhood...")

        # 获取骨架矩阵尺寸
        shape = self.skeleton_matrix.shape

        # 26邻域偏移
        offsets = []
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                for dz in [-1, 0, 1]:
                    if dx == 0 and dy == 0 and dz == 0:
                        continue
                    offsets.append((dx, dy, dz))

        # 创建体素索引到节点ID的映射
        voxel_to_node = {}
        for idx in np.argwhere(self.skeleton_matrix):
            voxel_to_node[tuple(idx)] = len(voxel_to_node)

        # 连接相邻体素
        edges_added = set()

        for idx in np.argwhere(self.skeleton_matrix):
            i, j, k = idx
            node_id = voxel_to_node[tuple(idx)]

            for dx, dy, dz in offsets:
                ni, nj, nk = i + dx, j + dy, k + dz

                # 检查边界
                if (0 <= ni < shape[0] and 0 <= nj < shape[1] and 0 <= nk < shape[2]):
                    if self.skeleton_matrix[ni, nj, nk]:
                        neighbor_id = voxel_to_node[(ni, nj, nk)]

                        # 确保边只添加一次
                        edge = tuple(sorted((node_id, neighbor_id)))
                        if edge not in edges_added:
                            # 计算距离
                            p1 = self.skeleton_points[node_id]
                            p2 = self.skeleton_points[neighbor_id]
                            distance = np.linalg.norm(p1 - p2)

                            # 添加到图
                            self.skeleton_graph.add_edge(node_id, neighbor_id, weight=distance)

                            # 添加到边列表
                            self.skeleton_edges.append((node_id, neighbor_id, distance))

                            edges_added.add(edge)

        print(f"  Nodes: {self.skeleton_graph.number_of_nodes()}")
        print(f"  Edges: {self.skeleton_graph.number_of_edges()}")

        # 检查连通性
        if nx.is_connected(self.skeleton_graph):
            print("  Skeleton graph is connected")
        else:
            components = list(nx.connected_components(self.skeleton_graph))
            print(f"  Warning: Skeleton graph is not connected, {len(components)} components")

            # 找到最大连通分量
            largest_component = max(components, key=len)
            print(f"  Largest component size: {len(largest_component)}")

    def get_skeleton_info(self):
        """获取骨架信息"""
        if not self.is_skeletonized:
            return None

        info = {
            'points_count': len(self.skeleton_points) if self.skeleton_points is not None else 0,
            'edges_count': len(self.skeleton_edges),
            'graph_nodes': self.skeleton_graph.number_of_nodes(),
            'graph_edges': self.skeleton_graph.number_of_edges(),
            'is_connected': nx.is_connected(self.skeleton_graph),
            'voxel_size': self.voxel_size
        }

        # 计算连通分量
        if not info['is_connected']:
            components = list(nx.connected_components(self.skeleton_graph))
            info['components_count'] = len(components)
            info['largest_component_size'] = max(len(c) for c in components)

        return info

    def save_skeleton_data(self, output_dir='./result/4/skeleton_results'):
        """
        保存骨架数据

        Parameters:
        -----------
        output_dir : str
            输出目录
        """
        if not self.is_skeletonized:
            print("Please extract skeleton first")
            return

        os.makedirs(output_dir, exist_ok=True)

        print(f"\nSaving skeleton data to: {output_dir}")

        try:
            # 1. 保存为NPZ格式
            npz_path = os.path.join(output_dir, 'kidney_skeleton_raw.npz')
            np.savez_compressed(
                npz_path,
                skeleton_points=self.skeleton_points,
                skeleton_edges=np.array(self.skeleton_edges, dtype=object),
                voxel_size=np.array(self.voxel_size)
            )
            print(f"  NPZ format: {npz_path}")

            # 2. 保存为JSON格式
            import json
            json_path = os.path.join(output_dir, 'kidney_skeleton_raw.json')

            # 准备JSON数据
            json_data = {
                'metadata': {
                    'stl_file': self.stl_path,
                    'voxel_size': self.voxel_size,
                    'points_count': len(self.skeleton_points),
                    'edges_count': len(self.skeleton_edges),
                    'extraction_time': time.strftime('%Y-%m-%d %H:%M:%S')
                },
                'points': self.skeleton_points.tolist() if self.skeleton_points is not None else [],
                'edges': []
            }

            # 转换边数据
            for node1_idx, node2_idx, distance in self.skeleton_edges:
                json_data['edges'].append({
                    'source': int(node1_idx),
                    'target': int(node2_idx),
                    'distance': float(distance)
                })

            # 保存JSON
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
            print(f"  JSON format: {json_path}")

            # 3. 保存为TXT格式（便于查看）
            txt_path = os.path.join(output_dir, 'skeleton_summary.txt')
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(f"Kidney Skeleton Extraction Results\n")
                f.write(f"=" * 50 + "\n\n")
                f.write(f"STL file: {self.stl_path}\n")
                f.write(f"Voxel size: {self.voxel_size} mm\n")
                f.write(f"Skeleton points: {len(self.skeleton_points)}\n")
                f.write(f"Skeleton edges: {len(self.skeleton_edges)}\n")
                f.write(f"Extraction time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

                f.write(f"First 10 skeleton points:\n")
                for i, point in enumerate(self.skeleton_points[:10]):
                    f.write(f"  Point {i}: ({point[0]:.2f}, {point[1]:.2f}, {point[2]:.2f})\n")

                f.write(f"\nFirst 10 skeleton edges:\n")
                for i, (u, v, d) in enumerate(self.skeleton_edges[:10]):
                    f.write(f"  Edge {i}: Node {u} - Node {v}, Distance: {d:.2f} mm\n")

            print(f"  Text summary: {txt_path}")

            return npz_path, json_path

        except Exception as e:
            print(f"Failed to save skeleton data: {e}")
            return None, None

    def visualize_skeleton(self, output_dir='./skeleton_results'):
        """
        可视化最终骨架结果

        Parameters:
        -----------
        output_dir : str
            输出目录
        """
        if not self.is_skeletonized:
            print("Please extract skeleton first")
            return

        os.makedirs(output_dir, exist_ok=True)

        print(f"\nVisualizing final skeleton results")

        try:
            # 创建绘图器 - 不显示坐标轴
            plotter = vedo.Plotter(axes=0, bg='white', size=(1200, 900))

            # 1. 显示原始网格（半透明红色）
            v_mesh = vedo.Mesh([self.mesh.vertices, self.mesh.faces])
            v_mesh.color('#FF6666').alpha(0.2).lighting('ambient')
            plotter.add(v_mesh)

            # 2. 显示骨架点
            if self.skeleton_points is not None and len(self.skeleton_points) > 0:
                # 显示所有骨架点
                all_points = vedo.Points(self.skeleton_points, r=4, c='darkgreen', alpha=0.8)
                plotter.add(all_points)

                # 3. 显示骨架边（原始连接）
                if self.skeleton_edges:
                    # 使用蓝色显示边
                    max_edges_to_show = min(200, len(self.skeleton_edges))
                    step = max(1, len(self.skeleton_edges) // max_edges_to_show)

                    for i, (node1_idx, node2_idx, distance) in enumerate(self.skeleton_edges[::step]):
                        if node1_idx < len(self.skeleton_points) and node2_idx < len(self.skeleton_points):
                            p1 = self.skeleton_points[node1_idx]
                            p2 = self.skeleton_points[node2_idx]
                            line = vedo.Line(p1, p2, lw=2, c='blue', alpha=0.6)
                            plotter.add(line)

            # 4. 保存图像
            output_path = os.path.join(output_dir, 'kidney_raw_skeleton.png')

            print("  Final skeleton visualization opened. Press 'q' in the visualization window to exit...")
            plotter.show(interactive=True, zoom=1.2, viewup='z')
            plotter.screenshot(output_path)
            plotter.close()

            print(f"  Skeleton visualization saved: {output_path}")

            # 5. 生成骨架点云可视化
            self._visualize_point_cloud(output_dir)

        except Exception as e:
            print(f"Visualization failed: {e}")
            import traceback
            traceback.print_exc()

    def _visualize_point_cloud(self, output_dir):
        """可视化骨架点云（使用matplotlib）"""
        try:
            if self.skeleton_points is None or len(self.skeleton_points) == 0:
                return

            # 设置matplotlib不使用中文字体
            import matplotlib.pyplot as plt
            plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'sans-serif']
            plt.rcParams['axes.unicode_minus'] = False

            from mpl_toolkits.mplot3d import Axes3D

            print("  Generating skeleton point cloud visualization...")

            fig = plt.figure(figsize=(12, 10))
            ax = fig.add_subplot(111, projection='3d')

            # 绘制骨架点
            ax.scatter(self.skeleton_points[:, 0],
                      self.skeleton_points[:, 1],
                      self.skeleton_points[:, 2],
                      c='darkgreen', s=2, alpha=0.6)

            # 绘制部分边
            if self.skeleton_edges:
                # 随机选择部分边显示
                import random
                max_edges = min(100, len(self.skeleton_edges))
                sample_edges = random.sample(self.skeleton_edges, max_edges)

                for u, v, dist in sample_edges:
                    if u < len(self.skeleton_points) and v < len(self.skeleton_points):
                        p1 = self.skeleton_points[u]
                        p2 = self.skeleton_points[v]
                        ax.plot([p1[0], p2[0]],
                               [p1[1], p2[1]],
                               [p1[2], p2[2]],
                               'blue', alpha=0.2, linewidth=0.5)

            ax.set_xlabel('X (mm)')
            ax.set_ylabel('Y (mm)')
            ax.set_zlabel('Z (mm)')
            ax.set_title(f'Kidney Skeleton Point Cloud ({len(self.skeleton_points)} points)')

            # 调整视角
            ax.view_init(elev=20, azim=45)

            plt.tight_layout()
            output_path = os.path.join(output_dir, 'skeleton_point_cloud.png')
            plt.savefig(output_path, dpi=150, bbox_inches='tight')
            plt.close()

            print(f"  Point cloud visualization saved: {output_path}")

        except Exception as e:
            print(f"Point cloud visualization failed: {e}")


def extract_skeleton_from_stl(stl_path, voxel_size=1.0, output_dir='./result/4/skeleton_results',
                             visualize=True, interactive=True):
    """
    从STL文件提取骨架的便捷函数

    Parameters:
    -----------
    stl_path : str
        STL文件路径
    voxel_size : float
        体素大小（毫米）
    output_dir : str
        输出目录
    visualize : bool
        是否可视化结果
    interactive : bool
        是否交互式显示各阶段结果

    Returns:
    --------
    skeleton_points, skeleton_edges : tuple
        骨架点和边
    """
    print("=" * 60)
    print("Kidney Skeleton Extraction - Interactive Mode")
    print("=" * 60)

    # 检查文件
    if not os.path.exists(stl_path):
        print(f"File not found: {stl_path}")
        return None, None

    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)

    # 创建提取器
    extractor = KidneySkeletonExtractor(stl_path, voxel_size=voxel_size)

    try:
        # 阶段1: 显示原始网格
        if interactive:
            print("\n[STAGE 1] Original Mesh Visualization")
            extractor.visualize_mesh(interactive=interactive)

        # 阶段2: 体素化
        print("\n[STAGE 2] Mesh Voxelization")
        voxel_matrix = extractor.voxelize_mesh(interactive=interactive)

        if voxel_matrix is None:
            print("Voxelization failed")
            return None, None

        # 阶段3: 提取骨架
        print("\n[STAGE 3] Skeleton Extraction")
        skeleton_points = extractor.extract_skeleton(interactive=interactive)

        if skeleton_points is None:
            print("Skeleton extraction failed")
            return None, None

        # 获取骨架信息
        info = extractor.get_skeleton_info()
        if info:
            print(f"\nSkeleton information:")
            print(f"  Skeleton points: {info['points_count']}")
            print(f"  Skeleton edges: {info['edges_count']}")
            print(f"  Is connected: {info['is_connected']}")
            if not info['is_connected']:
                print(f"  Connected components: {info.get('components_count', 1)}")
                print(f"  Largest component: {info.get('largest_component_size', 0)}")

        # 保存数据
        print("\n[STAGE 4] Saving Skeleton Data")
        extractor.save_skeleton_data(output_dir)

        # 最终可视化
        if visualize:
            print("\n[STAGE 5] Final Visualization")
            extractor.visualize_skeleton(output_dir)

        print("\n" + "=" * 60)
        print("Skeleton extraction completed!")
        print(f"Results saved in: {output_dir}")
        print("=" * 60)

        return extractor.skeleton_points, extractor.skeleton_edges

    except Exception as e:
        print(f"Skeleton extraction failed: {e}")
        import traceback
        traceback.print_exc()
        return None, None


def main(stl_path, voxel_size, output_dir, visualize, interactive):
    """主函数"""
    # 从STL提取骨架
    skeleton_points, skeleton_edges = extract_skeleton_from_stl(
        stl_path=stl_path,
        voxel_size=voxel_size,
        output_dir=output_dir,
        visualize=visualize,
        interactive=interactive
    )

    # 输出骨架数据供后续使用
    if skeleton_points is not None:
        print(f"\nSkeleton data ready for other modules:")
        print(f"  Skeleton points shape: {skeleton_points.shape}")
        print(f"  Skeleton edges count: {len(skeleton_edges)}")

        # 保存为独立的.npy文件便于导入
        np.save(os.path.join(output_dir, 'skeleton_points.npy'), skeleton_points)
        np.save(os.path.join(output_dir, 'skeleton_edges.npy'), skeleton_edges, allow_pickle=True)
        print(f"  Saved as .npy format for easy import")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Extract a 3D skeleton from a kidney STL")
    parser.add_argument("--case-id", default="1", help="Case number; determines result/<case-id>/...")
    parser.add_argument("--kidney-stl", default="RenalPelvis/RenalPelvis.stl")
    parser.add_argument("--voxel-size", type=float, default=1.0)
    parser.add_argument("--output-dir", default=None,
                         help="默认: result/<case-id>/skeleton_results")
    parser.add_argument("--visualize", action="store_true", default=True)
    parser.add_argument("--interactive", action="store_true", default=False)
    args = parser.parse_args()

    main(
        stl_path=args.kidney_stl,
        voxel_size=args.voxel_size,
        output_dir=args.output_dir or f"result/{args.case_id}/skeleton_results",
        visualize=args.visualize,
        interactive=args.interactive,
    )