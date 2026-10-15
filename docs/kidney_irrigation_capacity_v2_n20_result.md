# N2.0 自适应几何求解预研结果

2026-10-15，v1。**研究交付完成；±30%目标尚未达到，连续安全门禁仍未闭合，未生成正式 N2 资源。** 标签为 `MORPHOLOGY_GUIDED_UNCALIBRATED_CAPACITY_ESTIMATE`。N1.6 A1 已被本轮用户目标取代，但其原文件、失败记录、医学 null 结论及全部既有成果不变。

## 1. 目标与实际证据分开

D2=`C11_R1_IN02_fixed_collar`，Reference 16.805962087430178 mL。以下“离散候选”指 float64 五档检查，**不是最大安全容量、临床极限或正式三态**。

| 方向 | 用户目标 mL | 新原型离散候选 mL | 相对 Reference | 尚差目标 mL |
|---|---:|---:|---:|---:|
| 收缩 | 11.764173461201125 | 15.524507478263565 | −7.625% | 3.760334017062440 |
| 扩张 | 21.847750713659231 | 17.562230381364536 | +4.500% | 4.285520332294695 |

两侧分别经过13、5个保留求解检查站。未静默降低±30%目标。停止原因是本实现的局部质量／接触代理／线搜索限制，**不能据此证明所有受约束方法都无法达到±30%**。仅解初始区域方向的体积方程可以得到目标有向积分，但物理质量失败；`unconstrained_predictions.json` 将其明确列为未验证代数预测，不能称为有效腔体容量。

连续运动充分认证的非零范围：**尚无**。原样 Reference 是唯一不涉及新运动的基线；本轮不能给出“最大连续安全容量”。浮点事件检查未检出两条 Reference—候选轨迹的横向穿越，但收缩4529对、扩张4528对永久共面／数值条件不充分事件仍 unresolved，不能将它们计为安全。详见 CCD 压缩证据。

## 2. 实际实现

新增工具均在 `godot_sim/tools/capacity_v2/n20_*.py`，数据隔离在 `godot_sim/deformation/capacity_v2_n20_v1/`。

- 新区域响应：按原拓扑的互斥 Terminals／MainCavity／J_01 主响应，Branches／其他 J 次响应；人工过渡单列，非邻接路径不参与无约束混合。
- 实际 D2 体积梯度、非线性三次积分求根、局部 mobility 缩减、剩余容量转移与回退。
- 组织软映射＋形状连续性＋单侧活动接触稀疏 QP；139真实共点严格保持，126,104远场点固定，F03/F04不假称解剖归属确定。
- 固定拓扑细长面保护及切向整理专项；未删点、未边折叠、未重网格。
- D2材料截环额外来源锚点固定，共97点不属于原固定接口；封口使用原固定模板，不逐状态更换，不进入实体网格。
- 全部保留求解检查站的质量、腔体／D2自身和相互横向穿越检查；补齐所有检查站组织自身横向穿越。五档额外检查共享单顶点面。
- Reference—候选五档全表面检查、各求解段连续面积／法向多项式检查、有限事件 CCD 研究、离线float32质量预检查。

完整方程、支持规则、A/B剪枝比较、计算开销和限制见 `kidney_irrigation_capacity_v2_n20_design.md`。此实现是交替式研究求解，尚不是具备完整CCD步长认证的全局联合非线性最优解。

## 3. 物理质量、容量与接触

| float64 Reference—候选全区间指标 | 收缩腔体 | 扩张腔体 | 收缩组织 | 扩张组织 |
|---|---:|---:|---:|---:|
| 最大位移 mm | 0.552627 | 0.375344 | 0.504585 | 0.342469 |
| 平均位移 mm | 0.128513 | 0.073074 | 0.017863 | 0.010563 |
| 最大边位移梯度 | 0.185182 | 0.157007 | 0.111208 | 0.085911 |
| 最小面积比 | 0.800014987 | 0.958318472 | 0.845810356 | 0.967249219 |
| 最大面积比 | 1.069864775 | 1.324898768 | 1.045712573 | 1.104009161 |

五档 `u=0,.25,.5,.75,1` 分别检查腔体、组织、D2自身及腔体—组织：未检出新增确认横向穿越、退化或翻面；3,675接口顶点严格零位移，139共点相对位移为零，远场组织零位移。原点边接触、共面重叠与候选误报不改写为原有真实穿透。`reference_contact_changes.json` 记录原共面配对的保留／变化与成对重叠面积；面积之和不是唯一接触面积或穿透面积。

