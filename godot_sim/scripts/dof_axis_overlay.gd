extends Control

## Debug-only overlay: draws a fixed line across the screen at the
## camera/1DOF roll offset (a device-rigid constant, same value regardless of
## camera roll -- see Instruction/apply_roll_correction.py in the sibling
## /home/leo/project repo where this was calibrated: -68.2 deg in image
## y-down convention, i.e. the same convention used here since Godot's 2D
## Control space is also y-down). Lets you eyeball, while the auto-tour's
## roll-then-bend maneuver plays, whether the virtual camera's turning
## actually looks like it's rotating around that axis the way the real robot
## would.
##
## Toggle with L. Defaults to visible, but this draws directly into the root
## viewport that EndoscopeController._save_capture() grabs -- if you leave it
## on during a real tour run meant to produce a training/eval dataset, this
## line WILL be baked into every saved frame. Press L to turn it off first.

@export var axis_deg: float = -68.2
@export var line_color: Color = Color(1, 1, 0)
@export var line_width: float = 3.0

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	resized.connect(queue_redraw)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_L:
		visible = not visible


func _draw() -> void:
	var center := size / 2.0
	var rad := deg_to_rad(axis_deg)
	var dir := Vector2(cos(rad), sin(rad))
	var length := size.length()
	draw_line(center - dir * length, center + dir * length, line_color, line_width, true)

	var arrow_tip := center + dir * 90.0
	var back := -dir.rotated(deg_to_rad(25))
	var back2 := -dir.rotated(deg_to_rad(-25))
	draw_line(arrow_tip, arrow_tip + back * 20.0, line_color, line_width, true)
	draw_line(arrow_tip, arrow_tip + back2 * 20.0, line_color, line_width, true)

	var label := "1DOF axis (%+.1f deg, device-rigid) -- L to toggle" % axis_deg
	var font := ThemeDB.fallback_font
	var font_size := 20
	draw_string_outline(font, Vector2(16, 30), label, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, 4, Color.BLACK)
	draw_string(font, Vector2(16, 30), label, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, line_color)
