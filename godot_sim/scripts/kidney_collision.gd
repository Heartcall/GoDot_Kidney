extends StaticBody3D

## Builds a trimesh collision shape from the imported kidney mesh at runtime
## and applies the triplanar tissue shader, so the raw imported model never
## needs manual collision baking or UV setup.
##
## Note: a semi-transparent "see-through" mode (blend_mix on this cull_disabled
## 50k-tri mesh) was tried here and dropped — combined with the camera's DOF
## it reliably crashes the renderer (D3D12 and Vulkan both) on this GPU.

@export var shader_material: ShaderMaterial


func _ready() -> void:
	var mesh_instance := _find_mesh_instance(self)
	if mesh_instance == null:
		push_warning("KidneyBody: no MeshInstance3D found under imported model.")
		return

	if shader_material:
		mesh_instance.material_override = shader_material

	var shape := mesh_instance.mesh.create_trimesh_shape()
	var collision := CollisionShape3D.new()
	collision.shape = shape
	collision.transform = mesh_instance.transform
	add_child(collision)


func _find_mesh_instance(node: Node) -> MeshInstance3D:
	for child in node.get_children():
		if child is MeshInstance3D:
			return child
		var found := _find_mesh_instance(child)
		if found:
			return found
	return null
