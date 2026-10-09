extends CharacterBody3D

## Endoscope tip navigation.
## Manual mode: mouse-look + WASD/QE fly movement with collision sliding.
## Auto-tour mode (toggle with T): follows a pre-computed path
## (res://data/cavity_path.json: {"points": [[x,y,z],...], "forwards": [[x,y,z],...]})
## and periodically saves the rendered frame + pose to res://captures/.
##
## "forwards" is optional and holds one look-direction per point, independent
## of the direction of travel -- this is what lets a retreat segment (points
## re-visited in reverse order) keep the camera facing the original forward/
## insertion direction instead of spinning around to face where it's moving.
## If omitted, look direction falls back to the raw motion tangent (old
## behaviour, fine for a simple one-way path with no retreat).
##
## "pauses" is optional: a list of arc-length offsets (meters, same units as
## the point coordinates) at which the tour holds still for `pause_duration`
## seconds -- e.g. one entry per target arrival, so the tour dwells at each
## stone before continuing. While paused, frames are still saved every
## `pause_capture_interval` seconds (wall-clock, since no distance is being
## covered for the normal distance-triggered capture to fire on).
##
## "speeds" is optional: one multiplier per point (0-1), applied on top of
## tour_speed -- e.g. lower near sharp turns so the camera slows down while
## reorienting instead of whipping through it at the same speed as a
## straight stretch. If omitted, speed is constant (multiplier 1.0) everywhere.
##
## "junctions" is optional: arc-length offsets (mm) of real branch points the
## path passes through (see optimize_for_robot/export_cavity_path_for_godot.py
## -- sourced from PathPlanning's topology graph, degree>=3 skeleton nodes,
## not a curvature heuristic).
##
## Orientation is NOT a free look_at(). The real robot only has 2 DOF to
## redirect the tip: roll (spin the whole shaft about its own long axis) and
## bend (within the single plane that roll currently selects, fixed at
## dof_axis_offset_deg from the camera's own right axis -- a device-rigid
## constant, see scripts/dof_axis_overlay.gd). With "junctions" loaded, the
## tour deliberately does NOT keep re-deriving ROLL every tick: a single
## corridor doesn't twist around its own axis, so there's nothing to adjust
## while travelling one. Instead, roll is LOCKED except during an explicit
## "settling" phase, entered once junction_lookahead_mm before each
## junction: _target_basis() is computed ONCE against the path pose
## junction_lookahead_mm PAST that junction (a fixed target, so it doesn't
## drift as tour_offset keeps advancing through the approach), delivery speed
## is eased by junction_settle_speed_scale so rolling gets ahead of movement
## instead of happening alongside it, and _step_toward() rate-limits the
## rotation (quaternion slerp, max_rotation_rate_deg) toward that fixed
## target -- also always keeping the commanded roll within +-90deg, see
## _target_basis's comment. Once close enough (or the junction is physically
## reached), settling ends and roll locks again at whatever it reached --
## "调节好之后，就以目前的姿态走过去就好了." While cruising (roll locked),
## _cruise_free_basis() freely reorients FORWARD to track the path's own
## current tangent directly, with no bend-plane restriction (per
## conversation, the device's bend limit no longer constrains cruising),
## while roll itself never moves except during settling. Without "junctions"
## loaded, there's no way to know where a real fork is, so this falls back
## to the old behaviour: re-deriving and tracking the path direction (roll
## included) every tick, continuously, everywhere.
##
## (An earlier version of the always-tracking mode rate-limited roll and bend
## separately and iterated them together tick to tick -- that turned out to
## be a genuine feedback instability near large roll angles, not just slow.
## _target_basis computes the full exact target in one closed-form step and
## _step_toward rotates toward it via quaternion slerp instead, which is the
## standard, numerically robust way to do a rate-limited "rotate toward" --
## verified stable against this project's real cavity path data.)

@export var move_speed: float = 25.0  # mm/s, manual mode
@export var boost_multiplier: float = 3.0
@export var mouse_sensitivity: float = 0.0025
@export var max_pitch_deg: float = 85.0

@export var cavity_path_file: String = "res://data/organ_1_kidney/lab_1/cavity_path_stone1.json"
@export var tour_speed: float = 4.0          # mm/s along the path (slowed down from 8.0)
@export var capture_interval_distance: float = 0.0665  # mm between saved frames (tour_speed/60, ~60fps-equivalent)
@export var pause_duration: float = 3.0          # seconds to hold still at each entry in "pauses"
@export var pause_capture_interval: float = 0.1  # seconds between saved frames while paused
@export var capture_dir: String = "res://captures"
@export var captures_enabled: bool = false  # temporarily off while tuning tour navigation -- flip back to true for a real capture run
@export var junction_snapshots_enabled: bool = true  # save a before/after pair of images (capture_dir/organ_id/lab_id/stone_id/) around each junction's roll settling, independent of captures_enabled
@export var landmark_ref_samples: int = 80  # how many jittered reference views to render for the "before" side of each junction landmark (see _save_junction_reference_set) -- "after" stays a single snapshot
@export var landmark_ref_pos_radius_mm: float = 5.0  # sample positions within this radius (mm) of the landmark, uniform in volume
@export var landmark_ref_bend_max_deg: float = 10.0  # sample look directions within this cone half-angle (deg) of the landmark's own forward
@export var landmark_ref_roll_max_deg: float = 20.0  # additional +- roll (deg) around the sampled look direction
@export var loop_tour: bool = false

