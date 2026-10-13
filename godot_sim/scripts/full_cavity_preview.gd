@tool
extends "res://scripts/cavity_morph_preview.gd"

const FULL_DIR := "res://deformation/full_cavity/morph"

func _ready() -> void:
	display_mode = 0
	_load_morph()
	if not Engine.is_editor_hint():
		_create_ui()
		for arg in OS.get_cmdline_user_args():
			if arg.begins_with("--full-validation-dir="):
				call_deferred("_capture_full_validation", arg.trim_prefix("--full-validation-dir="))

func _load_morph() -> void:
	_mesh_node = get_node("MaskMesh") as MeshInstance3D
	_lines = get_node("Centerlines") as MeshInstance3D
	_wire = get_node("ReferenceWire") as MeshInstance3D
	_vectors = get_node("VectorGlyphs") as MeshInstance3D
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(FULL_DIR.path_join("morph_preview.json")))
	if not parsed is Dictionary:
		_fail("请先运行 build_full_cavity_deformation.py。")
		return
	_meta = parsed
	for record: Dictionary in [_meta["source_mesh"], _meta["approved_weight_source"]] + _meta["sources"].values():
		if FileAccess.get_sha256("res://" + str(record["path"])) != str(record["sha256"]):
			_fail("三态来源已改变，请基于认可的数据重新构建全天然形变。")
			return
	var binary_path := FULL_DIR.path_join(str(_meta["binary_file"]))
	if FileAccess.get_sha256(binary_path) != str(_meta["binary_sha256"]):
		_fail("三态预览数据哈希不匹配。")
		return
	var file := FileAccess.open(binary_path, FileAccess.READ)
	if file == null:
		_fail("无法打开三态预览数据。")
		return
	var magic := file.get_buffer(8).get_string_from_ascii()
	var n := int(file.get_32())
	var m := int(file.get_32())
	if magic != "KMOR0001" or n != int(_meta["vertex_count"]) or m != int(_meta["triangle_count"]) or file.get_length() != 16 + n * 60 + m * 12:
		_fail("三态预览格式无效。")
		return
	_reference = _read_vectors(file, n)
	_accepted_displacement = _read_vectors(file, n)
	_state_normals = [_read_vectors(file, n), _read_vectors(file, n), _read_vectors(file, n)]
	_normals = _state_normals[0]
	_indices = file.get_buffer(m * 12).to_int32_array()
	file.close()
	# These indices are exported directly from the approved fixed masks.
	var fixed_data: Variant = JSON.parse_string(FileAccess.get_file_as_string(FULL_DIR.path_join("fixed_vertex_indices.json")))
	if not fixed_data is Array or fixed_data.size() != int(_meta["fixed_vertices"]):
		_fail("固定顶点编号无效。")
		return
	if FileAccess.get_sha256(FULL_DIR.path_join("fixed_vertex_indices.json")) != str(_meta["fixed_indices_sha256"]):
		_fail("固定顶点编号哈希不匹配。")
		return
	for index in fixed_data:
		_fixed_indices.append(int(index))
	# Display uses a translated coordinate frame for float32 precision. All
	# exported state arrays remain in the original cavity mesh coordinates.
	var origin := _vec(_meta["preview_origin_mm"])
	for path: Dictionary in _meta["paths"]:
		var centered := []
		for point in path["points_mm"]:
			var p := _vec(point) - origin
			centered.append([p.x, p.y, p.z])
		path["points_mm"] = centered
	for name in _meta["landmarks"]:
		var p := _vec(_meta["landmarks"][name]) - origin
		_meta["landmarks"][name] = [p.x, p.y, p.z]
	for k in 2:
		var p := _vec(_meta["bounds_mm"][k]) - origin
		_meta["bounds_mm"][k] = [p.x, p.y, p.z]
	var material := StandardMaterial3D.new()
	material.vertex_color_use_as_albedo = true
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.roughness = 1.0
	_mesh_node.material_override = material
	_build_centerlines()
	_focus("ALL")
	_apply_colors()
	print("FullCavityPreview: all natural branches; exact approved masks; same-topology morphs.")


