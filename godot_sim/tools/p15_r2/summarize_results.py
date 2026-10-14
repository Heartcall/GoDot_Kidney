"""Global/regional R1-R2 comparison, continuous bounds and unchanged engineering gates."""
from scipy.spatial import cKDTree
from common import *
from build_cavity_morph_states import minimum_oriented_area_ratio
from trimesh.triangles import points_to_barycentric
import csv


def sample_gate_violations(q,cross,slf):
    failures=[]
    if not q['finite'] or q['degenerate_count'] or q['normal_reversal_count']: failures.append('finite/degenerate/orientation')
    if q['maximum_edge_gradient']>.2: failures.append('edge_gradient')
    if q['area_ratio_range'][0]<.8 or q['area_ratio_range'][1]>1.35: failures.append('area_ratio')
    if cross['positive_segment_count']: failures.append('finite_cavity_tissue_crossing')
    if slf['positive_segment_count'] or slf['coplanar_overlap_pair_count']: failures.append('finite_tissue_self_intersection')
    return failures


def continuous(tv,tf,field):
    a=tv[tf];h=field[tf];e1=a[:,1]-a[:,0];e2=a[:,2]-a[:,0];h1=h[:,1]-h[:,0];h2=h[:,2]-h[:,0]
    c0=np.cross(e1,e2);c1=np.cross(h1,e2)+np.cross(e1,h2);c2=np.cross(h1,h2)
    denominator=np.linalg.norm(c0,axis=1)
    # Quadratic Bezier convex-hull bound on cross-product norm, valid for EVERY u.
    controls=[c0,c0+c1/2,c0+c1+c2]
    upper=np.maximum.reduce([np.linalg.norm(c,axis=1)/denominator for c in controls])
    lower=minimum_oriented_area_ratio(tv,tf,field)
    return {'all_u_area_ratio_lower_bound':lower,'all_u_area_ratio_upper_bound':float(upper.max()),
      'all_u_edge_gradient_limit_from_expanded':True,'normals_continuous_and_not_reversed':bool(lower>0),
      'scope':'Analytic minimum oriented-area projection and quadratic Bezier norm convex-hull bound; no continuous collision certificate.'}