@export var dof_axis_offset_deg: float = 68.2  # 1DOF bend axis vs camera frame -- device-rigid constant, but SIGN-FLIPPED from the -68.2 in scripts/dof_axis_overlay.gd, because that one draws directly in 2D screen space (y-down, matches cv2 convention) while this one is a 3D Vector3.rotated() around the camera's own forward axis, which -- verified earlier this session via render screenshot, same as main.tscn's Camera3D roll -- uses the OPPOSITE rotation sign convention from cv2's image-space rotation. The real robot can only bend in THIS plane, roll picks where that plane points.
@export var max_rotation_rate_deg: float = 40.0  # deg/s cap on the combined roll+bend reorientation rate -- lower = gentler/less frequent-feeling turning, at the cost of lagging the path more during sharp sections
@export var lookahead_distance_mm: float = 3.0  # (fallback mode only, no "junctions" loaded) orient toward the path direction this far AHEAD of the current position every tick
@export var junction_lookahead_mm: float = 15.0  # ONLY for roll/settling: a junction this close ahead starts the settling phase, and the settling target roll is read from the path pose this far PAST the junction -- one distance, used both ways
@export var cruise_bend_lookahead_mm: float = 0.5  # ONLY for the free forward-reorientation while cruising (roll locked, see _cruise_free_basis): orient toward the path direction this far ahead of the current position every tick -- kept separate from junction_lookahead_mm so tuning one never affects the other. Small-but-nonzero (not 0) so _sample_path always has a well-defined direction even on data with no "forwards" array (falls back to a raw point-to-point difference, which degenerates at exactly 0). Lowered from 3.0mm per conversation: cruising should track the path's own current tangent as tightly as possible ("光心沿着路径"), not ease toward a point further ahead.
@export var junction_settle_speed_scale: float = 0.35  # delivery speed multiplier while settling (rolling toward a junction's target) is still in progress -- so rolling gets ahead of movement instead of happening alongside it -- 1.0 = no slowdown
@export var settle_done_threshold_deg: float = 2.0  # settling ends once the remaining gap to the target orientation drops below this (or the junction is physically reached)
@export var debug_overlay_path: NodePath  # DebugOverlay CanvasLayer (1DOF axis line + path guide arrow) -- hidden while any capture image is grabbed, see _capture_image, so saved frames stay clean of debug drawing

@onready var head: Node3D = $Head
@onready var camera: Camera3D = $Head/Camera3D
@onready var debug_overlay: CanvasLayer = (get_node(debug_overlay_path) as CanvasLayer) if debug_overlay_path != NodePath() else null

var pitch: float = 0.0

var path_points: PackedVector3Array = PackedVector3Array()
var path_forwards: PackedVector3Array = PackedVector3Array()  # empty if not provided
var path_speeds: PackedFloat32Array = PackedFloat32Array()  # empty if not provided (-> constant 1.0)
var cum_lengths: PackedFloat32Array = PackedFloat32Array()
var total_length: float = 0.0
var pause_offsets: PackedFloat32Array = PackedFloat32Array()
var junction_offsets: PackedFloat32Array = PackedFloat32Array()  # empty if not provided -> roll re-derives everywhere

var tour_active: bool = false
var tour_offset: float = 0.0
var last_capture_offset: float = -1000.0
var capture_index: int = 0
var pending_capture: bool = false
var next_pause_idx: int = 0
var pause_timer: float = 0.0
var pause_capture_timer: float = 0.0

# persistent tour orientation state (see class doc comment above) -- replaces
# per-frame look_at() so roll only changes via the rate-limited roll+bend model
var current_look_basis: Basis = Basis.IDENTITY
# the roll angle most recently computed by _target_basis (always kept within
# +-90deg, see its comment) -- kept only so the diagnostic print there can
# report how much it changed at each junction
var last_roll_needed: float = 0.0

# junction-settling state (only used when junction_offsets is non-empty)
var settling_active: bool = false
var capturing_reference_set: bool = false  # true while _save_junction_reference_set is mid-capture -- freezes the tour so its own position/orientation updates don't fight the sampled-pose renders
var settling_target_roll: float = 0.0
var settling_junction_offset: float = -1.0
var last_settled_junction: float = -1.0  # so a junction we just finished settling for, but haven't physically reached yet, doesn't immediately re-trigger


func _ready() -> void:
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	_load_cavity_path()
	_snap_to_path_start()
	# Headless dataset generation: `godot --path . -- --autotest-tour`
	if "--autotest-tour" in OS.get_cmdline_user_args():
		call_deferred("_toggle_tour")
	# One-off snapshot at an arbitrary world-space point, e.g. for eyeballing
	# a specific labeled skeleton point from the PathPlanning tool:
	# `godot --path . -- --photo-at=x,y,z,dx,dy,dz,out_dir_name`
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--photo-at="):
			var parts := arg.trim_prefix("--photo-at=").split(",")
			var pos := Vector3(float(parts[0]), float(parts[1]), float(parts[2]))
			var dir := Vector3.FORWARD
			if parts.size() >= 6:
				dir = Vector3(float(parts[3]), float(parts[4]), float(parts[5]))
			var out_dir := "res://" + (parts[6] if parts.size() >= 7 else "captures_photo")
			call_deferred("_take_single_photo", pos, dir, out_dir)
	# Batch of nearby jittered poses (small position/rotation variation around
	# one target point), e.g. for sampling several views around a labeled
	# skeleton point instead of just one:
	# `godot --path . -- --photo-set=res://data/poses.json,out_dir_name`
	# poses.json: {"poses": [{"pos": [x,y,z], "dir": [dx,dy,dz]}, ...]}
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--photo-set="):
			var parts := arg.trim_prefix("--photo-set=").split(",")
			var json_path := parts[0]
			var out_dir := "res://" + (parts[1] if parts.size() >= 2 else "captures_photo_set")
			call_deferred("_take_photo_set", json_path, out_dir)


