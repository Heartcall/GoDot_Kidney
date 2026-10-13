# P1.1 / P1.2 实施结果与掩码查看方法

日期：2026-10-13。当前状态：已实现并执行验证，等待用户检查掩码边界；停在 P1.2，没有开始位移场或动态形变。

## 在 Godot 中查看

1. 打开现有 `godot_sim/project.godot`。
2. 在文件系统面板打开 **`res://irrigation_mask_preview.tscn`**。
3. 按 **F6（运行当前场景）**。F5 仍运行原来的主场景。
4. 默认模式：蓝色为固定区，橙色为过渡区，绿色为可扩张区。
5. 点击“连续权重”或按 **2**：显示权重从蓝色 0，经橙色 0.5，到绿色 1 的渐变。
6. 点击“膀胱接口”“B_31 接口”“B_32 接口”，分别检查三处连接；重点旋转观察接口的整圈边界。

操作：左键拖动旋转，中键拖动平移，滚轮缩放，R 恢复全模型视角。按 1/2/3 切换三种着色模式。中心线开关提供透视叠加；“路径归属”颜色仅显示最近折线诊断，不是最终解剖分区。

也可以在编辑器中查看生成的网格，选择 `MaskMesh` 后按 F 聚焦；图例、按钮与鼠标控制在 F6 运行时可用。

## 实际结果

拓扑解析保存于 `godot_sim/deformation/cavity_topology_resolved.json`：72 个标记、32 条 B 分支、37 条有序路径，展开图为 72 节点／71 边的连通树。控制点顺序及连接关系按原始草案保留，解析结果含弧长采样、节点邻接、路径邻接、输入哈希和验证范围。

参考网格仍是原来的 25,024 个顶点、50,044 个三角面，全部顶点坐标与面索引未发生形变或重排。

| 区域 | 顶点数 | 面积（mm²） | 扩张权重 |
| --- | ---: | ---: | --- |
| 固定区（蓝） | 3,698 | 1,628.295 | 严格等于 0 |
| 过渡区（橙） | 1,356 | 580.018 | 大于 0、小于 1 |
| 可扩张区（绿） | 19,970 | 8,603.921 | 等于 1 |
| 合计 | 25,024 | 10,812.234 | — |

面积按每个三角面向三个顶点各分配 1/3 面积，再按顶点类别汇总。跨类别三角面按顶点归属分摊；这不是精确裁切后的区域面积。

| 人工通道 | 固定顶点数 | 固定面积（mm²） | 对应过渡 | 过渡支持长度（mm） |
| --- | ---: | ---: | --- | ---: |
| BLADDER | 2,793 | 1,254.151 | BLADDER_TRANSITION | 7.158 |
| IN_01 | 420 | 184.597 | B_31 | 9.205 |
| IN_02 | 485 | 189.547 | B_32 | 2.844 |

三条固定管壁各自连通、互不重叠，权重严格为零。B_31、B_32 的接口过渡按各自长度生成，没有统一采用固定毫米宽度。

## 分区实现方式

- 读取原始 OBJ 的顶点和三角面，保留原有索引。
- 用 37 条确认折线做最近路径投影，用局部射线估计人工管径。
- 从每条管道远端的表面种子出发，沿网格边扩展；结合 BASE 截面、局部半径范围及拓扑相邻路径归属确定固定区，包含远端端帽。
- 管径范围同时参考种子连通片，覆盖膀胱连接段的沿程宽度变化。
- IN_02 附近有 56 个“最近路径属于该管道、但与远端种子不连通”的表面顶点，已排除出固定核心，避免把邻近分支误固定。
- 从每条固定管壁计算表面边图最短距离，按对应过渡路径长度应用 smoothstep；多个过渡影响取较小权重。距离沿表面传播，避免直接使用空间球形范围跨到邻近分支。

BASE 标记决定管段固定截面的初始位置，这一几何推断仍需你目视确认。尤其检查 B_32 周围固定蓝色是否截在正确接口，以及橙色是否侵入过多自然区。

B_32 的过渡很短，当前网格中相邻顶点的最大单边权重差约 0.587。此值已写入报告；检查权重模式，确认是否需要在后续位移计算前调整过渡或局部网格分辨率。本轮没有擅自延长接口范围或修改网格。

## 输出文件

