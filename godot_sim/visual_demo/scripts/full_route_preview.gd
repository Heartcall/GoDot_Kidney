extends Node3D
## Preview only, pending user approval. One global morph state, no local phase offsets.
const MAIN = preload("res://main.tscn")
const MODEL = preload("res://visual_demo/assets/kidney_manual_v3.glb")
const PATH_DRIVER = preload("res://visual_demo/scripts/full_route_preview_path.gd")
const ROUTE := "res://visual_demo/data/full_route_c04.json"
const REPORT := "res://../visual_demo/full_route_v6/preview/"
@export var duration_seconds := 45.93333333333333
@export var preview_loop := false
@export var near_clip_mm := 0.05
var scope: CharacterBody3D
var cavity: MeshInstance3D
var camera: Camera3D
var ci := -1
var ei := -1
var elapsed := 0.0
var frame := 0
var frame_count := 0
var state := -0.4
var audit := false
var once := false
var deterministic := false
var finished := false
var capture_frames: Array[int] = []
var telemetry: FileAccess
var last_q := Quaternion.IDENTITY
var max_step_deg := 0.0
var max_look_error_deg := 0.0

func _ready() -> void:
	if Engine.get_write_movie_path() != "":
		push_error("This is an approval preview. Final movie recording awaits user approval.")
		get_tree().quit(1); return
	audit = "--audit" in OS.get_cmdline_user_args()
	once = "--once" in OS.get_cmdline_user_args()
	# Engine options may be consumed before OS.get_cmdline_args(); audit explicitly
	# selects endpoint-inclusive 30 fps sampling without enabling Movie Maker.
	deterministic = audit
	get_window().content_scale_size = Vector2i(1920,1080)
	get_window().size = Vector2i(1280,720)
	get_window().content_scale_mode = Window.CONTENT_SCALE_MODE_VIEWPORT
	var original := MAIN.instantiate()
	var viewport: SubViewport = original.get_node("SubViewportContainer/EndoscopeView")
	viewport.get_node("KidneyBody").free()
	original.get_node("DebugOverlay").free()
	scope = viewport.get_node("Endoscope")
	scope.get_node("CollisionShape3D").free()
	scope.set_script(PATH_DRIVER)
	scope.cavity_path_file = ROUTE
	scope.debug_overlay_path = NodePath()
	scope.junction_snapshots_enabled = false
	scope.captures_enabled = false
	add_child(original)
	viewport.msaa_3d = Viewport.MSAA_4X
	camera = scope.get_node("Head/Camera3D")
	camera.attributes = null
	camera.near = near_clip_mm
	var light: SpotLight3D = camera.get_node("HeadLight")
	light.light_energy = 6.0
	light.spot_range = 45.0
	light.spot_angle = 80.0
	light.spot_attenuation = 0.65
	light.spot_angle_attenuation = 0.5
	light.light_color = Color(1.0,0.92,0.88)
	var fill := OmniLight3D.new()
	fill.light_color = Color(1.0,0.8,0.78)
	fill.light_energy = 0.6
	fill.omni_range = 18.0
	fill.omni_attenuation = 0.5
	camera.add_child(fill)
	var asset := MODEL.instantiate()
	asset.transform = Transform3D(Basis(Vector3(1000,0,0),Vector3(0,0,1000),Vector3(0,-1000,0)),Vector3(16,16,-81))
	viewport.add_child(asset)
	for n in asset.find_children("*","MeshInstance3D",true,false):
		if n.name.begins_with("KidneyCavity"): cavity = n
	if cavity == null:
		push_error("Manual v3 cavity missing"); get_tree().quit(1); return
	ci = cavity.find_blend_shape_by_name("Contracted")
	ei = cavity.find_blend_shape_by_name("Expanded")
	if ci < 0 or ei < 0:
		push_error("Manual v3 morphs missing"); get_tree().quit(1); return
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(0.78,0.44,0.49)
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.roughness = 0.46
	material.metallic_specular = 0.3
	material.clearcoat_enabled = true
	material.clearcoat = 0.08
	material.clearcoat_roughness = 0.4
	cavity.material_override = material
	frame_count = roundi(duration_seconds*30) + 1
	for i in range(13): capture_frames.append(roundi(float(i)*(frame_count-1)/12))
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(ROUTE))
	for j in data["junctions"]:
		var idx := 0
		for i in scope.route_arcs.size():
			if float(scope.route_arcs[i]) >= float(j): idx = i; break
		var junction_frame := roundi(float(scope.route_times[idx])/scope.route_duration*duration_seconds*30)
		for f in [junction_frame-30,junction_frame,junction_frame+30]:
			if f >= 0 and f < frame_count and f not in capture_frames: capture_frames.append(f)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(REPORT))
	if audit:
		telemetry = FileAccess.open(REPORT+"frames.csv",FileAccess.WRITE)
		telemetry.store_line("frame,time,s,contracted,expanded,arc_mm,x,y,z,qx,qy,qz,qw,forward_error_deg")
	last_q = camera.global_basis.get_rotation_quaternion()
	_apply_time(0.0,0.0)
	if audit: _dump_imported_shapes()
	print("FULL_ROUTE_PREVIEW_START ",JSON.stringify({"model":"manual_v3","route":ROUTE,"duration":duration_seconds,"states":[-0.4,1.0,-0.4],"global_morph":true,"points":scope.path_points.size(),"junctions":scope.junction_offsets,"renderer":RenderingServer.get_current_rendering_method(),"engine":Engine.get_version_info(),"near_clip_mm":near_clip_mm}))
	RenderingServer.frame_post_draw.connect(_after_draw)

