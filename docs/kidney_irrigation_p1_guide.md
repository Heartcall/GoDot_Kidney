# P1 工作指导：从人工拓扑生成可检查的局部形变

2026-10-13 进展：用户已正式验收全天然腔体位移和三态。P1.5 已进入几何审计，但原始组织自交、腔体—组织穿越及映射试验的新增穿越阻断了可信组织形变交付，见 [P1.5 审计与阻塞报告](kidney_irrigation_p15_audit_result.md)。仅交付只读参考态联合剖切预览，未生成通过验证的组织位移或联合三态。原有 OBJ、掩码、腔体驱动和旧阶段成果保持不变。历史记录见 [全天然扩展](kidney_irrigation_full_cavity_result.md)、[P1.4](kidney_irrigation_p14_result.md)、[P1.3](kidney_irrigation_p13_result.md)及 [P1.1～P1.2](kidney_irrigation_p1_masks_result.md)。下文保留历史路线，不代表当前文件缺失。

更新：2026-10-12。依据：当前保存的检查场景、标记 JSON、拓扑草案、现有实现计划，以及本轮自动复核。

本轮已新增只读输入审计工具与审计报告，尚未生成扩张网格、运行时形变或注排水控制器。

## 1. 接手结论

现有人工拓扑与坐标可以作为 P1 的输入，不需要重新标注 72 个点。下一步是将中心线信息转换为**表面区域权重、固定顶点集合和连续位移场**。

当前工作区与交接描述有两项差异：

1. 没有找到 `godot_sim/deformation/cavity_topology_resolved.json`；本轮没有将临时解析结果冒充既有文件，也未改写源拓扑。
2. 本轮开始时，`godot_sim/tools/` 中只有两版标记导出脚本和 `inspect_irrigation_assets.py`；未找到独立的拓扑解析／校验脚本。它们可能未保存到当前工作区；现有 JSON 足够重新构建派生数据，无需重新人工标注。

本轮新增 `godot_sim/tools/audit_p1_inputs.py`，保留现有标记和拓扑内容，核对保存的场景、关联关系和采样几何。报告生成在 `godot_sim/analysis/irrigation_baseline/p1_input_audit.json`。

## 2. 文件与数据格式核对

| 实际文件 | 当前格式／职责 | P1 使用方式 |
| --- | --- | --- |
| `godot_sim/irrigation_asset_check.tscn` | 72 个 Marker3D；腔体与组织引用；主根节点和非标记节点变换均为单位变换 | 人工标记来源与后续掩码可视化参照，保留原场景 |
| `godot_sim/deformation/irrigation_markers.json` | `schema_version = 2.0`，`markers` 是数组，名称在 `name` 字段 | 建立 `name -> marker` 索引 |
| 同上：坐标字段 | 推荐字段 `cavity_local_position_mm`；`position_mm` 仍表示世界坐标 | 几何处理统一读取前者，不依赖目前两者恰好相等 |
| 同上：参考信息 | `reference_mesh.mesh_resource_path` 指向 `res://source_assets/kidney_cavity.obj`，含根与网格变换 | 与实际 OBJ、场景和单位共同核对 |
| `godot_sim/deformation/cavity_topology_draft.json` | `schema_version = 1.0`；保存名称连接，不含完整坐标折线 | 按 `from -> controls -> to` 解析分支 |
| 同上：主腔室 | `main_cavity.centerline = [A_Start, A_Middle, A_End, J_01]` | 保留真实顺序，不能按名称排序生成折线 |
| 同上：膀胱过渡 | `main_cavity.bladder_transition = [P_BLADDER_BASE, A_Start]` | 作为独立过渡段，不能漏掉 |
| 同上：人工通道 | `artificial_ports` 中 BLADDER、IN_01、IN_02；`geometry_role = artificial_fixed` | 对应固定人工管段，和自然分支区分 |
| 同上：分支 | B_01–B_30 为 `natural`，B_31、B_32 为 `interface_transition` | 过渡段权重逐渐下降，不能与固定通道混为同一区域 |
| `godot_sim/tools/export_irrigation_markers_v2.gd` | EditorScript，导出显式腔体局部坐标、变换与诊断 | 后续继续使用此版本 |
| `godot_sim/tools/export_irrigation_markers.gd` | 旧版，仅导出世界／父局部坐标，输出文件名与新版相同 | 避免误运行后覆盖新版坐标结构 |
| `godot_sim/scripts/branch_midpoint_tool.gd` | EditorScript 辅助生成中点，属于标记工具 | 不承担运行时形变或拓扑解析 |

