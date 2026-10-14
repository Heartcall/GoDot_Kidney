# P2.3 完整交互面板与连续播放测量结果

日期：2026-10-14。**P2.3 功能、状态与几何回归通过，等待用户人工验收；本机量化性能仍未达到稳定 30 FPS。** 本轮没有进入 P2.4 三轮自动演示、P2.5 最终性能验收或 P3/P4。

## 1. 本次人工验收记录与基准保护

用户于 2026-10-14 正式验收 P2.1＋P2.2：注水、排水、暂停／继续、保持、重置正常，腔体与组织同步，主观观察没有明显卡顿。

新建 [独立验收记录](../godot_sim/deformation/p23/p21_p22_acceptance.json)及 `deformation/p23/baseline/` 代码副本，保留验收时的 player、controller、preview 和场景文本。记录将“人工交互体验正常”与“尚未量化证明稳定 30 FPS”分开。此前 P2 报告、测试输出、性能记录和 `accepted_inputs.json` 没有覆盖或改写。

基准中另存只增加分段计时的旧 player，供本轮优化前对比和重放使用；它仍使用原参考＋位移与原法线算法，不是新几何成果。

## 2. 完整控制面板

新增 [irrigation_panel.gd](../godot_sim/scripts/p2/irrigation_panel.gd)，界面只调用已验收控制器并发送观察信号；不持有第二份充盈度，不访问顶点，不包含形变求解或注排水时间模型。

- 运行：注水、保持、排水、暂停／继续、重置，全部使用同一个 `irrigation_controller.gd`，该文件逐字节保持不变。
- 状态：中文状态及枚举名、当前百分比、下次目标、剩余游戏秒、是否暂停。运动中额外显示“本段目标”，防止编辑下次目标时误认为当前目标已改变。
- 参数：目标 0～100%，完整注水／排水时长各 0.1～120 游戏秒。拒绝非有限或越界参数；合法修改仅影响下一次命令，当前运动段的起点、目标和 duration 不变。
- 手动：0～1 滑块、Reference／Mid／Expanded 均通过控制器接管并进入 HOLDING；动画反映滑块使用 `set_value_no_signal`，不会触发手动接管。
- 观察：腔体／组织独立显隐、不透明 X／Y／Z 剖切、局部定位剖切、位置滑块、相机旋转／平移／缩放／复位。
- 定位：ALL、MAIN、J_01～J_09、T_01～T_22、B_31、B_32、BLADDER、IN_01、IN_02、F01～F04，共 42 项含 ALL。只改变相机和剖切参数，不改变 u、状态或几何。

独立入口仍为 [irrigation_control_preview.tscn](../godot_sim/irrigation_control_preview.tscn)。根界面改为左侧滚动面板与右侧独立 SubViewport，模型不再被控件覆盖。模型、共同显示原点和局部坐标没有改变。常用 1024×768、1280×720、1422×1066、1920×1080 窗口均实际渲染并检查了布局；高度不足时纵向滚动，无横向控件重叠。图像位置以窗口／逻辑视口实测为准，项目原有 canvas_items 缩放配置保持。

## 3. 先测量，再做小范围优化

真实连续测量确认旧播放路径每次调用两次 `surface_get_arrays()`，把实际 ArrayMesh 数据回读到从未用于正常显示的 `last_arrays`。Forward+ 优化前该回读约占每次双网格更新 14～16 ms。

本轮仅做两项低风险优化：

1. 删除正常播放中的诊断回读和 `last_arrays` 保存；显式验证导出仍从真实 ArrayMesh 回读。
2. 将不随形态改变的顶点颜色数组缓存到加载阶段，避免每帧重新分配与填充。

坐标生成、float32 运算顺序、顶点／面编号、实时法线算法与 ArrayMesh 创建路径保持。没有减面、减小幅度、降低精度、跳过法线、引入 GPU 形变或调整物理／项目设置。

所有优化前、首轮优化后及最终面板测量分别存放，早期原始样本未覆盖。对比表中的回读次数是一次完整注水＋排水的总次数：