| 文件 | 用途 |
| --- | --- |
| `godot_sim/tools/resolve_cavity_topology.py` | 可重复生成 resolved 文件；`--check` 检查是否过期 |
| `godot_sim/tools/build_cavity_surface_masks.py` | 初版表面分区、权重、面积及预览数据生成 |
| `godot_sim/tools/test_p1_masks.py` | 9 项数据、算法和输出格式验证 |
| `godot_sim/deformation/surface_mask_config.json` | 管径探测、包络与过渡参数 |
| `godot_sim/deformation/p1_masks/weights.npy` | 每个原 OBJ 顶点的扩张权重 |
| `godot_sim/deformation/p1_masks/regions.npy` | 分类：0 固定、1 过渡、2 可扩张 |
| `godot_sim/deformation/p1_masks/port_fixed_masks.npy` | 三条通道各自的布尔固定掩码，顺序见 resolved 的 artificial_ports |
| `godot_sim/deformation/p1_masks/port_weights.npy` | 三条通道各自的过渡影响权重 |
| `godot_sim/deformation/p1_masks/vertices.npy`、`faces.npy` | 对应原始 OBJ 的规范顶点／面数组 |
| `godot_sim/deformation/p1_masks/vertex_area_mm2.npy` | 顶点分摊面积 |
| `godot_sim/deformation/p1_masks/mask_preview.bin`、`mask_preview.json` | Godot 可直接读取的预览数据，不依赖 OBJ 导入顶点顺序 |
| `godot_sim/deformation/p1_masks/surface_mask_report.json` | 区域／通道统计、方法、来源哈希和检查范围 |
| `godot_sim/deformation/p1_masks/p1_validation.json` | 本轮验证结果与受保护文件前后哈希 |
| `godot_sim/scripts/irrigation_mask_preview.gd` | 编辑器及运行时掩码查看工具 |
| `godot_sim/irrigation_mask_preview.tscn` | 独立查看入口 |

附加数组 `normals.npy`、`path_owner.npy`、`path_arc_mm.npy`、`fixed_port_owner.npy` 用于预览和后续调试。

预览二进制定义：小端、8 字节 `KMSK0001`，随后三个 uint32 表示顶点／三角面／路径数量；再依次保存 float32 顶点 xyz、法线 xyz、权重，uint32 类别、路径归属，float32 路径弧长，最后 uint32 三角面索引。预览面的绕序为适配 Godot 而反转，源 OBJ 和 `faces.npy` 保持原绕序。该转换经过索引和坐标精度验证。

## 已执行验证

- 解析器成功运行；`--check` 通过，37 条路径及所有控制点顺序保留。
- 掩码生成器成功运行；再次生成后 14 个生成产物逐字节一致。
- 9 项测试通过：异常引用／坐标拒绝、弧长采样、短接口渐变、断开表面不误固定、固定区连通与零权重、面积守恒、源几何一致、二进制布局等。
- Godot 4.7 成功加载独立预览。
- 在本机 RTX 4070 Ti、Vulkan Forward+ 上实际渲染六张截图，正常退出，错误日志为空；全模型、权重、路径归属和三个接口均有截图。
- 两份原始 OBJ、72 个标记所在场景、标记 JSON、人工拓扑草案及 `main.tscn` 的前后 SHA-256 完全一致。

截图位于 `godot_sim/analysis/irrigation_baseline/p1_preview/`：`regions.png`、`weights.png`、`paths.png`、`bladder.png`、`b31.png`、`b32.png`。此目录沿用仓库忽略规则，不进入 Git。

## 重新构建

从仓库根目录，在 PowerShell 中依次执行：

```powershell
& 'E:/Apps/Conda/miniconda3/envs/FURS/python.exe' godot_sim/tools/resolve_cavity_topology.py
& 'E:/Apps/Conda/miniconda3/envs/FURS/python.exe' godot_sim/tools/build_cavity_surface_masks.py
& 'E:/Apps/Conda/miniconda3/envs/FURS/python.exe' godot_sim/tools/test_p1_masks.py
```

修改标记／草案后需先重建 resolved；修改配置后需重建掩码。已打开的预览可停止后重新 F6，或在编辑器中使用根节点上的“重新加载掩码”。源 OBJ 或预览二进制哈希不匹配时预览会拒绝加载。

`p1_validation.json` 记录本轮验证快照；后续更改生成器或配置后，应重新测试并刷新验证记录，不能用旧记录证明新产物。

当前按要求停在掩码检查。用户确认固定边界和过渡范围后，再继续 P1.3～P1.5。
