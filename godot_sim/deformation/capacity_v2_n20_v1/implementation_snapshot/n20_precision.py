"""Offline preview-precision audit only, no Godot resources written."""
from n20_model import *

def run():
    protected();a,d2,tv,tf,resolved,approval=inputs();rows=[];origin=np.array([16.,16.,-81.])
    for side in ['contract','expand']:
        tr=read(OUT/side/'trajectory.json');n=len(tr['states'])
        for name,v,f in [('cavity',a['vertices'],a['faces']),('tissue',tv,tf)]:
            d=np.load(OUT/side/f'{name}_{n:03}.npy');reference=(v-origin).astype(np.float32);_,edges,length=mesh_graph(reference.astype(float),f)
            values=[]
            for u in [0,.25,.5,.75,1.]:
                position=reference+np.float32(u)*d.astype(np.float32);observed=position.astype(float)-reference.astype(float)
                q=quick_quality(reference.astype(float),f,observed,edges,length)
                values.append({'u':u,**q,'maximum_display_error_mm':float(np.linalg.norm(position.astype(float)-(v-origin+u*d),axis=1).max())})
            rows.append({'side':side,'mesh':name,'levels':values,'all_float32_quality_passed':all(x['pass'] for x in values),
                'actual_Godot_ArrayMesh_test_performed':False,'float32_finite_contacts_validated':False})
    write(OUT/'float32_quality_precheck.json',rows);protected()
    print('Float32 geometry only',[(r['side'],r['mesh'],r['all_float32_quality_passed']) for r in rows],flush=True)

if __name__=='__main__':run()
