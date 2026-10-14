extends "res://scripts/irrigation_geometry_audit_preview.gd"

const R2_DIR := "res://analysis/irrigation_baseline/p15_r2"
var _fill := 0.0
var _use_after := true
var _debug_mode := 0
var _fill_slider: HSlider
var _state_info: Label
var _trial_choice: OptionButton
var _mode_choice: OptionButton
var _reference_wire: MeshInstance3D
var _area_mesh: MeshInstance3D
var _show_reference := true
var _show_tissue := true
var _refresh_queued := false
var _validating := false
var _last_geometry := {}
var _capture_checks: Array = []
var _reference_face_ids := PackedInt32Array()

func _ready() -> void:
	_mesh_node = get_node("MaskMesh") as MeshInstance3D
	_tissue_node = get_node("TissueMesh") as MeshInstance3D
	_lines = get_node("Centerlines") as MeshInstance3D
	_area_mesh = MeshInstance3D.new()
	add_child(_area_mesh)
	_reference_wire = MeshInstance3D.new()
	add_child(_reference_wire)
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(R2_DIR.path_join("preview.json")))
	if not parsed is Dictionary:
		_fail("请先构建P1.5-R2诊断数据。")
		return
	_meta = parsed
	for record: Dictionary in _meta["sources"].values():
		if FileAccess.get_sha256("res://"+str(record["path"])) != str(record["sha256"]):
			_fail("原始参考网格哈希已改变。")
			return
	var origin := _vec(_meta["preview_origin_mm"])
	for path: Dictionary in _meta["paths"]:
		var points := []
		for point in path["points_mm"]:
			var p := _vec(point)-origin
			points.append([p.x,p.y,p.z])
		path["points_mm"] = points
	for name in _meta["landmarks"]:
		var p := _vec(_meta["landmarks"][name])-origin
		_meta["landmarks"][name] = [p.x,p.y,p.z]
	for i in 2:
		var p := _vec(_meta["bounds_mm"][i])-origin
		_meta["bounds_mm"][i] = [p.x,p.y,p.z]
	_cavity_data = _read_r2("cavity")
	_tissue_data = _read_r2("tissue")
	if _cavity_data.is_empty() or _tissue_data.is_empty():
		return
	for node: MeshInstance3D in [_mesh_node,_tissue_node,_area_mesh]:
		var material := ShaderMaterial.new()
		material.shader = SECTION_SHADER
		node.material_override = material
		_section_materials.append(material)
	_create_audit_ui()
	_focus("ALL")
	_refresh()
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--r2-validation-dir="):
			_validating = true
			call_deferred("_capture_r2",arg.trim_prefix("--r2-validation-dir="))

func _read_r2(name: String) -> Dictionary:
	var path := R2_DIR.path_join(name+"_preview.bin")
	if FileAccess.get_sha256(path) != str(_meta["binary_sha256"][name]):
		_fail("诊断二进制哈希不匹配。")
		return {}
	var file := FileAccess.open(path,FileAccess.READ)
	var magic := file.get_buffer(8).get_string_from_ascii()
	var n := int(file.get_32())
	var m := int(file.get_32())
	if magic!="R2MP0001" or file.get_length()!=16+n*44+m*16:
		_fail("诊断二进制格式错误。")
		return {}
	var data := {"vertices":_read_vectors(file,n),"before":_read_vectors(file,n),"after":_read_vectors(file,n),
		"before_gradient":file.get_buffer(n*4).to_float32_array(),"after_gradient":file.get_buffer(n*4).to_float32_array(),
		"reference_areas":file.get_buffer(m*4).to_float32_array(),"indices":file.get_buffer(m*12).to_int32_array()}
	file.close()
	_audit_counts[name] = {"vertices":n,"triangles":m}
	return data

func _normals_now(positions: PackedVector3Array, indices: PackedInt32Array) -> PackedVector3Array:
	var result := PackedVector3Array()
	result.resize(positions.size())
	for k in range(0,indices.size(),3):
		var a := indices[k]
		var b := indices[k+1]
		var c := indices[k+2]
		var n := (positions[c]-positions[a]).cross(positions[b]-positions[a])
		result[a] += n
		result[b] += n
		result[c] += n
	for i in result.size():
		result[i] = result[i].normalized()
	return result

