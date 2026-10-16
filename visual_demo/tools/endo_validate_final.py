"""Validate imported morphs, route clearance, unified clock and protected files."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from endo_path_audit import *
from scipy.spatial import cKDTree

def run():
    protect()
    shapes=np.load(ROOT/'data/manual_v3_shapes_RAS_mm.npz');basis=shapes['Basis'];faces=shapes['faces']
    prefix=PROJECT/'recordings/endoscope_v3_final'
    rows=np.genfromtxt(str(prefix)+'_frames.csv',delimiter=',',names=True)
    positions=np.column_stack([rows[k] for k in ['x_R','y_A','z_S']])
    report={'geometry_units':'RAS millimetres','states':{},'moving_cycle':{},'source':read(ROOT/'reports/manual_v3_inspection.json')}
    for s in [-.6,0.,1.]:
        vertices=basis+max(-s,0)*(shapes['Contracted']-basis)+max(s,0)*(shapes['Expanded']-basis)
        baked=np.fromfile(str(prefix)+f'_state_{s}.bin',dtype='<f4').reshape(-1,3)
        err=float(cKDTree(vertices).query(baked)[0].max())
        distance,inside=measure(vertices,faces,positions)
        report['states'][str(s)]={'Godot_baked_to_manual_max_error_mm':err,'all_241_camera_positions_inside':bool(inside.all()),'minimum_clearance_mm':float(distance.min())}
        assert err<1e-4 and inside.all() and distance.min()>.01
    distances=[];outs=[]
    for i,row in enumerate(rows):
        s=row['s'];vertices=basis+max(-s,0)*(shapes['Contracted']-basis)+max(s,0)*(shapes['Expanded']-basis)
        d,inside=measure(vertices,faces,positions[i:i+1]);distances.append(float(d[0]))
        if not inside[0]:outs.append(i)
        if i%60==0:print(f'Validated moving mesh frame {i}/{len(rows)-1}',flush=True)
    report['moving_cycle']={'frames':len(rows),'outside_frames':outs,'minimum_clearance_mm':min(distances),'clearance_mm':distances}
    data=read(PATH);points=np.array(data['points']);lengths=np.r_[0,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
    expected=np.array([np.interp(rows['path_offset_mm'],lengths,points[:,j]) for j in range(3)]).T
    report['max_camera_to_authoritative_path_error_mm']=float(np.linalg.norm(positions-expected,axis=1).max())
    times=rows['time_seconds'];states=.2-.8*np.cos(2*np.pi*times/8)
    report['clock']={'first_time':float(times[0]),'last_time':float(times[-1]),'maximum_s_error':float(abs(rows['s']-states).max()),'reference_crossing_times_seconds':[float(8*np.arccos(.25)/(2*np.pi)),float(8*(1-np.arccos(.25)/(2*np.pi)))],'sample_count':len(rows)}
    quaternions=np.column_stack([rows[k] for k in ['qx','qy','qz','qw']]);quaternions/=np.linalg.norm(quaternions,axis=1)[:,None]
    angles=np.rad2deg(2*np.arccos(np.clip(abs(np.sum(quaternions[1:]*quaternions[:-1],axis=1)),0,1)))
    report['max_interframe_camera_rotation_deg']=float(angles.max())
    report['path_offsets_mm']=[float(rows['path_offset_mm'][0]),float(rows['path_offset_mm'][-1])]
    assert not outs and min(distances)>.01
    assert report['max_camera_to_authoritative_path_error_mm']<1e-3
    assert report['clock']['maximum_s_error']<1e-7
    assert angles.max()<40/30+1e-3
    protect();report['protected_files']=read(ROOT/'reports/protected_after.json')
    write(ROOT/'reports/final_geometry_validation.json',report)
    print('PASS',{'minimum_dynamic_clearance_mm':min(distances),'max_rotation_deg':angles.max(),'protected':report['protected_files']},flush=True)

if __name__=='__main__':run()
