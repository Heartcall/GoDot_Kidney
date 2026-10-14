extends Node
## Command-line test/measurement harness, never an interactive auto-cycle feature.
var viewer: Control
var directory := ""
var benchmark := false
var tag := ""
var active := false
var phase := ""
var started := 0
var last_tick := 0
var frames: Array = []
var legs: Array = []
var checks: Array = []
var layout_records: Array = []

func _ready() -> void:
	process_priority = 1000
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--p23-benchmark="):
			benchmark = true
			directory = arg.trim_prefix("--p23-benchmark=")
		if arg.begins_with("--p23-regression="):
			directory = arg.trim_prefix("--p23-regression=")
		if arg.begins_with("--p23-tag="):
			tag = arg.trim_prefix("--p23-tag=")
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(directory))
	viewer.controller.automatic_advance = benchmark
	call_deferred("_benchmark" if benchmark else "_regression")

func _process(delta: float) -> void:
	if not active:
		return
	var now := Time.get_ticks_usec()
	frames.append({"phase":phase,"frame":frames.size(),"wall_since_start_s":(now-started)/1000000.0,
		"wall_frame_ms":(now-last_tick)/1000.0,"engine_delta_game_s":delta,"u":viewer.controller.filling,
		"controller_elapsed_game_s":viewer.controller.elapsed,"update_ms":viewer.player.last_update_ms,
		"update_phases_ms":viewer.player.last_phase_ms.duplicate(),"mesh_updates":viewer.player.update_count,
		"state":viewer.controller.state_name(),"sync":viewer.player.filling == viewer.controller.filling})
	last_tick = now
	if not viewer.controller.is_moving():
		active = false
		legs.append({"phase":phase,"wall_seconds":(now-started)/1000000.0,"game_seconds":viewer.controller.elapsed,
			"frames":frames.duplicate(),"end_u":viewer.controller.filling})

func _write(name: String, data: Variant) -> void:
	var file := FileAccess.open(directory.path_join(name),FileAccess.WRITE)
	file.store_string(JSON.stringify(data,"  "))
	file.close()

func _shot(name: String) -> void:
	await RenderingServer.frame_post_draw
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(directory.path_join(name+".png"))

func _benchmark() -> void:
	# Warm up outside the sample interval. No screenshots/readback exports during legs.
	viewer.controller.set_manual_fill(0.5)
	viewer.controller.set_manual_fill(1.0)
	viewer.controller.reset()
	for i in 20:
		await get_tree().process_frame
	var readbacks_before: int = viewer.player.readback_count
	for leg in ["fill","drain"]:
		phase = leg
		frames = []
		viewer.panel.buttons["inject" if leg == "fill" else "drain"].pressed.emit()
		started = Time.get_ticks_usec()
		last_tick = started
		active = true
		while active:
			await get_tree().process_frame
			if (Time.get_ticks_usec()-started)/1000000.0 > 90:
				push_error("Measurement timeout")
				get_tree().quit(1)
				return
		print("P23_MEASURED ",tag," ",leg," wall_s=",legs[-1]["wall_seconds"]," frames=",legs[-1]["frames"].size())
	var result := {"tag":tag,"legs":legs,"renderer":RenderingServer.get_current_rendering_method(),
		"device":RenderingServer.get_video_adapter_name(),"processor":OS.get_processor_name(),"os":OS.get_name(),
		"engine":Engine.get_version_info(),"window_pixels":DisplayServer.window_get_size(),
		"root_viewport_size":get_viewport().get_visible_rect().size,"model_viewport_pixels":viewer.viewport.size,
		"physics_hz":Engine.physics_ticks_per_second,"max_physics_steps_per_frame":Engine.max_physics_steps_per_frame,
		"vsync_mode":DisplayServer.window_get_vsync_mode(),"engine_max_fps":Engine.max_fps,"time_scale":Engine.time_scale,
		"window_focused_at_end":DisplayServer.window_is_focused(),"readbacks_during_measured_legs":viewer.player.readback_count-readbacks_before,
		"player_code_sha256":FileAccess.get_sha256(viewer.player.get_script().resource_path),
		"panel_code_sha256":FileAccess.get_sha256("res://scripts/p2/irrigation_panel.gd"),
		"controller_code_sha256":FileAccess.get_sha256("res://scripts/p2/irrigation_controller.gd"),
		"scene_sha256":FileAccess.get_sha256("res://irrigation_control_preview.tscn"),
		"method":"One actual _process-driven 6-game-second fill and drain. Monotonic wall timestamps at a late process-priority callback; CPU+previous render interval. No forced advance, screenshot or export readback in sampled legs. First/last intervals retained. Warmup: three poses and 20 idle frames. Not P2.4 three-cycle feature or final P2.5 certification."}
	_write("continuous_raw.json",result)
	await _shot("completed")
	get_tree().quit()

func check(label: String, passed: bool) -> void:
	checks.append({"name":label,"passed":passed})
	if not passed:
		push_error(label)

