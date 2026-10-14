extends Control
## Read-only N0 review. Virtual caps NEVER enter the accepted P2 player.
const ROOT := "res://deformation/capacity_v2_n0_research"
const Player := preload("res://scripts/p2/deformation_player.gd")
const SECTION_SHADER := preload("res://shaders/audit_section.gdshader")
const ORIGIN := Vector3(16,16,-81)
var meta: Dictionary
var player: Node3D
var extras := {}
var extra_materials: Array[ShaderMaterial] = []
var center := Vector3.ZERO
var yaw := 0.6
var pitch := 0.45
var distance := 215.0
var section_normal := Vector3.RIGHT
var section_offset := 0.0
var selected_pair := {}
var box: VBoxContainer
var mode: OptionButton
var candidates: OptionButton
var focus_choice: OptionButton
var pair_choice: OptionButton
var slider: HSlider
var status: Label
var pair_info: Label
var saved_info: Label
var cavity_check: CheckBox
var tissue_check: CheckBox
var cap_check: CheckBox
var excluded_check: CheckBox
var cuts_check: CheckBox
var reference_check: CheckBox
var section_check: CheckBox
var section_axis: OptionButton
var section_slider: HSlider
var face_cavity: SpinBox
var face_tissue: SpinBox
var point_inputs: Array[SpinBox] = []
@onready var panel: PanelContainer = $Layout/Panel
@onready var view: SubViewportContainer = $Layout/View
@onready var world: Node3D = $Layout/View/Viewport/World
@onready var camera: Camera3D = $Layout/View/Viewport/World/PreviewCamera

func _ready() -> void:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(ROOT.path_join("review_preview.json")))
	if not parsed is Dictionary or parsed.get("schema") != "CAPACITY_V2_N0_REVIEW_V1":
		push_error("N0 review metadata missing"); get_tree().quit(1); return
	meta = parsed
	if FileAccess.get_sha256("res://deformation/p2/accepted_inputs.json") != meta["p2_manifest_sha256"]:
		push_error("Accepted P2 manifest changed"); get_tree().quit(1); return
	player = Player.new()
	world.add_child(player)
	if not player.ready_ok: return
	for key: String in ["wall", "caps", "excluded", "cut_lines", "pair_lines", "reference_lines"]:
		var node := MeshInstance3D.new(); node.name = key; world.add_child(node); extras[key] = node
	_build_ui()
	view.gui_input.connect(_view_input)
	resized.connect(func(): panel.custom_minimum_size.x = clampf(size.x*0.29,300.0,390.0))
	panel.custom_minimum_size.x = clampf(size.x*0.29,300.0,390.0)
	for i in candidates.item_count:
		if str(meta["candidates"][i]["id"]) == "C11_inlet_distal_control": candidates.select(i)
	_load_candidate(candidates.selected)
	mode.select(2); _mode_changed(2); reset_camera()
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--n0-verify="):
			var runner = load("res://tools/capacity_v2/n0_verify.gd").new()
			runner.viewer = self; runner.output = arg.trim_prefix("--n0-verify="); add_child(runner)

func _label(text: String) -> Label:
	var node := Label.new(); node.text = text; node.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(node); return node

func _button(text: String, action: Callable) -> Button:
	var node := Button.new(); node.text = text; node.pressed.connect(action); box.add_child(node); return node

func _check(text: String, checked: bool, action: Callable) -> CheckBox:
	var node := CheckBox.new(); node.text = text; node.button_pressed = checked; node.toggled.connect(action); box.add_child(node); return node

func _spin(minimum: float, maximum: float, step: float) -> SpinBox:
	var node := SpinBox.new(); node.min_value = minimum; node.max_value = maximum; node.step = step; box.add_child(node); return node

