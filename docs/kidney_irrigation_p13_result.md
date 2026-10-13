# P1.3 局部静态膨胀位移场：实施结果

日期：2026-10-13。状态：实现与自动检查完成，等待用户在 Godot 检查。停在 P1.3。

## 本轮结果

已生成 MAIN（A_Start → A_Middle → A_End → J_01）和 J_02 子树 B_01～B_05 的单个静态位移场。最大位移 0.200 mm；参考顶点、面索引、坐标系均沿用已认可的 P1.2 数据。

三条人工通道的全部 3675 个固定顶点位移严格为零。没有修改原始 OBJ、Marker3D、人工拓扑、resolved 数据或 main.tscn。P1.2 目录内全部 20 个既有文件 SHA-256 保持一致。包括上述资产在内的 27 个受保护文件检查记录见 `godot_sim/deformation/p13_static/implementation_validation.json`。

本轮没有实现三态库、充盈度滑块、注排水状态机、组织映射、动态碰撞或录像。

## 实际新增和修改文件

| 文件 | 职责 |
| --- | --- |
| `godot_sim/tools/build_local_displacement.py` | 读取已有掩码，构建连续位移候选、约束平滑、静态质量检查及导出 |
| `godot_sim/deformation/local_displacement_config.json` | 六条测试路径、0.2 mm 上限、6 mm 测试区域淡出和平滑参数 |
| `godot_sim/tools/test_local_displacement.py` | 11 项算法和生成数据回归检查 |
| `godot_sim/scripts/local_displacement_preview.gd` | 静态网格、大小／方向着色、参考线叠加和局部观察 |
| `godot_sim/local_displacement_preview.tscn` | 独立预览入口，不修改主场景 |
| `godot_sim/deformation/p13_static/` | 可重建数据、数值报告和实施验证记录 |
| `docs/kidney_irrigation_p1_guide.md` | 仅更新顶部进度，保留历史路线 |
| 本文件 | 实际结果、限制和查看方式 |

Godot 渲染截图及日志在 `godot_sim/analysis/irrigation_baseline/p13_static_preview/` 和同级 `p13_static_stdout.log`、`p13_static_stderr.log`。此分析目录沿用仓库忽略规则，文件在本地可查看、可重新生成。

## 位移场构建方法

1. 从 `deformation/p1_masks/` 直接读取 `vertices/faces/normals/weights/regions/path_owner/port_fixed_masks`。先核对 P1.2 产物哈希以及源 OBJ、resolved 输入哈希；不调用掩码生成流程。
2. MAIN、B_01～B_05 的既有路径归属顶点作为本轮测试区域。额外的**局部激活系数**沿连通表面在 6 mm 内平滑降到零。它仅控制本轮测试范围，不改变或替换 P1.2 的材料区域和接口权重。邻近接点允许小幅淡出，其余远端保持零位移。
3. 在原折线上求投影中心和插值切向，构造横向径向分量。结合局部腔壁法线、局部管径估计，使用连续软权重混合六条路径的候选方向；避免在最近路径标签边界硬切换方向。T_01～T_04 附近提高法线响应，使端帽也能向外膨胀。
4. 用带目标项的表面图 Laplacian 平滑向量场；固定顶点和未激活顶点施加零约束。平滑的是位移候选，不是原始顶点位置。平滑强度为 30。
5. 去除向腔内的法线分量，整体限制候选幅度，再乘**原 P1.2 权重**和局部激活系数。因此 `|d_i| ≤ 0.2 × weight_P12_i × activity_i`；固定区最终再次置为严格零。
6. 保持原参考顶点顺序和面索引，通过 `reference_vertices + displacement` 构造唯一静态终点并重新计算法线。Godot 使用同一套导出数组建立 ArrayMesh，不依赖 Godot OBJ 导入后的顶点编号。

0.2 mm 是本轮几何调试上限，不代表已标定的生理膨胀量。测试区域外的零位移也不代表那些天然分支在真实注水中不会变形。

## 输出数据格式

目录：`godot_sim/deformation/p13_static/`。单位 mm，坐标为腔体网格局部坐标；N=25024，M=50044。

