extends "res://scripts/irrigation_geometry_audit_preview.gd"

const RESEARCH_DIR := "res://analysis/irrigation_baseline/p15_contact_research"
var _group_choice: OptionButton
var _group_info: Label
var _group_edges: MeshInstance3D

func _ready() -> void:
	_mesh_node = get_node("MaskMesh") as MeshInstance3D
	_tissue_node = get_node("TissueMesh") as MeshInstance3D
	_lines = get_node("Centerlines") as MeshInstance3D
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(RESEARCH_DIR.path_join("audit_preview.json")))
	if not parsed is Dictionary:
		_fail("请先运行 audit_tissue_cavity.py。")
		return
	_meta = parsed
	for record: Dictionary in _meta["sources"].values():
		if FileAccess.get_sha256("res://" + str(record["path"])) != str(record["sha256"]):
			_fail("参考 OBJ 已改变，请重新审计。")
			return
	var origin := _vec(_meta["preview_origin_mm"])
	for path: Dictionary in _meta["paths"]:
		var points := []
		for point in path["points_mm"]:
			var p := _vec(point) - origin
			points.append([p.x, p.y, p.z])
		path["points_mm"] = points
	for name in _meta["landmarks"]:
		var p := _vec(_meta["landmarks"][name]) - origin
		_meta["landmarks"][name] = [p.x, p.y, p.z]
	for i in 2:
		var p := _vec(_meta["bounds_mm"][i]) - origin
		_meta["bounds_mm"][i] = [p.x, p.y, p.z]
	_cavity_data = _read_reference("cavity")
	_tissue_data = _read_reference("tissue")
	if _cavity_data.is_empty() or _tissue_data.is_empty():
		return
	_build_reference(_mesh_node, _cavity_data, Color(0.15, 0.65, 0.95))
	_build_reference(_tissue_node, _tissue_data, Color(0.85, 0.48, 0.48))
	_create_audit_ui()
	_focus("ALL")
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--research-validation-dir="):
			call_deferred("_capture_research", arg.trim_prefix("--research-validation-dir="))


func _read_reference(name: String) -> Dictionary:
	var path := RESEARCH_DIR.path_join(name + "_reference.bin")
	if FileAccess.get_sha256(path) != str(_meta["binary_sha256"][name]):
		_fail("审计参考数据哈希不匹配。")
		return {}
	var file := FileAccess.open(path, FileAccess.READ)
	var magic := file.get_buffer(8).get_string_from_ascii()
	var n := int(file.get_32())
	var m := int(file.get_32())
	if magic != "KAUD0001" or file.get_length() != 16 + 28 * n + 12 * m:
		_fail("审计参考数据格式无效。")
		return {}
	var result := {"vertices":_read_vectors(file, n), "normals":_read_vectors(file, n),
		"flags":file.get_buffer(n * 4).to_float32_array(), "indices":file.get_buffer(m * 12).to_int32_array()}
	file.close()
	_audit_counts[name] = {"vertices":n, "triangles":m}
	return result


func _build_reference(node: MeshInstance3D, data: Dictionary, color: Color) -> void:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = data["vertices"]
	arrays[Mesh.ARRAY_NORMAL] = data["normals"]
	arrays[Mesh.ARRAY_INDEX] = data["indices"]
	var colors := PackedColorArray()
	for flag in data["flags"]:
		colors.append([color, Color(1.0,0.12,0.04),Color(1.0,0.8,0.05),Color(0.95,0.1,0.85)][int(flag)])
	arrays[Mesh.ARRAY_COLOR] = colors
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	node.mesh = mesh
	var material := ShaderMaterial.new()
	material.shader = SECTION_SHADER
	node.material_override = material
	_section_materials.append(material)
	_update_section()

func _create_audit_ui() -> void:
	super._create_audit_ui()
	var canvas := CanvasLayer.new()
	add_child(canvas)
	var panel := PanelContainer.new()
	panel.position = Vector2(880,16)
	canvas.add_child(panel)
	var column := VBoxContainer.new()
	panel.add_child(column)
	_group_choice = OptionButton.new()
	_group_choice.add_item("选择原始候选组／失败位置")
	for group: Dictionary in _meta["groups"]:
		_group_choice.add_item(str(group["id"]) + " · " + str(group["pair_count"]) + " 对")
	_group_choice.item_selected.connect(_select_group)
	column.add_child(_group_choice)
	_group_info = Label.new()
	_group_info.add_theme_font_size_override("font_size",14)
	_group_info.custom_minimum_size = Vector2(350,0)
	_group_info.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(_group_info)
	_group_edges = MeshInstance3D.new()
	add_child(_group_edges)
	var button := Button.new()
	button.text = "同组完整表面／剖切"
	button.pressed.connect(_swap_cut)
	column.add_child(button)

