from common import *
if __name__=='__main__':
    protect(True);a,m=inputs();v=a['cavity_reference_vertices'];f=a['cavity_faces']
    groups=np.load(PROJECT/'deformation/capacity_v2_n20_v1/region_ids.npy')
    fixed=np.load(PROJECT/'deformation/p2/evidence/port_fixed_masks.npy').any(0)
    assert v.shape==(25024,3) and f.shape==(50044,3) and fixed.sum()==3675
    assert np.array_equal(groups==0,fixed)
    tri=v[f];cr=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);norm=np.zeros_like(v)
    for k in range(3):np.add.at(norm,f[:,k],cr)
    norm/=np.maximum(np.linalg.norm(norm,axis=1,keepdims=True),1e-20)
    # Only a small export fixture. It is never the user's final sculpt.
    from scipy.spatial import cKDTree
    center=np.array(read(PROJECT/'deformation/cavity_topology_resolved.json')['nodes']['A_Middle']['position_mm'])
    radius=np.linalg.norm(v-center,axis=1)
    fade=1-np.exp(-(cKDTree(v[fixed]).query(v)[0]/4)**2)
    draft=(v-center)*(.004*np.exp(-(radius/30)**2)*fade)[:,None]
    draft[fixed]=0
    p=OUT/'data/edit_inputs.npz';np.savez(p,cavity=v,faces=f,tissue=a['tissue_reference_vertices'],tissue_faces=a['tissue_faces'],groups=groups,fixed=fixed,draft=draft)
    topology=read(PROJECT/'deformation/cavity_topology_resolved.json')
    write(OUT/'data/topology.json',topology)
    write(OUT/'data/source_manifest.json',{'schema':'V_DEMO_EDIT_V1','status':'DRAFT_TEST_ONLY_AWAITING_MANUAL_SCULPT',
        'accepted_input_manifest_sha256':sha(PROJECT/'deformation/p2/accepted_inputs.json'),'accepted_arrays':m['arrays'],
        'edit_package_sha256':sha(p),'group_source_sha256':sha(PROJECT/'deformation/capacity_v2_n20_v1/region_ids.npy'),
        'group_counts':{g:int((groups==i).sum()) for i,g in enumerate(GROUPS)},'fixed_vertices':int(fixed.sum()),
        'origin_RAS_mm':ORIGIN.tolist(),'Blender':'(RAS_mm-origin)*0.001, x=R,y=A,z=S; unit=m',
        'glTF_Godot':'(Blender_x,Blender_z,-Blender_y); right handed, determinant +1',
        'reference_D2_mL':16.805962087430178,'final_visual_approved':False})
    protect();print('Prepared accepted reference; fixed',fixed.sum(),flush=True)
