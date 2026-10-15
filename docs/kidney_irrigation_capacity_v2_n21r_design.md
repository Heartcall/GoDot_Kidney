# N2.1-R 方法、数值范围与复现

本文件只说明离线研究方法。正式 ±30% 目标与 D2 不变；所有研究数组均不供正式 Godot 播放。本轮结果与失败见 `kidney_irrigation_capacity_v2_n21r_result.md`。

## 1. 有限接触模型

对腔体三角面 A、组织三角面 B，分别建立投影落在有限面内的双向 VF 和有限线段 EE 特征。每条记录包含源顶点／面索引、重心或边参数、法向、有限位置及有符号相对间隙。

局部约束为

`n · [Σ w_t (t_reference + d_t) − Σ w_c (c_reference + d_c)] ≥ 0`

只有对应有限特征存在时才建立该行，不把某面无限延伸到场外顶点。VF 重心的微小数值容差用于判定投影支持，最终真穿越判据仍为历史有限三角方法的 1e-10 mm。EE 候选使用有限边参数，不以最近顶点距代替三角相交。

139 个已确认共点满足 `d_t[i] = d_c[exact_id[i]]`；当整条特征就是相同来源的线性组合，将其识别为恒等式。不确定材料归属没有新增硬绑定。组织远场仍为 0。组织形状保持能继承已验收研究基线，接触增量通过稀疏凸二次型对偶 L-BFGS-B 求解，再尝试 KKT 精化；只有全部原始残差通过且修正不超 0.05 mm 才接受。

局限：特征参数与法向来自局部线性化；不是全局无穿越障碍能，也不是从 Reference 到候选自动安全的推进器。冷启动失败表明需要连续安全步长和重新发现特征，不能把线性 QP 可行当作有限几何通过。

## 2. 总区域系数与容量约束

`c(q) = c_ref + Σ q_k B_k`，每次由参考重算，不在上一轮坐标上盲目叠加。区域基函数沿用 N2.0 的拓扑归属、局部支持、掩码和固定接口，生成新的研究副本。`review/exclusive_source_vertex_group.npy` 与 `source_vertex_local_mode.npy` 给出精确源顶点映射，JSON 给出路径名称和来源代码 SHA。

互斥组：FIXED 3,675；Terminals 3,659；MainCavity 2,299；J_01 67；Branches 13,919；OtherJunctions 595；InterfaceTransition 810。合计 25,024。MainCavity 映射到原 MAIN 支持；J_01 独立，不重计入 OtherJunctions。初始响应优先权为 `[0,1,1,1,0.22,0.18,0.10]`，是正则权重，不是强制容量百分比。

使用实际 D2 映射后的体积积分及其源顶点梯度：

`∂V_D2/∂q_k = <∇_source V_D2, B_k>`。

分块优化包含实际容量梯度、面积／边梯度线性化、组织增量响应后的有限相对法向行，以及系数信赖域。总 q 保持非负，但允许增量为负；本轮第二次重线性化确实尝试负增量，失败后未应用。LP 用于判断当前线性信赖域可行及提供初值，目标尺度调整后交给 SQP。

全部非线性网格／接触门禁在外部重新检查。此次约 +5% 提案的 69 对穿越说明当前特征集合不覆盖新接触；尚未实现每步先 CCD 裁步再提交的完整非穿越联合优化。

容量贡献采用互斥源支持对实际积分沿轨迹的守恒归因，而不是把分支截面积积分简单相加，也不是正式解剖分区容量。研究总量守恒不替代测量域有效性或接触安全。

## 3. 局部切向整理、舍入预算

先按面积比与舍入风险自动取种子；扩三环，在每个连通 patch 内以局部法向的两个切向基为自由度。边界点加强形状正则但不产生单面孤立修正。优化约束覆盖所有入射面和边，保留容量罚项及很小容量残差复核。所有源连接、固定点和 D2 映射不变。

为了重复已经检查的 R2，生成规则冻结为 V1 双储备；它只用于生成。独立 V2 预算包含中心 `[16,16,-81] mm` 下的参考 cast、位移 cast、u 舍入、乘法和加法。对三角叉积二次多项式使用 Bernstein 控制量给出全区间方向下界及范数上界，再叠加误差预算；binary64 运算设置 `128*eps` 条件数保护。

阈值 0.8～1.35、梯度 0.2 保持不变。预算的内部余量依具体短边／小面敏感性而异，不能统一套任意百分比，也不能宣称它是医学应变限制。独立实际 float32 全面片五档检查仍不可省略。误差预算是限定运算路径的工程筛查，不等价于形式化验证所有实现。

采用真正简化／统一重网格会改变材料对应及面编号，需要新 Reference、双向状态、组织映射和 D2 映射的联合审核。当前 patch 修复成功，不具备进行删点／边折叠的必要性证据，因此本轮未实施 B 类简化。

## 4. 连续检测算法与分类

轨迹是二份确定 binary64 端点的精确线性插值。扫掠 AABB 使用向外一 ULP；所有候选的固定轴区间投影乘加使用向外 nextafter。固定轴不是必要分离轴时只会保留更多对应，不把未分离当作穿越。

剩余面对应的三角平面有向体积为低次有理多项式。Fraction 精确表示输入 double，使用 Bernstein 控制量严格符号与自适应二分；有限交线区间见证用于确认实际横向穿越。当前二分最大深度 3，面法向非退化保护另至深度 6；超出能力一律未解析，不自动通过。

