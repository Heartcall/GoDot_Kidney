extends Node
var viewer: Control
var output := ""
var checks: Array = []
var captures: Array = []

func _ready() -> void: call_deferred("run")
func check(label: String,passed: bool) -> void:
	checks.append({"name":label,"passed":passed})
	if not passed: push_error(label)

func capture(tag: String) -> void:
	(viewer.panel.get_child(0) as ScrollContainer).scroll_vertical = 0
	await get_tree().process_frame; await RenderingServer.frame_post_draw
	var code := viewer.get_viewport().get_texture().get_image().save_png(ProjectSettings.globalize_path(output.path_join(tag+".png")))
	check("capture "+tag,code==OK); captures.append({"tag":tag,"state":viewer.review_state()})

func choose(id: String) -> void:
	for i in viewer.path_choice.item_count:
		if viewer.path_choice.get_item_text(i)==id: viewer.choose_path(i); return
	check("path found "+id,false)

func run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output)); await get_tree().process_frame
	check("N1 ready",viewer.n1_ready); check("approved D2 displayed",viewer.analysis["D2_status"]=="USER_APPROVED_PROJECT_MEASUREMENT_DOMAIN")
	check("reference only",viewer.player.filling==0); check("virtual cap separate",viewer.extras["caps"].mesh!=viewer.player.nodes["cavity"].mesh)
	check("overview clipping really disabled",not viewer.section_check.button_pressed and not bool(viewer.extra_materials[0].get_shader_parameter("section_enabled")))
	await capture("D2_reference_overview")
	for id: String in ["MAIN","B_12","B_31","B_32"]:
		choose(id); viewer.focus_station(); check(id+" station selected",viewer.current_station["path_id"]==id)
		check(id+" clip uses station normal",viewer.section_normal.is_equal_approx(viewer._vec(viewer.current_station["plane_normal_unit"])))
		check(id+" geometry unchanged",viewer.player.filling==0); await capture(id+"_section")
	for id: String in ["J_05","J_09","T_01","T_22"]:
		for i in viewer.node_choice.item_count:
			if viewer.node_choice.get_item_text(i)==id: viewer.node_choice.select(i); viewer.focus_node(i)
		check(id+" node displayed",viewer.local_info.text.contains(id)); await capture(id+"_node")
	var original: Array = viewer.extras["wall"].mesh.surface_get_arrays(0)
	viewer.region_check.button_pressed = true; viewer.color_regions()
	var colored: Array = viewer.extras["wall"].mesh.surface_get_arrays(0)
	check("colors do not alter coordinates",original[Mesh.ARRAY_VERTEX]==colored[Mesh.ARRAY_VERTEX]); check("colors do not alter indices",original[Mesh.ARRAY_INDEX]==colored[Mesh.ARRAY_INDEX])
	check("colors do not re-quantize normals",original[Mesh.ARRAY_NORMAL]==colored[Mesh.ARRAY_NORMAL])
	var normal_file := FileAccess.open(output.path_join("wall_initial_actual_normals.bin"),FileAccess.WRITE)
	normal_file.store_buffer((original[Mesh.ARRAY_NORMAL] as PackedVector3Array).to_byte_array()); normal_file.close()
	for i in 5:
		viewer.region_check.button_pressed = not viewer.region_check.button_pressed; viewer.color_regions()
	colored = viewer.extras["wall"].mesh.surface_get_arrays(0)
	check("repeat color toggles preserve normals",original[Mesh.ARRAY_NORMAL]==colored[Mesh.ARRAY_NORMAL])
	viewer.region_check.button_pressed = true; viewer.color_regions()
	viewer.section_check.button_pressed = false; viewer._apply_section(); viewer.reset_camera(); await capture("candidate_region_overlay")
	viewer.tissue_check.button_pressed = true; viewer._visibility(); check("opaque reference tissue visible",viewer.player.nodes["tissue"].visible)
	viewer.focus_station(); await capture("Reference_tissue_section")
	for mesh_name: String in ["wall","caps"]:
		var arrays: Array = viewer.extras[mesh_name].mesh.surface_get_arrays(0)
		var file := FileAccess.open(output.path_join(mesh_name+"_actual_positions.bin"),FileAccess.WRITE)
		file.store_buffer((arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).to_byte_array()); file.close()
		file = FileAccess.open(output.path_join(mesh_name+"_actual_indices.bin"),FileAccess.WRITE)
		file.store_buffer((arrays[Mesh.ARRAY_INDEX] as PackedInt32Array).to_byte_array()); file.close()
		file = FileAccess.open(output.path_join(mesh_name+"_actual_normals.bin"),FileAccess.WRITE)
		file.store_buffer((arrays[Mesh.ARRAY_NORMAL] as PackedVector3Array).to_byte_array()); file.close()
	viewer.player.export_actual(output,"Reference")
	var failed := 0
	for row: Dictionary in checks:
		if not row["passed"]: failed+=1
	var file := FileAccess.open(output.path_join("runtime_checks.json"),FileAccess.WRITE)
	file.store_string(JSON.stringify({"checks":checks,"failures":failed,"captures":captures,"renderer":RenderingServer.get_current_rendering_method(),"adapter":RenderingServer.get_video_adapter_name()},"\t"));file.close()
	print("N1 graphics checks ",checks.size()," failures ",failed);get_tree().quit(0 if failed==0 else 1)
