@tool
extends "res://scripts/irrigation_mask_preview.gd"

## Reuse camera utilities only. This scene never runs the parent's P1.2 loader.
const DATA_DIR := "res://deformation/p13_static"
const VIEW_NAMES := ["位移大小", "位移方向 RGB / 箭头×6", "膨胀 + 参考蓝线", "参考形态", "静态膨胀"]
@export_enum("位移大小", "位移方向", "参考线叠加", "参考形态", "静态膨胀") var display_mode: int = 0:
	set(value):
		display_mode = value
		if is_inside_tree():
			call_deferred("_apply_colors")

var _reference := PackedVector3Array()
var _displacement := PackedVector3Array()
var _normals_deformed := PackedVector3Array()
var _magnitude := PackedFloat32Array()
var _mask_weights := PackedFloat32Array()
var _activity := PackedFloat32Array()
var _wire: MeshInstance3D
var _vectors: MeshInstance3D
var _helpers_pending := false
var _arrow_enabled := true


func _ready() -> void:
	_load_displacement()
	if not Engine.is_editor_hint():
		_create_ui()
		for arg in OS.get_cmdline_user_args():
			if arg.begins_with("--displacement-validation-dir="):
				call_deferred("_capture_validation", arg.trim_prefix("--displacement-validation-dir="))


func _load_displacement() -> void:
	_mesh_node = get_node("MaskMesh") as MeshInstance3D
	_lines = get_node("Centerlines") as MeshInstance3D
	_wire = get_node("ReferenceWire") as MeshInstance3D
	_vectors = get_node("VectorGlyphs") as MeshInstance3D
	var meta_path := DATA_DIR.path_join("displacement_preview.json")
	if not FileAccess.file_exists(meta_path):
		_fail("请先运行 build_local_displacement.py。")
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(meta_path))
	if not parsed is Dictionary:
		_fail("位移元数据格式无效。")
		return
	_meta = parsed
	var binary_path := DATA_DIR.path_join(str(_meta["binary_file"]))
	if FileAccess.get_sha256(binary_path) != str(_meta["binary_sha256"]):
		_fail("位移二进制哈希不匹配。")
		return
	for key in ["approved_weight_source", "source_mesh"]:
		var record: Dictionary = _meta[key]
		if FileAccess.get_sha256("res://" + str(record["path"])) != str(record["sha256"]):
			_fail("源网格或已认可的 P1.2 权重已改变，请重新构建位移。")
			return
	var file := FileAccess.open(binary_path, FileAccess.READ)
	if file == null:
		_fail("无法打开位移数据。")
		return
	var magic := file.get_buffer(8).get_string_from_ascii()
	var n := int(file.get_32())
	var m := int(file.get_32())
	if magic != "KDSP0001" or n != int(_meta["vertex_count"]) or m != int(_meta["triangle_count"]) or file.get_length() != 16 + n * 60 + m * 12:
		_fail("位移格式／数组数量不匹配。")
		return
	_reference = _read_vectors(file, n)
	_displacement = _read_vectors(file, n)
	_normals = _read_vectors(file, n)
	_normals_deformed = _read_vectors(file, n)
	_mask_weights = file.get_buffer(n * 4).to_float32_array()
	_activity = file.get_buffer(n * 4).to_float32_array()
	_magnitude = file.get_buffer(n * 4).to_float32_array()
	_indices = file.get_buffer(m * 12).to_int32_array()
	file.close()
	_vertices = _reference.duplicate()
	var material := StandardMaterial3D.new()
	material.vertex_color_use_as_albedo = true
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.roughness = 1.0
	_mesh_node.material_override = material
	_build_centerlines()
	_focus("ALL")
	_apply_colors()
	print("DisplacementPreview: loaded %d vertices, %d triangles; max %.6f mm; single static field." % [n, m, float(_meta["maximum_displacement_mm"])])


