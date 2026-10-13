@tool
extends Node3D

## P1.2 inspection only. Reads a canonical mesh; never moves source vertices.
const META_PATH := "res://deformation/p1_masks/mask_preview.json"
const BINARY_PATH := "res://deformation/p1_masks/mask_preview.bin"

@export_enum("区域类别", "连续权重", "路径归属") var color_mode: int = 0:
	set(value):
		color_mode = value
		if is_inside_tree():
			call_deferred("_apply_colors")
@export_tool_button("重新加载掩码") var reload_masks: Callable = _load_masks

var _meta: Dictionary = {}
var _vertices := PackedVector3Array()
var _normals := PackedVector3Array()
var _weights := PackedFloat32Array()
var _regions := PackedInt32Array()
var _owners := PackedInt32Array()
var _indices := PackedInt32Array()
var _mesh_node: MeshInstance3D
var _lines: MeshInstance3D
var _label: Label
var _center := Vector3.ZERO
var _distance := 190.0
var _yaw := 0.6
var _pitch := 0.55
var _focus_name := "全模型"


func _ready() -> void:
	_load_masks()
	if not Engine.is_editor_hint():
		_create_ui()
		var screenshot_path := ""
		var validation_dir := ""
		for arg in OS.get_cmdline_user_args():
			if arg.begins_with("--mask-mode="):
				color_mode = int(arg.trim_prefix("--mask-mode="))
			if arg.begins_with("--mask-focus="):
				_focus(arg.trim_prefix("--mask-focus="))
			if arg.begins_with("--mask-screenshot="):
				screenshot_path = arg.trim_prefix("--mask-screenshot=")
			if arg.begins_with("--mask-validation-dir="):
				validation_dir = arg.trim_prefix("--mask-validation-dir=")
		_apply_colors()
		if not validation_dir.is_empty():
			call_deferred("_validation_screenshots", validation_dir)
		elif not screenshot_path.is_empty():
			call_deferred("_save_screenshot", screenshot_path)


func _fail(message: String) -> void:
	push_error("MaskPreview: " + message)
	if not Engine.is_editor_hint():
		get_tree().quit(1)


func _read_vectors(file: FileAccess, count: int) -> PackedVector3Array:
	var floats := file.get_buffer(count * 12).to_float32_array()
	var vectors := PackedVector3Array()
	vectors.resize(count)
	for i in count:
		vectors[i] = Vector3(floats[i * 3], floats[i * 3 + 1], floats[i * 3 + 2])
	return vectors


func _load_masks() -> void:
	if not is_inside_tree():
		return
	_mesh_node = get_node("MaskMesh") as MeshInstance3D
	_lines = get_node("Centerlines") as MeshInstance3D
	if not FileAccess.file_exists(META_PATH) or not FileAccess.file_exists(BINARY_PATH):
		_fail("请先运行 resolve_cavity_topology.py 和 build_cavity_surface_masks.py。")
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(META_PATH))
	if not parsed is Dictionary:
		_fail("掩码元数据不是有效的 JSON 对象。")
		return
	_meta = parsed
	if FileAccess.get_sha256(BINARY_PATH) != str(_meta["binary_sha256"]):
		_fail("掩码二进制校验失败，请重新生成。")
		return
	var source_path := "res://" + str(_meta["source_mesh"]["path"])
	if FileAccess.get_sha256(source_path) != str(_meta["source_mesh"]["sha256"]):
		_fail("原始腔体已改变，请重新构建拓扑和掩码。")
		return
	var file := FileAccess.open(BINARY_PATH, FileAccess.READ)
	if file == null:
		_fail("无法打开掩码二进制。")
		return
	if file.get_buffer(8).get_string_from_ascii() != "KMSK0001":
		_fail("未知掩码二进制格式。")
		return
	var vertex_count := int(file.get_32())
	var triangle_count := int(file.get_32())
	var path_count := int(file.get_32())
	if vertex_count != int(_meta["vertex_count"]) or triangle_count != int(_meta["triangle_count"]) or path_count != _meta["paths"].size():
		_fail("掩码顶点／面／路径数量不匹配。")
		return
	if file.get_length() != 20 + vertex_count * 40 + triangle_count * 12:
		_fail("掩码二进制长度不匹配。")
		return
	_vertices = _read_vectors(file, vertex_count)
	_normals = _read_vectors(file, vertex_count)
	_weights = file.get_buffer(vertex_count * 4).to_float32_array()
	_regions = file.get_buffer(vertex_count * 4).to_int32_array()
	_owners = file.get_buffer(vertex_count * 4).to_int32_array()
	file.get_buffer(vertex_count * 4) # Owner arclength reserved for later inspection.
	_indices = file.get_buffer(triangle_count * 12).to_int32_array()
	file.close()
	var material := StandardMaterial3D.new()
	material.vertex_color_use_as_albedo = true
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.roughness = 1.0
	_mesh_node.material_override = material
	_apply_colors()
	_build_centerlines()
	_focus("ALL")
	print("MaskPreview: loaded %d vertices, %d triangles, %d paths; no deformation." % [vertex_count, triangle_count, path_count])


