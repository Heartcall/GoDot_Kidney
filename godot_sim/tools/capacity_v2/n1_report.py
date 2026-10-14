"""Assemble the implemented N1 report from computed evidence, never edit history."""
from n1_analysis import *

def report():
    a=read_json(ROOT/'D2_approval_2026_10_14_v1.json');v=read_json(ROOT/'D2_independent_volume.json')
    stats=read_json(ROOT/'path_statistics.json');p=read_json(ROOT/'capacity_partition_candidate.json')
    sensitivity=read_json(ROOT/'partition_resolution_sensitivity.json');anomalies=read_json(ROOT/'section_anomalies.json')
    tests=read_json(ROOT/'python_tests.json');checks=read_json(ROOT/'verification/independent_checks.json');template=read_json(ROOT/'capacity_target_template.json')
    database=json.loads(gzip.decompress((ROOT/'sections.json.gz').read_bytes()));records=database['stations']
    def fmt(value,d=3):return '未确认' if value is None else f'{value:.{d}f}'
    def triplet(values):return '未确认' if values is None else ' / '.join(fmt(x) for x in values)
    lines=['# Capacity V2 N1：参考容量、局部截面与容量目标准备',
       '', '实施日期：2026-10-15；D2 用户批准日期：2026-10-14。**N0 按用户批准结束；N1 分析与可视化交付，等待人工审核。未实施 N2/N3，未设置 V_min/V_max。**','',
       '## 1. 正式 D2 与独立复算','',
       '新记录：[D2_approval_2026_10_14_v1.json](../godot_sim/deformation/capacity_v2_n1_v1/D2_approval_2026_10_14_v1.json)。用户明确批准 `C11_R1_IN02_fixed_collar` 为项目容量统计域。BLADDER 截止上游、B_31/B_32 根部和现有 T_01～T_22 封闭范围计入；批准截面外的人工延伸仍排除，不恢复 C06 错删的天然腔壁。无需继续追寻人工通道前数据或内移截面。','',
       f'从 R1 顶点/面数组独立计算 **{v["V_reference_D2_mm3"]:.12f} mm³ = {v["V_reference_D2_mL"]:.15f} mL**。未从旧报告复制常数。四个原点有向三角面积分、trimesh 和三个轴向散度积分的最大差为 **{v["method_spread_mm3"]:.9g} mm³**；边界边/非流形边/退化面均为0，水密、绕序一致。','',
       '该精度仅表示同一网格的数值一致性。单位沿用已验收的 RAS mm；显示减去 `[16,16,-81] mm`。没有独立重验原 DICOM 标定。工程 D2 定义已批准，不等于独立临床边界或正常容量范围验证。Reference 是中间参考，不能推导正常端点、压力或顺应性。','',
       'D2 副本位于新版本 `d2/`，逐文件与 R1 字节一致；保留源面、源顶点重心权重、截面中心/法向/截环/封口索引及 SHA-256。源面ID为-1表示虚拟封口。D2 总积分只算一次封闭边界，不叠加分支或封口“体积”。旧 N0 待批准记录和报告未回写。虚拟封口只在测量节点，未加入 P2 腔体、组织或碰撞网格。','',
       '## 2. 截面数据库与归属方法','',
       '完整精确数据库：[sections.json.gz](../godot_sim/deformation/capacity_v2_n1_v1/sections.json.gz)；便于表格查看的量测值：[sections.csv](../godot_sim/deformation/capacity_v2_n1_v1/sections.csv)。压缩只减少文件大小，不降低浮点精度。','',
       f'共 **{len(records)} 个站点**：MAIN、B_01～B_32、BLADDER_TRANSITION 和两条保留的注水固定管壁短段；9个 J 和22个 T 以所有相连路径距端点2 mm内的站点探针统计。常规间距1 mm，J_05/J_09相关分支及短接口0.5 mm，并补充距端点0.1/0.25/0.5/1/2 mm站点。实际站点坐标、弧长和法向全部保存。','',
       '位置严格在既有控制折线上；法向采用前后0.25 mm中心线弦，不移动标记。长度/曲折度和控制点折转反映现有折线，不宣称已恢复真实连续解剖中心线曲率。','',
       '截面解析全部相交边与闭环；选择必须同时满足唯一简单闭环包含站点、既有源顶点路径归属及共享端点拓扑邻域约束。禁止最近环/最大环回退。所有环保留有序源面和边插值映射；新的测量顶点通过 D2 重心权重追溯 CT 顶点。路径标签只是已有工程证据，不是临床材料归属。','',
       '归属门槛：自身边界长度票≥0.10，非相邻路径票≤0.10；自身≥0.70且无虚拟封口段才标局部截面，其余有效环标共享连接。阈值只控制几何审核分类，不是生理阈值；未放宽门槛来增加通过数量。嵌套环或偏心孔洞不静默填平。','',
       '| 截面状态 | 数量 | 使用范围 |','| --- | ---: | --- |']
    meanings={'PATH_LOCAL_SECTION':'路径局部几何量，可用于候选尺度','SHARED_JUNCTION_OR_INTERFACE_SECTION':'共享连接/接口，不是独占分支截面',
              'AMBIGUOUS_TOPOLOGY':'候选环尺寸保留，但不填入有效局部值','OUTSIDE_APPROVED_D2_CUTOFF':'BLADDER远端已批准排除，不是新的几何失败',
              'MULTIRING_WITH_HOLE_UNRESOLVED':'嵌套/孔洞需复核，不使用外环面积冒充净面积'}
    for key,count in stats['station_status_counts'].items():lines.append(f'| {key} | {count} | {meanings.get(key,"待审核")} |')
    lines+=['', '长短轴采用面积二阶矩等效椭圆直径，扁率=`1-短轴/长轴`；不是包围框，也不是经过医学确认的肾盂径线。相对宽/窄由有效局部面积四分位标记，不能诊断狭窄。','',
       '### 全路径统计','', '| 路径 | 已采样长度 mm | 曲折度 | 局部面积最小/中位/最大 mm² | 扁率最小/中位/最大 | 局部/共享/待定 |',
       '| --- | ---: | ---: | --- | --- | --- |']
    for row in stats['paths']:
        c=row['status_counts'];local=c.get('PATH_LOCAL_SECTION',0);shared=c.get('SHARED_JUNCTION_OR_INTERFACE_SECTION',0);other=row['stations']-local-shared
        lines.append(f'| {row["id"]} | {row["length_mm"]:.3f} | {row["tortuosity_length_over_chord"]:.4f} | {triplet(row["local_area_min_median_max_mm2"])} | {triplet(row["local_metric_min_median_max"]["flattening_1_minus_minor_major"])} | {local}/{shared}/{other} |')
    lines+=['', 'IN_01/IN_02仅统计 D2 保留的1 mm与约0.857417 mm段，不把被排除的远端管道计入。最小局部截面站点、坐标、周长/等效半径/长短轴范围、控制点转角及全部候选环统计见 [path_statistics.json](../godot_sim/deformation/capacity_v2_n1_v1/path_statistics.json)。若“未确认”，不是尺寸为0。','',
       '### J/T 探针覆盖','', '| 节点 | 相连路径 | 探针数 | 已确认几何探针面积范围 mm² |', '| --- | --- | ---: | --- |']
    for row in stats['nodes']:
        lines.append(f'| {row["id"]} | {", ".join(row["incident_paths"])} | {len(row["probe_station_ids"])} | {triplet(row["probe_metric_min_median_max"]["area_mm2"])} |')
    lines+=['', '节点统计包含共享截面，不能把其面积解释为一个唯一横截面，更不能相加得到节点容量。各类原始探针状态和源坐标都有记录。','',
       '### 异常和高复杂度区域','',
       f'共 **{len(anomalies["flags"])} 对相邻有效站点**触发复核：相邻面积比超过1.35或切向角超过20°。详见 [section_anomalies.json](../godot_sim/deformation/capacity_v2_n1_v1/section_anomalies.json)。这是采样连续性提示，原因候选包括控制折线方向变化、进入共享连接以及真实参考形态变化，不等于已诊断病理狭窄。图中无效站点断线，不跨缺失值伪造平滑曲线。','',
       '- J_05：B_11上游、B_12～B_18七条天然下游和B_31接口；共9条相连路径，所谓八条下游包含接口，不能误写为八条天然分支。',
       '- J_09：B_27上游、B_28～B_30天然下游及B_32接口，需共同查看。',
       '- B_32全长约2.843529 mm，15个站点中3个共享、12个归属待定，没有独占局部截面。候选环面积/长短轴仍保存，但不作为独立管径控制依据。',
       '- B_31有5个局部、7个共享、17个归属待定站点；与J_05一起审核，不再沿所有天然分支扩散接口参数。',
       '- B_27:25与B_30:4发现偏心嵌套环/孔洞情况，标MULTIRING_WITH_HOLE_UNRESOLVED；外环候选面积分别约151.755和205.051 mm²，不当作有效净截面。',
       '- BLADDER_TRANSITION前8个站点位于用户批准截止面外，保留为排除证据；不把它们当域内测量遗漏。','',
       '![参考截面积曲线](../godot_sim/deformation/capacity_v2_n1_v1/section_area_profiles.png)','',
       '## 3. 无重叠局部容量：候选账，不是正式解剖分区','',
       '本轮没有可靠建立全域连续的独占分支容量。采用明确可审计的候选：D2 内互不重叠的轴对齐立方单元；中心到壁距离须超过半对角线+0.0002 mm，并通过3/5奇数射线符号一致性。使用中心化float32空间查询，所以这是保守计算筛查，非形式化精确内点证明。','',
       '每个内部单元只有一个标签。中心线种子只在距单元中心≤0.75h时采用，且中心至表面距离大于0.866h：该直线配对受局部内球保护，不通过近邻跨壁绑定。多路径种子冲突不使用。位移尚未求解；标签仅在六邻接内部单元图上做多源测地传播，近而不相连的分支不能跨空隙传播。','',
       'J候选共享区半径2.5 mm，T候选末端区半径2 mm，且必须属于该节点相连路径的测地所有者；多个节点冲突则归共享未定。半径是显式工程边界，不是医学肾盏尺度。网格侵蚀可能断开细连接，无种子成分保留未归属；本例该分辨率内部图为一个分量，无无种子单元。','',
       f'0.5 mm网格共 **{p["interior_cubes"]:,} 个内部单元，{p["cube_interior_volume_mL"]:.9f} mL**；边界补集 **{p["boundary_remainder_mL"]:.9f} mL（{p["boundary_remainder_mL"]/p["D2_total_mL"]*100:.3f}%）**明确不分配。这个补集是精确D2减去候选内部单元量的账目项，不是另一个已分割解剖器官。','',
       f'各候选标签加未归属项之和为 **{p["partition_sum_mL"]:.15f} mL**，数值残差 **{p["residual_mm3"]:.9g} mm³**。这种守恒不意味着已完成区域解剖验证；没有归一化放大内部标签填满边界，也没有累加重叠的截面积积分。','',
       '| 候选区域 | 内部单元/补集容量 mL | D2比例 |','| --- | ---: | ---: |']
    for row in p['regions']:lines.append(f'| {row["id"]} | {row["candidate_volume_mL"]:.6f} | {row["fraction_D2"]*100:.3f}% |')
    lines+=['', '上述各行全部是候选工程账目，不是临床独立分支容量。内部单元、原点、格点、测地前驱、路径所有者、区域标签和最近D2/源面及重心坐标均保存；最近面只用于溯源，未用于无约束供体绑定。','',
       '### 边界与分辨率敏感性','',
       f'0.75 mm时内部量为 **{sensitivity["coarse"]["cube_interior_volume_mL"]:.9f} mL**，边界余量 **{sensitivity["coarse"]["boundary_remainder_mL"]:.9f} mL**；0.5 mm边界余量减少约 **{sensitivity["coarse"]["boundary_remainder_mL"]-p["boundary_remainder_mL"]:.9f} mL**。细分辨率仍有较大余量，不能声称局部容量已收敛。','',
       '对J/T候选半径另做0.75/1/1.25倍敏感性，所有方案独占标签+未归属均守恒，但各区变化说明边界仍需审核；数值见 [partition_resolution_sensitivity.json](../godot_sim/deformation/capacity_v2_n1_v1/partition_resolution_sensitivity.json)。这些变化不是生理置信区间。不移动已批准D2截面做新的边界搜索；N0的局部截面差分保留为历史证据，非临床容量不确定性。','',
       '![候选容量账](../godot_sim/deformation/capacity_v2_n1_v1/candidate_capacity_accounting.png)','',
       '正式局部容量如确有必要，下一步需人工批准共享区域/连接截面后建立经检验的体积分区或自适应切割单元；在此之前保持候选和未归属，不宣称上述表格满足独占解剖容量标定。','',
       '## 4. 双向形变设计与医学资料','',
       '详见 [局部形变设计与医学标定准备](kidney_irrigation_capacity_v2_n1_design.md)，比较局部截面放样、径向场、形状保持约束优化和连续体模型。推荐可信截面尺度+拓扑局部径向初始场+离线形状/接触/容量约束优化；不整体缩放，不用旧0.2 mm场推导端点。','',
       f'参数表 [capacity_target_template.json](../godot_sim/deformation/capacity_v2_n1_v1/capacity_target_template.json)列出 **{len(template["regional_parameters"])} 个候选区域参数**，Reference值为0，Contracted/Expanded目标、响应权重、V_min/V_max与生理量均为null。它是设计表，没有生成形变。单个容量约束不能唯一确定全部局部位移，仍需区域先验、形状保持、固定区、组织相对运动和接触约束。','',
       '本轮重新阅读成人离体顺应性、健康成人补液影像、CT肾盂肾盏静态测容及灌注模型原始研究，并逐项核对其测量范围与D2的差异。没有直接适用的正常成人容量端点；未读到的健康组数据不填入。生理标定路线需要同域影像/实验及状态、出口、漏液与不确定性；演示路线需用户另批不对称工程端点并标待标定。具体来源链接、阅读范围和待批准项见设计文档，旧医学证据报告不改写。','',
       '## 5. 实际测试、运行与保护','',
       f'- Python自动测试 **{tests["run"]}/{tests["run"]}通过**，失败{tests["failures"]}、错误{tests["errors"]}；含旁边更大但不连通的截环、不选最大环、嵌套环/偏心孔洞拒绝、面积惯性、源面映射、固定输入及候选账守恒。',
       f'- 重复完整构建：**{checks["repeat_build"]["checked_products"]}个分析产物字节一致**，没有重新计算任何腔体/组织位移。']
    for backend,row in checks['graphics'].items():
        lines.append(f'- Godot {backend}：**{row["runtime_checks"]}项通过，{row["screenshots"]}张实际截图**；D2源壁/封口位置float32及面索引与冻结资源逐字节一致；已验收腔体/组织Reference的完整实际顶点、法线、索引与N0回读二进制逐字节一致，{row["fixed_cavity_vertices_exact"]}个固定腔体顶点原位。')
    lines+=['- 两种后端测量网格法线回读有限，与输入的最大分量差记录在独立检查中；ArrayMesh法线编码量化差单独记录，未降输入精度。',
       f'- **{checks["protected_files_unchanged"]}个受保护文件哈希不变**，六份权威输入SHA-256不变；原OBJ、Marker、拓扑、掩码、旧形变、N0证据、P2场景/控制、主场景和碰撞均未修改。',
       '- 测试设备：Godot4.7 stable，NVIDIA RTX4070Ti，1440×1000；Compatibility/OpenGL和Forward+/Vulkan各真实运行。仅验证静态审核显示，不是P2播放FPS测试。历史18～19FPS限制未解决，未改写为已达标。',
       '- 旧点/边接触与共面重叠基线保留；用户所见无异常只适用于当时视角。本轮无新形变，未无谓重复全量接触扫描；未来新形变需重新做有限几何门禁。','',
       '开发中修正了GDScript不支持的格式字符和默认剖切开关与材质不一致；一次旧输出目录PNG写入失败的运行未计为通过，随后在独立最终输出目录重新执行并逐图验证。法线核对另发现分类着色曾把已编码回读的法线重新提交，造成重复编码；现缓存源float32数组，每次着色均从源数组提交，重复切换的实际法线与首次实际法线逐字节一致。未引用顶点的零法线不作为实体面法线比较，真实面片使用顶点的编码差单列。早期verification/compatibility、*_final和*_release不是最终交付验收证据，最终以*_delivery及independent_checks.json为准。未放宽任何几何门槛。','',
       '## 6. Godot人工审核','',
       '打开 `res://capacity_v2_n1_preview.tscn`，按 **F6**；它是新的独立Reference审核场景，不替换N0或P2。','',
       '1. 先看完整D2、金色独立测量封口；当前固定s=0，没有新版充盈控制。',
       '2. 选择MAIN/B路径和实际弧长站点，点击“正对当前截面定位”；查看面积、惯性长短轴、扁率、归属状态及候选容量。',
       '3. 用J/T下拉定位全部节点，重点检查J_05/J_09及B_31/B_32；共享区域不能独立重复计容。',
       '4. 表面分类着色只是可审计的区域示意，不是精确体积分区表面；金色所选截环保持完整精确点，其他拓扑相关环显示线最多64点，其完整精确环和映射仍在数据库。诊断线可透视，不代表实体腔壁。',
       '5. 腔壁、组织和虚拟封口分别显隐；使用不透明剖切和位置滑块、鼠标左键旋转/中键平移/滚轮缩放，R复位。未采用透明混合。',
       '6. 保存审核现场只写新版本user_sessions；请反馈路径/节点、站点ID及认为归属不合理的环。','',
       '![Godot完整D2](../godot_sim/deformation/capacity_v2_n1_v1/verification/forward_delivery/D2_reference_overview.png)',
       '![Godot B32共享接口](../godot_sim/deformation/capacity_v2_n1_v1/verification/forward_delivery/B_32_section.png)',
       '![Godot候选区域示意](../godot_sim/deformation/capacity_v2_n1_v1/verification/forward_delivery/candidate_region_overlay.png)','',
       '## 7. 新文件与可重复命令','',
       '- `tools/capacity_v2/n1_analysis.py`：固化批准、独立测容、截面/源映射、候选容量账、敏感性、图表及预览数据。',
       '- `n1_design.py`、`n1_report.py`：待批准目标表和源数据驱动报告。',
       '- `test_n1.py`、`n1_verify_outputs.py`、`verify_n1.gd`：自动测试、重复构建和实际ArrayMesh核对。',
       '- `scripts/capacity_v2_n1_preview.gd`、`capacity_v2_n1_preview.tscn`：新的审核UI，复用旧相机/读网格/不透明剖切方法，旧脚本不改。',
       '- `deformation/capacity_v2_n1_v1/`：批准记录、D2逐字节副本、压缩完整几何数据库、CSV/NPY/图表、候选账、目标模板、哈希及真实日志/截图。',
       '- 本报告及`kidney_irrigation_capacity_v2_n1_design.md`；不覆盖旧阶段报告。','',
       '在仓库根目录执行（Python需现有NumPy/SciPy/trimesh/Open3D/VTK/Matplotlib环境）：','',
       '```powershell',
       "& 'E:/Apps/Conda/miniconda3/envs/FURS/python.exe' godot_sim/tools/capacity_v2/n1_analysis.py",
       "& 'E:/Apps/Conda/miniconda3/envs/FURS/python.exe' godot_sim/tools/capacity_v2/n1_design.py",
       "& 'E:/Apps/Conda/miniconda3/envs/FURS/python.exe' godot_sim/tools/capacity_v2/test_n1.py",
       "$n1Godot = 'E:/Apps/Godot/Godot_v4.7-stable/Godot_v4.7-stable_win64_console.exe'",
       "New-Item -ItemType Directory -Force -Path 'godot_sim/deformation/capacity_v2_n1_v1/verification/compatibility_delivery','godot_sim/deformation/capacity_v2_n1_v1/verification/forward_delivery' | Out-Null",
       "& $n1Godot --path godot_sim --rendering-method gl_compatibility --resolution 1440x1000 res://capacity_v2_n1_preview.tscn -- --n1-verify=res://deformation/capacity_v2_n1_v1/verification/compatibility_delivery | Tee-Object -FilePath 'godot_sim/deformation/capacity_v2_n1_v1/verification/compatibility_delivery/godot_stdout.log'",
       "& $n1Godot --path godot_sim --rendering-method forward_plus --resolution 1440x1000 res://capacity_v2_n1_preview.tscn -- --n1-verify=res://deformation/capacity_v2_n1_v1/verification/forward_delivery | Tee-Object -FilePath 'godot_sim/deformation/capacity_v2_n1_v1/verification/forward_delivery/godot_stdout.log'",
       "& 'E:/Apps/Conda/miniconda3/envs/FURS/python.exe' godot_sim/tools/capacity_v2/n1_verify_outputs.py --repeat-build",
       "& 'E:/Apps/Conda/miniconda3/envs/FURS/python.exe' godot_sim/tools/capacity_v2/n1_report.py",
       '```','',
       '上述命令保存实际stdout日志。若自行重跑改变目录，可在验证器中对应修改目录；没有日志时不要把旧日志当新运行证据。数据构建不会运行形变求解或自动推进阶段。','',
       '## 8. 验收边界与停止','',
       '**已交付**：工程D2固化与容量复核、全路径/J/T局部数据库和异常、候选无重叠内部单元账及显式未归属量、区域形变与标定准备、真实Godot审核和自动测试。','',
       '**未解决/需审核**：复杂共享环的归属、两个偏心嵌套环、局部区域容量边界与较大未归属边界层、临床肾盂/肾盏语义及区域响应先验。它们不撤销用户已批准的D2统计范围；本轮也不要求重新移动D2截止面。','',
       '等待用户审核局部形态及候选容量分析，选择生理标定或待标定演示路线，并另行批准端点/区域响应与N2。**本轮停止在N1；没有新的Contracted/Expanded、组织求解、P3内镜集成或P4录像。**','']
    path=REPO/'docs/kidney_irrigation_capacity_v2_n1_result.md';path.write_text('\n'.join(lines),encoding='utf8')
    with (ROOT/'candidate_capacity_accounting.csv').open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=['id','candidate_volume_mL','fraction_D2','status']);writer.writeheader();writer.writerows(p['regions'])
    write_json(ROOT/'delivery_manifest.json',{'schema':'N1_DELIVERY_V1','D2_project_approved':True,'N1_waiting_user_review':True,'N2_started':False,
       'V_reference_D2_mL':a['V_reference_D2_mL'],'V_min_mL':None,'V_max_mL':None,'formal_anatomical_branch_volumes':False,
       'report_sha256':sha(path),'design_sha256':sha(REPO/'docs/kidney_irrigation_capacity_v2_n1_design.md'),
       'approval_sha256':sha(ROOT/'D2_approval_2026_10_14_v1.json'),'source_arrays_sha256':AUTHORITY,
       'implementation_sha256':{p.relative_to(REPO).as_posix():sha(p) for p in [PROJECT/'capacity_v2_n1_preview.tscn',PROJECT/'scripts/capacity_v2_n1_preview.gd']+sorted((PROJECT/'tools/capacity_v2').glob('*n1*')) if p.is_file()},
       'test_result_sha256':sha(ROOT/'python_tests.json'),'independent_checks_sha256':sha(ROOT/'verification/independent_checks.json')})
    print('N1 report generated',path)

if __name__=='__main__':report()