func _build_ui() -> void:
	var scroll := ScrollContainer.new(); scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED; panel.add_child(scroll)
	box = VBoxContainer.new(); box.size_flags_horizontal = Control.SIZE_EXPAND_FILL; box.add_theme_constant_override("separation",7); scroll.add_child(box)
	_label("Capacity V2 · N0 审核\n研究候选／未批准，不是新形变")
	_label("D0 含人工结构：19.723077 mL\n天然有效容量：未确定")
	mode = OptionButton.new(); box.add_child(mode)
	for text: String in ["D0 完整计算域", "仅人工排除结构", "候选测量域 D2（未批准）", "接触诊断 · 旧验收工程 u"]: mode.add_item(text)
	mode.item_selected.connect(_mode_changed)
	_label("截面候选（保留失败方案供审查）")
	candidates = OptionButton.new(); candidates.fit_to_longest_item = false; box.add_child(candidates)
	for rec: Dictionary in meta["candidates"]: candidates.add_item(str(rec["id"]))
	candidates.item_selected.connect(_load_candidate)
	status = _label("")
	_label("蓝：源腔壁；粉：组织；金：虚拟封口\n灰：排除结构；彩线：候选截面\n虚拟封口只存在于独立测量节点。")
	cavity_check = _check("显示腔体／候选源壁",true,func(_v): _visibility())
	tissue_check = _check("显示组织（不透明）",false,func(_v): _visibility())
	cap_check = _check("显示虚拟测量封口（金）",true,func(_v): _visibility())
	excluded_check = _check("叠加排除结构（灰）",false,func(_v): _visibility())
	cuts_check = _check("显示三组截面环与平面参考框",true,func(_v): _visibility())
	_label("测量候选只看 Reference。接触模式可调旧 u。")
	slider = HSlider.new(); slider.min_value = 0; slider.max_value = 1; slider.step = 0.001; box.add_child(slider); slider.value_changed.connect(set_u)
	for value in [0.0,0.25,0.5,0.75,1.0]:
		var val: float = value
		_button("旧 u = %.2f" % val,func(): mode.select(3); _mode_changed(3); set_u(val))
	_label("位置定位（不改变旧 u）")
	focus_choice = OptionButton.new(); box.add_child(focus_choice); focus_choice.add_item("ALL")
	var names: Array = meta["locations"].keys(); names.sort()
	for name in names: focus_choice.add_item(str(name))
	focus_choice.item_selected.connect(func(i): focus(focus_choice.get_item_text(i)))
	for index in 3:
		var cut_index: int = index
		_button("定位候选截面 · "+["BLADDER", "IN_01", "IN_02"][index],func(): focus_cut(cut_index))
	_label("自动分类面配对（只提供诊断，不认定解剖）")
	pair_choice = OptionButton.new(); pair_choice.fit_to_longest_item = false; box.add_child(pair_choice)
	for rec: Dictionary in meta["review_pairs"]: pair_choice.add_item(str(rec["region"])+" · u="+str(rec["u"])+" · "+str(rec["class"]))
	pair_choice.item_selected.connect(select_pair)
	pair_info = _label("尚未复现用户指定的视觉异常；可指定面或位置后保存现场。")
	_label("手工面编号：腔体 0～50043／组织 0～311843")
	face_cavity = _spin(0,50043,1); face_tissue = _spin(0,311843,1)
	_button("定位并高亮这两个源三角面",manual_pair)
	reference_check = _check("叠加所选面的 Reference 线（白）",false,func(_v): _draw_pair())
	_label("彩线＝当前面；白线＝Reference。诊断线可透视，不代表可见腔壁。")
	_label("原始 RAS mm 坐标定位：X / Y / Z")
	for value in [16.0,16.0,-81.0]:
		var spin := _spin(-250,250,0.01); spin.value = value; point_inputs.append(spin)
	_button("定位输入坐标",func(): focus_point(Vector3(point_inputs[0].value,point_inputs[1].value,point_inputs[2].value)-ORIGIN,section_normal,16.0))
	section_check = _check("不透明剖切（丢弃半空间，不补正式壁）",false,func(_v): _apply_section())
	section_axis = OptionButton.new(); box.add_child(section_axis)
	for text: String in ["X", "Y", "Z", "定位法向"]: section_axis.add_item(text)
	section_axis.item_selected.connect(func(i):
		if i<3: section_normal = [Vector3.RIGHT,Vector3.UP,Vector3.BACK][i]
		_apply_section())
	section_slider = HSlider.new(); section_slider.min_value = -180; section_slider.max_value = 180; section_slider.step = 0.01; box.add_child(section_slider)
	section_slider.value_changed.connect(func(value): section_offset = value; _apply_section())
	_button("镜头复位",reset_camera)
	_button("保存审核现场 JSON＋真实截图",save_review)
	saved_info = _label("左键旋转／中键平移／滚轮缩放；R 复位。\n保存文件仅写入新的 N0 user_sessions 目录。")