func _load_cavity_path() -> void:
	if not FileAccess.file_exists(cavity_path_file):
		push_warning("EndoscopeController: cavity path file not found at %s (auto-tour disabled until it exists)" % cavity_path_file)
		return

	var f := FileAccess.open(cavity_path_file, FileAccess.READ)
	var data: Variant = JSON.parse_string(f.get_as_text())
	f.close()

	if typeof(data) != TYPE_DICTIONARY or not data.has("points"):
		push_warning("EndoscopeController: malformed cavity path file.")
		return

	path_points = PackedVector3Array()
	for p in data["points"]:
		path_points.append(Vector3(p[0], p[1], p[2]))

	path_forwards = PackedVector3Array()
	if data.has("forwards") and data["forwards"].size() == path_points.size():
		for d in data["forwards"]:
			var v := Vector3(d[0], d[1], d[2])
			path_forwards.append(v.normalized() if v.length() > 0.00001 else Vector3.FORWARD)

	path_speeds = PackedFloat32Array()
	if data.has("speeds") and data["speeds"].size() == path_points.size():
		for s in data["speeds"]:
			path_speeds.append(float(s))

	cum_lengths = PackedFloat32Array()
	cum_lengths.append(0.0)
	for i in range(1, path_points.size()):
		cum_lengths.append(cum_lengths[i - 1] + path_points[i].distance_to(path_points[i - 1]))
	total_length = cum_lengths[-1] if cum_lengths.size() > 0 else 0.0

	pause_offsets = PackedFloat32Array()
	if data.has("pauses"):
		for v in data["pauses"]:
			pause_offsets.append(float(v))

	junction_offsets = PackedFloat32Array()
	if data.has("junctions"):
		for v in data["junctions"]:
			junction_offsets.append(float(v))

	print("EndoscopeController: loaded cavity path with %d points, length %.4f m%s%s%s" % [
		path_points.size(), total_length,
		" (explicit look directions)" if path_forwards.size() > 0 else "",
		" (%d pause points)" % pause_offsets.size() if pause_offsets.size() > 0 else "",
		" (%d junctions)" % junction_offsets.size() if junction_offsets.size() > 0 else ""
	])


## Binary-searches cum_lengths for the segment containing `offset`, then
## linearly interpolates position; look direction comes from path_forwards
## if present (slerp between the segment's two endpoint directions), else
## falls back to the segment's own motion tangent.
func _sample_path(offset: float) -> Dictionary:
	offset = clamp(offset, 0.0, total_length)
	var n := path_points.size()
	if n < 2:
		return {"pos": global_position, "dir": Vector3.FORWARD}

	var lo := 0
	var hi := n - 1
	while lo < hi - 1:
		var mid := (lo + hi) / 2
		if cum_lengths[mid] <= offset:
			lo = mid
		else:
			hi = mid

	var seg_len: float = cum_lengths[hi] - cum_lengths[lo]
	var t: float = 0.0 if seg_len < 0.00001 else (offset - cum_lengths[lo]) / seg_len
	var pos: Vector3 = path_points[lo].lerp(path_points[hi], t)

	var dir: Vector3
	if path_forwards.size() == n:
		dir = path_forwards[lo].slerp(path_forwards[hi], t)
		if dir.length() < 0.00001:
			dir = path_forwards[lo]
	else:
		dir = path_points[hi] - path_points[lo]

	var speed_scale: float = 1.0
	if path_speeds.size() == n:
		speed_scale = lerp(path_speeds[lo], path_speeds[hi], t)

	return {"pos": pos, "dir": dir, "speed_scale": speed_scale}


func _snap_to_path_start() -> void:
	# Spawn exactly where the auto-tour begins, facing along the path, so
	# pressing T never causes a visible jump from an unrelated start pose.
	if path_points.size() < 2:
		return

	var sample := _sample_path(0.0)
	global_position = sample["pos"]
	head.rotation = Vector3.ZERO
	pitch = 0.0
	var dir: Vector3 = sample["dir"]
	if dir.length() > 0.00001:
		_apply_orientation(dir.normalized(), Vector3.UP)
	else:
		current_look_basis = global_transform.basis


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED and not tour_active:
		rotate_y(-event.relative.x * mouse_sensitivity)
		pitch = clamp(
			pitch - event.relative.y * mouse_sensitivity,
			deg_to_rad(-max_pitch_deg),
			deg_to_rad(max_pitch_deg)
		)
		head.rotation.x = pitch

	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_ESCAPE:
			if Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
				Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
			else:
				Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
		elif event.keycode == KEY_T:
			_toggle_tour()


func _toggle_tour() -> void:
	if path_points.size() < 2:
		push_warning("EndoscopeController: no cavity path loaded, cannot start tour.")
		return

	tour_active = not tour_active
	if tour_active:
		tour_offset = 0.0
		last_capture_offset = -1000.0
		capture_index = 0
		next_pause_idx = 0
		pause_timer = 0.0
		pause_capture_timer = 0.0
		last_roll_needed = 0.0
		settling_active = false
		settling_junction_offset = -1.0
		last_settled_junction = -1.0
		head.rotation = Vector3.ZERO
		var start_dir: Vector3 = _sample_path(0.0)["dir"]
		if start_dir.length() > 0.00001:
			_apply_orientation(start_dir.normalized(), Vector3.UP)
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("%s/images" % capture_dir))
		# fresh groundtruth.txt for this run (TUM format: timestamp tx ty tz qx qy qz qw),
		# same layout stella_vslam itself writes to results/*/frame_trajectory.txt,
		# so evo can diff them directly
		var gt := FileAccess.open("%s/groundtruth.txt" % capture_dir, FileAccess.WRITE)
		gt.close()
		print("EndoscopeController: auto-tour started, saving frames to ", capture_dir)
	else:
		print("EndoscopeController: auto-tour stopped at ", capture_index, " frames.")