分类包括：分离多项式认证无横穿、共享特征认证无横穿、永久共面无横穿、原有横穿见证、新横穿见证、数值／退化／时间盒未解析。共享点本身不能绕过见证检查。自交共享边不可能在非共面时产生超出公共线的横穿，但共面重叠仍需独立判定。

永久共面横穿判定不能回答新增共面重叠。额外用精确常量重心嵌入证明三对 C-T 轨迹中每对永久共面三角共同变换，且 A 非退化，因而原有有限接触拓扑不变。普通滑动而无此证明的情况保留未解析，合成测试覆盖这一差别。

完整自交共享特征、float32 量化轨迹以及封口连续检测尚未完成。摘要的 false 是范围阻塞，不是“已检测到穿越”的同义词；失败与未解析分别保存。

## 5. D2 封口与额外 97 点

固定模式保持 N2.0 的额外截环来源锚点不动；随动模式只允许相同材料重心映射运动，截面定义和封口连接表不随帧切换。原 3,675 固定接口点始终不动。对合法耳切替代方式只做容量敏感性审核，不择优替换；没有采用被拒绝的质心扇形封口。

源 D2 虚拟封口不进入实体腔壁、组织或碰撞系统。非平面随动封口只在已检测站点报告容量有效；连续封口门禁没通过前不能把其全区间积分都当作无歧义封闭空间容量。

## 6. 复现环境与命令

仓库根目录运行；Python 3 环境需要 NumPy、SciPy、VTK、trimesh、matplotlib。实际版本在新目录 `summary.json/environment`。本机解释器：`E:/Apps/Conda/miniconda3/envs/FURS/python.exe`。以下均为 **N21 新入口**，不调用会覆写旧证据的 N16／N20 构建入口。

快速交付复核（重新计算测试及局部整理；不会重新扫全部大网格）：

```powershell
$n21Python = 'E:/Apps/Conda/miniconda3/envs/FURS/python.exe'
& $n21Python godot_sim/tools/capacity_v2/n21_finalize.py --verify
& $n21Python godot_sim/tools/capacity_v2/n21_repeat.py
& $n21Python godot_sim/tools/capacity_v2/test_n21.py
```

重算当前离线研究候选与诊断（会更新**新目录**内相应结果；需先保存本轮交付 manifest 以便比较）：

```powershell
& $n21Python godot_sim/tools/capacity_v2/n21_common.py
& $n21Python godot_sim/tools/capacity_v2/n21_reproduce.py
& $n21Python godot_sim/tools/capacity_v2/n21_contact_runs.py --final S1_expand S2_expand S3_expand expand
& $n21Python godot_sim/tools/capacity_v2/n21_warm_runs.py
& $n21Python godot_sim/tools/capacity_v2/n21_robust_patch.py --r2
& $n21Python godot_sim/tools/capacity_v2/n21_margin_audit.py
& $n21Python godot_sim/tools/capacity_v2/n21_repeat.py
& $n21Python godot_sim/tools/capacity_v2/n21_boundary.py
& $n21Python godot_sim/tools/capacity_v2/n21_regions.py
& $n21Python godot_sim/tools/capacity_v2/n21_regional_lp.py
& $n21Python godot_sim/tools/capacity_v2/n21_region_failure.py
& $n21Python godot_sim/tools/capacity_v2/n21_feature_track.py
```

五档大网格与连续检测（耗时较长；已有相同输入结果时复用带来源校验的检查点，不应误认为新一次全扫；改变输入或内核将拒绝旧 CCD 检查点）：

```powershell
& $n21Python godot_sim/tools/capacity_v2/n21_verify.py robust_contract_r2
& $n21Python godot_sim/tools/capacity_v2/n21_verify.py S2_expand
& $n21Python godot_sim/tools/capacity_v2/n21_ccd.py s1_n20_passed --fresh
& $n21Python godot_sim/tools/capacity_v2/n21_ccd.py s2_warm --fresh
& $n21Python godot_sim/tools/capacity_v2/n21_ccd.py robust_contract_r2 --fresh
& $n21Python godot_sim/tools/capacity_v2/n21_coplanar.py
& $n21Python godot_sim/tools/capacity_v2/n21_ccd.py s1_n20_passed cavity
& $n21Python godot_sim/tools/capacity_v2/n21_ccd.py s1_n20_passed tissue
& $n21Python godot_sim/tools/capacity_v2/n21_ccd.py robust_contract_r2 cavity
& $n21Python godot_sim/tools/capacity_v2/n21_ccd.py robust_contract_r2 tissue
& $n21Python godot_sim/tools/capacity_v2/test_n21.py
& $n21Python godot_sim/tools/capacity_v2/n21_report.py
& $n21Python godot_sim/tools/capacity_v2/n21_finalize.py
```

`--fresh` 表示使用本轮正式当前内核结果目录，不是自动删除已有检查点。旧失败尝试、R1 与 N2.0 原研究夹具是交付的一部分；命令重算当前算法，不会重新生成已经归档的旧算法失败历史。必须保留它们供测试读取。R1 只供余量对照，不要用当前生成器覆盖它。重算计时和环境字符串可能变化；几何数组重复性有独立逐字节测试，非数值日志不要求相同 SHA。

源快照、全部新交付文件哈希在 `source_snapshot/` 与 `delivery_manifest.json`。原始保护快照及复核在 `protected_before.json`、`protected_after.json`。没有自动提交 Git，也没有启动下一阶段。