func _create_ui() -> void:
	var canvas := CanvasLayer.new()
	add_child(canvas)
	var panel := PanelContainer.new()
	panel.position = Vector2(16, 16)
	canvas.add_child(panel)
	var column := VBoxContainer.new()
	panel.add_child(column)
	_label = Label.new()
	_label.add_theme_font_size_override("font_size", 16)
	column.add_child(_label)
	var states := HBoxContainer.new()
	column.add_child(states)
	for i in 3:
		var button := Button.new()
		button.text = ["1 Reference", "2 Mid", "3 Expanded"][i]
		button.pressed.connect(_set_fill.bind([0.0, 0.5, 1.0][i]))
		states.add_child(button)
		_state_buttons.append(button)
	_state_label = Label.new()
	column.add_child(_state_label)
	_slider = HSlider.new()
	_slider.min_value = 0.0
	_slider.max_value = 1.0
	_slider.step = 0.001
	_slider.custom_minimum_size = Vector2(385, 28)
	_slider.value = filling
	_slider.value_changed.connect(_set_fill)
	column.add_child(_slider)
	var modes := HBoxContainer.new()
	column.add_child(modes)
	for entry in [["4 大小", 0], ["5 方向", 1], ["6 参考线", 2], ["7 表面", 4]]:
		var button := Button.new()
		button.text = str(entry[0])
		button.pressed.connect(_choose_mode.bind(int(entry[1])))
		modes.add_child(button)
	var focus_row := HBoxContainer.new()
	column.add_child(focus_row)
	for name in ["ALL", "MAIN", "B_31", "B_32", "BLADDER_TRANSITION"]:
		var button := Button.new()
		button.text = {"ALL":"全模型", "MAIN":"主腔室", "B_31":"IN_01", "B_32":"IN_02", "BLADDER_TRANSITION":"膀胱"}[name]
		button.pressed.connect(_focus.bind(str(name)))
		focus_row.add_child(button)
	for group in [["J_", 9, "分叉"], ["T_", 22, "末端"], ["B_", 30, "天然分支"]]:
		var row := HBoxContainer.new()
		column.add_child(row)
		var label := Label.new()
		label.text = str(group[2])
		row.add_child(label)
		var choice := OptionButton.new()
		choice.custom_minimum_size.x = 100
		for i in range(1, int(group[1]) + 1):
			choice.add_item("%s%02d" % [group[0], i])
		choice.item_selected.connect(_focus_choice.bind(choice))
		row.add_child(choice)
		var go := Button.new()
		go.text = "定位"
		go.pressed.connect(_go_focus_choice.bind(choice))
		row.add_child(go)
	var toggle := CheckButton.new()
	toggle.text = "显示天然路径与接口过渡中心线"
	toggle.toggled.connect(_toggle_lines)
	column.add_child(toggle)
	_update_label()


func _focus_choice(index: int, choice: OptionButton) -> void:
	_focus(choice.get_item_text(index))


func _go_focus_choice(choice: OptionButton) -> void:
	_focus_choice(choice.selected, choice)


func _focus(name: String) -> void:
	super._focus(name)
	if _meta.has("focus_camera") and _meta["focus_camera"].has(name):
		var settings: Dictionary = _meta["focus_camera"][name]
		_yaw = float(settings["yaw"])
		_pitch = float(settings["pitch"])
		_distance = float(settings["distance"])
		_update_camera()
	_update_label()


func _update_label() -> void:
	if _label == null or _meta.is_empty():
		return
	_label.text = "全天然腔体形变 · %s\nMAIN + B_01～B_30 · T_01～T_22\n固定 %d 点 · 真实最大位移 0.200 mm\n灰=0，蓝→青→红=0～0.2 mm\n箭头×6；模型位移不放大\n左键旋转 · 中键平移 · 滚轮缩放 · R 复位\nB_24 原有相交与各档变化已单独记录。" % [_focus_name, int(_meta["fixed_vertices"])]
	if _state_label != null:
		var state := "插值"
		if is_equal_approx(filling, 0.0):
			state = "Reference"
		elif is_equal_approx(filling, 0.5):
			state = "Mid"
		elif is_equal_approx(filling, 1.0):
			state = "Expanded"
		_state_label.text = "%s · 充盈度 %.3f · 最大位移 %.3f mm" % [state, filling, filling * float(_meta["maximum_displacement_mm"])]


func _capture_full_validation(directory: String) -> void:
	_focus("ALL")
	display_mode = 0
	for level in [0.0, 0.25, 0.5, 0.75, 1.0]:
		_slider.value = level
		_apply_colors()
		if not _check_live_geometry():
			get_tree().quit(1)
			return
		if not await _write_screenshot(directory.path_join("full_u%03d.png" % int(level * 100))):
			return
	for i in 3:
		_state_buttons[i].pressed.emit()
		_apply_colors()
		if not is_equal_approx(filling, [0.0, 0.5, 1.0][i]) or not _check_live_geometry():
			get_tree().quit(1)
			return
	for prefix in ["J_", "T_"]:
		for i in range(1, 10 if prefix == "J_" else 23):
			var name := "%s%02d" % [prefix, i]
			_focus(name)
			_apply_colors()
			if not await _write_screenshot(directory.path_join(name.to_lower() + "_expanded.png")):
				return
	for name in ["B_31", "B_32", "BLADDER_TRANSITION", "B_24"]:
		_focus(name)
		_apply_colors()
		if not await _write_screenshot(directory.path_join(name.to_lower() + "_expanded.png")):
			return
	for entry in [["full_direction", "ALL", 1], ["j05_overlay", "J_05", 2], ["j09_overlay", "J_09", 2]]:
		_focus(str(entry[1]))
		display_mode = int(entry[2])
		_apply_colors()
		if not await _write_screenshot(directory.path_join(str(entry[0]) + ".png")):
			return
	# Match the accepted local baseline's J_02 comparison camera.
	_focus("J_02")
	display_mode = 4
	for level in [0.0, 0.5, 1.0]:
		_set_fill(level)
		_apply_colors()
		if not await _write_screenshot(directory.path_join("j02_u%03d.png" % int(level * 100))):
			return
	var log := FileAccess.open(directory.path_join("godot_runtime_validation.json"), FileAccess.WRITE)
	log.store_string(JSON.stringify({"checks":_runtime_checks, "all_passed":true}, "  "))
	log.close()
	get_tree().quit()

