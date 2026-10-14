extends Node3D
## Pure geometry consumer. No irrigation state, timers, collision or analysis cache.

signal geometry_updated(value: float, milliseconds: float)
const DATA_DIR := "res://deformation/p2"
const SECTION_SHADER := preload("res://shaders/audit_section.gdshader")
var filling := -1.0
var update_count := 0
var last_update_ms := 0.0
var timing_samples: Array = []
var data := {}
var nodes := {}
var materials: Array[ShaderMaterial] = []
var ready_ok := false
var failure_message := ""
## P2.3 timings; readback occurs only on explicit validation export.
var last_phase_ms := {}
var readback_count := 0

func _ready() -> void:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(DATA_DIR.path_join("accepted_inputs.json")))
	if not parsed is Dictionary or parsed.get("schema") != "P2_ACCEPTED_INPUTS_V1":
		_fail("P2 manifest missing or invalid")
		return
	for name: String in ["cavity", "tissue"]:
		var record: Dictionary = parsed["binaries"][name]
		var path := DATA_DIR.path_join(record["path"])
		if FileAccess.get_sha256(path) != str(record["sha256"]):
			_fail("P2 runtime hash mismatch: " + name)
			return
		var file := FileAccess.open(path, FileAccess.READ)
		var magic := file.get_buffer(8).get_string_from_ascii()
		var n := int(file.get_32())
		var m := int(file.get_32())
		if magic != "P2DG0001" or file.get_length() != 16 + n*24 + m*12 or n != int(record["vertices"]) or m != int(record["triangles"]):
			_fail("P2 invalid runtime format: " + name)
			return
		data[name] = {"reference": _read_vectors(file, n), "displacement": _read_vectors(file, n),
			"indices": file.get_buffer(m*12).to_int32_array()}
		file.close()
		# Constant colors are shared across poses; they carry no deformation state.
		var colors := PackedColorArray()
		colors.resize(n)
		colors.fill(Color(0.15, 0.65, 0.95) if name == "cavity" else Color(0.85, 0.48, 0.48))
		data[name]["colors"] = colors
		var node := MeshInstance3D.new()
		node.name = name.capitalize()
		add_child(node)
		nodes[name] = node
		var material := ShaderMaterial.new()
		material.shader = SECTION_SHADER
		node.material_override = material
		materials.append(material)
	ready_ok = true
	set_section(true, Vector3.RIGHT, 0.0)
	set_filling(0.0)

func _fail(message: String) -> void:
	failure_message = message
	push_error(message)
	get_tree().quit(1)

func _read_vectors(file: FileAccess, count: int) -> PackedVector3Array:
	var flat := file.get_buffer(count*12).to_float32_array()
	var vectors := PackedVector3Array()
	vectors.resize(count)
	for i in count:
		vectors[i] = Vector3(flat[3*i], flat[3*i+1], flat[3*i+2])
	return vectors

func _normals(positions: PackedVector3Array, indices: PackedInt32Array) -> PackedVector3Array:
	var result := PackedVector3Array()
	result.resize(positions.size())
	for k in range(0, indices.size(), 3):
		var a := indices[k]
		var b := indices[k+1]
		var c := indices[k+2]
		# Godot index order is reversed from OBJ; this matches approved R2 normals.
		var normal := (positions[c]-positions[a]).cross(positions[b]-positions[a])
		result[a] += normal
		result[b] += normal
		result[c] += normal
	for i in result.size():
		result[i] = result[i].normalized()
	return result

func set_filling(u: float) -> void:
	if not ready_ok or not is_finite(u):
		return
	var value := clampf(u, 0.0, 1.0)
	if value == filling:
		return
	var start_us := Time.get_ticks_usec()
	var pending := {}
	var phases := {"positions_ms":0.0,"normals_ms":0.0,"colors_ms":0.0,"mesh_create_ms":0.0,"commit_ms":0.0,"readback_ms":0.0}
	for name: String in ["cavity", "tissue"]:
		var tick := Time.get_ticks_usec()
		var positions: PackedVector3Array = data[name]["reference"].duplicate()
		var field: PackedVector3Array = data[name]["displacement"]
		for i in positions.size():
			positions[i] += value * field[i]
		phases["positions_ms"] += (Time.get_ticks_usec()-tick)/1000.0
		var indices: PackedInt32Array = data[name]["indices"]
		var arrays := []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = positions
		tick = Time.get_ticks_usec()
		arrays[Mesh.ARRAY_NORMAL] = _normals(positions, indices)
		phases["normals_ms"] += (Time.get_ticks_usec()-tick)/1000.0
		arrays[Mesh.ARRAY_INDEX] = indices
		tick = Time.get_ticks_usec()
		arrays[Mesh.ARRAY_COLOR] = data[name]["colors"]
		phases["colors_ms"] += (Time.get_ticks_usec()-tick)/1000.0
		tick = Time.get_ticks_usec()
		var mesh := ArrayMesh.new()
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		pending[name] = mesh
		phases["mesh_create_ms"] += (Time.get_ticks_usec()-tick)/1000.0
	# No await between commits: both meshes use this single value in the same frame.
	for name: String in ["cavity", "tissue"]:
		var tick := Time.get_ticks_usec()
		nodes[name].mesh = pending[name]
		phases["commit_ms"] += (Time.get_ticks_usec()-tick)/1000.0
	filling = value
	update_count += 1
	last_update_ms = (Time.get_ticks_usec()-start_us)/1000.0
	last_phase_ms = phases
	timing_samples.append({"u":value, "update_ms":last_update_ms})
	# Keep bounded diagnostics during interactive use.
	if timing_samples.size() > 256:
		timing_samples.pop_front()
	geometry_updated.emit(value, last_update_ms)

func set_section(enabled: bool, normal: Vector3, offset: float) -> void:
	for material in materials:
		material.set_shader_parameter("section_enabled", enabled)
		material.set_shader_parameter("section_normal", normal)
		material.set_shader_parameter("section_offset", offset)

func set_mesh_visible(mesh_name: String, enabled: bool) -> void:
	if nodes.has(mesh_name):
		nodes[mesh_name].visible = enabled

func export_actual(directory: String, tag: String) -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(directory))
	for name: String in ["cavity", "tissue"]:
		# Export the ACTUAL ArrayMesh arrays, not the input buffer.
		var arrays: Array = nodes[name].mesh.surface_get_arrays(0)
		readback_count += 1
		var file := FileAccess.open(directory.path_join(name+"_"+tag+".bin"), FileAccess.WRITE)
		file.store_buffer((arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).to_byte_array())
		file.store_buffer((arrays[Mesh.ARRAY_NORMAL] as PackedVector3Array).to_byte_array())
		file.store_buffer((arrays[Mesh.ARRAY_INDEX] as PackedInt32Array).to_byte_array())
		file.close()
