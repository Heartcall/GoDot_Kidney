@tool
extends "res://scripts/local_displacement_preview.gd"

## Same camera, coloring and vector helpers; P1.3 scene/data stay untouched.
const MORPH_DIR := "res://deformation/p14_morph"
@export_range(0.0, 1.0, 0.001) var filling: float = 0.0:
	set(value):
		filling = clampf(value, 0.0, 1.0)
		if is_inside_tree() and not _refresh_pending:
			_refresh_pending = true
			call_deferred("_apply_colors")

var _accepted_displacement := PackedVector3Array()
var _slider: HSlider
var _state_label: Label
var _refresh_pending := false
var _state_normals: Array[PackedVector3Array] = []
var _fixed_indices := PackedInt32Array()
var _runtime_checks: Array[Dictionary] = []
var _state_buttons: Array[Button] = []


func _ready() -> void:
	display_mode = 4
	_load_morph()
	if not Engine.is_editor_hint():
		_create_ui()
		for arg in OS.get_cmdline_user_args():
			if arg.begins_with("--morph-validation-dir="):
				call_deferred("_capture_morph_validation", arg.trim_prefix("--morph-validation-dir="))


func _load_morph() -> void:
	_mesh_node = get_node("MaskMesh") as MeshInstance3D
	_lines = get_node("Centerlines") as MeshInstance3D
	_wire = get_node("ReferenceWire") as MeshInstance3D
	_vectors = get_node("VectorGlyphs") as MeshInstance3D
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(MORPH_DIR.path_join("morph_preview.json")))
	if not parsed is Dictionary:
		_fail("请先运行 build_cavity_morph_states.py。")
		return
	_meta = parsed
	for record: Dictionary in [_meta["source_mesh"], _meta["approved_weight_source"]] + _meta["sources"].values():
		if FileAccess.get_sha256("res://" + str(record["path"])) != str(record["sha256"]):
			_fail("三态来源已改变，请基于认可的数据重新构建 P1.4。")
			return
	var binary_path := MORPH_DIR.path_join(str(_meta["binary_file"]))
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
	var fixed_data: Variant = JSON.parse_string(FileAccess.get_file_as_string(MORPH_DIR.path_join("fixed_vertex_indices.json")))
	if not fixed_data is Array or fixed_data.size() != int(_meta["fixed_vertices"]):
		_fail("固定顶点编号无效。")
		return
	if FileAccess.get_sha256(MORPH_DIR.path_join("fixed_vertex_indices.json")) != str(_meta["fixed_indices_sha256"]):
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
	print("MorphPreview: accepted P1.3 field; Reference/Mid/Expanded and continuous filling [0,1].")


func _current_normals(positions: PackedVector3Array) -> PackedVector3Array:
	# Recompute from CURRENT positions. Blending endpoint normals would not
	# give the actual normals of intermediate geometry.
	var result := PackedVector3Array()
	result.resize(positions.size())
	for k in range(0, _indices.size(), 3):
		var a := _indices[k]
		var b := _indices[k + 1]
		var c := _indices[k + 2]
		var normal := (positions[c] - positions[a]).cross(positions[b] - positions[a])
		result[a] += normal
		result[b] += normal
		result[c] += normal
	for i in result.size():
		result[i] = result[i].normalized()
	return result


func _apply_colors() -> void:
	_refresh_pending = false
	if _accepted_displacement.is_empty() or _mesh_node == null:
		return
	_displacement.resize(_reference.size())
	_magnitude.resize(_reference.size())
	var positions := _reference.duplicate()
	for i in positions.size():
		_displacement[i] = _accepted_displacement[i] * filling
		_magnitude[i] = _displacement[i].length()
		positions[i] += _displacement[i]
	_normals_deformed = _current_normals(positions)
	# Parent renders current geometry and helpers with an absolute 0.2 mm
	# color scale shared by all fillings. It does not solve a new field.
	super._apply_colors()
	if _slider != null:
		_slider.set_value_no_signal(filling)
	_update_label()


func _set_fill(value: float) -> void:
	filling = value


func _update_helpers() -> void:
	if filling <= 0.01:
		_helpers_pending = false
		if _wire != null:
			_wire.visible = false
		if _vectors != null:
			_vectors.visible = false
		return
	_arrow_enabled = filling > 0.1
	super._update_helpers()


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
	_slider.custom_minimum_size = Vector2(380, 28)
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
	for row in [["ALL", "MAIN", "J_01", "J_02"], ["T_01", "T_02", "T_03", "T_04"], ["BLADDER_TRANSITION", "B_31", "B_32"]]:
		var focuses := HBoxContainer.new()
		column.add_child(focuses)
		for name in row:
			var button := Button.new()
			button.text = {"ALL":"全模型", "MAIN":"主腔室", "BLADDER_TRANSITION":"膀胱接口", "B_31":"IN_01 / B_31", "B_32":"IN_02 / B_32"}.get(name, name)
			button.pressed.connect(_focus.bind(str(name)))
			focuses.add_child(button)
	var toggle := CheckButton.new()
	toggle.text = "显示已确认的测试中心路径"
	toggle.toggled.connect(_toggle_lines)
	column.add_child(toggle)
	_update_label()


