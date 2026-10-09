extends Control

## Debug/visualization overlay: projects the upcoming stretch of the planned
## path into the camera's CURRENT view and draws it as a dashed highlighted
## guide line -- like an AR "road ahead" indicator. Uses the real camera
## projection (Camera3D.unproject_position), so it correctly foreshortens
## with perspective and curves away as the path turns, instead of being a
## flat schematic overlay.
##
## Finds the path point closest to the camera's actual current world
## position each frame (not tour_offset -- so this works the same in manual
## fly mode as it does during the auto-tour), then samples
## guide_lookahead_mm of path ahead of that point using the endoscope
## controller's own path_points/cum_lengths (read directly, not re-loaded).
##
## The camera renders into a SubViewport at its own internal resolution
## (main.tscn: SubViewportContainer/EndoscopeView, e.g. 1422x1066), which
## SubViewportContainer then stretches to fill the actual window -- so
## Camera3D.unproject_position()'s output (in the SubViewport's own pixel
## space) has to be rescaled to this Control's size before drawing, or the
## guide line drifts out of alignment with the video whenever those two
## sizes don't match exactly.

@export var camera_path: NodePath
@export var controller_path: NodePath
@export var guide_lookahead_mm: float = 25.0  # how far ahead of the camera's nearest path point the line extends
@export var guide_sample_spacing_mm: float = 1.0
@export var line_color: Color = Color(0, 1, 0.6, 0.85)
@export var line_width: float = 4.0
@export var dash_length: float = 10.0
@export var arrow_length: float = 34.0  # screen pixels, tip to base
@export var arrow_width: float = 22.0  # screen pixels, across the base

@onready var camera: Camera3D = (get_node(camera_path) as Camera3D) if camera_path != NodePath() else null
@onready var controller: Node = get_node(controller_path) if controller_path != NodePath() else null


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	resized.connect(queue_redraw)


func _process(_delta: float) -> void:
	queue_redraw()


func _draw() -> void:
	if camera == null or controller == null:
		return
	var points: PackedVector3Array = controller.path_points
	var cum: PackedFloat32Array = controller.cum_lengths
	if points.size() < 2 or cum.size() != points.size():
		return

	var vp := camera.get_viewport()
	var vp_size := Vector2(vp.get_visible_rect().size)
	if vp_size.x < 1.0 or vp_size.y < 1.0 or size.x < 1.0 or size.y < 1.0:
		return
	var rescale := Vector2(size.x / vp_size.x, size.y / vp_size.y)

	var start_offset := _nearest_offset(points, cum)
	var end_offset: float = min(start_offset + guide_lookahead_mm, cum[cum.size() - 1])

	var screen_pts: Array[Vector2] = []
	var s := start_offset
	while s <= end_offset + 0.0001:
		var world_pt := _point_at_offset(points, cum, s)
		if not camera.is_position_behind(world_pt):
			screen_pts.append(camera.unproject_position(world_pt) * rescale)
		s += guide_sample_spacing_mm

	for i in range(screen_pts.size() - 1):
		draw_dashed_line(screen_pts[i], screen_pts[i + 1], line_color, line_width, dash_length, true)

	if screen_pts.size() >= 2:
		_draw_arrowhead(screen_pts[-2], screen_pts[-1])


## Filled triangle at the far (last) end of the guide line, pointing along
## the direction of that final segment -- marks which way the route is
## actually heading, not just how far it's drawn.
func _draw_arrowhead(from: Vector2, to: Vector2) -> void:
	var dir := to - from
	if dir.length() < 0.001:
		return
	dir = dir.normalized()
	var perp := Vector2(-dir.y, dir.x)
	var base := to - dir * arrow_length
	var left := base + perp * (arrow_width * 0.5)
	var right := base - perp * (arrow_width * 0.5)
	draw_colored_polygon(PackedVector2Array([to, left, right]), line_color)


## Arc-length offset of the path point closest (in 3D world space) to the
## camera's current position -- deliberately NOT controller.tour_offset, so
## the guide line still makes sense while flying manually, not just mid-tour.
func _nearest_offset(points: PackedVector3Array, cum: PackedFloat32Array) -> float:
	var cam_pos := camera.global_position
	var best_idx := 0
	var best_dist := INF
	for i in range(points.size()):
		var d := cam_pos.distance_squared_to(points[i])
		if d < best_dist:
			best_dist = d
			best_idx = i
	return cum[best_idx]


func _point_at_offset(points: PackedVector3Array, cum: PackedFloat32Array, offset: float) -> Vector3:
	var n := points.size()
	var lo := 0
	var hi := n - 1
	while lo < hi - 1:
		var mid := (lo + hi) / 2
		if cum[mid] <= offset:
			lo = mid
		else:
			hi = mid
	var seg_len: float = cum[hi] - cum[lo]
	var t: float = 0.0 if seg_len < 0.00001 else (offset - cum[lo]) / seg_len
	return points[lo].lerp(points[hi], t)