拓扑草案仍保留 `P0_TOPOLOGY_UPDATED_PENDING_GEOMETRY_VALIDATION` 状态。用户已确认的人工检查与本轮采样复核应单独记录；后续生成 resolved 文件时保留来源状态及验证记录，避免简单改字符串后丢失验证依据。

CSV 已被 Godot 以 `csv_translation` 导入，生成了多个 `.translation` 文件。这些不是拓扑解析产物；P1 使用 JSON 作为权威输入即可。CSV 的导入用途可随后整理，本轮未删除文件。

## 3. 本轮复核证据

| 检查项 | 结果 |
| --- | --- |
| 标记数量 | P=6、A=3、J=9、T=22、B=32，总计 72 |
| 引用完整性 | 无缺失引用、无未使用标记 |
| 坐标一致性 | 世界与腔体局部坐标差为 0；保存场景与 JSON 最大位置误差约 `3.01e-6 mm` |
| 分支数量 | 32 条，其中自然分支 30 条、接口过渡 2 条 |
| 展开图 | 72 个顶点、71 条边、1 个连通分量、无环、无重复边 |
| 末端 | T_01–T_22 的度数全部为 1 |
| 采样几何 | 37 条折线：主线 1、膀胱过渡 1、人工通道 3、B 分支 32 |
| 采样密度 | 最大间距 0.25 mm，共 2,447 个点；未发现采样点位于腔外 |
| 特别关注的接点 | J_05 度数为 9；J_01、J_02、J_09 度数为 5 |
| 特别关注的过渡 | B_31 长约 9.205 mm；B_32 长约 2.844 mm |

以上几何复核针对 JSON 所定义的折线。它与人工检查一致，但不等于证明任意拟合样条也处于腔内，更不等于证明具有半径的器械全程安全。符号距离判断还依赖闭合网格无自交的假设；本轮没有做完整自交检测。

本轮没有重新运行图形界面，也没有重新验证视频输出。现有 P0 的图形和录像记录沿用此前工作，不将本次数据检查当作渲染验证。

## 4. P1 的推荐推进顺序

### P1.1 固化输入和重建 resolved 数据

建议新增 `godot_sim/tools/resolve_cavity_topology.py`，读取现有两份 JSON，不修改人工拓扑，生成缺失的 `cavity_topology_resolved.json`。

派生文件至少包括以下信息；这是建议结构，尚未实现：

- 输入文件、网格文件的路径和 SHA-256；schema、单位、坐标字段。
- 名称到腔体局部坐标的节点索引。
- 每条路径的 ID、类型、有序标记名、坐标折线、分段长度和总弧长。
- 主腔室、膀胱过渡、三条人工通道以及 32 条 B 分支，合计 37 条路径。
- 节点邻接、分叉邻接关系；原始拓扑状态、人工确认来源和采样复核记录分别保存。

先以现有折线进行弧长重采样，保留原控制点。不优先改成三次样条，因为新曲线可能越过弯曲腔壁；确需平滑时重新检查采样点并保留几何约束。

**验收：**所有 72 个名称均解析；37 条路径完整；图仍是连通无环结构；新派生文件可以由同一输入重建。

### P1.2 把中心线标签转换为表面掩码

标记位于腔内，不能直接作为固定顶点集合。需要建立“每个表面顶点属于哪条分支／接点邻域、形变量权重多少”的映射。

建议先生成调试掩码，颜色显示以下区域：