func _focus(name: String) -> void:
	super._focus(name)
	if name.begins_with("T_"):
		_distance = 30.0
		if name == "T_04":
			_yaw = -2.4
			_pitch = 0.3
		_update_camera()


func _update_label() -> void:
	if _label == null or _meta.is_empty():
		return
	_label.text = "P1.4 三态与插值 · %s\nMAIN + B_01～B_05 · 固定 %d 点\n灰=0，蓝→青→红=0～0.2 mm（统一色标）\n黄色方向箭头×6，模型位移不放大\n左键旋转 · 中键平移 · 滚轮缩放 · R 复位\n五个充盈度已检查；B_24 保留原有一对自交。" % [_focus_name, int(_meta["fixed_vertices"])]
	if _state_label != null:
		var state := "插值"
		if is_equal_approx(filling, 0.0):
			state = "Reference"
		elif is_equal_approx(filling, 0.5):
			state = "Mid"
		elif is_equal_approx(filling, 1.0):
			state = "Expanded"
		_state_label.text = "%s · 充盈度 %.3f · 最大位移 %.3f mm" % [state, filling, filling * float(_meta["maximum_displacement_mm"])]


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode >= KEY_1 and event.keycode <= KEY_3:
			_set_fill([0.0, 0.5, 1.0][event.keycode - KEY_1])
			return
		if event.keycode >= KEY_4 and event.keycode <= KEY_7:
			display_mode = [0, 1, 2, 4][event.keycode - KEY_4]
			return
	super._unhandled_input(event)


func _check_live_geometry() -> bool:
	var arrays: Array = (_mesh_node.mesh as ArrayMesh).surface_get_arrays(0)
	var positions: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var maximum_error := 0.0
	var fixed_maximum := 0.0
	var normal_error := 0.0
	for i in positions.size():
		maximum_error = maxf(maximum_error, positions[i].distance_to(_reference[i] + _accepted_displacement[i] * filling))
		normal_error = maxf(normal_error, absf(_normals_deformed[i].length() - 1.0))
	for i in _fixed_indices:
		fixed_maximum = maxf(fixed_maximum, positions[i].distance_to(_reference[i]))
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var passed := maximum_error <= 0.00001 and fixed_maximum == 0.0 and normal_error < 0.00001 and indices == _indices
	_runtime_checks.append({"fill":filling, "vertex_count":positions.size(), "triangle_count":indices.size()/3,
		"maximum_formula_error_mm":maximum_error, "fixed_maximum_displacement_mm":fixed_maximum,
		"maximum_normal_length_error":normal_error, "indices_unchanged":indices == _indices, "passed":passed})
	if not passed:
		push_error("Morph runtime geometry check failed at u=%f" % filling)
	return passed


func _capture_morph_validation(directory: String) -> void:
	# Exercise the actual slider signal, not only the fill setter.
	_focus("J_02")
	for level in [0.0, 0.25, 0.5, 0.75, 1.0]:
		_slider.value = level
		_apply_colors()
		if not _check_live_geometry():
			get_tree().quit(1)
			return
		if not await _write_screenshot(directory.path_join("j02_u%03d.png" % int(level * 100))):
			return
	# Exercise the actual button signals and verify their bound target fills.
	for i in 3:
		_state_buttons[i].pressed.emit()
		_apply_colors()
		if not is_equal_approx(filling, [0.0, 0.5, 1.0][i]) or not _check_live_geometry():
			get_tree().quit(1)
			return
	for name in ["J_01", "T_01", "T_02", "T_03", "T_04", "BLADDER_TRANSITION", "B_31", "B_32"]:
		display_mode = 0
		_focus(name)
		_apply_colors()
		if not await _write_screenshot(directory.path_join(name.to_lower() + "_expanded.png")):
			return
	_focus("J_02")
	for entry in [["j02_mid_direction", 0.5, 1], ["j02_expanded_overlay", 1.0, 2]]:
		_set_fill(float(entry[1]))
		display_mode = int(entry[2])
		_apply_colors()
		if not await _write_screenshot(directory.path_join(str(entry[0]) + ".png")):
			return
	var log := FileAccess.open(directory.path_join("godot_runtime_validation.json"), FileAccess.WRITE)
	log.store_string(JSON.stringify({"checks":_runtime_checks, "all_passed":true}, "  "))
	log.close()
	get_tree().quit()
