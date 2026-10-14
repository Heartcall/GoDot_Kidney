"""Verify REAL Godot ArrayMesh exports against independently computed float32 trajectories."""
import argparse
from common import *
from research_p15_contact_mapping import verify_pairs
from audit_tissue_cavity import contact_pairs,ORIGIN
from check_geometry import quality


def verify(scan_contacts=False):
    d=read_inputs();field=np.load(OUT/'research_tissue_displacement.npy');directory=OUT/'godot_validation';records=[];cross_records=[]
    fixed=np.load(PROJECT/'deformation/p1_masks/port_fixed_masks.npy').any(axis=0)
    for after in (False,True):
        for u in (0,.25,.5,.75,1):
            poses={}
            for name,ref,faces,disp in [('cavity',d['v'],d['f'],d['driver']),('tissue',d['tv'],d['tf'],field if after else d['old'])]:
                n,m=len(ref),len(faces);path=directory/f'{"after" if after else "before"}_{name}_u{int(100*u):03}.bin';raw=path.read_bytes()
                if len(raw)!=24*n+12*m: raise ValueError('Invalid runtime export length')
                p=np.frombuffer(raw,dtype='<f4',count=3*n).reshape(-1,3).astype(float)
                normals=np.frombuffer(raw,dtype='<f4',count=3*n,offset=12*n).reshape(-1,3).astype(float)
                indices=np.frombuffer(raw,dtype='<i4',count=3*m,offset=24*n).reshape(-1,3)
                expected=(ref-ORIGIN).astype(np.float32)+np.float32(u)*disp.astype(np.float32)
                max_error=float(np.abs(p-expected).max());same_indices=bool(np.array_equal(indices,faces[:,::-1]))
                actual_norm=vertex_normals(p,faces);cos=np.einsum('ij,ij->i',actual_norm,normals)/np.linalg.norm(normals,axis=1)
                record={'after':after,'fill':u,'mesh':name,'maximum_position_error_mm':max_error,'positions_bit_equal_to_expected':bool(np.array_equal(p,expected)),
                  'source_indices_exact':same_indices,'normal_finite':bool(np.isfinite(normals).all()),'normal_length_error':float(np.abs(np.linalg.norm(normals,axis=1)-1).max()),
                  'maximum_normal_angle_to_actual_geometry_deg':float(np.degrees(np.arccos(np.clip(cos,-1,1))).max())}
                if name=='cavity': record['fixed_positions_exactly_reference']=bool(np.array_equal(p[fixed],(ref-ORIGIN).astype(np.float32)[fixed]))
                if name=='tissue' and after:
                    ref32=(ref-ORIGIN).astype(np.float32).astype(float)
                    _,edges,length=mesh_graph(ref32,faces)
                    record['actual_float32_geometry_quality']=quality(ref32,faces,p-ref32,1.,edges,length)
                if max_error>2e-6 or not same_indices or not record['normal_finite'] or record['normal_length_error']>2e-6: raise ValueError('Runtime consistency failed '+str(record))
                records.append(record);poses[name]=p
            if after and scan_contacts:
                pairs=contact_pairs(poses['cavity'],d['f'],poses['tissue'],d['tf'])
                review=verify_pairs(poses['cavity'],d['f'],poses['tissue'],d['tf'],pairs)
                review['fill']=u;review['coordinate_scope']='Actual centered float32 Godot positions; not substituted for float64 reference geometry.'
                np.save(OUT/f'godot_float32_contacts_u{int(100*u):03}.npy',pairs)
                cross_records.append(review);print('actual float32',u,'raw',len(pairs),'finite-cross',review['positive_segment_count'],'maxsegment',review['maximum_segment_mm'],flush=True)
    report={'records':records,'all_position_arrays_match':all(x['positions_bit_equal_to_expected'] for x in records),
       'all_cavity_fixed_exact':all(x.get('fixed_positions_exactly_reference',True) for x in records),'graphical_runtime':read_json(directory/'runtime_checks.json'),
       'float32_cross_review':cross_records,'status':'REAL_RUNTIME_DATA_MATCHED','sources':{'driver':source_record(PROJECT/'deformation/full_cavity/field/displacement.npy'),'research_field':source_record(OUT/'research_tissue_displacement.npy')}}
    (OUT/'godot_runtime_validation.json').write_bytes(json_bytes(report));print('runtime arrays verified',len(records),flush=True)
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--contacts',action='store_true');args=p.parse_args();verify(args.contacts)