func _physics_process(delta: float) -> void:
	if tour_active:
		_physics_process_tour(delta)
	else:
		_physics_process_manual(delta)


func _physics_process_tour(delta: float) -> void:
	if capturing_reference_set:
		return  # frozen mid-landmark-reference-set capture, see _save_junction_reference_set
	if pause_timer > 0.0:
		pause_timer -= delta
		pause_capture_timer += delta
		if pause_capture_timer >= pause_capture_interval:
			pause_capture_timer = 0.0
			pending_capture = true
		if pause_timer <= 0.0 and tour_offset >= total_length:
			tour_active = false
			print("EndoscopeController: reached end of cavity path, tour complete (", capture_index, " frames).")
		return

	if junction_offsets.size() == 0:
		_advance_continuous(delta)
	else:
		_advance_junction_gated(delta)


## Fallback when no "junctions" data is loaded: re-derive and track the path
## direction every tick, continuously, everywhere (the only option without
## knowing where a real fork is).
func _advance_continuous(delta: float) -> void:
	var speed_scale: float = _sample_path(tour_offset)["speed_scale"]
	_advance_offset_and_housekeeping(speed_scale, delta)
	var look_dir: Vector3 = _sample_path(tour_offset + lookahead_distance_mm)["dir"]
	if look_dir.length() > 0.00001:
		_step_toward(_target_basis(look_dir.normalized()), delta)


## Normal mode: orientation is frozen except while settling_active. Enters
## settling junction_lookahead_mm before the next unsettled junction, and
## exits once close enough to the (fixed) target or the junction is
## physically reached -- "先把周转调节好再做递送...调节好之后，就以目前的姿态走过去就好了."
func _advance_junction_gated(delta: float) -> void:
	if not settling_active:
		var upcoming := _upcoming_junction_offset(tour_offset)
		if upcoming >= 0.0 and upcoming != last_settled_junction and upcoming - tour_offset <= junction_lookahead_mm:
			_start_settling(upcoming)

	var speed_scale: float = _sample_path(tour_offset)["speed_scale"]
	if settling_active:
		speed_scale *= junction_settle_speed_scale
	_advance_offset_and_housekeeping(speed_scale, delta)

	if settling_active:
		# roll ALONE, forward direction untouched -- "周转是单独调节的"
		_step_roll_only(delta)
		if absf(settling_target_roll - last_roll_needed) < deg_to_rad(settle_done_threshold_deg) \
				or tour_offset >= settling_junction_offset:
			settling_active = false
			last_settled_junction = settling_junction_offset
			_save_junction_snapshot(settling_junction_offset, "after")
	else:
		# roll stays locked (last_roll_needed untouched, only ever set at
		# junction settling); forward is freely reoriented to track the
		# path's own current tangent instead -- per conversation, cruising
		# no longer needs to stay within the device's single bend plane
		# ("现在没有bend这个约束了"), so _cruise_free_basis just points
		# straight at the path direction with no plane restriction.
		var look_dir: Vector3 = _sample_path(tour_offset + cruise_bend_lookahead_mm)["dir"]
		if look_dir.length() > 0.00001:
			_step_toward(_cruise_free_basis(look_dir.normalized()), delta)


## Starts settling toward junction_offset: computes the target ROLL ONLY
## (see _compute_target_roll), against the path pose junction_lookahead_mm
## PAST it -- a single fixed point for the whole approach+crossing, instead
## of a continuously-advancing lookahead that would drift (and visibly
## wobble) as tour_offset keeps moving through the approach.
func _start_settling(junction_offset: float) -> void:
	var ref: Vector3 = _sample_path(junction_offset + junction_lookahead_mm)["dir"]
	settling_target_roll = last_roll_needed
	if ref.length() > 0.00001:
		settling_target_roll = _compute_target_roll(ref.normalized())
	var delta_deg: float = rad_to_deg(settling_target_roll - last_roll_needed)
	if absf(delta_deg) > 0.5:
		print("EndoscopeController: 周转 @ %.1fmm -> %.1f° (本次变化 %+.1f°)" % [
			junction_offset, rad_to_deg(settling_target_roll), delta_deg])
	settling_active = true
	settling_junction_offset = junction_offset
	_save_junction_reference_set(junction_offset)


## Advances tour_offset by speed_scale*tour_speed*delta, handles pause points
## and end-of-path/looping, and updates position + the distance-triggered
## capture flag. Shared by both advance modes.
func _advance_offset_and_housekeeping(speed_scale: float, delta: float) -> void:
	tour_offset += tour_speed * speed_scale * delta

	if next_pause_idx < pause_offsets.size() and tour_offset >= pause_offsets[next_pause_idx]:
		# snap exactly to the pause point and hold there for pause_duration,
		# instead of overshooting past it this tick
		tour_offset = pause_offsets[next_pause_idx]
		next_pause_idx += 1
		pause_timer = pause_duration
		pause_capture_timer = 0.0
	elif tour_offset >= total_length:
		if loop_tour:
			tour_offset = fmod(tour_offset, total_length)
		else:
			tour_offset = total_length
			tour_active = false
			print("EndoscopeController: reached end of cavity path, tour complete (", capture_index, " frames).")

	global_position = _sample_path(tour_offset)["pos"]

	if tour_offset - last_capture_offset >= capture_interval_distance:
		last_capture_offset = tour_offset
		pending_capture = true