func _apply_time(t: float,dt: float) -> void:
	var u := clampf(t/duration_seconds,0.0,1.0)
	state = 0.3-0.7*cos(TAU*u)
	if u == 0.0 or u == 1.0: state = -0.4
	if u == 0.5: state = 1.0
	cavity.set_blend_shape_value(ci,maxf(-state,0))
	cavity.set_blend_shape_value(ei,maxf(state,0))
	if dt > 0:
		var steps := maxi(1,ceili(dt*240))
		for i in range(1,steps+1): scope.advance_to((t-dt+dt*float(i)/steps)/duration_seconds*scope.route_duration,dt/steps)
	var q := camera.global_basis.get_rotation_quaternion()
	max_step_deg = maxf(max_step_deg,rad_to_deg(last_q.angle_to(q)))
	last_q = q
	var desired: Vector3 = scope._sample_path(scope.tour_offset)["dir"]
	var look_error := rad_to_deg(acos(clampf((-camera.global_basis.z).dot(desired.normalized()),-1,1)))
	max_look_error_deg = maxf(max_look_error_deg,look_error)
	if audit:
		var p := camera.global_position
		telemetry.store_line("%d,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f" % [frame,t,state,cavity.get_blend_shape_value(ci),cavity.get_blend_shape_value(ei),scope.tour_offset,p.x,p.y,p.z,q.x,q.y,q.z,q.w,look_error])

func _process(delta: float) -> void:
	if frame == 0 or finished: return
	var next := minf(float(frame)/30.0,duration_seconds) if deterministic else minf(elapsed+delta,duration_seconds)
	if deterministic and frame >= frame_count - 1: next = duration_seconds
	_apply_time(next,next-elapsed)
	elapsed = next

func _after_draw() -> void:
	if finished: return
	if audit and frame in capture_frames:
		get_viewport().get_texture().get_image().save_png(REPORT+"frame_%04d.png" % frame)
	if elapsed >= duration_seconds:
		var result := {"complete":true,"frames":frame+1,"duration":elapsed,"first_arc_mm":0,"last_arc_mm":scope.tour_offset,"end_position":camera.global_position,"final_contracted":cavity.get_blend_shape_value(ci),"final_expanded":cavity.get_blend_shape_value(ei),"max_frame_rotation_deg":max_step_deg,"max_forward_error_deg":max_look_error_deg,"no_movie_recorded":true}
		if audit:
			telemetry.flush();telemetry.close()
			var file := FileAccess.open(REPORT+"runtime.json",FileAccess.WRITE)
			file.store_string(JSON.stringify(result,"  "));file.close()
		print("FULL_ROUTE_PREVIEW_COMPLETE ",JSON.stringify(result))
		finished = true
		if once: get_tree().quit()
		elif preview_loop: get_tree().reload_current_scene()
	frame += 1

func _dump_imported_shapes() -> void:
	for s: float in [-0.4,0.0,1.0]:
		cavity.set_blend_shape_value(ci,maxf(-s,0.0)); cavity.set_blend_shape_value(ei,maxf(s,0.0))
		var baked := cavity.bake_mesh_from_current_blend_shape_mix()
		var vertices: PackedVector3Array = baked.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
		var packed := PackedFloat32Array()
		for v in vertices:
			var p := cavity.global_transform*v
			packed.append_array(PackedFloat32Array([p.x,p.y,p.z]))
		var file := FileAccess.open(REPORT+"imported_%s.bin" % str(s),FileAccess.WRITE)
		file.store_buffer(packed.to_byte_array());file.close()
	cavity.set_blend_shape_value(ci,0.4);cavity.set_blend_shape_value(ei,0.0)
