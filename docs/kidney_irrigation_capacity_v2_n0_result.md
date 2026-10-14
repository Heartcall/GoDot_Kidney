# Capacity V2 N0：天然容量测量域与疑似穿模审核结果

日期：2026-10-14。**N0 分析与审核工具已交付；D2 未获解剖批准，具体用户视觉异常尚待现场定位。** 未进入 N1/N2，未产生新版 Contracted/Expanded，也未设置正常 V_min/V_max。

完整计算网格 D0 仍为 **19.723077 mL**。旧 17.028206 mL 代数补集没有提升为容量；本轮每一个新候选也都不是正式天然有效容量。`V_reference_effective_mL = null`。

## 1. 源数据检索与保护

搜索当前仓库（含忽略文件，但排除 Git 对象、Godot 缓存）及本地可用 Git refs／路径历史，只找到当前 `kidney_cavity.obj`、`kidney_tissue.obj`。源资产历史仅见首次提交，未发现添加通道前的天然模型、原始分割或可逆预处理配方。OBJ 中 ITK-SNAP／Slicer、RAS 标头只能说明来源线索，不能恢复人工孔之前的解剖。没有搜索仓库外磁盘或未取得的远程历史。

检索清单：[source_inventory.json](../godot_sim/deformation/capacity_v2_n0_research/source_inventory.json)。本轮冻结 **1157 个既有文件**，结束哈希未变；六份权威数组 SHA-256 不变，3,675 个腔体固定点仍严格零位移。原始 OBJ、Marker、拓扑、掩码、R2／P2 运行资源、旧场景、主场景、内镜及碰撞脚本、历史报告均未修改；`TissueReference.visible=false` 保留。

## 2. 测量派生几何的构造及验证

候选只写入 `deformation/capacity_v2_n0_research/`。先计算整份源表面与指定平面的全部边界环，再选择包含路径站点的唯一简单环，仅切分这个环经过的三角面；以该环作拓扑屏障，从人工 END 连通区域提取排除部分。其余同平面相交的天然分支保持原面，不进行全局半空间删除。多环归属不唯一、切面恰经原顶点、非简单环或分裂分量不符合预期时明确拒绝。

封口使用平面简单多边形耳切；保留边界共线顶点及来源映射。**没有采用旧非星形质心扇形，也没有复用已拒绝的 IN_01 固定区封口。** 原参考顶点完全不动，新截点由原顶点线性／重心权重表示。

每个候选保存 `reference_vertices.npy`、`faces.npy`、`source_face_ids.npy`、`source_vertex_ids.npy`、`source_vertex_weights.npy`、`virtual_port_labels.npy`、`fully_removed_source_faces.npy`。`candidate.json` 记录每个截面中心、朝人工 END 的法向、全部平面环、所选环、新封口面索引、被切源面、删除源面、源 OBJ／六数组哈希及未批准状态。虚拟封口的源面编号为 -1，并单独标记所属接口。

检查涵盖闭合、边界／非流形边、绕序、退化、连通分量、平面残差、封口内部重叠、封口对保留壁面及**全部原始壁面（含被排除部分）**的有限相交。预期的同一切环交线和共享边作为构造边界记录，其他正长度交线／重叠拒绝。检测详情分别保存为 `cap_contact_details.json`、`cap_original_contact_details.json`。

体积采用中心化 float64 有向积分／精确求和，并由 trimesh、三个坐标方向散度积分及多个原点重复核对；截除块与保留块使用反向同一封口检验可加性。12 个主候选均通过这组工程检查，但不因此获得解剖批准。

## 3. 全部主候选及不确定边界

下表中的分数沿“天然侧标记 → 人工 BASE”计算；BLADDER 的原路径方向相反，已显式转换。`D+1` 表示人工 BASE 向 END 方向 1 mm。分数是具名测量假设，不是已识别的孔缘或 UPJ。