## Applies an orientation given only forward + an up hint, re-orthonormalizing
## (right = forward x up_hint, up = right x forward) so small numerical drift
## from repeated `rotated()` calls never accumulates into a skewed basis.
func _apply_orientation(forward: Vector3, up_hint: Vector3) -> void:
	var f := forward.normalized()
	var r := f.cross(up_hint).normalized()
	var u := r.cross(f).normalized()
	current_look_basis = Basis(r, u, -f)
	global_transform.basis = current_look_basis


## The arc-length of the nearest known junction still AHEAD of (or at) offset,
## or -1.0 if none.
func _upcoming_junction_offset(offset: float) -> float:
	var best: float = -1.0
	for j in junction_offsets:
		if j >= offset and (best < 0.0 or j < best):
			best = j
	return best


## Computes the target roll: the 1DOF axis (dof_axis_offset_deg from the
## right axis -- device-rigid, rolls rigidly with the camera) re-derived onto
## cross(current_forward, target_forward). A pure computation -- does NOT
## touch last_roll_needed; callers (settling, or _target_basis below) decide
## when the actual state should catch up to this target and update it then.
func _compute_target_roll(target_forward: Vector3) -> float:
	var f0: Vector3 = -current_look_basis.z
	var r0: Vector3 = current_look_basis.x
	var d0 := r0.rotated(f0, deg_to_rad(dof_axis_offset_deg))

	var r1 := f0.cross(target_forward)
	if r1.length() < 0.0001:
		return last_roll_needed
	r1 = r1.normalized()
	var raw_roll: float = atan2(d0.cross(r1).dot(f0), d0.dot(r1))
	# bending is two-directional around its one axis, so d0 landing on +r1 or
	# on -r1 reach the same target_forward (bend just goes the other
	# rotational way) -- of those two solutions (180deg apart), always pick
	# whichever has magnitude <= 90deg: within that range basically any
	# target is reachable, and it keeps the commanded roll bounded to
	# +-90deg instead of letting successive junctions drift it further from
	# center (decided in conversation: "累计的周转量不要超过±90°").
	var roll_needed := raw_roll
	if roll_needed > PI / 2.0:
		roll_needed -= PI
	elif roll_needed < -PI / 2.0:
		roll_needed += PI
	return roll_needed


## Rotates ONLY roll -- up/right around the current, UNCHANGED forward axis
## -- toward settling_target_roll, rate-limited. Forward direction (and
## hence bend) doesn't move at all during this, so roll and bend never mix:
## "周转是单独调节的". (Unlike an earlier version that rate-limited roll and
## bend together via one combined quaternion slerp toward a full target
## orientation -- separating them like this is safe here specifically
## because the target is a single fixed value computed once at
## _start_settling, not recomputed each tick from a moving reference, which
## is what made an even earlier per-tick-iterative version unstable.)
func _step_roll_only(delta: float) -> void:
	var remaining := settling_target_roll - last_roll_needed
	if absf(remaining) < 0.00001:
		return
	var max_step: float = deg_to_rad(max_rotation_rate_deg) * delta
	var step: float = clamp(remaining, -max_step, max_step)
	var f0: Vector3 = -current_look_basis.z
	current_look_basis = current_look_basis.rotated(f0, step).orthonormalized()
	global_transform.basis = current_look_basis
	last_roll_needed += step


## Computes the FULL, exact target orientation: forward = target_forward, and
## the 1DOF axis re-derived per _compute_target_roll -- i.e. what a complete
## roll-then-bend would reach if applied all the way, right now. Only used by
## the no-"junctions" fallback mode (_advance_continuous), where roll and
## bend still move together every tick since there's no known junction to
## separate them around. A single closed-form computation (not iterative),
## so it has no notion of "how fast" -- that's added separately in
## _step_toward. Also updates last_roll_needed and logs the new roll value.
func _target_basis(target_forward: Vector3) -> Basis:
	var f0: Vector3 = -current_look_basis.z
	var u0: Vector3 = current_look_basis.y
	var r0: Vector3 = current_look_basis.x
	var d0 := r0.rotated(f0, deg_to_rad(dof_axis_offset_deg))

	var roll_needed := _compute_target_roll(target_forward)
	var delta_deg: float = rad_to_deg(roll_needed - last_roll_needed)
	if absf(delta_deg) > 0.5:
		print("EndoscopeController: 周转 -> %.1f° (本次变化 %+.1f°)" % [rad_to_deg(roll_needed), delta_deg])
	last_roll_needed = roll_needed

	var rolled_up := u0.rotated(f0, roll_needed)
	var bend_axis := d0.rotated(f0, roll_needed)  # wherever the 1DOF axis actually lands

	# Bend within the plane perpendicular to bend_axis, toward whichever point
	# in that plane is closest to target_forward -- exact when target_forward
	# lies in the plane already (guaranteed here, since roll was just derived
	# to make that true), included for robustness if this is ever called
	# without that guarantee holding.
	var target_in_plane := target_forward - bend_axis * target_forward.dot(bend_axis)
	if target_in_plane.length() < 0.0001:
		return current_look_basis  # target lies along the axis itself -- no defined bend direction
	target_in_plane = target_in_plane.normalized()
	var bend_angle: float = atan2(f0.cross(target_in_plane).dot(bend_axis), f0.dot(target_in_plane))

	var final_forward := f0.rotated(bend_axis, bend_angle)
	var final_up := rolled_up.rotated(bend_axis, bend_angle)
	var r := final_forward.cross(final_up).normalized()
	var u := r.cross(final_forward).normalized()
	return Basis(r, u, -final_forward)


