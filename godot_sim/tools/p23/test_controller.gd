extends SceneTree
const Controller := preload("res://scripts/p2/irrigation_controller.gd")
var checks: Array = []
var failures: Array = []
var traces: Array = []

func _initialize() -> void:
	call_deferred("_run")

func check(label: String, condition: bool) -> void:
	checks.append({"test":label, "passed":condition})
	if not condition:
		failures.append(label)
		push_error(label)

func near(a: float, b: float, tolerance := 1e-10) -> bool:
	return absf(a-b) <= tolerance

func _run() -> void:
	var c := Controller.new()
	c.automatic_advance = false
	check("initial reference", c.state_name() == "REFERENCE" and c.filling == 0.0)
	c.inject()
	check("full injection duration", c.duration == 6.0 and c.state_name() == "FILLING")
	c.advance(3.0)
	check("injection smooth midpoint", near(c.filling, 0.5))
	c.advance(3.0)
	check("injection stops exactly at goal", c.filling == 1.0 and c.state_name() == "HOLDING")
	c.advance(100.0)
	check("holding never auto drains", c.filling == 1.0)
	c.drain()
	c.advance(3.0)
	check("drain midpoint", near(c.filling, 0.5))
	c.advance(10.0)
	check("oversized dt stops at zero", c.filling == 0.0 and c.state_name() == "RESTORED")
	c.drain()
	check("zero length drain", c.duration == 0.0 and c.state_name() == "RESTORED")
	c.reset()
	c.inject()
	c.advance(2.0)
	var prior: float = c.filling
	c.drain()
	check("midflight reverse position continuous", c.filling == prior)
	check("partial drain duration proportional", near(c.duration, prior*6.0))
	c.advance(c.duration)
	check("reverse completes", c.filling == 0.0)
	c.set_manual_fill(0.35)
	c.inject()
	check("partial inject duration proportional", near(c.duration, 3.9))
	c.advance(1.0)
	prior = c.filling
	c.set_paused(true)
	var elapsed_before: float = c.elapsed
	var remaining_before: float = c.remaining_seconds()
	c.advance(100.0)
	check("paused u and elapsed unchanged", c.filling == prior and c.elapsed == elapsed_before)
	check("pause preserves segment and remaining", c.state_name() == "FILLING" and c.remaining_seconds() == remaining_before)
	c.inject()
	check("repeated injection during pause is idempotent", c.paused and c.elapsed == elapsed_before)
	c.set_paused(false)
	c.advance(remaining_before)
	check("resume finishes remaining segment", c.filling == 1.0 and c.state_name() == "HOLDING")
	c.drain()
	c.advance(1.0)
	prior = c.filling
	c.hold()
	check("hold cancels segment", c.state_name() == "HOLDING" and not c.paused and c.remaining_seconds() == 0.0)
	c.advance(100.0)
	c.set_paused(false)
	c.advance(100.0)
	check("hold cannot resume old motion", c.filling == prior)
	c.inject()
	c.set_paused(true)
	c.set_manual_fill(0.42)
	check("manual slider cancels motion and pause", c.filling == 0.42 and c.state_name() == "HOLDING" and not c.paused)
	c.advance(100.0)
	check("no delayed command overrides manual", c.filling == 0.42)
	c.inject()
	c.set_paused(true)
	c.reset()
	c.advance(100.0)
	check("reset cancels paused motion exactly", c.filling == 0.0 and c.state_name() == "REFERENCE" and not c.paused)
	c.inject()
	c.advance(1.25)
	elapsed_before = c.elapsed
	var revision_before: int = c.command_revision
	c.inject()
	check("same command does not restart clock", c.elapsed == elapsed_before and c.command_revision == revision_before)
	c.drain()
	c.advance(0.1)
	elapsed_before = c.elapsed
	c.drain()
	check("same drain does not restart clock", c.elapsed == elapsed_before)
	c.set_manual_fill(1.0)
	c.inject()
	check("zero length injection holds", c.state_name() == "HOLDING" and c.filling == 1.0 and c.remaining_seconds() == 0.0)
	c.reset()
	c.inject()
	c.advance(1.0)
	prior = c.filling
	for dt in [0.0, -1.0, NAN, INF, -INF]:
		c.advance(dt)
	check("abnormal dt ignored", c.filling == prior and c.elapsed == 1.0)
	c.set_manual_fill(NAN)
	c.set_target(INF)
	check("nonfinite manual and target ignored", c.filling == prior and c.target_filling == 1.0)
	check("invalid durations rejected", not c.set_durations(0.0, 6.0) and not c.set_durations(NAN, 6.0))
	c.set_manual_fill(-2.0)
	check("manual lower bound", c.filling == 0.0)
	c.set_manual_fill(2.0)
	check("manual upper bound", c.filling == 1.0)
	c.set_target(0.5)
	c.inject()
	check("lower target does not drain during injection", c.filling == 1.0 and c.state_name() == "HOLDING")
	c.reset()
	c.set_target(1.0)
	c.inject()
	c.advance(1.0)
	var segment_end: float = c._end
	c.set_target(0.75)
	check("target edit does not change active segment", c._end == segment_end and c.target_filling == 0.75)
	c.advance(5.0)
	check("active target completes unchanged", c.filling == 1.0)
	c.reset()
	c.inject()
	c.advance(6.0)
	check("next command uses new target", c.filling == 0.75)
	c.set_target(1.0)
	# Compare at common absolute observation times, not just endpoints.
	for rate in [30, 60, 120, 0]:
		c.reset()
		c.inject()
		var time := 0.0
		var step := 0
		for observation in [0.25, 1.0, 2.37, 3.0, 5.9, 6.0]:
			while time < observation-1e-12:
				var dt: float = 1.0/rate if rate > 0 else [0.007, 0.041, 0.013, 0.12][step%4]
				dt = minf(dt, observation-time)
				c.advance(dt)
				time += dt
				step += 1
			var s: float = observation/6.0
			check("time partition %s at %.2f" % [rate, observation], near(c.filling, 3*s*s-2*s*s*s))
			traces.append({"rate":rate,"time":observation,"u":c.filling,"state":c.state_name()})
		check("partition endpoint exact %s" % rate, c.filling == 1.0 and c.state_name() == "HOLDING")
		c.drain()
		for i in (6*rate if rate > 0 else 6):
			c.advance(1.0/rate if rate > 0 else 1.0)
		check("drain partition endpoint exact %s" % rate, c.filling == 0.0 and c.state_name() == "RESTORED")
	# Unit regression only; no automatic-cycle feature added to preview.
	for cycle in 8:
		c.inject()
		c.advance(6.0)
		c.drain()
		c.advance(6.0)
		check("repeat endpoint no controller drift %s" % cycle, c.filling == 0.0 and c.state_name() == "RESTORED")
	check("no asynchronous callbacks or tweens", not c.get_script().source_code.contains("await ") and not c.get_script().source_code.contains("create_tween"))
	c.free()
	var directory := "res://analysis/irrigation_baseline/p23"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(directory))
	var file := FileAccess.open(directory.path_join("controller_tests.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify({"checks":checks, "failures":failures, "traces":traces}, "  "))
	file.close()
	print("P2_CONTROLLER_TESTS ", checks.size(), " passed=", checks.size()-failures.size(), " failures=", failures)
	quit(0 if failures.is_empty() else 1)
