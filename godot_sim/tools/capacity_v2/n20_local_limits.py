"""Auditable finite-face proximity and curvature-proxy risk diagnostics.
Distances are NOT tissue thickness, material correspondence, or absolute motion
ceilings. Joint moving-contact limits cannot be inferred from a static gap.
"""
from n20_model import *
from audit_tissue_cavity import polydata
import vtk,math

def finite_proximity(query,vertices,faces):
    locator=vtk.vtkStaticCellLocator();locator.SetDataSet(polydata(vertices,faces));locator.BuildLocator()
    point=[0.,0.,0.];cell=vtk.reference(0);sub=vtk.reference(0);squared=vtk.reference(0.)
    ids=[];gaps=[];points=[]
    for p in query:
        locator.FindClosestPoint(p,point,cell,sub,squared)
        ids.append(int(cell));gaps.append(math.sqrt(max(float(squared),0.)));points.append(point.copy())
    return np.array(gaps),np.array(ids),np.array(points)

def run():
    protected();a,d2,tv,tf,resolved,approval=inputs();_,edges,length=mesh_graph(a['vertices'],a['faces']);records=[]
    for side in ['reference','contract','expand']:
        cv=np.zeros_like(a['vertices']);tt=np.zeros_like(tv)
        if side!='reference':
            n=len(read(OUT/side/'trajectory.json')['states']);cv=np.load(OUT/side/f'cavity_{n:03}.npy');tt=np.load(OUT/side/f'tissue_{n:03}.npy')
        v=a['vertices']+cv;t=tv+tt;norm=vertex_normals(v,a['faces']);variation=np.linalg.norm(norm[edges[:,0]]-norm[edges[:,1]],axis=1)/length
        total=np.zeros(len(v));degree=np.zeros(len(v))
        for k in [0,1]:np.add.at(total,edges[:,k],variation);np.add.at(degree,edges[:,k],1)
        proxy=total/degree;gap,donor,points=finite_proximity(v,t,tf)
        folder=OUT/'local_limit_diagnostics'/side;folder.mkdir(parents=True,exist_ok=True)
        for name,array in [('normal_variation_proxy_per_mm',proxy),('finite_tissue_face_distance_mm',gap),('nearest_tissue_source_face_ids',donor),('closest_finite_points_RAS_mm',points)]:np.save(folder/f'{name}.npy',array)
        records.append({'state':side,'distance_quantiles_mm':np.quantile(gap,[0,.01,.5,.99,1]).tolist(),
            'normal_variation_proxy_quantiles_per_mm':np.quantile(proxy,[0,.5,.95,1]).tolist(),
            'proxy_is_principal_curvature':False,'distance_is_tissue_thickness':False,'nearest_face_is_material_homology':False,
            'static_distance_is_absolute_displacement_ceiling':False,'curvature_specific_inequality_implemented':False})
        print('Finite proximity',side,'min mm',gap.min(),flush=True)
    write(OUT/'local_limit_diagnostics/summary.json',{'states':records,
        'local_limit_strategy':'Moving relative halfspaces + actual local area/edge quality + finite pair rejection; not a universal maximum displacement.',
        'missing':'Certified curvature-aware trust limits and persistent finite contact-manifold constraints; individual principal curvatures not fitted.',
        'new_material_model_or_wall_thickness_claim':False});protected()

if __name__=='__main__':run()
