"""Preserve accepted P2.1/P2.2 before P2.3; never overwrite previous records."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'p2'))
from prepare_runtime import *

STAGE=PROJECT/'deformation/p23'
OUT=PROJECT/'analysis/irrigation_baseline/p23'
ALLOWED=['godot_sim/scripts/p2/control_preview.gd','godot_sim/scripts/p2/deformation_player.gd',
         'godot_sim/irrigation_control_preview.tscn']


def freeze():
    verify_sources()
    if (STAGE/'p21_p22_acceptance.json').exists():
        raise ValueError('Baseline already frozen; do not overwrite acceptance or historical data')
    STAGE.mkdir(parents=True,exist_ok=True);(STAGE/'baseline').mkdir()
    names=subprocess.check_output(['git','ls-files','-z'],cwd=REPO).decode('utf8').split('\0')
    paths={REPO/name for name in names if name and (REPO/name).is_file()}
    old=read_json(PROJECT/'deformation/p2/verification/protected_before.json')
    paths.update(REPO/name for name in old if (REPO/name).is_file())
    protected={p.relative_to(REPO).as_posix():sha(p) for p in sorted(paths)}
    write_json(STAGE/'protected_before.json',protected)
    for name in ['deformation_player.gd','irrigation_controller.gd','control_preview.gd']:
        shutil.copyfile(PROJECT/'scripts/p2'/name,STAGE/'baseline'/name)
    shutil.copyfile(PROJECT/'irrigation_control_preview.tscn',STAGE/'baseline/irrigation_control_preview.tscn.txt')
    write_json(STAGE/'p21_p22_acceptance.json',{
        'date':'2026-10-14','stage':'P2.1+P2.2','status':'USER_ACCEPTED_FUNCTIONAL_BASELINE',
        'confirmed':['inject','drain','pause_resume','hold','reset','synchronous_cavity_tissue_deformation'],
        'subjective_experience':'User observed no obvious stutter in actual Godot interaction.',
        'quantitative_30fps_status':'NOT_YET_PROVEN_BY_CONTINUOUS_FRAME_MEASUREMENT',
        'historical_measurements_preserved':True,'input_manifest_sha256':sha(ROOT/'accepted_inputs.json'),
        'baseline_sha256':{p.name:sha(p) for p in sorted((STAGE/'baseline').iterdir())},
        'allowed_p23_code_changes':ALLOWED,
        'authorized_existing_visibility_setting':'TissueReference.visible=false retained unchanged',
    })
    resolved=read_json(PROJECT/'deformation/cavity_topology_resolved.json')
    markers=read_json(PROJECT/'deformation/irrigation_markers.json')['markers']
    focus={}
    for marker in markers:
        name=marker['name']
        if name.startswith(('J_','T_')):
            focus[name]={'center_mm':marker['cavity_local_position_mm'],'distance_mm':28.,'normal':[.4,.3,1.]}
    for path in resolved['paths']:
        if path['id'] in ['MAIN','B_31','B_32','BLADDER','IN_01','IN_02']:
            focus[path['id']]={'center_mm':np.mean(path['points_mm'],axis=0).tolist(),
                               'distance_mm':max(16.,float(path['length_mm'])*2),'normal':[.4,.3,1.]}
    # Reuse geometric F01-F04 observation positions, not anatomical reassignment.
    for group in read_json(R2/'preview.json')['groups']:
        if group['id'].startswith('F'):
            focus[group['id']]={'center_mm':group['center_mm'],'normal':group['view_normal'],
                                'distance_mm':6. if group['id'] in ['F01','F02'] else 16.}
    write_json(STAGE/'focus_locations.json',{'origin_mm':ORIGIN.tolist(),'locations':focus,
        'sources':{'markers':sha(PROJECT/'deformation/irrigation_markers.json'),
                   'resolved':sha(PROJECT/'deformation/cavity_topology_resolved.json'),'r2_preview':sha(R2/'preview.json')},
        'purpose':'Observation targets only. No geometry, material correspondence or controller change.'})
    OUT.mkdir(parents=True,exist_ok=True)
    print('Accepted P2 baseline frozen;',len(protected),'old files protected;',len(focus),'focus targets')


if __name__=='__main__':freeze()