| 候选 | BLADDER / IN_01 / IN_02 截面 | 候选测量值 mL | 几何 | 天然中心路径／末端 | 审核解释 |
| --- | --- | ---: | --- | --- | --- |
| C00_distal_control | D+1 / D+1 / D+1 | 17.079740 | 通过 | 未排除标记／中心路径 | 保守对照，仍含接口过渡 |
| C01_transition_mid | 0.5 / 0.5 / 0.5 | 14.937493 | 通过 | T_09, T_10, T_13, T_14, T_19, T_20 | 不推荐：排除已确认天然区域 |
| C02_transition_proximal | 0.2 / 0.2 / 0.2 | 14.065336 | 通过 | T_09, T_10, T_13, T_14, T_19, T_20 | 不推荐：排除已确认天然区域 |
| C03_transition_distal | 0.8 / 0.8 / 0.8 | 16.145636 | 通过 | T_14, T_19 | 不推荐：排除已确认天然区域 |
| C04_bladder_proximal | 0.2 / 0.5 / 0.5 | 14.805874 | 通过 | T_09, T_10, T_13, T_14, T_19, T_20 | 不推荐：排除已确认天然区域 |
| C05_bladder_distal | 0.8 / 0.5 / 0.5 | 15.064260 | 通过 | T_09, T_10, T_13, T_14, T_19, T_20 | 不推荐：排除已确认天然区域 |
| C06_near_BASE | 0.5 / 0.98 / 0.98 | 16.665652 | 通过 | 未排除标记／中心路径 | 待审核；保留中心路径不等于保留全部天然壁面 |
| C07_IN01_collar | 0.5 / 0.95 / 0.98 | 16.661831 | 通过 | 未排除标记／中心路径 | 待审核；保留中心路径不等于保留全部天然壁面 |
| C08_IN02_collar | 0.5 / 0.98 / 0.95 | 16.657480 | 通过 | 未排除标记／中心路径 | 待审核；保留中心路径不等于保留全部天然壁面 |
| C09_UPJ_proximal_unconfirmed | 0.2 / 0.98 / 0.98 | 16.534033 | 通过 | 未排除标记／中心路径 | 待审核；保留中心路径不等于保留全部天然壁面 |
| C10_UPJ_distal_unconfirmed | 0.8 / 0.98 / 0.98 | 16.792419 | 通过 | 未排除标记／中心路径 | 待审核；保留中心路径不等于保留全部天然壁面 |
| C11_inlet_distal_control | 0.5 / D+1 / D+1 | 16.807273 | 通过 | 未排除标记／中心路径 | 保守对照，仍含接口过渡 |

**重要失败结果：** C01／C02／C04／C05 排除了 T_09、T_10、T_13、T_14、T_19、T_20 及对应 B_13、B_14、B_17、B_18、B_26、B_28 的部分已确认路径；C03 排除了 T_14、T_19 及 B_18、B_26 的部分路径。因此这些闭合结果不适合作为保全天然集合系统的 D2，已在 JSON 和 Godot 面板警示，不以其较小体积作为容量答案。

C00、C06～C11 保留了 A／J／T 全部天然标记和 MAIN＋B_01～B_30 的采样中心路径。该检查基于封闭候选的有符号距离，仍不能证明整个天然分支壁面都未被裁掉。

**IN_02 关键疑点：** C06 的 IN_02 截面面积约 94.884 mm²，是 C00 远端管道对照（9.203 mm²）的约 10.31 倍。虽然中心路径未排除，仍明显切入较宽空间，不能认定为原人工孔。C07～C10 有同类警示。**优先比较 C11 的保守管道截面与 C06 的宽截面。** C11 仍保留 B_31／B_32 过渡，不能直接称为纯天然域。

BLADDER 的三种过渡位置仅为 UPJ／输尿管截止待审核候选，名字含 UPJ 不表示已定位真实 UPJ。肾盂／肾盏／连接段的语义需影像或人工确认。所有 T_01～T_22 均提供原源面的端部几何候选清单，但没有资料判断哪些来自真实解剖边界或分割封口；未将其改成新的封口。

