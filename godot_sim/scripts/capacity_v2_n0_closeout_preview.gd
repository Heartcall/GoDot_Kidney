extends "res://scripts/capacity_v2_n0_preview.gd"
## New feedback overlay. Historical N0 scene/data are immutable.
const CLOSE_ROOT := "res://deformation/capacity_v2_n0_closeout"
var closeout_loaded := false
var collar_check: CheckBox

func _ready() -> void:
	super._ready()
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(CLOSE_ROOT.path_join("review_preview.json")))
	if not parsed is Dictionary or FileAccess.get_sha256(ROOT.path_join("review_preview.json")) != parsed.get("historical_preview_sha256",""):
		push_error("N0 closeout evidence missing or historical source changed"); get_tree().quit(1); return
	meta = parsed
	closeout_loaded = true
	(box.get_child(0) as Label).text = "N0 人工反馈＋C11 边界收尾\n工程测量代理；D2 仍未批准"
	candidates.clear()
	for rec: Dictionary in meta["candidates"]: candidates.add_item(str(rec["id"]))
	var collar := MeshInstance3D.new(); collar.name = "VerifiedRemovableCollar"; world.add_child(collar); extras["collar"] = collar
	var rings := MeshInstance3D.new(); rings.name = "OldAndNewCutRings"; world.add_child(rings); extras["comparison_rings"] = rings
	collar_check = _check("显示已计量 IN_02 固定管壁段（青绿）",false,func(_v): _visibility())
	_button("定位 IN_02 侧面：比较旧／新截环",focus_collar)
	_label("橙环＝C11；青环＝R1。真实间距约%.6f mm，未放大几何。\n仅移除%.6f mL已确认固定管壁；其余人工过渡容量未知。" % [meta["closeout_refinement"]["collar_length_mm"],meta["closeout_refinement"]["certified_fixed_wall_collar_removed_mL"]])
	for i in candidates.item_count:
		if meta["candidates"][i]["id"]=="C11_inlet_distal_control": candidates.select(i)
	_load_candidate(candidates.selected)
	reset_camera()
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--closeout-verify="):
			var runner = load("res://tools/capacity_v2/verify_n0_closeout.gd").new()
			runner.viewer = self; runner.output = arg.trim_prefix("--closeout-verify="); add_child(runner)

func _load_candidate(index: int) -> void:
	if not closeout_loaded or not meta["candidates"][index].has("display_dataset"):
		super._load_candidate(index)
	else:
		var rec: Dictionary = meta["candidates"][index]; extra_materials.clear()
		for entry: Array in [["wall","original_wall.bin",Color(.15,.65,.95)],["caps","virtual_caps.bin",Color(1,.72,.05)],["excluded","excluded_structure.bin",Color(.53,.57,.62)]]:
			_load_mesh(extras[entry[0]],CLOSE_ROOT.path_join("domains").path_join(rec["id"]).path_join(entry[1]),rec["output_sha256"][entry[1]],entry[2])
		var vertices: PackedVector3Array = extras["wall"].mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
		var points := PackedVector3Array(); var colors := PackedColorArray()
		for i in 3:
			var cut: Dictionary = rec["cuts"][i]; var ring: Array = cut["selected_boundary_vertex_ids"]; var color: Color = [Color(1,.25,.2),Color(.3,1,.3),Color(.5,.6,1)][i]
			for k in ring.size(): _line(points,colors,vertices[int(ring[k])],vertices[int(ring[(k+1)%ring.size()])],color)
		_set_lines(extras["cut_lines"],points,colors,false)
	if closeout_loaded and extras.has("collar"):
		_load_mesh(extras["collar"],CLOSE_ROOT.path_join("removed_fixed_collar.bin"),str(meta["closeout_collar_binary_sha256"]),Color(.1,.95,.7))
		var points := PackedVector3Array(); var colors := PackedColorArray()
		for name: String in ["C11","R1"]:
			var ring: Array = meta["closeout_refinement"]["ring_comparison_mm"][name]
			for k in ring.size(): _line(points,colors,_vec(ring[k])-ORIGIN,_vec(ring[(k+1)%ring.size()])-ORIGIN,Color(1,.45,.05) if name=="C11" else Color(.1,1,1))
		_set_lines(extras["comparison_rings"],points,colors,true)
	_apply_section(); _visibility(); _status()

func _visibility() -> void:
	super._visibility()
	if not closeout_loaded or not extras.has("collar") or not is_instance_valid(collar_check): return
	extras["collar"].visible = mode.selected==2 and collar_check.button_pressed and meta["candidates"][candidates.selected].has("display_dataset")
	extras["comparison_rings"].visible = mode.selected==2 and collar_check.button_pressed

func _status() -> void:
	super._status()
	if not closeout_loaded: return
	if mode.selected==3:
		status.text = status.text.replace("具体视觉穿模尚待用户现场定位。","用户本次审核视角未见异常；不是全连续区间无碰撞证明。")
		return
	var rec: Dictionary = meta["candidates"][candidates.selected]; var id: String = rec["id"]
	if id=="C11_R1_IN02_fixed_collar": status.text += "\n固定管壁局部精修：待人工确认。\n没有补证全部天然腔壁或UPJ；有效容量仍未知。"
	else:
		var reviewed: Dictionary = meta["closeout_feedback"]["candidate_statuses"][id]
		status.text += "\n本次记录："+str(reviewed["status"])
		if id=="C06_near_BASE": status.text += "\n用户已拒绝：删除天然分支入口与腔壁。"
		elif id=="C11_inlet_distal_control": status.text += "\n本次视觉通过；尚未确认为纯天然容量域。"

func focus_collar() -> void:
	var row: Dictionary = meta["candidates"][-1]; var cut: Dictionary = row["cuts"][2]
	var n := _vec(cut["normal_toward_artificial_END"]); var side := n.cross(Vector3.UP).normalized()
	focus_point(_vec(cut["center_mm"])-ORIGIN+n*float(meta["closeout_refinement"]["collar_length_mm"])*0.5,side,9.0)
	collar_check.button_pressed = true; _visibility()

func save_review() -> void:
	await RenderingServer.frame_post_draw
	var directory := CLOSE_ROOT.path_join("user_sessions"); DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(directory))
	var path := directory.path_join("review_"+str(Time.get_ticks_msec())); var record := review_state()
	record["schema"] = "N0_CLOSEOUT_USER_SESSION_V1"; record["D2_approved"] = false
	var file := FileAccess.open(path+".json",FileAccess.WRITE); file.store_string(JSON.stringify(record,"\t")); file.close()
	get_viewport().get_texture().get_image().save_png(ProjectSettings.globalize_path(path+".png")); saved_info.text = "收尾现场已保存："+path
