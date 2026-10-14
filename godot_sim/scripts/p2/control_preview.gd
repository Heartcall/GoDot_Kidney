extends Control
## Composition and observation only; UI and timing are separate reusable modules.
const Player := preload("res://scripts/p2/deformation_player.gd")
const Controller := preload("res://scripts/p2/irrigation_controller.gd")
var player: Node3D
var controller: Node
@onready var panel: PanelContainer = $Layout/Panel
@onready var view: SubViewportContainer = $Layout/View
@onready var viewport: SubViewport = $Layout/View/Viewport
@onready var world: Node3D = $Layout/View/Viewport/World
@onready var camera: Camera3D = $Layout/View/Viewport/World/PreviewCamera
var center := Vector3.ZERO
var yaw := 0.6
var pitch := 0.45
var distance := 215.0
var section_enabled := true
var section_normal := Vector3.RIGHT
var section_offset := 0.0
var locations := {}

func _ready() -> void:
	var player_script: Script = Player
	for arg in OS.get_cmdline_user_args():
		if arg == "--p23-use-instrumented-baseline":
			player_script = load("res://deformation/p23/baseline/instrumented_player.gd")
	player = player_script.new()
	world.add_child(player)
	if not player.ready_ok:
		return
	controller = Controller.new()
	add_child(controller)
	controller.filling_changed.connect(player.set_filling)
	var meta: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://deformation/p23/focus_locations.json"))
	locations = meta["locations"]
	var names: Array = locations.keys()
	names.sort()
	panel.bind_controller(controller, names)
	panel.mesh_visibility_changed.connect(player.set_mesh_visible)
	panel.section_changed.connect(_section)
	panel.focus_requested.connect(focus)
	panel.camera_reset_requested.connect(reset_camera)
	view.gui_input.connect(_view_input)
	resized.connect(_layout)
	_layout()
	reset_camera()
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--p23-benchmark=") or arg.begins_with("--p23-regression="):
			var runner = load("res://tools/p23/verification_runner.gd").new()
			runner.viewer = self
			add_child(runner)

func _layout() -> void:
	panel.custom_minimum_size.x = clampf(size.x*0.27, 280.0, 390.0)

func _section(enabled: bool, normal: Vector3, offset: float) -> void:
	section_enabled = enabled
	section_normal = normal
	section_offset = offset
	player.set_section(enabled, normal, offset)

func _update_camera() -> void:
	camera.position = center+Vector3(sin(yaw)*cos(pitch), sin(pitch), cos(yaw)*cos(pitch))*distance
	camera.look_at(center, Vector3.UP)

func reset_camera() -> void:
	var bounds: AABB = player.nodes["cavity"].mesh.get_aabb().merge(player.nodes["tissue"].mesh.get_aabb())
	center = bounds.get_center()
	distance = maxf(bounds.size.x,maxf(bounds.size.y,bounds.size.z))*1.7
	yaw = 0.6
	pitch = 0.45
	_update_camera()

func focus(name: String) -> void:
	for index in panel.focus_choice.item_count:
		if (index == 0 and name == "ALL") or panel.focus_choice.get_item_text(index) == name:
			panel.focus_choice.select(index)
			break
	if name == "ALL":
		reset_camera()
		return
	if not locations.has(name):
		return
	var record: Dictionary = locations[name]
	center = Vector3(record["center_mm"][0]-16.0,record["center_mm"][1]-16.0,record["center_mm"][2]+81.0)
	var normal := Vector3(record["normal"][0],record["normal"][1],record["normal"][2]).normalized()
	yaw = atan2(normal.x,normal.z)
	pitch = asin(clampf(normal.y,-0.95,0.95))
	distance = record["distance_mm"]
	_update_camera()
	_section(true,normal,center.dot(normal)+0.5)
	panel.reflect_section(true,normal,section_offset)

func _view_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		if Input.is_mouse_button_pressed(MOUSE_BUTTON_LEFT):
			yaw -= event.relative.x*0.006
			pitch = clampf(pitch+event.relative.y*0.006,-1.45,1.45)
			_update_camera()
		elif Input.is_mouse_button_pressed(MOUSE_BUTTON_MIDDLE):
			center += (-camera.global_basis.x*event.relative.x+camera.global_basis.y*event.relative.y)*distance*0.001
			_update_camera()
	if event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			distance = maxf(2.0,distance/1.12)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			distance = minf(500.0,distance*1.12)
		_update_camera()

func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and event.keycode == KEY_R:
		reset_camera()
