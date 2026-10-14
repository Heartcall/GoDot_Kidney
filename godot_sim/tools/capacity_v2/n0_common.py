"""N0 is a measurement/contact review, never a replacement deformation model."""
import sys,subprocess,struct,hashlib,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'p2'))
from prepare_runtime import PROJECT,REPO,verify_sources,sha,read_json,write_json,ORIGIN,AUTHORITY
sys.path.insert(0,str(PROJECT/'tools'))
from audit_reference_capacity import signed_volume,triangulate_ring
from localize_p15_conflicts import intersection_segment,coplanar_overlap_area,closest_features
from build_cavity_morph_states import vertex_normals
import numpy as np
import trimesh
import os
OUT=PROJECT/'deformation/capacity_v2_n0_research'

def atomic_bytes(path,data):
    path=Path(path);temporary=path.with_name(path.name+'.building-'+str(os.getpid()))
    temporary.write_bytes(data)
    os.replace(temporary,path)

def write_json(path,value):
    atomic_bytes(path,(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True)+'\n').encode('utf8'))

def save_npy(path,array):
    """Atomic writes confined to new N0 products; never partially replace a candidate."""
    path=Path(path);temporary=path.with_name(path.name+'.building-'+str(os.getpid()))
    with temporary.open('wb') as file:np.save(file,array,allow_pickle=False)
    os.replace(temporary,path)

def freeze():
    verify_sources()
    OUT.mkdir(parents=True,exist_ok=True)
    path=OUT/'protected_before.json'
    if not path.exists():
        names=subprocess.check_output(['git','ls-files','-z'],cwd=REPO).decode('utf8').split('\0')
        paths={REPO/name for name in names if name and (REPO/name).is_file()}
        for base in [PROJECT/'deformation',PROJECT/'analysis/irrigation_baseline']:
            paths.update(p for p in base.rglob('*') if p.is_file() and OUT not in p.parents and p.suffix in ('.npy','.bin','.json','.csv','.md','.png','.log'))
        write_json(path,{p.relative_to(REPO).as_posix():sha(p) for p in sorted(paths)})
    protected()

def protected():
    before=read_json(OUT/'protected_before.json')
    changed=[p for p,h in before.items() if not (REPO/p).exists() or sha(REPO/p)!=h]
    write_json(OUT/'protected_after.json',{'files':len(before),'changed':changed})
    if changed:raise ValueError('Protected input changed: '+str(changed))
    return len(before)

def binary_mesh(path,v,f):
    """Reference-only measuring geometry; virtual faces remain a separate surface."""
    raw=b'N0MS0001'+struct.pack('<II',len(v),len(f))
    raw+=np.asarray(v-ORIGIN,dtype='<f4').tobytes()
    raw+=np.asarray(vertex_normals(v,f),dtype='<f4').tobytes()
    raw+=np.asarray(f[:,::-1],dtype='<i4').tobytes()
    atomic_bytes(path,raw)

def inventory():
    freeze()
    extensions={'.obj','.stl','.ply','.vtk','.vtp','.nrrd','.nhdr','.nii','.dcm','.mha','.mhd','.blend','.fbx','.gz'}
    files=[]
    for p in REPO.rglob('*'):
        if any(x in p.parts for x in ('.git','.godot','__pycache__')) or not p.is_file():continue
        if p.suffix.lower() in extensions:
            files.append({'path':p.relative_to(REPO).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
    history=subprocess.check_output(['git','log','--all','--format=','--name-only'],cwd=REPO).decode('utf8',errors='replace')
    historical=sorted({p for p in history.splitlines() if Path(p).suffix.lower() in extensions})
    log=subprocess.check_output(['git','log','--all','--oneline','--','godot_sim/source_assets'],cwd=REPO).decode('utf8')
    headers={name:(PROJECT/'source_assets'/f'kidney_{name}.obj').read_text(encoding='utf8').splitlines()[:8] for name in ['cavity','tissue']}
    result={'date':'2026-10-14','authorization':'User approved Capacity V2 plan and authorized N0 only.',
       'scope':'Current repository including ignored files and locally available Git refs; no external disk or remote history search.',
       'geometry_or_segmentation_files':files,'local_git_geometry_paths':historical,'source_asset_history':log.splitlines(),'obj_headers':headers,
       'pre_artificial_natural_geometry_found':False,'original_segmentation_found':False,'reversible_preprocessing_recipe_found':False,
       'interpretation':'Only current cavity/tissue OBJs found. ITK-SNAP/Slicer RAS header is provenance metadata, NOT original segmentation or a reversible artificial-port construction recipe. Natural anatomy has not been restored.',
       'V_reference_effective_mL':None,'D2_anatomical_approval':'PENDING_USER_REVIEW'}
    write_json(OUT/'source_inventory.json',result)
    print('Inventory:',len(files),'geometry files;',protected(),'protected files unchanged')
    return result

if __name__=='__main__':inventory()
