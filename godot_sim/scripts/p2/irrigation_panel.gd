extends PanelContainer
## UI adapter only. The controller owns filling; this layer never reads vertices.
signal focus_requested(location: String)
signal camera_reset_requested
signal mesh_visibility_changed(mesh_name: String, enabled: bool)
signal section_changed(enabled: bool, normal: Vector3, offset: float)

var controller: Node
var buttons := {}
var visibility_toggles := {}
var fill_slider: HSlider
var target_input: SpinBox
var fill_time_input: SpinBox
var drain_time_input: SpinBox
var state_label: Label
var parameter_message: Label
var section_toggle: CheckButton
var section_axis: OptionButton
var section_slider: HSlider
var focus_choice: OptionButton
var manual_input_events := 0
var column: VBoxContainer
var scroll: ScrollContainer
var observation_normal := Vector3.RIGHT

func bind_controller(value: Node, locations: Array) -> void:
	controller = value
	scroll = ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	add_child(scroll)
	column = VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.add_theme_constant_override("separation", 8)
	scroll.add_child(column)
	_label("肾脏注排水 · P2.3", 22)
	_label("已验收几何 · 最大腔体位移 0.2 mm")
	state_label = _label("")
	_heading("运行控制")
	var grid := GridContainer.new()
	grid.columns = 3
	column.add_child(grid)
	_button(grid, "inject", "注水", controller.inject)
	_button(grid, "hold", "保持", controller.hold)
	_button(grid, "drain", "排水", controller.drain)
	_button(grid, "pause", "暂停", func(): controller.set_paused(not controller.paused))
	_button(grid, "reset", "重置", controller.reset)
	_heading("下一次运动参数")
	target_input = _spin("目标充盈度（%）", 0.0, 100.0, 1.0, 100.0)
	fill_time_input = _spin("完整注水时长（游戏秒）", 0.1, 120.0, 0.1, 6.0)
	drain_time_input = _spin("完整排水时长（游戏秒）", 0.1, 120.0, 0.1, 6.0)
	for input: SpinBox in [target_input, fill_time_input, drain_time_input]:
		input.value_changed.connect(_parameters_edited)
	parameter_message = _label("修改参数仅影响下一次命令；当前运动段不变。")
	_heading("手动充盈度（0～1）")
	fill_slider = HSlider.new()
	fill_slider.min_value = 0.0
	fill_slider.max_value = 1.0
	fill_slider.step = 0.001
	fill_slider.value_changed.connect(_manual_fill)
	column.add_child(fill_slider)
	grid = GridContainer.new()
	grid.columns = 3
	column.add_child(grid)
	for entry in [["reference","Reference",0.0],["mid","Mid",0.5],["expanded","Expanded",1.0]]:
		_button(grid, entry[0], entry[1], controller.set_manual_fill.bind(entry[2]))
	_label("手动输入结束当前运动并进入保持；保持不会自动排水。")
	_heading("观察")
	var row := HBoxContainer.new()
	column.add_child(row)
	for name: String in ["cavity", "tissue"]:
		var toggle := CheckButton.new()
		toggle.text = "腔体" if name == "cavity" else "肾组织"
		toggle.button_pressed = true
		toggle.toggled.connect(_visibility.bind(name))
		visibility_toggles[name] = toggle
		row.add_child(toggle)
	section_toggle = CheckButton.new()
	section_toggle.text = "不透明剖切（无封口）"
	section_toggle.button_pressed = true
	section_toggle.toggled.connect(func(_enabled: bool): _emit_section())
	column.add_child(section_toggle)
	section_axis = OptionButton.new()
	for name in ["X 方向剖切", "Y 方向剖切", "Z 方向剖切", "局部定位方向"]:
		section_axis.add_item(name)
	section_axis.item_selected.connect(func(_index: int): _emit_section())
	column.add_child(section_axis)
	section_slider = HSlider.new()
	section_slider.min_value = -100.0
	section_slider.max_value = 100.0
	section_slider.step = 0.1
	section_slider.value_changed.connect(func(_offset: float): _emit_section())
	column.add_child(section_slider)
	focus_choice = OptionButton.new()
	focus_choice.add_item("ALL · 全模型")
	for name in locations:
		focus_choice.add_item(name)
	focus_choice.item_selected.connect(func(index: int): focus_requested.emit("ALL" if index == 0 else focus_choice.get_item_text(index)))
	column.add_child(focus_choice)
	_button(column, "camera_reset", "复位全局镜头", func(): camera_reset_requested.emit())
	_label("在右侧视区：左键旋转、中键平移、滚轮缩放，R 复位。定位只改变观察，不改变形变或状态。")
	_label("演示时长不代表真实流量或压力。剖切不表示真实壁厚。未接入动态碰撞、内镜或录像。")
	controller.status_changed.connect(refresh)
	refresh()