func _vec(value: Array) -> Vector3:
	return Vector3(float(value[0]), float(value[1]), float(value[2]))


func _color(value: Array) -> Color:
	return Color(float(value[0]), float(value[1]), float(value[2]))


func _apply_colors() -> void:
	if _vertices.is_empty() or _mesh_node == null:
		return
	var colors := PackedColorArray()
	colors.resize(_vertices.size())
	for i in _vertices.size():
		if color_mode == 1:
			var weight := float(_weights[i])
			var low := Color(0.18, 0.48, 1.0)
			var middle := Color(1.0, 0.62, 0.08)
			var high := Color(0.2, 0.84, 0.4)
			colors[i] = low.lerp(middle, weight * 2.0) if weight <= 0.5 else middle.lerp(high, (weight - 0.5) * 2.0)
		elif color_mode == 2:
			colors[i] = _color(_meta["paths"][_owners[i]]["color"])
		else:
			colors[i] = _color(_meta["regions"][_regions[i]]["color"])
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = _vertices
	arrays[Mesh.ARRAY_NORMAL] = _normals
	arrays[Mesh.ARRAY_COLOR] = colors
	arrays[Mesh.ARRAY_INDEX] = _indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	_mesh_node.mesh = mesh
	_update_label()


func _build_centerlines() -> void:
	var lines := ImmediateMesh.new()
	lines.surface_begin(Mesh.PRIMITIVE_LINES)
	for path in _meta["paths"]:
		lines.surface_set_color(_color(path["color"]))
		var points: Array = path["points_mm"]
		for i in range(points.size() - 1):
			lines.surface_add_vertex(_vec(points[i]))
			lines.surface_add_vertex(_vec(points[i + 1]))
	lines.surface_end()
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.vertex_color_use_as_albedo = true
	material.no_depth_test = true
	_lines.mesh = lines
	_lines.material_override = material
	_lines.visible = false


func _focus(path_id: String) -> void:
	if _meta.is_empty():
		return
	var bounds: Array = _meta["bounds_mm"]
	_center = (_vec(bounds[0]) + _vec(bounds[1])) * 0.5
	_distance = (_vec(bounds[1]) - _vec(bounds[0])).length() * 1.2
	_focus_name = "全模型"
	for path in _meta["paths"]:
		if str(path["id"]) == path_id:
			var points: Array = path["points_mm"]
			_center = (_vec(points[0]) + _vec(points[-1])) * 0.5
			_distance = maxf(_vec(points[-1]).distance_to(_vec(points[0])) * 2.8, 32.0)
			_focus_name = path_id
			break
	_update_camera()
	_update_label()


func _update_camera() -> void:
	var camera := get_node("PreviewCamera") as Camera3D
	camera.position = _center + Vector3(sin(_yaw) * cos(_pitch), sin(_pitch), cos(_yaw) * cos(_pitch)) * _distance
	camera.look_at(_center, Vector3.UP)


