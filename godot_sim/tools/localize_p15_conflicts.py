"""Localize cached P1.5 contacts; no repeat whole-mesh reference intersection scan."""
from pathlib import Path
import argparse
import struct
from collections import Counter
import numpy as np
from trimesh.triangles import closest_point
from scipy.cluster.hierarchy import fclusterdata
from audit_tissue_cavity import ROOT as AUDIT,ORIGIN,classify_contacts,polydata
from build_cavity_surface_masks import load_obj
from build_local_displacement import normalize
from build_cavity_morph_states import vertex_normals
from resolve_cavity_topology import PROJECT,read_json,json_bytes,source_record

ROOT=PROJECT/"analysis/irrigation_baseline/p15_contact_research"


def coplanar_overlap_area(a,b,epsilon=1e-10):
    """Convex polygon clipping on the dominant plane. Units: mm2, not depth."""
    normal=normalize(np.cross(a[1]-a[0],a[2]-a[0])[None,:])[0]
    if np.max(np.abs((b-a[0])@normal))>epsilon:
        return 0.
    axis=int(np.argmax(abs(normal)));keep=[i for i in range(3) if i!=axis]
    subject=[p.copy() for p in a[:,keep]];clip=b[:,keep]
    cross2=lambda x,y:float(x[0]*y[1]-x[1]*y[0])
    orientation=1. if cross2(clip[1]-clip[0],clip[2]-clip[0])>0 else -1.
    for i in range(3):
        start,end=clip[i],clip[(i+1)%3];previous=subject;subject=[]
        if not previous: break
        for p,q in zip(previous,previous[1:]+previous[:1]):
            edge_length=np.linalg.norm(end-start)
            dp=orientation*cross2(end-start,p-start)/edge_length;dq=orientation*cross2(end-start,q-start)/edge_length
            if dp>=-epsilon: subject.append(p)
            if (dp<0<dq) or (dq<0<dp): subject.append(p+dp/(dp-dq)*(q-p))
    if len(subject)<3: return 0.
    polygon=np.asarray(subject)
    return abs(sum(cross2(p,q) for p,q in zip(polygon,np.roll(polygon,-1,axis=0))))/(2*abs(normal[axis]))


def intersection_segment(a,b,epsilon=1e-10):
    """Independent plane/edge clipping. Positive line overlap is not depth."""
    na=normalize(np.cross(a[1]-a[0],a[2]-a[0])[None,:])[0]
    nb=normalize(np.cross(b[1]-b[0],b[2]-b[0])[None,:])[0]
    axis=np.cross(na,nb)
    if np.linalg.norm(axis)<1e-10:
        return None
    axis/=np.linalg.norm(axis)
    def cut(triangle,point,normal):
        distance=(triangle-point)@normal
        points=[]
        for i,j in ((0,1),(1,2),(2,0)):
            # Do not snap vertices to an infinite plane with the requested
            # segment acceptance tolerance: almost parallel DISJOINT triangles
            # would acquire fictitious overlapping cuts.
            if abs(distance[i])<=min(epsilon,1e-12):
                points.append(triangle[i])
            if distance[i]*distance[j]<0:
                points.append(triangle[i]+distance[i]/(distance[i]-distance[j])*(triangle[j]-triangle[i]))
        return np.asarray(points)
    pa,pb=cut(a,b[0],nb),cut(b,a[0],na)
    if len(pa)<2 or len(pb)<2:
        return None
    origin=pa[0]
    ta,tb=(pa-origin)@axis,(pb-origin)@axis
    lo,hi=max(ta.min(),tb.min()),min(ta.max(),tb.max())
    if hi-lo<=epsilon:
        return None
    return np.stack([origin+lo*axis,origin+hi*axis])


def closest_features(a,b):
    """Closest finite triangle features (vertex/face and edge/edge)."""
    candidates=[]
    for x,y in ((a,b),(b,a)):
        q=closest_point(np.repeat(y[None,:,:],3,axis=0),x)
        candidates.extend((float(np.linalg.norm(p-r)),(p+r)/2) for p,r in zip(x,q))
    for i,j in ((0,1),(1,2),(2,0)):
        for k,l in ((0,1),(1,2),(2,0)):
            p,q=a[i],b[k];u,w=a[j]-p,b[l]-q;r=p-q
            aa,bb,cc,dd,ee=u@u,u@w,w@w,u@r,w@r
            denominator=aa*cc-bb*bb
            s=np.clip((bb*ee-cc*dd)/denominator,0,1) if denominator>1e-20 else 0.
            t=np.clip((bb*s+ee)/cc,0,1)
            s=np.clip((bb*t-dd)/aa,0,1)
            x,y=p+s*u,q+t*w
            candidates.append((float(np.linalg.norm(x-y)),(x+y)/2))
    return min(candidates,key=lambda item:item[0])