func _label(text: String, font_size := 16) -> Label:
	var label := Label.new()
	label.text = text
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_font_size_override("font_size", font_size)
	column.add_child(label)
	return label

func _heading(text: String) -> void:
	column.add_child(HSeparator.new())
	_label(text, 18)

func _button(parent: Control, key: String, title: String, action: Callable) -> void:
	var button := Button.new()
	button.text = title
	button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	button.pressed.connect(action)
	buttons[key] = button
	parent.add_child(button)

func _spin(title: String, minimum: float, maximum: float, step: float, initial: float) -> SpinBox:
	_label(title)
	var spin := SpinBox.new()
	spin.min_value = minimum
	spin.max_value = maximum
	spin.step = step
	spin.value = initial
	spin.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.add_child(spin)
	return spin

func apply_parameters(target: float, fill_time: float, drain_time: float) -> bool:
	if not is_finite(target) or not is_finite(fill_time) or not is_finite(drain_time) or target < 0.0 or target > 1.0 or fill_time < 0.1 or fill_time > 120.0 or drain_time < 0.1 or drain_time > 120.0:
		parameter_message.text = "参数无效：目标 0～100%，时长 0.1～120 秒。"
		refresh()
		return false
	controller.set_durations(fill_time, drain_time)
	controller.set_target(target)
	parameter_message.text = "已应用至下一次命令；当前运动段保持原目标与时长。"
	return true

func _parameters_edited(_value: float) -> void:
	apply_parameters(target_input.value/100.0, fill_time_input.value, drain_time_input.value)

func _manual_fill(value: float) -> void:
	manual_input_events += 1
	controller.set_manual_fill(value)

func _visibility(enabled: bool, mesh_name: String) -> void:
	mesh_visibility_changed.emit(mesh_name, enabled)

func _emit_section() -> void:
	if section_axis.selected >= 0 and section_axis.selected < 3:
		observation_normal = [Vector3.RIGHT,Vector3.UP,Vector3.BACK][section_axis.selected]
	section_changed.emit(section_toggle.button_pressed, observation_normal, section_slider.value)

func reflect_section(enabled: bool, normal: Vector3, offset: float) -> void:
	observation_normal = normal
	section_toggle.set_pressed_no_signal(enabled)
	section_slider.set_value_no_signal(offset)
	section_axis.select(0 if normal == Vector3.RIGHT else 1 if normal == Vector3.UP else 2 if normal == Vector3.BACK else 3)

func refresh() -> void:
	if state_label == null:
		return
	var names := {"REFERENCE":"参考", "FILLING":"注水", "HOLDING":"保持", "DRAINING":"排水", "RESTORED":"已恢复"}
	state_label.text = "状态：%s · %s\n当前：%.2f%%    下次目标：%.1f%%\n剩余：%.3f 游戏秒    暂停：%s" % [names[controller.state_name()],controller.state_name(),
		controller.filling*100.0,controller.target_filling*100.0,controller.remaining_seconds(),"是" if controller.paused else "否"]
	if controller.is_moving():
		state_label.text += "\n本段目标：%.1f%%（执行中保持不变）" % (controller._end*100.0)
	fill_slider.set_value_no_signal(controller.filling)
	for entry in [[target_input,controller.target_filling*100.0],[fill_time_input,controller.fill_seconds],[drain_time_input,controller.drain_seconds]]:
		var input: SpinBox = entry[0]
		if not input.get_line_edit().has_focus():
			input.set_value_no_signal(entry[1])
	buttons["pause"].text = "继续" if controller.paused else "暂停"
	buttons["pause"].disabled = not controller.is_moving()
