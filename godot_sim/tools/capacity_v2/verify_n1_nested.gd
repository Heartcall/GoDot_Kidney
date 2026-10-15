extends Node
var viewer: Control
var output := ""
var checks: Array = []
var captures: Array = []
func _ready() -> void: call_deferred("run")
func check(label: String,ok: bool) -> void:
	checks.append({"name":label,"passed":ok})
	if not ok: push_error(label)
func capture(tag: String) -> void:
	(viewer.panel.get_child(0) as ScrollContainer).scroll_vertical = 0
	await get_tree().process_frame; await RenderingServer.frame_post_draw
	var code := viewer.get_viewport().get_texture().get_image().save_png(ProjectSettings.globalize_path(output.path_join(tag+".png")))
	check("capture "+tag,code==OK); captures.append({"tag":tag,"state":viewer.review_state()})
func run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output)); await get_tree().process_frame
	check("review ready",viewer.review_ready);check("reference unchanged",viewer.player.filling==0)
	for index in 2:
		viewer.load_case(index); var tag: String = str(viewer.current_case["id"]).replace(":","_")
		check(tag+" unresolved shown",viewer.status.text.contains("MULTIRING_WITH_HOLE_UNRESOLVED"));check(tag+" no real crossing",viewer.current_case["local_finite_contacts"]["confirmed_invalid_pairs"].is_empty())
		await capture(tag+"_plane")
		viewer.oblique_view();await capture(tag+"_oblique")
		viewer.inner_only();check(tag+" independent inner visible",viewer.extras["inner_source_faces"].visible and not viewer.extras["outer_source_faces"].visible);await capture(tag+"_inner_source")
		viewer.restore_local();viewer.group_checks["context"].button_pressed = true;viewer._visibility();viewer.oblique_view();viewer.section_check.button_pressed = false;viewer._apply_section();await capture(tag+"_full_context_oblique")
		viewer.restore_local();viewer.choose_plane(1);viewer.focus_plane();await capture(tag+"_neighbor_minus050")
		for mesh_name: String in ["outer_source_faces","inner_source_faces"]:
			var arrays: Array = viewer.extras[mesh_name].mesh.surface_get_arrays(0)
			var file := FileAccess.open(output.path_join(tag+"_"+mesh_name+"_positions.bin"),FileAccess.WRITE)
			file.store_buffer((arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).to_byte_array());file.close()
	viewer.player.export_actual(output,"Reference")
	var failed := 0
	for row: Dictionary in checks:
		if not row["passed"]: failed+=1
	var file := FileAccess.open(output.path_join("runtime_checks.json"),FileAccess.WRITE)
	file.store_string(JSON.stringify({"checks":checks,"failures":failed,"captures":captures,"renderer":RenderingServer.get_current_rendering_method(),"adapter":RenderingServer.get_video_adapter_name()},"\t"));file.close()
	print("Nested ring graphics checks ",checks.size()," failures ",failed);get_tree().quit(0 if failed==0 else 1)
