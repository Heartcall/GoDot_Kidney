extends Node3D
## Minimal P2.1/P2.2 verification UI. No automatic three-cycle showcase.
const Player := preload("res://scripts/p2/deformation_player.gd")
const Controller := preload("res://scripts/p2/irrigation_controller.gd")
var player: Node3D
var controller: Node
var slider: HSlider
var info: Label
var camera: Camera3D
var center := Vector3.ZERO
var yaw := 0.6
var pitch := 0.45
var distance := 215.0
var section_enabled := true
var section_offset := 0.0
var validation := false
var runtime_rows: Array = []
var visibility_toggles := {}

func _ready() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--p2-validation-dir="):
			validation = true
	player = Player.new()
	add_child(player)
	if not player.ready_ok:
		return
	controller = Controller.new()
	controller.automatic_advance = not validation
	add_child(controller)
	controller.filling_changed.connect(player.set_filling)
	camera = get_node("PreviewCamera")
	_create_ui()
	controller.status_changed.connect(_update_label)
	player.geometry_updated.connect(func(_u: float, _ms: float): _update_label())
	_reset_camera()
	_update_label()
	if validation:
		for argument in OS.get_cmdline_user_args():
			if argument.begins_with("--p2-validation-dir="):
				call_deferred("_validate", argument.trim_prefix("--p2-validation-dir="))
	else:
		for argument in OS.get_cmdline_user_args():
			if argument.begins_with("--p2-live-smoke-dir="):
				call_deferred("_live_smoke", argument.trim_prefix("--p2-live-smoke-dir="))

func _button(row: HBoxContainer, title: String, action: Callable) -> void:
	var button := Button.new()
	button.text = title
	button.pressed.connect(action)
	row.add_child(button)

func _create_ui() -> void:
	var canvas := CanvasLayer.new()
	add_child(canvas)
	var panel := PanelContainer.new()
	panel.position = Vector2(16, 16)
	panel.custom_minimum_size.x = 420
	canvas.add_child(panel)
	var column := VBoxContainer.new()
	panel.add_child(column)
	var title := Label.new()
	title.text = "P2.1 + P2.2 最小控制验证\n已验收 R2 几何 · 腔体最大位移 0.2 mm"
	column.add_child(title)
	info = Label.new()
	column.add_child(info)
	var row := HBoxContainer.new()
	column.add_child(row)
	_button(row, "注水", controller.inject)
	_button(row, "保持", controller.hold)
	_button(row, "排水", controller.drain)
	_button(row, "暂停/继续", func(): controller.set_paused(not controller.paused))
	_button(row, "重置", controller.reset)
	slider = HSlider.new()
	slider.min_value = 0.0
	slider.max_value = 1.0
	slider.step = 0.001
	slider.value_changed.connect(controller.set_manual_fill)
	column.add_child(slider)
	row = HBoxContainer.new()
	column.add_child(row)
	for value in [0.0, 0.5, 1.0]:
		_button(row, ["Reference", "Mid", "Expanded"][int(value*2)], controller.set_manual_fill.bind(value))
	row = HBoxContainer.new()
	column.add_child(row)
	for mesh_name: String in ["cavity", "tissue"]:
		var toggle := CheckButton.new()
		toggle.text = "腔体" if mesh_name == "cavity" else "组织"
		toggle.button_pressed = true
		toggle.toggled.connect(_visibility.bind(mesh_name))
		visibility_toggles[mesh_name] = toggle
		row.add_child(toggle)
	var section := CheckButton.new()
	section.text = "不透明 X 剖切（无封口）"
	section.button_pressed = true
	section.toggled.connect(func(enabled: bool):
		section_enabled = enabled
		player.set_section(enabled, Vector3.RIGHT, section_offset))
	column.add_child(section)
	var section_slider := HSlider.new()
	section_slider.min_value = -40.0
	section_slider.max_value = 40.0
	section_slider.step = 0.1
	section_slider.value = 0.0
	section_slider.value_changed.connect(func(value: float):
		section_offset = value
		player.set_section(section_enabled, Vector3.RIGHT, value))
	column.add_child(section_slider)
	var help := Label.new()
	help.text = "左键旋转 · 中键平移 · 滚轮缩放 · R 全局\n滑块接管后进入保持；保持不会自动排水\n6 秒完整行程是演示时间，不是真实流量\n静态碰撞与内镜未接入；无自动循环或录像"
	column.add_child(help)

