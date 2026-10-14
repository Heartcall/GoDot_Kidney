"""Shared read-only inputs for the independent P1.5-R2 experiment."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from research_p15_contact_mapping import inputs,ROOT as R1,AUDIT
from resolve_cavity_topology import PROJECT,read_json,json_bytes,source_record
from build_cavity_surface_masks import mesh_graph
from build_cavity_morph_states import vertex_normals
from build_local_displacement import triangle_data,normalize,smoothstep
OUT=PROJECT/'analysis/irrigation_baseline/p15_r2'
FOCUS={'F01':[34757,34758],'F02':[30718,30717,30719],'F03':[61933,61934],'F04':[30663]}


def read_inputs():
    v,f,tv,tf,d=inputs()
    old=np.load(R1/'UNACCEPTED_contact_tissue_displacement.npy')
    report=read_json(R1/'mapping_build_report.json')
    for name,digest in report['output_sha256'].items():
        if source_record(R1/name)['sha256']!=digest: raise ValueError('R1 input changed: '+name)
    ids=np.load(AUDIT/'tissue_to_cavity_face.npy');bary=np.load(AUDIT/'mapping_barycentric.npy').astype(float)
    gap=np.load(AUDIT/'tissue_to_cavity_distance_mm.npy');owner=np.load(PROJECT/'deformation/p1_masks/path_owner.npy')
    resolved=read_json(PROJECT/'deformation/cavity_topology_resolved.json')
    contact=np.zeros(len(tv),bool);contact[np.unique(tf[np.load(AUDIT/'cross_contact_pairs.npy')[:,1]])]=True
    exact=np.load(R1/'coincident_mask.npy');remote=np.load(R1/'remote_anchors.npy');ring=np.load(R1/'contact_anchors.npy')
    normals=normalize(np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]]))
    tn=vertex_normals(tv,tf);facing=np.einsum('ij,ij->i',tn,normals[ids])<-.5
    q=np.einsum('ni,nij->nj',bary,v[f[ids]])
    side=np.einsum('ij,ij->i',tv-q,normals[ids])>=-1e-5
    classes=np.full(len(tv),'D',dtype='<U1');classes[(gap<=1)&facing&side]='C'
    classes[ring]='C';classes[remote]='E';classes[contact]='B';classes[exact]='A'
    return dict(v=v,f=f,tv=tv,tf=tf,driver=d,old=old,ids=ids,bary=bary,gap=gap,owner=owner,resolved=resolved,
                contact=contact,exact=exact,remote=remote,ring=ring,classes=classes,tissue_normals=tn,cavity_normals=normals)


def record_vertex(data,index):
    d=data;paths=d['resolved']['paths'];face=d['f'][d['ids'][index]]
    return {'vertex':int(index),'reference_mm':d['tv'][index].tolist(),'displacement_mm':d['old'][index].tolist(),
        'magnitude_mm':float(np.linalg.norm(d['old'][index])),'donor_face':int(d['ids'][index]),'barycentric':d['bary'][index].tolist(),
        'donor_vertex_path_ids':[paths[int(o)]['id'] for o in d['owner'][face]],'gap_mm':float(d['gap'][index]),
        'r2_constraint_class':str(d['classes'][index]),'old_effective_constraint':('exact_coincident' if d['exact'][index] else 'contact_hard' if d['contact'][index] else 'near_wall_or_one_ring_hard' if d['ring'][index] else 'remote_zero' if d['remote'][index] else 'free_solve'),
        'old_is_one_ring_only':bool(d['ring'][index] and d['gap'][index]>1),
        'normal_dot':float(d['tissue_normals'][index]@d['cavity_normals'][d['ids'][index]]),
        'anatomical_assignment':'UNCONFIRMED' if index in (61933,61934,30663) else 'geometric donor only'}


def snapshot():
    if (OUT/'protected_before.json').exists(): return
    paths=set()
    for directory in [PROJECT/'deformation',R1,PROJECT/'analysis/irrigation_baseline/p15_mapping_probe']:
        paths.update(p for p in directory.rglob('*') if p.is_file())
    for directory,pattern in [(PROJECT/'source_assets','*.obj'),(PROJECT/'scripts','*.gd'),(PROJECT/'shaders','*.gdshader'),(PROJECT/'tools','*.py'),(PROJECT.parent/'docs','*.md'),(PROJECT,'*.tscn')]:
        paths.update(directory.glob(pattern))
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'protected_before.json').write_bytes(json_bytes({str(p.relative_to(PROJECT.parent)).replace('\\','/'):source_record(p)['sha256'] for p in sorted(paths)}))
