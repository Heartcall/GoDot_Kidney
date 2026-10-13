
@tool
extends Node3D

# 选择两个已存在的 Marker3D
@export var start_marker: Marker3D
@export var end_marker: Marker3D

# 新生成的中点名称
@export var midpoint_name: String = "B_01_P01"

# 在 Godot 检查器中显示按钮
@export_tool_button("生成 / 更新中点")
var generate_button = generate_midpoint


func generate_midpoint() -> void:
	if start_marker == null or end_marker == null:
		push_warning("请先选择起点和终点")
		return

	# 根据世界坐标计算三维中点
	var middle_position: Vector3 = (
		start_marker.global_position
		+ end_marker.global_position
	) / 2.0

	# 如果已有同名中点，就更新位置
	var middle := get_node_or_null(
		NodePath(midpoint_name)
	) as Marker3D

	# 否则新建 Marker3D
	if middle == null:
		middle = Marker3D.new()
		middle.name = midpoint_name
		add_child(middle)

		# 确保节点保存在 Godot 场景中
		middle.owner = get_tree().edited_scene_root

	middle.global_position = middle_position

	EditorInterface.mark_scene_as_unsaved()

	print("中点已生成：", midpoint_name)
	print("坐标：", middle_position)
