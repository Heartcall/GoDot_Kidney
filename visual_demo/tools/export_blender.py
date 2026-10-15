"""Validate current .blend; only then export cavity+tissue GLB and source-order shapes."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *
import bpy

def run():
    protect();a,m=inputs();o=bpy.data.objects.get('KidneyCavity')
    if not o or o.type!='MESH':raise ValueError('KidneyCavity missing')
    if o.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
    f=np.array([p.vertices[:] for p in o.data.polygons]);n=len(o.data.vertices)
    if n!=25024 or f.shape!=(50044,3) or not np.array_equal(f,a['cavity_faces']):raise ValueError('Topology/order changed')
    if o.modifiers or not np.allclose(np.array(o.matrix_world),np.eye(4),rtol=0,atol=1e-10):raise ValueError('Modifiers/object transform present; remove through reviewed workflow')
    ids=np.array([x.value for x in o.data.attributes['source_vertex_id'].data])
    if not np.array_equal(ids,np.arange(n)):raise ValueError('Source vertex attribute changed')
    faceids=np.array([x.value for x in o.data.attributes['source_face_id'].data])
    if not np.array_equal(faceids,np.arange(len(f))):raise ValueError('Source face attribute changed')
    keys=o.data.shape_keys.key_blocks
    if list(keys.keys())!=['Basis','Contracted','Expanded']:raise ValueError('Need exactly Basis, Contracted, Expanded in order')
    base=np.array([x.co[:] for x in keys['Basis'].data]);check_basis(base,a['cavity_reference_vertices'])
    fixed=np.load(PROJECT/'deformation/p2/evidence/port_fixed_masks.npy').any(0)
    source={};violations={};report={}
    for key in keys:
        x=np.array([p.co[:] for p in key.data]);delta=(x-base)*1000
        if not np.isfinite(x).all():raise ValueError('NaN/Inf in '+key.name)
        changed=fixed_changes(delta,fixed)
        if changed:violations[key.name]=changed
        source[key.name]=a['cavity_reference_vertices']+delta
        tri=source[key.name][f];cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);ref=a['cavity_reference_vertices'][f];rc=np.cross(ref[:,1]-ref[:,0],ref[:,2]-ref[:,0])
        area=np.linalg.norm(cross,axis=1);rlen=np.linalg.norm(rc,axis=1)
        report[key.name]={'max_displacement_mm':float(np.linalg.norm(delta,axis=1).max()),'degenerate_faces':np.flatnonzero(area<1e-12).tolist(),
            'reversed_vs_reference':np.flatnonzero((cross*rc).sum(1)<=0).tolist(),'minimum_area_ratio':float((area/rlen).min())}
    output=OUT/'reports/export_validation.json';write(output,{'fixed_violations':violations,'quality':report,'status':o.get('status'),'strict_continuous_safety_certified':False})
    if violations:raise ValueError('FixedPorts moved: see '+str(output))
    if any(x['degenerate_faces'] or x['reversed_vs_reference'] for x in report.values()):raise ValueError('Degenerate/reversed faces: inspect report, no silent repair')
    np.savez(OUT/'data/shape_keys_source_RAS_mm.npz',**source,faces=f)
    # Zero weights for export Basis, restore artist's UI selection afterwards.
    saved=[k.value for k in keys];only=o.show_only_shape_key;o.show_only_shape_key=False
    for k in keys:k.value=0
    bpy.ops.object.select_all(action='DESELECT');o.select_set(True)
    tissue=bpy.data.objects['TissueReference'];tissue.hide_set(False);tissue.hide_render=False;tissue.hide_select=False;tissue.select_set(True)
    bpy.context.view_layer.objects.active=o
    available=set(bpy.ops.export_scene.gltf.get_rna_type().properties.keys())
    options={'filepath':str(PROJECT/'visual_demo/assets/kidney_visual_DRAFT.glb'),'export_format':'GLB','use_selection':True,
        'export_yup':True,'export_apply':False,'export_morph':True,'export_morph_normal':True,'export_animations':False,'export_extras':True,'export_attributes':True,
        'export_texcoords':False,'export_normals':True,'export_materials':'EXPORT','export_try_sparse_sk':False}
    if not set(options)<=available:raise ValueError('Unrecognized glTF API options '+str(set(options)-available))
    bpy.ops.export_scene.gltf(**options)
    for k,value in zip(keys,saved):k.value=value
    o.show_only_shape_key=only
    write(OUT/'reports/export_api.json',{'version':bpy.app.version_string,'verified_options':options,'source_blend_sha256':sha(bpy.data.filepath),
        'source_basis_quantization_error_mm':float(np.max(abs(base*1000+ORIGIN-a['cavity_reference_vertices']))),
        'exported_source_coordinates':'original Reference + (Blender key-Blender Basis)*1000; preserves authoritative Reference exactly',
        'status':o.get('status'),'final_approved':False})
    protect()
if __name__=='__main__':run()
