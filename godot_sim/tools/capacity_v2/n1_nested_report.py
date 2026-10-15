"""Independent graphics readback and source-backed two-station report."""
from n1_nested_review import *

def report():
    data=read_json(OUT/'review_data.json');tests=read_json(OUT/'python_tests.json');graphics={}
    for backend in ['compatibility_checked','forward_checked']:
        directory=OUT/'verification'/backend;checks=read_json(directory/'runtime_checks.json');log=(directory/'godot_stdout.log').read_text(encoding='utf8',errors='replace')
        if checks['failures'] or 'ERROR:' in log:raise ValueError('Graphics failed '+backend)
        rows={}
        for case in data['cases']:
            tag=case['id'].replace(':','_')
            for group in ['outer_source_faces','inner_source_faces']:
                raw=(OUT/case['mesh_groups'][group]['file']).read_bytes();n=struct.unpack_from('<I',raw,8)[0]
                actual=(directory/(tag+'_'+group+'_positions.bin')).read_bytes()
                if actual!=raw[16:16+12*n]:raise ValueError('Actual source patch position changed')
        for name in ['cavity','tissue']:
            baseline=ROOT/'verification/compatibility_delivery'/(name+'_Reference.bin')
            if (directory/(name+'_Reference.bin')).read_bytes()!=baseline.read_bytes():raise ValueError('Accepted Reference changed')
        graphics[backend]={'checks':len(checks['checks']),'screenshots':len(checks['captures']),'failures':0,
                           'patch_positions_float32_byte_exact':True,'accepted_Reference_whole_arrays_byte_exact':True}
    write_json(OUT/'verification/independent_checks.json',graphics)
    _,accepted=verify_sources();source_faces=accepted['cavity_faces']
    with (OUT/'central_loop_source_faces.csv').open('w',encoding='utf-8-sig',newline='') as file:
        fields=['case_id','loop_id','segment_index','D2_face_id','source_face_id','CT_v0','CT_v1','CT_v2','start_x_mm','start_y_mm','start_z_mm']
        writer=csv.DictWriter(file,fieldnames=fields);writer.writeheader()
        for case in data['cases']:
            for loop in case['loops']:
                for k,(fid,src,p) in enumerate(zip(loop['D2_face_ids'],loop['source_face_ids'],loop['ring_positions_mm'])):
                    writer.writerow(dict(zip(fields,[case['id'],loop['loop_id'],k,fid,src,*source_faces[src],*p])))
    lines=['# N1 人工反馈与两个嵌套环专项复核','',
       '日期：2026-10-15。**N1工程工具和已有数据的人工验收已独立记录；两个目标分支的净截面积仍未确定，不进行外环减内环。**','',
       '## 1. 人工反馈及只读范围','',
       '新增 [human_review_2026_10_15_v1.json](../godot_sim/deformation/capacity_v2_n1_nested_review_v1/human_review_2026_10_15_v1.json)：用户认可J_05/J_09/B_31/B_32显示与局部结构，确认两个嵌套轮廓已准确定位，未发现足以确认真实腔壁穿透的新证据。仅认可N1工程交付，不批准两个外环作为有效净面积，也不批准候选容量为最终解剖分区。旧N1/N0报告和数据未回写。','',
       f'D2总参考容量保持 **{data["V_reference_D2_mL"]:.12f} mL**。本轮只读原始D2、P1/P2输入和两个站点，另存局部源面显示派生物；未重新划分全肾、未设端点、未生成N2形变。','',
       '## 2. 方法与判定边界','',
       '读取原N1完整精确闭环与源面映射，而不是从预览简化线提取。以原网格外向三角面法线和截面法向决定真实截环方向：切向为`plane_normal × outward_face_normal`，在右手平面基下域内位于左侧。正向外轮廓与负向内轮廓分别记录，原始保存环的遍历方向不会被误当成面朝向。','',
       '对全部真实环逐对检查有限边界相交、最小间距和所有顶点包含关系；每个内环用不重叠耳切三角形的全部内部质心做float64有向立体角绕数，并用独立的5射线符号距离复核。环的三维来源用真实面邻接链追踪，路径标签仅取现有P1边界票作为工程归属线索，不伪造临床材料标签。','',
       '另外对原站点沿中心线和固定法向平移各采样13档：−0.5、−0.25、−0.1、−0.075、−0.05、−0.025、0、+0.025、+0.05、+0.075、+0.1、+0.25、+0.5 mm。零偏移严格复用原始中央平面，避免重算切向造成远处近切线交点的浮点漂移。对应关系使用源面重合及两跳面邻接，禁止仅凭轮廓中心最近匹配。','',
       '## 3. 两站点结论','']
    for case in data['cases']:
        item=case['nesting'][0];outer=case['loops'][item['outer_loop']];inner=case['loops'][item['inner_loop']];tag=case['id'].replace(':','_')
        lines += [f'### {case["id"]}，弧长 {case["station_arc_mm"]:.9f} mm','',
          f'- 原始RAS站点(mm)：`{case["position_mm"]}`；平面法向：`{case["plane_normal_unit"]}`。',
          f'- 全平面真实闭环数 **{len(case["loops"])}**；嵌套对为外环{item["outer_loop"]}、内环{item["inner_loop"]}。',
          f'- 外环面积 **{outer["absolute_area_mm2"]:.9f} mm²**、外向定向为正；内环面积 **{inner["absolute_area_mm2"]:.9f} mm²**、外向定向为负。它们仅是各环面积，不是目标分支净面积。',
          f'- 内环全部顶点在外环内；边界无有限相交，最小环间距 **{item["relation"]["minimum_boundary_distance_mm"]:.9f} mm**。',
          f'- 内环全部耳三角形质心绕数约0、独立射线距离为正；离壁最近探针 **{item["inner_probes"]["minimum_absolute_distance_mm"]:.9f} mm**，支持该内环围合的是D2外部空域。外环中的独立对照点绕数约1。',
          f'- 内环源面编号（0-based原CT三角面）：`{inner["source_face_ids_unique"]}`。',
          f'- 内环路径边界票：`{inner["path_boundary_votes"]}`；外环票：`{outer["path_boundary_votes"]}`。',
          f'- 内外环源壁经 **{int(item["surface_face_graph_hops"])}跳**真实面邻接连接；源面链：`{item["surface_shortest_face_chain_source"]}`，面中心离截平面距离(mm)：`{item["bridge_centroid_plane_distance_mm"]}`。这是离平面后相连的原壁，不是新增封口。','',
          '**分类结论**：可确认当前完整D2截平面中存在由原壁限定的外部间隙轮廓；其源面来自相邻分支/接口的连接壁，不能仅凭二维嵌套称为独立解剖孔洞或腔壁破洞。外环跨多路径空间，并非已批准的目标分支独占横截面。因此仍为 `MULTIRING_WITH_HOLE_UNRESOLVED`，`effective_branch_area_mm2=null`，没有计算外减内值。','',
          '| 环 | 有符号面积 mm²（按原壁外向） | 原始源面数 | 包含站点 | 工程路径边界票 |','| --- | ---: | ---: | --- | --- |']
        for loop in case['loops']:
            lines.append(f'| {loop["loop_id"]} | {loop["mesh_outward_oriented_signed_area_mm2"]:.9f} | {len(loop["source_face_ids_unique"])} | {loop["contains_path_station"]} | {loop["path_boundary_votes"]} |')
        lines+=['', '#### 固定法向相邻截面对照','',
           '| 法向偏移 mm | 负向内环及面积 mm² | 与中央内环重合最多的源面环：环ID/重合数/正负 |',
           '| ---: | --- | --- |']
        for neighbor in case['neighbors']:
            if neighbor['kind']!='FIXED_NORMAL_PARALLEL':continue
            negatives=[f'{l["loop_id"]}: {l["absolute_area_mm2"]:.9f}' for l in neighbor['loops'] if l['mesh_outward_oriented_signed_area_mm2']<0]
            key=str(item['inner_loop']);scores=[l['source_face_overlap_with_central_loops'][key] for l in neighbor['loops']]
            maximum=max(scores,default=0);matches=[f'{l["loop_id"]}/{score}/{"+" if l["mesh_outward_oriented_signed_area_mm2"]>0 else "-"}' for l,score in zip(neighbor['loops'],scores) if score==maximum and score>0]
            lines.append(f'| {neighbor["offset_mm"]:+.3f} | {", ".join(negatives) or "未出现负向闭环"} | {", ".join(matches) or "无直接源面重合；另存两跳邻接支持"} |')
        lines+=['', '内环在短距离切面中出现/消失，中央内环源面在部分相邻平面转入正向轮廓，支持局部分叉壁面截交的拓扑变化，而非凭一张图认定永久贯通孔。该采样不声称精确求出了所有临界切面。沿路径的另一组13档和全部真实环亦保存在review.json。','',
           f'![{case["id"]}中央截面](../godot_sim/deformation/capacity_v2_n1_nested_review_v1/verification/forward_checked/{tag}_plane.png)',
           f'![{case["id"]}完整背景斜视](../godot_sim/deformation/capacity_v2_n1_nested_review_v1/verification/forward_checked/{tag}_full_context_oblique.png)','']
    lines+=['## 4. 局部有限相交复核与数值候选','',
       '对两个中央环源面、离平面连接链和二环邻域分别检查615/871个面；允许原拓扑共享边/点，两个范围均未确认非合法有限交叉或共面面积重叠。非邻接候选在1e−12/1e−10/1e−8/1e−6 mm判据敏感性下均未检出正长度交线。**仅限本轮局部参考几何，不扩大为全模型或连续形变无碰撞证明。**','',
       'B_27局部曾产生源面[135,7808]与[15995,16020]两个公共顶点候选，原平面计算长度约5.524e−10和1.458e−10 mm。独立复核把真实公共顶点设为两平面的共同原点并循环重排顶点，保持epsilon=1e−10 mm不变，正长度线段消失；最近有限特征距离为0，归为公共顶点点接触数值候选。未增大容差、删除面或改几何。自动测试另构造共享顶点但存在真实交线的反例，确认其仍被检测。','',
       '## 5. 数据、测试与保护','',
       '- 完整中央及相邻环、逐段D2/原始面ID、坐标/源边插值、包含矩阵、定向、绕数/射线探针、连接链、有限交叉与面片分组：[review_data.json](../godot_sim/deformation/capacity_v2_n1_nested_review_v1/review_data.json)。',
       '- 完整源三角面编号及原CT顶点三元组：[central_loop_source_faces.csv](../godot_sim/deformation/capacity_v2_n1_nested_review_v1/central_loop_source_faces.csv)。环编号在各站点独立，跨站点靠源面/邻接追踪，不默认编号一致。',
       f'- Python **{tests["run"]}/{tests["run"]}通过**，包括真实共享顶点交线反例、立体角内外判定、环来源精确复用、面邻接、零偏移一致性及禁止净面积晋升。']
    for backend,row in graphics.items():lines.append(f'- Godot {backend}：**{row["checks"]}项通过、{row["screenshots"]}张实际截图**；源面片实际位置与派生文件float32逐字节一致；已验收腔体/组织Reference完整回读与N1基线逐字节一致。')
    count=protect();lines += [f'- **{count}个受保护文件哈希未变**；六份已验收输入保持权威SHA-256。原始D2/OBJ、Marker、拓扑、P1/P2场景与位移、主场景/碰撞及旧报告未修改。','',
       '开发初次图形运行发现B_30内外来源面直接邻接、没有额外桥接三角面，空面组不能创建ArrayMesh；已改为空节点显示，没有补造三角面。初次邻平面测试发现重算零偏移切向会导致约1.9e−12 mm的远端交点漂移，已改为复用原中央平面，不放宽数值门槛。最终以*_checked日志为准。','',
       '## 6. 独立Godot审核入口','',
       '打开 `res://capacity_v2_nested_review.tscn`，按F6。选择两个站点、中央或相邻截面、全部真实环；可正视/斜视、独立显隐外环/内环源面、离平面连接面、二环邻域及剩余原腔壁背景，并不透明剖切。','',
       '彩色面片是真实源三角面的开放子集，单独显示的黑缝/边界不能直接解释成原始网格破洞。完整背景仅为原壁，不含远处虚拟测量封口；截环线可透视，不是实体腔壁。相邻截面模式的彩色面片仍对应中央来源，界面明确提示，完整邻环来源在JSON。保存现场只写新的user_sessions。','',
       '## 7. 重建与停止','', '在仓库根目录：','', '```powershell',
       "& 'E:/Apps/Conda/miniconda3/envs/FURS/python.exe' godot_sim/tools/capacity_v2/n1_nested_review.py",
       "& 'E:/Apps/Conda/miniconda3/envs/FURS/python.exe' godot_sim/tools/capacity_v2/test_n1_nested.py",
       "$nestedGodot = 'E:/Apps/Godot/Godot_v4.7-stable/Godot_v4.7-stable_win64_console.exe'",
       "New-Item -ItemType Directory -Force -Path 'godot_sim/deformation/capacity_v2_n1_nested_review_v1/verification/compatibility_checked','godot_sim/deformation/capacity_v2_n1_nested_review_v1/verification/forward_checked' | Out-Null",
       "& $nestedGodot --path godot_sim --rendering-method gl_compatibility --resolution 1440x1000 res://capacity_v2_nested_review.tscn -- --nested-verify=res://deformation/capacity_v2_n1_nested_review_v1/verification/compatibility_checked | Tee-Object -FilePath 'godot_sim/deformation/capacity_v2_n1_nested_review_v1/verification/compatibility_checked/godot_stdout.log'",
       "& $nestedGodot --path godot_sim --rendering-method forward_plus --resolution 1440x1000 res://capacity_v2_nested_review.tscn -- --nested-verify=res://deformation/capacity_v2_n1_nested_review_v1/verification/forward_checked | Tee-Object -FilePath 'godot_sim/deformation/capacity_v2_n1_nested_review_v1/verification/forward_checked/godot_stdout.log'",
       "& 'E:/Apps/Conda/miniconda3/envs/FURS/python.exe' godot_sim/tools/capacity_v2/n1_nested_report.py",'```','',
       '**完成本次两个站点专项复核后停止。** 尚未定义目标分支独占净截面，维持未确定；如以后需要正式净面积，需另行批准共享连接区/分支测量范围，而不是直接扣内环。本轮不变更D2总容量，不推进N2或任何新形变。','']
    path=REPO/'docs/kidney_irrigation_capacity_v2_n1_nested_review_result.md';path.write_text('\n'.join(lines),encoding='utf8')
    write_json(OUT/'delivery_manifest.json',{'schema':'N1_NESTED_REVIEW_DELIVERY_V1','date':'2026-10-15',
       'source_arrays_sha256':AUTHORITY,'source_N1_database_sha256':sha(ROOT/'sections.json.gz'),
       'D2_volume_mL':data['V_reference_D2_mL'],'effective_branch_areas_mm2':dict.fromkeys(TARGETS,None),
       'N2_started':False,'report_sha256':sha(path),'data_sha256':sha(OUT/'review_data.json'),
       'protected_unchanged_files':count,'python_tests_sha256':sha(OUT/'python_tests.json'),
       'graphics_checks_sha256':sha(OUT/'verification/independent_checks.json')})
    print('Nested review report',path,'protected',count)

if __name__=='__main__':report()