def pair_geometry(va,fa,vb,fb,pairs):
    a,b=va[fa[pairs[:,0]]],vb[fb[pairs[:,1]]]
    na=normalize(np.cross(a[:,1]-a[:,0],a[:,2]-a[:,0]));nb=normalize(np.cross(b[:,1]-b[:,0],b[:,2]-b[:,0]))
    da=np.einsum("pij,pj->pi",b-a[:,:1],na);db=np.einsum("pij,pj->pi",a-b[:,:1],nb)
    straddle=np.maximum(0,np.minimum.reduce([-da.min(axis=1),da.max(axis=1),-db.min(axis=1),db.max(axis=1)]))
    segments=[];centers=[];length=[];verified=[];distance=[];overlap=[]
    for x,y in zip(a,b):
        segment=intersection_segment(x,y)
        verified.append(segment is not None)
        gap,point=closest_features(x,y)
        distance.append(gap);overlap.append(coplanar_overlap_area(x,y))
        centers.append(segment.mean(axis=0) if segment is not None else point)
        length.append(float(np.linalg.norm(segment[1]-segment[0])) if segment is not None else 0.)
        segments.append(segment if segment is not None else np.zeros((2,3)))
    return {"centers":np.asarray(centers),"segments":np.asarray(segments),"length":np.asarray(length),
            "verified":np.asarray(verified),"straddle":straddle,
            "feature_distance":np.asarray(distance),"coplanar_overlap_area":np.asarray(overlap),
            "angle_deg":np.degrees(np.arccos(np.clip(abs(np.einsum('ij,ij->i',na,nb)),0,1)))}


def spatial_labels(points,radius=2.):
    if len(points)==1:
        return np.ones(1,dtype=int)
    labels=fclusterdata(points,radius,criterion="distance",method="single")
    order=sorted(np.unique(labels),key=lambda k:tuple(points[labels==k].mean(axis=0)[[2,0,1]]))
    return np.array([order.index(k)+1 for k in labels],dtype=int)


def summarize_groups(prefix,pairs,geometry,va,fa,vb,fb,owners,resolved,cavity_faces,donor=None):
    labels=spatial_labels(geometry["centers"])
    result=[]
    for label in np.unique(labels):
        members=np.flatnonzero(labels==label);selected=pairs[members]
        centers=geometry["centers"][members]
        vertices=np.concatenate([va[fa[selected[:,0]]].reshape(-1,3),vb[fb[selected[:,1]]].reshape(-1,3)])
        a_faces,b_faces=np.unique(selected[:,0]),np.unique(selected[:,1])
        if prefix=="S":
            mapped=donor[np.unique(fb[selected.ravel()].ravel())]
            path_ids=owners[cavity_faces[mapped]].ravel()
        else:
            path_ids=owners[fa[a_faces]].ravel()
        count=Counter(resolved["paths"][int(i)]["id"] for i in path_ids)
        center=centers.mean(axis=0)
        nodes=sorted(((name,float(np.linalg.norm(center-node["position_mm"]))) for name,node in resolved["nodes"].items() if name.startswith(("J_","T_","P_"))),key=lambda item:item[1])[:4]
        area=lambda v,f,idx:float(np.linalg.norm(np.cross(v[f[idx,1]]-v[f[idx,0]],v[f[idx,2]]-v[f[idx,0]]),axis=1).sum()/2)
        normal=normalize(np.mean(np.cross(va[fa[a_faces,1]]-va[fa[a_faces,0]],va[fa[a_faces,2]]-va[fa[a_faces,0]]),axis=0)[None,:])[0]
        result.append({"id":f"{prefix}{label:02}","kind":{"C":"old_crossing_candidate","S":"tissue_self_contact_candidate","P":"near_coplanar"}[prefix],
            "pair_count":len(members),"pair_indices":members.tolist(),"pairs":selected.tolist(),
            "first_unique_faces":len(a_faces),"second_unique_faces":len(b_faces),
            "center_mm":center.tolist(),"bounds_mm":[vertices.min(axis=0).tolist(),vertices.max(axis=0).tolist()],
            "extent_mm":(vertices.max(axis=0)-vertices.min(axis=0)).tolist(),
            "nearest_path_vertex_votes":dict(count.most_common()),"nearest_landmarks_mm":nodes,
            "independent_positive_segments":int(geometry["verified"][members].sum()),
            "sum_pair_segment_lengths_mm":float(geometry["length"][members].sum()),
            "maximum_pair_segment_length_mm":float(geometry["length"][members].max()),
            "maximum_plane_straddle_mm":float(geometry["straddle"][members].max()),
            "minimum_feature_distance_mm":float(geometry["feature_distance"][members].min()),
            "maximum_feature_distance_mm":float(geometry["feature_distance"][members].max()),
            "coplanar_pair_area_sum_mm2":float(geometry["coplanar_overlap_area"][members].sum()),
            "incident_support_area_mm2":[area(va,fa,a_faces),area(vb,fb,b_faces)],
            "view_normal":normal.tolist(),
            "metric_limits":"Segment sum can double-count overlapping curves. Incident area is supporting triangle area, NOT penetration area. Plane straddle is NOT physical depth."})
    return result,labels