func _heat_gradient(value: float) -> Color:
	var t := clampf(value/0.2,0.0,1.0)
	return Color(0.1,0.25,0.95).lerp(Color(0.1,0.95,0.7),t*2) if t<0.5 else Color(0.1,0.95,0.7).lerp(Color(1.0,0.1,0.03),(t-0.5)*2)

func _heat_area(value: float) -> Color:
	if value<1.0:
		return Color(0.15,0.9,0.65).lerp(Color(1.0,0.1,0.03),clampf((1-value)/0.2,0,1))
	return Color(0.15,0.9,0.65).lerp(Color(0.2,0.25,1.0),clampf((value-1)/0.35,0,1))

func _mesh_arrays(positions: PackedVector3Array,normals: PackedVector3Array,indices: PackedInt32Array,colors: PackedColorArray) -> ArrayMesh:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = positions
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_COLOR] = colors
	if not indices.is_empty():
		arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
	return mesh

func _render_one(name: String,node: MeshInstance3D,data: Dictionary) -> void:
	var field: PackedVector3Array = data["after"] if _use_after else data["before"]
	var positions: PackedVector3Array = data["vertices"].duplicate()
	var gradients: PackedFloat32Array = data["after_gradient"] if _use_after else data["before_gradient"]
	var indices: PackedInt32Array = data["indices"]
	for i in positions.size():
		positions[i] += _fill*field[i]
	var normals := _normals_now(positions,indices)
	var colors := PackedColorArray()
	colors.resize(positions.size())
	for i in positions.size():
		colors[i] = _heat_gradient(_fill*gradients[i]) if name=="tissue" and _debug_mode==1 else Color(0.15,0.65,0.95) if name=="cavity" else Color(0.85,0.48,0.48)
	node.mesh = _mesh_arrays(positions,normals,indices,colors)
	_last_geometry[name] = {"positions":positions,"normals":normals,"indices":indices}
	if name=="tissue" and _debug_mode==2:
		# Deindex only this debug rendering, so each face has its EXACT own area color.
		# The authoritative indexed mesh above retains all source IDs and faces.
		var flat_p := PackedVector3Array()
		var flat_n := PackedVector3Array()
		var flat_c := PackedColorArray()
		flat_p.resize(indices.size())
		flat_n.resize(indices.size())
		flat_c.resize(indices.size())
		for k in range(0,indices.size(),3):
			var ratio: float = (positions[indices[k+2]]-positions[indices[k]]).cross(positions[indices[k+1]]-positions[indices[k]]).length()/(2*data["reference_areas"][k/3])
			var color := _heat_area(ratio)
			for corner in 3:
				flat_p[k+corner] = positions[indices[k+corner]]
				flat_n[k+corner] = normals[indices[k+corner]]
				flat_c[k+corner] = color
		_area_mesh.mesh = _mesh_arrays(flat_p,flat_n,PackedInt32Array(),flat_c)

func _refresh() -> void:
	_refresh_queued = false
	if _cavity_data.is_empty():
		return
	_render_one("cavity",_mesh_node,_cavity_data)
	_render_one("tissue",_tissue_node,_tissue_data)
	_tissue_node.visible = _show_tissue and _debug_mode!=2
	_area_mesh.visible = _show_tissue and _debug_mode==2
	_reference_wire.visible = _show_reference
	if _fill_slider != null:
		_fill_slider.set_value_no_signal(_fill)
	if _trial_choice != null:
		_trial_choice.select(0 if _use_after else 1)
	if _mode_choice != null:
		_mode_choice.select(_debug_mode)
	_update_section()
	_update_label()

func _set_fill_r2(value: float) -> void:
	_fill = clampf(value,0,1)
	if not _refresh_queued and not _validating:
		_refresh_queued = true
		call_deferred("_refresh")

func _choose_trial(index: int) -> void:
	_use_after = index==0
	_refresh()

func _choose_debug(index: int) -> void:
	_debug_mode = index
	_refresh()

func _visibility(enabled: bool,node: MeshInstance3D) -> void:
	if node==_tissue_node:
		_show_tissue = enabled
		_tissue_node.visible = enabled and _debug_mode!=2
		_area_mesh.visible = enabled and _debug_mode==2
	else:
		node.visible = enabled