def summarize():
    d=read_inputs();tv,tf,old=d['tv'],d['tf'],d['old'];field=np.load(OUT/'research_tissue_displacement.npy')
    digest=source_record(OUT/'research_tissue_displacement.npy')['sha256'];build=read_json(OUT/'build_report.json')
    for name,h in build['output_sha256'].items():
        if source_record(OUT/name)['sha256']!=h: raise ValueError('Stale R2 artifact '+name)
    graph,edges,length=mesh_graph(tv,tf);c0,a0,q0=triangle_data(tv,tf);regions={}
    assigned=d['owner'][d['f'][d['ids']]]
    for i,path in enumerate(d['resolved']['paths']): regions[path['id']]=(assigned==i).any(axis=1)&(d['gap']<=2)
    for name,node in d['resolved']['nodes'].items():
        if name.startswith(('J_','T_')): regions[name]=(np.linalg.norm(tv-node['position_mm'],axis=1)<=(8 if name.startswith('J_') else 5))&(d['gap']<=3)
    for name,ids in FOCUS.items():
        mask=np.zeros(len(tv),bool);mask[ids]=True
        for _ in range(2): mask[edges[mask[edges].any(axis=1)].ravel()]=True
        regions[name]=mask
    regional={};rows=[];extrema={}
    for variant,fld in [('before',old),('after',field)]:
        cross,area,quality=triangle_data(tv+fld,tf);ratio=area/a0
        gradient=np.linalg.norm(fld[edges[:,0]]-fld[edges[:,1]],axis=1)/length;mag=np.linalg.norm(fld,axis=1)
        rotation=np.degrees(np.arccos(np.clip(np.einsum('ij,ij->i',c0,cross)/(4*a0*area),-1,1)))
        worst_edge=int(np.argmax(gradient));worst_face=int(np.argmin(ratio))
        extrema[variant]={'maximum_gradient_edge':edges[worst_edge].tolist(),'maximum_gradient':float(gradient[worst_edge]),
          'edge_center_mm':tv[edges[worst_edge]].mean(axis=0).tolist(),'minimum_area_ratio_face':worst_face,
          'minimum_area_ratio':float(ratio[worst_face]),'face_center_mm':tv[tf[worst_face]].mean(axis=0).tolist()}
        for name,mask in regions.items():
            em=mask[edges].any(axis=1);fm=mask[tf].any(axis=1)
            if not mask.any(): regional.setdefault(name,{})[variant]={'vertices':0};continue
            rec={'vertices':int(mask.sum()),'triangles':int(fm.sum()),'maximum_displacement_mm':float(mag[mask].max()),'mean_displacement_mm':float(mag[mask].mean()),'moving_vertices':int((mag[mask]>1e-12).sum()),
                'maximum_edge_gradient':float(gradient[em].max()),'minimum_area_ratio':float(ratio[fm].min()),'maximum_area_ratio':float(ratio[fm].max()),'maximum_normal_rotation_deg':float(rotation[fm].max()),
                'maximum_change_from_R1_mm':float(np.linalg.norm(fld[mask]-old[mask],axis=1).max())}
            regional.setdefault(name,{})[variant]=rec;rows.append({'region':name,'variant':variant,**rec})
    levels=[];violations=[]
    for u in (0,.25,.5,.75,1):
        tag=f'{int(u*100):03}';cross=read_json(OUT/f'cross_check_u{tag}.json');slf=read_json(OUT/f'self_check_u{tag}.json')
        if cross['field_sha256']!=digest or slf['field_sha256']!=digest: raise ValueError('Scan cache not matching R2')
        q=cross['tissue_quality']
        reasons=sample_gate_violations(q,cross,slf)
        if reasons: violations.append({'fill':u,'reason':reasons})
        # Exact local edge/face trajectory, not only the global extrema.
        local={}
        for variant,fld in [('before',old),('after',field)]:
            moved=tv[tf[53208]]+u*fld[tf[53208]];c=np.cross(moved[1]-moved[0],moved[2]-moved[0])
            local[variant]={'F01_gradient':float(u*np.linalg.norm(fld[34757]-fld[34758])/np.linalg.norm(tv[34757]-tv[34758])),
              'F02_area_ratio':float(np.linalg.norm(c)/(2*a0[53208])),
              'F02_edge_lengths_mm':[float(np.linalg.norm(moved[a]-moved[b])) for a,b in [(0,1),(1,2),(2,0)]],
              'F02_normal':normalize(c[None])[0].tolist()}
        levels.append({'fill':u,'quality_before':cross['R1_quality'],'quality_after':q,'cross':{k:v for k,v in cross.items() if k not in ['R1_quality','tissue_quality']},'self':slf,'local':local})
    bounds=continuous(tv,tf,field)
    if bounds['all_u_area_ratio_lower_bound']<.8 or bounds['all_u_area_ratio_upper_bound']>1.35: violations.append({'reason':'all-u area bound failed'})
    fixed=np.load(PROJECT/'deformation/p1_masks/port_fixed_masks.npy');ports={name:{'vertices':int(mask.sum()),'maximum_displacement_mm':float(np.linalg.norm(d['driver'][mask],axis=1).max()),'all_u_exactly_zero':bool(np.all(d['driver'][mask]==0))} for name,mask in zip(['BLADDER','IN_01','IN_02'],fixed)}
    if not all(r['all_u_exactly_zero'] for r in ports.values()): violations.append({'reason':'approved cavity fixed constraint changed'})
    cp=np.load(AUDIT/'cross_contact_pairs.npy');points=np.load(R1/'original_contact_sample_points.npy')
    # R1 sampled all3840 finite contacts, which remain fixed by all contact-face vertices.
    bc=points_to_barycentric(d['v'][d['f'][cp[:,0]]],points);bt=points_to_barycentric(tv[tf[cp[:,1]]],points)
    relative=np.einsum('ni,nij->nj',bt,field[tf[cp[:,1]]])-np.einsum('ni,nij->nj',bc,d['driver'][d['f'][cp[:,0]]])
    patch=np.load(OUT/'repair_patch_mask.npy')
    if (not np.array_equal(field[d['exact']],old[d['exact']]) or not np.array_equal(field[d['contact']],old[d['contact']])
            or not np.all(field[d['remote']]==0) or not np.array_equal(field[~patch],old[~patch])
            or np.linalg.norm(relative,axis=1).max()>1e-10 or np.linalg.norm(field,axis=1).max()>.2+1e-12):
        violations.append({'reason':'contact/exact/far/exterior/amplitude invariants failed'})
    remote=d['remote'];near_norm=np.einsum('ij,ij->i',d['tissue_normals'],d['cavity_normals'][d['ids']]);outproxy=near_norm>.5
    proxy={}
    for variant,fld in [('before',old),('after',field)]:
        proxy[variant]={'outward_facing_proxy_vertices':int(outproxy.sum()),'maximum_outward_proxy_displacement_mm':float(np.linalg.norm(fld[outproxy],axis=1).max()),
           'remote_vertices':int(remote.sum()),'remote_exact_zero':bool(np.all(fld[remote]==0)),'bounds_change_expanded_mm':(np.stack([(tv+fld).min(axis=0),(tv+fld).max(axis=0)])-np.stack([tv.min(axis=0),tv.max(axis=0)])).tolist()}
    reference_centers={};f02cause=read_json(OUT/'source_diagnosis.json')['F02']
    for group in read_json(R1/'audit_preview.json')['groups']:
        if group['id'].startswith('F'): reference_centers[group['id']]=group['center_mm']
    status='ENGINEERING_GATES_PASSED_PENDING_HUMAN_ACCEPTANCE' if not violations else 'RESEARCH_FAILED_NOT_FOR_ACCEPTANCE'
    result={'status':status,'not_final_acceptance':True,'violations':violations,'thresholds':{'gradient_maximum':.2,'area_ratio_range':[.8,1.35],'finite_cross_epsilon_mm':1e-10},
       'build':build,'five_levels':levels,'continuous':bounds,'regional_before_after':regional,'global_extrema':extrema,'cavity_fixed_ports':ports,
       'contact_consistency':{'original_sample_count':len(points),'maximum_relative_displacement_mm':float(np.linalg.norm(relative,axis=1).max()),'A139_exact_unchanged':bool(np.array_equal(field[d['exact']],old[d['exact']])),'B_contact_faces_vertices_exact_unchanged':bool(np.array_equal(field[d['contact']],old[d['contact']]))},
       'outer_remote':proxy,'anatomical_assignment_unconfirmed':[61933,61934,30663],
       'source_quality_at_F02':{'area_mm2':float(a0[53208]),'triangle_quality':float(q0[53208])},
       'limits':['All anatomical assignments remain geometric proxies; no proven inner/outer material partition or true tissue thickness.','Five-level full collision checks and all-u area/orientation bounds do not certify continuous collision freedom.','Engineering gates have no calibrated physiological mechanics meaning.','Cavity accepted field and B_24 historical record remain unchanged. No source mesh repair or P2.'],
       'candidate_generation':'Only isolated tissue same-topology states, pending human approval.' if not violations else 'No accepted candidate states.'}
    if not violations:
        candidate=OUT/'candidate';candidate.mkdir(exist_ok=True)
        for name,array in [('reference_vertices',tv),('mid_vertices',tv+.5*field),('expanded_vertices',tv+field),('faces',tf),('displacement',field)]: np.save(candidate/(name+'.npy'),array)
        result['candidate_output_sha256']={p.name:source_record(p)['sha256'] for p in sorted(candidate.glob('*.npy'))}
    (OUT/'quality_report.json').write_bytes(json_bytes(result))
    with (OUT/'regional_comparison.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(status,'regions',len(regions),'violations',violations,'continuous',bounds,flush=True)
    print('F01/F02 expanded',levels[-1]['local'],'outer',proxy,flush=True)
    return result

if __name__=='__main__': summarize()