完整候选：[domain_candidates.json](../godot_sim/deformation/capacity_v2_n0_research/domain_candidates.json)；22 个末端：[terminal_boundary_inventory.json](../godot_sim/deformation/capacity_v2_n0_research/terminal_boundary_inventory.json)。

### 3.1 截面敏感性

另将各接口的中部截面沿朝人工 END 法向独立移动 ±0.1 mm，形成 6 个单接口敏感性试验。每个同样保存坐标、面、来源权重、截环、封口和检测记录，且均通过构造检查。它们只分析边界定义，不是另 6 份完整 D2，也不修复中部截面排除天然分支的问题。

| 接口 | -0.1 mm 的排除块 mL | +0.1 mm 的排除块 mL |
| --- | ---: | ---: |
| BLADDER | 2.648872 | 2.636622 |
| IN_01 | 1.233595 | 1.188045 |
| IN_02 | 0.953161 | 0.910776 |

不同主候选相差的体积反映域定义差异，不能作为正常容量范围或统计置信区间。当前保留 `V_reference_effective=null`，不选择数值最小或视觉最顺眼的候选。

## 4. 正式 P2.3 五档接触分类

源 float64 在原始坐标下计算；显示侧使用 P2.3 真正导出的中心化 float32 ArrayMesh，并逐值核对正式参考＋u×正式位移。两者分开扫描，不把平移后重新舍入的 float64 候选数量当成另一份参考几何。

每档重新执行 VTK 有限候选搜索（box/cell tolerance=0），随后进行有限三角面交线、双侧共面距离、有限多边形重叠及最近特征复核。穿越长度接受阈值维持 1e-10 mm，共面正面积统计阈值 1e-12 mm²；近距搜索的 0.1 mm 仅用于额外抽样定位，不是放宽穿越阈值。

正长度交线不自动等于穿模：还检查交线端点／中点是否在两三角面内，以及中点是否位于边界。三角面沿同一条边接触可有非零交线；本轮没有把这些接触隐藏，也没有把无限平面跨越当成确认穿越。

| u | 数据 | VTK 候选 | 点接触／切触 | 边接触 | 共面重叠配对 | 额外近距不相交 | 确认横向穿越 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.00 | 实际 float32 | 3866 | 3405 | 424 | 42 | 18 | 0 |
| 0.00 | 原始 float64 | 3840 | 3377 | 423 | 42 | 18 | 0 |
| 0.25 | 实际 float32 | 2902 | 2498 | 381 | 41 | 18 | 0 |
| 0.25 | 原始 float64 | 2887 | 2469 | 398 | 41 | 18 | 0 |
| 0.50 | 实际 float32 | 2912 | 2507 | 380 | 42 | 20 | 0 |
| 0.50 | 原始 float64 | 2814 | 2412 | 379 | 42 | 20 | 0 |
| 0.75 | 实际 float32 | 2870 | 2465 | 379 | 41 | 20 | 0 |
| 0.75 | 原始 float64 | 2939 | 2512 | 401 | 42 | 20 | 0 |
| 1.00 | 实际 float32 | 2857 | 2448 | 391 | 40 | 20 | 0 |
| 1.00 | 原始 float64 | 3029 | 2596 | 407 | 40 | 20 | 0 |

各分类合计包含补充近距面配对，故不等于 VTK 列。五档中未发现未解释的正长度有限相交或算法交线误报；确认横向穿越为 0。共面重叠、点／边接触继续存在，不自动解释为分割错误或生理允许贴合。共面配对面积和约 12 mm²，可能重复计数，**不是穿透面积／深度**。

另对 u=0.37 实际 P2.3 数据完成附加扫描，未检出确认横向穿越。没有对整个连续 u 区间作碰撞证明；近距搜索为全腔体面心采样及局部候选的定位检查，不是表面全局最小间隙证明。组织自交／面积／梯度等旧工程结果依照六数组和实际网格逐字节一致性保留，本轮未重复无必要的大规模组织自交扫描。

