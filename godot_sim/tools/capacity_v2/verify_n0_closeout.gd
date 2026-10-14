extends Node
var viewer: Control
var output := ""
var checks: Array = []
var captures: Array = []

func _ready() -> void: call_deferred("run")

func check(name: String,condition: bool) -> void:
	checks.append({"name":name,"passed":condition})
	if not condition: push_error(name)

func choose(id: String) -> void:
	for i in viewer.candidates.item_count:
		if viewer.meta["candidates"][i]["id"]==id:
			viewer.candidates.select(i); viewer._load_candidate(i); return
	check("candidate exists "+id,false)

func capture(tag: String) -> void:
	(viewer.panel.get_child(0) as ScrollContainer).scroll_vertical = 0
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	var code := viewer.get_viewport().get_texture().get_image().save_png(ProjectSettings.globalize_path(output.path_join(tag+".png")))
	check("screenshot "+tag,code==OK); captures.append({"tag":tag,"state":viewer.review_state()})

func run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output)); await get_tree().process_frame
	check("closeout loaded",viewer.closeout_loaded)
	choose("C11_inlet_distal_control"); viewer.mode.select(2); viewer._mode_changed(2); viewer.section_check.button_pressed = false; viewer._apply_section(); viewer.reset_camera()
	check("C11 limited approval displayed",viewer.status.text.contains("VISUAL_REVIEW_PASSED_D2_PENDING")); await capture("C11_visual_pass_D2_pending")
	var same_view: Vector3 = viewer.camera.position
	choose("C06_near_BASE"); check("C06 user rejected displayed",viewer.status.text.contains("REJECTED_BY_USER_NATURAL_WALL_REMOVAL")); check("candidate switch same camera",viewer.camera.position==same_view); await capture("C06_user_rejected")
	for id: String in ["C07_IN01_collar","C08_IN02_collar","C09_UPJ_proximal_unconfirmed","C10_UPJ_distal_unconfirmed"]:
		choose(id); check(id+" not falsely user reviewed",viewer.status.text.contains("NOT_INDIVIDUALLY_REVIEWED"))
	choose("C11_R1_IN02_fixed_collar"); check("R1 geometry gate passed",viewer.meta["candidates"][viewer.candidates.selected]["geometry_valid"]); check("R1 pending approval displayed",viewer.status.text.contains("待人工确认")); check("caps remain separate",viewer.extras["caps"].mesh!=viewer.player.nodes["cavity"].mesh); await capture("R1_measurement_candidate")
	choose("C11_inlet_distal_control"); viewer.focus_collar(); var collar_camera: Vector3 = viewer.camera.position
	check("no coincident green overlay on C11",not viewer.extras["collar"].visible); await capture("C11_collar_side")
	choose("C11_R1_IN02_fixed_collar"); check("same collar camera",viewer.camera.position==collar_camera); check("removed collar visible independently",viewer.extras["collar"].visible); await capture("R1_removed_fixed_collar_side")
	viewer.mode.select(3); viewer._mode_changed(3); viewer.cavity_check.button_pressed = true; viewer.tissue_check.button_pressed = true; viewer._visibility()
	check("contact feedback limited to reviewed views",viewer.status.text.contains("用户本次审核视角未见异常")); check("virtual caps hidden during contact review",not viewer.extras["caps"].visible)
	viewer.focus("J_09")
	for value in [0.,.25,.5,.75,1.,.37]:
		viewer.set_u(value); viewer.player.export_actual(output,"u%03d" % roundi(value*100)); check("accepted player u "+str(value),viewer.player.filling==value)
		if value==0 or value==1: await capture("accepted_J09_u%03d" % roundi(value*100))
	viewer.set_u(0.); viewer.player.export_actual(output,"restored"); await viewer.save_review()
	var failed := 0
	for row: Dictionary in checks:
		if not row["passed"]: failed+=1
	var file := FileAccess.open(output.path_join("runtime_checks.json"),FileAccess.WRITE)
	file.store_string(JSON.stringify({"checks":checks,"failures":failed,"captures":captures,"renderer":RenderingServer.get_current_rendering_method(),"adapter":RenderingServer.get_video_adapter_name()},"\t")); file.close()
	print("N0 closeout graphics checks ",checks.size()," failures ",failed); get_tree().quit(0 if failed==0 else 1)
