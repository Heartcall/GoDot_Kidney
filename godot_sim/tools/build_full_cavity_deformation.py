"""All-natural cavity extension; approved masks and local P1.3/P1.4 are read-only."""
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path

import numpy as np
from scipy.sparse import csgraph

from resolve_cavity_topology import PROJECT, read_json, json_bytes, source_record
from build_local_displacement import (load_approved_masks, path_projection, normalize,
    smoothstep, constrained_vector_smoothing, triangle_data, self_intersection_pairs)
from build_cavity_surface_masks import mesh_graph
from build_cavity_morph_states import (sample_quality, local_domains,
    continuous_diagnostics, vertex_normals, load_inputs, FILL_LEVELS, STATES)

NATURAL_IDS = ["MAIN"] + [f"B_{i:02}" for i in range(1,31)]
TRANSITION_IDS = ["BLADDER_TRANSITION", "B_31", "B_32"]
ROOT = PROJECT / "deformation/full_cavity"


def plain(value):
    """Reports must also serialize NumPy indices of REMOVED baseline pairs."""
    if isinstance(value,dict):
        return {k:plain(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):
        return [plain(v) for v in value]
    if isinstance(value,np.generic):
        return value.item()
    return value


def endpoint_adjacency(paths):
    ends = [set((p["marker_names"][0], p["marker_names"][-1])) for p in paths]
    return np.array([[bool(a & b) for b in ends] for a in ends], dtype=bool)


def restricted_surface_graph(graph,eligible):
    restricted=graph.multiply(eligible[:,None]).multiply(eligible[None,:]).tocsr()
    # SciPy treats explicit stored zero entries as zero-cost graph edges.
    # Remove them so excluded owners/fixed walls truly block propagation.
    restricted.eliminate_zeros()
    return restricted


def topological_candidates(arrays, resolved, graph, config):
    vertices, owners = arrays["vertices"], arrays["path_owner"]
    normals = normalize(arrays["normals"].astype(float))
    fixed = arrays["port_fixed_masks"].any(axis=0)
    paths = resolved["paths"]
    selected = [i for i,p in enumerate(paths) if p["id"] in NATURAL_IDS + TRANSITION_IDS]
    adjacency = endpoint_adjacency(paths)
    projections = [path_projection(vertices, np.asarray(p["points_mm"])) for p in paths]
    support_weights, vectors, details = [], [], []
    for index in selected:
        path = paths[index]
        distance, center, tangent, arc, length = projections[index]
        belongs = (owners == index) & ~fixed
        if not belongs.any():
            raise ValueError(f"Path has no free surface vertices: {path['id']}")
        radius = max(.5, float(np.median(distance[belongs])))
        support = min(config["junction_surface_support_mm"], 1.5*radius)
        # Travel ONLY through this path and paths sharing a real endpoint.
        eligible = adjacency[index,owners] & ~fixed
        restricted = restricted_surface_graph(graph,eligible)
        geodesic = csgraph.dijkstra(restricted, directed=False, indices=np.flatnonzero(belongs),
                                   min_only=True, limit=support)
        gate = 1-smoothstep(geodesic/support)
        # The candidate may enter an adjacent branch only near their shared
        # endpoint, not along an entire close/parallel neighbor.
        for other in np.unique(owners[eligible & ~belongs]):
            shared = set((path["marker_names"][0],path["marker_names"][-1])) & set((paths[other]["marker_names"][0],paths[other]["marker_names"][-1]))
            if not shared:
                continue
            knot = next(iter(shared))
            other_arc, other_length = projections[other][3:]
            other_progress = other_arc if paths[other]["marker_names"][0] == knot else other_length-other_arc
            own_progress = arc if path["marker_names"][0] == knot else length-arc
            collar = min(config["junction_axial_support_mm"], .45*min(length,other_length))
            on_other = owners == other
            gate[on_other] *= (1-smoothstep(other_progress[on_other]/collar)) * (1-smoothstep(own_progress[on_other]/collar))
        gate[~eligible] = 0
        gate[belongs] = 1
        radial = vertices-center
        radial -= np.einsum("ij,ij->i",radial,tangent)[:,None]*tangent
        radial -= np.minimum(np.einsum("ij,ij->i",radial,normals),0)[:,None]*normals
        radial = normalize(radial)
        mix = np.full(len(vertices),config["wall_normal_mix"])
        terminal = path["marker_names"][-1].startswith("T_")
        if terminal:
            cap = smoothstep((arc-max(0,length-2*radius))/min(length,2*radius))
            mix += (config["terminal_normal_mix"]-config["wall_normal_mix"])*cap
        vector = (1-mix[:,None])*radial+mix[:,None]*normals
        kernel = np.exp(-.5*np.minimum((distance/radius)**2,100)) * gate
        vectors.append(vector)
        support_weights.append(kernel)
        details.append({"id":path["id"],"radius_mm":radius,"surface_support_mm":support,
                        "own_vertices":int(belongs.sum()),"supported_vertices":int(np.sum(kernel>0)),
                        "terminal_normal_blend":terminal})
    weights = np.asarray(support_weights)
    denominator = weights.sum(axis=0)
    weights = np.divide(weights,denominator[None,:],out=np.zeros_like(weights),where=denominator[None,:]>0)
    candidate = np.einsum("pn,pni->ni",weights,np.asarray(vectors))
    fallback = (~fixed) & (denominator==0)
    candidate[fallback] = normals[fallback]
    candidate[fixed] = 0
    return candidate, weights, selected, details, {"fallback_normal_vertices":int(fallback.sum()),
        "maximum_candidates_at_vertex":int((weights>0).sum(axis=0).max()),
        "mean_candidates_at_free_vertex":float((weights[:,~fixed]>0).sum(axis=0).mean()),
        "nonadjacent_candidate_weight_maximum":float(max((weights[k,~adjacency[i,owners]].max(initial=0) for k,i in enumerate(selected)),default=0))}


def make_full_field(arrays,resolved,config):
    vertices,faces = arrays["vertices"],arrays["faces"]
    fixed = arrays["port_fixed_masks"].any(axis=0)
    graph,edges,lengths = mesh_graph(vertices,faces)
    normals = normalize(arrays["normals"].astype(float))
    candidate,weights,selected,details,support_report = topological_candidates(arrays,resolved,graph,config)
    field = constrained_vector_smoothing(graph,candidate,fixed,~fixed,config["vector_smoothing_strength"])
    field -= np.minimum(np.einsum("ij,ij->i",field,normals),0)[:,None]*normals
    field *= config["maximum_displacement_mm"] / np.linalg.norm(field,axis=1).max()
    displacement = field*arrays["weights"][:,None]
    displacement[fixed] = 0
    return displacement,candidate,weights,selected,details,support_report,graph,edges,lengths


def region_stats(vertices,displacement,faces,resolved,arrays,edges,lengths):
    magnitude = np.linalg.norm(displacement,axis=1)
    difference = np.linalg.norm(displacement[edges[:,0]]-displacement[edges[:,1]],axis=1)
    paths = resolved["paths"]
    stats = {"paths":{},"junctions":{},"terminals":{}}
    def summarize(mask):
        free = mask & ~arrays["port_fixed_masks"].any(axis=0)
        local_edges = free[edges].any(axis=1)
        values = magnitude[free]
        return {"vertices":int(mask.sum()),"free_vertices":int(free.sum()),
            "moved_over_1e_8mm":int(np.sum(values>1e-8)),"minimum_mm":float(values.min()) if len(values) else 0,
            "mean_mm":float(values.mean()) if len(values) else 0,"maximum_mm":float(values.max()) if len(values) else 0,
            "maximum_neighbor_difference_mm":float(difference[local_edges].max()) if local_edges.any() else 0,
            "maximum_edge_gradient":float((difference[local_edges]/lengths[local_edges]).max()) if local_edges.any() else 0}
    for i,path in enumerate(paths):
        if path["id"] not in NATURAL_IDS+TRANSITION_IDS:
            continue
        stats["paths"][path["id"]] = summarize(arrays["path_owner"]==i)
    for name,node in resolved["nodes"].items():
        if not name.startswith(("J_","T_")):
            continue
        adjacent = [i for i,p in enumerate(paths) if name in (p["marker_names"][0],p["marker_names"][-1])]
        domain = np.isin(arrays["path_owner"],adjacent) & (np.linalg.norm(vertices-node["position_mm"],axis=1)<=8)
        entry = summarize(domain)
        entry["adjacent_paths"] = [paths[i]["id"] for i in adjacent]
        if name.startswith("T_"):
            path = paths[adjacent[0]]
            points = np.asarray(path["points_mm"])
            tangent = normalize((points[-1]-points[-2])[None,:])[0]
            cap = (arrays["path_owner"]==adjacent[0]) & ((vertices-points[-1])@tangent>=0)
            entry["cap_vertices"] = int(cap.sum())
            entry["cap_mean_axial_displacement_mm"] = float((displacement[cap]@tangent).mean()) if cap.any() else None
            entry["cap_mean_displacement_mm"] = float(magnitude[cap].mean()) if cap.any() else None
            stats["terminals"][name] = entry
        else:
            stats["junctions"][name] = entry
    return stats


def all_domains(arrays,resolved,edges):
    domains=local_domains(arrays["vertices"],arrays,resolved,edges)
    paths=resolved["paths"]
    for name,node in resolved["nodes"].items():
        if name.startswith(("J_","T_")):
            adjacent=[i for i,p in enumerate(paths) if name in (p["marker_names"][0],p["marker_names"][-1])]
            domains[name]=np.isin(arrays["path_owner"],adjacent) & (np.linalg.norm(arrays["vertices"]-node["position_mm"],axis=1)<=8)
    for i,p in enumerate(paths):
        if p["id"] in NATURAL_IDS+TRANSITION_IDS:
            domains[p["id"]+"_PATH"]=arrays["path_owner"]==i
    return domains


def compare_local_baseline(arrays,displacement,resolved,stats):
    old=np.load(PROJECT/"deformation/p14_morph/displacement.npy")
    difference=np.linalg.norm(displacement-old,axis=1)
    ids=[p["id"] for p in resolved["paths"]]
    paths={}
    for name in NATURAL_IDS:
        domain=arrays["path_owner"]==ids.index(name)
        paths[name]={"local_mean_mm":float(np.linalg.norm(old[domain],axis=1).mean()),
                     "full_mean_mm":stats["paths"][name]["mean_mm"],
                     "mean_vector_change_mm":float(difference[domain].mean())}
    return {"baseline":source_record(PROJECT/"deformation/p14_morph/interpolation_report.json"),
        "same_reference_vertices":bool(np.array_equal(arrays["vertices"],np.load(PROJECT/"deformation/p14_morph/reference_vertices.npy"))),
        "same_faces":bool(np.array_equal(arrays["faces"],np.load(PROJECT/"deformation/p14_morph/faces.npy"))),
        "local_moved_vertices":int(np.sum(np.linalg.norm(old,axis=1)>1e-8)),
        "full_moved_vertices":int(np.sum(np.linalg.norm(displacement,axis=1)>1e-8)),
        "newly_moving_vertices":int(np.sum((np.linalg.norm(old,axis=1)<=1e-8)&(np.linalg.norm(displacement,axis=1)>1e-8))),
        "paths":paths,
        "interpretation":"Local baseline is preserved, not forced as a full-field target; topology gating and stronger smoothing change local vectors too."}


def export_full(root,arrays,resolved,config,displacement,candidate,weights,selected,details,support,edges,lengths,baseline,config_path):
    stats=region_stats(arrays["vertices"],displacement,arrays["faces"],resolved,arrays,edges,lengths)
    for name in NATURAL_IDS:
        if stats["paths"][name]["mean_mm"]<=.02:
            raise ValueError(f"Natural branch did not expand: {name}")
    for kind in ("junctions","terminals"):
        for name,entry in stats[kind].items():
            if entry["moved_over_1e_8mm"]!=entry["free_vertices"] or entry["maximum_mm"]<=.02:
                raise ValueError(f"Missing active natural region: {name}")
            if kind=="terminals" and (not entry["cap_vertices"] or entry["cap_mean_axial_displacement_mm"]<=0):
                raise ValueError(f"Terminal cap response failed: {name}")
    domains=all_domains(arrays,resolved,edges)
    endpoint,normal,pairs=sample_quality(arrays["vertices"],arrays["faces"],displacement,1.,baseline,arrays,domains,edges,lengths)
    endpoint=plain(endpoint)
    continuous=continuous_diagnostics(arrays["vertices"],arrays["faces"],displacement)
    field_dir=root/"field"
    field_dir.mkdir(parents=True,exist_ok=True)
    generated={"reference_vertices":arrays["vertices"],"faces":arrays["faces"],"displacement":displacement,
        "displacement_magnitude_mm":np.linalg.norm(displacement,axis=1),"displacement_direction":normalize(displacement),
        "candidate_direction":normalize(candidate),"candidate_weights":weights,"candidate_path_indices":np.asarray(selected),
        "approved_p12_weights":arrays["weights"],"reference_normals":vertex_normals(arrays["vertices"],arrays["faces"]),
        "deformed_normals":normal,"reference_self_intersection_pairs":baseline,"deformed_self_intersection_pairs":pairs}
    for name,value in generated.items():
        np.save(field_dir/(name+".npy"),value,allow_pickle=False)
    mask_hashes={p.name:source_record(p)["sha256"] for p in sorted((PROJECT/"deformation/p1_masks").iterdir()) if p.is_file()}
    junction_connections={name:[p["id"] for p in resolved["paths"] if name in (p["marker_names"][0],p["marker_names"][-1])] for name in ("J_05","J_09")}
    report={"schema_version":"1.0","status":"ALL_NATURAL_STATIC_VALIDATED_PENDING_USER_REVIEW", "unit":"mm",
        "configuration":config,"coordinate_system":"cavity_mesh_local","selected_path_ids":NATURAL_IDS+TRANSITION_IDS,
        "approved_mask_sha256":mask_hashes,
        "output_sha256":{name+".npy":source_record(field_dir/(name+".npy"))["sha256"] for name in generated},
        "sources":{"builder":source_record(__file__),"config":source_record(config_path),
            "p12_report":source_record(PROJECT/"deformation/p1_masks/surface_mask_report.json"),
            "p14_baseline":source_record(PROJECT/"deformation/p14_morph/interpolation_report.json"),
            "resolved":source_record(PROJECT/"deformation/cavity_topology_resolved.json")},
        "methods":{"candidate_gate":"Shared endpoint adjacency + restricted intrinsic surface distance + endpoint arc collars; no nonadjacent candidate mixture.",
            "field":"Radial projection, wall normals, terminal caps; screened vector Laplacian on connected surface; no coordinate smoothing.",
            "amplitude":"No local test activation envelope. Global 0.2 mm bound times the exact approved P1.2 material weights.",
            "smoothing":"Strength 120 resolves one source B_26 skinny triangle exceeding area-change bound at strength 30."},
        "support":support,"candidate_paths":details,"region_statistics":stats,
        "important_connections":junction_connections,"endpoint_quality":endpoint,"continuous_diagnostics":continuous,
        "local_baseline_comparison":compare_local_baseline(arrays,displacement,resolved,stats),
        "baseline_intersection":{"reference_pairs":baseline.tolist(),"expanded_pairs":pairs.tolist(),
            "new_pairs":endpoint["new_intersection_pairs"],"removed_pairs":endpoint["removed_baseline_pairs"],
            "note":"B_24 source geometry is untouched. Displaced triangles may separate; baseline pairs remain recorded even if absent at Expanded."}}
    (field_dir/"displacement_report.json").write_bytes(json_bytes(report))
    print("Static field passed; building the reused P1.4 five-fill pipeline...",flush=True)
    morph=build_full_morph(root/"morph",field_dir,arrays,resolved,displacement,baseline,domains,edges,lengths)
    # Extend only the NEW outputs; the accepted P1.4 implementation is unchanged.
    morph["status"]="ALL_NATURAL_MORPH_VALIDATED_PENDING_USER_REVIEW"
    morph["formula"]="x(u) = reference + u * full_natural_displacement; Mid = x(0.5)"
    morph["user_accepted_input"]="P1.2 masks and local P1.4 reference accepted; all-natural extension awaits user review."
    morph["sources"]["field_report"]=morph["sources"].pop("p13_report")
    morph["sources"]["field_displacement"]=morph["sources"].pop("p13_displacement")
    morph["sources"]["full_builder"]=source_record(__file__)
    morph["limits"]=["Five-fill self-intersection tests are not a continuous collision certificate.",
        "B_24 reference intersection is recorded; changes to its pair status are reported per fill.",
        "0.2 mm geometric debug field; no calibrated material, tissue, flow, pressure, dynamic collision or video."]
    (root/"morph/interpolation_report.json").write_bytes(json_bytes(morph))
    meta=read_json(root/"morph/morph_preview.json")
    meta["sources"]=morph["sources"]
    meta["landmarks"]={name:node["position_mm"] for name,node in resolved["nodes"].items() if name.startswith(("J_","T_"))}
    meta["focus_camera"]=choose_focus_cameras(arrays,resolved)
    (root/"morph/morph_preview.json").write_bytes(json_bytes(meta))
    (root/"region_statistics.json").write_bytes(json_bytes(stats))
    (root/"local_baseline_comparison.json").write_bytes(json_bytes(report["local_baseline_comparison"]))
    write_coverage_table(root,stats,report["local_baseline_comparison"])
    print("All-natural field and morphs validated.",flush=True)
    return report,morph


def write_coverage_table(root,stats,comparison):
    lines=["# 全天然腔体位移覆盖统计", "", "Expanded，单位 mm。只统计非固定顶点；端帽轴向正值表示向外。", ""]
    for kind,title in (("paths","全部路径"),("junctions","全部分叉"),("terminals","全部末端")):
        lines += ["## "+title,"","| 区域 | 非固定顶点 | 移动顶点 | 最小位移 | 平均位移 | 最大位移 | 最大边位移梯度 |","| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for name,entry in stats[kind].items():
            lines.append(f"| {name} | {entry['free_vertices']} | {entry['moved_over_1e_8mm']} | {entry['minimum_mm']:.6f} | {entry['mean_mm']:.6f} | {entry['maximum_mm']:.6f} | {entry['maximum_edge_gradient']:.6f} |")
        lines.append("")
    lines += ["## 端帽响应","","| 末端 | 端帽顶点 | 端帽平均位移 | 平均向外轴向位移 |","| --- | ---: | ---: | ---: |"]
    for name,entry in stats["terminals"].items():
        lines.append(f"| {name} | {entry['cap_vertices']} | {entry['cap_mean_displacement_mm']:.6f} | {entry['cap_mean_axial_displacement_mm']:.6f} |")
    lines += ["","## 与 P1.4 局部基准比较","","| 路径 | 局部平均位移 | 全天然平均位移 | 平均向量变化 |","| --- | ---: | ---: | ---: |"]
    for name,entry in comparison["paths"].items():
        lines.append(f"| {name} | {entry['local_mean_mm']:.6f} | {entry['full_mean_mm']:.6f} | {entry['mean_vector_change_mm']:.6f} |")
    (root/"coverage_statistics.md").write_text("\n".join(lines)+"\n",encoding="utf-8")


def build_full_morph(output_dir,field_dir,arrays,resolved,displacement,baseline,domains,edges,lengths):
    # Reuse P1.4 geometry validators, normals, continuous diagnostics, exact
    # linear formula and KMOR0001 layout, with all-region diagnostics.
    reference,faces=arrays["vertices"],arrays["faces"]
    origin=np.rint((reference.min(axis=0)+reference.max(axis=0))*.5)
    generated={"reference_vertices":reference,"faces":faces,"displacement":displacement}
    samples,quantized_samples=[],[]
    for fill in FILL_LEVELS:
        print(f"Checking full filling {fill:.2f} (float64 and centered float32)...",flush=True)
        sample,normals,pairs=sample_quality(reference,faces,displacement,fill,baseline,arrays,domains,edges,lengths)
        samples.append(plain(sample))
        generated[f"intersections_u{int(fill*100):03}"]=pairs
        for state,level in STATES.items():
            if level==fill:
                generated[state+"_vertices"]=reference+fill*displacement
                generated[state+"_normals"]=normals
        q=((reference-origin).astype(np.float32)+np.float32(fill)*displacement.astype(np.float32)).astype(float)
        qp=self_intersection_pairs(q,faces)
        cross,area,_=triangle_data(q,faces)
        c0,_,_=triangle_data(reference,faces)
        fixed=arrays["port_fixed_masks"].any(axis=0)
        check={"fill":fill,"maximum_coordinate_roundoff_mm":float(np.abs(q+origin-reference-fill*displacement).max()),
            "degenerate_triangles":int(np.sum(area<1e-10)),"normal_reversals":int(np.sum(np.einsum("ij,ij->i",cross,c0)<=0)),
            "intersection_pairs":qp.tolist(),"new_intersection_pairs":plain(sorted(set(map(tuple,qp))-set(map(tuple,baseline)))),
            "removed_baseline_pairs":plain(sorted(set(map(tuple,baseline))-set(map(tuple,qp)))),
            "fixed_coordinates_exactly_unchanged":bool(np.array_equal(q[fixed],(reference-origin).astype(np.float32)[fixed]))}
        if check["degenerate_triangles"] or check["normal_reversals"] or check["new_intersection_pairs"] or not check["fixed_coordinates_exactly_unchanged"]:
            raise ValueError(f"Full float32 geometry failed at {fill}: {check}")
        quantized_samples.append(check)
    if not np.all(np.diff([s["volume_mm3"] for s in samples])>0):
        raise ValueError("Full cavity volume is not monotonically increasing")
    output_dir.mkdir(parents=True,exist_ok=True)
    for name,value in generated.items():
        np.save(output_dir/(name+".npy"),value,allow_pickle=False)
    raw=bytearray(b"KMOR0001"+struct.pack("<II",len(reference),len(faces)))
    for name in ("reference_vertices","displacement","reference_normals","mid_normals","expanded_normals"):
        values=generated[name]-origin if name=="reference_vertices" else generated[name]
        raw.extend(np.asarray(values,dtype="<f4").tobytes())
    raw.extend(np.asarray(faces[:,::-1],dtype="<u4").tobytes())
    (output_dir/"morph_preview.bin").write_bytes(raw)
    (output_dir/"fixed_vertex_indices.json").write_bytes(json_bytes(np.flatnonzero(fixed).tolist()))
    hashes={name+".npy":source_record(output_dir/(name+".npy"))["sha256"] for name in generated}
    for name in ("morph_preview.bin","fixed_vertex_indices.json"):
        hashes[name]=source_record(output_dir/name)["sha256"]
    sources={"p13_report":source_record(field_dir/"displacement_report.json"),"p13_displacement":source_record(field_dir/"displacement.npy"),
        "p12_report":source_record(PROJECT/"deformation/p1_masks/surface_mask_report.json"),
        "resolved":source_record(PROJECT/"deformation/cavity_topology_resolved.json"),
        "builder":source_record(PROJECT/"tools/build_cavity_morph_states.py")}
    report={"schema_version":"1.0","unit":"mm","coordinate_system":"cavity_mesh_local",
        "vertex_count":len(reference),"triangle_count":len(faces),"states":STATES,"same_topology_all_states":True,
        "sources":sources,"output_sha256":hashes,"samples":samples,"godot_float32_samples":quantized_samples,
        "godot_preview_origin_mm":origin.tolist(),"volume_strictly_increasing_at_samples":True,
        "baseline_intersection":{"location":"B_24","pairs":baseline.tolist()},
        "continuous_diagnostics":continuous_diagnostics(reference,faces,displacement),
        "normal_method":"Area-weighted normals recomputed from each fill's actual geometry."}
    mask_report=read_json(PROJECT/"deformation/p1_masks/surface_mask_report.json")
    meta={"schema_version":"1.0","binary_file":"morph_preview.bin","binary_sha256":hashlib.sha256(raw).hexdigest(),
        "vertex_count":len(reference),"triangle_count":len(faces),"maximum_displacement_mm":float(np.linalg.norm(displacement,axis=1).max()),
        "states":STATES,"sample_fills":FILL_LEVELS,"landmarks":{},"sources":sources,"preview_origin_mm":origin.tolist(),
        "bounds_mm":[reference.min(axis=0).tolist(),reference.max(axis=0).tolist()],"fixed_vertices":int(fixed.sum()),
        "fixed_indices_sha256":hashes["fixed_vertex_indices.json"],
        "paths":[{"id":p["id"],"points_mm":p["points_mm"]} for p in resolved["paths"]],
        "selected_path_ids":NATURAL_IDS+TRANSITION_IDS,"source_mesh":mask_report["sources"]["cavity_mesh"],
        "approved_weight_source":source_record(PROJECT/"deformation/p1_masks/weights.npy")}
    (output_dir/"morph_preview.json").write_bytes(json_bytes(meta))
    return report


def choose_focus_cameras(arrays,resolved):
    # Select an outward view from wall normals near each node. Rendering checks
    # can adjust individual presets without changing any marker or field.
    result={}
    vertices=arrays["vertices"]
    for name,node in resolved["nodes"].items():
        if not name.startswith(("J_","T_")):
            continue
        distances=np.linalg.norm(vertices-node["position_mm"],axis=1)
        nearest=np.argsort(distances)[:30]
        normal=normalize(np.mean(arrays["normals"][nearest],axis=0)[None,:])[0]
        if np.linalg.norm(normal)<.5:
            normal=np.array([.5,.4,.7]);normal/=np.linalg.norm(normal)
        result[name]={"yaw":float(np.arctan2(normal[0],normal[2])),"pitch":float(np.arcsin(np.clip(normal[1],-.95,.95))),
                      "distance":36. if name.startswith("J_") else 28.}
    result["J_01"]={"yaw":-2.4,"pitch":.3,"distance":36.}
    result["J_02"]={"yaw":.6,"pitch":.55,"distance":36.}
    return result


def diagnose(vertices,faces,displacement,edges,lengths,baseline):
    c0,a0,_ = triangle_data(vertices,faces)
    cross,area,_ = triangle_data(vertices+displacement,faces)
    ratios = area/a0
    cosine = np.einsum("ij,ij->i",c0,cross)/(4*a0*area)
    gradient = np.linalg.norm(displacement[edges[:,0]]-displacement[edges[:,1]],axis=1)/lengths
    pairs = self_intersection_pairs(vertices+displacement,faces)
    added = sorted(set(map(tuple,pairs))-set(map(tuple,baseline)))
    return {"area_ratio_range":[float(ratios.min()),float(ratios.max())],
        "degenerate":int(np.sum(area<1e-10)),"reversed":int(np.sum(cosine<=0)),
        "maximum_edge_gradient":float(gradient.max()),"intersection_pairs":pairs.tolist(),
        "new_intersection_pairs":[list(p) for p in added],
        "bad_area_faces":np.flatnonzero((ratios<.8)|(ratios>1.35)).tolist(),
        "bad_gradient_edges":edges[gradient>.2].tolist()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,default=PROJECT/"deformation/full_cavity_config.json")
    parser.add_argument("--diagnose-only",action="store_true")
    args=parser.parse_args()
    config=read_json(args.config)
    if (not 0<config["maximum_displacement_mm"]<=.2 or config["vector_smoothing_strength"]<=0
        or not 0<=config["wall_normal_mix"]<=config["terminal_normal_mix"]<=1
        or min(config["junction_surface_support_mm"],config["junction_axial_support_mm"])<=0):
        parser.error("Invalid full-field configuration")
    # Validate the accepted baseline files, without rebuilding them.
    load_inputs(PROJECT/"deformation/p13_static")
    arrays,mask_report,_=load_approved_masks(PROJECT/"deformation/p1_masks",PROJECT/"deformation/cavity_topology_resolved.json")
    resolved=read_json(PROJECT/"deformation/cavity_topology_resolved.json")
    displacement,candidate,weights,selected,details,support,graph,edges,lengths=make_full_field(arrays,resolved,config)
    baseline=np.load(PROJECT/"deformation/p13_static/reference_self_intersection_pairs.npy")
    diagnostic=diagnose(arrays["vertices"],arrays["faces"],displacement,edges,lengths,baseline)
    debug=PROJECT/"analysis/irrigation_baseline/full_cavity"
    debug.mkdir(parents=True,exist_ok=True)
    np.save(debug/"initial_displacement.npy",displacement)
    (debug/"initial_diagnostic.json").write_bytes(json_bytes(diagnostic))
    print({k:v for k,v in diagnostic.items() if k not in ("bad_area_faces","bad_gradient_edges")},flush=True)
    if args.diagnose_only:
        print("bad area faces:",len(diagnostic["bad_area_faces"]),"bad gradient edges:",len(diagnostic["bad_gradient_edges"]),flush=True)
        return
    if (diagnostic["degenerate"] or diagnostic["reversed"] or diagnostic["new_intersection_pairs"]
        or diagnostic["bad_area_faces"] or diagnostic["bad_gradient_edges"]):
        parser.error("Full static field failed; see initial_diagnostic.json. No verified morphs generated.")
    export_full(ROOT,arrays,resolved,config,displacement,candidate,weights,selected,details,support,edges,lengths,baseline,args.config)


if __name__=="__main__":
    main()