### 4.1 原有与新增配对的空间比较

新面配对独立回到 Reference 重新分类，并计算与原始接触样本云的空间距离，不只比较编号。实际 float32 各非零档新增索引配对分别为 268／260／266／260；这些配对在 Reference 中已经属于点接触或边接触，当前仍无确认横向穿越。其中心距原接触样本云最大约 0.182111 mm，是位置变化指标，不是穿透深度。

逐配对结果：[contact_changes.json](../godot_sim/deformation/capacity_v2_n0_research/contact_changes.json)。浮点坐标下候选数量改变可以发生在原有接触区域，不能据此认定出现新的生理接触或缺陷。

### 4.2 重点区域与面索引入口

J_05、J_09、B_32、IN_02、F01～F04 各提供局部分类与一键定位。下表选取 u=1 的代表；坐标为原始 RAS mm，预览世界坐标需减 `[16,16,-81] mm`。路径／定位关联只是空间定位，不证明 F03/F04 材料归属。

| 定位 | 腔体面／组织面 | 类别 | RAS 中心 mm | 有限交线 mm | 最近几何距离 mm |
| --- | --- | --- | --- | ---: | ---: |
| J_05 | 24257 / 26251 | EDGE_CONTACT | 29.42419, 15.05865, -60.53184 | 0.909797079 | 0.000000000 |
| J_09 | 6970 / 64744 | EDGE_CONTACT | 10.19442, 19.81943, -39.86110 | 0.911258767 | 0.000000000 |
| B_32 | 6970 / 64744 | EDGE_CONTACT | 10.19442, 19.81943, -39.86110 | 0.911258767 | 0.000000000 |
| F04 | 6970 / 64744 | EDGE_CONTACT | 10.19442, 19.81943, -39.86110 | 0.911258767 | 0.000000000 |

完整面索引、交线端点、RAS／Godot 世界坐标、双侧共面残差及各局部统计见 [contact_summary.json](../godot_sim/deformation/capacity_v2_n0_research/contact_summary.json) 和 `contacts/` 逐档报告。全局共面重叠按 2 mm 单链分为每档 13 组，共 65 组；其代表面也加入 Godot 下拉菜单，详见 [contact_groups.json](../godot_sim/deformation/capacity_v2_n0_research/contact_groups.json)。

### 4.3 用户视觉异常仍待定位

**没有复现用户此前指定的镜头／位置，因此不宣布穿模问题已经消失。** 共面双表面、深度缓冲归属、双面内壁及剖切丢弃半空间都可能造成看似互相穿出的显示，但本轮不能把它们指定为用户异常的唯一原因。

已提供同镜头的腔体单独、组织单独、两者联合截图，并保存面配对；这能对照显示与几何关系，不能证明任何未知位置的异常只是显示问题。需要用户保存现场 JSON＋截图后，对该确切 u、面及镜头分类。若为真实穿越则记录为待解决缺陷，本轮不会修改模型或掩盖。

## 5. Godot 只读审核操作

