"""
肾脏路径规划拓扑图模块
功能：加载骨架数据，自动识别尿道口（Y最小点），从结石STL中提取内部中心点，
      构建拓扑图，计算从尿道口到各结石的最短路径，并支持可视化与数据导出。
"""

import numpy as np
import networkx as nx
import pandas as pd
import vedo
import os
import json
from scipy.spatial import KDTree
import time

from kidney_stone_extractor import KidneyStoneExtractor


# ======================= 肾脏路径规划拓扑图类 ========================
class KidneyPathTopology:
    """
    肾脏路径规划拓扑图类
    结合树状骨架、尿道口和肾结石位置
    """

    def __init__(self, skeleton_points, skeleton_edges, urethra_point, stone_points):
        """
        初始化拓扑图

        参数:
        -----------
        skeleton_points: numpy数组 (N, 3)
            骨架节点坐标
        skeleton_edges: 列表 [(node1_idx, node2_idx, distance), ...]
            骨架边
        urethra_point: numpy数组 (3,)
            尿道口坐标
        stone_points: numpy数组 (M, 3)
            肾结石坐标列表
        """
        self.skeleton_points = skeleton_points
        self.skeleton_edges = skeleton_edges
        self.urethra_point = urethra_point
        self.stone_points = stone_points

        # 拓扑图
        self.graph = nx.Graph()

        # 关键点映射
        self.node_types = {}  # 节点类型: 'skeleton', 'urethra', 'stone'
        self.node_positions = {}  # 节点ID -> 坐标

        # 路径信息
        self.paths_to_stones = {}  # 结石ID -> 路径节点列表
        self.path_lengths = {}  # 结石ID -> 路径长度

        # 构建拓扑图
        self._build_topology_graph()

        # 检查并修复骨架连通性
        self._check_and_fix_connectivity()

        # 连接尿道口到骨架
        self._connect_urethra_to_skeleton()

        # 连接结石到骨架
        self._connect_stones_to_skeleton()

        # 分析路径
        self._analyze_paths()

    def _build_topology_graph(self):
        """构建优化后的骨架拓扑图"""
        print("构建优化骨架拓扑图...")

        # 清空图
        self.graph.clear()

        # 1. 直接构建简化骨架
        print("1. 构建简化骨架...")

        # 将骨架点转换为数组以便处理
        skeleton_array = np.array(self.skeleton_points)

        # 创建一个简化版的骨架
        simplified_nodes, simplified_edges = self._simplify_skeleton_direct(
            skeleton_array,
            self.skeleton_edges
        )

        # 2. 添加简化后的骨架节点
        skeleton_node_ids = {}
        for i, (node_id, point) in enumerate(simplified_nodes):
            self.graph.add_node(node_id, pos=point, type='skeleton', original_id=i, simplified=True)
            self.node_types[node_id] = 'skeleton'
            self.node_positions[node_id] = point
            skeleton_node_ids[i] = node_id

        # 3. 添加简化后的骨架边
        for edge in simplified_edges:
            if len(edge) == 3:
                node1_idx, node2_idx, distance = edge
            else:
                # 计算距离
                node1_idx, node2_idx = edge[:2]
                p1 = simplified_nodes[node1_idx][1]
                p2 = simplified_nodes[node2_idx][1]
                distance = np.linalg.norm(p1 - p2)

            node1_id = skeleton_node_ids.get(node1_idx)
            node2_id = skeleton_node_ids.get(node2_idx)

            if node1_id and node2_id:
                self.graph.add_edge(node1_id, node2_id,
                                    weight=distance,
                                    distance=distance,
                                    type='skeleton',
                                    simplified=True)

        print(f"简化骨架节点数: {len(simplified_nodes)}")
        print(f"简化骨架边数: {len(simplified_edges)}")

    def _simplify_skeleton_direct(self, skeleton_points, skeleton_edges):
        """
        直接简化骨架
        1. 首先剪除没有结石的无关端点路径
        2. 然后简化非分叉点（度数为2的节点）

        参数:
        -----------
        skeleton_points: numpy数组 (N, 3)
            原始骨架点
        skeleton_edges: 列表
            原始骨架边

        返回:
        -----------
        simplified_nodes: 列表 [(node_id, point), ...]
            简化后的节点
        simplified_edges: 列表
            简化后的边
        """
        print("  剪除无关端点路径并简化非分叉点...")

        # 1. 构建原始图
        G_original = nx.Graph()

        # 添加节点
        for i, point in enumerate(skeleton_points):
            G_original.add_node(i, pos=point)

        # 添加边
        for edge in skeleton_edges:
            if len(edge) == 3:
                u, v, dist = edge
            else:
                u, v = edge[:2]
                dist = np.linalg.norm(skeleton_points[u] - skeleton_points[v])
            G_original.add_edge(u, v, weight=dist)

        # 2. 找到所有结石在骨架上的连接点
        stone_connection_nodes = set()

        # 计算每个骨架节点到结石的平均距离
        if len(self.stone_points) > 0:
            print("  识别潜在的结石连接点...")
            stone_array = np.array(self.stone_points)

            for stone_point in self.stone_points:
                # 找到离这个结石最近的骨架节点
                min_dist = float('inf')
                nearest_node = None

                for node in G_original.nodes():
                    node_pos = G_original.nodes[node]['pos']
                    dist = np.linalg.norm(stone_point - node_pos)
                    if dist < min_dist:
                        min_dist = dist
                        nearest_node = node

                if nearest_node is not None:
                    stone_connection_nodes.add(nearest_node)
                    print(f"    结石可能连接到骨架节点 {nearest_node}, 距离: {min_dist:.2f}")

        # 3. 剪除没有结石的无关端点路径
        print("  剪除无关端点路径...")
        G_pruned = G_original.copy()
        pruned_count = 0

        # 找到所有端点（度数为1的节点）
        endpoints = [node for node in G_pruned.nodes() if G_pruned.degree(node) == 1]

        # 创建尿道口连接点集合
        urethra_connection_node = None

        # 找到离尿道口最近的骨架节点
        if self.urethra_point is not None:
            min_dist = float('inf')
            for node in G_pruned.nodes():
                node_pos = G_pruned.nodes[node]['pos']
                dist = np.linalg.norm(self.urethra_point - node_pos)
                if dist < min_dist:
                    min_dist = dist
                    urethra_connection_node = node

            if urethra_connection_node is not None:
                print(f"  尿道口可能连接到骨架节点 {urethra_connection_node}, 距离: {min_dist:.2f}")

        # 开始剪枝：反复移除无关端点
        changed = True
        while changed:
            changed = False
            endpoints = [node for node in G_pruned.nodes() if G_pruned.degree(node) == 1]

            for endpoint in endpoints:
                # 判断这个端点是否重要
                is_important = False

                # 检查是否连接到结石
                if endpoint in stone_connection_nodes:
                    is_important = True

                # 检查是否连接到尿道口
                if endpoint == urethra_connection_node:
                    is_important = True

                # 如果不是重要端点，删除它
                if not is_important:
                    # 获取它的邻居
                    neighbors = list(G_pruned.neighbors(endpoint))

                    # 删除这个端点
                    G_pruned.remove_node(endpoint)
                    pruned_count += 1
                    changed = True

                    # 如果邻居现在变成了端点，会在下一轮处理
                    for neighbor in neighbors:
                        if G_pruned.degree(neighbor) == 1:
                            # 这个邻居现在是新的端点，会在下一轮检查
                            pass

        print(f"  剪除了 {pruned_count} 个无关端点")
        print(f"  剪枝后节点数: {G_pruned.number_of_nodes()}")

        # 如果剪枝后图不连通，只保留最大的连通分量
        if not nx.is_connected(G_pruned):
            print("  剪枝后图不连通，保留最大连通分量...")
            connected_components = list(nx.connected_components(G_pruned))
            largest_component = max(connected_components, key=len)

            # 创建只包含最大连通分量的图
            G_temp = G_pruned.subgraph(largest_component).copy()
            G_pruned = G_temp

            print(f"  保留最大连通分量，节点数: {G_pruned.number_of_nodes()}")

        # 4. 简化非分叉点（度数为2的节点）
        print("  简化非分叉点...")

        # 识别关键节点（分叉点、端点）
        critical_nodes = set()

        # 分叉点（度数≥3）
        for node in G_pruned.nodes():
            if G_pruned.degree(node) >= 3:
                critical_nodes.add(node)

        # 端点（度数为1）
        for node in G_pruned.nodes():
            if G_pruned.degree(node) == 1:
                critical_nodes.add(node)

        print(f"  关键节点数: {len(critical_nodes)}")

        # 打印分叉点信息（调试用）
        bifurcation_nodes = [node for node in G_pruned.nodes() if G_pruned.degree(node) >= 3]
        print(f"  分叉点(度数≥3): {len(bifurcation_nodes)}个")
        for i, node in enumerate(bifurcation_nodes[:5]):  # 打印前5个
            pos = G_pruned.nodes[node]['pos']
            print(f"    分叉点 {node}: 位置({pos[0]:.1f}, {pos[1]:.1f}, {pos[2]:.1f}), 度数{G_pruned.degree(node)}")

        if len(critical_nodes) < 2:
            print("  关键节点太少，返回剪枝后的骨架")
            return self._convert_pruned_to_simplified(G_pruned)

        # 找到所有关键节点之间的路径
        critical_list = sorted(list(critical_nodes))
        critical_paths = []

        for i in range(len(critical_list)):
            for j in range(i + 1, len(critical_list)):
                node1 = critical_list[i]
                node2 = critical_list[j]

                try:
                    # 找到两个关键节点之间的最短路径
                    path = nx.shortest_path(G_pruned, node1, node2)

                    # 检查路径上是否只有端点是关键节点，中间都是非关键节点（度数为2）
                    intermediate_nodes = path[1:-1]
                    if intermediate_nodes and all(G_pruned.degree(node) == 2 for node in intermediate_nodes):
                        # 这是一个可简化的路径段
                        critical_paths.append((node1, node2, path))

                except nx.NetworkXNoPath:
                    continue

        print(f"  找到可简化路径段: {len(critical_paths)}个")

        if not critical_paths:
            print("  没有找到可简化路径段，返回剪枝后的骨架")
            return self._convert_pruned_to_simplified(G_pruned)

        # 5. 简化每条路径段
        simplified_segments = {}

        for node1, node2, path in critical_paths:
            # 获取路径上的所有点（关键节点+中间点）
            path_points = [G_pruned.nodes[idx]['pos'] for idx in path]

            # 修复: 只对中间点进行简化，关键节点不参与
            # 分离关键节点和中间点
            start_point = path_points[0]  # 关键节点1（位置不变）
            end_point = path_points[-1]   # 关键节点2（位置不变）
            middle_points = path_points[1:-1]  # 中间点（可简化）

            if len(middle_points) <= 1:
                # 中间点太少，直接保留
                simplified_segment = path_points
            else:
                # 只简化中间点
                if len(middle_points) > 2:
                    # 修复: 确保DP算法不会移动起点和终点
                    # 对中间点进行简化
                    simplified_middle = self._douglas_peucker_simplify(middle_points, epsilon=6.0)
                    # 重新组合：起点（不变） + 简化后的中间点 + 终点（不变）
                    simplified_segment = [start_point] + simplified_middle + [end_point]
                else:
                    simplified_segment = path_points

            # 调试输出
            if len(path_points) > 10:
                print(f"    路径 {node1}->{node2}: 原始{len(path_points)}点 -> 简化后{len(simplified_segment)}点")

            # 存储简化后的路径
            simplified_segments[(node1, node2)] = {
                'original_path': path,
                'simplified_points': simplified_segment,  # 包含不变的关键节点
                'start_node': node1,
                'end_node': node2
            }

        # 6. 创建简化节点列表
        simplified_nodes = []
        node_id_counter = 0
        critical_node_mapping = {}  # 原始关键节点ID -> 简化节点索引

        # 首先添加所有关键节点（分叉点和端点）- 这些位置严格保持不变
        for critical_node in critical_list:
            node_id = f"skeleton_critical_{critical_node}"
            pos = G_pruned.nodes[critical_node]['pos']  # 直接使用原始位置
            simplified_nodes.append((node_id, pos))
            critical_node_mapping[critical_node] = node_id_counter
            node_id_counter += 1

        print(f"  添加关键节点到简化列表: {len(critical_nodes)}个")
        print(f"  分叉点位置示例（验证不变）:")
        for node in bifurcation_nodes[:3]:
            pos = G_pruned.nodes[node]['pos']
            simplified_pos = simplified_nodes[critical_node_mapping[node]][1]
            diff = np.linalg.norm(pos - simplified_pos)
            print(f"    节点{node}: 原始位置{pos}, 简化后位置{simplified_pos}, 差异{diff:.6f}")

        # 为每条简化路径段添加中间简化点（不包括起点和终点）
        segment_points_mapping = {}
        segment_id = 0

        for (node1, node2), segment_info in simplified_segments.items():
            simplified_points = segment_info['simplified_points']

            # 添加简化后的中间点（不包括起点和终点）
            segment_points = []
            for point in simplified_points[1:-1]:
                node_id = f"skeleton_simplified_{node_id_counter}"
                simplified_nodes.append((node_id, point))
                segment_points.append(node_id_counter)
                node_id_counter += 1

            if segment_points:
                segment_points_mapping[segment_id] = {
                    'start_idx': critical_node_mapping[node1],
                    'end_idx': critical_node_mapping[node2],
                    'middle_indices': segment_points
                }
                segment_id += 1

        # 7. 创建简化边
        simplified_edges = []
        added_edges = set()

        # 首先，为每条简化路径段创建边
        for segment_id, segment_info in segment_points_mapping.items():
            start_idx = segment_info['start_idx']
            end_idx = segment_info['end_idx']
            middle_indices = segment_info['middle_indices']

            # 连接起点到第一个中间点
            if middle_indices:
                # 连接起点到第一个中间点
                p1 = simplified_nodes[start_idx][1]
                p2 = simplified_nodes[middle_indices[0]][1]
                dist = np.linalg.norm(p1 - p2)
                edge_key = (min(start_idx, middle_indices[0]), max(start_idx, middle_indices[0]))
                if edge_key not in added_edges:
                    simplified_edges.append((start_idx, middle_indices[0], dist))
                    added_edges.add(edge_key)

                # 连接中间点之间
                for i in range(len(middle_indices) - 1):
                    idx1 = middle_indices[i]
                    idx2 = middle_indices[i + 1]
                    p1 = simplified_nodes[idx1][1]
                    p2 = simplified_nodes[idx2][1]
                    dist = np.linalg.norm(p1 - p2)
                    edge_key = (min(idx1, idx2), max(idx1, idx2))
                    if edge_key not in added_edges:
                        simplified_edges.append((idx1, idx2, dist))
                        added_edges.add(edge_key)

                # 连接最后一个中间点到终点
                last_middle = middle_indices[-1]
                p1 = simplified_nodes[last_middle][1]
                p2 = simplified_nodes[end_idx][1]
                dist = np.linalg.norm(p1 - p2)
                edge_key = (min(last_middle, end_idx), max(last_middle, end_idx))
                if edge_key not in added_edges:
                    simplified_edges.append((last_middle, end_idx, dist))
                    added_edges.add(edge_key)
            else:
                # 没有中间点，直接连接起点和终点
                p1 = simplified_nodes[start_idx][1]
                p2 = simplified_nodes[end_idx][1]
                dist = np.linalg.norm(p1 - p2)
                edge_key = (min(start_idx, end_idx), max(start_idx, end_idx))
                if edge_key not in added_edges:
                    simplified_edges.append((start_idx, end_idx, dist))
                    added_edges.add(edge_key)

        # 然后，添加剪枝后图中关键节点之间的直接连接（如果还没有添加）
        for u, v in G_pruned.edges():
            if u in critical_node_mapping and v in critical_node_mapping:
                idx1 = critical_node_mapping[u]
                idx2 = critical_node_mapping[v]
                edge_key = (min(idx1, idx2), max(idx1, idx2))

                # 如果这条边还没有添加（可能是被简化路径替代了）
                if edge_key not in added_edges:
                    p1 = simplified_nodes[idx1][1]
                    p2 = simplified_nodes[idx2][1]
                    dist = np.linalg.norm(p1 - p2)
                    simplified_edges.append((idx1, idx2, dist))
                    added_edges.add(edge_key)

        print(f"  简化后节点数: {len(simplified_nodes)}")
        print(f"  简化后边数: {len(simplified_edges)}")

        return simplified_nodes, simplified_edges

    def _douglas_peucker_simplify(self, points, epsilon):
        """
        Douglas-Peucker算法简化点集

        参数:
        -----------
        points: 点列表，每个点是一个numpy数组 (3,)
        epsilon: 容差阈值

        返回:
        -----------
        简化后的点列表
        """
        if len(points) <= 2:
            return points

        # 找到离首尾点连线最远的点
        start = points[0]
        end = points[-1]

        max_distance = 0
        max_index = 0

        # 计算点到直线的距离（3D空间）
        for i in range(1, len(points) - 1):
            distance = self._point_to_line_distance_3d(points[i], start, end)
            if distance > max_distance:
                max_distance = distance
                max_index = i

        # 如果最大距离大于容差，递归简化
        if max_distance > epsilon:
            # 递归简化左右两部分
            left_part = self._douglas_peucker_simplify(points[:max_index + 1], epsilon)
            right_part = self._douglas_peucker_simplify(points[max_index:], epsilon)

            # 合并结果（去掉重复的中间点）
            return left_part[:-1] + right_part
        else:
            # 直接返回首尾点
            return [points[0], points[-1]]

    def _point_to_line_distance_3d(self, point, line_start, line_end):
        """
        计算3D空间中点到直线的距离

        参数:
        -----------
        point: 目标点 (3,)
        line_start: 直线起点 (3,)
        line_end: 直线终点 (3,)

        返回:
        -----------
        点到直线的距离
        """
        # 直线向量
        line_vec = line_end - line_start
        line_length = np.linalg.norm(line_vec)

        if line_length == 0:
            # 起点终点重合，返回点到起点的距离
            return np.linalg.norm(point - line_start)

        # 单位向量
        line_unit_vec = line_vec / line_length

        # 从起点到点的向量
        point_vec = point - line_start

        # 点在直线上的投影长度
        projection_length = np.dot(point_vec, line_unit_vec)

        if projection_length < 0:
            # 投影在起点之前，返回点到起点的距离
            return np.linalg.norm(point - line_start)
        elif projection_length > line_length:
            # 投影在终点之后，返回点到终点的距离
            return np.linalg.norm(point - line_end)
        else:
            # 计算垂足
            closest_point = line_start + projection_length * line_unit_vec
            # 返回点到垂足的距离
            return np.linalg.norm(point - closest_point)

    def _convert_pruned_to_simplified(self, G_pruned):
        """
        将剪枝后的图转换为简化节点和边的格式

        参数:
        -----------
        G_pruned: networkx图
            剪枝后的骨架图

        返回:
        -----------
        simplified_nodes: 列表 [(node_id, point), ...]
            简化后的节点
        simplified_edges: 列表
            简化后的边
        """
        print("  将剪枝后的图转换为简化格式...")

        # 创建节点列表
        simplified_nodes = []
        node_mapping = {}  # 原始节点ID -> 简化节点索引

        for i, node in enumerate(G_pruned.nodes()):
            node_id = f"skeleton_pruned_{i}"
            pos = G_pruned.nodes[node]['pos']
            simplified_nodes.append((node_id, pos))
            node_mapping[node] = i

        # 创建边列表
        simplified_edges = []

        for u, v, data in G_pruned.edges(data=True):
            if u in node_mapping and v in node_mapping:
                idx1 = node_mapping[u]
                idx2 = node_mapping[v]

                # 计算距离
                p1 = simplified_nodes[idx1][1]
                p2 = simplified_nodes[idx2][1]
                dist = np.linalg.norm(p1 - p2)

                simplified_edges.append((idx1, idx2, dist))

        return simplified_nodes, simplified_edges

    def _connect_urethra_to_skeleton(self):
        """将尿道口连接到最近的骨架节点，并确保连接到主骨架"""
        print("连接尿道口到骨架...")

        # 首先检查骨架的连通性
        skeleton_nodes = [node for node in self.graph.nodes()
                          if self.graph.nodes[node].get('type') == 'skeleton']

        if not skeleton_nodes:
            print("❌ 没有骨架节点可用")
            return

        # 获取骨架子图
        skeleton_subgraph = self.graph.subgraph(skeleton_nodes)

        # 检查连通分量
        connected_components = list(nx.connected_components(skeleton_subgraph))
        print(f"骨架连通分量数量: {len(connected_components)}")

        # 找到最大的连通分量（主骨架）
        largest_component = max(connected_components, key=len)
        print(f"主骨架节点数: {len(largest_component)}")

        # 获取主骨架节点的坐标
        largest_component_coords = []
        largest_component_nodes = []
        for node in largest_component:
            largest_component_nodes.append(node)
            largest_component_coords.append(self.node_positions[node])

        largest_component_coords = np.array(largest_component_coords)

        # 使用KDTree查找最近的骨架节点（只在主骨架中查找）
        tree = KDTree(largest_component_coords)
        distances, indices = tree.query(self.urethra_point.reshape(1, -1), k=1)

        nearest_skeleton_node = largest_component_nodes[indices[0]]
        distance = distances[0]

        # 添加尿道口节点
        urethra_node_id = "urethra_entry"
        self.graph.add_node(urethra_node_id,
                            pos=self.urethra_point,
                            type='urethra',
                            is_start=True)
        self.node_types[urethra_node_id] = 'urethra'
        self.node_positions[urethra_node_id] = self.urethra_point

        # 连接到最近的骨架节点（主骨架中的节点）
        self.graph.add_edge(urethra_node_id, nearest_skeleton_node,
                            weight=distance,
                            distance=distance,
                            type='connection')

        print(f"尿道口连接到主骨架节点: {nearest_skeleton_node}, 距离: {distance:.2f}mm")

        # 如果有其他连通分量（孤立的骨架部分），连接到主骨架
        for i, component in enumerate(connected_components):
            if component == largest_component:
                continue  # 跳过主骨架

            print(f"处理孤立骨架分量 {i + 1} ({len(component)}个节点)")

            # 找到孤立分量中离主骨架最近的节点
            component_nodes = list(component)
            component_coords = np.array([self.node_positions[node] for node in component_nodes])

            # 查找孤立分量中每个节点到主骨架的最短距离
            min_distance = float('inf')
            best_component_node = None
            best_main_node = None

            for comp_node, comp_coord in zip(component_nodes, component_coords):
                # 计算到主骨架所有节点的距离
                distances, indices = tree.query(comp_coord.reshape(1, -1), k=1)
                dist = distances[0]
                main_node = largest_component_nodes[indices[0]]

                if dist < min_distance:
                    min_distance = dist
                    best_component_node = comp_node
                    best_main_node = main_node

            # 在孤立的骨架节点和主骨架节点之间添加连接边
            if best_component_node and best_main_node:
                self.graph.add_edge(best_component_node, best_main_node,
                                    weight=min_distance,
                                    distance=min_distance,
                                    type='connection')
                print(f"  连接孤立节点 {best_component_node} 到主骨架节点 {best_main_node}, 距离: {min_distance:.2f}mm")

    def _connect_stones_to_skeleton(self):
        """将肾结石连接到最近的骨架节点"""
        print("连接肾结石到骨架...")

        if len(self.stone_points) == 0:
            print("⚠️ 没有肾结石点")
            return

        # 首先检查骨架的连通性
        skeleton_nodes = [node for node in self.graph.nodes()
                          if self.graph.nodes[node].get('type') == 'skeleton']

        if not skeleton_nodes:
            print("❌ 没有骨架节点可用")
            return

        # 获取骨架子图
        skeleton_subgraph = self.graph.subgraph(skeleton_nodes)

        # 检查连通分量
        connected_components = list(nx.connected_components(skeleton_subgraph))

        # 找到最大的连通分量（主骨架）
        largest_component = max(connected_components, key=len)

        # 获取主骨架节点的坐标
        largest_component_coords = []
        largest_component_nodes = []
        for node in largest_component:
            largest_component_nodes.append(node)
            largest_component_coords.append(self.node_positions[node])

        largest_component_coords = np.array(largest_component_coords)

        # 创建KDTree（只使用主骨架节点）
        tree = KDTree(largest_component_coords)

        # 连接每个结石
        for i, stone_point in enumerate(self.stone_points):
            stone_node_id = f"stone_{i + 1}"

            # 查找最近的骨架节点（只在主骨架中查找）
            distances, indices = tree.query(stone_point.reshape(1, -1), k=1)
            nearest_skeleton_node = largest_component_nodes[indices[0]]
            distance = distances[0]

            # 添加结石节点
            self.graph.add_node(stone_node_id,
                                pos=stone_point,
                                type='stone',
                                stone_id=i + 1,
                                is_target=True)
            self.node_types[stone_node_id] = 'stone'
            self.node_positions[stone_node_id] = stone_point

            # 连接到最近的骨架节点（主骨架中的节点）
            self.graph.add_edge(stone_node_id, nearest_skeleton_node,
                                weight=distance,
                                distance=distance,
                                type='connection')

            print(f"结石{i + 1}连接到主骨架节点: {nearest_skeleton_node}, 距离: {distance:.2f}mm")

    def _check_and_fix_connectivity(self):
        """检查并修复骨架的连通性"""
        print("检查骨架连通性...")

        # 获取所有骨架节点
        skeleton_nodes = [node for node in self.graph.nodes()
                          if self.graph.nodes[node].get('type') == 'skeleton']

        if not skeleton_nodes:
            print("❌ 没有骨架节点")
            return True

        # 创建骨架子图
        skeleton_subgraph = self.graph.subgraph(skeleton_nodes)

        # 检查连通分量
        connected_components = list(nx.connected_components(skeleton_subgraph))

        if len(connected_components) == 1:
            print(f"骨架是连通的，包含 {len(skeleton_nodes)} 个节点")
            return True

        print(f"警告: 骨架有 {len(connected_components)} 个连通分量")

        # 找到最大的连通分量
        largest_component = max(connected_components, key=len)
        print(f"主骨架节点数: {len(largest_component)}")

        # 对于其他每个分量，找到离主骨架最近的节点并连接
        for i, component in enumerate(connected_components):
            if component == largest_component:
                continue

            print(f"修复孤立分量 {i + 1} ({len(component)}个节点)")

            # 获取分量中的节点坐标
            component_nodes = list(component)
            component_coords = np.array([self.node_positions[node] for node in component_nodes])

            # 获取主骨架节点坐标
            main_nodes = list(largest_component)
            main_coords = np.array([self.node_positions[node] for node in main_nodes])

            # 创建KDTree查找最近节点
            tree_main = KDTree(main_coords)

            # 查找两个分量之间的最短距离
            min_distance = float('inf')
            best_main_node = None
            best_component_node = None

            for comp_node, comp_coord in zip(component_nodes, component_coords):
                distances, indices = tree_main.query(comp_coord.reshape(1, -1), k=1)
                dist = distances[0]
                main_node = main_nodes[indices[0]]

                if dist < min_distance:
                    min_distance = dist
                    best_main_node = main_node
                    best_component_node = comp_node

            # 添加连接边
            if best_main_node and best_component_node:
                self.graph.add_edge(best_main_node, best_component_node,
                                    weight=min_distance,
                                    distance=min_distance,
                                    type='skeleton_connection')
                print(f"  连接 {best_component_node} 到 {best_main_node}, 距离: {min_distance:.2f}mm")

        return True

    def _analyze_paths(self):
        """分析从尿道口到每个结石的路径"""
        print("分析路径...")

        # 找到尿道口节点
        urethra_nodes = [node for node in self.graph.nodes()
                         if self.graph.nodes[node].get('type') == 'urethra']

        if not urethra_nodes:
            print("❌ 没有找到尿道口节点")
            return

        urethra_node = urethra_nodes[0]

        # 找到所有结石节点
        stone_nodes = [node for node in self.graph.nodes()
                       if self.graph.nodes[node].get('type') == 'stone']

        if not stone_nodes:
            print("⚠️ 没有找到结石节点")
            return

        # 计算从尿道口到每个结石的最短路径
        print("\n=== 计算路径 ===")
        for stone_node in stone_nodes:
            stone_id = self.graph.nodes[stone_node].get('stone_id', 0)

            try:
                # 使用Dijkstra算法找到最短路径
                path = nx.shortest_path(self.graph, urethra_node, stone_node, weight='weight')

                # 计算路径长度
                path_length = 0
                for i in range(len(path) - 1):
                    if self.graph.has_edge(path[i], path[i + 1]):
                        path_length += self.graph[path[i]][path[i + 1]]['weight']

                # 存储路径信息
                self.paths_to_stones[stone_id] = path
                self.path_lengths[stone_id] = path_length

                print(f"到结石{stone_id}的路径长度: {path_length:.2f}mm, 节点数: {len(path)}")

            except nx.NetworkXNoPath:
                print(f"❌ 无法找到到结石{stone_id}的路径")
                print(f"  尿道口节点: {urethra_node}")
                print(f"  结石节点: {stone_node}")

    def get_all_paths(self):
        """获取所有路径信息"""
        paths_info = []

        for stone_id, path in self.paths_to_stones.items():
            path_length = self.path_lengths.get(stone_id, 0)

            # 获取路径中的坐标
            path_coords = [self.node_positions[node] for node in path]

            paths_info.append({
                'stone_id': stone_id,
                'path_nodes': path,
                'path_length': path_length,
                'path_coords': path_coords,
                'num_nodes': len(path)
            })

        return paths_info

    def visualize_topology(self, output_path=None, interactive=False,
                           kidney_stl_path=None, stone_stl_path=None, cavity_stl_path=None):
        """
        可视化拓扑图

        参数:
        -----------
        output_path: str
            输出图像路径
        interactive: bool
            是否显示交互窗口
        kidney_stl_path: str
            肾脏STL模型路径
        stone_stl_path: str
            结石STL模型路径
        cavity_stl_path: str
            肾脏腔室STL模型路径
        """
        print("Visualizing topology...")

        try:
            # 创建无坐标系的plotter
            plotter = vedo.Plotter(axes=0, bg='white', size=(1200, 900))

            # 0. 显示肾脏STL模型（半透明红色）
            if kidney_stl_path and os.path.exists(kidney_stl_path):
                print(f"Loading kidney STL: {kidney_stl_path}")
                try:
                    kidney_mesh = vedo.load(kidney_stl_path)
                    kidney_mesh.alpha(0.1).color('red')  # 半透明红色
                    plotter.add(kidney_mesh)
                    print("Kidney model loaded successfully (semi-transparent red)")
                except Exception as e:
                    print(f"Failed to load kidney STL: {e}")

            # 或者显示肾脏腔室STL模型（同样半透明红色）
            elif cavity_stl_path and os.path.exists(cavity_stl_path):
                print(f"Loading kidney cavity STL: {cavity_stl_path}")
                try:
                    cavity_mesh = vedo.load(cavity_stl_path)
                    cavity_mesh.alpha(0.3).color('red')  # 半透明红色
                    plotter.add(cavity_mesh)
                    print("Kidney cavity model loaded successfully (semi-transparent red)")
                except Exception as e:
                    print(f"Failed to load kidney cavity STL: {e}")

            # 1. 显示骨架节点和边
            skeleton_nodes = [node for node in self.graph.nodes()
                              if self.graph.nodes[node].get('type') == 'skeleton']

            if skeleton_nodes:
                # 骨架节点 - 只显示关键节点
                skeleton_coords = np.array([self.node_positions[node] for node in skeleton_nodes])
                skeleton_points_viz = vedo.Points(skeleton_coords, r=2, c='gray', alpha=0.3)
                plotter.add(skeleton_points_viz)

                # 骨架边
                skeleton_edges = [(u, v) for u, v, data in self.graph.edges(data=True)
                                  if data.get('type') == 'skeleton']

                for u, v in skeleton_edges:
                    p1 = self.node_positions[u]
                    p2 = self.node_positions[v]
                    line = vedo.Line(p1, p2, lw=2, c='blue', alpha=0.6)
                    plotter.add(line)

                # 修复: 明确标记分叉点（度数≥3的节点）
                bifurcation_nodes = [node for node in skeleton_nodes if self.graph.degree(node) >= 3]
                if bifurcation_nodes:
                    bifurcation_coords = np.array([self.node_positions[node] for node in bifurcation_nodes])
                    # 用红色大点标记分叉点，确保视觉上明显
                    bifurcation_points = vedo.Points(bifurcation_coords, r=8, c='red')
                    plotter.add(bifurcation_points)
                    print(f"  标记分叉点: {len(bifurcation_nodes)}个")

            # 2. 显示尿道口
            urethra_nodes = [node for node in self.graph.nodes()
                             if self.graph.nodes[node].get('type') == 'urethra']

            if urethra_nodes:
                urethra_coords = np.array([self.node_positions[node] for node in urethra_nodes])
                urethra_points_viz = vedo.Points(urethra_coords, r=6, c='green')
                plotter.add(urethra_points_viz)

            # 3. 显示结石（黄色）
            stone_nodes = [node for node in self.graph.nodes()
                           if self.graph.nodes[node].get('type') == 'stone']

            if stone_nodes:
                stone_coords = np.array([self.node_positions[node] for node in stone_nodes])
                stone_points_viz = vedo.Points(stone_coords, r=6, c='yellow')  # 黄色点
                plotter.add(stone_points_viz)

                # 加载结石STL模型（非透明黄色）
                if stone_stl_path and os.path.exists(stone_stl_path):
                    print(f"Loading stone STL: {stone_stl_path}")
                    try:
                        stone_mesh = vedo.load(stone_stl_path)
                        stone_mesh.alpha(1.0).color('yellow')  # 非透明黄色
                        plotter.add(stone_mesh)
                        print("Stone model loaded successfully (opaque yellow)")
                    except Exception as e:
                        print(f"Failed to load stone STL: {e}")

            # 4. 显示连接边
            connection_edges = [(u, v) for u, v, data in self.graph.edges(data=True)
                                if data.get('type') == 'connection']

            for u, v in connection_edges:
                p1 = self.node_positions[u]
                p2 = self.node_positions[v]
                # 尝试使用dashed参数创建虚线，如果失败则使用普通线
                try:
                    line = vedo.Line(p1, p2, lw=2, c='orange', alpha=0.8, dashed=True)
                except TypeError:
                    # 如果dashed参数不被支持，使用普通线
                    line = vedo.Line(p1, p2, lw=2, c='orange', alpha=0.8)

                plotter.add(line)

            # 5. 显示关键路径
            paper_color = 'navy'  # 学术论文推荐颜色，专业且清晰

            for stone_id, path in self.paths_to_stones.items():
                # 绘制路径
                path_coords = [self.node_positions[node] for node in path]
                path_array = np.array(path_coords)

                # 使用Tube显示路径
                if len(path_array) > 1:
                    # 所有路径使用同一颜色
                    path_line = vedo.Line(path_array, lw=4, c=paper_color)
                    plotter.add(path_line)

            # 6. 显示或保存
            if output_path:
                # 如果指定了输出路径，先保存截图
                print(f"Saving screenshot to: {output_path}")
                plotter.show(interactive=False, zoom=1.2, viewup='z')
                plotter.screenshot(output_path)
                print(f"✅ Topology visualization saved: {output_path}")

            if interactive:
                # 如果需要交互，显示交互窗口
                print("Showing interactive window...")
                plotter.show(interactive=True, axes=0, viewup='z')
            elif not output_path:
                # 如果既没有输出路径也不交互，显示非交互窗口
                print("Showing non-interactive window...")
                plotter.show(interactive=False, zoom=1.2, viewup='z')
                plotter.close()

        except Exception as e:
            print(f"Visualization failed: {e}")
            import traceback
            traceback.print_exc()

    def save_topology_data(self, output_path):
        """保存拓扑图数据"""
        print("保存拓扑图数据...")

        # 准备数据
        topology_data = {
            'metadata': {
                'total_nodes': self.graph.number_of_nodes(),
                'total_edges': self.graph.number_of_edges(),
                'num_stones': len(self.stone_points),
                'num_paths': len(self.paths_to_stones)
            },
            'nodes': [],
            'edges': [],
            'paths': []
        }

        # 保存节点数据 - 确保所有numpy数组转换为列表
        for node in self.graph.nodes():
            node_data = self.graph.nodes[node].copy()
            node_data['node_id'] = node

            # 处理position坐标
            if node in self.node_positions:
                node_data['position'] = self.node_positions[node].tolist()
            else:
                # 如果node_positions中没有，尝试从graph节点属性中获取
                if 'pos' in node_data:
                    if isinstance(node_data['pos'], np.ndarray):
                        node_data['pos'] = node_data['pos'].tolist()

                # 确保有position字段
                if 'pos' in node_data:
                    node_data['position'] = node_data.pop('pos')

            # 确保所有numpy数组都转换为列表
            for key, value in node_data.items():
                if isinstance(value, np.ndarray):
                    node_data[key] = value.tolist()
                elif isinstance(value, np.generic):  # numpy标量类型
                    node_data[key] = value.item()

            topology_data['nodes'].append(node_data)

        # 保存边数据
        for u, v, data in self.graph.edges(data=True):
            edge_data = {
                'source': u,
                'target': v,
                'weight': float(data.get('weight', 0)),  # 确保是Python float
                'distance': float(data.get('distance', 0)),  # 确保是Python float
                'type': data.get('type', 'unknown')
            }
            topology_data['edges'].append(edge_data)

        # 保存路径数据
        for stone_id, path in self.paths_to_stones.items():
            path_coordinates = []
            for node in path:
                if node in self.node_positions:
                    path_coordinates.append(self.node_positions[node].tolist())
                else:
                    # 如果node_positions中没有，尝试从graph节点中获取
                    node_data = self.graph.nodes[node]
                    if 'pos' in node_data:
                        pos = node_data['pos']
                        if isinstance(pos, np.ndarray):
                            path_coordinates.append(pos.tolist())
                        else:
                            path_coordinates.append(pos)
                    else:
                        path_coordinates.append([0, 0, 0])  # 默认值

            path_data = {
                'stone_id': int(stone_id) if isinstance(stone_id, np.generic) else stone_id,
                'path_length': float(self.path_lengths.get(stone_id, 0)),
                'path_nodes': path,
                'path_coordinates': path_coordinates
            }
            topology_data['paths'].append(path_data)

        # 保存为JSON
        if not output_path.endswith('.json'):
            output_path = output_path + '.json'

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(topology_data, f, ensure_ascii=False, indent=2)

        print(f"✅ 拓扑图数据已保存: {output_path}")

        # 同时保存为Excel（便于查看）
        excel_path = output_path.replace('.json', '.xlsx')
        self._save_to_excel(excel_path)

        return output_path

    def _save_to_excel(self, output_path):
        """保存到Excel文件"""
        try:
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                # 1. 节点表
                nodes_data = []
                for node in self.graph.nodes():
                    node_info = self.graph.nodes[node].copy()
                    node_info['node_id'] = node

                    # 获取坐标，确保是Python列表
                    pos = None
                    if node in self.node_positions:
                        pos = self.node_positions[node]
                    elif 'pos' in node_info:
                        pos = node_info['pos']

                    if pos is not None:
                        if isinstance(pos, np.ndarray):
                            pos = pos.tolist()
                        node_info['x'] = float(pos[0]) if len(pos) > 0 else 0.0
                        node_info['y'] = float(pos[1]) if len(pos) > 1 else 0.0
                        node_info['z'] = float(pos[2]) if len(pos) > 2 else 0.0

                    # 转换所有numpy类型到Python类型
                    for key, value in node_info.items():
                        if isinstance(value, np.generic):
                            node_info[key] = value.item()

                    nodes_data.append(node_info)

                nodes_df = pd.DataFrame(nodes_data)
                nodes_df.to_excel(writer, sheet_name='Nodes', index=False)

                # 2. 边表
                edges_data = []
                for u, v, data in self.graph.edges(data=True):
                    edge_info = {
                        'source': u,
                        'target': v,
                        'weight': float(data.get('weight', 0)),
                        'distance': float(data.get('distance', 0)),
                        'type': data.get('type', 'unknown')
                    }
                    edges_data.append(edge_info)

                edges_df = pd.DataFrame(edges_data)
                edges_df.to_excel(writer, sheet_name='Edges', index=False)

                # 3. 路径表
                paths_data = []
                for stone_id, path in self.paths_to_stones.items():
                    stone_id_value = stone_id
                    if isinstance(stone_id, np.generic):
                        stone_id_value = stone_id.item()

                    path_info = {
                        'stone_id': stone_id_value,
                        'path_length': float(self.path_lengths.get(stone_id, 0)),
                        'num_nodes': len(path),
                        'path_nodes': ' -> '.join(path)
                    }
                    paths_data.append(path_info)

                paths_df = pd.DataFrame(paths_data)
                paths_df.to_excel(writer, sheet_name='Paths', index=False)

                # 4. 结石表
                stones_data = []
                for i, stone_point in enumerate(self.stone_points):
                    stone_info = {
                        'stone_id': i + 1,
                        'x': float(stone_point[0]),
                        'y': float(stone_point[1]),
                        'z': float(stone_point[2])
                    }
                    stones_data.append(stone_info)

                stones_df = pd.DataFrame(stones_data)
                stones_df.to_excel(writer, sheet_name='Stones', index=False)

            print(f"✅ Excel数据已保存: {output_path}")
        except Exception as e:
            print(f"⚠️ Excel保存失败（可能缺少 openpyxl）: {e}")

    def get_path_planning_data(self):
        """获取路径规划所需数据"""
        planning_data = {
            'start_point': {
                'id': 'urethra_entry',
                'position': self.urethra_point.tolist(),
                'type': 'urethra'
            },
            'target_points': [],
            'paths': []
        }

        # 目标点（结石）
        for i, stone_point in enumerate(self.stone_points):
            target_info = {
                'id': f'stone_{i+1}',
                'position': stone_point.tolist(),
                'type': 'stone',
                'stone_id': i+1
            }
            planning_data['target_points'].append(target_info)

        # 路径信息
        for stone_id, path in self.paths_to_stones.items():
            path_info = {
                'stone_id': stone_id,
                'path_length': self.path_lengths.get(stone_id, 0),
                'node_sequence': path,
                'coordinate_sequence': [self.node_positions[node].tolist() for node in path]
            }
            planning_data['paths'].append(path_info)

        return planning_data


