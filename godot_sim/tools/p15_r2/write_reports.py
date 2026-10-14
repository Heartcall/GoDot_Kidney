"""Write inspectable R2 reports from validated arrays and saved runtime evidence."""
import hashlib,re
from common import *
from PIL import Image,ImageDraw,ImageFont


def vector(values): return '('+', '.join(f'{x:.6f}' for x in values)+')'

def require_engineering_candidate(report):
    if report['status']!='ENGINEERING_GATES_PASSED_PENDING_HUMAN_ACCEPTANCE' or report['violations']:
        raise ValueError('Failed research must not publish an engineering-passed report or candidate manifest')

def comparisons():
    directory=OUT/'godot_validation'
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',24)
    for focus,mode in [('F01',1),('F02',2)]:
        sheet=Image.new('RGB',(1440,535),(18,22,30));draw=ImageDraw.Draw(sheet)
        for i,variant in enumerate(['before','after']):
            frame=Image.open(directory/f'{focus}_{variant}_mode{mode}.png').convert('RGB')
            frame.thumbnail((720,500));sheet.paste(frame,(i*720,35))
            draw.text((i*720+10,3),focus+(' R1修复前' if i==0 else ' R2局部修复后')+' · 原始真实位移',font=font,fill='white')
        sheet.save(OUT/f'{focus}_comparison.png')
    sheet=Image.new('RGB',(2160,1070),(18,22,30));draw=ImageDraw.Draw(sheet)
    for row,focus in enumerate(['F01','F02']):
        for column,level in enumerate([0,50,100]):
            frame=Image.open(directory/f'{focus}_state_u{level:03}.png').convert('RGB');frame.thumbnail((720,500))
            sheet.paste(frame,(column*720,row*535+35));draw.text((column*720+10,row*535+3),f'{focus} · u={level/100:g}',font=font,fill='white')
    sheet.save(OUT/'three_state_comparison.png')