def export_preview(output,v,f,tv,tf,groups,cross,coplanar,tissue_self):
    # Keep the accepted source topology; category colors mark associated vertices.
    for name,vertices,faces in (("cavity",v,f),("tissue",tv,tf)):
        flags=np.zeros(len(vertices),dtype=np.float32)
        column=0 if name=="cavity" else 1
        flags[np.unique(faces[coplanar[:,column]].ravel())]=2
        flags[np.unique(faces[cross[:,column]].ravel())]=1
        if name=="tissue":
            flags[np.unique(faces[tissue_self.ravel()].ravel())]=3
        raw=bytearray(b"KAUD0001"+struct.pack("<II",len(vertices),len(faces)))
        for data in (vertices-ORIGIN,vertex_normals(vertices,faces),flags):
            raw.extend(np.asarray(data,dtype="<f4").tobytes())
        raw.extend(np.asarray(faces[:,::-1],dtype="<u4").tobytes())
        (output/(name+"_reference.bin")).write_bytes(raw)
    meta=read_json(AUDIT/"audit_preview.json")
    meta["groups"]=groups
    meta["binary_sha256"]={name:source_record(output/(name+"_reference.bin"))["sha256"] for name in ("cavity","tissue")}
    (output/"audit_preview.json").write_bytes(json_bytes(meta))