func _apply_colors() -> void:
	if _reference.is_empty() or _mesh_node == null:
		return
	var positions := _reference.duplicate()
	var colors := PackedColorArray()
	colors.resize(positions.size())
	var max_magnitude := maxf(float(_meta["maximum_displacement_mm"]), 0.000001)
	for i in positions.size():
		if display_mode != 3:
			positions[i] += _displacement[i]
		if display_mode == 0:
			var t := clampf(_magnitude[i] / max_magnitude, 0.0, 1.0)
			if _magnitude[i] < 0.00000001:
				colors[i] = Color(0.25, 0.28, 0.34)
			elif t <= 0.5:
				colors[i] = Color(0.08, 0.3, 1.0).lerp(Color(0.1, 0.95, 0.7), t * 2.0)
			else:
				colors[i] = Color(0.1, 0.95, 0.7).lerp(Color(1.0, 0.22, 0.08), (t - 0.5) * 2.0)
		elif display_mode == 1:
			if _magnitude[i] < 0.00000001:
				colors[i] = Color(0.25, 0.28, 0.34)
			else:
				var direction := _displacement[i].normalized()
				colors[i] = Color((direction.x + 1.0) * 0.5, (direction.y + 1.0) * 0.5, (direction.z + 1.0) * 0.5)
		else:
			colors[i] = Color(0.87, 0.59, 0.55)
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = positions
	arrays[Mesh.ARRAY_NORMAL] = _normals if display_mode == 3 else _normals_deformed
	arrays[Mesh.ARRAY_COLOR] = colors
	arrays[Mesh.ARRAY_INDEX] = _indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	_mesh_node.mesh = mesh
	_update_helpers()
	_update_label()


func _build_centerlines() -> void:
	if _meta.is_empty() or _lines == null:
		return
	var lines := ImmediateMesh.new()
	lines.surface_begin(Mesh.PRIMITIVE_LINES)
	lines.surface_set_color(Color(1.0, 0.9, 0.25))
	for path in _meta["paths"]:
		if not str(path["id"]) in _meta["selected_path_ids"]:
			continue
		var points: Array = path["points_mm"]
		for i in range(points.size() - 1):
			lines.surface_add_vertex(_vec(points[i]))
			lines.surface_add_vertex(_vec(points[i + 1]))
	lines.surface_end()
	_lines.mesh = lines
	_lines.material_override = _line_material(Color(1.0, 0.9, 0.25))
	_lines.visible = false


func _line_material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.albedo_color = color
	material.no_depth_test = true
	return material


func _update_helpers() -> void:
	_helpers_pending = false
	if _reference.is_empty() or _wire == null or _vectors == null:
		return
	_wire.visible = display_mode == 2
	_vectors.visible = display_mode == 1 and _arrow_enabled
	var camera := get_node("PreviewCamera") as Camera3D
	if _wire.visible:
		var edges := {}
		for k in range(0, _indices.size(), 3):
			var a := _indices[k]
			var b := _indices[k + 1]
			var c := _indices[k + 2]
			if maxf(_magnitude[a], maxf(_magnitude[b], _magnitude[c])) < 0.002:
				continue
			var center := (_reference[a] + _reference[b] + _reference[c]) / 3.0
			if (_normals[a] + _normals[b] + _normals[c]).dot(camera.position - center) <= 0:
				continue
			for edge in [Vector2i(a, b), Vector2i(b, c), Vector2i(c, a)]:
				var low := mini(edge.x, edge.y)
				var high := maxi(edge.x, edge.y)
				edges[low * _reference.size() + high] = Vector2i(low, high)
		var wire := ImmediateMesh.new()
		wire.surface_begin(Mesh.PRIMITIVE_LINES)
		var counter := 0
		for edge: Vector2i in edges.values():
			if counter % 3 == 0:
				wire.surface_add_vertex(_reference[edge.x])
				wire.surface_add_vertex(_reference[edge.y])
			counter += 1
		wire.surface_end()
		_wire.mesh = wire
		_wire.material_override = _line_material(Color(0.1, 0.4, 1.0))
	if _vectors.visible:
		var arrows := ImmediateMesh.new()
		arrows.surface_begin(Mesh.PRIMITIVE_LINES)
		var stride := maxi(1, _reference.size() / 200)
		for i in range(0, _reference.size(), stride):
			if _magnitude[i] < 0.01 or _normals[i].dot(camera.position - _reference[i]) <= 0:
				continue
			var start := _reference[i] + _normals[i] * 0.03
			var finish := start + _displacement[i] * 6.0
			var direction := _displacement[i].normalized()
			var helper := Vector3.UP if absf(direction.dot(Vector3.UP)) < 0.9 else Vector3.RIGHT
			var side := direction.cross(helper).normalized()
			var head := minf(_magnitude[i] * 1.5, 0.25)
			for pair in [[start, finish], [finish, finish - direction * head + side * head * 0.5], [finish, finish - direction * head - side * head * 0.5]]:
				arrows.surface_add_vertex(pair[0])
				arrows.surface_add_vertex(pair[1])
		arrows.surface_end()
		_vectors.mesh = arrows
		_vectors.material_override = _line_material(Color(1.0, 0.9, 0.2))


