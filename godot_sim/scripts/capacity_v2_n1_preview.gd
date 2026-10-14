extends "res://scripts/capacity_v2_n0_preview.gd"
## Reference-only analysis. Measurement caps never enter accepted runtime meshes.
const N1_ROOT := "res://deformation/capacity_v2_n1_v1"
var analysis: Dictionary
var path_choice: OptionButton
var station_choice: OptionButton
var node_choice: OptionButton
var region_check: CheckBox
var centers_check: CheckBox
var loops_check: CheckBox
var local_info: Label
var contribution: Label
var selected_stations: Array = []
var current_station := {}
var n1_ready := false
var raw_mesh_arrays := {}
var focused_node_name := ""

func _load_mesh(node: MeshInstance3D, path: String, digest: String, color: Color) -> void:
	if FileAccess.get_sha256(path)!=digest: push_error("N1 frozen mesh hash mismatch"); get_tree().quit(1); return
	var file := FileAccess.open(path,FileAccess.READ); var magic := file.get_buffer(8).get_string_from_ascii(); var n := int(file.get_32()); var m := int(file.get_32())
	if magic!="N0MS0001" or file.get_length()!=16+24*n+12*m: push_error("Invalid frozen D2 mesh"); get_tree().quit(1); return
	var arrays := []; arrays.resize(Mesh.ARRAY_MAX); arrays[Mesh.ARRAY_VERTEX] = _read_vectors(file,n); arrays[Mesh.ARRAY_NORMAL] = _read_vectors(file,n)
	arrays[Mesh.ARRAY_INDEX] = file.get_buffer(m*12).to_int32_array(); file.close()
	var colors := PackedColorArray(); colors.resize(n); colors.fill(color); arrays[Mesh.ARRAY_COLOR] = colors
	# Retain original float32 normals: debug color changes must not repeatedly encode decoded normals.
	raw_mesh_arrays[node.name] = arrays.duplicate(true)
	var mesh := ArrayMesh.new(); mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays); node.mesh = mesh
	var material := ShaderMaterial.new(); material.shader = SECTION_SHADER; node.material_override = material; extra_materials.append(material)

func _ready() -> void:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(N1_ROOT.path_join("review_preview.json")))
	if not parsed is Dictionary or parsed.get("schema") != "CAPACITY_V2_N1_REVIEW_V1":
		push_error("N1 data missing"); get_tree().quit(1); return
	analysis = parsed
	if FileAccess.get_sha256(N1_ROOT.path_join("D2_approval_2026_10_14_v1.json")) != analysis["approval_sha256"]:
		push_error("D2 approval hash changed"); get_tree().quit(1); return
	player = Player.new(); world.add_child(player)
	if not player.ready_ok: return
	for key: String in ["wall","caps","section_lines","centers","node_lines"]:
		var node := MeshInstance3D.new(); node.name = key; world.add_child(node); extras[key] = node
	for entry: Array in [["wall","original_wall.bin",Color(.16,.60,.88)],["caps","virtual_caps.bin",Color(1,.72,.05)]]:
		_load_mesh(extras[entry[0]],N1_ROOT.path_join("d2").path_join(entry[1]),analysis["mesh_sha256"][entry[1]],entry[2])
	_build_ui(); view.gui_input.connect(_view_input)
	resized.connect(func(): panel.custom_minimum_size.x = clampf(size.x*.29,320,420))
	panel.custom_minimum_size.x = clampf(size.x*.29,320,420)
	choose_path(0); _apply_section(); reset_camera(); _visibility(); n1_ready = true
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--n1-verify="):
			var runner = load("res://tools/capacity_v2/verify_n1.gd").new()
			runner.viewer = self; runner.output = arg.trim_prefix("--n1-verify="); add_child(runner)

