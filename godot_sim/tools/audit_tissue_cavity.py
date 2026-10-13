"""P1.5 audit gate. No approved geometry/displacement files are written.

Diagnostic mappings are explicitly UNACCEPTED; failed crossings stop delivery.
"""
from pathlib import Path
import argparse
import hashlib
import struct
import numpy as np
import open3d as o3d
import trimesh
import vtk
from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray,vtk_to_numpy
from resolve_cavity_topology import PROJECT,read_json,json_bytes,source_record
from build_cavity_surface_masks import load_obj,mesh_graph
from build_local_displacement import normalize,smoothstep,constrained_vector_smoothing,self_intersection_pairs
from build_cavity_morph_states import vertex_normals

ROOT=PROJECT/"deformation/p15_audit"
ORIGIN=np.array([16.,16.,-81.])


def polydata(vertices,faces):
    poly=vtk.vtkPolyData();points=vtk.vtkPoints()
    points.SetData(numpy_to_vtk(np.ascontiguousarray(vertices,dtype=float),deep=True));poly.SetPoints(points)
    cells=vtk.vtkCellArray()
    cells.SetData(numpy_to_vtkIdTypeArray(np.arange(0,len(faces)*3+1,3,dtype=np.int64),deep=True),
                  numpy_to_vtkIdTypeArray(np.ascontiguousarray(faces,dtype=np.int64).ravel(),deep=True))
    poly.SetPolys(cells)
    return poly


def contact_pairs(v0,f0,v1,f1):
    collision=vtk.vtkCollisionDetectionFilter()
    collision.SetInputData(0,polydata(v0,f0));collision.SetInputData(1,polydata(v1,f1))
    identity=vtk.vtkMatrix4x4();identity.Identity()
    collision.SetMatrix(0,identity);collision.SetMatrix(1,identity)
    collision.SetBoxTolerance(0.);collision.SetCellTolerance(0.)
    collision.SetNumberOfCellsPerNode(2);collision.SetCollisionModeToAllContacts();collision.Update()
    return np.column_stack([vtk_to_numpy(collision.GetContactCells(i)) for i in (0,1)]).astype(np.int64)


def classify_contacts(v0,f0,v1,f1,pairs,tolerance=1e-6):
    a,b=v0[f0[pairs[:,0]]],v1[f1[pairs[:,1]]]
    na=normalize(np.cross(a[:,1]-a[:,0],a[:,2]-a[:,0]));nb=normalize(np.cross(b[:,1]-b[:,0],b[:,2]-b[:,0]))
    da=np.einsum("pij,pj->pi",b-a[:,:1],na);db=np.einsum("pij,pj->pi",a-b[:,:1],nb)
    proper=(da.min(axis=1)<-tolerance)&(da.max(axis=1)>tolerance)&(db.min(axis=1)<-tolerance)&(db.max(axis=1)>tolerance)
    coplanar=np.maximum(abs(da).max(axis=1),abs(db).max(axis=1))<=tolerance
    return proper,coplanar


def ray_scene(vertices,faces):
    scene=o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh(o3d.core.Tensor((vertices-ORIGIN).astype(np.float32)),o3d.core.Tensor(faces.astype(np.uint32))))
    return scene


def summary(values):
    return {k:float(v) for k,v in zip(("min","p01","p05","median","p95","p99","max"),np.quantile(values,[0,.01,.05,.5,.95,.99,1]))}


def mesh_info(name,vertices,faces,output):
    mesh=trimesh.Trimesh(vertices,faces,process=False)
    print(f"Scanning {name} original self intersections...",flush=True)
    pairs=self_intersection_pairs(vertices,faces)
    np.save(output/(name+"_self_intersections.npy"),pairs)
    _,counts=np.unique(mesh.edges_sorted,axis=0,return_counts=True)
    components=mesh.split(only_watertight=False)
    info={"vertices":len(vertices),"triangles":len(faces),"bounds_mm":mesh.bounds.tolist(),
        "watertight":bool(mesh.is_watertight),"winding_consistent":bool(mesh.is_winding_consistent),
        "connected_components":len(components),"boundary_edges":int(np.sum(counts==1)),
        "nonmanifold_edges":int(np.sum(counts>2)),"euler_characteristic":int(mesh.euler_number),
        "signed_volume_mm3":float(mesh.volume),"degenerate_triangles":int(np.sum(mesh.area_faces<1e-10)),
        "normal_finite":bool(np.isfinite(mesh.face_normals).all()),"normal_length_range":[float(np.linalg.norm(mesh.face_normals,axis=1).min()),float(np.linalg.norm(mesh.face_normals,axis=1).max())],
        "self_intersection_pairs":pairs.tolist(),"self_intersection_pair_count":len(pairs),
        "obj_supplied_normal_count":sum(line.startswith("vn ") for line in (PROJECT/"source_assets"/f"kidney_{name}.obj").read_text(encoding="utf-8").splitlines()),
        "normal_method":"OBJ winding, recomputed geometric face normals; no anatomical inner/outer labels."}
    return mesh,info