| 测量版本／运动 | FPS 均值 | 双网格更新均值 ms | 测量段内回读次数 |
| --- | --- | --- | --- |
| baseline_forward · fill | 14.57 | 67.333 | 722 |
| baseline_forward · drain | 13.85 | 70.720 | 722 |
| baseline_compatibility · fill | 16.60 | 58.529 | 722 |
| baseline_compatibility · drain | 16.75 | 58.026 | 722 |
| final_forward · fill | 18.49 | 52.715 | 0 |
| final_forward · drain | 18.40 | 52.943 | 0 |
| final_compatibility · fill | 19.00 | 50.964 | 0 |
| final_compatibility · drain | 18.94 | 51.168 | 0 |

这些是本次单轮对照数据，不是多次实验的统计显著性结论。历史约 60 ms 的离散测量仍保留原值，不以本轮连续结果覆盖它。

## 4. 最终真实连续性能

设备：Windows，Intel Core i7-13700KF，NVIDIA RTX 4070 Ti；Godot 4.7 stable official。Forward+ 使用 Vulkan，Compatibility 使用 OpenGL。窗口 1422×1066，模型 SubViewport 1034×1066，VSync 模式 1，Engine.max_fps=0，time_scale=1，原项目物理 240 Hz、每帧最多 8 步设置未改；测量结束时窗口具有焦点。

方法：预热三个姿态和 20 个空闲帧，随后由正常 `_process(delta)` 驱动完整注水、排水，各 6 游戏秒、目标 1。控件调用与日常播放相同的控制器；不是强制推进时间的离散 set_filling 测试。采样段内不截图、不导出网格、不做诊断回读。

帧时间使用低优先级之后的晚执行 `_process` 回调中的单调墙钟间隔，包含当前 CPU 更新和上一轮渲染间隔；它是实际运行循环的帧率，**不是 GPU 时间戳或显示器 present 轨迹**。首尾样本保留。FPS 均值是逐帧 `1000/间隔ms` 的算术均值，报告也保留帧数／总墙钟时间的加权值。完整原始数据与所有组件的均值、中位数、P95、最大值见 [性能 JSON](../godot_sim/deformation/p23/verification/performance_report.json)。

| 后端／运动 | FPS 均值／中位数／最低 | 帧时间中位数／P95／最大 ms | 6 游戏秒对应墙钟秒 |
| --- | --- | --- | --- |
| Forward+ 注水 | 18.49／18.43／17.53 | 54.253／55.507／57.029 | 9.795 |
| Forward+ 排水 | 18.40／18.40／17.31 | 54.338／55.685／57.756 | 9.838 |
| Compatibility 注水 | 19.00／19.02／17.18 | 52.585／53.893／58.206 | 9.530 |
| Compatibility 排水 | 18.94／18.97／13.45 | 52.702／54.385／74.374 | 9.512 |

| 后端／运动 | 双网格更新均值／P95／最大 ms | 大于 50 ms 的帧／总采样帧 |
| --- | --- | --- |
| Forward+ 注水 | 52.715／54.125／55.574 | 181／181 |
| Forward+ 排水 | 52.943／54.197／56.340 | 181／181 |
| Compatibility 注水 | 50.964／52.208／56.608 | 181／181 |
| Compatibility 排水 | 51.168／52.782／71.972 | 180／180 |

组件均值：

| 后端／运动 | 坐标 ms | 法线 ms | 颜色绑定 ms | ArrayMesh 创建 ms | 提交 ms | 回读 ms |
| --- | --- | --- | --- | --- | --- | --- |
| Forward+ 注水 | 4.099 | 36.091 | 0.003 | 12.344 | 0.053 | 0.000 |
| Forward+ 排水 | 4.076 | 35.960 | 0.003 | 12.724 | 0.054 | 0.000 |
| Compatibility 注水 | 3.979 | 36.266 | 0.002 | 10.564 | 0.075 | 0.000 |
| Compatibility 排水 | 3.991 | 36.383 | 0.002 | 10.636 | 0.073 | 0.000 |

颜色数组生成已移到初始化，表中只是每帧绑定缓存的耗时。ArrayMesh 创建包含 `add_surface_from_arrays` 的同步调用；提交是将新 mesh 分配给两个节点，不包含异步 GPU 完成时间。各组件之和与总计之间还有循环、字典、分配等少量开销。

结论：本次最终约 18～19 FPS，P95 帧时间约 54～56 ms，**不满足稳定 30 FPS／33.3 ms 帧预算**。虽然用户主观体验可接受，但不将其改写为量化达标。当前法线约 36 ms、ArrayMesh 创建约 11～13 ms，是主要剩余瓶颈。

