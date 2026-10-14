"""Independent readback and deterministic rebuild checks; no accepted geometry writes."""
from n1_analysis import *

def verify(repeat=False):
    result={'repeat_build':None,'graphics':{},'accepted_inputs_unchanged':True}
    if repeat:
        products=read_json(ROOT/'build_manifest.json')['products']
        before={name:sha(ROOT/name) for name in products if 'matplotlib_cache' not in name}
        build()
        changed=[name for name,digest in before.items() if sha(ROOT/name)!=digest]
        result['repeat_build']={'checked_products':len(before),'changed':changed,'byte_identical':not changed}
        if changed:raise ValueError('Non-deterministic analysis products: '+str(changed))
        write_json(ROOT/'verification/repeat_build_checks.json',{**result['repeat_build'],'product_sha256':before})
    elif (ROOT/'verification/repeat_build_checks.json').exists():
        previous=read_json(ROOT/'verification/repeat_build_checks.json')
        if all(sha(ROOT/name)==digest for name,digest in previous['product_sha256'].items()):
            result['repeat_build']={k:previous[k] for k in ['checked_products','changed','byte_identical']}
    for backend in ['compatibility_delivery','forward_delivery']:
        directory=ROOT/'verification'/backend
        checks=read_json(directory/'runtime_checks.json');log=(directory/'godot_stdout.log').read_text(encoding='utf8',errors='replace')
        if checks['failures'] or 'ERROR:' in log or 'SCRIPT ERROR:' in log:raise ValueError('Godot runtime error '+backend)
        rows={}
        for name,filename in [('wall','original_wall.bin'),('caps','virtual_caps.bin')]:
            raw=(ROOT/'d2'/filename).read_bytes();n,m=struct.unpack_from('<II',raw,8)
            expected_positions=raw[16:16+12*n];expected_normals=np.frombuffer(raw,dtype='<f4',count=3*n,offset=16+12*n).reshape(-1,3)
            expected_indices=raw[16+24*n:]
            actual_pos=(directory/(name+'_actual_positions.bin')).read_bytes();actual_idx=(directory/(name+'_actual_indices.bin')).read_bytes()
            actual_normals=np.fromfile(directory/(name+'_actual_normals.bin'),dtype='<f4').reshape(-1,3)
            used=np.unique(np.frombuffer(expected_indices,dtype='<i4'))
            error=float(np.max(abs(actual_normals[used]-expected_normals[used])))
            rows[name]={'positions_float32_byte_exact':actual_pos==expected_positions,'indices_byte_exact':actual_idx==expected_indices,
                        'normal_finite':bool(np.isfinite(actual_normals).all()),'normal_max_component_difference':error,
                        'used_vertices':len(used),'unreferenced_vertices_not_surface_normals':n-len(used),
                        'normal_difference_note':'Used vertices only: ArrayMesh standard octahedral packing/readback. Original input normals retained; color toggles checked byte-exact against initial actual normals.'}
            if name=='wall':
                rows[name]['normal_byte_exact_after_repeated_color_changes']=(directory/'wall_initial_actual_normals.bin').read_bytes()==(directory/'wall_actual_normals.bin').read_bytes()
                if not rows[name]['normal_byte_exact_after_repeated_color_changes']:raise ValueError('Normal re-quantization regression')
            if actual_pos!=expected_positions or actual_idx!=expected_indices or not np.isfinite(actual_normals).all():
                raise ValueError('Measurement ArrayMesh differs '+str(rows[name]))
        for name in ['cavity','tissue']:
            baseline=PROJECT/'deformation/capacity_v2_n0_closeout/verification/compatibility'/(name+'_u000.bin')
            actual=directory/(name+'_Reference.bin')
            rows[name+'_accepted_Reference']={'whole_actual_mesh_byte_exact_to_N0':actual.read_bytes()==baseline.read_bytes()}
            if actual.read_bytes()!=baseline.read_bytes():raise ValueError('Accepted Reference changed '+name)
        _,a=verify_sources();fixed=np.load(PROJECT/'deformation/p1_masks/port_fixed_masks.npy').any(0)
        n=len(a['cavity_reference_vertices']);pos=np.fromfile(directory/'cavity_Reference.bin',dtype='<f4',count=n*3).reshape(-1,3)
        expected=(a['cavity_reference_vertices']-ORIGIN).astype('<f4')
        if not np.array_equal(pos[fixed],expected[fixed]):raise ValueError('Fixed vertex regression')
        rows['fixed_cavity_vertices_exact']=int(fixed.sum());rows['runtime_checks']=len(checks['checks']);rows['screenshots']=len(checks['captures'])
        result['graphics'][backend]=rows
    result['protected_files_unchanged']=protect()
    write_json(ROOT/'verification/independent_checks.json',result)
    print(json.dumps(result,indent=2))

if __name__=='__main__':verify('--repeat-build' in sys.argv)
