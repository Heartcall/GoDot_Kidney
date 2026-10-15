extends Node3D
## GPU imported blend shapes only. Independent of P2 and original collisions.
const ASSET = preload("res://visual_demo/assets/kidney_visual_DRAFT.glb")
var cavity: MeshInstance3D
var tissue: MeshInstance3D
var camera: Camera3D
var tissue_material: StandardMaterial3D
var state_label: Label
var slider: HSlider
var status := 0.0
var playing := false
var clock := 0.0
var yaw := 0.0
var pitch := 0.15
var distance := 0.21
var target := Vector3.ZERO
var ci := -1
var ei := -1
var frame_ms: Array[float] = []
var test_mode := false
var manual_seek := false

func _ready() -> void:
	var asset := ASSET.instantiate()
	add_child(asset)
	for n in asset.find_children("*", "MeshInstance3D", true, false):
		if n.name.begins_with("KidneyCavity"): cavity = n
		elif n.name.begins_with("TissueReference"): tissue = n
	if cavity == null or tissue == null:
		push_error("V-Demo imported meshes missing"); get_tree().quit(1); return
	ci = cavity.find_blend_shape_by_name("Contracted")
	ei = cavity.find_blend_shape_by_name("Expanded")
	if ci != 0 or ei != 1 or cavity.get_blend_shape_count() != 2:
		push_error("V-Demo requires ordered Contracted / Expanded blend shapes"); get_tree().quit(1); return
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.10, 0.58, 0.92)
	mat.roughness = 0.6
	cavity.material_override = mat
	tissue_material = StandardMaterial3D.new()
	tissue_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	tissue_material.albedo_color = Color(0.8, 0.32, 0.30, 0.12)
	tissue_material.roughness = 0.85
	tissue.material_override = tissue_material
	tissue.visible = false
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-35,-25,0); light.light_energy = 1.5; add_child(light)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(30,160,0); fill.light_energy = 0.7; add_child(fill)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color(0.035,0.05,0.075)
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color.WHITE
	env.environment.ambient_light_energy = 0.45
	add_child(env)
	camera = Camera3D.new(); camera.near = 0.0001; camera.far = 10.0; camera.fov = 42; add_child(camera)
	camera.current = true; _camera_update(); _ui(); set_state(-1.0)
	test_mode = "--vd-test" in OS.get_cmdline_user_args()
	if test_mode: call_deferred("_test")

func _ui() -> void:
	var layer := CanvasLayer.new(); add_child(layer)
	var panel := PanelContainer.new(); panel.position = Vector2(16,16); panel.custom_minimum_size = Vector2(300,0); layer.add_child(panel)
	var box := VBoxContainer.new(); panel.add_child(box)
	var title := Label.new(); title.text = "肾腔注排水 · Shape Keys"; box.add_child(title)
	var warning := Label.new(); warning.text = "视觉演示 / 非生理标定\nDRAFT_TEST_ONLY · 等待人工塑形"; box.add_child(warning)
	state_label = Label.new(); box.add_child(state_label)
	var row := HBoxContainer.new(); box.add_child(row)
	_button(row,"播放 / 暂停",_toggle_play)
	_button(row,"重置",func(): playing = false; manual_seek = false; clock = 0.0; set_state(-1.0))
	slider = HSlider.new(); slider.min_value = -1; slider.max_value = 1; slider.step = 0.001; slider.custom_minimum_size.x = 290; box.add_child(slider)
	slider.value_changed.connect(_manual_state)
	row = HBoxContainer.new(); box.add_child(row)
	_button(row,"收缩",func(): _manual_state(-1.0))
	_button(row,"Reference",func(): _manual_state(0.0))
	_button(row,"扩张",func(): _manual_state(1.0))
	var toggle := CheckButton.new(); toggle.text = "静态组织（透明参考）"; box.add_child(toggle)
	toggle.toggled.connect(func(v: bool): tissue.visible = v)
	var alpha := HSlider.new(); alpha.min_value = 0.03; alpha.max_value = 0.6; alpha.value = 0.12; alpha.step = 0.01; box.add_child(alpha)
	alpha.value_changed.connect(func(v: float): tissue_material.albedo_color.a = v)
	_button(box,"恢复镜头",func(): yaw = 0; pitch = 0.15; distance = 0.21; target = Vector3.ZERO; _camera_update())
	var hint := Label.new(); hint.text = "右键拖动旋转 · 中键平移 · 滚轮缩放\n组织保持静态；占位幅度很小，非最终效果"; box.add_child(hint)

func _button(parent: Control, text: String, action: Callable) -> void:
	var b := Button.new(); b.text = text; b.pressed.connect(action); parent.add_child(b)

func _manual_state(value: float) -> void:
	playing = false; manual_seek = true; set_state(value)