## Cruising (between junctions, roll locked at last_roll_needed): freely
## reorients forward to point exactly at target_forward, with NO bend-plane
## restriction -- per conversation, the device's single-bend-axis limit no
## longer constrains cruising ("现在没有bend这个约束了"), only junction
## settling still owns roll explicitly (_start_settling/_step_roll_only).
## Uses the minimal rotation (one axis-angle pair) that carries the CURRENT
## forward onto target_forward, applying that same rotation to up as well,
## so no incidental roll is introduced beyond what pointing at target_forward
## itself requires -- roll drifts only as a side effect of _step_toward's
## rate-limited slerp catching up each tick, never set here directly.
func _cruise_free_basis(target_forward: Vector3) -> Basis:
	var f0: Vector3 = -current_look_basis.z
	var u0: Vector3 = current_look_basis.y

	var axis := f0.cross(target_forward)
	if axis.length() < 0.0001:
		return current_look_basis  # already aligned (or exactly opposite -- degenerate, keep as-is)
	axis = axis.normalized()
	var angle: float = acos(clamp(f0.dot(target_forward), -1.0, 1.0))

	var final_forward := f0.rotated(axis, angle)
	var final_up := u0.rotated(axis, angle)
	var r := final_forward.cross(final_up).normalized()
	var u := r.cross(final_forward).normalized()
	return Basis(r, u, -final_forward)


## Rotates current_look_basis toward target_basis via quaternion slerp,
## capped at max_rotation_rate_deg per second. An earlier version rate-
## limited roll and bend *separately* and iterated them together tick to
## tick (roll partially, then bend around wherever that partial roll left
## the axis) -- simulating that against this project's actual cavity path
## showed it wasn't just slow to catch up, it was genuinely UNSTABLE: near
## large roll angles the error compounded roughly 1.9x per tick into a
## sustained oscillation (the reported "tumbling"). Slerping toward a fully,
## exactly computed target is the standard, numerically robust way to do a
## rate-limited "rotate toward" -- verified stable (smooth, monotonic
## convergence, no oscillation at any rate tested) against the same real
## path data.
func _step_toward(target_basis: Basis, delta: float) -> void:
	var current_quat := Quaternion(current_look_basis)
	var target_quat := Quaternion(target_basis)

	var angle := current_quat.angle_to(target_quat)
	if angle < 0.0001:
		return
	var max_angle: float = deg_to_rad(max_rotation_rate_deg) * delta
	var t: float = min(1.0, max_angle / angle)

	current_look_basis = Basis(current_quat.slerp(target_quat, t)).orthonormalized()
	global_transform.basis = current_look_basis


func _physics_process_manual(_delta: float) -> void:
	var input_dir := Vector3.ZERO
	if Input.is_key_pressed(KEY_W):
		input_dir -= transform.basis.z
	if Input.is_key_pressed(KEY_S):
		input_dir += transform.basis.z
	if Input.is_key_pressed(KEY_A):
		input_dir -= transform.basis.x
	if Input.is_key_pressed(KEY_D):
		input_dir += transform.basis.x
	if Input.is_key_pressed(KEY_E):
		input_dir += transform.basis.y
	if Input.is_key_pressed(KEY_Q):
		input_dir -= transform.basis.y

	if input_dir.length() > 0.0:
		input_dir = input_dir.normalized()

	var speed := move_speed
	if Input.is_key_pressed(KEY_SHIFT):
		speed *= boost_multiplier

	velocity = input_dir * speed
	move_and_slide()


func _process(_delta: float) -> void:
	if pending_capture:
		pending_capture = false
		if captures_enabled:
			_save_capture()


func _take_single_photo(pos: Vector3, dir: Vector3, out_dir: String) -> void:
	capture_dir = out_dir
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("%s/images" % capture_dir))
	var gt := FileAccess.open("%s/groundtruth.txt" % capture_dir, FileAccess.WRITE)
	gt.close()

	global_position = pos
	head.rotation = Vector3.ZERO
	if dir.length() > 0.00001:
		look_at(global_position + dir.normalized(), Vector3.UP)

	# let the SubViewport render at least one frame from the new pose before
	# grabbing its texture, or the capture would still show the old view
	await get_tree().process_frame
	await get_tree().process_frame
	_save_capture()
	print("EndoscopeController: single photo saved to ", capture_dir)
	await get_tree().process_frame
	get_tree().quit()


func _take_photo_set(json_path: String, out_dir: String) -> void:
	if not FileAccess.file_exists(json_path):
		push_warning("EndoscopeController: pose set file not found at %s" % json_path)
		get_tree().quit()
		return
	var f := FileAccess.open(json_path, FileAccess.READ)
	var data: Variant = JSON.parse_string(f.get_as_text())
	f.close()
	if typeof(data) != TYPE_DICTIONARY or not data.has("poses"):
		push_warning("EndoscopeController: malformed pose set file.")
		get_tree().quit()
		return

	capture_dir = out_dir
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("%s/images" % capture_dir))
	var gt := FileAccess.open("%s/groundtruth.txt" % capture_dir, FileAccess.WRITE)
	gt.close()
	capture_index = 0

	head.rotation = Vector3.ZERO
	for pose in data["poses"]:
		var p: Array = pose["pos"]
		var d: Array = pose["dir"]
		global_position = Vector3(p[0], p[1], p[2])
		var dir := Vector3(d[0], d[1], d[2])
		# "up" is optional -- rotating IT around the (fixed) look direction
		# rolls the camera around its own viewing axis without changing what's
		# in frame, unlike varying "dir" itself which pans/tilts to a
		# different view. Defaults to world up (no roll) if omitted.
		var up := Vector3.UP
		if pose.has("up"):
			var u: Array = pose["up"]
			up = Vector3(u[0], u[1], u[2])
		if dir.length() > 0.00001:
			look_at(global_position + dir.normalized(), up)
		await get_tree().process_frame
		await get_tree().process_frame
		await _save_capture()

	print("EndoscopeController: photo set saved ", capture_index, " frames to ", capture_dir)
	await get_tree().process_frame
	get_tree().quit()


