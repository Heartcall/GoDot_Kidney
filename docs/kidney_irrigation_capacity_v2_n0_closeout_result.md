# N0 边界收尾：人工反馈记录与 C11 固定管壁精修

日期：2026-10-14。状态：**人工反馈已独立固化；C11 仍是首选工程测量代理，局部精修待用户确认。D2 未批准，天然有效容量仍未知，未进入 N1。**

本轮没有覆盖原 [N0 报告](kidney_irrigation_capacity_v2_n0_result.md)、候选计算或接触证据，也没有改动原始 OBJ、标记、拓扑、掩码、已验收形变、P2 运行资源、主场景及碰撞系统。只新增反馈记录、一个局部测量候选、验证和独立审核入口。

## 1. 正式人工审核记录

版本：[human_review_2026_10_14_v1.json](../godot_sim/deformation/capacity_v2_n0_closeout/human_review_2026_10_14_v1.json)。来源为用户本轮明确反馈，记录原候选和旧报告的哈希。再次构建只验证本记录一致，不覆盖或追加扩大解释；反馈改变时需另立版本。

| 对象 | 本轮状态 | 适用范围 |
| --- | --- | --- |
| C11 | `VISUAL_REVIEW_PASSED_D2_PENDING` | 用户所见 IN_02 金色封口在较窄人工管道，灰色排除部分包含应排除的人工结构；视觉通过，非全部天然域批准 |
| C06 | `REJECTED_BY_USER_NATURAL_WALL_REMOVAL` | 用户确认 IN_02 封口跨宽天然腔室、切除天然入口及应保留腔壁；拒绝作为最终天然容量域 |
| C01～C05 | `EXISTING_NATURAL_BRANCH_EXCLUSION_NOT_RECOMMENDED` | 保留既有天然路径／末端被排除的失败证据，不晋升 |
| C07～C10 | `NOT_INDIVIDUALLY_REVIEWED_WIDE_CHAMBER_RISK` | 未逐例人工审核；本轮另做几何比较，不伪造用户逐例结论 |
| BLADDER、IN_01 | 本次所见视角未见明显异常 | 不等于确认真实 UPJ、完整孔缘或所有人工结构均已排除 |
| 疑似穿模 | `NO_VISIBLE_ANOMALY_IN_USER_REVIEWED_VIEWS` | 当前人工检查未复现；非已修复、全模型或全连续区间无碰撞证明 |

### C07～C10 的独立计算复核

[逐例比较记录](../godot_sim/deformation/capacity_v2_n0_closeout/C07_C10_computational_review.json)比对了 IN_02 截面中心、法向、源切面集合、排除源面集合及截环点云：

- **C07、C09、C10**：IN_02 截环 Hausdorff 距离为 0，源切面和排除源面集合均与 C06 一致。因此它们使用同一被拒绝的 IN_02 几何，不推荐晋升；这是计算证据，不是新增人工观察。各自 BLADDER／IN_01 截面仍须按自身定义理解。
- **C08**：IN_02 截面不同，沿路径向天然侧移动约 0.085306 mm，面积约 96.710107 mm²，截环相对 C06 的 Hausdorff 距离约 0.438395 mm。仍属邻近宽腔室风险，不能自动通过，也没有把 C06 的人工拒绝直接复制为 C08 的人工结论。

旧候选 JSON 的历史状态不改写。本轮新场景叠加上述反馈，旧 N0 场景仍保留当时状态。

## 2. C11 内保留了什么，能否完整扣除人工容量

**不能完整确定。** 16.807273 mL 是含未知过渡贡献的工程测量代理。当前没有人工通道添加前的分割、可逆构造记录或逐源面的原始解剖归属，不能把 B 路径长度、最近路径标签或固定权重直接转换为独立人工体积。

| C11 内的结构 | 可核对的保留量 | 容量解释 |
| --- | --- | --- |
| BLADDER 远端固定管壁 | 无原固定面片保留，固定面面积为 0 | 远端固定管道已排除；不证明上游截止恰为真实 UPJ |
| BLADDER_TRANSITION | 名义中心线保留约 3.579165 mm，即原过渡路径的一半 | 天然肾盂／输尿管与人工连接的边界未确定，人工体积未知 |
| B_31 | 全长约 9.882074 mm 的过渡中心线保留 | 与 J_05 天然腔室融合，不能作为独立圆管积分或用 C06 差值替代 |
| B_32 | 全长约 2.843529 mm 的过渡中心线保留 | 临近 J_09／B_28 等天然结构，宽截面会删天然壁；人工体积未知 |
| IN_01 近端残留 | C11 截面在 BASE 向 END 方向 1 mm；保留 52 个全固定源面对应的面片，面积约 5.334007 mm² | 部分源面仅部分保留；固定面片是开放曲面，面积不能解释为容量 |
| IN_02 近端残留 | 同样截在 BASE 外 1 mm；保留 58 个全固定源面对应的面片，面积约 8.014417 mm² | 其中一段可建立可靠封闭差分体积，见下节；不等于全部残留人工体积 |

