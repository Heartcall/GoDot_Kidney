extends Node3D
## Isolated first-person video. The artist file and authoritative route are read-only.
const MAIN = preload("res://main.tscn")
const MODEL = preload("res://visual_demo/assets/kidney_manual_v3.glb")
const VIDEO_PATH = preload("res://visual_demo/scripts/endoscope_video_path.gd")
const ORIGIN_RAS_MM := Vector3(16, 16, -81)
@export_range(0.5, 120.0) var duration_seconds := 8.0
@export_range(1, 120) var video_fps := 30
@export_range(0.0, 1.0) var path_start_progress := 0.5778149846
@export_range(0.0, 1.0) var path_end_progress := 0.6933779815
@export var preview_loop := true
@export var video_size := Vector2i(1920, 1080)
var scope: CharacterBody3D
var cavity: MeshInstance3D
var camera: Camera3D
var ci := -1
var ei := -1
var movie := false
var once := false
var frame := 0
var frame_count := 0
var elapsed := 0.0
var report_prefix := "res://recordings/endoscope_v3"
var telemetry: FileAccess
var snapshot_frames: Array[int] = []
var audit_mode := false
var finished := false
var previous_quat := Quaternion.IDENTITY
var max_rotation_step_deg := 0.0

func _ready() -> void:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--duration="): duration_seconds = float(arg.get_slice("=", 1))
		elif arg.begins_with("--fps="): video_fps = int(arg.get_slice("=", 1))
		elif arg.begins_with("--start="): path_start_progress = float(arg.get_slice("=", 1))
		elif arg.begins_with("--end="): path_end_progress = float(arg.get_slice("=", 1))
		elif arg.begins_with("--report="): report_prefix = arg.get_slice("=", 1)
		elif arg == "--once": once = true
		elif arg == "--audit": audit_mode = true
	movie = Engine.get_write_movie_path() != ""
	var engine_args := OS.get_cmdline_args()
	var fps_arg := engine_args.find("--fixed-fps")
	if fps_arg >= 0: video_fps = int(engine_args[fps_arg + 1])
	elif movie: video_fps = int(ProjectSettings.get_setting("editor/movie_writer/fps", 30))
	if duration_seconds <= 0 or video_fps < 1 or path_start_progress < 0 or path_end_progress > 1 or path_end_progress < path_start_progress:
		push_error("Invalid video parameters"); get_tree().quit(1); return
	frame_count = maxi(3, roundi(duration_seconds * video_fps) + 1)
	get_window().content_scale_size = video_size
	get_window().size = video_size
	var original := MAIN.instantiate()
	var viewport: SubViewport = original.get_node("SubViewportContainer/EndoscopeView")
	viewport.get_node("KidneyBody").free()
	original.get_node("DebugOverlay").free()
	scope = viewport.get_node("Endoscope")
	scope.get_node("CollisionShape3D").free()
	scope.set_script(VIDEO_PATH)
	scope.cavity_path_file = "res://data/organ_2_kidney/lab_6/cavity_path_stone1.json"
	scope.junction_snapshots_enabled = false
	scope.captures_enabled = false
	scope.debug_overlay_path = NodePath()
	scope.lookahead_distance_mm = 10.0
	scope.junction_lookahead_mm = 10.0
	add_child(original)
	viewport.msaa_3d = Viewport.MSAA_4X
	camera = scope.get_node("Head/Camera3D")
	camera.attributes = null # Keep nearby mucosa in focus for this visual demonstration.
	var light: SpotLight3D = camera.get_node("HeadLight")
	light.light_energy = 6.0
	light.spot_range = 45.0
	light.spot_angle = 80.0
	light.spot_attenuation = 0.65
	light.spot_angle_attenuation = 0.5
	light.light_color = Color(1.0, 0.92, 0.88)
	var fill := OmniLight3D.new()
	fill.light_color = Color(1.0, 0.80, 0.78)
	fill.light_energy = 0.6
	fill.omni_range = 18.0
	fill.omni_attenuation = 0.5
	camera.add_child(fill)
	var asset := MODEL.instantiate()
	# Inverse glTF axis conversion plus metres -> RAS millimetres.
	asset.transform = Transform3D(Basis(Vector3(1000,0,0), Vector3(0,0,1000), Vector3(0,-1000,0)), ORIGIN_RAS_MM)
	viewport.add_child(asset)
	for node in asset.find_children("*", "MeshInstance3D", true, false):
		if node.name.begins_with("KidneyCavity"): cavity = node
	if cavity == null or cavity.get_blend_shape_count() != 2:
		push_error("Formal v3 KidneyCavity or morphs missing"); get_tree().quit(1); return
	ci = cavity.find_blend_shape_by_name("Contracted")
	ei = cavity.find_blend_shape_by_name("Expanded")
	if ci < 0 or ei < 0:
		push_error("Required named v3 morphs missing"); get_tree().quit(1); return
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(0.78, 0.44, 0.49)
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.roughness = 0.34
	material.metallic_specular = 0.45
	material.clearcoat_enabled = true
	material.clearcoat = 0.2
	material.clearcoat_roughness = 0.25
	cavity.material_override = material
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(report_prefix.get_base_dir()))
	telemetry = FileAccess.open(report_prefix + "_frames.csv", FileAccess.WRITE)
	telemetry.store_line("frame,time_seconds,s,contracted,expanded,path_offset_mm,x_R,y_A,z_S,qx,qy,qz,qw")
	snapshot_frames = [0, frame_count / 4, frame_count / 2, 3 * frame_count / 4, frame_count - 1]
	scope.prepare_start(path_start_progress * scope.total_length)
	previous_quat = camera.global_basis.get_rotation_quaternion()
	_apply_time(0.0, 0.0)
	if audit_mode: _dump_states()
	print("ENDOSCOPE_VIDEO_START ", JSON.stringify({"engine":Engine.get_version_info(),"model":"kidney_manual_v3.glb","morphs":["Contracted","Expanded"],"duration":duration_seconds,"fps":video_fps,"frames":frame_count,"path_mm":[path_start_progress*scope.total_length,path_end_progress*scope.total_length],"movie":movie,"renderer":RenderingServer.get_current_rendering_method(),"device":RenderingServer.get_video_adapter_name()}))
	RenderingServer.frame_post_draw.connect(_after_draw)