| 区域 | 初始边界策略 |
| --- | --- |
| 三条人工通道 `BASE -> END` | 明确选出对应管壁和封闭端帽，顶点位移固定为零 |
| `P_BLADDER_BASE -> A_Start` | 从固定管壁平滑过渡到主腔室的形变权重 |
| B_31：`J_05 -> B_31_P01 -> P_IN_01_BASE` | J_05 侧与自然区连续，BASE 侧逐渐降到零 |
| B_32：`J_09 -> B_32_P01 -> P_IN_02_BASE` | 同上，按本段局部弧长设计过渡 |
| 主腔室 A 与 B_01–B_30 | 可形变区域；幅度由配置控制 |
| J 接点邻域 | 相邻分支共同作用，并做连续性处理 |
| T 末端及端帽 | 自然末端，不能全部当成固定入口；单独检查末端形变方向和圆滑程度 |

固定掩码应结合线段投影、局部管径、网格连接和从管壁种子开始的连通扩展来确定。仅用“离 BASE 点小于某个球半径”的做法，容易误冻住相邻自然组织。

B_32 只有约 2.84 mm，不能对所有接口统一使用 5 mm 等固定宽度。应从本段可用长度定义权重变化，并检查 J_09 邻域，防止扩大固定区或产生陡峭位移梯度。

对于靠得近、但拓扑上不相邻的分支，表面分区要受到拓扑和表面连通约束，避免单纯欧氏最近距离导致串区。J_05 有 9 条相邻路径，尤其需要看权重可视化。

**验收：**人工通道掩码覆盖实际管壁与端帽；接口没有大范围侵入自然区；非固定区权重连续；固定顶点数、过渡顶点数、区域面积有记录。

### P1.3 构造局部位移场

首轮先制作主腔室 A 和 B_01–B_05 子树的小幅静态形变，其余自然区域逐渐降权，接点周围保留过渡。通过后再扩展到全部自然分支；整个拓扑仍参与区域映射。

对于表面顶点 `x`，用中心线投影点 `c` 和局部切向 `t` 定义横向分量：

`r = (I - t t^T) (x - c)`

以区域权重和小幅系数构造位移候选：

`d_target(x) = gain(x) * r`

这只是首轮几何位移候选，不是组织力学方程。末端端帽和分叉邻域需要额外处理，不能无条件套用单根管道的径向公式。

分叉处使用拓扑相邻的多个候选场和连续权重，随后在表面网格上平滑**位移**，固定顶点施加严格零位移约束。可以用带目标约束的稀疏 Laplacian 求解作为初始方案；不要直接平滑原始顶点位置，否则可能产生无关的整体收缩。

首轮建议将最大位移限制在约 0.2 mm 作为数值调试值，再按几何检查逐步调整。这是演示工程参数，不是生理扩张量；最终幅度不能只靠“看起来明显”决定。

**验收：**局部位移方向可视化可读；固定区保持零位移；接点无明显跳变；首轮小幅目标形态通过几何检查。

### P1.4 导出同拓扑形态并验证插值

生成 `reference`、`mid`、`expanded`，保持同一参考顶点及面索引，不分别重建、简化或重排三个状态。

`mid` 可以先取同一有效位移场的 0.5 倍作为工程初版；若后续需要非线性形态，独立生成中间目标并再次检查分段插值。不能因为两个端点通过就认为所有中间状态有效。

对 `u=0、0.25、0.5、0.75、1` 至少检查：

- 固定区最大位移和全体最大位移；固定区工程误差目标不大于 0.01 mm。
- 面数／顶点数／面索引一致，法线正确，无退化面；检查局部折叠和三角形自交。
- 腔体封闭性、方向一致性和容积随设定充盈度增长。
- 三个人工通道的几何位置和形状保持稳定，接口过渡连续。
- J_05、J_09、B_32 和 T 端帽的局部特写。

单纯比较新旧三角面法线点积，只能作为局部异常提示，不能单独证明没有折叠／自交。整体容积增加也不能替代局部有效性检查。

