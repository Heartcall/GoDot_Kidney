# P2.1＋P2.2 实施结果：输入固化与注排水时间控制

日期：2026-10-14。**功能与几何正确性检查通过，待用户人工验收；连续播放性能尚未解决。** 本轮没有开发 P2.3 完整面板、P2.4 三轮自动演示或 P2.5 完整性能验收，也未进入 P3/P4。

P1.5-R2 的正式人工验收记录已写入新 manifest，历史研究报告、候选状态文字和旧测试未改。已验收的腔体与组织几何完全复用，没有重新求解位移场或改变 0.2 mm 腔体幅度。

## 1. 正式输入与可独立运行的资源

[验收清单](../godot_sim/deformation/p2/accepted_inputs.json)的版本为 `p2.1-p2.2-v1`，记录用户于 2026-10-14 验收 P1.5-R2，来源、单位、形状、数据类型、显示原点与哈希。

| 输入键 | 权威 SHA-256；固化副本逐字节一致 |
| --- | --- |
| `cavity_reference_vertices` | `f137add4c401fe63851565f913a93968c9b11e18e630722ed42a21b4d0842fa1` |
| `cavity_faces` | `dbf4771365f42398f329100e695dc8580f8c038c557c671c02724bff45b29c3d` |
| `cavity_displacement` | `fbe95cfeaf8b77d80c5aa850618ad8ce8439c8ef770719b1f9a1f1789b050573` |
| `tissue_reference_vertices` | `63ce22d71be21c2a1266933aac2112ab7c66bcd887312f81e1d7d87c4f9ecb20` |
| `tissue_faces` | `532034f649eac73d2c28ecba5f0097ba04b79164fea3e385de5518c098cc3a05` |
| `tissue_displacement` | `bcef3bda21aa3621547a80f8d7902c7506fc638cd8c18fe6a8c8c5516491eaec` |

六份 `.npy` 正式副本位于 `godot_sim/deformation/p2/runtime/`，组织数据已从忽略的研究缓存导出到不被 Git 忽略的新目录。预览只读取此处两份二进制与 manifest；不读取 OBJ、R1 位移或本地分析缓存。NPY 保留原始 float64 参考顶点／位移和原面索引，二进制是明确记录的 float32 显示派生资源。

二进制 SHA-256：

- cavity.bin：`d6f93030493f82b3cd6b14e17fa7cc8921a94ca52767548b3e177f95d4819b8a`。
- tissue.bin：`7867296f685a3f630970f6fa1c228d84d8283d30f5339a2c2866b293b67b4cbb`。

格式见 [资源说明](../godot_sim/deformation/p2/README.md)。从正式副本连续重建两次，六份 NPY、两份二进制及 manifest 均逐字节一致。缺失或错误权威哈希会停止；代码没有组织映射求解入口。

另外建立只含新资源、脚本、剖切 shader 和最小 project.godot 的隔离工程，实际启动并导出双网格成功；其中没有复制原分析缓存。这是隔离加载验证，没有声称已创建远程 Git 克隆。新文件需与代码一起纳入仓库提交，运行不需要 `analysis/`。

## 2. 双网格播放模块

新增 [deformation_player.gd](../godot_sim/scripts/p2/deformation_player.gd)，公开 `set_filling(u: float)`，不含注排水状态、计时器或碰撞。

每次从参考坐标重建：`reference32 + float32(u)*displacement32`。两份网格共用 `[16,16,-81] mm` 显示原点、同一 `u`，同一帧提交；顶点编号、面拓扑与既有 Godot 绕序保持。实时法线从当前几何重新计算。重复相同 `u` 不重建；显隐、剖切与暂停不额外提交几何。没有 240 Hz 物理更新回调。

实际 Godot ArrayMesh 导出验证共 40 份：两个后端各 20 份，含五档、0.37、状态控制器驱动的 0.15625、重置、排水恢复和重复恢复。全部坐标与 Python float32 基准逐值一致、面索引完全一致。返回 0 的坐标字节与首次 Reference 相同。