def scene_transforms(path,names):
    text=path.read_text(encoding="utf-8")
    result={}
    for block in text.split("[node ")[1:]:
        header,body=block.split("]",1)
        for name in names:
            if 'name="'+name+'"' in header:
                transform=[line for line in body.splitlines() if line.startswith(("transform =","position =","rotation =","scale ="))]
                result[name]=transform or ["identity (no serialized spatial transform)"]
    return result


def export_reference_preview(output,meshes,proper_pairs,tissue_self):
    for name,(vertices,faces) in meshes.items():
        flags=np.zeros(len(vertices),dtype=np.float32)
        column=0 if name=="cavity" else 1
        flags[np.unique(faces[proper_pairs[:,column]].ravel())]=1
        if name=="tissue":
            flags[np.unique(faces[tissue_self.ravel()].ravel())]=1
        raw=bytearray(b"KAUD0001"+struct.pack("<II",len(vertices),len(faces)))
        for values in (vertices-ORIGIN,vertex_normals(vertices,faces),flags):
            raw.extend(np.asarray(values,dtype="<f4").tobytes())
        raw.extend(np.asarray(faces[:,::-1],dtype="<u4").tobytes())
        (output/(name+"_reference.bin")).write_bytes(raw)
    resolved=read_json(PROJECT/"deformation/cavity_topology_resolved.json")
    meta=read_json(PROJECT/"deformation/full_cavity/morph/morph_preview.json")
    meta["preview_origin_mm"]=ORIGIN.tolist()
    meta["bounds_mm"]=[np.minimum(meshes["cavity"][0].min(axis=0),meshes["tissue"][0].min(axis=0)).tolist(),np.maximum(meshes["cavity"][0].max(axis=0),meshes["tissue"][0].max(axis=0)).tolist()]
    meta["landmarks"]={k:n["position_mm"] for k,n in resolved["nodes"].items() if k.startswith(("J_","T_"))}
    meta["binary_sha256"]={name:source_record(output/(name+"_reference.bin"))["sha256"] for name in meshes}
    meta["sources"]={name:source_record(PROJECT/"source_assets"/f"kidney_{name}.obj") for name in meshes}
    meta["reference_only"]=True
    (output/"audit_preview.json").write_bytes(json_bytes(meta))