“中心线保留量”是拓扑路径的工程描述，不是独立人工管腔的材料长度；面数包含部分保留的源面。完整清单和轴向边界见 [C11_retained_structure_inventory.json](../godot_sim/deformation/capacity_v2_n0_closeout/C11_retained_structure_inventory.json)。

C11 与被拒绝 C06 的体积差为 **0.141620898 mL**。用户已确认 C06 删除天然腔壁，因此这个差值混入天然空间，**不能称为 C11 内人工过渡容量，也不能整块扣除**。

### 为什么不继续移动 IN_01／BLADDER

- IN_01 的固定／非固定混合源三角面，其轴向顶点最远达 BASE 外约 **1.007307 mm**；当前 C11 在 1 mm 处，已有 2 个截面源面不是全固定面。继续向天然侧移动，无法保证只裁人工固定管壁。本轮不做这种精修。
- BLADDER 的 C11 截面位于过渡路径中部，已经不在全固定远端管壁内部。用户所见正常不能唯一定位 UPJ；不能再以固定区规则推进。
- B_31、B_32 的根部与天然腔室共用连续壁面，没有可独立批准的人工孔缘。C06 的人工反馈进一步否定了“向内切到过渡段就能全部排人工”的推断。

到这里停止内移，不以追求更小容量为目标进行截面搜索。

## 3. 唯一新增局部候选：C11_R1_IN02_fixed_collar

候选目录：[C11_R1_IN02_fixed_collar](../godot_sim/deformation/capacity_v2_n0_closeout/domains/C11_R1_IN02_fixed_collar/candidate.json)。这是独立测量几何，不是正式腔壁，不参与 P2 播放、组织映射或碰撞。

### 3.1 截面依据

沿现有 IN_02 人工固定管道 BASE→END 轴计算源顶点投影。固定／非固定混合三角面的最大投影为 **0.849914657 mm**，其后的第一个全固定源顶点事件位于 **0.864919175 mm**。选择两事件之间的中点：

`IN_02 新截面轴向位置 = 0.857416916 mm`

这使所选环及新删除的壁面完全落在已验收 IN_02 固定管壁片内，同时远离顶点事件以保证裁切质量。它是源网格／质量驱动的选择，没有容量目标，不改 Marker 或原权重。BLADDER、IN_01 截面与 C11 保持完全相同。

### 3.2 体积与来源证明

| 指标 | 实际结果 |
| --- | ---: |
| C11 测量代理体积 | 16.807272913 mL |
| R1 测量代理体积 | **16.805962087 mL** |
| 本次可剔除固定管壁段的封闭体积 | **0.001310826 mL＝1.310826 mm³** |
| 新旧截面轴向间距 | 0.142583084 mm |
| 减少的源壁面积 | 1.589140104 mm² |
| 发生面积变化的源三角面 | 43 个，全部属于 IN_02 全固定源面 |
| 非全固定源壁的面积变化 | **逐值为 0** |
| 剩余人工过渡总容量 | **未知** |
| 正式 V_reference_effective | **未确定** |

体积差另通过对 C11 本身截出的封闭差分小块独立积分核对，两者一致到 1e-12 mL 以内。差分小块保存源面编号、参考坐标和独立封口标识；不能把这个局部量扩大为全部残留人工结构体积。

R1 后 IN_02 仍保留约 6.425277 mm² 的全固定源壁面片，IN_01 的上述面片也未改变。这些开放面片不能独立给出封闭容量；继续靠近非平面根部封口会引入新的、尚未批准的测量边界假设。本轮停止在可证明只删固定管壁的平面精修，不宣称穷尽所有几何封口方法，也不把它们当作原人工孔缘的恢复。

证明与原／新截环：[refinement_proof.json](../godot_sim/deformation/capacity_v2_n0_closeout/refinement_proof.json)。[43 个源面索引](../godot_sim/deformation/capacity_v2_n0_closeout/removed_fixed_collar_source_faces.npy)、`C11_source_wall_area_mm2.npy`、`R1_source_wall_area_mm2.npy` 支持逐面审计。

### 3.3 完整几何门禁