func _toggle_reference(enabled: bool) -> void:
	_show_reference = enabled
	_reference_wire.visible = enabled

func _create_audit_ui() -> void:
	super._create_audit_ui()
	var canvas := CanvasLayer.new()
	add_child(canvas)
	var panel := PanelContainer.new()
	panel.position = Vector2(880,16)
	canvas.add_child(panel)
	var column := VBoxContainer.new()
	panel.add_child(column)
	_state_info = Label.new()
	_state_info.custom_minimum_size = Vector2(350,0)
	_state_info.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(_state_info)
	var row := HBoxContainer.new()
	column.add_child(row)
	for i in 3:
		var button := Button.new()
		button.text = ["Reference","Mid","Expanded"][i]
		button.pressed.connect(_set_fill_r2.bind([0.0,0.5,1.0][i]))
		row.add_child(button)
	_fill_slider = HSlider.new()
	_fill_slider.min_value = 0
	_fill_slider.max_value = 1
	_fill_slider.step = 0.001
	_fill_slider.value_changed.connect(_set_fill_r2)
	column.add_child(_fill_slider)
	var trial := OptionButton.new()
	_trial_choice = trial
	trial.add_item("R2 局部修复后")
	trial.add_item("R1 修复前研究基准")
	trial.item_selected.connect(_choose_trial)
	column.add_child(trial)
	var modes := OptionButton.new()
	_mode_choice = modes
	for title in ["普通表面","组织边位移梯度：蓝0 → 红0.2+","组织面面积比：红0.8 → 绿1 → 蓝1.35"]:
		modes.add_item(title)
	modes.item_selected.connect(_choose_debug)
	column.add_child(modes)
	var wire := CheckButton.new()
	wire.text = "参考态线框（穿透标注）"
	wire.button_pressed = true
	wire.toggled.connect(_toggle_reference)
	column.add_child(wire)
	row = HBoxContainer.new()
	column.add_child(row)
	for i in 4:
		var button := Button.new()
		button.text = "F0%d" % [i+1]
		button.pressed.connect(_focus_region.bind(i))
		row.add_child(button)

func _build_reference_wire(faces: PackedInt32Array) -> void:
	var mesh := ImmediateMesh.new()
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.no_depth_test = true
	material.albedo_color = Color(0.98,0.95,0.12)
	mesh.surface_begin(Mesh.PRIMITIVE_LINES,material)
	var indices: PackedInt32Array = _tissue_data["indices"]
	for face in faces:
		for edge in [[0,1],[1,2],[2,0]]:
			mesh.surface_add_vertex(_tissue_data["vertices"][indices[face*3+int(edge[0])]])
			mesh.surface_add_vertex(_tissue_data["vertices"][indices[face*3+int(edge[1])]])
	mesh.surface_end()
	_reference_wire.mesh = mesh

func _focus_region(index: int) -> void:
	var group: Dictionary = _meta["groups"][index]
	_center = _vec(group["center_mm"])-_vec(_meta["preview_origin_mm"])
	var normal := _vec(group["view_normal"]).normalized()
	_yaw = atan2(normal.x,normal.z)
	_pitch = asin(clampf(normal.y,-0.95,0.95))
	_distance = 4.0 if index<2 else 10.0
	_focus_name = str(group["id"])
	_section_enabled = true
	_section_normal = normal
	_section_offset = _center.dot(normal)+0.5
	_section_toggle.set_pressed_no_signal(true)
	_reference_face_ids = PackedInt32Array(group["reference_faces"])
	_build_reference_wire(_reference_face_ids)
	_update_camera()
	_update_section()

func _focus(name: String) -> void:
	super._focus(name)
	if _reference_wire != null and not _tissue_data.is_empty():
		var faces := PackedInt32Array()
		for i in range(0,_tissue_data["indices"].size()/3,200):
			faces.append(i)
		_build_reference_wire(faces)

