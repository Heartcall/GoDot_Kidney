"""Read artist's v3, inspect then export a NEW GLB. NEVER save the .blend."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from endo_common import *
import bpy
def run():
    protect();a,_=inputs();o=bpy.data.objects.get('KidneyCavity')
    if not o:raise ValueError('KidneyCavity missing in manual v3')
    source_hash=sha(BLEND)
    if Path(bpy.data.filepath).resolve()!=BLEND.resolve():raise ValueError('Wrong Blender input; only manual v3 authorized')
    keys=o.data.shape_keys.key_blocks
    if list(keys.keys())!=['Basis','Contracted','Expanded']:raise ValueError('Unexpected shape keys '+str(list(keys.keys())))
    f=np.array([p.vertices[:] for p in o.data.polygons]);v=np.array([p.co[:] for p in keys['Basis'].data])
    if len(v)!=25024 or not np.array_equal(f,a['cavity_faces']):raise ValueError('Source topology changed')
    if o.modifiers:raise ValueError('Modifiers present; no unreviewed topology change')
    matrix=np.array(o.matrix_world);report={'source_blend_sha256':source_hash,'Blender':bpy.app.version_string,
        'object_matrix':matrix.tolist(),'keys':list(keys.keys()),'vertices':len(v),'triangles':len(f),'shapes':{},'materials':[]}
    if not np.allclose(matrix,np.eye(4),atol=1e-10,rtol=0):raise ValueError('Manual object transform requires explicit alignment review: '+str(matrix))
    expected=((a['cavity_reference_vertices']-ORIGIN)*.001).astype(np.float32)
    report['Basis_reference_max_error_mm']=float(abs(v-expected).max()*1000)
    if not np.array_equal(v,expected):raise ValueError('Manual Basis differs from accepted reference; stop and report')
    fixed=np.load(PROJECT/'deformation/p2/evidence/port_fixed_masks.npy').any(0);shapes={}
    for k in keys:
        x=np.array([p.co[:] for p in k.data]);delta=(x-v)*1000
        if not np.isfinite(x).all():raise ValueError('Nonfinite key '+k.name)
        shapes[k.name]=a['cavity_reference_vertices']+delta
        report['shapes'][k.name]={'max_displacement_mm':float(np.linalg.norm(delta,axis=1).max()),
            'fixed_moved_vertices':np.flatnonzero(fixed & (np.linalg.norm(delta,axis=1)>0)).tolist(),
            'fixed_max_displacement_mm':float(np.linalg.norm(delta[fixed],axis=1).max())}
    for m in o.data.materials:
        row={'name':m.name,'diffuse_color':list(m.diffuse_color)}
        if m.use_nodes:
            p=next((n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
            if p:
                row['base_color']=list(p.inputs['Base Color'].default_value);row['roughness']=p.inputs['Roughness'].default_value
        report['materials'].append(row)
    np.savez(ROOT/'data/manual_v3_shapes_RAS_mm.npz',**shapes,faces=f)
    write(ROOT/'reports/manual_v3_inspection.json',report)
    # Clear animation ONLY in this disposable in-memory session: export targets,
    # not Blender's existing action, and preserve the artist's disk file exactly.
    if o.data.shape_keys.animation_data:o.data.shape_keys.animation_data_clear()
    o.show_only_shape_key=False;o.active_shape_key_index=0
    for k in keys:k.value=0
    bpy.ops.object.select_all(action='DESELECT');o.hide_set(False);o.hide_render=False;o.hide_select=False;o.select_set(True)
    bpy.context.view_layer.objects.active=o;bpy.context.view_layer.update()
    available=set(bpy.ops.export_scene.gltf.get_rna_type().properties.keys())
    opts={'filepath':str(GLB),'export_format':'GLB','use_selection':True,'export_yup':True,'export_apply':False,
        'export_morph':True,'export_morph_normal':True,'export_animations':False,'export_extras':True,'export_attributes':True,
        'export_texcoords':False,'export_normals':True,'export_materials':'EXPORT','export_try_sparse_sk':False}
    if not set(opts)<=available:raise ValueError('Unsupported export API')
    bpy.ops.export_scene.gltf(**opts)
    report.update({'GLB_sha256':sha(GLB),'export_options':opts,'disk_blend_unchanged':sha(BLEND)==source_hash,'contains_only_dynamic_cavity':True})
    write(ROOT/'reports/manual_v3_inspection.json',report);protect();print('MANUAL V3 exported; original unchanged',flush=True)
if __name__=='__main__':run()