def audit(output,probe=True):
    output.mkdir(parents=True,exist_ok=True)
    v,f=load_obj(PROJECT/"source_assets/kidney_cavity.obj")
    tv,tf=load_obj(PROJECT/"source_assets/kidney_tissue.obj")
    driver_path=PROJECT/"deformation/full_cavity/field/displacement.npy"
    approved=read_json(PROJECT/"deformation/full_cavity/field/displacement_report.json")
    if source_record(driver_path)["sha256"]!=approved["output_sha256"]["displacement.npy"]:
        raise ValueError("Accepted cavity driver hash changed")
    cavity,ci=mesh_info("cavity",v,f,output)
    tissue,ti=mesh_info("tissue",tv,tf,output)
    cs,ts=ray_scene(v,f),ray_scene(tv,tf)
    vc=o3d.core.Tensor((v-ORIGIN).astype(np.float32));vt=o3d.core.Tensor((tv-ORIGIN).astype(np.float32))
    gap=ts.compute_distance(vc).numpy();signed=ts.compute_signed_distance(vc,nsamples=3).numpy()
    nearest=cs.compute_closest_points(vt)
    ids,uv=nearest["primitive_ids"].numpy(),nearest["primitive_uvs"].numpy()
    bary=np.column_stack([1-uv.sum(axis=1),uv])
    distances=np.linalg.norm(nearest["points"].numpy()+ORIGIN-tv,axis=1)
    normal_dot=np.einsum("ij,ij->i",tissue.vertex_normals,cavity.face_normals[ids])
    original=contact_pairs(v,f,tv,tf)
    proper,coplanar=classify_contacts(v,f,tv,tf,original)
    baseline=original[proper]
    for name,values in (("cross_contact_pairs",original),("proper_crossing_pairs",baseline),("tissue_to_cavity_face",ids),("mapping_barycentric",bary),("tissue_to_cavity_distance_mm",distances)):
        np.save(output/(name+".npy"),values)
    statistics={}
    for threshold in (.01,.05,.1,.2,.5,1,2,5,12):
        close=distances<threshold
        statistics[str(threshold)]={"vertices":int(close.sum()),"opposing_normals":int(np.sum(close&(normal_dot<-.5))),"aligned_normals":int(np.sum(close&(normal_dot>.5)))}
    resolved=read_json(PROJECT/"deformation/cavity_topology_resolved.json")
    points=np.concatenate([p["points_mm"] for p in resolved["paths"]])
    center_signed=ts.compute_signed_distance(o3d.core.Tensor((points-ORIGIN).astype(np.float32)),nsamples=3).numpy()
    report={"schema_version":"1.0","status":"P1_5_AUDIT_BLOCKED_NO_ACCEPTED_TISSUE_FIELD","unit":"mm",
        "sources":{"cavity":source_record(PROJECT/"source_assets/kidney_cavity.obj"),"tissue":source_record(PROJECT/"source_assets/kidney_tissue.obj"),"approved_cavity_driver":source_record(driver_path),"auditor":source_record(__file__)},
        "meshes":{"cavity":ci,"tissue":ti},
        "coordinate_system":{"obj_headers":"ITK-SNAP / 3D Slicer SPACE=RAS; shared exported coordinates, mm per existing marker reference.",
            "inspection_scene":scene_transforms(PROJECT/"irrigation_asset_check.tscn",["IrrigationAssetCheck","CavityReference","TissueReference"]),
            "main_scene":scene_transforms(PROJECT/"main.tscn",["Main","KidneyBody","kidney_tissue"]),"preview_origin_mm":ORIGIN.tolist()},
        "relation":{"cavity_vertex_to_tissue_surface_mm":summary(gap),"tissue_vertex_to_cavity_surface_mm":summary(distances),
            "cavity_vertices_inside_tissue_parity_below_minus_1e_4":int(np.sum(signed<-1e-4)),
            "center_path_points_tested":len(points),"center_path_points_inside_tissue_parity":int(np.sum(center_signed<-1e-4)),
            "center_path_clearance_min_mm":float(center_signed.min()),"near_surface_normal_statistics":statistics,
            "contact_pairs":len(original),"proper_crossing_pairs":len(baseline),"coplanar_pairs":int(coplanar.sum()),
            "touching_or_ambiguous_pairs":int(np.sum(~(proper|coplanar))),"crossing_tolerance_mm":1e-6,
            "inner_outer":"Single connected genus-10 boundary, not two explicitly labeled shells. Near-cavity opposing-normal patches are geometric inner-wall candidates only.",
            "wall_thickness":"Not established. Ordinary nearest-surface distances are gaps, NOT tissue wall thickness.",
            "containment_limit":"Parity samples assume valid closed solids; tissue self intersections violate that assumption. Samples do not prove triangle separation."},
        "diagnostic_probes":[],
        "blockers":["Original tissue has self intersections and original cavity/tissue boundaries cross.","Diagnostic barycentric transfer and smoothing introduce NEW cross-interface triangle pairs.","No validated anatomical inner/outer partition or wall-thickness model."],
        "limits":["VTK triangle contacts + both-sided plane crossing test distinguish proper crossings from touching; contact tolerance and mesh discretization remain limitations.","Audit preview is reference-only. Diagnostic probe arrays are UNACCEPTED, not production tissue states.","Cavity displacement, fixed masks, source OBJ, markers, topology and main scene are unchanged."]}
    if probe:
        diagnostic=PROJECT/"analysis/irrigation_baseline/p15_mapping_probe";diagnostic.mkdir(parents=True,exist_ok=True)
        driver=np.load(driver_path)
        target=np.einsum("ni,nij->nj",bary,driver[f[ids]])*(1-smoothstep((distances-1)/11))[:,None]
        graph,_,_=mesh_graph(tv,tf)
        old=set(map(tuple,baseline))
        for strength in (0,5,30):
            field=target if strength==0 else constrained_vector_smoothing(graph,target,distances>=12,distances<12,strength)
            np.save(diagnostic/f"UNACCEPTED_tissue_displacement_strength{strength}.npy",field)
            for u in (.25,1.):
                av,bv=v+u*driver,tv+u*field
                candidates=contact_pairs(av,f,bv,tf);crossing,_=classify_contacts(av,f,bv,tf,candidates)
                pairs=candidates[crossing];added=sorted(set(map(tuple,pairs))-old)
                result={"smoothing_strength":strength,"fill":u,"accepted":False,"tissue_maximum_displacement_mm":float(np.linalg.norm(field,axis=1).max()),"tissue_mean_displacement_mm":float(np.linalg.norm(field,axis=1).mean()),"contact_pairs":len(candidates),"proper_crossing_pairs":len(pairs),"new_proper_crossing_pair_count":len(added)}
                report["diagnostic_probes"].append(result)
                np.save(diagnostic/f"proper_strength{strength}_u{int(100*u):03}.npy",pairs)
                print(result,flush=True)
    else:
        report["status"]="P1_5_REFERENCE_AUDIT_ONLY"
    export_reference_preview(output,{"cavity":(v,f),"tissue":(tv,tf)},baseline,np.asarray(ti["self_intersection_pairs"],dtype=np.int64))
    report["output_sha256"]={p.name:source_record(p)["sha256"] for p in sorted(output.iterdir()) if p.suffix in (".npy",".bin")}
    (output/"audit_report.json").write_bytes(json_bytes(report))
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT)
    parser.add_argument("--skip-probes",action="store_true")
    args=parser.parse_args()
    audit(args.output,probe=not args.skip_probes)