游戏秒与墙钟秒区别也已实测：引擎提供的 delta 与墙钟间隔不同，当前 240 Hz／8 步配置和采样中的游戏时间推进相符；本轮未修改这些设置，未改为墙钟驱动掩盖低帧率。6 游戏秒实际约 9.5～9.8 墙钟秒。

## 5. 长帧位置

以墙钟帧间隔大于 50 ms 为工程筛查标记。当前几乎所有更新帧都超过该值，属于持续帧预算不足，不能只称为偶发尖峰。下面列出各段最慢帧；完整列表记录了帧编号、阶段、阶段墙钟时间、u 和组件耗时。

| 后端／运动 | 段内帧编号（从 0） | 段内墙钟秒 | u | 帧时间 ms |
| --- | --- | --- | --- | --- |
| Forward+ 注水 | 126 | 6.847 | 0.785701 | 57.029 |
| Forward+ 排水 | 165 | 9.022 | 0.017304 | 57.756 |
| Compatibility 注水 | 19 | 1.055 | 0.031869 | 58.206 |
| Compatibility 排水 | 110 | 5.864 | 0.327250 | 74.374 |

这里“位置”是播放时间与充盈度，不是解剖热点。每次更新都会处理整个双网格，不能从这些样本声称某个天然分支单独导致卡顿。Compatibility 排水的最大尖峰主要出现在法线与坐标计算段；没有绕过或剔除该帧。

## 6. 状态与几何回归

- 未修改的控制器通过原有 74 项状态／时间检查，结果写入新的 P2.3 目录。
- 两个后端的最终面板检查各 83 项通过：按钮、参数不中断当前段、非法参数拒绝、滑块不被程序回调接管、暂停零更新、保持、反向、三态、显隐、全部定位、局部剖切方向及四种窗口布局。
- 新增 Python 自动测试 13 项通过。
- 两个后端共 32 份实际 ArrayMesh 输出，覆盖五档、0.37、返回 0 与重置。坐标与已验收 float32 公式逐值一致，面索引不变；五档法线字节也与 P2.1＋P2.2 的实际输出完全一致。
- 3675 个腔体固定顶点严格不动；139 个真实共点精确一致，126104 个远区锚点仍为零；3840 个原接触样本相对位移最大约 2.908e-17 mm。
- 六份权威 SHA-256 和旧输入 manifest 不变。五档组织面积比、边梯度、退化与翻面重新核对通过，实际 float32 输出也通过原门禁；连续面积／法线方向结论继续有效。

有限三角形接触检查按原输入与实际五档坐标／索引逐字节一致性继承；没有重新跑大规模全配对扫描，没有增大容差或删除候选。原 float32 共面接触、旧误报候选以及 B_24 原始 `[1856,1862]` 记录保留，不改称新增穿透。五档检查仍不证明整个连续区间无碰撞。

[几何与状态报告](../godot_sim/deformation/p23/verification/regression_report.json)保留全部实际输出记录和布局数据。

## 7. 受保护文件

本轮冻结 808 个既有文件的开工哈希。允许修改的只有独立 preview 场景、`control_preview.gd`、`deformation_player.gd`，实际恰好这三项有改动，其他 805 项哈希不变。原始 OBJ、Marker、拓扑、P1.2 掩码、已验收 P1.5/P2 数据与历史报告、main.tscn、碰撞脚本均未变。

用户已确认的 `TissueReference.visible=false` 在本轮开工时即是当前基准，本轮保持原样，没有再次当成失败，也没有回写该场景。开工前已有的 Godot 图片 `.import` 文件保留。

## 8. 操作说明

1. 打开 `res://irrigation_control_preview.tscn`，按 **F6**；F5 仍启动原主场景。
2. 在左侧设定目标百分比、完整注／排水游戏秒，点击注水或排水。中途修改参数后，当前段继续原目标；下一次命令采用新参数。
3. 暂停／继续保留当前段；保持结束当前段并固定当前值；重置回到 Reference。拖动手动滑块或使用三态按钮会进入 HOLDING。
4. 面板显示“下次目标”与运动中的“本段目标”，不要将实际当前值误当目标。
5. 向下滚动左侧面板可见观察控件：分别显隐、剖切方向和位置、定位选择与镜头复位。局部定位的任意剖切方向会保留，移动剖切滑块不会偷偷变回 X。
6. 在右侧模型区域左键旋转、中键平移、滚轮缩放，R 或复位按钮回到全局视角。定位和状态切换互不影响；三态比较保持当前镜头。