func _create_ui() -> void:
	var canvas := CanvasLayer.new()
	add_child(canvas)
	var panel := PanelContainer.new()
	panel.position = Vector2(18, 18)
	canvas.add_child(panel)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 8)
	panel.add_child(column)
	_label = Label.new()
	_label.add_theme_font_size_override("font_size", 17)
	column.add_child(_label)
	var modes := HBoxContainer.new()
	column.add_child(modes)
	for i in 3:
		var button := Button.new()
		button.text = ["1 区域类别", "2 连续权重", "3 路径归属"][i]
		button.pressed.connect(_select_mode.bind(i))
		modes.add_child(button)
	var focus_row := HBoxContainer.new()
	column.add_child(focus_row)
	for id in ["ALL", "BLADDER_TRANSITION", "B_31", "B_32"]:
		var button := Button.new()
		button.text = {"ALL": "全模型", "BLADDER_TRANSITION": "膀胱接口", "B_31": "B_31 接口", "B_32": "B_32 接口"}[id]
		button.pressed.connect(_focus.bind(str(id)))
		focus_row.add_child(button)
	var toggle := CheckButton.new()
	toggle.text = "显示中心线（透视叠加）"
	toggle.toggled.connect(_toggle_lines)
	column.add_child(toggle)
	_update_label()


func _update_label() -> void:
	if _label == null or _meta.is_empty():
		return
	var r: Array = _meta["regions"]
	_label.text = "P1.2 腔体掩码检查 · %s\n蓝：固定 %d  |  橙：过渡 %d  |  绿：可扩张 %d\n权重 0=固定，1=可扩张；当前模式：%s\n左键旋转 · 中键平移 · 滚轮缩放 · R 复位\n路径归属色仅为最近中心线诊断；本场景不执行形变。" % [_focus_name, int(r[0]["vertices"]), int(r[1]["vertices"]), int(r[2]["vertices"]), ["区域类别", "连续权重", "路径归属"][color_mode]]


func _select_mode(mode: int) -> void:
	color_mode = mode


func _toggle_lines(enabled: bool) -> void:
	_lines.visible = enabled


func _unhandled_input(event: InputEvent) -> void:
	if Engine.is_editor_hint():
		return
	if event is InputEventMouseMotion:
		if event.button_mask & MOUSE_BUTTON_MASK_LEFT:
			_yaw -= event.relative.x * 0.008
			_pitch = clampf(_pitch + event.relative.y * 0.008, -1.45, 1.45)
			_update_camera()
		elif event.button_mask & MOUSE_BUTTON_MASK_MIDDLE:
			var camera := get_node("PreviewCamera") as Camera3D
			_center += (-camera.basis.x * event.relative.x + camera.basis.y * event.relative.y) * _distance * 0.001
			_update_camera()
	elif event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			_distance = maxf(_distance * 0.88, 2.0)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			_distance = minf(_distance / 0.88, 1500.0)
		_update_camera()
	elif event is InputEventKey and event.pressed and not event.echo:
		if event.keycode >= KEY_1 and event.keycode <= KEY_3:
			color_mode = event.keycode - KEY_1
		elif event.keycode == KEY_R:
			_yaw = 0.6
			_pitch = 0.55
			_focus("ALL")


func _write_screenshot(path: String) -> bool:
	for i in 4:
		await RenderingServer.frame_post_draw
	var absolute := ProjectSettings.globalize_path(path)
	DirAccess.make_dir_recursive_absolute(absolute.get_base_dir())
	var error := get_viewport().get_texture().get_image().save_png(absolute)
	if error != OK:
		_fail("无法保存预览截图：%s" % path)
		return false
	print("MaskPreview: screenshot saved to ", absolute)
	return true


func _save_screenshot(path: String) -> void:
	await _write_screenshot(path)
	get_tree().quit()


func _validation_screenshots(directory: String) -> void:
	for shot in [["regions", 0, "ALL"], ["weights", 1, "ALL"], ["paths", 2, "ALL"],
			["bladder", 0, "BLADDER_TRANSITION"], ["b31", 0, "B_31"], ["b32", 1, "B_32"]]:
		color_mode = int(shot[1])
		_focus(str(shot[2]))
		_apply_colors()
		if not await _write_screenshot(directory.path_join(str(shot[0]) + ".png")):
			return
	get_tree().quit()