func _read_vectors(file: FileAccess, count: int) -> PackedVector3Array:
	var flat := file.get_buffer(count*12).to_float32_array(); var result := PackedVector3Array(); result.resize(count)
	for i in count: result[i] = Vector3(flat[3*i],flat[3*i+1],flat[3*i+2])
	return result

func _load_mesh(node: MeshInstance3D, path: String, digest: String, color: Color) -> void:
	if FileAccess.get_sha256(path) != digest: push_error("N0 mesh hash mismatch"); get_tree().quit(1); return
	var file := FileAccess.open(path,FileAccess.READ); var magic := file.get_buffer(8).get_string_from_ascii(); var n := int(file.get_32()); var m := int(file.get_32())
	if magic != "N0MS0001" or file.get_length()!=16+24*n+12*m: push_error("Invalid N0 measurement mesh"); get_tree().quit(1); return
	var arrays := []; arrays.resize(Mesh.ARRAY_MAX); arrays[Mesh.ARRAY_VERTEX] = _read_vectors(file,n); arrays[Mesh.ARRAY_NORMAL] = _read_vectors(file,n); arrays[Mesh.ARRAY_INDEX] = file.get_buffer(m*12).to_int32_array(); file.close()
	var colors := PackedColorArray(); colors.resize(n); colors.fill(color); arrays[Mesh.ARRAY_COLOR] = colors
	var mesh := ArrayMesh.new(); mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays); node.mesh = mesh
	var material := ShaderMaterial.new(); material.shader = SECTION_SHADER; node.material_override = material; extra_materials.append(material)

func _load_candidate(index: int) -> void:
	var rec: Dictionary = meta["candidates"][index]; extra_materials.clear()
	for entry: Array in [["wall","original_wall.bin",Color(0.15,0.65,0.95)],["caps","virtual_caps.bin",Color(1.0,0.72,0.05)],["excluded","excluded_structure.bin",Color(0.53,0.57,0.62)]]:
		_load_mesh(extras[entry[0]],ROOT.path_join("domains").path_join(rec["id"]).path_join(entry[1]),rec["output_sha256"][entry[1]],entry[2])
	var vertices: PackedVector3Array = extras["wall"].mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var positions := PackedVector3Array(); var colors := PackedColorArray()
	for i in 3:
		var cut: Dictionary = rec["cuts"][i]; var ring: Array = cut["selected_boundary_vertex_ids"]; var color: Color = [Color(1,.25,.2),Color(.3,1,.3),Color(.5,.6,1)][i]
		for k in ring.size(): _line(positions,colors,vertices[int(ring[k])],vertices[int(ring[(k+1)%ring.size()])],color)
		var c := _vec(cut["center_mm"])-ORIGIN; var normal := _vec(cut["normal_toward_artificial_END"]); var e := normal.cross(Vector3.RIGHT if absf(normal.x)<0.8 else Vector3.UP).normalized(); var b := normal.cross(e)
		var radius := 1.0
		for id in ring: radius = maxf(radius,c.distance_to(vertices[int(id)])*1.1)
		var corners := [c+radius*(e+b),c+radius*(-e+b),c+radius*(-e-b),c+radius*(e-b)]
		for k in 4: _line(positions,colors,corners[k],corners[(k+1)%4],color)
	_set_lines(extras["cut_lines"],positions,colors,false)
	_apply_section(); _visibility(); _status()