func _toggle_play() -> void:
	if not playing and manual_seek:
		# Resume a manually selected pose on the filling half without a jump.
		var t := status+1.0 if status<0 else status
		var lo := 0.0; var hi := 1.0
		for k in 24:
			var mid := (lo+hi)*0.5
			if smoothstep(0.0,1.0,mid)<t: lo = mid
			else: hi = mid
		clock = (2.0 if status<0 else 6.0)+4.0*(lo+hi)*0.5
		manual_seek = false
	playing = not playing

func set_state(value: float) -> void:
	status = clampf(value,-1,1)
	cavity.set_blend_shape_value(ci,maxf(-status,0))
	cavity.set_blend_shape_value(ei,maxf(status,0))
	if slider != null: slider.set_value_no_signal(status)
	if state_label != null:
		state_label.text = ("原始参考态" if absf(status)<0.001 else ("排水 · 收缩" if status<0 else "注水 · 扩张")) + "  s=%.2f" % status

func _process(delta: float) -> void:
	if test_mode: frame_ms.append(delta*1000.0)
	if not playing: return
	clock = fmod(clock+delta,20.0)
	if clock<2: set_state(-1)
	elif clock<6: set_state(lerpf(-1,0,smoothstep(2,6,clock)))
	elif clock<10: set_state(smoothstep(6,10,clock))
	elif clock<12: set_state(1)
	elif clock<16: set_state(lerpf(1,0,smoothstep(12,16,clock)))
	else: set_state(-smoothstep(16,20,clock))

func _camera_update() -> void:
	camera.position = target+distance*Vector3(sin(yaw)*cos(pitch),sin(pitch),-cos(yaw)*cos(pitch))
	camera.look_at(target,Vector3.UP)

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		if Input.is_mouse_button_pressed(MOUSE_BUTTON_RIGHT):
			yaw -= event.relative.x*0.008; pitch = clampf(pitch+event.relative.y*0.008,-1.4,1.4); _camera_update()
		elif Input.is_mouse_button_pressed(MOUSE_BUTTON_MIDDLE):
			target += (-camera.global_basis.x*event.relative.x+camera.global_basis.y*event.relative.y)*distance*0.001; _camera_update()
	elif event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP: distance = maxf(distance*0.9,0.01); _camera_update()
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN: distance *= 1.1; _camera_update()

func _test() -> void:
	var rows: Array = []
	for value: float in [-1.0,-0.5,0.0,0.5,1.0]:
		set_state(value); await get_tree().process_frame; await get_tree().process_frame
		var baked := cavity.bake_mesh_from_current_blend_shape_mix()
		var arrays := baked.surface_get_arrays(0)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
		var normals_finite := true
		for normal in normals:
			if not normal.is_finite(): normals_finite = false
		var packed := PackedFloat32Array(); packed.resize(vertices.size()*3)
		for i in vertices.size():
			var p := cavity.global_transform*vertices[i]; packed[3*i] = p.x; packed[3*i+1] = p.y; packed[3*i+2] = p.z
		var file := FileAccess.open("res://../visual_demo/reports/godot_state_%s.bin" % str(value),FileAccess.WRITE)
		file.store_buffer(packed.to_byte_array()); file.close()
		rows.append({"s":value,"vertices":vertices.size(),"triangles":arrays[Mesh.ARRAY_INDEX].size()/3,"normals_finite":normals_finite,"contracted":cavity.get_blend_shape_value(ci),"expanded":cavity.get_blend_shape_value(ei)})
		if value == 1.0:
			await RenderingServer.frame_post_draw
			get_viewport().get_texture().get_image().save_png("res://../visual_demo/reports/godot_draft.png")
	clock = 0; playing = true; frame_ms.clear()
	await get_tree().create_timer(4.0).timeout
	tissue.visible = true
	await get_tree().create_timer(3.0).timeout
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png("res://../visual_demo/reports/godot_tissue.png")
	frame_ms.sort()
	var total := 0.0
	for x in frame_ms: total += x
	var report := {"version":Engine.get_version_info(),"renderer":RenderingServer.get_current_rendering_method(),"device":RenderingServer.get_video_adapter_name(),
		"blend_shapes":[cavity.mesh.get_blend_shape_name(0),cavity.mesh.get_blend_shape_name(1)],"samples":rows,"frames":frame_ms.size(),
		"fps_mean":1000.0*frame_ms.size()/total,"frame_ms_median":frame_ms[frame_ms.size()/2],"frame_ms_p95":frame_ms[int(frame_ms.size()*0.95)],
		"resolution":[get_viewport().size.x,get_viewport().size.y],"scope":"7 s draft continuous playback; transparency included; not final performance certification"}
	var result := FileAccess.open("res://../visual_demo/reports/godot_runtime.json",FileAccess.WRITE); result.store_string(JSON.stringify(report,"  ")); result.close()
	result = FileAccess.open("res://../visual_demo/reports/godot_runtime_%s.json" % RenderingServer.get_current_rendering_method(),FileAccess.WRITE); result.store_string(JSON.stringify(report,"  ")); result.close()
	print("V_DEMO_RUNTIME ",JSON.stringify(report)); get_tree().quit()
