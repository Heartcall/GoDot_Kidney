"""Light geometry, GLB provenance and actual Godot baked-shape comparisons."""
from common import *
import struct
from scipy.spatial import cKDTree

def glb(path):
    raw=Path(path).read_bytes();magic,version,size=struct.unpack_from('<III',raw);assert magic==0x46546c67 and version==2 and size==len(raw)
    offset=12;doc=None;buf=None
    while offset<len(raw):
        length,kind=struct.unpack_from('<II',raw,offset);chunk=raw[offset+8:offset+8+length];offset+=8+length
        if kind==0x4e4f534a:doc=json.loads(chunk)
        elif kind==0x004e4942:buf=chunk
    def access(i):
        a=doc['accessors'][i];v=doc['bufferViews'][a['bufferView']];dtype={5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[a['componentType']]
        count={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']];dt=np.dtype(dtype);stride=v.get('byteStride',dt.itemsize*count)
        assert 'sparse' not in a
        return np.ndarray((a['count'],count),dtype=dt,buffer=buf,offset=v.get('byteOffset',0)+a.get('byteOffset',0),strides=(stride,dt.itemsize)).copy()
    return doc,access
def to_godot(x):
    b=(x-ORIGIN)*.001;return b[:,[0,2,1]]*np.array([1,1,-1])
def run():
    protect();a,_=inputs();source=np.load(OUT/'data/shape_keys_source_RAS_mm.npz');d,acc=glb(PROJECT/'visual_demo/assets/kidney_visual_DRAFT.glb')
    mesh=next(x for x in d['meshes'] if x['name']=='KidneyCavity');p=mesh['primitives'][0]
    assert mesh['extras']['targetNames']==['Contracted','Expanded'] and len(p['targets'])==2
    pos=acc(p['attributes']['POSITION']);ids=acc(p['attributes']['_SOURCE_ID']).ravel().astype(int)
    f=acc(p['indices']).reshape(-1,3);assert np.array_equal(ids[f],a['cavity_faces'])
    expected=to_godot(source['Basis']);glb_error=float(abs(pos-expected[ids]).max());assert glb_error<1e-8
    ds=[acc(x['POSITION']) for x in p['targets']]
    for delta,name in zip(ds,['Contracted','Expanded']):
        assert np.max(abs(pos+delta-to_godot(source[name])[ids]))<1e-8
    normals=acc(p['attributes']['NORMAL']);assert np.isfinite(normals).all() and np.min(np.linalg.norm(normals,axis=1))>.99
    tissue=next(x for x in d['meshes'] if x['name']=='TissueReference')['primitives'][0]
    tissue_ids=acc(tissue['attributes']['_SOURCE_ID']).ravel().astype(int)
    tissue_pos=acc(tissue['attributes']['POSITION'])
    assert np.array_equal(tissue_ids[acc(tissue['indices']).reshape(-1,3)],a['tissue_faces'])
    tissue_error=float(abs(tissue_pos-to_godot(a['tissue_reference_vertices'])[tissue_ids]).max());assert tissue_error<1e-8
    states=[]
    for s in [-1.,-.5,0.,.5,1.]:
        path=OUT/f'reports/godot_state_{s:.1f}.bin'
        if not path.exists():raise ValueError('Actual Godot runtime dump missing: '+str(path))
        actual=np.fromfile(path,dtype='<f4').reshape(-1,3)
        expected=pos+max(-s,0)*ds[0]+max(s,0)*ds[1]
        # Symmetric nearest-surface-vertex test tolerates GLB/Godot reindexing.
        e1=cKDTree(expected).query(actual)[0];e2=cKDTree(actual).query(expected)[0]
        maxerr=float(max(e1.max(),e2.max()));assert maxerr<2e-7
        states.append({'s':s,'Godot_vertices':len(actual),'symmetric_vertex_position_error_m':maxerr})
    report={'status':'DRAFT_TEST_ONLY','source_vertices':25024,'source_faces':50044,'GLB_vertices':len(pos),'actual_GLTF_source_face_mapping_exact':True,
        'source_index_attribute':'_SOURCE_ID; GLB provenance only, Godot ordering not assumed','GLB_reference_max_error_m':glb_error,
        'transform_determinant':1,'basis_bounds_RAS_mm':[source['Basis'].min(0).tolist(),source['Basis'].max(0).tolist()],
        'GLB_bounds_m':[pos.min(0).tolist(),pos.max(0).tolist()],'Godot_actual_five_states':states,
        'normals_finite':True,'strict_collision_or_physiology_certification':False,'final_visual_approved':False}
    report['static_tissue']={'vertices':len(tissue_pos),'triangles':len(a['tissue_faces']),'GLB_source_mapping_exact':True,'reference_max_error_m':tissue_error}
    write(OUT/'reports/pipeline_validation.json',report);protect();print('GLB + actual Godot five states verified',flush=True)
if __name__=='__main__':run()