func _vec(value: Array) -> Vector3: return Vector3(value[0],value[1],value[2])

func _line(p: PackedVector3Array,c: PackedColorArray,a: Vector3,b: Vector3,color: Color) -> void:
	p.append(a); p.append(b); c.append(color); c.append(color)

func _set_lines(node: MeshInstance3D,p: PackedVector3Array,c: PackedColorArray,xray: bool) -> void:
	if p.is_empty(): node.mesh = null; return
	var arrays := []; arrays.resize(Mesh.ARRAY_MAX); arrays[Mesh.ARRAY_VERTEX] = p; arrays[Mesh.ARRAY_COLOR] = c
	var mesh := ArrayMesh.new(); mesh.add_surface_from_arrays(Mesh.PRIMITIVE_LINES,arrays); node.mesh = mesh
	var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.vertex_color_use_as_albedo = true; material.no_depth_test = xray; node.material_override = material

func _mode_changed(index: int) -> void:
	slider.editable = index==3
	if index!=3: set_u(0.0)
	_visibility(); _status()

func _visibility() -> void:
	if not is_instance_valid(cavity_check): return
	var index := mode.selected
	player.set_mesh_visible("cavity",index in [0,3] and cavity_check.button_pressed)
	player.set_mesh_visible("tissue",index!=1 and tissue_check.button_pressed)
	extras["wall"].visible = index==2 and cavity_check.button_pressed
	extras["caps"].visible = index==2 and cap_check.button_pressed
	extras["excluded"].visible = index==1 or (index==2 and excluded_check.button_pressed)
	extras["cut_lines"].visible = index!=3 and cuts_check.button_pressed
	extras["pair_lines"].visible = index==3
	extras["reference_lines"].visible = index==3 and reference_check.button_pressed

func _status() -> void:
	if not is_instance_valid(status): return
	var rec: Dictionary = meta["candidates"][candidates.selected]
	status.text = "旧工程 u=%.3f\n候选 Reference 测量值 %.6f mL\n几何检查：%s；解剖审核：未批准\n排除天然端点：%s\n排除天然路径：%s\n正式天然有效容量：未确定" % [player.filling,rec["candidate_measurement_volume_mL"],"通过" if rec["geometry_valid"] else "失败",str(rec["excluded_natural_marker_ids"]),str(rec["natural_paths_with_outside_samples"])]
	if not rec["excluded_natural_marker_ids"].is_empty() or not rec["natural_paths_with_outside_samples"].is_empty(): status.text += "\n警告：丢失天然区域，此方案不推荐。"
	if rec["id"]=="C00_distal_control": status.text += "\n远端对照：保留接口过渡，不是完整天然域。"
	if not rec["wide_chamber_cut_warning"].is_empty(): status.text += "\n截面显著宽于管道："+str(rec["wide_chamber_cut_warning"])+"；可能切入宽腔室。"
	if rec["id"]=="C11_inlet_distal_control": status.text += "\n保守对照：仍保留 B_31/B_32 过渡，需审核。"
	if mode.selected==3:
		var volume := 0.0
		for k in 4: volume += float(meta["legacy_volume_polynomial_mm3"][k])*pow(player.filling,k)/1000.0
		status.text = "旧工程 u=%.3f\n完整计算网格体积 %.6f mL（含人工）\n正式天然有效容量：未确定\n当前显示 P2.3 已验收双网格，无虚拟封口。\n具体视觉穿模尚待用户现场定位。" % [player.filling,volume]

func set_u(value: float) -> void:
	if not is_finite(value): return
	player.set_filling(clampf(value,0,1)); slider.set_value_no_signal(player.filling); _draw_pair(); _status()
	if selected_pair.has("class") and absf(player.filling-float(selected_pair["u"]))>0.0000001:
		pair_info.text = "当前仍高亮同一对源面，但缓存分类只适用于 u=%.3f。\n当前 u=%.3f 未重新分类；请保存现场作有限几何复核。" % [selected_pair["u"],player.filling]
	elif selected_pair.has("class"):
		pair_info.text = "%s · 已分类 u=%.3f\n腔体面 %d / 组织面 %d\nRAS mm %s\n有限交线 %.9f mm / 距离 %.9f mm" % [selected_pair["class"],selected_pair["u"],selected_pair["cavity_face"],selected_pair["tissue_face"],str(selected_pair["center_mm"]),selected_pair["finite_segment_length_mm"],selected_pair["finite_feature_gap_mm"]]

