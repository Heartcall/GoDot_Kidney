extends "res://scripts/capacity_v2_n0_preview.gd"
## Two-station diagnostic only. Does not alter D2 or accepted runtime geometry.
const REVIEW_ROOT := "res://deformation/capacity_v2_n1_nested_review_v1"
var review_data: Dictionary
var case_choice: OptionButton
var neighbor_choice: OptionButton
var loop_choice: OptionButton
var group_checks := {}
var ring_check: CheckBox
var details: Label
var current_case := {}
var current_plane := {}
var selected_loop_index := 0
var review_ready := false

func _ready() -> void:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(REVIEW_ROOT.path_join("review_data.json")))
	if not parsed is Dictionary or parsed.get("schema")!="N1_NESTED_RING_REVIEW_V1": push_error("Nested review missing"); get_tree().quit(1); return
	review_data = parsed
	player = Player.new(); world.add_child(player)
	if not player.ready_ok: return
	for key: String in ["outer_source_faces","inner_source_faces","off_plane_bridge","local_neighbor_faces","context","rings"]:
		var node := MeshInstance3D.new(); node.name = key; world.add_child(node); extras[key] = node
	_build_ui(); view.gui_input.connect(_view_input)
	resized.connect(func(): panel.custom_minimum_size.x = clampf(size.x*.31,340,440))
	panel.custom_minimum_size.x = clampf(size.x*.31,340,440)
	load_case(0); review_ready = true
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--nested-verify="):
			var runner = load("res://tools/capacity_v2/verify_n1_nested.gd").new()
			runner.viewer = self; runner.output = arg.trim_prefix("--nested-verify="); add_child(runner)

func _build_ui() -> void:
	var scroll := ScrollContainer.new(); scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED; panel.add_child(scroll)
	box = VBoxContainer.new(); box.size_flags_horizontal = Control.SIZE_EXPAND_FILL; box.add_theme_constant_override("separation",7); scroll.add_child(box)
	_label("N1 两个嵌套环专项复核\nReference 只读；非 N2 形变")
	_label("D2 = %.9f mL 保持不变\n有效分支净截面积：未确定\n候选区域容量未获最终解剖批准" % review_data["V_reference_D2_mL"])
	case_choice = OptionButton.new(); box.add_child(case_choice)
	for rec: Dictionary in review_data["cases"]: case_choice.add_item(str(rec["id"]))
	case_choice.item_selected.connect(load_case)
	status = _label("")
	_label("中央及相邻截面（色块始终是中央源面）")
	neighbor_choice = OptionButton.new(); neighbor_choice.fit_to_longest_item = false; box.add_child(neighbor_choice)
	neighbor_choice.item_selected.connect(choose_plane)
	loop_choice = OptionButton.new(); box.add_child(loop_choice); loop_choice.item_selected.connect(choose_loop)
	details = _label("")
	_button("正对当前截面",focus_plane)
	_button("当前截面斜视",oblique_view)
	_button("只看中央内环源面（不剖切）",inner_only)
	_button("恢复局部全部源面",restore_local)
	_label("蓝：中央外环源面；红：中央内环源面\n金：离开截平面后的连接面；灰：二环邻域\n彩色源面都是真实原腔壁；截环线可透视。\n独立面片是开放子集，其黑缝/边界不能\n直接解释成原始腔壁破洞。")
	for pair: Array in [["outer_source_faces","外环源面",true],["inner_source_faces","内环源面",true],["off_plane_bridge","离平面连接源面",true],["local_neighbor_faces","局部二环邻域",true],["context","其余腔壁背景",false]]:
		group_checks[pair[0]] = _check(pair[1],pair[2],func(_v): _visibility())
	ring_check = _check("显示全部真实截环",true,func(_v): draw_rings())
	section_check = _check("不透明剖切",true,func(_v): _apply_section())
	section_axis = OptionButton.new(); box.add_child(section_axis)
	for text: String in ["X","Y","Z","当前截面法向"]: section_axis.add_item(text)
	section_axis.select(3); section_axis.item_selected.connect(func(i):
		if i<3: section_normal = [Vector3.RIGHT,Vector3.UP,Vector3.BACK][i]
		_apply_section())
	section_slider = HSlider.new(); section_slider.min_value = -180; section_slider.max_value = 180; section_slider.step = .001; box.add_child(section_slider)
	section_slider.value_changed.connect(func(value): section_offset = value; _apply_section())
	_button("局部镜头复位",reset_camera)
	_button("保存专项复核现场",save_review)
	saved_info = _label("左键旋转／中键平移／滚轮缩放。\n两个内环的三维外部空域证据≠腔壁破洞。\n不作外减内，不推广为单支净截面。")

func load_case(index: int) -> void:
	case_choice.select(index); current_case = review_data["cases"][index]; extra_materials.clear()
	var colors := {"outer_source_faces":Color(.12,.6,.95),"inner_source_faces":Color(1,.2,.18),"off_plane_bridge":Color(1,.75,.1),"local_neighbor_faces":Color(.52,.58,.64),"context":Color(.24,.29,.34)}
	for key: String in colors:
		var rec: Dictionary = current_case["mesh_groups"][key]
		if rec["D2_faces"]==0:
			extras[key].mesh = null; continue
		_load_mesh(extras[key],REVIEW_ROOT.path_join(rec["file"]),rec["sha256"],colors[key])
	status.text = "%s · 弧长 %.9f mm\nMULTIRING_WITH_HOLE_UNRESOLVED\n局部有限相交异常：%d\n负向内环围合的是 D2 外部间隙；\n外环跨多路径，单支净面积未定义。" % [current_case["id"],current_case["station_arc_mm"],current_case["local_finite_contacts"]["confirmed_invalid_pairs"].size()]
	neighbor_choice.clear(); neighbor_choice.add_item("中央原始站点（精确数据）")
	for rec: Dictionary in current_case["neighbors"]: neighbor_choice.add_item(str(rec["kind"])+" Δ="+str(rec["offset_mm"])+" mm")
	choose_plane(0); restore_local(); focus_plane()

