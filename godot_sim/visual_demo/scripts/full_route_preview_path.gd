extends "res://scripts/endoscope_controller.gd"
## Demonstration-only camera. Original research controller is unchanged.
var route_times: Array = []
var route_arcs: Array = []
var route_duration := 0.0

func _ready() -> void:
	_load_cavity_path()
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(cavity_path_file))
	route_times = data["times_seconds"]
	route_arcs = data["arc_lengths_mm"]
	route_duration = float(data["duration_seconds"])
	_snap_to_path_start()
	set_physics_process(false)
	set_process(false)
	set_process_unhandled_input(false)

func arc_at_time(t: float) -> float:
	var lo := 0
	var hi := route_times.size() - 1
	while lo < hi - 1:
		var mid := (lo + hi) / 2
		if float(route_times[mid]) <= t: lo = mid
		else: hi = mid
	var fraction := clampf((t - float(route_times[lo])) / (float(route_times[hi])-float(route_times[lo])),0.0,1.0)
	return lerpf(float(route_arcs[lo]),float(route_arcs[hi]),fraction)

func advance_to(t: float, delta: float) -> void:
	tour_offset = arc_at_time(t)
	var sample: Dictionary = _sample_path(tour_offset)
	global_position = sample["pos"]
	# Use original minimal-twist basis + rate-limited quaternion slerp continuously.
	# Junction slowdowns are baked into route_times; no forward-freezing roll phase.
	var forward: Vector3 = sample["dir"]
	_step_toward(_cruise_free_basis(forward.normalized()), delta)