# ======================= 辅助函数 ========================
def load_skeleton_data(skeleton_file):
    """
    加载树状骨架数据

    参数:
    -----------
    skeleton_file: str
        骨架文件路径(.json或.npz)

    返回:
    -----------
    skeleton_points: numpy数组
        骨架点坐标
    skeleton_edges: list
        骨架边列表[(node1_idx, node2_idx, distance), ...]
    """
    if skeleton_file.endswith('.json'):
        # JSON格式
        try:
            with open(skeleton_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 提取骨架点
            skeleton_points = np.array(data['points'])

            # 提取骨架边
            skeleton_edges = []
            for edge in data['edges']:
                skeleton_edges.append((edge['source'], edge['target'], edge['distance']))

            return skeleton_points, skeleton_edges

        except Exception as e:
            print(f"加载JSON骨架数据失败: {e}")
            return None, None

    elif skeleton_file.endswith('.npz'):
        # NPZ格式
        try:
            data = np.load(skeleton_file, allow_pickle=True)

            # 提取骨架点
            skeleton_points = data['skeleton_points']

            # 使用正确的键名 'skeleton_edges'
            if 'skeleton_edges' in data.files:
                edges_data = data['skeleton_edges']
                skeleton_edges = []

                # 处理对象数组
                if edges_data.dtype == object:
                    for edge in edges_data:
                        if len(edge) == 3:
                            skeleton_edges.append(tuple(edge))
                        else:
                            # 计算距离
                            p1 = skeleton_points[edge[0]]
                            p2 = skeleton_points[edge[1]]
                            distance = np.linalg.norm(p1 - p2)
                            skeleton_edges.append((edge[0], edge[1], distance))
                else:
                    # 普通数组
                    for edge in edges_data:
                        skeleton_edges.append(tuple(edge))

                print(f"✅ 成功加载NPZ骨架数据: {len(skeleton_points)}点, {len(skeleton_edges)}边")
                return skeleton_points, skeleton_edges
            else:
                print(f"❌ NPZ文件中未找到 'skeleton_edges' 键")
                print(f"可用键: {data.files}")
                return None, None

        except Exception as e:
            print(f"加载NPZ骨架数据失败: {e}")
            import traceback
            traceback.print_exc()
            return None, None

    else:
        print(f"不支持的文件格式: {skeleton_file}")
        return None, None


def build_topology_from_json(skeleton_file, stone_stl_path, output_dir="./result/5/topology_results",
                              kidney_stl_path=None, cavity_stl_path=None):
    """
    从骨架文件和结石 STL 构建拓扑图，自动识别尿道口（Y 最小点）。

    参数:
    -----------
    skeleton_file: str
        骨架数据文件路径（.npz 或 .json）
    stone_stl_path: str
        结石 STL 文件路径
    output_dir: str
        输出目录
    kidney_stl_path: str, optional
        肾脏 STL 模型路径（用于可视化）
    cavity_stl_path: str, optional
        肾脏腔室 STL 模型路径（用于可视化）

    返回:
    -----------
    topology: KidneyPathTopology 对象
    """
    print("=" * 60)
    print("从骨架和结石 STL 构建拓扑图")
    print("=" * 60)

    total_start = time.perf_counter()

    # 1. 加载骨架数据
    print(f"加载骨架数据: {skeleton_file}")
    skeleton_points, skeleton_edges = load_skeleton_data(skeleton_file)
    if skeleton_points is None or skeleton_edges is None:
        print("❌ 骨架数据加载失败")
        return None
    print(f"骨架点数: {len(skeleton_points)}, 边数: {len(skeleton_edges)}")

    # 2. 从骨架点中自动确定尿道口（Y 坐标最小的点）
    min_y_idx = np.argmin(skeleton_points[:, 1])
    urethra_point = skeleton_points[min_y_idx]
    print(f"尿道口自动确定为 Y 最小点: {urethra_point}")

    # 3. 从结石 STL 中提取结石中心点（使用体素分割+骨架中心）
    print(f"加载结石 STL: {stone_stl_path}")
    if not os.path.exists(stone_stl_path):
        print(f"❌ 结石 STL 文件不存在: {stone_stl_path}")
        return None

    extractor = KidneyStoneExtractor(stone_stl_path, safe_margin=2.0, voxel_size=0.5, min_voxel_ratio=0.01)
    stone_centers = extractor.get_stone_centers()
    if not stone_centers:
        print("❌ 未从 STL 中提取到任何结石中心点")
        return None

    stone_points = np.array(stone_centers)
    print(f"提取到 {len(stone_points)} 个结石中心点:")
    for i, p in enumerate(stone_points):
        print(f"  结石{i+1}: {p}")

    # 4. 创建拓扑图
    print("\n创建拓扑图...")
    t0 = time.perf_counter()
    topology = KidneyPathTopology(
        skeleton_points=skeleton_points,
        skeleton_edges=skeleton_edges,
        urethra_point=urethra_point,
        stone_points=stone_points
    )
    print(f"✅ 拓扑图创建成功")
    print(f"   总节点数: {topology.graph.number_of_nodes()}")
    print(f"   总边数: {topology.graph.number_of_edges()}")
    print(f"⏱ 拓扑构建耗时: {time.perf_counter() - t0:.2f} 秒")

    # 5. 路径分析
    paths_info = topology.get_all_paths()
    print(f"\n路径分析:")
    for path_info in paths_info:
        print(f"  到结石{path_info['stone_id']}: {path_info['path_length']:.1f}mm, {path_info['num_nodes']}个节点")

    # 6. 保存数据
    os.makedirs(output_dir, exist_ok=True)
    json_path = os.path.join(output_dir, "topology_result.json")
    topology.save_topology_data(json_path)
    print(f"\n✅ 数据已保存到: {json_path}")

    # 7. 可视化（可选）
    print("\n生成可视化图像...")
    viz_path = os.path.join(output_dir, "topology_visualization.png")
    try:
        topology.visualize_topology(
            output_path=viz_path,
            interactive=False,
            kidney_stl_path=kidney_stl_path,
            stone_stl_path=stone_stl_path,
            cavity_stl_path=cavity_stl_path
        )
        print(f"✅ 可视化图像已保存: {viz_path}")
    except Exception as e:
        print(f"⚠️ 可视化图像保存失败: {e}")

    # 8. 可选交互式可视化
    print("\n启动交互式可视化...")
    try:
        topology.visualize_topology(
            output_path=None,
            interactive=True,
            kidney_stl_path=kidney_stl_path,
            stone_stl_path=stone_stl_path,
            cavity_stl_path=cavity_stl_path
        )
    except Exception as e:
        print(f"⚠️ 交互式可视化失败: {e}")

    total_time = time.perf_counter() - total_start
    print(f"\n⏱ 总耗时: {total_time:.2f} 秒")
    return topology


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build path-planning topology from a skeleton + stone STL")
    parser.add_argument("--case-id", default="1", help="Case number; determines result/<case-id>/...")
    parser.add_argument("--skeleton-file", default=None,
                         help="默认: result/<case-id>/skeleton_results/kidney_skeleton_raw.npz")
    parser.add_argument("--stone-stl", default="RenalPelvis/KidneyStone.stl")
    parser.add_argument("--kidney-stl", default="RenalPelvis/RenalPelvis.stl")
    parser.add_argument("--cavity-stl", default=None)
    parser.add_argument("--output-dir", default=None,
                         help="默认: result/<case-id>/topology_results")
    args = parser.parse_args()

    topology = build_topology_from_json(
        skeleton_file=args.skeleton_file or f"result/{args.case_id}/skeleton_results/kidney_skeleton_raw.npz",
        stone_stl_path=args.stone_stl,
        output_dir=args.output_dir or f"result/{args.case_id}/topology_results",
        kidney_stl_path=args.kidney_stl,
        cavity_stl_path=args.cavity_stl
    )