每个求解检查站的原始相对质量与实际容量在 `trajectory.json`；有限相交细节在各 `attempt.json.gz`、`stage_*_tissue_self.json.gz`。最终五档完整索引与几何证据在 `verify_u*.json.gz`，汇总 `verification.json` 保留文件哈希，避免重复数百MB的行数据。

D2原封口及同截环三种耳序均进行几何检查。额外截环锚点使边界保持固定；替代封口只做体积敏感性，不替换原D2、不扩大统计范围。`independent_reintegrals.json` 用中心化有向积分、三轴散度、Trimesh和40位Decimal远原点积分独立复算每档。容量归因按互斥支持积分，报告守恒残差；不采用未批准解剖分区体积冒充实际容量。

对 MAIN、B、J、T、B31/B32 和 F01～F04 的局部质量见 `local_regions.json`。可信N1中心路径站点在两端均未出现外侧符号样本，也没有低于0.2mm的采样中心线表面距，但这仅是**局部通道探针**：不证明所有截面的最小净空，不是器械半径或内镜可通行证书。物理面连接与原分叉图未变，不能仅以此或欧拉数替代连续通道验证。

`capacity_region_contributions.csv`给出互斥支持的容量变化归因，`local_quality_by_region.csv`给出可重叠诊断区域统计。`local_limit_diagnostics/`保存逐腔体顶点的有限组织面距离、来源编号、最近点与法线变化代理；这不是壁厚、主曲率拟合或独立最大位移表。曲率专属信赖域约束和经认证的逐点膨胀上限尚未完成。

## 4. 失败定位及切向整理

收缩最终拒绝面 **7680，T_18邻域**：最小候选面积比约0.799900。缩减局部目标并减半步长仍不能越过本轮线搜索门槛。11点一环切向SQP只需约9.61e-7mm修正就能使该单个试验的全物理面积／边梯度恢复门禁内，但其组织、接触、全过程均未复核；容量重新积分，未计入上述已检查端点。

更重要的是：原收缩候选的float64最小面积比仅0.800015，按既有 `[16,16,-81] mm` 中心化float32表达后，面7680面积比约 **0.799996048**，已失败。最大坐标舍入差约3.46e-6mm。因此收缩候选**不具备直接Godot播放资格**，切向修正也需更可靠的数值余量；不能放宽0.8门槛。

扩张先在 **T_19** 触及局部质量，减小其响应后继续。随后出现保守接触半空间与严格共点的冲突：例如腔体面 **34852**、组织面 **181160**、组织顶点 **93578**。即使某些终态有限穿越已归零，此代理约束仍不可行。`blocking_regions.json` 提供源面、RAS坐标、所属路径和残差。这个冲突不能自动解释为真实穿透，更不能将约束删掉后宣称全部通过；需要可靠有限接触特征追踪与腔体局部回退／联合重分配。

## 5. 对N1.6失败基线的改善

这里固定旧失败腔体形状，仅测试新的组织接触协调，**不是用旧场作为新±30%驱动**。

| 冻结回归夹具 | 旧终态横向穿越 | 新研究最好终态 | 结论 |
|---|---:|---:|---|
| +8% | 173 | 0 | 组织质量／活动QP通过；额外五档完整静态检查通过；仍无全连续证明 |
| +15% | 753 | 0 | 半空间／严格约束冲突，QP不通过；不能判安全 |
| +25% | 1838 | 3 | 质量与接触均失败 |

+8%回归实际容量18.150439054424535mL，独立证据在 `regression_S1_expand/`。它使用旧夹具的区域与移动测量截环，**不能冒充新主次区域策略和固定截环方案已达到+8%**。新算法有效改善旧接触失败，但不足以声称+15%或+30%已安全实现。

## 6. 测试、保护与运行记录

Python **27项测试通过**。覆盖权威哈希、互斥支持、区域优先级与饱和重分配、实际体积梯度、D2截环固定、独立体积、全部检查站固定／共点与自交记录、容量归因守恒、有限面风险数据、第一步双网格逐值重复构建、+8%接触QP重复构建、全检查站记录回放、五档完整检查、连续面积、合成中间碰撞事件、float32失败保留和禁止晋升。

