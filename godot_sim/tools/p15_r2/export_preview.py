"""Diagnostic binary export: references, unchanged cavity driver, R1/R2 tissue fields."""
import struct
from common import *
from build_local_displacement import normalize


def export():
    d=read_inputs();field=np.load(OUT/'research_tissue_displacement.npy');origin=np.array([16.,16.,-81.])
    for name,v,f,before,after in [('cavity',d['v'],d['f'],d['driver'],d['driver']),('tissue',d['tv'],d['tf'],d['old'],field)]:
        _,edges,length=mesh_graph(v,f);gradients=[]
        for displacement in [before,after]:
            gradient=np.linalg.norm(displacement[edges[:,0]]-displacement[edges[:,1]],axis=1)/length
            gv=np.zeros(len(v));np.maximum.at(gv,edges[:,0],gradient);np.maximum.at(gv,edges[:,1],gradient);gradients.append(gv)
        centered=(v-origin).astype(np.float32);ref_area=np.linalg.norm(np.cross(centered[f[:,1]]-centered[f[:,0]],centered[f[:,2]]-centered[f[:,0]]),axis=1)/2
        raw=bytearray(b'R2MP0001'+struct.pack('<II',len(v),len(f)))
        for array in [centered,before,after,*gradients,ref_area]: raw.extend(np.asarray(array,dtype='<f4').tobytes())
        raw.extend(np.asarray(f[:,::-1],dtype='<u4').tobytes());(OUT/(name+'_preview.bin')).write_bytes(raw)
    meta=read_json(R1/'audit_preview.json');meta['groups']=[g for g in meta['groups'] if g['id'].startswith('F')]
    meta['sources']['approved_cavity_driver']=source_record(PROJECT/'deformation/full_cavity/field/displacement.npy')
    meta['sources']['R1_tissue_field']=source_record(R1/'UNACCEPTED_contact_tissue_displacement.npy')
    meta['sources']['R2_tissue_field']=source_record(OUT/'research_tissue_displacement.npy')
    graph,edges,_=mesh_graph(d['tv'],d['tf'])
    for group in meta['groups']:
        mask=np.zeros(len(d['tv']),bool);mask[FOCUS[group['id']]]=True
        for _ in range(2): mask[edges[mask[edges].any(axis=1)].ravel()]=True
        group['reference_faces']=np.flatnonzero(mask[d['tf']].any(axis=1)).tolist()
    meta['binary_sha256']={name:source_record(OUT/(name+'_preview.bin'))['sha256'] for name in ['cavity','tissue']}
    meta['status']='RESEARCH_ONLY_PENDING_FULL_REVIEW';meta['unit']='mm';meta['maximum_displacement_mm']=.2
    if (OUT/'quality_report.json').exists(): meta['status']=read_json(OUT/'quality_report.json')['status']
    (OUT/'preview.json').write_bytes(json_bytes(meta));print('exported diagnostic preview',meta['status'],flush=True)

if __name__=='__main__': export()
