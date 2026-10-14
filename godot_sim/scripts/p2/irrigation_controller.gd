extends Node
## Demonstration timing only: no pressure/flow law, no geometry or deferred jobs.

signal filling_changed(value: float)
signal status_changed

enum State { REFERENCE, FILLING, HOLDING, DRAINING, RESTORED }

@export var automatic_advance := true
var state: State = State.REFERENCE
var paused := false
var filling := 0.0
var target_filling := 1.0
var fill_seconds := 6.0
var drain_seconds := 6.0
var elapsed := 0.0
var duration := 0.0
var command_revision := 0
var _start := 0.0
var _end := 0.0

func _process(delta: float) -> void:
	if automatic_advance:
		advance(delta)

func is_moving() -> bool:
	return state == State.FILLING or state == State.DRAINING

func remaining_seconds() -> float:
	return maxf(0.0, duration - elapsed) if is_moving() else 0.0

func state_name() -> String:
	return State.keys()[state]

func set_target(value: float) -> void:
	if not is_finite(value):
		return
	target_filling = clampf(value, 0.0, 1.0)
	status_changed.emit()

func set_durations(fill_time: float, drain_time: float) -> bool:
	if not is_finite(fill_time) or not is_finite(drain_time) or fill_time <= 0.0 or drain_time <= 0.0:
		return false
	# Changes apply to the next command; an active segment keeps its duration.
	fill_seconds = fill_time
	drain_seconds = drain_time
	status_changed.emit()
	return true

func inject() -> void:
	# A target below current filling never makes an injection command drain.
	if target_filling <= filling:
		hold()
		return
	_begin(State.FILLING, target_filling, fill_seconds)

func drain() -> void:
	_begin(State.DRAINING, 0.0, drain_seconds)

func _begin(next_state: State, end: float, full_seconds: float) -> void:
	# Repeating a command, including during pause, never restarts its clock.
	if state == next_state and _end == end:
		return
	command_revision += 1
	paused = false
	_start = filling
	_end = end
	elapsed = 0.0
	duration = full_seconds * absf(_end - _start)
	state = next_state
	if duration == 0.0:
		state = State.HOLDING if next_state == State.FILLING else State.RESTORED
	status_changed.emit()

func hold() -> void:
	command_revision += 1
	state = State.HOLDING
	paused = false
	elapsed = 0.0
	duration = 0.0
	_start = filling
	_end = filling
	status_changed.emit()

func set_paused(value: bool) -> void:
	paused = value if is_moving() else false
	status_changed.emit()

func set_manual_fill(value: float) -> void:
	if not is_finite(value):
		return
	hold()
	_assign_fill(clampf(value, 0.0, 1.0))
	_start = filling
	_end = filling
	status_changed.emit()

func reset() -> void:
	command_revision += 1
	state = State.REFERENCE
	paused = false
	elapsed = 0.0
	duration = 0.0
	_start = 0.0
	_end = 0.0
	_assign_fill(0.0)
	status_changed.emit()

func advance(delta: float) -> void:
	if not is_finite(delta) or delta <= 0.0 or paused or not is_moving():
		return
	elapsed = minf(duration, elapsed + delta)
	if duration - elapsed <= 1e-9 * maxf(1.0, duration):
		elapsed = duration
	var s := clampf(elapsed / duration, 0.0, 1.0)
	var value := _start + (_end - _start) * (3.0*s*s - 2.0*s*s*s)
	if elapsed >= duration:
		value = _end
		state = State.HOLDING if state == State.FILLING else State.RESTORED
	_assign_fill(value)
	status_changed.emit()

func _assign_fill(value: float) -> void:
	if filling == value:
		return
	filling = value
	filling_changed.emit(filling)