五档实际坐标与原 R2 图形运行输出的坐标／索引 SHA-256 相同。法线有限、单位长度误差小于 2e-6；相对独立 Python 当前几何法线的最大角度偏差约 0.021566°。

## 3. 状态控制与时间语义

新增 [irrigation_controller.gd](../godot_sim/scripts/p2/irrigation_controller.gd)。它只维护唯一充盈度、状态、目标、游戏时间和独立 paused 标志，不访问顶点。

| 当前操作 | 行为 | 完成状态 |
| --- | --- | --- |
| 注水 | 从当前 u 到目标；完整行程 6 游戏秒，部分行程按距离比例 | HOLDING |
| 排水 | 从当前 u 到 0；完整行程 6 游戏秒 | RESTORED |
| 保持 | 取消运动段，固定当前 u，清除暂停 | HOLDING |
| 暂停／继续 | 冻结／继续同一段 elapsed，保留剩余过程 | 保持原运动状态 |
| 手动设置 u | 取消自动运动，按 0～1 夹取有效值 | HOLDING |
| 重置 | 取消运动和暂停，立即返回 u=0 | REFERENCE |

注水曲线为 `s=clamp(elapsed/duration,0,1)`、`u=start+(target-start)*(3s²-2s³)`。从 0 开始注水的 1.5／3／6 游戏秒对应 u=0.15625／0.5／1。目标与实际值独立，修改目标只作用于下一次注水；目标低于当前值时注水命令保持当前值，不隐式排水。

反向从实际当前值重新开始，位置连续，不保证速度连续。相同运动命令重复点击不会重置时间，暂停中重复同一命令也不会偷偷继续。没有 Tween、延迟任务或异步回调写入控制器，因此旧任务不会随后覆盖新命令。非有限手动值／目标和非正、非有限时间增量被拒绝／忽略；零行程立即停止。端点时间使用 1e-9 相对时间舍入阈值，使分步累计达到目标时端点状态精确；没有放宽任何几何门禁。

该曲线仅表示演示时间，不是真实压力、流量或容积模型。

## 4. 自动测试与几何回归

- Godot 原生状态检查：74 项，失败 0。覆盖 30／60／120 Hz 和不等步长在共同观察时刻的结果、保持与暂停、反向、重置、手动接管、重复命令、异常时间增量及八轮控制器往返。
- 新增 Python 测试：14 项，失败 0、错误 0。覆盖固化、重建、二进制布局、几何、真实运行与隔离项目。
- 真实 `_process(delta)` 单轮注水—暂停—继续—排水已通过；所有观察帧两份网格 u 一致，暂停无重建，最终精确恢复 Reference。
- 旧 R2 测试首次重跑 26 项通过；用户保存显隐设置后的最终重跑为 25 项通过、1 项旧文件哈希检查失败。失败只涉及下文用户确认的显隐变化，旧测试和历史保护清单均未修改，不将其伪报为全通过。

下表组织质量本轮由正式 float64 副本重新计算；接触列沿用已验收有限三角形扫描结果，以输入和实际输出逐字节一致性证明没有回归：

| u | 最大边梯度 | 面积比范围 | 退化／翻面 | 确认相互穿越／组织自交 |
| --- | --- | --- | --- | --- |
| 0 | 0.000000000 | 1.000000000～1.000000000 | 0／0 | 0／0 |
| 0.25 | 0.028185659 | 0.972207313～1.028131432 | 0／0 | 0／0 |
| 0.5 | 0.056371317 | 0.944608932～1.056699069 | 0／0 | 0／0 |
| 0.75 | 0.084556976 | 0.917232674～1.085698711 | 0／0 | 0／0 |
| 1 | 0.112742635 | 0.890109678～1.115126448 | 0／0 | 0／0 |

两种后端实际 float32 组织坐标也重新检查了面积、梯度、退化与翻面，均通过原门禁。连续区间面积界限仍为约 0.887786～1.115126，法线方向连续且不反转；本轮使用同一参考与位移，因此继承原解析结果。

固定与接触约束：