func _apply_section() -> void:
	if not is_instance_valid(section_check): return
	player.set_section(section_check.button_pressed,section_normal,section_offset)
	for material in extra_materials:
		material.set_shader_parameter("section_enabled",section_check.button_pressed); material.set_shader_parameter("section_normal",section_normal); material.set_shader_parameter("section_offset",section_offset)

func focus_point(point: Vector3, normal: Vector3, zoom: float) -> void:
	center = point; var n := normal.normalized(); yaw = atan2(n.x,n.z); pitch = asin(clampf(n.y,-.95,.95)); distance = zoom
	section_normal = n; section_offset = center.dot(n)+0.3; section_check.button_pressed = true; section_axis.select(3); section_slider.set_value_no_signal(section_offset); _apply_section(); _update_camera()

func focus(name: String) -> void:
	if name=="ALL": reset_camera(); return
	var rec: Dictionary = meta["locations"][name]; focus_point(_vec(rec["center_mm"])-ORIGIN,_vec(rec["normal"]),rec["distance_mm"])

func focus_cut(index: int) -> void:
	var cut: Dictionary = meta["candidates"][candidates.selected]["cuts"][index]
	var vertices: PackedVector3Array = extras["wall"].mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var c := _vec(cut["center_mm"])-ORIGIN; var radius := 0.0
	for id in cut["selected_boundary_vertex_ids"]: radius = maxf(radius,c.distance_to(vertices[int(id)]))
	focus_point(c,_vec(cut["normal_toward_artificial_END"]),maxf(20.0,radius*3.5))

func select_pair(index: int) -> void:
	var rec: Dictionary = meta["review_pairs"][index]; mode.select(3); _mode_changed(3); selected_pair = rec; set_u(rec["u"])
	face_cavity.value = rec["cavity_face"]; face_tissue.value = rec["tissue_face"]
	var ids: PackedInt32Array = player.data["cavity"]["indices"]; var k := int(rec["cavity_face"])*3
	var n := (_position("cavity",ids[k+2],false)-_position("cavity",ids[k],false)).cross(_position("cavity",ids[k+1],false)-_position("cavity",ids[k],false)).normalized()
	focus_point(_vec(rec["center_mm"])-ORIGIN,n,12.0)
	pair_info.text = "%s\n腔体面 %d / 组织面 %d\nRAS mm %s\n有限交线 %.9f mm / 距离 %.9f mm\n共面配对面积 %.9f mm²（非穿透面积）" % [rec["class"],rec["cavity_face"],rec["tissue_face"],str(rec["center_mm"]),rec["finite_segment_length_mm"],rec["finite_feature_gap_mm"],rec["coplanar_pair_overlap_area_mm2"]]

func manual_pair() -> void:
	mode.select(3); _mode_changed(3); selected_pair = {"cavity_face":int(face_cavity.value),"tissue_face":int(face_tissue.value)}; _draw_pair()
	var p := Vector3.ZERO; var ids: PackedInt32Array = player.data["cavity"]["indices"]
	for i in 3: p += _position("cavity",ids[int(face_cavity.value)*3+i],false)/3.0
	focus_point(p,section_normal,12.0); pair_info.text = "手工指定面；尚未计算有限接触类别。请保存现场供复核。"

func _position(name: String,id: int,reference: bool) -> Vector3:
	var p: Vector3 = player.data[name]["reference"][id]
	if not reference: p += player.filling * (player.data[name]["displacement"][id] as Vector3)
	return p

