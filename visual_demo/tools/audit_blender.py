"""Read saved editable .blend without saving or altering it."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *
import bpy
if __name__=='__main__':
    protect();a,_=inputs();o=bpy.data.objects['KidneyCavity'];keys=o.data.shape_keys.key_blocks
    assert len(o.data.vertices)==25024 and len(o.data.polygons)==50044
    assert np.array_equal(np.array([p.vertices[:] for p in o.data.polygons]),a['cavity_faces'])
    base=np.array([p.co[:] for p in keys['Basis'].data]);check_basis(base,a['cavity_reference_vertices'])
    assert all(np.array_equal(np.array([p.co[:] for p in k.data]),base) for k in keys)
    counts={g.name:sum(any(x.group==g.index for x in v.groups) for v in o.data.vertices) for g in o.vertex_groups}
    assert counts['FixedPorts']==3675 and counts['J_01']==67 and counts['OtherJunctions']==595
    write(OUT/'reports/manual_blend_audit.json',{'version':bpy.app.version_string,'blend_sha256':sha(bpy.data.filepath),
        'saved_Basis_matches_accepted_float32_edit_coordinates':True,'initial_keys_identical':True,'source_triangle_order_exact':True,
        'group_counts':counts,'static_marker_count':sum(o.type=='EMPTY' for o in bpy.data.collections['03_STATIC_MARKERS_PATHS_NOT_DEFORMED'].objects),
        'static_paths':sum(o.type=='CURVE' for o in bpy.data.collections['03_STATIC_MARKERS_PATHS_NOT_DEFORMED'].objects),
        'status':'READY_FOR_USER_SCULPT_NOT_FINAL_VISUAL_APPROVAL'})
    protect();print('Saved manual Blender project audited; no save performed',flush=True)
