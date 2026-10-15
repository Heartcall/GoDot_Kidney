"""Independent V-Demo I/O. No historical builder is called."""
from pathlib import Path
import json, hashlib, numpy as np
REPO=Path(__file__).resolve().parents[2]
OUT=REPO/'visual_demo'; PROJECT=REPO/'godot_sim'
ORIGIN=np.array([16.,16.,-81.])
GROUPS=['FixedPorts','Terminals','MainCavity','J_01','Branches','OtherJunctions','InterfaceTransition']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2,sort_keys=True),encoding='utf-8')
def inputs():
    base=PROJECT/'deformation/p2';manifest=read(base/'accepted_inputs.json');arrays={}
    for name,row in manifest['arrays'].items():
        p=base/row['runtime']
        if sha(p)!=row['sha256']:raise ValueError('Accepted input hash mismatch: '+name)
        arrays[name]=np.load(p)
    return arrays,manifest
def check_basis(actual,reference):
    expected=((reference-ORIGIN)*.001).astype(np.float32).astype(float)
    if not np.array_equal(actual,expected):raise ValueError('Basis modified; never silently restore it')
def fixed_changes(delta,fixed):
    return [{'source_vertex':int(i),'displacement_mm':float(np.linalg.norm(delta[i]))}
            for i in np.flatnonzero(fixed & (np.linalg.norm(delta,axis=1)>0))]
def protect(initial=False):
    p=OUT/'reports/protected_before.json'
    if initial and not p.exists():
        paths=[]
        for root in [REPO/'docs',PROJECT]:
            paths += [x for x in root.rglob('*') if x.is_file() and not any(z in x.parts for z in ('.godot','__pycache__','.mplconfig'))
                      and PROJECT/'visual_demo' not in x.parents and x.name!='visual_demo_kidney.tscn'
                      and x.suffix not in ('.import','.translation','.pyc')]
        write(p,{x.relative_to(REPO).as_posix():sha(x) for x in paths})
    before=read(p);bad=[n for n,h in before.items() if not (REPO/n).is_file() or sha(REPO/n)!=h]
    write(OUT/'reports/protected_after.json',{'checked':len(before),'changed':bad,'excludes':'Godot generated import/translation caches and Python caches'})
    if bad:raise ValueError('Protected files changed '+str(bad))

