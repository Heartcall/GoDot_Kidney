"""97-anchor sensitivity at equal small target perturbations. Material D2
stencils and original cap faces never change; no per-frame triangulation choice."""
from n21_common import *
from n20_solve import capacity_step
from n16_closure_and_regions import closure_variants
from n16_contacts import classify,self_bbox_pairs
import trimesh

def run():
    protect();a,d2,tv,tf,resolved,approval=inputs();rows=[];ref=TARGETS['reference_mL']
    for strategy in ['FIXED_97','MATERIAL_MOVING_SAME_CAP_TEMPLATE']:
        m=CavityModel(a,resolved,d2,approval) if strategy=='FIXED_97' else CavityModel(a,resolved)
        for side in ['contract','expand']:
            c,p=capacity_step(m,d2,np.zeros_like(a['vertices']),side,np.ones(len(m.names)),.005*ref)
            root=ROOT/'boundary'/strategy/side;root.mkdir(parents=True,exist_ok=True);np.save(root/'cavity_offset.npy',c)
            checks=[]
            for u in [0,.25,.5,.75,1.]:
                v=d2['reference_vertices']+u*map_d2(c,d2);mesh=trimesh.Trimesh(v,d2['faces'],process=False)
                result=classify(v,d2['faces'],v,d2['faces'],self_bbox_pairs(v,d2['faces']))
                alternatives=closure_variants(v,d2,approval)
                areas=triangle_data(v,d2['faces'])[1]
                valid=bool(mesh.is_watertight and mesh.is_winding_consistent and areas.min()>1e-10 and not result['confirmed_transverse_crossings'])
                checks.append({'u':u,'original_template_domain_valid_at_sample':valid,'oriented_integral_mL':volume(v,d2['faces']),
                    'actual_capacity_mL':volume(v,d2['faces']) if valid else None,'minimum_area_mm2':float(areas.min()),
                    'self_transverse':result['confirmed_transverse_crossings'],'ear_order_comparisons':alternatives})
            q=quality(a['vertices'],a['faces'],c);boundary=np.concatenate([r['selected_boundary_vertex_ids'] for r in approval['virtual_caps']])
            report={'strategy':strategy,'direction':side,'request_relative_change':-.005 if side=='contract' else .005,
                'quality':q,'levels':checks,'maximum_material_boundary_motion_mm':float(np.linalg.norm(map_d2(c,d2)[boundary],axis=1).max()),
                'source_stencils_and_cap_indices_changed':False,'statistical_cut_relocated':False,'cap_switching_per_frame':False,
                'full_continuous_cap_collision_certified':False,'tissue_and_contact_safety_not_inferred_from_boundary_probe':True}
            write(root/'report.json',report);rows.append({'strategy':strategy,'direction':side,'physical_quality':q['quality_gate_passed'],
                'sampled_domain_valid':all(r['original_template_domain_valid_at_sample'] for r in checks),
                'max_edge_gradient':q['maximum_edge_gradient'],'min_area':q['continuous_area']['minimum_area_ratio'],
                'max_boundary_motion_mm':report['maximum_material_boundary_motion_mm'],'endpoint_oriented_integral_mL':checks[-1]['oriented_integral_mL']})
            print('BOUNDARY',rows[-1],flush=True)
    write(ROOT/'boundary/summary.json',rows);protect()

if __name__=='__main__':run()
