"""Run with installed Blender --background --factory-startup --python."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *
import bpy
from mathutils import Quaternion

def mesh(name,v,f,collection):
    data=bpy.data.meshes.new(name);data.from_pydata(((v-ORIGIN)*.001).tolist(),[],f.tolist());data.update()
    obj=bpy.data.objects.new(name,data);collection.objects.link(obj)
    for p in data.polygons:p.use_smooth=True
    for domain,kind,count in [('POINT','source_vertex_id',len(v)),('FACE','source_face_id',len(f))]:
        attr=data.attributes.new(kind,'INT',domain);attr.data.foreach_set('value',np.arange(count,dtype=np.int32))
    attr=data.attributes.new('_SOURCE_ID','FLOAT','POINT');attr.data.foreach_set('value',np.arange(len(v),dtype=np.float32))
    return obj
def material(name,color):
    m=bpy.data.materials.new(name);m.diffuse_color=color;return m
def run():
    protect();a,m=inputs();package=read(OUT/'data/source_manifest.json')
    if sha(OUT/'data/edit_inputs.npz')!=package['edit_package_sha256']:raise ValueError('Edit package changed')
    d=np.load(OUT/'data/edit_inputs.npz');bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1.;scene.unit_settings.length_unit='MILLIMETERS'
    cavity_collection=bpy.data.collections.new('01_Cavity_EDIT_THIS');scene.collection.children.link(cavity_collection)
    cavity=mesh('KidneyCavity',d['cavity'],d['faces'],cavity_collection)
    cavity.data.materials.append(material('Cavity_blue',(.06,.48,.8,1)))
    cavity['status']='AWAITING_USER_MANUAL_SCULPT';cavity['basis_source_sha256']=m['arrays']['cavity_reference_vertices']['sha256']
    for name in ['Basis','Contracted','Expanded']:cavity.shape_key_add(name=name,from_mix=False)
    for i,name in enumerate(GROUPS):
        group=cavity.vertex_groups.new(name=name);group.add(np.flatnonzero(d['groups']==i).tolist(),1.,'REPLACE')
    ref=bpy.data.collections.new('02_Tissue_STATIC_REFERENCE');scene.collection.children.link(ref)
    tissue=mesh('TissueReference',d['tissue'],d['tissue_faces'],ref);tissue.data.materials.append(material('Tissue_reference',(.65,.18,.17,.16)))
    tissue.hide_set(True);tissue.hide_render=True;tissue.hide_select=True
    aux=bpy.data.collections.new('03_STATIC_MARKERS_PATHS_NOT_DEFORMED');scene.collection.children.link(aux)
    topo=read(OUT/'data/topology.json')
    for name,n in topo['nodes'].items():
        ob=bpy.data.objects.new(name,None);aux.objects.link(ob);ob.location=(np.array(n['position_mm'])-ORIGIN)*.001;ob.empty_display_type='SPHERE';ob.empty_display_size=.0007;ob.hide_select=True
    for p in topo['paths']:
        curve=bpy.data.curves.new('PATH_'+p['id'],'CURVE');curve.dimensions='3D';curve.bevel_depth=.00008
        spl=curve.splines.new('POLY');spl.points.add(len(p['points_mm'])-1)
        for point,co in zip(spl.points,p['points_mm']):point.co=tuple((np.array(co)-ORIGIN)*.001)+(1.,)
        ob=bpy.data.objects.new(curve.name,curve);aux.objects.link(ob);ob.hide_select=True
    scene['V_DEMO_NOTE']='Manual visual demo, not physiological calibration. Basis immutable. Helpers STATIC, excluded from export.'
    text=bpy.data.texts.new('READ_ME_中文');text.write('编辑 KidneyCavity 的 Contracted / Expanded，禁止编辑 Basis。详见 visual_demo/docs/Blender手工塑形指南.md。FixedPorts 分组不锁定顶点，导出时检查。静态 Marker 不跟随。当前三态相同，等待人工塑形。')
    bpy.context.view_layer.objects.active=cavity;cavity.select_set(True);cavity.active_shape_key_index=1
    cavity.show_only_shape_key=True
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                space=area.spaces.active;space.clip_start=.00001;space.clip_end=10;space.region_3d.view_distance=.20
                space.region_3d.view_rotation=Quaternion((1,0,0),1.57079632679);space.region_3d.view_perspective='ORTHO'
                space.shading.color_type='MATERIAL';space.overlay.show_floor=False
            elif area.type=='PROPERTIES':area.spaces.active.context='DATA'
    scene.tool_settings.use_proportional_edit=True;scene.tool_settings.use_proportional_connected=True
    scene.tool_settings.proportional_edit_falloff='SMOOTH'
    manual=OUT/'blender/kidney_manual_v1.blend'
    if manual.exists() and '--draft-only' not in sys.argv:raise ValueError('Manual project exists: refusing to overwrite your edits; use --draft-only for fixture')
    if '--draft-only' not in sys.argv:bpy.ops.wm.save_as_mainfile(filepath=str(manual),compress=True)
    cavity.show_only_shape_key=False
    base=np.array([x.co[:] for x in cavity.data.shape_keys.key_blocks['Basis'].data])
    for name,sign in [('Contracted',-1),('Expanded',1)]:
        coords=base+sign*d['draft']*.001;cavity.data.shape_keys.key_blocks[name].data.foreach_set('co',coords.astype(np.float32).ravel())
    cavity['status']='DRAFT_TEST_ONLY';scene['V_DEMO_NOTE']='DRAFT_TEST_ONLY: tiny automatic export fixture, never final visual approval.'
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'blender/kidney_pipeline_DRAFT_TEST_ONLY.blend'),compress=True)
    write(OUT/'reports/blender_build.json',{'Blender_version':bpy.app.version_string,'manual_file':str(manual),
        'cavity_vertices':len(cavity.data.vertices),'cavity_faces':len(cavity.data.polygons),'keys':list(cavity.data.shape_keys.key_blocks.keys()),
        'manual_keys_initially_identical':True,'draft_max_displacement_mm':float(np.linalg.norm(d['draft'],axis=1).max()),'final_approved':False})
    protect()
if __name__=='__main__':run()