真实截图：[完整面板](../godot_sim/deformation/p23/verification/screenshots/expanded_panel.png)、[1280×720](../godot_sim/deformation/p23/verification/screenshots/layout_1280x720.png)、[1024×768](../godot_sim/deformation/p23/verification/screenshots/layout_1024x768.png)、[1920×1080](../godot_sim/deformation/p23/verification/screenshots/layout_1920x1080.png)、[F01 定位](../godot_sim/deformation/p23/verification/screenshots/F01_focus.png)。

## 9. 文件与复现

新增 `scripts/p2/irrigation_panel.gd`；修改 `scripts/p2/control_preview.gd`、`scripts/p2/deformation_player.gd`、独立 preview 场景。新增 `deformation/p23/` 验收、基准、定位元数据、验证报告与截图；新增 `tools/p23/` 的冻结、测量／UI 验证、回归、性能汇总与报告工具。正常预览不依赖忽略的 analysis 缓存，定位元数据已独立固化。

在仓库根目录执行：

```powershell
$p23Python = 'E:/Apps/Conda/miniconda3/envs/FURS/python.exe'
$p23Godot = 'E:/Apps/Godot/Godot_v4.7-stable/Godot_v4.7-stable_win64_console.exe'
& $p23Godot --headless --path godot_sim --script res://tools/p23/test_controller.gd
& $p23Godot --path godot_sim res://irrigation_control_preview.tscn -- --p23-regression=res://analysis/irrigation_baseline/p23/final_regression_forward
& $p23Godot --path godot_sim --rendering-method gl_compatibility res://irrigation_control_preview.tscn -- --p23-regression=res://analysis/irrigation_baseline/p23/final_regression_compatibility
& $p23Godot --path godot_sim res://irrigation_control_preview.tscn -- --p23-benchmark=res://analysis/irrigation_baseline/p23/final_forward --p23-tag=final_p23_ui_low_risk_optimized
& $p23Godot --path godot_sim --rendering-method gl_compatibility res://irrigation_control_preview.tscn -- --p23-benchmark=res://analysis/irrigation_baseline/p23/final_compatibility --p23-tag=final_p23_ui_low_risk_optimized
& $p23Python godot_sim/tools/p23/check_results.py
& $p23Python godot_sim/tools/p23/summarize_performance.py
& $p23Python godot_sim/tools/p23/test_p23.py
```

如要保留本机当前原始样本，重测时给 `--p23-benchmark`／`--p23-regression` 换新目录名，再针对新目录分析。上面是从提交的归档与固化资源重建本轮默认诊断目录的方法；不要调用旧 P2 报告中的输出命令去覆盖历史目录。完整大网格导出保存在忽略的 `analysis/irrigation_baseline/p23/`，正式 JSON、原始帧样本、日志及截图已另存新版本化 verification 目录。

优化前基准可通过附加 `--p23-use-instrumented-baseline` 重测；它读取保存的旧计时版 player。验收冻结工具已执行，不要再次运行覆盖验收记录。

## 10. 下一轮最小优化方案与停止位置

本轮没有擅自做较大架构调整。若需要达到稳定 30 FPS，当前还需减少约 20 ms／帧，优先独立验证：

1. 将当前同序 float32 坐标／法线循环移到批量原生 CPU 实现，保留原三角面累加顺序和正确归一化；先做小型原型，不改输入与拓扑。
2. 单独评估复用显示缓冲或局部更新 ArrayMesh，避免每帧重建静态索引／颜色；必须先验证 Godot 属性格式与实际回读结果，不能假定更新接口等价。
3. 每项原型都重新导出五档及任意中间值的实际位置、索引、法线，核对固定区、精确恢复和接触／质量基准，再复测同协议真实连续 FPS。无法保持既有结果时应停止并报告。

如需 GPU 形变，应另提方案：保持同一参考＋位移、相同顶点编号与坐标精度，明确实时法线计算方式，建立 GPU 实际位置／法线读回与 CPU 基准对照，并验证五档与中间值；不能仅靠截图证明等价。本轮未实现或启用该路径。

本轮结束于 P2.3，等待用户 Godot 人工验收。F03/F04 解剖归属、真实壁厚、生理标定仍未验证；未开发真实压力／流量、动态碰撞、内镜交互、自动三轮循环或录像。