func _visibility(enabled: bool, mesh_name: String) -> void:
	player.set_mesh_visible(mesh_name, enabled)

func _update_label() -> void:
	if info == null:
		return
	slider.set_value_no_signal(controller.filling)
	info.text = "%s%s · u=%.6f · 目标 %.3f\n演示剩余 %.3f 秒 · 双网格更新 %.1f ms" % [
		controller.state_name(), " / Paused" if controller.paused else "", controller.filling,
		controller.target_filling, controller.remaining_seconds(), player.last_update_ms]

func _update_camera() -> void:
	var offset := Vector3(sin(yaw)*cos(pitch), sin(pitch), cos(yaw)*cos(pitch))*distance
	camera.position = center+offset
	camera.look_at(center, Vector3.UP)

func _reset_camera() -> void:
	var bounds: AABB = player.nodes["cavity"].mesh.get_aabb().merge(player.nodes["tissue"].mesh.get_aabb())
	center = bounds.get_center()
	distance = maxf(bounds.size.x, maxf(bounds.size.y, bounds.size.z))*1.7
	yaw = 0.6
	pitch = 0.45
	_update_camera()

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		if Input.is_mouse_button_pressed(MOUSE_BUTTON_LEFT):
			yaw -= event.relative.x*0.006
			pitch = clampf(pitch+event.relative.y*0.006, -1.45, 1.45)
			_update_camera()
		elif Input.is_mouse_button_pressed(MOUSE_BUTTON_MIDDLE):
			center += (-camera.global_basis.x*event.relative.x+camera.global_basis.y*event.relative.y)*distance*0.001
			_update_camera()
	if event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			distance = maxf(2.0, distance/1.12)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			distance = minf(500.0, distance*1.12)
		_update_camera()
	if event is InputEventKey and event.pressed and event.keycode == KEY_R:
		_reset_camera()

func _screenshot(path: String) -> void:
	await RenderingServer.frame_post_draw
	await RenderingServer.frame_post_draw
	var error := get_viewport().get_texture().get_image().save_png(path)
	if error != OK:
		push_error("Screenshot failed")
		get_tree().quit(1)

func _record_runtime(label: String) -> void:
	runtime_rows.append({"label":label, "state":controller.state_name(), "paused":controller.paused,
		"controller_u":controller.filling, "player_u":player.filling, "remaining_seconds":controller.remaining_seconds(),
		"updates":player.update_count})

