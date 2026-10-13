@tool
extends EditorScript

# Runs in Godot's editor. Exports every Marker3D from the current scene,
# including markers inside nested Node3D groups.
const OUTPUT_DIR := "res://deformation"
const JSON_NAME := "irrigation_markers.json"
const CSV_NAME := "irrigation_markers.csv"


func _run() -> void:
	var scene_root: Node = EditorInterface.get_edited_scene_root()
	if scene_root == null:
		push_error("请先打开 irrigation_asset_check.tscn 场景。")
		return
	if scene_root.name != "IrrigationAssetCheck":
		push_error("当前场景根节点不是 IrrigationAssetCheck，请切换到 irrigation_asset_check.tscn 再运行。")
		return

	var markers: Array[Marker3D] = []
	_collect_markers(scene_root, markers)
	if markers.is_empty():
		push_error("当前场景中未找到 Marker3D。")
		return

	var err: Error = DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUTPUT_DIR))
	if err != OK:
		push_error("无法创建导出目录，错误码：%s" % err)
		return

	var records: Array[Dictionary] = []
	var seen_names: Dictionary = {}
	for marker in markers:
		var p: Vector3 = marker.global_position
		var lp: Vector3 = marker.position
		var marker_name := str(marker.name)
		seen_names[marker_name] = int(seen_names.get(marker_name, 0)) + 1
		records.append({
			"name": marker_name,
			"path": str(scene_root.get_path_to(marker)),
			"parent": str(marker.get_parent().name),
			"position_mm": [p.x, p.y, p.z],
			"local_position_mm": [lp.x, lp.y, lp.z]
		})

	var json_path := OUTPUT_DIR.path_join(JSON_NAME)
	var json_file := FileAccess.open(json_path, FileAccess.WRITE)
	if json_file == null:
		push_error("无法写入 JSON：%s，错误码：%s" % [json_path, FileAccess.get_open_error()])
		return
	var payload := {
		"source_scene": scene_root.scene_file_path,
		"coordinate_system": "Godot global (world)",
		"unit": "mm",
		"count": records.size(),
		"markers": records
	}
	json_file.store_string(JSON.stringify(payload, "  ", true, true) + "\n")
	json_file.close()

	var csv_path := OUTPUT_DIR.path_join(CSV_NAME)
	var csv_file := FileAccess.open(csv_path, FileAccess.WRITE)
	if csv_file == null:
		push_error("JSON 已导出，但 CSV 创建失败：%s" % csv_path)
		return
	# UTF-8 BOM helps Excel recognize any non-ASCII node names.
	csv_file.store_buffer(PackedByteArray([0xEF, 0xBB, 0xBF]))
	csv_file.store_csv_line(PackedStringArray([
		"name", "path", "parent", "x_mm", "y_mm", "z_mm"
	]))
	for record in records:
		var xyz: Array = record["position_mm"]
		csv_file.store_csv_line(PackedStringArray([
			str(record["name"]), str(record["path"]), str(record["parent"]),
			"%.6f" % xyz[0], "%.6f" % xyz[1], "%.6f" % xyz[2]
		]))
	csv_file.close()

	print("已导出 %d 个 Marker3D。" % records.size())
	print("JSON: ", ProjectSettings.globalize_path(json_path))
	print("CSV:  ", ProjectSettings.globalize_path(csv_path))
	for marker_name in seen_names:
		if int(seen_names[marker_name]) > 1:
			push_warning("存在同名标记 '%s'（%d 个），请使用 path 区分。" % [marker_name, seen_names[marker_name]])


func _collect_markers(node: Node, results: Array[Marker3D]) -> void:
	if node is Marker3D:
		results.append(node as Marker3D)
	for child in node.get_children():
		_collect_markers(child, results)
