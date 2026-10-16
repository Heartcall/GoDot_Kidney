extends "res://scripts/endoscope_controller.gd"
## Only the demo clock supplies distance. All orientation routines are inherited.
var commanded_offset_mm := 0.0

func _ready() -> void:
	_load_cavity_path()
	_snap_to_path_start()
	set_physics_process(false)
	set_process(false)
	set_process_unhandled_input(false)

func _advance_offset_and_housekeeping(_speed_scale: float, _delta: float) -> void:
	tour_offset = clampf(commanded_offset_mm, 0.0, total_length)
	global_position = _sample_path(tour_offset)["pos"]

func drive_to(offset_mm: float, delta: float) -> void:
	commanded_offset_mm = offset_mm
	if junction_offsets.is_empty():
		_advance_continuous(delta)
	else:
		_advance_junction_gated(delta)

func prepare_start(offset_mm: float) -> void:
	_snap_to_path_start()
	settling_active = false
	last_settled_junction = -1.0
	last_roll_needed = 0.0
	tour_offset = 0.0
	# Replay the original orientation history before the chosen cut, offscreen.
	var steps := maxi(1, ceili(offset_mm / (4.0 / 240.0)))
	for i in range(1, steps + 1):
		drive_to(offset_mm * float(i) / steps, 1.0 / 240.0)