func _regression() -> void:
	var c: Node = viewer.controller
	var p: Node = viewer.panel
	var player: Node = viewer.player
	p.buttons["reset"].pressed.emit()
	check("initial reset reference",c.state_name()=="REFERENCE" and c.filling==0.0)
	p.buttons["inject"].pressed.emit()
	c.advance(1.5)
	check("UI injection unique u",c.filling==0.15625 and player.filling==c.filling)
	check("automatic slider reflection does not take over",p.manual_input_events==0 and c.state_name()=="FILLING")
	var u: float = c.filling
	var duration: float = c.duration
	var end: float = c._end
	p.target_input.value = 60.0
	p.fill_time_input.value = 8.0
	p.drain_time_input.value = 4.0
	check("parameter edits keep active geometry and segment",c.filling==u and c.duration==duration and c._end==end)
	check("new parameters stored separately",c.target_filling==0.6 and c.fill_seconds==8.0 and c.drain_seconds==4.0)
	check("invalid parameters rejected",not p.apply_parameters(NAN,6.0,6.0) and not p.apply_parameters(.5,0.0,6.0))
	check("rejected parameters have no hidden movement",c.filling==u and c._end==end)
	p.buttons["pause"].pressed.emit()
	var count: int = player.update_count
	c.advance(2.0)
	check("UI pause freezes without mesh submissions",c.paused and c.filling==u and player.update_count==count)
	p.buttons["pause"].pressed.emit()
	c.advance(c.remaining_seconds())
	check("UI continue completes original target",c.filling==1.0 and c.state_name()=="HOLDING")
	p.buttons["drain"].pressed.emit()
	check("next drain uses edited duration",c.duration==4.0)
	c.advance(1.0)
	u = c.filling
	p.buttons["hold"].pressed.emit()
	c.advance(20.0)
	check("UI hold cancels movement",c.state_name()=="HOLDING" and c.filling==u and not c.paused)
	p.fill_slider.value = 0.4
	check("manual slider owns controller not mesh",c.filling==0.4 and c.state_name()=="HOLDING" and player.filling==c.filling)
	p.buttons["inject"].pressed.emit()
	check("next injection uses target and proportional duration",is_equal_approx(c.duration,1.6) and c._end==0.6)
	c.advance(0.5)
	u = c.filling
	p.buttons["drain"].pressed.emit()
	check("UI reverse position continuous",c.filling==u)
	count = player.update_count
	for name in viewer.locations:
		var old_state: int = c.state
		viewer.focus(name)
		check("focus only observation "+name,c.filling==u and c.state==old_state and player.update_count==count)
	viewer.focus("F01")
	var local_normal: Vector3 = viewer.section_normal
	p.section_slider.value += 0.1
	check("local section offset preserves local direction",viewer.section_normal==local_normal and player.update_count==count)
	check("target label distinguishes active and next segment",p.state_label.text.contains("下次目标") and p.state_label.text.contains("本段目标"))
	viewer.reset_camera()
	viewer._section(true,Vector3.RIGHT,0.0)
	p.reflect_section(true,Vector3.RIGHT,0.0)
	for name in ["cavity","tissue"]:
		p.visibility_toggles[name].button_pressed = false
		check("independent hide "+name,not player.nodes[name].visible and player.nodes["tissue" if name=="cavity" else "cavity"].visible)
		p.visibility_toggles[name].button_pressed = true
	check("observation never submits geometry",player.update_count==count)
	p.apply_parameters(1.0,6.0,6.0)
	var camera: Transform3D = viewer.camera.transform
	var sample_index := 0
	for value in [0.0,0.25,0.5,0.75,1.0,0.37,0.0]:
		c.set_manual_fill(value)
		var name := "u%03d" % int(value*100)
		if value==0.0 and sample_index>0:
			name="reset"
		sample_index += 1
		player.export_actual(directory,name)
		check("snapshot synchronous "+name,c.filling==player.filling)
		check("snapshot same camera "+name,viewer.camera.transform==camera)
	check("no repeated filling rebuild",_same_value_no_update())
	# Resolve former scene test hooks without touching their historical results.
	p.buttons["expanded"].pressed.emit()
	check("Expanded button manual hold",c.filling==1.0 and c.state_name()=="HOLDING")
	p.buttons["mid"].pressed.emit()
	check("Mid button manual hold",c.filling==0.5 and c.state_name()=="HOLDING")
	p.buttons["reference"].pressed.emit()
	check("Reference button manual hold",c.filling==0.0 and c.state_name()=="HOLDING")
	p.buttons["reset"].pressed.emit()
	player.export_actual(directory,"restored")
	check("reset controller reference",c.filling==0.0 and c.state_name()=="REFERENCE" and not c.paused)
	for window in [Vector2i(1024,768),Vector2i(1280,720),Vector2i(1422,1066),Vector2i(1920,1080)]:
		DisplayServer.window_set_size(window)
		await get_tree().process_frame
		await get_tree().process_frame
		var rect: Rect2 = viewer.panel.get_global_rect()
		var model: Rect2 = viewer.view.get_global_rect()
		var valid: bool = rect.end.x <= model.position.x+1.0 and model.size.x>100 and model.size.y>100 and p.column.size.x <= p.scroll.size.x+1.0
		check("responsive layout "+str(window),valid)
		layout_records.append({"window":window,"root":viewer.size,"panel":rect,"model":model,"valid":valid,
			"scroll_content_height":p.column.size.y,"scroll_visible_height":p.scroll.size.y})
		await _shot("layout_%dx%d" % [window.x,window.y])
	DisplayServer.window_set_size(Vector2i(1422,1066))
	await get_tree().process_frame
	await get_tree().process_frame
	c.set_manual_fill(1.0)
	p.scroll.scroll_vertical=0
	await _shot("expanded_panel")
	viewer.focus("F01")
	p.scroll.scroll_vertical=9999
	await _shot("F01_focus")
	var failures: Array = checks.filter(func(row: Dictionary):return not row["passed"])
	_write("ui_regression.json",{"checks":checks,"failures":failures,"layout":layout_records,"unique_controller":true,
		"renderer":RenderingServer.get_current_rendering_method(),"readback_count":player.readback_count})
	print("P23_UI_REGRESSION checks=",checks.size()," failures=",failures)
	get_tree().quit(0 if failures.is_empty() else 1)

func _same_value_no_update() -> bool:
	var before: int = viewer.player.update_count
	viewer.player.set_filling(viewer.player.filling)
	return before==viewer.player.update_count