- BLADDER／IN_01／IN_02 固定顶点分别 2793／397／485，合计唯一顶点 3675；位移字段严格零，所有实际输出保持原位。
- 139 个真实共点目标仍与腔体位移精确一致；126104 个远区锚点仍严格零位移。
- 3840 个原接触样本的重心插值相对位移最大约 2.908e-17 mm。
- 原有 float32 共面接触配对数五档为 42／41／42／41／40，确认穿越均为 0，按原记录保留。这些是接触，不冒充新增穿透；旧 58／23 对候选也未改称真实交叉。
- 腔体 B_24 原始 `[1856,1862]` 问题记录保留，未修改源面或位移。

**接触验证范围：没有重新执行大规模全配对扫描。** 六份权威数组和五档实际 Godot 坐标／面索引完全相同，因此有限三角形结果没有几何变化；容差保持原值。本轮新增了约束、质量与输出一致性检查，没有删除候选或扩大容差。五档扫描仍不能证明所有连续 u 的无碰撞性。

## 5. 初步性能：明确未解决

Godot 4.7 stable，NVIDIA RTX 4070 Ti；下列是每次坐标、实时法线、ArrayMesh 创建／提交及回读的同步 CPU 总耗时，不是 GPU 完成时间或完整帧时间：

| 后端 | 最小 ms | 平均 ms | 最大 ms |
| --- | --- | --- | --- |
| forward_plus | 61.865 | 63.101 | 65.380 |
| gl_compatibility | 56.714 | 59.593 | 65.454 |

这已超过稳定 30 fps 所需的 33.3 ms 单帧预算，连续播放存在卡顿。真实单轮测试包含 12 游戏秒运动、0.3 游戏秒暂停及截图等待，实际等待约 25.382 秒；**6 游戏秒不是本机当前可保证的 6 墙钟秒**。本项目保留原 240 Hz 配置，未为了缩短等待修改项目设置或改用墙钟驱动。

没有测完整 FPS/P95，也没有把性能问题视为解决。后续应在维持精确几何和当前法线的条件下优化更新路径，再进入完整性能验收；不通过降低位移、简化网格或跳过检查掩盖问题。

## 6. 受保护文件检查

本轮开始建立 752 个旧文件的哈希清单，包含原资产、Marker 场景、拓扑、掩码、已验收字段、旧结果、主场景和旧脚本。

最终发现 `irrigation_asset_check.tscn` 仅在 `TissueReference` 节点新增 `visible=false`。用户已在本轮明确确认这是自己在 Godot 中保存的设置，并允许必要调整；这里保留用户设置。移除该唯一显示行后，重建字节的 SHA-256 与原始保护哈希一致，证明 Marker、坐标、变换和其他场景内容没有变化。

授权记录见 [authorized_workspace_changes.json](../godot_sim/deformation/p2/verification/authorized_workspace_changes.json)。此记录只识别这一项已确认的确切前后哈希，不能允许其他改动；旧保护清单未重置。其他 751 个旧文件哈希不变，未授权差异为 0。`main.tscn`、内镜碰撞脚本、原始 OBJ 与六份源数组未改。

## 7. Godot 操作说明

1. 在原项目打开 `res://irrigation_control_preview.tscn`，按 **F6** 运行当前场景；不要按 F5 启动旧主场景。
2. 初始为 REFERENCE、u=0。点击“注水”到 1，自动进入 HOLDING；点击“排水”返回 0，进入 RESTORED。当前性能下等待时间会长于显示的游戏秒数。
3. 运动途中点击“暂停/继续”，检查 u 和剩余时间冻结／恢复；点击“保持”结束当前运动，此后不会自动继续或排水。
4. 拖动充盈度滑块或点击 Reference／Mid／Expanded 接管到 HOLDING；“重置”回到 REFERENCE。屏幕显示实际状态、u、目标和剩余游戏秒。
5. 腔体与组织可分别显隐；默认不透明 X 剖切，下面滑块移动剖切平面；剖切没有封口，不代表真实壁厚。
6. 左键旋转、中键平移、滚轮缩放、R 恢复全局视角。状态切换和滑块本身不改变镜头，可在同一视角比较。