def build(output=ROOT):
    output.mkdir(parents=True,exist_ok=True)
    audit=read_json(AUDIT/"audit_report.json")
    for name,expected in audit["output_sha256"].items():
        if source_record(AUDIT/name)["sha256"]!=expected:
            raise ValueError(f"Cached audit changed: {name}")
    for name in ("cavity","tissue","approved_cavity_driver"):
        record=audit["sources"][name]
        if source_record(PROJECT/record["path"])["sha256"]!=record["sha256"]:
            raise ValueError(f"Accepted input changed: {name}")
    v,f=load_obj(PROJECT/"source_assets/kidney_cavity.obj");tv,tf=load_obj(PROJECT/"source_assets/kidney_tissue.obj")
    contacts=np.load(AUDIT/"cross_contact_pairs.npy");cross=np.load(AUDIT/"proper_crossing_pairs.npy");ts=np.load(AUDIT/"tissue_self_intersections.npy")
    _,co=classify_contacts(v,f,tv,tf,contacts);coplanar=contacts[co]
    owners=np.load(PROJECT/"deformation/p1_masks/path_owner.npy");donor=np.load(AUDIT/"tissue_to_cavity_face.npy")
    resolved=read_json(PROJECT/"deformation/cavity_topology_resolved.json")
    cg=pair_geometry(v,f,tv,tf,cross);sg=pair_geometry(tv,tf,tv,tf,ts);pg=pair_geometry(v,f,tv,tf,coplanar)
    cgroups,cl=summarize_groups("C",cross,cg,v,f,tv,tf,owners,resolved,f)
    sgroups,sl=summarize_groups("S",ts,sg,tv,tf,tv,tf,owners,resolved,f,donor)
    pgroups,pl=summarize_groups("P",coplanar,pg,v,f,tv,tf,owners,resolved,f)
    for group in cgroups+sgroups:
        group["nearby_other_groups"]=[{"id":other["id"],"center_distance_mm":float(np.linalg.norm(np.array(group["center_mm"])-other["center_mm"]))}
            for other in cgroups+sgroups+pgroups if other["id"]!=group["id"] and np.linalg.norm(np.array(group["center_mm"])-other["center_mm"])<=5]
    sensitivity=[]
    for tol in (1e-8,1e-7,1e-6,1e-5,1e-4,1e-3):
        proper,co=classify_contacts(v,f,tv,tf,contacts,tol)
        sensitivity.append({"tolerance_mm":tol,"old_plane_straddle_pairs":int(proper.sum()),"near_coplanar_pairs":int(co.sum()),
            "independent_positive_segments_cross58":sum(intersection_segment(v[f[i]],tv[tf[j]],tol) is not None for i,j in cross),
            "independent_positive_segments_self23":sum(intersection_segment(tv[tf[i]],tv[tf[j]],tol) is not None for i,j in ts)})
    groups=cgroups+sgroups+pgroups
    report={"schema_version":"1.0","date":"2026-10-14","status":"DIAGNOSTIC_LOCALIZATION_NOT_ANATOMICAL_APPROVAL",
        "source_audit":source_record(AUDIT/"audit_report.json"),"builder":source_record(__file__),
        "clustering":{"method":"Single-link Euclidean clustering of finite intersection midpoints or independently closest finite-feature midpoints.","radius_mm":2.,
            "radius_sensitivity":[{"radius_mm":radius,"cross_clusters":int(spatial_labels(cg["centers"],radius).max()),"self_clusters":int(spatial_labels(sg["centers"],radius).max())} for radius in (1.,2.,3.)]},
        "counts":{"cross_pairs":len(cross),"self_pairs":len(ts),"near_coplanar_pairs":len(coplanar),"cross_groups":len(cgroups),"self_groups":len(sgroups),"near_coplanar_groups":len(pgroups)},
        "tolerance_sensitivity":sensitivity,
        "independent_review":{"positive_cross_segments":int(cg["verified"].sum()),"cross_pairs":len(cross),"maximum_cross_segment_mm":float(cg["length"].max()),"maximum_plane_straddle_mm":float(cg["straddle"].max()),
            "old58_all_finite_feature_gap_zero":bool(np.all(cg["feature_distance"]==0)),"old58_coplanar_overlap_area_sum_mm2":float(cg["coplanar_overlap_area"].sum()),
            "self23_positive_segments":int(sg["verified"].sum()),"self23_feature_distance_mm":[float(sg["feature_distance"].min()),float(sg["feature_distance"].max())],"self23_coplanar_overlap_area_sum_mm2":float(sg["coplanar_overlap_area"].sum()),
            "correction":"The old two-sided infinite-plane test was insufficient. All old58 are point contacts; the 23 Open3D candidates are independently separated finite triangles. Historical reports are preserved, NOT evidence of confirmed penetration.",
            "method":"Independent finite plane-edge clipping plus line interval overlap; vertex/face and edge/edge distances; convex planar polygon clipping. Original VTK broad phase reused."},
        "groups":groups,"limits":["Group distances and path votes are spatial labels, not proof of anatomical membership or segmentation error.","True penetration depth, penetrated area/volume and wall thickness are not established.","Clustering is single-link; total cluster extent can exceed 2 mm."]}
    (output/"localization_report.json").write_bytes(json_bytes(report))
    for name,data in (("cross_centers",cg["centers"]),("cross_segments",cg["segments"]),("cross_group_labels",cl),("self_group_labels",sl)):
        np.save(output/(name+".npy"),data)
    export_preview(output,v,f,tv,tf,groups,cross,coplanar,ts)
    lines=["# 原始冲突空间分组（诊断）","","2 mm 单链空间分组；C=旧判据的穿越候选（独立复核未确认正长度穿越），S=组织自接触候选，P=近共面接触。路径票数仅为空间关联。","",
        "| ID | 配对 | 两侧独立三角面 | 中心 mm | 关联路径 | 最大交线 mm | 平面跨越幅度 mm |","| --- | ---: | --- | --- | --- | ---: | ---: |"]
    for group in groups:
        lines.append(f"| {group['id']} | {group['pair_count']} | {group['first_unique_faces']}/{group['second_unique_faces']} | {', '.join(f'{x:.3f}' for x in group['center_mm'])} | {', '.join(group['nearest_path_vertex_votes'])} | {group['maximum_pair_segment_length_mm']:.6f} | {group['maximum_plane_straddle_mm']:.6f} |")
    lines += ["","交线长度不是穿透深度，关联面面积不是穿透面积。原有接触既不自动认定为错误，也不自动认定为允许贴合。"]
    (output/"conflict_groups.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(report["counts"],report["independent_review"],flush=True)
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output",type=Path,default=ROOT)
    build(parser.parse_args().output)