func _update_label() -> void:
	if _label==null:
		return
	_label.text = "P1.5-R2 · 研究试验／未验收 · %s\n腔体保持已验收0.2 mm驱动，位移不放大\nR1=修复前；R2=局部约束分级修复\n三态与滑块同步更新腔体、组织\n黄色参考线穿透显示，仅作原位对照\n剖切无封口；不表示壁厚\n左键旋转 · 中键平移 · 滚轮缩放 · R 全局" % [_focus_name]
	if _state_info != null:
		var status := "工程门禁通过，待人工验收" if str(_meta["status"])=="ENGINEERING_GATES_PASSED_PENDING_HUMAN_ACCEPTANCE" else "研究试验，尚未通过完整检查"
		if not _use_after:
			status = "R1失败基准，仅用于诊断对比"
		_state_info.text = "%s · u=%.3f\n%s\n供体归属未确认点仍保留未确认标记" % ["R2 修复后" if _use_after else "R1 修复前",_fill,status]
		if _last_geometry.has("tissue"):
			var p: PackedVector3Array = _last_geometry["tissue"]["positions"]
			var field: PackedVector3Array = _tissue_data["after"] if _use_after else _tissue_data["before"]
			var g: float = _fill*(field[34757]-field[34758]).length()/(_tissue_data["vertices"][34757]-_tissue_data["vertices"][34758]).length()
			var f: PackedInt32Array = _tissue_data["indices"]
			var k := 53208*3
			var ratio: float = (p[f[k+2]]-p[f[k]]).cross(p[f[k+1]]-p[f[k]]).length()/(2*_tissue_data["reference_areas"][53208])
			_state_info.text += "\nF01 梯度 %.6f（门禁≤0.2）\nF02 面积比 %.6f（0.8～1.35）" % [g,ratio]

func _capture_r2(directory: String) -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(directory))
	_debug_mode = 0
	for use_after in [false,true]:
		_use_after = use_after
		for u in [0.0,0.25,0.5,0.75,1.0]:
			_fill = u
			_refresh()
			for name in ["cavity","tissue"]:
				var node := _mesh_node if name=="cavity" else _tissue_node
				var arrays: Array = (node.mesh as ArrayMesh).surface_get_arrays(0)
				var p: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
				var n: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
				var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
				var data := _cavity_data if name=="cavity" else _tissue_data
				var file := FileAccess.open(directory.path_join("%s_%s_u%03d.bin" % ["after" if use_after else "before",name,int(u*100)]),FileAccess.WRITE)
				file.store_buffer(p.to_byte_array())
				file.store_buffer(n.to_byte_array())
				file.store_buffer(indices.to_byte_array())
				file.close()
				_capture_checks.append({"mesh":name,"after":use_after,"fill":u,"vertices":p.size(),"triangles":indices.size()/3,"indices_exact":indices==data["indices"]})
	for focus in 4:
		_focus_region(focus)
		var camera := (get_node("PreviewCamera") as Camera3D).transform
		for mode in ([0,1,2] if focus<2 else [0,1]):
			_debug_mode = mode
			for use_after in [false,true]:
				_use_after = use_after
				_fill = 1.0
				_refresh()
				await _write_screenshot(directory.path_join("F0%d_%s_mode%d.png" % [focus+1,"after" if use_after else "before",mode]))
				if (get_node("PreviewCamera") as Camera3D).transform!=camera:
					_fail("同镜头对比失败。")
					return
		_debug_mode = 0
		_use_after = true
		for u in [0.0,0.5,1.0]:
			_fill = u
			_refresh()
			if (get_node("PreviewCamera") as Camera3D).transform!=camera:
				_fail("三态同镜头检查失败。")
				return
			await _write_screenshot(directory.path_join("F0%d_state_u%03d.png" % [focus+1,int(u*100)]))
	_focus("ALL")
	_section_enabled = true
	_section_normal = Vector3.RIGHT
	_section_offset = 0
	_use_after = true
	_fill = 1
	_debug_mode = 0
	_refresh()
	await _write_screenshot(directory.path_join("joint_expanded_section.png"))
	_section_enabled = false
	_toggle_reference(false)
	_update_section()
	await _write_screenshot(directory.path_join("joint_expanded_solid.png"))
	var file := FileAccess.open(directory.path_join("runtime_checks.json"),FileAccess.WRITE)
	file.store_string(JSON.stringify({"checks":_capture_checks,"camera_unchanged_during_before_after":true,"camera_unchanged_during_states":true,"opaque_shader":true,"reference_origin_mm":[16,16,-81],"research_not_accepted":true},"  "))
	file.close()
	get_tree().quit()