1. 在 Godot 4.7 打开 **`res://capacity_v2_n0_preview.tscn`，按 F6**。F5 仍为原主场景；旧 P2 场景没有覆盖。
2. 默认 C11 保守对照。模式切换：D0 完整域／仅排除结构／候选测量域／接触诊断。候选域强制只看 Reference，不与旧 u 形变混用。
3. 优先比较 C11 与 C06，保持当前镜头切换候选；查看 IN_02 金色封口是否切入天然宽腔室。C00 是远端对照，C01～C05 是标明失败的域假设。不要只根据“几何通过”批准。
4. 使用三个“定位候选截面”按钮，观察 BLADDER 截止、IN_01、IN_02；原壁为蓝，虚拟封口金，排除结构灰，彩线为截环及参考框。虚拟封口是独立 MeshInstance，**不会加入正式 P2 腔壁**。
5. 接触模式显示原正式双网格，可设 u=0／0.25／0.5／0.75／1 或连续滑块；腔体与组织分别显隐。不透明剖切、轴向与位置控制在左侧下方，滚动可见。
6. 定位菜单保留全部 J／T、B_31／B_32、人工接口及 F01～F04；自动面配对菜单还含全局共面组。配对定位会显式切换至记录中的 u；普通位置定位只改镜头和剖切。
7. 可输入原始 RAS X/Y/Z，或输入腔体面 0～50043 与组织面 0～311843。诊断线可透视，白线为 Reference，对比当前彩线；它们不是实体表面。切换 u 后若缓存分类不再适用，面板会提示需要重算。
8. 左键旋转、中键平移、滚轮缩放、R 镜头复位。三态／u 比较保留当前镜头。
9. 看到异常后点击“保存审核现场 JSON＋真实截图”；写入 `deformation/capacity_v2_n0_research/user_sessions/`，记录 u、候选、面、相机、剖切法向／偏移、显隐、尺寸及正式 manifest 哈希。提供这对文件或文件名即可按同一状态复核。

大组织网格保持原验证过的不透明材质与剖切，不启用透明混合，也不改实时法线、形变量或原碰撞。

## 6. 实际图形、数值测试与重复构建

- compatibility：110 项检查，0 个失败；32 张最终自动截图；gl_compatibility／NVIDIA GeForce RTX 4070 Ti。
- forward：110 项检查，0 个失败；32 张最终自动截图；forward_plus／NVIDIA GeForce RTX 4070 Ti。
- Python：**25/25 通过**。覆盖已知体积盒子、U 形管局部裁切不误删另一侧、穿越／边／点／共面／近距判据、来源重心映射、全部候选、天然路径拒绝规则、真实图形数据和保护检查。
- 两个后端共 28 份实际 ArrayMesh 导出，覆盖五档、u=0.37 和返回 Reference。位置、面索引、法线完整二进制与 P2.3 基准一致；3,675 个固定点不动。
- C06 独立重复构建的所有数组、二进制及封口检测报告逐字节一致；原点／散度复核差异在 1.4e-6 mm³ 以内，属于数值精度而非解剖精度。
- 本轮没有重新测量连续 FPS，没有解决既有 18～19 FPS 限制；审核截图与快速离散测试不能视为实时性能达标。

真实截图（均来自本轮 Godot，不是示意图）：

- [C11 同镜头对照](../godot_sim/deformation/capacity_v2_n0_research/verification/forward/compare_C11_inlet_distal_control.png)、[C06 同镜头对照](../godot_sim/deformation/capacity_v2_n0_research/verification/forward/compare_C06_near_BASE.png)。
- [失败中部截面 C01](../godot_sim/deformation/capacity_v2_n0_research/verification/forward/D2_C01_transition_mid.png)、[IN_02 宽截面特写](../godot_sim/deformation/capacity_v2_n0_research/verification/forward/C06_cut_IN02.png)。
- [J_09 Reference](../godot_sim/deformation/capacity_v2_n0_research/verification/forward/contact_J_09_u000.png)、[J_09 Expanded](../godot_sim/deformation/capacity_v2_n0_research/verification/forward/contact_J_09_u100.png)，相机位置相同。
- [共面组联合](../godot_sim/deformation/capacity_v2_n0_research/verification/forward/coplanar_both.png)、[仅腔体](../godot_sim/deformation/capacity_v2_n0_research/verification/forward/coplanar_cavity_only.png)、[仅组织](../godot_sim/deformation/capacity_v2_n0_research/verification/forward/coplanar_tissue_only.png)，相机和 u 相同。