## Grabs the current window frame with the debug overlay (1DOF axis line,
## path guide arrow -- both drawn in a CanvasLayer on top of everything,
## see debug_overlay_path) hidden for the grab, so saved captures reflect
## only the actual endoscope view. Toggling visible only takes effect on the
## NEXT draw pass, hence the await before grabbing.
func _capture_image() -> Image:
	var had_overlay := debug_overlay != null and debug_overlay.visible
	if had_overlay:
		debug_overlay.visible = false
	await get_tree().process_frame
	var img := get_tree().root.get_texture().get_image()
	if had_overlay:
		debug_overlay.visible = true
	return img


func _save_capture() -> void:
	var img := await _capture_image()
	img.save_png("%s/images/frame_%04d.png" % [capture_dir, capture_index])

	# TUM format: timestamp tx ty tz qx qy qz qw, one line per frame.
	# Timestamp is synthetic (capture cadence is fixed: capture_interval_distance
	# apart at constant tour_speed), just needs to be monotonically increasing
	# with the right relative spacing -- evo's Sim3 alignment doesn't care about
	# absolute epoch or which world-axis convention we used.
	var synthetic_fps := tour_speed / capture_interval_distance
	var timestamp := capture_index / synthetic_fps
	var q := Quaternion(camera.global_transform.basis.orthonormalized())
	var pos := camera.global_transform.origin
	var line := "%f %f %f %f %f %f %f %f" % [timestamp, pos.x, pos.y, pos.z, q.x, q.y, q.z, q.w]

	var gt := FileAccess.open("%s/groundtruth.txt" % capture_dir, FileAccess.READ_WRITE)
	gt.seek_end()
	gt.store_line(line)
	gt.close()

	capture_index += 1


## Saves a single still frame for a junction crossing, independent of the
## regular distance/pause-triggered capture stream (captures_enabled) -- just
## a before/after pair per junction instead of recording the whole tour.
## Awaiting a process frame first lets the orientation change just applied
## (roll about to start, or just finished) actually render before the
## texture is grabbed, same as _take_single_photo does. junction_offset is
## passed in rather than read from settling_junction_offset after the await,
## since that could have already moved on to a different junction by then.
func _save_junction_snapshot(junction_offset: float, label: String) -> void:
	if not junction_snapshots_enabled:
		return
	var img := await _capture_image()
	var subdir := "%s/%s" % [capture_dir, _capture_subdir()]
	var junction_name := "junction_%04.0fmm" % junction_offset
	var junction_dir := "%s/%s" % [subdir, junction_name]
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(junction_dir))
	var name := "%s_%s" % [junction_name, label]

	var img_path := "%s/%s.png" % [junction_dir, label]
	img.save_png(img_path)

	# same TUM-style pose fields as _save_capture's groundtruth.txt (tx ty tz
	# qx qy qz qw), but keyed by this snapshot's own name instead of a frame
	# index. Written twice: once appended to the shared per-lab/stone
	# junction_poses.txt (one file covering every junction, for quick
	# cross-junction lookups), and once as its own <label>_pose.txt right
	# next to <label>.png inside junction_dir -- mirrors before/poses.txt so
	# every saved image (before set AND after) has its pose sitting right
	# alongside it, not only in the shared file.
	var q := Quaternion(camera.global_transform.basis.orthonormalized())
	var pos := camera.global_transform.origin
	var line := "%s %f %f %f %f %f %f %f" % [name, pos.x, pos.y, pos.z, q.x, q.y, q.z, q.w]
	var pose_path := "%s/junction_poses.txt" % subdir
	var mode := FileAccess.READ_WRITE if FileAccess.file_exists(pose_path) else FileAccess.WRITE
	var pf := FileAccess.open(pose_path, mode)
	pf.seek_end()
	pf.store_line(line)
	pf.close()

	var local_pose_path := "%s/%s_pose.txt" % [junction_dir, label]
	var lpf := FileAccess.open(local_pose_path, FileAccess.WRITE)
	lpf.store_line(line)
	lpf.close()

	print("EndoscopeController: 岔道口截图已保存 -> ", img_path)