func _update_camera() -> void:
	super._update_camera()
	if not _helpers_pending and not _reference.is_empty():
		_helpers_pending = true
		call_deferred("_update_helpers")


func _focus(name: String) -> void:
	if _meta.has("landmarks") and _meta["landmarks"].has(name):
		_center = _vec(_meta["landmarks"][name])
		_distance = 36.0
		# Observe J_01 from the opposite side to avoid foreground branches.
		_yaw = -2.4 if name == "J_01" else 0.6
		_pitch = 0.3 if name == "J_01" else 0.55
		_focus_name = name
		_update_camera()
		_update_label()
	else:
		_yaw = 0.6
		_pitch = 0.55
		super._focus(name)


func _create_ui() -> void:
	var canvas := CanvasLayer.new()
	add_child(canvas)
	var panel := PanelContainer.new()
	panel.position = Vector2(18, 18)
	canvas.add_child(panel)
	var column := VBoxContainer.new()
	panel.add_child(column)
	_label = Label.new()
	_label.add_theme_font_size_override("font_size", 17)
	column.add_child(_label)
	var modes := HBoxContainer.new()
	column.add_child(modes)
	for i in 5:
		var button := Button.new()
		button.text = ["1 位移大小", "2 方向", "3 参考线叠加", "4 参考", "5 膨胀"][i]
		button.pressed.connect(_choose_mode.bind(i))
		modes.add_child(button)
	var focuses := HBoxContainer.new()
	column.add_child(focuses)
	for name in ["ALL", "MAIN", "J_01", "J_02", "B_32"]:
		var button := Button.new()
		button.text = {"ALL": "全模型", "MAIN": "主腔室", "J_01": "J_01", "J_02": "J_02", "B_32": "B_32"}[name]
		button.pressed.connect(_focus.bind(str(name)))
		focuses.add_child(button)
	var toggle := CheckButton.new()
	toggle.text = "显示本轮中心路径"
	toggle.toggled.connect(_toggle_lines)
	column.add_child(toggle)
	_update_label()


func _choose_mode(mode: int) -> void:
	display_mode = mode


func _update_label() -> void:
	if _label == null or _meta.is_empty():
		return
	_label.text = "P1.3 局部静态位移 · %s\nMAIN + B_01～B_05 · 最大 %.3f mm · 固定 %d 点\n当前：%s\n大小：灰=0，蓝→青→红=0～0.2 mm\n方向：RGB 对应 XYZ；箭头长度×6，模型位移不放大\n左键旋转 · 中键平移 · 滚轮缩放 · R 复位\n仅参考与单个静态终点；原网格 B_24 已有一对自交。" % [_focus_name, float(_meta["maximum_displacement_mm"]), int(_meta["fixed_vertices"]), VIEW_NAMES[display_mode]]


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode >= KEY_1 and event.keycode <= KEY_5:
		display_mode = event.keycode - KEY_1
	else:
		super._unhandled_input(event)


func _capture_validation(directory: String) -> void:
	for shot in [["full_magnitude", 0, "ALL"], ["main_magnitude", 0, "MAIN"],
			["j01_magnitude", 0, "J_01"], ["j02_magnitude", 0, "J_02"],
			["j02_direction", 1, "J_02"], ["j02_overlay", 2, "J_02"],
			["j02_reference", 3, "J_02"], ["j02_deformed", 4, "J_02"], ["b32_magnitude", 0, "B_32"]]:
		display_mode = int(shot[1])
		_focus(str(shot[2]))
		_apply_colors()
		if not await _write_screenshot(directory.path_join(str(shot[0]) + ".png")):
			return
	get_tree().quit()