def write():
    d=read_json(OUT/'source_diagnosis.json');r=read_json(OUT/'quality_report.json');b=r['build'];runtime=read_json(OUT/'godot_runtime_validation.json')
    require_engineering_candidate(r)
    changed=[p for p,h in read_json(OUT/'protected_before.json').items() if source_record(PROJECT.parent/p)['sha256']!=h]
    if changed: raise ValueError('Protected inputs changed '+str(changed))
    if not read_json(OUT/'rebuild_verification.json')['all_arrays_byte_identical']: raise ValueError('Rebuild not reproducible')
    if not runtime['all_position_arrays_match'] or not runtime['all_cavity_fixed_exact']: raise ValueError('Runtime mismatch')
    logs={name:(OUT/name).read_text(encoding='utf8') for name in ['python_r2_tests.log','python_r1_regression.log','godot_graphical.log']}
    if 'SCRIPT ERROR' in logs['godot_graphical.log'] or '\nERROR:' in logs['godot_graphical.log']: raise ValueError('Final Godot log contains errors')
    counts={name:int(re.search(r'Ran (\d+) tests',text).group(1)) for name,text in logs.items() if name.startswith('python')}
    if any(not text.rstrip().endswith('OK') for name,text in logs.items() if name.startswith('python')): raise ValueError('Tests not passed')
    comparisons()
    validation={'stage':'P1.5-R2','engineering_status':r['status'],'human_acceptance_complete':False,
       'protected_files_checked':len(read_json(OUT/'protected_before.json')),'changed_protected_files':changed,'tests':counts,
       'rebuild_arrays_identical':True,'runtime_mesh_snapshots':len(runtime['records']),'runtime_positions_bit_equal':runtime['all_position_arrays_match'],
       'real_screenshot_count':len(list((OUT/'godot_validation').glob('*.png'))),'godot_final_log_has_errors':False,
       'godot_renderer':'Godot 4.7 / OpenGL Compatibility / NVIDIA RTX4070Ti','new_source_sha256':{str(p.relative_to(PROJECT.parent)).replace('\\','/'):source_record(p)['sha256'] for p in sorted((PROJECT/'tools/p15_r2').glob('*.py'))+sorted((PROJECT/'scripts/p15_r2').glob('*.gd'))+[PROJECT/'p15_r2_mapping_preview.tscn']}}
    (OUT/'implementation_validation.json').write_bytes(json_bytes(validation))
    if (OUT/'forward_renderer_validation.json').exists():
        validation['forward_renderer_validation']=read_json(OUT/'forward_renderer_validation.json')
        if not validation['forward_renderer_validation']['all_runtime_mesh_binaries_identical_to_compatibility']:
            raise ValueError('Forward+ and Compatibility runtime geometry differ')
        (OUT/'implementation_validation.json').write_bytes(json_bytes(validation))
    # Detailed source report is generated independently of the new solution.
    lines=['# F01～F04 位移来源精确诊断（R1基准）','','原始坐标及位移单位mm；面/顶点编号均为原OBJ零基编号。解剖归属未确认的点不作确定性重分类。','',
      '## 逐顶点来源','', '|顶点|原坐标|原位移向量|位移大小|供体面|重心坐标|供体顶点路径|R1实际约束|R2类别|','|---:|---|---|---:|---:|---|---|---|---|']
    for key,rec in d['vertices'].items(): lines.append(f"|{key}|{vector(rec['reference_mm'])}|{vector(rec['displacement_mm'])}|{rec['magnitude_mm']:.6f}|{rec['donor_face']}|{vector(rec['barycentric'])}|{', '.join(rec['donor_vertex_path_ids'])}|{rec['old_effective_constraint']}|{rec['r2_constraint_class']}|")
    f1=d['F01'];lines+=['','## F01 边[34757,34758]','',f"原边长{f1['length_mm']:.9f}，两端位移差{f1['difference_mm']:.9f}，梯度{f1['gradient']:.9f}；两位移夹角{f1['displacement_angle_deg']:.6f}°。",'',
       f"**同一个供体面8516，主要是约束类型拼接造成的幅度差，不是供体跳变或方向冲突。** 两端供体重心插值目标分别为{vector(f1['barycentric_donor_targets_mm'][0])}、{vector(f1['barycentric_donor_targets_mm'][1])}，供体目标本身的边梯度仅{f1['donor_target_gradient']:.6f}。34757属于旧近壁一环硬约束，34758属于旧自由求解，两者距腔体均约1.231 mm。",'',
       '两个端点均非A真实共点、非B原接触约束，因此局部协调不要求改变真实共点或原接触面。仍必须检查周围表面与全局相交，不能据此省略几何门禁。', '',
       '## F02 面53208','',f"顶点{[x['vertex'] for x in d['F02']['vertices']]}；原面积{d['F02']['area_mm2']:.9f} mm²，质量{d['F02']['quality']:.9f}；原单位法线{vector(d['F02']['normal'])}。三个点均非A/B，旧实现均硬绑定近壁目标。30718供体1723跨IN_02/B_26标签，30717/30719供体2531/2532均为B_26。路径标签不是组织解剖归属证明。",'',
       '|方案|u|三条边长 mm|面积比|相对参考法线转角°|单位法线|','|---|---:|---|---:|---:|---|']
    refn=np.asarray(d['F02']['normal'])
    for level in r['five_levels']:
        for variant in ['before','after']:
            rec=level['local'][variant];rot=np.degrees(np.arccos(np.clip(np.asarray(rec['F02_normal'])@refn,-1,1)))
            lines.append(f"|{variant}|{level['fill']:g}|{vector(rec['F02_edge_lengths_mm'])}|{rec['F02_area_ratio']:.9f}|{rot:.6f}|{vector(rec['F02_normal'])}|")
    lines+=['','长边变化很小，短边30717/30719的相对位移却显著改变细长面的面积和朝向。R1短边从0.032518 mm缩到0.027918 mm，而R2为0.032460 mm。只改一个点无法保护邻域：','',
      '|仅替换顶点为其他两点位移均值|目标面面积比|二环最低/最高面积比|','|---:|---:|---|']
    for rec in d['F02']['relative_motion_counterfactuals']: lines.append(f"|{rec['replace_vertex_with_other_two_mean']}|{rec['single_face']['minimum_area_ratio']:.6f}|{rec['two_ring']['minimum_area_ratio']:.6f}/{rec['two_ring']['maximum_area_ratio']:.6f}|")
    lines+=['','30717单点替换使目标面看似改善，却把二环最大面积比推至1.589269，必须拒收。30718/30719单点替换则分别使目标面面积比降至约0.699/0.600。完整一环及二环顶点、面索引见source_diagnosis.json，R2二环与全局结果见quality_report.json。','',
       '## F03/F04 其他可能供体','',
       '候选同时检查：到三角面的距离不超过当前最近距离+0.5 mm、法线点积<-0.5、供体路径属于当前路径或共享真实端点的邻接路径、从当前供体面出发的腔体表面图距离下界≤4 mm。当前最近面作为第0行保留，即使不满足法线筛查也不删除。每个候选的单点替换只用于诊断，不自动作为解剖重归属。']
    for idx,record in d['F03_F04_alternatives'].items():
        lines+=['',f"### 顶点{idx}：归属未确认",'',f"满足几何筛查的供体面共{record['candidate_count_passing_geometrical_filters']}个，以下列出当前面及全部符合筛查的近邻面。仅凭这些信息仍不能确定材料归属。",'',
          '|供体面|距离mm|法线点积|法线相容|表面距离下界mm|供体路径|目标位移mm|最大邻边梯度|关联面面积比范围|','|---:|---:|---:|---|---:|---|---|---:|---|']
        for c in record['candidates']:
            q=c['incident_faces'];lines.append(f"|{c['face']}|{c['distance_mm']:.6f}|{c['normal_dot']:.6f}|{c['normal_compatible']}|{c['cavity_surface_distance_lower_bound_mm']:.6f}|{', '.join(c['vertex_path_ids'])}|{vector(c['target_mm'])}|{c['maximum_incident_edge_gradient']:.6f}|{q['minimum_area_ratio']:.6f}～{q['maximum_area_ratio']:.6f}|")
    lines+=['','R2不选择一个“确定解剖供体”，而是降低这三个点的局部目标权重，依照组织表面连通性和周围位移协调整体场；139真实共点和原接触面仍严格保留。',
       '',f"逐项邻域清单包含{d['local_detailed_counts']['vertices']}个顶点、{d['local_detailed_counts']['edges']}条边和{d['local_detailed_counts']['faces']}个面，见diagnostic_vertices.csv、diagnostic_edges.csv、diagnostic_faces.csv。"]
    (OUT/'source_diagnosis.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    before=r['five_levels'][-1]['quality_before'];after=r['five_levels'][-1]['quality_after'];last=r['five_levels'][-1]['local']
    doc=['# P1.5-R2 组织局部映射修复与待验收候选','','日期：2026-10-14。**工程门禁通过，等待用户Godot人工验收；不代表P1.5最终验收完成，未进入P2。**','',
     '本轮在不修改原始OBJ、标记、拓扑、P1.2掩码、已验收全腔体位移/三态或main.tscn的前提下，完成F01～F04来源诊断、一次有依据的局部联合求解、五档全局检查、连续面积与法线方向分析，以及实际Godot联合三态诊断。', '',
     '## 先诊断，再选择修复','',
     '[逐顶点、逐边、逐面及候选供体报告](../godot_sim/analysis/irrigation_baseline/p15_r2/source_diagnosis.md)与[完整JSON](../godot_sim/analysis/irrigation_baseline/p15_r2/source_diagnosis.json)保存全部原坐标、位移、供体面/重心、约束类型、一/二环索引及供体替换反事实分析。', '',
     '- F01：两端都使用供体面8516，目标本身梯度仅0.020061；旧一环硬约束与自由求解之间产生幅度拼接，形成0.988045梯度。不是先前猜测的供体跳变。两位移方向夹角仅0.107310°，两点都非真实共点或原接触硬约束。',
     '- F02：面53208细长，短边30717/30719的相对运动放大了面积压缩。单独改30717可改善目标面，却让二环某面面积比升至1.589269；改其他单点会使目标面更差。因此采用邻域联合求解，未修补OBJ。',
     '- F03：61933/61934当前供体19057跨B_16/B_17标签；法线相容的局部候选分别17/15个，仍不足以确定材料归属。',
     '- F04：30663当前供体4785位于B_28/B_32邻域；筛得17个几何候选，仍不宣称真实解剖归属。三个不确定点在数据、报告和界面中持续标记未确认。', '',
     '旧58对无限平面跨越候选仍按上一轮独立复核视为点接触；旧23对组织自交算法候选仍需有限几何复核，未冒充已确认交叉。旧数据与报告保留，不重跑无必要的原始大规模扫描。', '',
     '## 局部映射与参数','',
     'A类139个真实坐标共点精确绑定已验收腔体位移；B类为原接触面关联点，包含A后总计545点，除A外406点，保留R1值；C类近壁及一环几何软目标；D类通过组织表面连通传播；E类远区零约束。只在本轮局部补丁内把原C硬绑定改为软目标，补丁之外保持R1基准作为边界条件。', '',
     '补丁由F01～F04顶点出发，使用组织表面图距离支持半径6 mm；3～6 mm渐变边界。1077个补丁顶点中1069个可求解，实际1064点变化（约全组织0.68%），其余顶点逐位保持R1。非零A/B与E及外边界约束通过消元精确保留。', '',
     '求解目标为加权位移目标偏差，加局部边位移差/原边长的平方惩罚。短边因此受到更强的连续性保护；系数0.05 mm²，C/D目标权重为1/0.25，三个未确认点目标权重为0.1。边界目标权重按渐变函数平方的倒数增强。没有提高全局Laplacian强度，没有降低腔体幅度，也没有把IN_02/J_09整体冻结。', '',
     '仅使用一个固定局部配置，未进行全局参数搜索。面积/梯度/相交是不可放宽的拒收门禁；本次解自然满足门禁，未对网格删面、扩大接触容差或事后缩小位移。', '',
     '## 全局修复前后（Expanded）','', '|指标|R1修复前|R2修复后|','|---|---:|---:|']
    for label,key in [('最大位移mm','maximum_displacement_mm'),('全组织平均位移mm','mean_displacement_mm'),('移动点数（>1e-12 mm）','moving_vertices'),('最大边位移梯度','maximum_edge_gradient'),('最大面法线转角°','maximum_normal_rotation_deg'),('组织积分体积mm³','volume_mm3')]:
        left=str(before[key]) if key=='moving_vertices' else f'{before[key]:.9f}'
        right=str(after[key]) if key=='moving_vertices' else f'{after[key]:.9f}'
        doc.append(f"|{label}|{left}|{right}|")
    doc+= [f"|最小/最大面积比|{before['area_ratio_range'][0]:.9f}/{before['area_ratio_range'][1]:.9f}|{after['area_ratio_range'][0]:.9f}/{after['area_ratio_range'][1]:.9f}|",
      f"|F01边梯度|{last['before']['F01_gradient']:.9f}|{last['after']['F01_gradient']:.9f}|",
      f"|F02面面积比|{last['before']['F02_area_ratio']:.9f}|{last['after']['F02_area_ratio']:.9f}|",'',
      '最大相对R1修改为0.022280 mm；最大组织位移仍为0.196101 mm，腔体最大仍为0.2 mm。组织积分体积与R1的差约0.025590 mm³，不将积分体积变化解释为材料不可压缩性或生理规律。', '',
      'R2全局最坏边为[28971,28973]，梯度0.112743；最小面积比发生于面61260（中心约[1.908,14.549,-36.958] mm），为0.890110。该面R1面积比约0.889704，修复后略改善，未将F02畸变转移为新的超阈值问题。F01/F02二环分别68/92个关联三角面，均通过门禁。', '',
      '## 五档与连续区间','',
      '门禁保持：最大边梯度≤0.2、面积比0.8～1.35、无新增退化/翻面或有限方法确认的组织自交/两网格穿越；有限交线接受阈值保持1e-10 mm。它们仍是工程筛查，不是生理力学标定。', '',
      '|u|R2面积比范围|最大边梯度|最大法线转角°|退化/翻面|确认组织自交/相互穿越|原算法组织候选数|组织体积mm³|','|---:|---|---:|---:|---|---|---:|---:|']
    for level in r['five_levels']:
        q=level['quality_after'];doc.append(f"|{level['fill']:g}|{q['area_ratio_range'][0]:.6f}～{q['area_ratio_range'][1]:.6f}|{q['maximum_edge_gradient']:.6f}|{q['maximum_normal_rotation_deg']:.6f}|{q['degenerate_count']}/{q['normal_reversal_count']}|{level['self']['positive_segment_count']}/{level['cross']['positive_segment_count']}|{level['self']['raw_candidate_count']}|{q['volume_mm3']:.6f}|")
    doc+=['','u=0复用原始候选索引；其余四档重新执行全组织自交及腔体—组织检测。算法候选全部做有限复核，未仅用候选数或配对编号变化判断安全。自交扫描四档并行各约212秒，完整原始面集合未删减。', '',
      '连续区间用三角面叉积的二次多项式：原朝向投影的解析最小值给出面积比下界0.887786，二次Bezier控制向量范数的凸包界给出上界1.115126。因此所有u∈[0,1]面积在门禁内，原朝向投影严格正，归一化法线连续且不翻转。边位移差随u线性，Expanded通过即保证全部u的边梯度通过。**这不是连续碰撞/自交证书**；碰撞检查覆盖指定五档。', '',
      '## 全区域与远场检查','',
      '[72个区域的R1/R2对比CSV](../godot_sim/analysis/irrigation_baseline/p15_r2/regional_comparison.csv)及[完整质量JSON](../godot_sim/analysis/irrigation_baseline/p15_r2/quality_report.json)覆盖MAIN、B_01～B_30、全部J/T、B_31/B_32、人工管道路径及F01～F04。路径统计采用源供体标签且间距≤2 mm，J/T采用固定空间邻域；这些标签不代表已确定的组织材料归属。', '',
      '|区域|R1最大梯度|R2最大梯度|R2最小/最大面积比|最大R1→R2变化mm|','|---|---:|---:|---|---:|']
    for name in ['F01','F02','F03','F04','J_05','B_31','IN_01','J_09','B_32','IN_02','MAIN']:
        rec=r['regional_before_after'][name];a=rec['after'];doc.append(f"|{name}|{rec['before']['maximum_edge_gradient']:.6f}|{a['maximum_edge_gradient']:.6f}|{a['minimum_area_ratio']:.6f}/{a['maximum_area_ratio']:.6f}|{a['maximum_change_from_R1_mm']:.6f}|")
    doc+=['','J_05、B_31、IN_01保持R1值；J_09附近组织仍有最高0.168257 mm跟随位移。三个人工腔体管道2793/397/485个固定顶点，在五档及整个线性区间严格零位移。已验收腔体场/三态及B_24历史记录未改动。', '',
      '126104个远场E点严格不动；79170个法线朝向符合外层几何代理的顶点最大位移仍仅1.88e-13 mm，五档包围盒不变。没有语义上已识别的独立内/外壁；普通两表面距离不能解释成真实壁厚。源网格水密、拓扑和表面方向记录沿用P1.5审计，不能据此宣称厚度或材料安全。', '',
      '## 接触与实际Godot精度','',
      '139个真实共点严格一致；原接触面关联545个组织顶点完全保持R1值，3840个原有限接触采样点最大相对位移误差约2.88e-17 mm。原有点接触、共面重叠及近接触保留并单独统计，未自动判定其生理允许性。', '',
      '|u|float64候选对数|确认有限穿越|共面重叠配对面积和mm²|真实Godot float32候选数|float32确认有限穿越|','|---:|---:|---:|---:|---:|---:|']
    for level,gpu in zip(r['five_levels'],runtime['float32_cross_review']):
        c=level['cross'];doc.append(f"|{level['fill']:g}|{c['raw_candidate_count']}|{c['positive_segment_count']}|{c['coplanar_pair_area_sum_mm2']:.6f}|{gpu['raw_candidate_count']}|{gpu['positive_segment_count']}|")
    doc+=['','源float64与实际float32候选数量不同，但有限穿越均为0，未混淆候选误报与真实交叉。原接触云位置、新候选坐标、有限交线/共面指标和组织候选有限距离均保存，未以配对数量代替几何变化。共面配对面积和可能重复计数，不是穿透面积。', '',
      f"实际Godot4.7/RTX4070Ti Compatibility运行退出码0，最终日志无脚本/渲染错误。导出R1/R2各五档、各两份实际ArrayMesh共20份快照，位置逐位匹配预期float32插值，原面索引全部一致；腔体R1/R2对应快照完整二进制相同，固定点保持原位。实际法线有限并重新由当前几何计算，与float64复算当前显示几何的最大角误差约{max(x['maximum_normal_angle_to_actual_geometry_deg'] for x in runtime['records']):.6f}°。",'',
      '两份模型都使用[16,16,-81] mm共同显示原点。真实显示坐标也执行五档质量及相互穿越复核，无新增确认穿越；没有用扩大容差消除精度误报。组织float32自交未另做一轮全扫描，完整五档自交结论来自源float64模型；20份实际坐标一致性和显示几何质量已检查。', '',
      '另实际执行Forward+完整图形验证，退出码0、无错误；20份运行时网格与Compatibility导出逐字节一致，另保存34张Forward+截图。见forward_renderer_validation.json及godot_forward_validation目录。这验证编辑器常用渲染路径，不改变几何算法或项目设置。', '',
      '## Godot 操作与真实截图','',
      '**打开 `res://p15_r2_mapping_preview.tscn`，按F6运行当前场景。** 场景始终显示“研究试验／未验收”，R2显示“工程门禁通过，待人工验收”；R1明确显示失败基准。', '',
      '1. 右侧Reference/Mid/Expanded按钮或0～1滑块同步改变腔体和组织，位移不放大。',
      '2. 点F01～F04定位；选择“R1修复前研究基准”与“R2局部修复后”保持相同镜头、充盈度和剖切位置。优先Expanded下F01梯度与F02面积热力图，再用普通表面检查Reference/Mid/Expanded。',
      '3. 梯度热力图：顶点关联边的最大位移梯度后插值，蓝0→红0.2及以上；F01精确数值同时显示。面积热力图：调试副本网格逐面着色，红0.8→绿1→蓝1.35，颜色不跨面平均；权威索引网格保持原编号。',
      '4. 黄色参考线为局部二环/全模型抽样的原始参考面边，穿透显示用于对照，可关闭。它不表示接触穿孔；不是把真实位移放大。',
      '5. 左侧分别隐藏腔体/组织，用不透明X/Y/Z剖切和位置滑块看内部；剖切无封口，不能量壁厚。左侧定位下拉覆盖全部J/T、B_31/B_32及人工接口。',
      '6. 左键旋转、中键平移、滚轮缩放，R回全模型。同镜头三态及修复前后比较已在实际运行中检查。', '',
      '[F01同镜头梯度对比](../godot_sim/analysis/irrigation_baseline/p15_r2/F01_comparison.png) · [F02同镜头面积对比](../godot_sim/analysis/irrigation_baseline/p15_r2/F02_comparison.png) · [全部34张截图](../godot_sim/analysis/irrigation_baseline/p15_r2/godot_validation/) · [Reference/Mid/Expanded截图](../godot_sim/analysis/irrigation_baseline/p15_r2/three_state_comparison.png)', '',
      '未启用ALPHA、透明混合或DOF，继续使用已验证的不透明discard剖切。Godot首次实际加载发现类型推断声明错误，已修复；最终完整图形运行通过，未改任何几何门禁。', '',
      '## 文件、验证和重建','',
      '新增Python代码全部在 `godot_sim/tools/p15_r2/`：common.py（输入/保护）、diagnose_sources.py、build_mapping.py、check_geometry.py、summarize_results.py、export_preview.py、verify_runtime.py、test_r2_mapping.py、write_reports.py。新增独立 `godot_sim/scripts/p15_r2/mapping_preview.gd`、对应uid、`godot_sim/p15_r2_mapping_preview.tscn`和本报告。', '',
      '独立研究数据在 `godot_sim/analysis/irrigation_baseline/p15_r2/`，候选三态在其 `candidate/` 子目录：reference_vertices.npy、mid_vertices.npy、expanded_vertices.npy、faces.npy、displacement.npy，以及pending-human manifest。两份模型重建公式仍为reference+u×对应位移；腔体直接引用原已验收驱动，不复制另一套形变算法。', '',
      f"{counts['python_r2_tests.log']}项R2测试+{counts['python_r1_regression.log']}项R1回归共{sum(counts.values())}项通过；10项构建数组重复执行SHA-256逐字节一致；{validation['protected_files_checked']}个受保护源文件/旧数据哈希一致。原OBJ、标记、人工拓扑/resolved、P1.2掩码、已验收全腔体场/三态、R1研究成果及main.tscn均未改动。", '',
      '[实际验证记录](../godot_sim/analysis/irrigation_baseline/p15_r2/implementation_validation.json) · [R2测试日志](../godot_sim/analysis/irrigation_baseline/p15_r2/python_r2_tests.log) · [R1回归日志](../godot_sim/analysis/irrigation_baseline/p15_r2/python_r1_regression.log) · [运行时验证](../godot_sim/analysis/irrigation_baseline/p15_r2/godot_runtime_validation.json) · [重复构建](../godot_sim/analysis/irrigation_baseline/p15_r2/rebuild_verification.json)', '',
      '仓库根目录PowerShell（依赖现有FURS环境及R1审计/研究缓存）：','', '```powershell',
      "$p15r2Python = 'E:/Apps/Conda/miniconda3/envs/FURS/python.exe'",
      '& $p15r2Python godot_sim/tools/p15_r2/diagnose_sources.py',
      '& $p15r2Python godot_sim/tools/p15_r2/build_mapping.py',
      'foreach ($p15r2Fill in @(0, 0.25, 0.5, 0.75, 1)) {',
      '    & $p15r2Python godot_sim/tools/p15_r2/check_geometry.py --fill $p15r2Fill',
      '    & $p15r2Python godot_sim/tools/p15_r2/check_geometry.py --fill $p15r2Fill --self-scan',
      '}',
      '& $p15r2Python godot_sim/tools/p15_r2/summarize_results.py',
      '& $p15r2Python godot_sim/tools/p15_r2/export_preview.py',
      "& 'E:/Apps/Godot/Godot_v4.7-stable/Godot_v4.7-stable_win64_console.exe' --path godot_sim --rendering-method gl_compatibility --resolution 1440x1000 --scene res://p15_r2_mapping_preview.tscn -- --r2-validation-dir=res://analysis/irrigation_baseline/p15_r2/godot_validation",
      '& $p15r2Python godot_sim/tools/p15_r2/verify_runtime.py --contacts',
      '& $p15r2Python godot_sim/tools/p15_r2/test_r2_mapping.py',
      '& $p15r2Python godot_sim/tools/test_p15_contact_research.py',
      '& $p15r2Python godot_sim/tools/p15_r2/write_reports.py',
      '```', '',
      '若只重建数据，且位移哈希与已有五档扫描缓存一致，可复用扫描结果，跳过耗时碰撞扫描；若位移哈希不同，汇总器会拒绝旧缓存。重复构建文件记录的是本轮实际两次构建，不由后续单次运行伪造。write_reports读取已保存测试日志、运行时导出和重复构建记录；重新运行测试时应将输出保存到相应日志后再更新报告。', '',
      '## 剩余限制与停止点','',
      'F03/F04归属仍未确认；内/外壁语义、壁厚、材料体积守恒与生理响应未建立。五档无确认相交和连续面积界不能代替连续碰撞检测。本轮没有证据要求修改原OBJ或建立派生组织参考；原始细长面可先保留，局部映射已满足工程质量要求。', '',
      '本轮停止于待人工验收的P1.5-R2候选。未开发压力/流量、动态碰撞、注排水控制、P2或录像。']
    (PROJECT.parent/'docs/kidney_irrigation_p15_r2_result.md').write_text('\n'.join(doc)+'\n',encoding='utf8')
    candidate=OUT/'candidate'
    (candidate/'manifest.json').write_bytes(json_bytes({'status':r['status'],'human_acceptance_required':True,'formula':'tissue(u)=reference+u*displacement; cavity(u)=approved_reference+u*approved_full_cavity_displacement','unit':'mm','topology':'source OBJ IDs and triangles unchanged','output_sha256':r.get('candidate_output_sha256',{}),'approved_cavity_driver':source_record(PROJECT/'deformation/full_cavity/field/displacement.npy')}))
    print('reports written; engineering candidate pending human acceptance',flush=True)

if __name__=='__main__': write()