## Renders a small "reference view set" around a junction landmark instead of
## one exact snapshot -- position jittered within a landmark_ref_pos_radius_mm
## sphere, look direction within a landmark_ref_bend_max_deg cone around the
## landmark's own forward, plus an extra +-landmark_ref_roll_max_deg roll.
## Ports generate_landmark_poses.py's sample_poses() so this runs automatically
## during the T-mode tour instead of needing the separate manual script +
## --photo-set invocation. Saved to .../junction_<offset>mm/before/images/
## frame_%04d.png -- "after" stays a single _save_junction_snapshot frame.
## capturing_reference_set freezes _physics_process_tour for the duration so
## the tour's own position/orientation updates don't fight these sampled poses.
func _save_junction_reference_set(junction_offset: float) -> void:
	if not junction_snapshots_enabled:
		return
	capturing_reference_set = true
	var had_overlay := debug_overlay != null and debug_overlay.visible
	if had_overlay:
		debug_overlay.visible = false

	var base_pos := global_position
	var base_basis := current_look_basis
	var f0 := -base_basis.z
	var u0 := base_basis.y

	var junction_name := "junction_%04.0fmm" % junction_offset
	var out_dir := "%s/%s/%s/before" % [capture_dir, _capture_subdir(), junction_name]
	var images_dir := "%s/images" % out_dir
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(images_dir))

	var rng := RandomNumberGenerator.new()
	rng.randomize()

	var pose_path := "%s/poses.txt" % out_dir
	var pf := FileAccess.open(pose_path, FileAccess.WRITE)

	for i in range(landmark_ref_samples):
		var sample := _sample_landmark_offset_pose(f0, u0, rng, base_pos)
		global_position = base_pos + sample["pos_offset"]
		_apply_orientation(sample["dir"], sample["up"])

		# overlay already hidden for the whole capture set (above), so a
		# single frame wait here is enough -- no per-frame toggle needed
		await get_tree().process_frame
		await get_tree().process_frame

		var frame_name := "frame_%04d" % i
		var img := get_tree().root.get_texture().get_image()
		img.save_png("%s/%s.png" % [images_dir, frame_name])

		# same TUM-style fields as _save_junction_snapshot's junction_poses.txt,
		# one line per sampled reference view so each frame's actual rendered
		# pose (not just the nominal landmark pose) is recoverable later.
		var q := Quaternion(camera.global_transform.basis.orthonormalized())
		var pos := camera.global_transform.origin
		pf.store_line("%s %f %f %f %f %f %f %f" % [frame_name, pos.x, pos.y, pos.z, q.x, q.y, q.z, q.w])

	pf.close()

	global_position = base_pos
	_apply_orientation(f0, u0)
	if had_overlay:
		debug_overlay.visible = true
	await get_tree().process_frame

	capturing_reference_set = false
	print("EndoscopeController: landmark参考视图集已保存 -> ", images_dir, " (", landmark_ref_samples, " 张)")


const LANDMARK_REF_WALL_MARGIN_MM: float = 0.5  # keep sampled positions at least this far short of any tissue wall hit, so a jittered view never ends up embedded in/clipping through the mesh (see conversation: "确保不穿模") -- matters much more now that landmark_ref_pos_radius_mm was raised from 2mm to 5mm, since a 5mm sphere is more likely to poke through a nearby wall in a narrow cavity than a 2mm one was


## One jittered pose around a landmark's own forward/up (f0/u0), matching
## generate_landmark_poses.py's sample_poses(): position offset uniform-in-
## volume within landmark_ref_pos_radius_mm, bend direction uniform-in-solid-
## angle within a landmark_ref_bend_max_deg cone around f0 (randomly-rotated
## perpendicular axis + sqrt(u)-scaled angle), plus an additional
## +-landmark_ref_roll_max_deg roll around the bent forward axis.
##
## base_pos is the landmark's own (un-jittered) position -- the sampled radius
## is clamped, via a raycast from base_pos toward the sampled offset direction
## against the tissue's real collision mesh, to stop LANDMARK_REF_WALL_MARGIN_MM
## short of any wall hit -- otherwise a large-enough radius can place the
## camera on the far side of (or straddling) a nearby cavity wall.
func _sample_landmark_offset_pose(f0: Vector3, u0: Vector3, rng: RandomNumberGenerator, base_pos: Vector3) -> Dictionary:
	var offset_dir := Vector3(rng.randfn(), rng.randfn(), rng.randfn()).normalized()
	var offset_r := landmark_ref_pos_radius_mm * pow(rng.randf(), 1.0 / 3.0)

	var space_state := get_world_3d().direct_space_state
	var query := PhysicsRayQueryParameters3D.create(base_pos, base_pos + offset_dir * offset_r)
	query.exclude = [get_rid()]
	var hit := space_state.intersect_ray(query)
	if hit:
		var hit_dist: float = base_pos.distance_to(hit["position"])
		offset_r = max(0.0, min(offset_r, hit_dist - LANDMARK_REF_WALL_MARGIN_MM))

	var pos_offset := offset_dir * offset_r

	var rand_dir := Vector3(rng.randfn(), rng.randfn(), rng.randfn()).normalized()
	var perp := f0.cross(rand_dir).normalized()
	var bend_angle := deg_to_rad(landmark_ref_bend_max_deg) * sqrt(rng.randf())
	var bend_dir_angle := rng.randf_range(0.0, TAU)
	perp = perp.rotated(f0, bend_dir_angle)
	var f1 := f0.rotated(perp, bend_angle).normalized()
	var u1 := u0.rotated(perp, bend_angle)

	var roll_angle := deg_to_rad(rng.randf_range(-landmark_ref_roll_max_deg, landmark_ref_roll_max_deg))
	u1 = u1.rotated(f1, roll_angle).normalized()

	return {"pos_offset": pos_offset, "dir": f1, "up": u1}


## Derives "organ_id/lab_id/stone_id" from cavity_path_file's own path (e.g.
## "res://data/organ_1_kidney/lab_1/cavity_path_stone1.json" ->
## "organ_1_kidney/lab_1/stone1") instead of a separate set of exports, so
## captures always land under the lab/stone that was actually loaded and
## can't drift out of sync with it.
func _capture_subdir() -> String:
	var stone_part := cavity_path_file.get_file().get_basename().replace("cavity_path_", "")
	var dir_parts := cavity_path_file.get_base_dir().split("/")
	var lab_part := dir_parts[-1] if dir_parts.size() >= 1 else "lab_unknown"
	var organ_part := dir_parts[-2] if dir_parts.size() >= 2 else "organ_unknown"
	return "%s/%s/%s" % [organ_part, lab_part, stone_part]