func _apply_time(t: float, dt: float) -> void:
	var u := clampf(t / duration_seconds, 0.0, 1.0)
	# One cosine over the WHOLE cycle: nonzero speed at Reference, no middle pause.
	var s := 0.2 - 0.8 * cos(TAU * u)
	if u == 0.0 or u == 1.0: s = -0.6
	if u == 0.5: s = 1.0
	cavity.set_blend_shape_value(ci, maxf(-s, 0.0))
	cavity.set_blend_shape_value(ei, maxf(s, 0.0))
	var offset: float = lerpf(path_start_progress, path_end_progress, u) * scope.total_length
	if dt > 0.0:
		# Same 240 Hz orientation rules as main; clock and distance are shared with morphs.
		var steps := maxi(1, ceili(dt * 240.0))
		var old_offset: float = scope.tour_offset
		for i in range(1, steps + 1): scope.drive_to(lerpf(old_offset, offset, float(i)/steps), dt/steps)
	var q := camera.global_basis.get_rotation_quaternion()
	max_rotation_step_deg = maxf(max_rotation_step_deg, rad_to_deg(previous_quat.angle_to(q)))
	previous_quat = q
	var p := camera.global_position
	telemetry.store_line("%d,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f" % [frame,t,s,cavity.get_blend_shape_value(ci),cavity.get_blend_shape_value(ei),scope.tour_offset,p.x,p.y,p.z,q.x,q.y,q.z,q.w])

func _process(delta: float) -> void:
	if finished or frame == 0: return
	var next_time := minf(float(frame)/video_fps, duration_seconds) if movie else minf(elapsed + delta, duration_seconds)
	var dt := next_time - elapsed
	elapsed = next_time
	_apply_time(elapsed, dt)

func _after_draw() -> void:
	if finished: return
	if audit_mode and frame in snapshot_frames:
		get_viewport().get_texture().get_image().save_png(report_prefix + "_%04d.png" % frame)
	if elapsed >= duration_seconds:
		telemetry.flush()
		var report := {"frames":frame+1,"final_time":elapsed,"final_contracted":cavity.get_blend_shape_value(ci),"final_expanded":cavity.get_blend_shape_value(ei),"max_frame_rotation_deg":max_rotation_step_deg,"viewport_size":[get_viewport().size.x,get_viewport().size.y],"movie":movie,"finished_normally":true}
		var f := FileAccess.open(report_prefix+"_runtime.json",FileAccess.WRITE)
		f.store_string(JSON.stringify(report,"  ")); f.close()
		print("ENDOSCOPE_VIDEO_COMPLETE ",JSON.stringify(report))
		if movie or once:
			finished = true
			telemetry.close()
			get_tree().quit()
		elif preview_loop:
			frame = 0; elapsed = 0.0
			scope.prepare_start(path_start_progress * scope.total_length)
			_apply_time(0.0, 0.0)
		else: finished = true
	frame += 1

func _dump_states() -> void:
	for s: float in [-0.6, 0.0, 1.0]:
		cavity.set_blend_shape_value(ci,maxf(-s,0.0)); cavity.set_blend_shape_value(ei,maxf(s,0.0))
		var baked := cavity.bake_mesh_from_current_blend_shape_mix()
		var vertices: PackedVector3Array = baked.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
		var packed := PackedFloat32Array()
		for v in vertices:
			var p := cavity.global_transform * v
			packed.append_array(PackedFloat32Array([p.x,p.y,p.z]))
		var file := FileAccess.open(report_prefix+"_state_%s.bin" % str(s),FileAccess.WRITE)
		file.store_buffer(packed.to_byte_array()); file.close()
	cavity.set_blend_shape_value(ci,0.6); cavity.set_blend_shape_value(ei,0.0)