真实截图：[参考剖切](../godot_sim/deformation/p2/verification/reference_section.png)、[扩张剖切](../godot_sim/deformation/p2/verification/expanded_section.png)、[扩张外表面](../godot_sim/deformation/p2/verification/expanded_solid.png)、[注水中](../godot_sim/deformation/p2/verification/injecting.png)、[真实播放暂停](../godot_sim/deformation/p2/verification/live_paused.png)。

## 8. 实际新增文件

- `godot_sim/deformation/p2/accepted_inputs.json`、`runtime/` 六份 NPY／两份二进制、`evidence/` 约束与已验收质量记录、`README.md`。
- `godot_sim/scripts/p2/deformation_player.gd`、`irrigation_controller.gd`、`control_preview.gd`。
- `godot_sim/irrigation_control_preview.tscn`。
- `godot_sim/tools/p2/prepare_runtime.py`、`test_controller.gd`、`validate_runtime.py`、`test_p2.py`、`prepare_clean_checkout.py`、`write_result.py`。
- `godot_sim/deformation/p2/verification/` 本轮日志、数值报告、哈希与截图；这些是交付证据，不是形变输入。
- 本报告。大的实际网格导出与隔离工程位于忽略的 `analysis/irrigation_baseline/p2/`，可按下列步骤重建，正常预览不依赖它们。

## 9. 可重复执行命令

在仓库根目录用 PowerShell 执行；路径按当前机器记录。

```powershell
$p2Python = 'E:/Apps/Conda/miniconda3/envs/FURS/python.exe'
$p2Godot = 'E:/Apps/Godot/Godot_v4.7-stable/Godot_v4.7-stable_win64_console.exe'
& $p2Python godot_sim/tools/p2/prepare_runtime.py
& $p2Godot --headless --path godot_sim --script res://tools/p2/test_controller.gd
& $p2Godot --path godot_sim res://irrigation_control_preview.tscn -- --p2-validation-dir=res://analysis/irrigation_baseline/p2/godot_forward
& $p2Godot --path godot_sim --rendering-method gl_compatibility res://irrigation_control_preview.tscn -- --p2-validation-dir=res://analysis/irrigation_baseline/p2/godot_compatibility
& $p2Godot --path godot_sim res://irrigation_control_preview.tscn -- --p2-live-smoke-dir=res://analysis/irrigation_baseline/p2/live
& $p2Python godot_sim/tools/p2/prepare_clean_checkout.py
& $p2Godot --path godot_sim/analysis/irrigation_baseline/p2/clean_checkout --rendering-method gl_compatibility res://irrigation_control_preview.tscn -- --p2-validation-dir=res://verification
& $p2Python godot_sim/tools/p2/test_p2.py
& $p2Python godot_sim/tools/p2/validate_runtime.py godot_sim/analysis/irrigation_baseline/p2/godot_forward godot_sim/analysis/irrigation_baseline/p2/godot_compatibility
```

初次资源固化已经完成，不要在此目录再次使用 `--from-approved`；普通 rebuild 仅使用已固化文件。隔离工程命令不会复制旧分析输入。新的克隆没有本机开工保护快照时，仍会核对权威六哈希与资源证据；本次旧文件保护记录已随交付归档。

本次日志保存在 `verification/`；若需重新归档报告，先将测试输出保存到对应日志文件再执行 `write_result.py`。旧 R2 测试依赖历史诊断缓存，作为本机附加回归；不是新预览的运行依赖。

## 10. 剩余问题与停止位置

当前可交付 P2.1/P2.2 的输入、播放、状态控制和最小预览，等待人工验收。性能是明确待解决项：建议下一批先确认更新路径优化范围，再开展 P2.3 完整面板；P2.4 三轮自动往返、P2.5 完整性能验收仍未开发。

F03/F04 的材料归属、真实壁厚、连续碰撞证明和生理标定仍未完成。本轮没有添加真实水压、mL/s、动态碰撞、内镜控制、自动录像或 P3/P4 功能。