Godot 导入 OBJ 后可能拆分或重排顶点，不能把 Python 的第 i 个顶点直接当成 Godot 导入网格第 i 个顶点。应建立参考坐标映射，或采用统一的网格数组构建流程，再在同一参考 surface 上创建 Blend Shape。原 OBJ 的 LOD／shadow mesh 也不能无检查地沿用到新形态。

### P1.5 独立预览和组织跟随

建议新增 `godot_sim/irrigation_deformation_preview.tscn`，提供参考／中间／扩张切换、充盈滑块、固定区／区域权重／位移着色，以及固定外部镜头。

先在独立腔体视图证明形变有效，再映射到组织内壁，并检查组织外表面响应、两层表面关系和局部壁厚。腔体与组织没有一一对应的顶点编号；组织映射可以复用连续控制场或单独建立空间映射。仅展示腔体的版本属于 P1 子里程碑，不算完成原计划中的组织适配。

P1 预览阶段不要求流量、压力、自动注排水时间线、移动内镜或动态碰撞。原 `main.tscn` 仍然使用静态组织和一次性碰撞，本轮不把它当作形变入口。

**验收：**同一镜头能稳定比较三态；掩码与位移可调试；组织映射检查通过后，进入 P2 注排水状态控制。

## 5. 建议文件与职责

以下是待实施清单，除本轮审计工具外尚未创建。

| 文件 | 内容 |
| --- | --- |
| `godot_sim/tools/audit_p1_inputs.py` | 本轮已完成：复核坐标、引用、图结构和采样折线 |
| `godot_sim/tools/resolve_cavity_topology.py` | 名称与坐标解析，生成缺失的 resolved 派生数据 |
| `godot_sim/deformation/cavity_topology_resolved.json` | 37 条有序路径、单位、来源哈希及验证记录 |
| `godot_sim/deformation/deformation_config.json` | 区域增益、固定规则、局部过渡规则、位移上限 |
| `godot_sim/tools/prepare_kidney_deformation.py` | 掩码、局部候选场、位移平滑、三态导出与几何检查 |
| `godot_sim/deformation/p1/` | 固定掩码、区域权重、参考网格、位移数组、目标形态及检查摘要 |
| `godot_sim/scripts/kidney_deformation_preview.gd` | 独立预览的滑块、状态选择、调试显示 |
| `godot_sim/irrigation_deformation_preview.tscn` | 独立 P1 验收场景 |

预处理数组可使用 NumPy 容器供 Python 保存；Godot 侧另导出明确可读取的 JSON／二进制格式或网格资源，不能默认 GDScript 可以直接读取 `.npz`。

## 6. 当前可运行的复核命令

在仓库根目录运行：

```powershell
& 'E:/Apps/Conda/miniconda3/envs/FURS/python.exe' godot_sim/tools/audit_p1_inputs.py
```

工具仅读取标记、拓扑草案、保存场景和腔体 OBJ，并写入被 Git 忽略的分析报告。它不会生成 resolved 文件，也不会更改标记、连接、源网格或场景。

本轮建议立即开始的实现顺序是：**resolved 派生数据 → 固定／过渡掩码可视化 → 主腔室及一组分支的小幅位移 → 三态检查 → 全自然分支与组织映射**。不需要先回到 Godot 继续添加大量标记。

## 7. 实现参考

- [Godot ArrayMesh](https://docs.godotengine.org/en/stable/classes/class_arraymesh.html)：Blend Shape、surface 数组和形变包围盒。使用同一参考网格数组构建目标，注意法线／切线数据要求。
- [Godot MeshDataTool](https://docs.godotengine.org/en/stable/classes/class_meshdatatool.html)：网格顶点、边与面的访问接口。
- [SciPy 图 Laplacian](https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.csgraph.laplacian.html)：图邻接到 Laplacian 的接口；约束位移求解方案属于本项目工程建议，不是该接口自动提供的形变模型。

本机 scipy 版本为 1.15.3；正式实现使用已安装版本支持的接口，并以当前 Godot 4.7 实机检查为准。