func _build_ui() -> void:
	var scroll := ScrollContainer.new(); scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED; panel.add_child(scroll)
	box = VBoxContainer.new(); box.size_flags_horizontal = Control.SIZE_EXPAND_FILL; box.add_theme_constant_override("separation",7); scroll.add_child(box)
	_label("Capacity V2 · N1 Reference 审核\nD2 项目测量域已批准；局部分区待审")
	status = _label("D2 Reference = %.9f mL\n工程范围定义，不是生理容量端点\n本场景无新版形变；s = 0" % analysis["V_reference_D2_mL"])
	_label("选择路径 → 选择实际截面站点")
	path_choice = OptionButton.new(); path_choice.fit_to_longest_item = false; box.add_child(path_choice)
	for rec: Dictionary in analysis["paths"]: path_choice.add_item(str(rec["id"]))
	path_choice.item_selected.connect(choose_path)
	station_choice = OptionButton.new(); station_choice.fit_to_longest_item = false; box.add_child(station_choice); station_choice.item_selected.connect(choose_station)
	_button("正对当前截面定位（自动剖切）",focus_station)
	local_info = _label(""); contribution = _label("")
	_label("J／T 拓扑节点与邻近站点")
	node_choice = OptionButton.new(); box.add_child(node_choice)
	for rec: Dictionary in analysis["nodes"]: node_choice.add_item(str(rec["id"]))
	node_choice.item_selected.connect(focus_node)
	_label("金：所选截环；灰：拓扑相关其他环\n红：归属不确定环；白：已确认中心线\n诊断线可透视，不代表实体腔壁。\n完整精确截环／源映射见 sections.json.gz。\n其他环显示线简化；测量仍用完整数据。")
	cavity_check = _check("显示 D2 源腔壁",true,func(_v): _visibility())
	tissue_check = _check("显示已验收 Reference 组织（不透明）",false,func(_v): _visibility())
	cap_check = _check("显示 D2 虚拟封口（金，独立测量节点）",true,func(_v): _visibility())
	loops_check = _check("显示截环（含其他环，供归属核对）",true,func(_v): _draw_station())
	centers_check = _check("显示中心线与节点",true,func(_v): _visibility())
	region_check = _check("表面几何分类着色（不是精确容量分界）",false,func(_v): color_regions())
	_label("容量候选：0.5 mm 内部立方单元无重叠；\n边界补集保持未归属，不归一化分配。\nJ 半径 2.5 mm／T 半径 2 mm 是待审工程划分。")
	section_check = _check("不透明剖切",false,func(_v): _apply_section())
	section_axis = OptionButton.new(); box.add_child(section_axis)
	for text: String in ["X","Y","Z","截面法向"]: section_axis.add_item(text)
	section_axis.item_selected.connect(func(i):
		if i<3: section_normal = [Vector3.RIGHT,Vector3.UP,Vector3.BACK][i]
		_apply_section())
	section_slider = HSlider.new(); section_slider.min_value = -180; section_slider.max_value = 180; section_slider.step = .01; box.add_child(section_slider)
	section_slider.value_changed.connect(func(value): section_offset = value; _apply_section())
	_button("全模型镜头复位",reset_camera)
	_button("保存 N1 审核现场与截图",save_review)
	saved_info = _label("左键旋转／中键平移／滚轮缩放；R 复位。\n组织、源壁、虚拟封口可独立显隐。\n区域容量候选待人工审核，V_min/V_max 未设置。")

func choose_path(index: int) -> void:
	focused_node_name = ""
	var id: String = str(analysis["paths"][index]["id"]); path_choice.select(index)
	selected_stations.clear(); station_choice.clear()
	for rec: Dictionary in analysis["stations"]:
		if rec["path_id"]==id:
			selected_stations.append(rec); station_choice.add_item("%.3f mm · %s" % [rec["station_arc_mm"],rec["status"]])
	if not selected_stations.is_empty():
		var mid := int(selected_stations.size()/2); station_choice.select(mid); choose_station(mid)
	_draw_centers()
	contribution.text = "候选容量（非正式解剖分支容量）：\n"
	for rec: Dictionary in analysis["capacity"]["regions"]:
		if rec["id"]==id: contribution.text += "%s: %.6f mL / %.2f%% D2\n" % [id,rec["candidate_volume_mL"],rec["fraction_D2"]*100]
	contribution.text += "边界未归属：%.6f mL\n总账残差 %.9f mm³；分区不确定性见报告" % [analysis["capacity"]["boundary_remainder_mL"],analysis["capacity"]["residual_mm3"]]

func choose_station(index: int) -> void:
	current_station = selected_stations[index]; station_choice.select(index)
	local_info.text = "%s\n站点 %.3f mm；%s\n" % [current_station["path_id"],current_station["station_arc_mm"],current_station["status"]]
	if current_station["metrics"] is Dictionary:
		var m: Dictionary = current_station["metrics"]
		local_info.text += "面积 %.4f mm²；周长 %.4f mm\n等效半径 %.4f mm\n惯性等效长／短轴 %.4f / %.4f mm\n扁率 %.4f\n" % [m["area_mm2"],m["perimeter_mm"],m["equivalent_radius_mm"],m["major_axis_mm"],m["minor_axis_mm"],m["flattening_1_minus_minor_major"]]
	else: local_info.text += "未确认有效局部截面，不填零、不选最大环。\n"
	local_info.text += "同平面闭环数：%d；显示相关环 %d\n%s\n路径编号不等于解剖分类" % [current_station["all_plane_loop_count"],current_station["loops"].size(),current_station["geometric_class"]]
	_draw_station()

func _draw_station() -> void:
	if current_station.is_empty(): return
	var p := PackedVector3Array(); var c := PackedColorArray()
	for i in current_station["loops"].size():
		var ring: Array = current_station["loops"][i]["ring_positions_mm"]
		var color := Color(.45,.48,.52)
		if current_station["selected_loop"]==i: color = Color(1,.78,.08) if current_station["metrics"] is Dictionary else Color(1,.15,.1)
		for k in ring.size(): _line(p,c,_vec(ring[k])-ORIGIN,_vec(ring[(k+1)%ring.size()])-ORIGIN,color)
	_set_lines(extras["section_lines"],p,c,true)
	if is_instance_valid(loops_check): extras["section_lines"].visible = loops_check.button_pressed