- R1 水密、绕序一致，单连通分量；边界边、非流形边及退化面均为 0。
- 虚拟封口与保留壁面、全部原始壁面及其他封口没有非预期有限交线／重叠；预期的同一切环交线作为构造边界记录，未扩大实际接触判定容差。
- 保留 31 条天然路径的采样中心线、34 个 A／J／T 标记；没有新排除的天然路径或末端。
- 原参考顶点逐值不动，新截点保存原顶点重心来源；源面映射、虚拟封口面索引、截环、排除部分及源哈希齐全。
- 对原参考网格做直接精修，与从 C11 提取的独立封闭差分体积核对。多个原点、trimesh 及三方向散度积分一致，数值误差低于原工程门禁。
- 最小三角面面积约 **8.983365×10⁻⁶ mm²**，当前法向有限，未通过删除异常面来通过检查。

这证明相对 C11 的精修只移除了固定人工面片上的壁面，**不补证 C11 本身已保留全部真实天然腔壁**。中心线保留也不能替代整面解剖归属。

### 3.4 已拒绝的首次尝试

初次仅在混合面最远投影外加数值余量，切面过近源顶点，产生 2 个面积低于门禁的极小面，尽管闭合且体积可核算，仍未通过。已保存为 [拒绝试验](../godot_sim/deformation/capacity_v2_n0_closeout/failed_attempts/near_boundary_gate_failure/REJECTED.json)，包含当时全部派生数据和失败画面。

随后改为上述相邻源顶点事件区间的中点，只改变新测量候选切面，未放宽退化阈值、删除三角面、修改原始数据或改变 0.2 mm 工程场。首次试验的 0.001380 mL 初算不作为最终交付量；最终使用 **0.001311 mL**。

## 4. T_01～T_22 与天然域的不确定性

全部末端继续使用原始封闭源表面，原 N0 的 [22 个末端清单](../godot_sim/deformation/capacity_v2_n0_research/terminal_boundary_inventory.json) 保持原样。没有资料判断这些面代表真实解剖终止、分割截断还是人为封口，也没有据此删除、移动或重新封闭末端。

因此当前体积包含“原重建模型在各末端闭合”的测量约定。如果封口位置截断了真实腔室，或包含了不应计入的空间，体积会相应变化，现有数据不能定量校正。需要原始分割／影像和终端解剖范围，不能将水密性当作末端解剖正确的证明。

## 5. 穿模反馈与旧检查的保留

本次用户反馈正式记为 **`NO_VISIBLE_ANOMALY_IN_USER_REVIEWED_VIEWS`**。此前疑似异常暂列“当前人工检查未复现，后续新形变需重新验证”，不称为已经修复。

原五档 u=0、0.25、0.5、0.75、1 及附加 u=0.37 的有限几何结论保持：未检出确认横向穿越，仍有点／边接触和共面重叠；共面配对面积和不是穿透面积或壁厚。没有新证据要求修改已验收腔体或组织位移，本轮没有重复无必要的大规模接触扫描。

新场景继续使用原 P2 播放器和相同充盈度。两个后端共 28 份实际 ArrayMesh 快照的位置、法线及面索引与原 N0／P2.3 基准完整二进制一致；这支持旧结论继续适用，**仍不构成整个连续区间无碰撞证明**。测量封口和被删除小块不会进入接触诊断模式的正式双网格。

## 6. 推荐边界与 N1 就绪判断

**本轮不宣布任何候选成为最终天然 D2。**

推荐将 C11 保留为用户视觉通过的首选父候选，提交 R1 作为进一步清除明确固定管壁段的保守工程候选。其 BLADDER、IN_01 边界沿用 C11；IN_02 采用源面分级和裁切质量依据的新截面；末端沿用原闭合源面。是否接受 R1 的测量边界由用户确认。

即使批准 R1 为工程测量代理，仍需明确保留 BLADDER_TRANSITION、B_31、B_32 及入口根部的未知贡献，不能将 **16.805962 mL** 自动命名为纯天然有效容量。

目前缺少以下证据：

1. 添加通道前的天然分割／模型，或包含逐面来源的可逆预处理记录。
2. 真实 UPJ／输尿管测量截止、人工入口孔缘和过渡根部的解剖边界，并能绑定到现有源面。
3. T_01～T_22 的分割／封口含义。

**尚不具备正式 N1 容量目标标定的条件。** 用户确认工程代理域之后，可以另外授权仅以该约定域开展参考尺寸、截面和局部形态描述；这与个体天然容量、正常 V_min/V_max 的标定分开。当前 N1 未启动，V_reference_effective、V_min、V_max 均未填写。

## 7. 新 Godot 收尾入口

