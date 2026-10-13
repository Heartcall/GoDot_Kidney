extends "res://scripts/irrigation_mask_preview.gd"

const AUDIT_DIR := "res://deformation/p15_audit"
const SECTION_SHADER := preload("res://shaders/audit_section.gdshader")
var _tissue_node: MeshInstance3D
var _section_materials: Array[ShaderMaterial] = []
var _audit_counts := {}
var _section_enabled := true
var _section_normal := Vector3.RIGHT
var _section_offset := 0.0
var _highlight := true
var _cavity_data := {}
var _tissue_data := {}
var _visibility_toggles: Array[CheckButton] = []
var _section_toggle: CheckButton


func _ready() -> void:
	_mesh_node = get_node("MaskMesh") as MeshInstance3D
	_tissue_node = get_node("TissueMesh") as MeshInstance3D
	_lines = get_node("Centerlines") as MeshInstance3D
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(AUDIT_DIR.path_join("audit_preview.json")))
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
		if arg.begins_with("--audit-validation-dir="):
			call_deferred("_capture_audit", arg.trim_prefix("--audit-validation-dir="))


func _read_reference(name: String) -> Dictionary:
	var path := AUDIT_DIR.path_join(name + "_reference.bin")
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
		colors.append(Color(1.0, 0.12, 0.04) if _highlight and flag > 0 else color)
	arrays[Mesh.ARRAY_COLOR] = colors
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	node.mesh = mesh
	var material := ShaderMaterial.new()
	material.shader = SECTION_SHADER
	node.material_override = material
	_section_materials.append(material)
	_update_section()


func _update_section() -> void:
	for material in _section_materials:
		material.set_shader_parameter("section_enabled", _section_enabled)
		material.set_shader_parameter("section_normal", _section_normal)
		material.set_shader_parameter("section_offset", _section_offset)
	_update_label()


func _section_axis(axis: Vector3) -> void:
	_section_normal = axis
	_section_enabled = true
	if _section_toggle != null:
		_section_toggle.set_pressed_no_signal(true)
	_update_section()


func _set_offset(value: float) -> void:
	_section_offset = value
	_update_section()


func _create_audit_ui() -> void:
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
	for entry in [["显示腔体（蓝）", _mesh_node], ["显示组织（粉）", _tissue_node]]:
		var toggle := CheckButton.new()
		toggle.text = str(entry[0])
		toggle.button_pressed = true
		toggle.toggled.connect(_visibility.bind(entry[1]))
		column.add_child(toggle)
		_visibility_toggles.append(toggle)
	var section := CheckButton.new()
	section.text = "剖切显示（不透明，无 DOF）"
	section.button_pressed = true
	section.toggled.connect(_toggle_section)
	column.add_child(section)
	_section_toggle = section
	var row := HBoxContainer.new()
	column.add_child(row)
	for entry in [["X 剖切", Vector3.RIGHT], ["Y 剖切", Vector3.UP], ["Z 剖切", Vector3.BACK]]:
		var button := Button.new()
		button.text = str(entry[0])
		button.pressed.connect(_section_axis.bind(entry[1]))
		row.add_child(button)
	var slider := HSlider.new()
	slider.min_value = -65
	slider.max_value = 65
	slider.step = 0.1
	slider.custom_minimum_size = Vector2(390, 25)
	slider.value_changed.connect(_set_offset)
	column.add_child(slider)
	var choice := OptionButton.new()
	choice.add_item("ALL")
	for prefix in ["J_", "T_"]:
		for i in range(1, 10 if prefix == "J_" else 23):
			choice.add_item("%s%02d" % [prefix, i])
	for name in ["B_31", "B_32", "BLADDER", "IN_01", "IN_02"]:
		choice.add_item(name)
	choice.item_selected.connect(_select_focus.bind(choice))
	column.add_child(choice)
	_update_label()


func _visibility(enabled: bool, node: MeshInstance3D) -> void:
	node.visible = enabled


func _toggle_section(enabled: bool) -> void:
	_section_enabled = enabled
	_update_section()


func _select_focus(index: int, choice: OptionButton) -> void:
	_focus(choice.get_item_text(index))


func _focus(name: String) -> void:
	if _meta.has("landmarks") and _meta["landmarks"].has(name):
		_center = _vec(_meta["landmarks"][name])
		_distance = 42.0
		_yaw = -2.4
		_pitch = 0.3
		_focus_name = name
		_update_camera()
	else:
		super._focus(name)
		if name == "ALL":
			_distance *= 0.75
			_update_camera()
	_update_label()


func _update_label() -> void:
	if _label == null:
		return
	_label.text = "P1.5 几何审计 · 仅原始参考态 · %s\n组织 23 对原自交；两网格 58 对穿越\n红色=问题三角面关联顶点（示意范围）\n尚无通过验证的组织位移／三态\n剖切位置 %.1f mm（显示坐标）\n左键旋转 · 中键平移 · 滚轮缩放 · R 全局\n此剖切无封口，不用于壁厚测量。" % [_focus_name, _section_offset]


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and event.keycode >= KEY_1 and event.keycode <= KEY_6:
		return
	super._unhandled_input(event)


func _capture_audit(directory: String) -> void:
	_focus("ALL")
	for shot in [["joint_section_x", true, true, true, Vector3.RIGHT], ["joint_section_y", true, true, true, Vector3.UP],
		["joint_solid", true, true, false, Vector3.RIGHT], ["tissue_only", false, true, false, Vector3.RIGHT], ["cavity_only", true, false, false, Vector3.RIGHT]]:
		_mesh_node.visible = bool(shot[1])
		_tissue_node.visible = bool(shot[2])
		_section_enabled = bool(shot[3])
		_section_normal = shot[4]
		_visibility_toggles[0].set_pressed_no_signal(_mesh_node.visible)
		_visibility_toggles[1].set_pressed_no_signal(_tissue_node.visible)
		_section_toggle.set_pressed_no_signal(_section_enabled)
		_update_section()
		if not await _write_screenshot(directory.path_join(str(shot[0]) + ".png")):
			return
	var passed := true
	for entry in [["cavity", _mesh_node, _cavity_data], ["tissue", _tissue_node, _tissue_data]]:
		var arrays: Array = (entry[1].mesh as ArrayMesh).surface_get_arrays(0)
		passed = passed and arrays[Mesh.ARRAY_VERTEX] == entry[2]["vertices"] and arrays[Mesh.ARRAY_INDEX] == entry[2]["indices"]
	var file := FileAccess.open(directory.path_join("runtime_audit.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify({"reference_only":true, "counts":_audit_counts, "geometry_arrays_match":passed, "opaque_section_shader":true}, "  "))
	file.close()
	get_tree().quit(0 if passed else 1)
