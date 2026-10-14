"""Exact R1 provenance, local sensitivity and plausible donor alternatives before R2 solve."""
import numpy as np
import csv
from scipy.sparse.csgraph import dijkstra
from trimesh.triangles import closest_point,points_to_barycentric
from common import *


def local_stats(tv,tf,field,faces):
    cross0,area0,_=triangle_data(tv,tf);cross,area,_=triangle_data(tv+field,tf)
    mask=np.zeros(len(tf),bool);mask[faces]=True
    return {'faces':len(faces),'minimum_area_ratio':float((area/area0)[mask].min()),'maximum_area_ratio':float((area/area0)[mask].max()),
       'maximum_normal_rotation_deg':float(np.degrees(np.arccos(np.clip(np.einsum('ij,ij->i',cross0,cross)/(4*area0*area),-1,1)))[mask].max())}


def diagnose():
    snapshot();data=read_inputs();d=data;v,f,tv,tf,old=d['v'],d['f'],d['tv'],d['tf'],d['old']
    graph,edges,length=mesh_graph(tv,tf);cgraph,_,_=mesh_graph(v,f)
    local=np.zeros(len(tv),bool);local[sum(FOCUS.values(),[])]=True
    for _ in range(2): local[edges[local[edges].any(axis=1)].ravel()]=True
    local_edges=np.flatnonzero(local[edges].any(axis=1));local_faces=np.flatnonzero(local[tf].any(axis=1))
    report_vertices=np.unique(np.r_[edges[local_edges].ravel(),tf[local_faces].ravel()])
    c0,a0,q0=triangle_data(tv,tf);c1,a1,_=triangle_data(tv+old,tf)
    records=[]
    for idx in report_vertices:
        rec=record_vertex(d,idx)
        records.append({'vertex':int(idx),'x':tv[idx,0],'y':tv[idx,1],'z':tv[idx,2],'dx':old[idx,0],'dy':old[idx,1],'dz':old[idx,2],
          'displacement_mm':rec['magnitude_mm'],'donor_face':rec['donor_face'],'bary0':d['bary'][idx,0],'bary1':d['bary'][idx,1],'bary2':d['bary'][idx,2],
          'old_constraint':rec['old_effective_constraint'],'r2_class':rec['r2_constraint_class'],'gap_mm':rec['gap_mm'],'path_ids':','.join(rec['donor_vertex_path_ids'])})
    edge_rows=[]
    for ei in local_edges:
        a,b=edges[ei];diff=old[a]-old[b]
        edge_rows.append({'v0':int(a),'v1':int(b),'reference_length_mm':length[ei],'difference_x':diff[0],'difference_y':diff[1],'difference_z':diff[2],
          'difference_mm':float(np.linalg.norm(diff)),'gradient':float(np.linalg.norm(diff)/length[ei]),'donor0':int(d['ids'][a]),'donor1':int(d['ids'][b]),'class0':d['classes'][a],'class1':d['classes'][b]})
    face_rows=[]
    for fi in local_faces:
        tri=tv[tf[fi]];normal=normalize(c0[fi][None])[0]
        face_rows.append({'face':int(fi),'v0':int(tf[fi,0]),'v1':int(tf[fi,1]),'v2':int(tf[fi,2]),'edge01_mm':float(np.linalg.norm(tri[1]-tri[0])),
           'edge12_mm':float(np.linalg.norm(tri[2]-tri[1])),'edge20_mm':float(np.linalg.norm(tri[0]-tri[2])),
           'reference_area_mm2':a0[fi],'reference_quality':q0[fi],'normal_x':normal[0],'normal_y':normal[1],'normal_z':normal[2],
           'R1_expanded_area_ratio':a1[fi]/a0[fi],'R1_normal_rotation_deg':float(np.degrees(np.arccos(np.clip(c0[fi]@c1[fi]/(4*a0[fi]*a1[fi]),-1,1))))})
    for filename,rows in [('diagnostic_vertices.csv',records),('diagnostic_edges.csv',edge_rows),('diagnostic_faces.csv',face_rows)]:
        with (OUT/filename).open('w',newline='',encoding='utf-8-sig') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    vertex_records={str(i):record_vertex(d,i) for i in sorted(set(sum(FOCUS.values(),[])))}
    f01=FOCUS['F01'];delta=old[f01[0]]-old[f01[1]]
    targets=np.einsum('ni,nij->nj',d['bary'][f01],d['driver'][f[d['ids'][f01]]])
    angle=float(np.degrees(np.arccos(np.clip(old[f01[0]]@old[f01[1]]/(np.linalg.norm(old[f01[0]])*np.linalg.norm(old[f01[1]])),-1,1))))
    f01_report={'vertices':[vertex_records[str(i)] for i in f01],'length_mm':float(np.linalg.norm(tv[f01[0]]-tv[f01[1]])),
      'difference_mm':float(np.linalg.norm(delta)),'gradient':float(np.linalg.norm(delta)/np.linalg.norm(tv[f01[0]]-tv[f01[1]])),
      'displacement_angle_deg':angle,'barycentric_donor_targets_mm':targets.tolist(),
      'donor_target_gradient':float(np.linalg.norm(targets[0]-targets[1])/np.linalg.norm(tv[f01[0]]-tv[f01[1]])),
      'cause':'Same donor triangle 8516. Hard one-ring binding at34757 versus unconstrained screened propagation at34758 creates a constraint seam. Not a donor-face or anatomical-branch jump.',
      'can_coordinate_without_changing_exact_contact':bool(not(d['exact'][f01]|d['contact'][f01]).any())}
    tri=tv[tf[53208]];cross0,area0,qual0=triangle_data(tv,tf)
    f02_report={'face':53208,'vertices':[vertex_records[str(i)] for i in tf[53208]],'normal':normalize(cross0[53208][None])[0].tolist(),
      'area_mm2':float(area0[53208]),'quality':float(qual0[53208]),'levels':[]}
    for u in (0,.25,.5,.75,1):
        moved=tri+u*old[tf[53208]];cross=np.cross(moved[1]-moved[0],moved[2]-moved[0]);normal=normalize(cross[None])[0]
        f02_report['levels'].append({'fill':u,'edge_lengths_mm':[float(np.linalg.norm(moved[a]-moved[b])) for a,b in [(0,1),(1,2),(2,0)]],
          'area_ratio':float(np.linalg.norm(cross)/(2*area0[53208])),'normal':normal.tolist(),'rotation_deg':float(np.degrees(np.arccos(np.clip(normal@normalize(cross0[53208][None])[0],-1,1))))})
    ring_vertices=np.zeros(len(tv),bool);ring_vertices[tf[53208]]=True;neighborhoods={}
    for ring in (1,2):
        ring_vertices[edges[ring_vertices[edges].any(axis=1)].ravel()]=True
        faces=np.flatnonzero(ring_vertices[tf].any(axis=1));neighborhoods[str(ring)]={'vertices':np.flatnonzero(ring_vertices).tolist(),'face_indices':faces.tolist(),'quality':local_stats(tv,tf,old,faces)}
    f02_report['rings']=neighborhoods;f02_report['relative_motion_counterfactuals']=[]
    for changed in tf[53208]:
        temp=old.copy();other=tf[53208][tf[53208]!=changed];temp[changed]=old[other].mean(axis=0)
        f02_report['relative_motion_counterfactuals'].append({'replace_vertex_with_other_two_mean':int(changed),
           'single_face':local_stats(tv,tf,temp,np.array([53208])),'two_ring':local_stats(tv,tf,temp,np.array(neighborhoods['2']['face_indices']))})
    # Distance is only the first filter; independent normal, path endpoint topology,
    # and bounded cavity-surface geodesics are reported separately.
    alternatives={};paths=d['resolved']['paths'];path_ids=[p['id'] for p in paths]
    for idx in (61933,61934,30663):
        point=tv[idx];closest=closest_point(v[f],np.repeat(point[None],len(f),axis=0));distance=np.linalg.norm(closest-point,axis=1)
        dot=d['cavity_normals']@d['tissue_normals'][idx]
        primary=set(d['owner'][f[d['ids'][idx]]]);allowed=set(primary)
        for p in primary: allowed.update(path_ids.index(name) for name in paths[int(p)]['adjacent_path_ids'])
        compatible=np.isin(d['owner'][f],list(allowed)).any(axis=1)
        geo=dijkstra(cgraph,indices=f[d['ids'][idx]],min_only=True,limit=4.)
        surface_distance=geo[f].min(axis=1)
        candidates=np.flatnonzero((distance<=distance.min()+.5)&(dot<-.5)&compatible&(surface_distance<=4))
        neighbors=np.unique(edges[(edges==idx).any(axis=1)]);neighbors=neighbors[neighbors!=idx]
        faces=np.flatnonzero((tf==idx).any(axis=1))
        chosen=[int(d['ids'][idx])]+[int(i) for i in candidates[np.argsort(distance[candidates])] if i!=d['ids'][idx]]
        records=[]
        for face in chosen:
            weights=points_to_barycentric(v[f[face]][None],closest[face][None])[0];target=weights@d['driver'][f[face]]
            field=old.copy();field[idx]=target
            records.append({'face':face,'distance_mm':float(distance[face]),'normal_dot':float(dot[face]),'normal_compatible':bool(dot[face]<-.5),
              'cavity_surface_distance_lower_bound_mm':float(surface_distance[face]),'shared_endpoint_topology_allowed':bool(compatible[face]),
              'vertex_path_ids':[paths[int(o)]['id'] for o in d['owner'][f[face]]],'barycentric':weights.tolist(),'target_mm':target.tolist(),
              'max_neighbor_difference_mm':float(np.linalg.norm(target-old[neighbors],axis=1).max()),
              'maximum_incident_edge_gradient':float((np.linalg.norm(target-old[neighbors],axis=1)/np.linalg.norm(tv[idx]-tv[neighbors],axis=1)).max()),
              'incident_faces':local_stats(tv,tf,field,faces)})
        alternatives[str(idx)]={'current':vertex_records[str(idx)],'candidates':records,'candidate_count_passing_geometrical_filters':len(candidates),
             'conclusion':'ANATOMICAL_ASSIGNMENT_UNCONFIRMED. Normal, Euclidean distance, path adjacency and surface support are geometric evidence only. Use a soft target and tissue connectivity, not a declared anatomical reassignment.'}
    result={'status':'DIAGNOSIS_BEFORE_ALGORITHM_CHANGE','local_detailed_counts':{'vertices':len(report_vertices),'edges':len(local_edges),'faces':len(local_faces)},
      'vertices':vertex_records,'F01':f01_report,'F02':f02_report,'F03_F04_alternatives':alternatives,
      'repair_choice':'Keep139 exact A and545 source-contact vertices unchanged; convert local C one-ring hard binding to soft goals; local intrinsic patch and short-edge metric regularization. Unchanged global engineering rejection gates. Outside patch and remote E unchanged. No anatomical reassignment of61933/61934/30663.'}
    (OUT/'source_diagnosis.json').write_bytes(json_bytes(result));print('F01',f01_report['cause'],'original gradient',f01_report['gradient'],'donor-only gradient',f01_report['donor_target_gradient'],flush=True)
    print('F02 counterfactual',f02_report['relative_motion_counterfactuals'],flush=True)
    for idx,record in alternatives.items(): print(idx,'geometrical alternatives',record['candidate_count_passing_geometrical_filters'],flush=True)

if __name__=='__main__': diagnose()