| 文件 | 数组／格式 |
| --- | --- |
| `reference_vertices.npy` | N×3，原 P1.2 顶点的精确副本 |
| `faces.npy` | M×3，原 P1.2 面索引的精确副本 |
| `displacement.npy` | N×3，float64 位移；终点为 reference + displacement |
| `displacement_magnitude_mm.npy` | N，位移模长 |
| `displacement_direction.npy` | N×3，有位移处为单位方向，零位移处为零向量 |
| `candidate_direction.npy` | N×3，平滑前的方向调试数据 |
| `approved_p12_weights.npy` | N，原 P1.2 权重精确副本，便于追溯 |
| `test_region_activity.npy` | N，局部测试激活系数，范围 [0,1] |
| `test_region_distance_mm.npy` | N，表面到测试种子的距离；支持域外用 -1 表示，避免保存无穷值 |
| `reference_normals.npy`、`deformed_normals.npy` | N×3，参考／终点法线 |
| `reference_self_intersection_pairs.npy`、`deformed_self_intersection_pairs.npy` | 相交三角面的索引对，零基编号 |
| `displacement_report.json` | 数值结果、构建参数、输入和输出哈希、限制 |
| `displacement_preview.json`、`displacement_preview.bin` | Godot 元数据与二进制数组；float32，预览面绕序转换为 Godot 顺时针约定 |

二进制头为 `KDSP0001` 与 uint32 N/M；随后依次为 reference、displacement、reference normals、deformed normals、P1.2 weights、activity、magnitude，最后为 uint32 面索引。总长度为 `16 + 60*N + 12*M` 字节。预览加载时检查格式和哈希。

## 数值与网格质量

| 检查 | 实测结果 |
| --- | --- |
| 顶点／三角面 | 25024 / 50044；面索引不变 |
| 位移有限性 | 全部有限 |
| 最大位移 | 0.200000 mm |
| 位移 > 1e-8 mm 的顶点 | 6566 |
| 固定顶点 | BLADDER 2793；IN_01 397；IN_02 485；合计 3675 |
| 固定区最大位移 | 三条通道分别为 0 mm |
| 全网格最大相邻位移差 | 0.084088 mm |
| 最大边位移梯度 `|d_i-d_j|/|x_i-x_j|` | 0.116016，小于本轮调试阈值 0.2 |
| 退化面（面积 < 1e-10 mm²） | 参考 0；终点 0 |
| 新旧面法线点积非正 | 0 |
| 最大面法线转角 | 13.0894° |
| 最小终点面面积 | 0.000062592 mm² |
| 面积比（终点／参考） | 0.936585～1.288064；调试阈值 0.8～1.35 |
| 面积比 1%～99% 分位 | 0.996109～1.088372 |
| 最小三角形质量 | 参考和终点均为 0.0109519；保留了源网格已有的狭长小面 |
| 水密性 | 参考和终点均为 true |
| 体积 | 19723.0774 → 20118.9468 mm³，增加 395.8695 mm³（约 2.007%） |
| 全网格三角面相交检查 | 参考 1 对；终点 1 对；新增 0 对 |

面法线点积用于提示翻面，不单独作为无自交证明。相交检测使用 Open3D 0.19 对完整参考网格和静态终点分别执行。

**既有源网格问题：**三角面 `[1856,1862]` 在 B_24 附近已相交。本轮检测前后是同一对，相关顶点位移全部为零；未修复或修改源网格。因此本轮结果是“未新增自交”，不是“网格完全无自交”。水密性也不等于无自交，以上体积仅作几何调试观测。

### 接点邻域与末端

邻域统计使用到 J_01、J_02 或 B_32 路径中点的欧氏距离 ≤8 mm 的顶点；不是新的分区掩码。

| 邻域 | 顶点数 | 最大位移 mm | 最大相邻位移差 mm | 最大边位移梯度 |
| --- | ---: | ---: | ---: | ---: |
| J_01 | 899 | 0.191226 | 0.052361 | 0.051543 |
| J_02 | 993 | 0.166401 | 0.065724 | 0.094547 |
| B_32 | 920 | 0 | 0 | 0 |

J_01 和 J_02 的大小和方向显示未见明显断裂，仍需用户旋转视角验收。B_32 不在本轮激活子树内，整个检查邻域保持零位移；这证明本轮未扰动它，不能替代将来激活该接口后的连续性检查。