重复构建证据是首步腔体／组织和+8%活动QP**逐值完全一致**；另提供全部已记录检查站的区域预测和绑定接触求解回放，不声称对全部自适应搜索做了两次完整重跑。恢复检查站时仅恢复已有绑定来源行，没有保留所有曾出现的非活动半空间；因此不中断搜索和恢复搜索可能走不同局部路径，研究执行顺序必须明示。正式算法冻结前需要统一活动集持久化。初次扩张及加入QP冲突归属后的 `expand_redistributed/` 重试均未超过+4.5%。修复了初次拒绝分支日志缺少reason的运行错误；原试验与后续重试分别保留。高精度积分解决数值抵消报错，没有改物理检测阈值。

**2,658个受保护文件逐项SHA-256无变化**，包括旧N1.6失败、D2、原始OBJ、Marker/拓扑、P1/P2、主场景及碰撞。具体见 `protected_before.json`／`protected_after.json`、交付清单、源代码快照。旧P2.3约18～19FPS未解决，医学参数继续null。

本阶段只执行离线研究与标准科学绘图；**没有启动新的Godot形变场景、没有实际ArrayMesh/图形运行验收或录制视频**。离线float32预检查不冒充Godot实际运行。

## 7. 可重复命令

在仓库根目录，以现有FURS环境执行。以下工具只写本轮新目录；不要调用旧阶段build/protect入口。

```powershell
$pythonN20 = 'E:/Apps/Conda/miniconda3/envs/FURS/python.exe'
& $pythonN20 godot_sim/tools/capacity_v2/n20_model.py
& $pythonN20 godot_sim/tools/capacity_v2/n20_solve.py expand 4
& $pythonN20 godot_sim/tools/capacity_v2/n20_solve.py expand 35 --resume
& $pythonN20 godot_sim/tools/capacity_v2/n20_solve.py contract 3
& $pythonN20 godot_sim/tools/capacity_v2/n20_solve.py contract 35 --resume
& $pythonN20 godot_sim/tools/capacity_v2/n20_predictions.py
& $pythonN20 godot_sim/tools/capacity_v2/n20_tangential.py
& $pythonN20 godot_sim/tools/capacity_v2/n20_regression.py
& $pythonN20 godot_sim/tools/capacity_v2/n20_verify.py expand
& $pythonN20 godot_sim/tools/capacity_v2/n20_verify.py contract
& $pythonN20 godot_sim/tools/capacity_v2/n20_stage_audit.py expand
& $pythonN20 godot_sim/tools/capacity_v2/n20_stage_audit.py contract
& $pythonN20 godot_sim/tools/capacity_v2/n20_ccd.py expand
& $pythonN20 godot_sim/tools/capacity_v2/n20_ccd.py contract
& $pythonN20 godot_sim/tools/capacity_v2/n20_precision.py
& $pythonN20 godot_sim/tools/capacity_v2/n20_local_limits.py
& $pythonN20 godot_sim/tools/capacity_v2/n20_replay.py
& $pythonN20 godot_sim/tools/capacity_v2/test_n20.py
& $pythonN20 godot_sim/tools/capacity_v2/n20_report.py
```

第一次完整检查组织所有阶段耗时较长；静态全表面检测在本机本轮每检查站约59～61秒，不代表实时播放耗时。缓存按场／源哈希核查，研究算法变更应换版本目录，不混用旧验证。JSON读取器支持同名 `.json.gz`；归档不丢原始配对证据。

`n20_finalize.py` 汇总快照、大小和哈希；`capacity_contact_curves.png`展示实际容量轨迹、位移、面积门槛和回归改善。`summary.json`／`blocking_regions.json`提供机器可读结论。

## 8. 审核后下一步

审核本轮区域定义、固定测量截环策略、T_18切向整理与float32风险、共点半空间冲突和真实回归改善。推荐先解决有限接触特征的连续追踪与数值裕量，再冻结能通过+8%／+15%全过程的求解器；随后才能重新研究±30%。详见 `kidney_irrigation_capacity_v2_n20_next_plan.md`。

**当前不建议批准正式±30%三态。** 本轮没有证明目标全局不可达，也没有给出可替换目标的最大安全容量。停在N2.0等待用户审核，不开始正式N2、组织生产求解、内镜／碰撞集成或录像。