func _validate(directory: String) -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(directory))
	var initial_camera := camera.transform
	for u in [0.0, 0.25, 0.5, 0.75, 1.0, 0.37, 0.0]:
		controller.set_manual_fill(u)
		var tag := "u%03d" % int(100*u)
		if u == 0.0 and player.update_count > 1:
			tag = "reset"
		player.export_actual(directory, tag)
		_record_runtime(tag)
		if u in [0.0, 0.5, 1.0]:
			await _screenshot(directory.path_join(tag+".png"))
	var before: int = player.update_count
	player.set_filling(player.filling)
	visibility_toggles["tissue"].button_pressed = false
	var visibility_ok: bool = not player.nodes["tissue"].visible and player.nodes["cavity"].visible
	visibility_toggles["tissue"].button_pressed = true
	visibility_toggles["cavity"].button_pressed = false
	visibility_ok = visibility_ok and player.nodes["tissue"].visible and not player.nodes["cavity"].visible
	visibility_toggles["cavity"].button_pressed = true
	player.set_section(true, Vector3.RIGHT, 1.0)
	player.set_section(true, Vector3.RIGHT, 0.0)
	var no_redundant_update: bool = before == player.update_count
	controller.reset()
	controller.inject()
	controller.advance(1.5)
	_record_runtime("inject_1_5s")
	player.export_actual(directory, "driven")
	await _screenshot(directory.path_join("injecting.png"))
	controller.set_paused(true)
	var paused_before: int = player.update_count
	controller.advance(2.0)
	_record_runtime("paused")
	var pause_no_update: bool = paused_before == player.update_count
	controller.set_paused(false)
	controller.advance(4.5)
	_record_runtime("filled")
	controller.drain()
	controller.advance(3.0)
	_record_runtime("draining_mid")
	controller.advance(3.0)
	_record_runtime("restored")
	player.export_actual(directory, "restored")
	var repeated_restore_exact := true
	# Repeated geometry unit regression, not a user-facing automatic-cycle feature.
	for repeat in 2:
		controller.set_manual_fill(1.0)
		controller.set_manual_fill(0.0)
		for mesh_name: String in ["cavity", "tissue"]:
			var arrays: Array = player.nodes[mesh_name].mesh.surface_get_arrays(0)
			repeated_restore_exact = repeated_restore_exact and arrays[Mesh.ARRAY_VERTEX] == player.data[mesh_name]["reference"]
	player.export_actual(directory, "repeat_restored")
	controller.set_manual_fill(1.0)
	player.set_section(false, Vector3.RIGHT, 0.0)
	await _screenshot(directory.path_join("expanded_solid.png"))
	var timings: Array = player.timing_samples
	var result := {"runtime_rows":runtime_rows, "no_update_without_geometry_change":no_redundant_update,
		"pause_no_mesh_submission":pause_no_update, "camera_unchanged":camera.transform == initial_camera,
		"repeated_actual_mesh_restore_exact":repeated_restore_exact,
		"independent_visibility_ui_verified":visibility_ok,
		"timing_samples":timings, "renderer":RenderingServer.get_current_rendering_method(),
		"device":RenderingServer.get_video_adapter_name(), "scope":"P2.1/P2.2 minimal verification, not P2.4 automated cycle or P2.5 FPS benchmark"}
	var file := FileAccess.open(directory.path_join("runtime_checks.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(result, "  "))
	file.close()
	print("P2_GRAPHICAL_VALIDATION ", JSON.stringify(result))
	get_tree().quit()

func _live_smoke(directory: String) -> void:
	# Test hook only, not an interactive automatic-cycle feature or recording.
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(directory))
	var began := Time.get_ticks_usec()
	var sync_ok := true
	var observed: Array = []
	controller.inject()
	await get_tree().create_timer(1.0).timeout
	controller.set_paused(true)
	var pause_u: float = controller.filling
	var pause_updates: int = player.update_count
	await get_tree().create_timer(0.3).timeout
	var pause_ok: bool = controller.filling == pause_u and player.update_count == pause_updates
	await _screenshot(directory.path_join("live_paused.png"))
	controller.set_paused(false)
	for phase in ["fill", "drain"]:
		if phase == "drain":
			controller.drain()
		while controller.is_moving():
			await get_tree().process_frame
			sync_ok = sync_ok and controller.filling == player.filling
			observed.append({"phase":phase,"u":controller.filling,"player_u":player.filling,"remaining":controller.remaining_seconds()})
			if (Time.get_ticks_usec()-began)/1000000.0 > 90.0:
				push_error("Live playback did not complete")
				get_tree().quit(1)
				return
		await _screenshot(directory.path_join("live_"+phase+"_completed.png"))
	player.export_actual(directory, "live_restored")
	var result := {"passed":sync_ok and pause_ok and controller.filling == 0.0 and controller.state_name() == "RESTORED",
		"automatic_process_used":true,"pause_u_stable_and_no_mesh_update":pause_ok,"all_observed_meshes_sync":sync_ok,
		"wall_seconds":(Time.get_ticks_usec()-began)/1000000.0,"observations":observed,
		"timing_samples":player.timing_samples,"scope":"One real-process smoke test, not P2.4 three-cycle implementation or FPS/P95 benchmark"}
	var file := FileAccess.open(directory.path_join("live_smoke.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(result,"  "))
	file.close()
	print("P2_LIVE_SMOKE passed=",result["passed"]," wall_seconds=",result["wall_seconds"])
	get_tree().quit(0 if result["passed"] else 1)