末端 T_01～T_04 的标记平面外侧端帽分别检查 60、128、47、25 个顶点；最大端帽位移分别为 0.171544、0.170619、0.167882、0.133482 mm，平均轴向位移均向外，未将天然端帽误固定。

## 实际执行的验证

- Python 构建器实际运行，包含全网格终点质量和相交检查。
- 同一输入重复构建；16 个数组／二进制／元数据／报告文件哈希全部一致。
- `test_local_displacement.py` 的 11 项测试全部通过：折线结点切向、平滑与固定约束、相交检测器、原数组复用、三通道零位移、幅度及方向、分支和端帽响应、接点连续性、网格质量、既有相交保留、Godot 二进制布局和输出哈希。
- Godot 4.7 headless 场景加载通过；图形模式 Forward+ / RTX 4070 Ti 实际渲染并导出 9 张 1280×800 截图，退出码 0、错误日志为空。
- 查看截图后调整 J_01 默认观察方向，避免被其他分支遮挡；J_02 放大视图保留接点和末端上下文。没有因视角调整更改位移数据。
- 27 个受保护文件哈希一致，包括两个源 OBJ、保存的标记场景、标记 JSON、两份拓扑 JSON、main.tscn 和全部既有 P1.2 数据。

在仓库根目录重新运行（依赖当前 FURS 环境里的 numpy/scipy/trimesh/open3d）：

```powershell
& 'E:/Apps/Conda/miniconda3/envs/FURS/python.exe' godot_sim/tools/build_local_displacement.py
& 'E:/Apps/Conda/miniconda3/envs/FURS/python.exe' godot_sim/tools/test_local_displacement.py
```

重新导出截图：

```powershell
& 'E:/Apps/Godot/Godot_v4.7-stable/Godot_v4.7-stable_win64_console.exe' --path godot_sim res://local_displacement_preview.tscn --resolution 1280x800 -- --displacement-validation-dir=res://analysis/irrigation_baseline/p13_static_preview
```

## 在 Godot 中检查

1. 打开本仓库的 `godot_sim/project.godot`。
2. 在 FileSystem 双击 `res://local_displacement_preview.tscn`，按 **F6（运行当前场景）**。数据已生成，无需先运行掩码工具；F5 仍进入原主场景。
3. 点击“主腔室”“J_01”“J_02”“B_32”调整观察位置；左键拖动旋转、中键拖动平移、滚轮缩放、R 恢复全模型。
4. 按 **1** 看位移大小：灰色为零，蓝→青→红对应 0～0.2 mm；灰色同时包含固定人工管道和未激活天然区域，具体固定分类沿用原 P1.2 预览。
5. 按 **2** 看方向：RGB=`(单位方向 XYZ + 1)/2`，黄色箭头指示向外位移。仅箭头长度放大 6 倍，网格始终使用真实 0.2 mm 上限。
6. 按 **3** 看粉色膨胀表面与蓝色参考网格稀疏线叠加；参考线使用透视叠加辅助观察，不代表终点表面裂纹。
7. 固定同一镜头，按 **4 / 5** 在参考形态和单个静态膨胀终点间切换。没有中间态或滑块；0.2 mm 变化较小，可放大接点和端帽观察。
8. 可勾选“显示本轮中心路径”，显示六条原有路径作为位置参照。

本轮截图：`full_magnitude.png`、`main_magnitude.png`、`j01_magnitude.png`、`j02_magnitude.png`、`j02_direction.png`、`j02_overlay.png`、`j02_reference.png`、`j02_deformed.png`、`b32_magnitude.png`。

## 剩余问题与边界

- 等待用户确认 MAIN、J_01、J_02 和 T_01～T_04 的静态外观、方向与连续性。
- B_24 源自交及源网格狭长小面保留并单独记录；进一步增大幅度前仍需关注几何风险。
- 本轮仅验证参考与 0.2 mm 静态终点。尚未证明所有插值时刻无碰撞，也未验证组织壁厚、外层组织响应或器械接触。
- B_32 本轮保持零位移；全自然分支扩展时必须重新检查其短接口激活后的梯度与质量。
- 本轮为局部几何位移算法，尚未进行压力、流量、材料参数或生理幅度标定。

用户检查 P1.3 后，再按授权推进 P1.4～P1.5；本轮在此暂停。
