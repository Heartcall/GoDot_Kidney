extends Node
## Actual graphics smoke/UI tests and mesh export. No legacy file writes.
var viewer: Control
var output := ""
var checks: Array = []
var captures: Array = []

func _ready() -> void: call_deferred("run")

func check(name: String, condition: bool) -> void:
	checks.append({"name":name,"passed":condition})
	if not condition: push_error("N0 verification failed: "+name)

func capture(tag: String) -> void:
	(viewer.panel.get_child(0) as ScrollContainer).scroll_vertical = 0
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	var path := output.path_join(tag+".png"); var code := viewer.get_viewport().get_texture().get_image().save_png(ProjectSettings.globalize_path(path))
	check("screenshot "+tag,code==OK); captures.append({"tag":tag,"state":viewer.review_state(),"path":path})

func run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output))
	await get_tree().process_frame
	get_window().size = Vector2i(1422,1066)
	await get_tree().process_frame
	check("accepted player ready",viewer.player.ready_ok)
	viewer.mode.select(3); viewer._mode_changed(3); viewer.cavity_check.button_pressed = true; viewer.tissue_check.button_pressed = true; viewer._visibility()
	for value in [0.0,0.25,0.5,0.75,1.0,0.37]:
		viewer.set_u(value); viewer.player.export_actual(output,"u%03d" % roundi(value*100))
		check("both meshes one u "+str(value),viewer.player.filling==value)
		var count: int = viewer.player.update_count; viewer.set_u(value); check("unchanged u no rebuild "+str(value),viewer.player.update_count==count)
	viewer.set_u(0); viewer.player.export_actual(output,"restored")
	viewer.mode.select(0); viewer._mode_changed(0); viewer.tissue_check.button_pressed = false; viewer.section_check.button_pressed = false; viewer._visibility(); viewer._apply_section(); viewer.reset_camera()
	await capture("D0_complete")
	for i in viewer.candidates.item_count:
		viewer.candidates.select(i); viewer._load_candidate(i); viewer.mode.select(2); viewer._mode_changed(2); viewer.section_check.button_pressed = false; viewer._apply_section(); viewer.reset_camera()
		check("candidate source mesh separate "+str(i),viewer.extras["wall"]!=viewer.player.nodes["cavity"])
		check("candidate reference only "+str(i),viewer.player.filling==0 and not viewer.slider.editable)
		check("virtual caps separate "+str(i),viewer.extras["caps"].mesh!=viewer.player.nodes["cavity"].mesh)
		check("source cavity vertices "+str(i),viewer.player.data["cavity"]["reference"].size()==25024)
		await capture("D2_"+str(viewer.meta["candidates"][i]["id"]))
		if str(viewer.meta["candidates"][i]["id"])=="C06_near_BASE":
			for j in 3:
				viewer.focus_cut(j); await capture("C06_cut_"+["BLADDER","IN01","IN02"][j])
	var common_camera: Vector3 = viewer.camera.position
	for name: String in ["C11_inlet_distal_control","C06_near_BASE"]:
		for i in viewer.candidates.item_count:
			if str(viewer.meta["candidates"][i]["id"])==name: viewer.candidates.select(i); viewer._load_candidate(i)
		check("same domain comparison camera "+name,viewer.camera.position==common_camera); await capture("compare_"+name)
	viewer.mode.select(3); viewer._mode_changed(3); viewer.cavity_check.button_pressed = true; viewer.tissue_check.button_pressed = true; viewer._visibility()
	for name: String in ["J_05","J_09","F01","F02"]:
		viewer.focus(name)
		var before: Vector3 = viewer.camera.position
		for value in [0.,1.]:
			viewer.set_u(value); check("same camera "+name+str(value),viewer.camera.position==before); await capture("contact_"+name+"_u%03d" % roundi(100*value))
	if not viewer.meta["review_pairs"].is_empty():
		viewer.pair_choice.select(0); viewer.select_pair(0); check("pair lines generated",viewer.extras["pair_lines"].mesh!=null); await capture("classified_pair")
	for i in viewer.meta["review_pairs"].size():
		if viewer.meta["review_pairs"][i]["class"]!="COPLANAR_OVERLAP": continue
		viewer.select_pair(i)
		var pair_camera: Vector3 = viewer.camera.position
		for visibility: Array in [[true,true,"both"],[true,false,"cavity_only"],[false,true,"tissue_only"]]:
			viewer.cavity_check.button_pressed = visibility[0]; viewer.tissue_check.button_pressed = visibility[1]; viewer._visibility()
			check("same coplanar camera "+visibility[2],viewer.camera.position==pair_camera); await capture("coplanar_"+visibility[2])
		viewer.cavity_check.button_pressed = true; viewer.tissue_check.button_pressed = true; viewer._visibility()
		break
	viewer.manual_pair(); check("manual pair stored",viewer.selected_pair.has("cavity_face"))
	await viewer.save_review()
	for width in [1024,1280]:
		get_window().size = Vector2i(width,768 if width==1024 else 720); await get_tree().process_frame; await get_tree().process_frame
		check("view area positive "+str(width),viewer.view.size.x>500 and viewer.view.size.y>500); await capture("layout_"+str(width))
	var failed := 0
	for record: Dictionary in checks:
		if not record["passed"]: failed += 1
	var file := FileAccess.open(output.path_join("runtime_checks.json"),FileAccess.WRITE)
	file.store_string(JSON.stringify({"checks":checks,"failures":failed,"captures":captures,"renderer":RenderingServer.get_current_rendering_method(),"adapter":RenderingServer.get_video_adapter_name(),"virtual_caps_in_accepted_player":false},"\t")); file.close()
	print("N0 graphics checks: ",checks.size()," failures: ",failed)
	get_tree().quit(0 if failed==0 else 1)