打开 **`res://capacity_v2_n0_closeout_preview.tscn`，按 F6**。原 N0 场景保留历史状态，本轮反馈应在新入口查看。

1. 默认 C11，面板显示 `VISUAL_REVIEW_PASSED_D2_PENDING`；切换 C06 显示用户拒绝，不将其作为 D2。
2. 选择 `C11_R1_IN02_fixed_collar` 比较精修候选。切换候选保持同一镜头，模型只在 Reference 测量状态显示。
3. 左侧向下滚动，点击“定位 IN_02 侧面：比较旧／新截环”。橙环为 C11，青环为 R1，真实间距约 0.142583 mm。
4. “显示已计量 IN_02 固定管壁段”在 R1 中以青绿色单独显示被排除小块；C11 中只画比较环，不叠加共面的绿色表面，避免引入诊断显示闪烁。
5. 原有不透明剖切、旋转／平移／缩放、全部 J/T/F 定位、双模型显隐及旧 u 滑块保留。没有放大形变量或启用透明混合。
6. 接触诊断面板显示本次“用户审核视角未见异常”的限定结论。若后续再次看到异常，“保存审核现场”写入新的 `capacity_v2_n0_closeout/user_sessions/`，不写旧 N0 证据目录。

真实同镜头截图：

- [C11 侧面](../godot_sim/deformation/capacity_v2_n0_closeout/verification/forward/C11_collar_side.png)、[R1 及可移除管壁段](../godot_sim/deformation/capacity_v2_n0_closeout/verification/forward/R1_removed_fixed_collar_side.png)。
- [R1 全貌](../godot_sim/deformation/capacity_v2_n0_closeout/verification/forward/R1_measurement_candidate.png)、[C11 视觉通过记录](../godot_sim/deformation/capacity_v2_n0_closeout/verification/forward/C11_visual_pass_D2_pending.png)、[C06 用户拒绝记录](../godot_sim/deformation/capacity_v2_n0_closeout/verification/forward/C06_user_rejected.png)。

## 8. 测试、文件保护与复现

- Python：**19/19 通过**，包括人工结论边界、逐例风险复核、R1 全部门禁、固定源面差分、独立体积、天然路径／末端保留、原始坐标与重心映射、重复构建、实际网格和保护检查。
- Godot 4.7，RTX 4070 Ti：Compatibility／Forward+ 各 **29 项检查通过**，各 7 张最终自动截图，覆盖五档、u=0.37 和回 Reference 的真实网格导出。
- 本轮冻结 **1917 个既有文件**，哈希均未改变；六份正式输入 SHA-256 不变，3675 个固定腔体顶点仍严格零位移。用户原有未跟踪的 Godot 导入边车保留，未当成几何失败。
- 人工记录、R1 数组、二进制、体积证明及来源报告重复构建逐字节一致。完整 [测试结果](../godot_sim/deformation/capacity_v2_n0_closeout/verification/python_tests.json) 与 [保护检查](../godot_sim/deformation/capacity_v2_n0_closeout/protected_after.json) 已保存。
- 本轮未进行新的连续 FPS 验收，旧 18～19 FPS 限制没有改写为已解决。

新增文件包括本文；`tools/capacity_v2/n0_closeout.py`、`test_n0_closeout.py`、`verify_n0_closeout.gd`；新独立场景及 `scripts/capacity_v2_n0_closeout_preview.gd`；全部新记录与候选在 `deformation/capacity_v2_n0_closeout/`。旧工具和结果保持不变。

从仓库根目录逐条运行：

```powershell
$closeoutPython = 'E:/Apps/Conda/miniconda3/envs/FURS/python.exe'
$closeoutGodot = 'E:/Apps/Godot/Godot_v4.7-stable/Godot_v4.7-stable_win64_console.exe'
& $closeoutPython godot_sim/tools/capacity_v2/n0_closeout.py
& $closeoutGodot --path godot_sim --rendering-method gl_compatibility res://capacity_v2_n0_closeout_preview.tscn -- --closeout-verify=res://deformation/capacity_v2_n0_closeout/verification/compatibility
& $closeoutGodot --path godot_sim --rendering-method forward_plus res://capacity_v2_n0_closeout_preview.tscn -- --closeout-verify=res://deformation/capacity_v2_n0_closeout/verification/forward
& $closeoutPython godot_sim/tools/capacity_v2/test_n0_closeout.py
```

**本轮已停止进一步边界推进和形变开发，等待用户确认测量域及其工程代理声明。没有启动 N1、设置新的 V_min/V_max、生成 Contracted/Expanded 或修改已验收形变。**