初次运行遇到缺失 Shapely、Godot 启动环境／相对日志参数崩溃、以及研究目录重复覆盖时的 Windows 文件打开错误；分别改用验证过的 NumPy 多边形实现、正常桌面运行并捕获终端日志、仅对新 N0 产物作临时文件＋原子替换。JSON 换行格式统一后重新构建，重复检查通过。这些修复未改变几何阈值、源数组或旧报告。格式不一致的失败测试日志保留在 `verification/failures/`；最终日志和成功结果单独记录。

[Python 结果](../godot_sim/deformation/capacity_v2_n0_research/verification/python_tests.json)、[Compatibility 记录](../godot_sim/deformation/capacity_v2_n0_research/verification/compatibility/runtime_checks.json)、[Forward+ 记录](../godot_sim/deformation/capacity_v2_n0_research/verification/forward/runtime_checks.json)、[保护检查](../godot_sim/deformation/capacity_v2_n0_research/protected_after.json)。

## 7. 文件与复现命令

新增独立场景 `capacity_v2_n0_preview.tscn`、`scripts/capacity_v2_n0_preview.gd`，以及 `tools/capacity_v2/` 中的 n0_common、build_n0_domains、diagnose_n0_contacts、compare_n0_contact_changes、prepare_n0_review、test_n0_review、summarize_n0 和 n0_verify.gd。旧 Capacity V2 分析工具及旧阶段代码不改。所有研究结果在新的 `deformation/capacity_v2_n0_research/`，除绘图之外没有依赖新的外部库安装。

从仓库根目录逐条执行；每条成功后再执行下一条：

```powershell
$n0Python = 'E:/Apps/Conda/miniconda3/envs/FURS/python.exe'
$n0Godot = 'E:/Apps/Godot/Godot_v4.7-stable/Godot_v4.7-stable_win64_console.exe'
& $n0Python godot_sim/tools/capacity_v2/n0_common.py
& $n0Python godot_sim/tools/capacity_v2/build_n0_domains.py
& $n0Python godot_sim/tools/capacity_v2/diagnose_n0_contacts.py
& $n0Python godot_sim/tools/capacity_v2/diagnose_n0_contacts.py --u 0.37
& $n0Python godot_sim/tools/capacity_v2/compare_n0_contact_changes.py
& $n0Python godot_sim/tools/capacity_v2/prepare_n0_review.py
& $n0Godot --path godot_sim --rendering-method gl_compatibility res://capacity_v2_n0_preview.tscn -- --n0-verify=res://deformation/capacity_v2_n0_research/verification/compatibility
& $n0Godot --path godot_sim --rendering-method forward_plus res://capacity_v2_n0_preview.tscn -- --n0-verify=res://deformation/capacity_v2_n0_research/verification/forward
& $n0Python godot_sim/tools/capacity_v2/test_n0_review.py
& $n0Python godot_sim/tools/capacity_v2/summarize_n0.py
```

对额外滑块值：`diagnose_n0_contacts.py --u 0.413`。对已保存现场：`diagnose_n0_contacts.py --session "完整 JSON 路径"`；会验证 manifest，重算该 u 并额外分类指定面，不修改几何。现场诊断命令已实际执行。

图形预览只读版本化 P2 资源和新 N0 测量二进制；原 P2.3 的诊断导出及 R2 缓存用于分析对照，缺失时不会重新求解位移或伪造证明。

## 8. 下一次人工审核与停止状态

请优先核对：**C11 与 C06 的 IN_02 截面**是否保留所需天然腔壁；BLADDER 截止位置与人工连接的测量范围；IN_01 孔缘及 B_31 过渡；天然末端封口的原分割含义。若无法从模型判定，继续保留多候选和未确定状态，需人工画定局部解剖边界或找回原分割。
同时请在诊断入口保存你此前疑似穿模的现场，尤其 J_05／J_09／B_32／IN_02／F 区域；只有取得该位置和状态后，才能关闭或确认该具体问题。

**本轮停止在 N0。没有批准 D2，没有正式天然容量值，没有启动 N1/N2、P2.4、P3/P4、压力／流量、动态碰撞或录像。**
