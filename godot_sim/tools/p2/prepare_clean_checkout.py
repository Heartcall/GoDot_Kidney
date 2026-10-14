"""Create a minimal project from versioned P2 files only; no analysis/ inputs.

This is an isolation smoke test, not a claim that a remote Git clone was made.
"""
import shutil
from prepare_runtime import *


def prepare():
    verify_sources()
    output=DIAG/'clean_checkout'
    output.mkdir(parents=True,exist_ok=True)
    names=['irrigation_control_preview.tscn','shaders/audit_section.gdshader']
    names += [p.relative_to(PROJECT).as_posix() for p in (PROJECT/'scripts/p2').glob('*.gd')]
    names += [p.relative_to(PROJECT).as_posix() for p in ROOT.rglob('*') if p.is_file() and p.suffix in ('.json','.bin','.npy')]
    for name in names:
        target=output/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PROJECT/name,target)
    (output/'project.godot').write_text('''config_version=5
[application]
config/name="P2 isolated versioned assets smoke test"
run/main_scene="res://irrigation_control_preview.tscn"
[display]
window/size/viewport_width=1422
window/size/viewport_height=1066
''',encoding='utf8')
    write_json(DIAG/'clean_checkout_inputs.json',{'isolated_project':output.relative_to(REPO).as_posix(),
               'source_analysis_files_copied':False,'files':{name:sha(PROJECT/name) for name in names}})
    print(output)


if __name__=='__main__': prepare()