func choose_plane(index: int) -> void:
	neighbor_choice.select(index)
	current_plane = current_case if index==0 else current_case["neighbors"][index-1]
	loop_choice.clear()
	for rec: Dictionary in current_plane["loops"]:
		loop_choice.add_item("环 %d · %.6f mm² · %s" % [rec["loop_id"],rec["absolute_area_mm2"],rec["orientation_relative_plane_normal"]])
	selected_loop_index = int(current_case["nesting"][0]["inner_loop"]) if index==0 else 0
	choose_loop(selected_loop_index)
	var station: Dictionary = current_case if index==0 else current_plane["station"]
	section_normal = _vec(station["plane_normal_unit"]); section_offset = (_vec(station["position_mm"])-ORIGIN).dot(section_normal)+.02
	section_slider.set_value_no_signal(section_offset); _apply_section()

func choose_loop(index: int) -> void:
	if current_plane["loops"].is_empty(): details.text = "无真实闭环"; return
	loop_choice.select(index); selected_loop_index = index
	var rec: Dictionary = current_plane["loops"][index]
	var ids: Array = rec["source_face_ids_unique"]; var excerpt: Array = ids.slice(0,24)
	details.text = "环 %d：面积 %.9f mm²\n原网格定向有符号面积 %.9f mm²\n源三角面 %d 个（0-based）：\n%s%s\n路径边界票：%s\n平面外残差 %.9f mm\n完整编号见 review.json，不代表解剖标签。" % [rec["loop_id"],rec["absolute_area_mm2"],rec["mesh_outward_oriented_signed_area_mm2"],ids.size(),str(excerpt)," …" if ids.size()>24 else "",str(rec["path_boundary_votes"]),rec["plane_max_residual_mm"]]
	draw_rings()

func draw_rings() -> void:
	var p := PackedVector3Array(); var c := PackedColorArray()
	for rec: Dictionary in current_plane["loops"]:
		var pts: Array = rec["ring_positions_mm"]; var color := Color(.6,.65,.7)
		if rec["loop_id"]==selected_loop_index: color = Color(1,.15,.08)
		elif rec["mesh_outward_oriented_signed_area_mm2"]>0: color = Color(1,.8,.2)
		for i in pts.size(): _line(p,c,_vec(pts[i])-ORIGIN,_vec(pts[(i+1)%pts.size()])-ORIGIN,color)
	_set_lines(extras["rings"],p,c,true); extras["rings"].visible = ring_check.button_pressed

func _visibility() -> void:
	player.set_mesh_visible("cavity",false); player.set_mesh_visible("tissue",false)
	for key: String in group_checks: extras[key].visible = group_checks[key].button_pressed

func focus_plane() -> void:
	var station: Dictionary = current_case if neighbor_choice.selected==0 else current_plane["station"]
	var point := _vec(station["position_mm"]); var radius := 4.0
	var outer: Dictionary = current_case["loops"][int(current_case["nesting"][0]["outer_loop"]) ]
	for value: Array in outer["ring_positions_mm"]: radius = maxf(radius,point.distance_to(_vec(value)))
	focus_point(point-ORIGIN,_vec(station["plane_normal_unit"]),radius*3.3)

func oblique_view() -> void:
	focus_plane(); yaw += .6; pitch = clampf(pitch+.25,-1.4,1.4); _update_camera()

func inner_only() -> void:
	for key: String in group_checks: group_checks[key].button_pressed = key=="inner_source_faces"
	_visibility(); section_check.button_pressed = false; _apply_section()
	var inner: Dictionary = current_case["loops"][int(current_case["nesting"][0]["inner_loop"])]
	var low := _vec(inner["bounds_mm"][0]); var high := _vec(inner["bounds_mm"][1]); center = (low+high)*.5-ORIGIN; distance = 6; _update_camera()

func restore_local() -> void:
	for key: String in group_checks: group_checks[key].button_pressed = key!="context"
	_visibility()

func reset_camera() -> void: focus_plane()

func review_state() -> Dictionary:
	return {"case":current_case.get("id"),"plane":neighbor_choice.get_item_text(neighbor_choice.selected),"loop":selected_loop_index,
		"camera_display_mm":[camera.position.x,camera.position.y,camera.position.z],"yaw":yaw,"pitch":pitch,"distance_mm":distance,
		"section_normal":[section_normal.x,section_normal.y,section_normal.z],"section_offset_display_mm":section_offset,
		"section_enabled":section_check.button_pressed,"effective_branch_area_mm2":null,"D2_volume_changed":false}

func save_review() -> void:
	await RenderingServer.frame_post_draw
	var directory := REVIEW_ROOT.path_join("user_sessions"); DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(directory)); var base := directory.path_join("review_"+str(Time.get_ticks_msec()))
	var file := FileAccess.open(base+".json",FileAccess.WRITE); file.store_string(JSON.stringify(review_state(),"\t")); file.close()
	get_viewport().get_texture().get_image().save_png(ProjectSettings.globalize_path(base+".png")); saved_info.text = "已保存 "+base