func _swap_cut() -> void:
	_toggle_section(not _section_enabled)
	_section_toggle.set_pressed_no_signal(_section_enabled)

func _select_group(index: int) -> void:
	if index == 0:
		_focus("ALL")
		return
	_focus_group(_meta["groups"][index-1])

func _focus_group(group: Dictionary) -> void:
	_center = _vec(group["center_mm"]) - _vec(_meta["preview_origin_mm"])
	var normal := _vec(group["view_normal"]).normalized()
	if normal.length() < 0.9:
		normal = Vector3(0.3,0.4,0.85).normalized()
	_yaw = atan2(normal.x,normal.z)
	_pitch = asin(clampf(normal.y,-0.95,0.95))
	_distance = clampf(_vec(group["extent_mm"]).length()*2.5,8.0,65.0)
	_focus_name = str(group["id"])
	_section_enabled = true
	_section_normal = normal
	_section_offset = _center.dot(normal)+0.2
	_section_toggle.set_pressed_no_signal(true)
	_group_info.text = "%s · %s 对\n中心 (%.2f, %.2f, %.2f) mm\n路径 %s\n独立交线数 %s\n线框=原始配对的精确三角面\n候选颜色不等于缺陷结论" % [group["id"],group["pair_count"],group["center_mm"][0],group["center_mm"][1],group["center_mm"][2],str(group["nearest_path_vertex_votes"].keys()),group["independent_positive_segments"]]
	if str(group["id"]).begins_with("F"):
		_group_info.text += "\n试验检查位置；仍显示原始参考态\n" + str(group.get("reason_cn","需人工检查"))
	_group_edges.visible = true
	var mesh := ImmediateMesh.new()
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.no_depth_test = true
	material.vertex_color_use_as_albedo = true
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	mesh.surface_begin(Mesh.PRIMITIVE_LINES,material)
	for pair in group["pairs"]:
		for side in 2:
			var data := _tissue_data if str(group["id"]).begins_with("S") or str(group["id"]).begins_with("F") or side==1 else _cavity_data
			var face := int(pair[side])
			for edge in [[0,1],[1,2],[2,0]]:
				mesh.surface_set_color(Color(1,0.25,0.05) if side==0 else Color(0.1,1,0.75))
				mesh.surface_add_vertex(data["vertices"][data["indices"][face*3+int(edge[0])]])
				mesh.surface_add_vertex(data["vertices"][data["indices"][face*3+int(edge[1])]])
	mesh.surface_end()
	_group_edges.mesh = mesh
	_update_camera()
	_update_section()

func _update_label() -> void:
	if _label == null:
		return
	_label.text = "P1.5 接触研究 · 原始参考态 · %s\n红=C 旧穿越候选，复核为点接触\n黄=P 近共面；紫=S 旧自交候选，复核相离\n仅空间诊断，不认定接触错误或允许贴合\n未交付正式组织位移／联合三态\n剖切 %.2f mm（无封口，不测壁厚）\n左键旋转 · 中键平移 · 滚轮缩放 · R 全局" % [_focus_name,_section_offset]

func _focus(name: String) -> void:
	super._focus(name)
	if _group_edges != null:
		_group_edges.visible = false

func _capture_research(directory: String) -> void:
	_focus("ALL")
	_section_enabled = false
	_update_section()
	await _write_screenshot(directory.path_join("original_joint.png"))
	for i in _meta["groups"].size():
		var group: Dictionary = _meta["groups"][i]
		_group_choice.select(i+1)
		_focus_group(group)
		if not await _write_screenshot(directory.path_join(str(group["id"])+"_section.png")):
			return
		if int(group["pair_count"])>=4 or str(group["id"]).begins_with("F"):
			_toggle_section(false)
			await _write_screenshot(directory.path_join(str(group["id"])+"_surface.png"))
	var matched := true
	for entry in [[_mesh_node,_cavity_data],[_tissue_node,_tissue_data]]:
		var arrays: Array = (entry[0].mesh as ArrayMesh).surface_get_arrays(0)
		matched = matched and arrays[Mesh.ARRAY_VERTEX]==entry[1]["vertices"] and arrays[Mesh.ARRAY_INDEX]==entry[1]["indices"]
	var file := FileAccess.open(directory.path_join("runtime_research.json"),FileAccess.WRITE)
	file.store_string(JSON.stringify({"geometry_arrays_match":matched,"reference_only":true,"opaque_shader":true,"groups":_meta["groups"].size(),"counts":_audit_counts},"  "))
	file.close()
	get_tree().quit(0 if matched else 1)