func _draw_centers() -> void:
	var resolved: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://deformation/cavity_topology_resolved.json"))
	var p := PackedVector3Array(); var c := PackedColorArray()
	var selected := path_choice.get_item_text(path_choice.selected)
	for rec: Dictionary in resolved["paths"]:
		if rec["id"] in ["BLADDER","IN_01","IN_02"]: continue
		var pts: Array = rec["points_mm"]; var color := Color(1,1,1) if rec["id"]==selected else Color(.45,.55,.62)
		for i in pts.size()-1: _line(p,c,_vec(pts[i])-ORIGIN,_vec(pts[i+1])-ORIGIN,color)
	_set_lines(extras["centers"],p,c,true)

func focus_station() -> void:
	focused_node_name = ""
	var radius := 4.0; var station_center := _vec(current_station["position_mm"])
	if current_station["selected_loop"]!=null:
		for value: Array in current_station["loops"][int(current_station["selected_loop"])]["ring_positions_mm"]:
			radius = maxf(radius,station_center.distance_to(_vec(value)))
	focus_point(station_center-ORIGIN,_vec(current_station["plane_normal_unit"]),maxf(16,radius*3.2))

func focus_node(index: int) -> void:
	var node: Dictionary = analysis["nodes"][index]; var point := _vec(node["position_mm"])-ORIGIN
	focused_node_name = str(node["id"])
	var p := PackedVector3Array(); var c := PackedColorArray()
	for axis: Vector3 in [Vector3.RIGHT,Vector3.UP,Vector3.BACK]: _line(p,c,point-axis*.7,point+axis*.7,Color(1,.2,.3))
	_set_lines(extras["node_lines"],p,c,true); focus_point(point,Vector3.BACK,24)
	local_info.text = "%s · %s\n相连路径 %s\n邻近站点 %d 个，见数据库\n连接球／末端区为候选工程分类" % [node["id"],node["status"],str(node["incident_paths"]),node["probe_station_ids"].size()]
	for rec: Dictionary in analysis["capacity"]["regions"]:
		if rec["id"]==node["id"]: contribution.text = "候选 %s: %.6f mL / %.2f%% D2\n不是独立临床肾盏容量" % [node["id"],rec["candidate_volume_mL"],rec["fraction_D2"]*100]

func color_regions() -> void:
	var arrays: Array = raw_mesh_arrays["wall"].duplicate(true)
	var colors := PackedColorArray(); colors.resize(analysis["wall_vertex_region_ids"].size())
	for i in colors.size():
		var rgb: Array = analysis["region_colors"][int(analysis["wall_vertex_region_ids"][i])]
		colors[i] = Color(rgb[0],rgb[1],rgb[2]) if region_check.button_pressed else Color(.16,.60,.88)
	arrays[Mesh.ARRAY_COLOR] = colors
	var mesh := ArrayMesh.new(); mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays); extras["wall"].mesh = mesh

func _visibility() -> void:
	if not is_instance_valid(cavity_check): return
	player.set_mesh_visible("cavity",false); player.set_mesh_visible("tissue",tissue_check.button_pressed)
	extras["wall"].visible = cavity_check.button_pressed; extras["caps"].visible = cap_check.button_pressed
	extras["centers"].visible = centers_check.button_pressed

func reset_camera() -> void:
	var low := _vec(analysis["used_bounds_mm"][0])-ORIGIN; var high := _vec(analysis["used_bounds_mm"][1])-ORIGIN
	center = (low+high)*.5; var extent := high-low; distance = maxf(extent.x,maxf(extent.y,extent.z))*1.9; yaw = .6; pitch = .45; _update_camera()

func review_state() -> Dictionary:
	return {"schema":"N1_REVIEW_SESSION_V1","domain":"C11_R1_IN02_fixed_collar","s":0,"station_id":current_station.get("id"),
		"focused_node":focused_node_name,
		"camera_position_display_mm":[camera.position.x,camera.position.y,camera.position.z],"yaw":yaw,"pitch":pitch,"distance_mm":distance,
		"section_enabled":section_check.button_pressed,"section_normal":[section_normal.x,section_normal.y,section_normal.z],"section_offset_display_mm":section_offset,
		"D2_approved":true,"region_partition_approved":false,"V_min":null,"V_max":null,"approval_sha256":analysis["approval_sha256"]}

func save_review() -> void:
	await RenderingServer.frame_post_draw
	var directory := N1_ROOT.path_join("user_sessions"); DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(directory))
	var base := directory.path_join("review_"+str(Time.get_ticks_msec()))
	var file := FileAccess.open(base+".json",FileAccess.WRITE); file.store_string(JSON.stringify(review_state(),"\t")); file.close()
	get_viewport().get_texture().get_image().save_png(ProjectSettings.globalize_path(base+".png")); saved_info.text = "已保存 "+base