func _draw_pair() -> void:
	if selected_pair.is_empty(): return
	for reference in [false,true]:
		var p := PackedVector3Array(); var c := PackedColorArray()
		for name: String in ["cavity","tissue"]:
			var face := int(selected_pair[name+"_face"]); var ids: PackedInt32Array = player.data[name]["indices"]; var color := Color.WHITE if reference else (Color(.1,1,1) if name=="cavity" else Color(1,.15,.15))
			for i in 3: _line(p,c,_position(name,ids[face*3+i],reference),_position(name,ids[face*3+(i+1)%3],reference),color)
		_set_lines(extras["reference_lines" if reference else "pair_lines"],p,c,true)
	_visibility()

func _update_camera() -> void:
	camera.position = center+Vector3(sin(yaw)*cos(pitch),sin(pitch),cos(yaw)*cos(pitch))*distance; camera.look_at(center,Vector3.UP)

func reset_camera() -> void:
	var bounds: AABB = player.nodes["cavity"].mesh.get_aabb().merge(player.nodes["tissue"].mesh.get_aabb()); center = bounds.get_center(); distance = maxf(bounds.size.x,maxf(bounds.size.y,bounds.size.z))*1.7; yaw = .6; pitch = .45; _update_camera()
	if mode.selected==2:
		var b: Array = meta["candidates"][candidates.selected]["used_surface_bounds_mm"]; var low := _vec(b[0])-ORIGIN; var high := _vec(b[1])-ORIGIN
		center = (low+high)*.5; var extent := high-low; distance = maxf(extent.x,maxf(extent.y,extent.z))*1.8; _update_camera()

func review_state() -> Dictionary:
	return {"schema":"N0_USER_REVIEW_SESSION_V1","u":player.filling,"candidate":meta["candidates"][candidates.selected]["id"],"mode":mode.selected,
		"camera_display_position_mm":[camera.position.x,camera.position.y,camera.position.z],"camera_rotation_radians":[camera.rotation.x,camera.rotation.y,camera.rotation.z],
		"camera_fov":camera.fov,"focus_display_center_mm":[center.x,center.y,center.z],"distance_mm":distance,"yaw":yaw,"pitch":pitch,
		"section_enabled":section_check.button_pressed,"section_normal":[section_normal.x,section_normal.y,section_normal.z],"section_offset_display_mm":section_offset,
		"section_offset_RAS_mm":section_offset+section_normal.dot(ORIGIN),"selected_pair":selected_pair,"cavity_visible":cavity_check.button_pressed,"tissue_visible":tissue_check.button_pressed,
		"origin_mm":[16,16,-81],"viewport_size":[size.x,size.y],"source_manifest_sha256":meta["p2_manifest_sha256"],"anatomical_approval":"PENDING"}

func save_review() -> void:
	await RenderingServer.frame_post_draw
	var directory := ROOT.path_join("user_sessions"); DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(directory)); var tag := "review_"+str(Time.get_ticks_msec()); var base := directory.path_join(tag)
	var file := FileAccess.open(base+".json",FileAccess.WRITE); file.store_string(JSON.stringify(review_state(),"\t")); file.close()
	get_viewport().get_texture().get_image().save_png(ProjectSettings.globalize_path(base+".png")); saved_info.text = "已保存："+base+".json / .png\n请提供这组文件或文件名以定位原观察。"

func _view_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		if Input.is_mouse_button_pressed(MOUSE_BUTTON_LEFT): yaw -= event.relative.x*.006; pitch = clampf(pitch+event.relative.y*.006,-1.45,1.45); _update_camera()
		elif Input.is_mouse_button_pressed(MOUSE_BUTTON_MIDDLE): center += (-camera.global_basis.x*event.relative.x+camera.global_basis.y*event.relative.y)*distance*.001; _update_camera()
	if event is InputEventMouseButton and event.pressed:
		if event.button_index==MOUSE_BUTTON_WHEEL_UP: distance = maxf(2,distance/1.12)
		elif event.button_index==MOUSE_BUTTON_WHEEL_DOWN: distance = minf(500,distance*1.12)
		_update_camera()

func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and event.keycode==KEY_R: reset_camera()
