@tool
extends EditorScript

# Godot 4.x EditorScript: export all Marker3D positions in multiple coordinate
# spaces, including the LOCAL coordinate system of the actual cavity mesh.
# READ ONLY for scene nodes; writes JSON and CSV under res://deformation.
const OUTPUT_DIR := "res://deformation"
const JSON_NAME := "irrigation_markers.json"
const CSV_NAME := "irrigation_markers.csv"
const CAVITY_REFERENCE_NAME := "CavityReference"


func _run() -> void:
    var root: Node = EditorInterface.get_edited_scene_root()
    if root == null or not (root is Node3D):
        push_error("请打开包含标记的 3D 场景 irrigation_asset_check.tscn。")
        return
    if root.scene_file_path.get_file() != "irrigation_asset_check.tscn":
        push_warning("当前不是 irrigation_asset_check.tscn，请确认导出场景正确：%s" % root.scene_file_path)

    var reference: Node = root.find_child(CAVITY_REFERENCE_NAME, true, false)
    if reference == null:
        push_error("找不到 CavityReference。请在场景树检查名字。")
        return

    var cavity_mesh: MeshInstance3D = null
    if reference is MeshInstance3D:
        cavity_mesh = reference as MeshInstance3D
    else:
        var candidates: Array[MeshInstance3D] = []
        _collect_meshes(reference, candidates)
        if candidates.size() != 1:
            push_error("CavityReference 下面找到 %d 个 MeshInstance3D（需要恰好一个）；请调整选择逻辑。" % candidates.size())
            return
        cavity_mesh = candidates[0]

    if cavity_mesh.mesh == null:
        push_error("CavityReference 对应 MeshInstance3D 没有 Mesh 资源。")
        return
    if absf(cavity_mesh.global_transform.basis.determinant()) < 0.00000001:
        push_error("CavityReference 网格变换不可逆：有一个轴缩放接近 0。")
        return

    var markers: Array[Marker3D] = []
    _collect_markers(root, markers)
    if markers.is_empty():
        push_error("场景内没有 Marker3D。")
        return

    # A name-only topology requires globally unique names.
    var names: Dictionary = {}
    for marker in markers:
        var name_text := str(marker.name)
        if names.has(name_text):
            push_error("存在重复的 Marker3D 名称：%s。请先解决重名。" % name_text)
            return
        names[name_text] = true

    var root_3d := root as Node3D
    var records: Array[Dictionary] = []
    var parent_transforms: Dictionary = {}
    var max_roundtrip_error := 0.0
    var offsets: Array[Vector3] = []

    for marker in markers:
        var world: Vector3 = marker.global_position
        var parent_local: Vector3 = marker.position
        var cavity_local: Vector3 = cavity_mesh.to_local(world)
        var scene_local: Vector3 = root_3d.to_local(world)
        var offset: Vector3 = world - parent_local
        var roundtrip_error := cavity_mesh.to_global(cavity_local).distance_to(world)
        max_roundtrip_error = maxf(max_roundtrip_error, roundtrip_error)
        offsets.append(offset)

        var parent_3d := marker.get_parent_node_3d()
        var parent_path := ""
        if parent_3d != null:
            parent_path = str(root.get_path_to(parent_3d))
            if not parent_transforms.has(parent_path):
                parent_transforms[parent_path] = _transform_data(parent_3d.global_transform)

        records.append({
            "name": str(marker.name),
            "path": str(root.get_path_to(marker)),
            "parent": str(marker.get_parent().name),
            "parent_path": parent_path,
            "top_level": marker.top_level,
            "position_mm": _vec(world),  # ORIGINAL KEY: world, keep compatibility
            "local_position_mm": _vec(parent_local), # ORIGINAL KEY: local to parent
            "global_position_mm": _vec(world),
            "parent_local_position_mm": _vec(parent_local),
            "scene_local_position_mm": _vec(scene_local),
            "cavity_local_position_mm": _vec(cavity_local),
            "world_minus_parent_local_mm": _vec(offset),
            "cavity_local_roundtrip_error_mm": roundtrip_error
        })

    var first_offset := offsets[0]
    var max_offset_difference := 0.0
    for offset in offsets:
        max_offset_difference = maxf(max_offset_difference, offset.distance_to(first_offset))

    var payload := {
        "schema_version": "2.0",
        "source_scene": root.scene_file_path,
        "coordinate_system": "Godot global (world) for position_mm; explicit cavity-local field added",
        "unit": "mm",
        "unit_note": "Project convention: one Godot spatial unit is treated as one millimeter",
        "count": records.size(),
        "recommended_geometry_coordinate_field": "cavity_local_position_mm",
        "reference_mesh": {
            "node_path": str(root.get_path_to(cavity_mesh)),
            "mesh_resource_path": cavity_mesh.mesh.resource_path,
            "global_transform": _transform_data(cavity_mesh.global_transform),
            "local_transform": _transform_data(cavity_mesh.transform)
        },
        "scene_root_global_transform": _transform_data(root_3d.global_transform),
        "marker_parent_global_transforms": parent_transforms,
        "diagnostics": {
            "first_world_minus_parent_local_mm": _vec(first_offset),
            "max_difference_between_marker_offsets_mm": max_offset_difference,
            "max_cavity_coordinate_roundtrip_error_mm": max_roundtrip_error,
            "offset_meaning": "Offset comparison is diagnostic only; it does NOT establish the cavity mesh coordinate system."
        },
        "markers": records
    }

    if max_roundtrip_error > 0.001:
        push_error("Cavity-local 坐标往返误差超过 0.001 mm：%f" % max_roundtrip_error)
        return

    var dir_error := DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUTPUT_DIR))
    if dir_error != OK:
        push_error("无法创建目录 %s，错误码 %d" % [OUTPUT_DIR, dir_error])
        return

    var json_path := OUTPUT_DIR.path_join(JSON_NAME)
    var json_file := FileAccess.open(json_path, FileAccess.WRITE)
    if json_file == null:
        push_error("无法写入 %s，错误码 %d" % [json_path, FileAccess.get_open_error()])
        return
    json_file.store_string(JSON.stringify(payload, "  ") + "\n")
    json_file.close()

    var csv_path := OUTPUT_DIR.path_join(CSV_NAME)
    var csv_file := FileAccess.open(csv_path, FileAccess.WRITE)
    if csv_file == null:
        push_error("JSON 已导出，但 CSV 无法写入 %s" % csv_path)
        return
    csv_file.store_buffer(PackedByteArray([0xEF, 0xBB, 0xBF]))
    csv_file.store_csv_line(PackedStringArray([
        "name", "path", "parent_path",
        "world_x_mm", "world_y_mm", "world_z_mm",
        "cavity_x_mm", "cavity_y_mm", "cavity_z_mm",
        "parent_local_x_mm", "parent_local_y_mm", "parent_local_z_mm",
        "scene_x_mm", "scene_y_mm", "scene_z_mm"
    ]))
    for item in records:
        var w: Array = item["position_mm"]
        var c: Array = item["cavity_local_position_mm"]
        var p: Array = item["local_position_mm"]
        var s: Array = item["scene_local_position_mm"]
        csv_file.store_csv_line(PackedStringArray([
            str(item["name"]), str(item["path"]), str(item["parent_path"]),
            str(w[0]), str(w[1]), str(w[2]),
            str(c[0]), str(c[1]), str(c[2]),
            str(p[0]), str(p[1]), str(p[2]),
            str(s[0]), str(s[1]), str(s[2])
        ]))
    csv_file.close()

    print("=== 灌注标记坐标导出完成 ===")
    print("标记数：", records.size())
    print("腔体网格：", payload["reference_mesh"]["node_path"])
    print("局部->世界偏移样本：", first_offset)
    print("各标记偏移的最大差异：", max_offset_difference)
    print("腔体局部坐标往返误差：", max_roundtrip_error)
    print("JSON：", ProjectSettings.globalize_path(json_path))
    print("CSV：", ProjectSettings.globalize_path(csv_path))


func _vec(v: Vector3) -> Array:
    return [v.x, v.y, v.z]


func _transform_data(t: Transform3D) -> Dictionary:
    return {
        "origin": _vec(t.origin),
        "basis_x": _vec(t.basis.x),
        "basis_y": _vec(t.basis.y),
        "basis_z": _vec(t.basis.z),
        "determinant": t.basis.determinant()
    }


func _collect_markers(node: Node, output: Array[Marker3D]) -> void:
    if node is Marker3D:
        output.append(node as Marker3D)
    for child in node.get_children():
        _collect_markers(child, output)


func _collect_meshes(node: Node, output: Array[MeshInstance3D]) -> void:
    if node is MeshInstance3D:
        output.append(node as MeshInstance3D)
    for child in node.get_children():
        _collect_meshes(child, output)
