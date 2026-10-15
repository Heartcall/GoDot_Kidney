"""N2.1-R isolated research. Old phase imports below are pure readers/math only."""
from n20_model import (PROJECT,REPO,inputs,read,write,sha,np,sparse,splu,spsolve,
    map_d2,volume,volume_coefficients,volume_gradient_source,quality,triangle_data,
    mesh_graph,normalize,quick_quality,TissueModel,CavityModel,region_contributions,GROUPS,
    scan_cross,gzip_write)
from pathlib import Path
import os,sys,time,json,hashlib
ROOT=PROJECT/'deformation/capacity_v2_n21r_v1'
OLD=PROJECT/'deformation/capacity_v2_n20_v1'
N16=PROJECT/'deformation/capacity_v2_n16_v1'
TARGETS={'reference_mL':16.805962087430178,'contract_mL':11.764173461201125,'expand_mL':21.847750713659231}

def protect(initialize=False):
    ROOT.mkdir(parents=True,exist_ok=True);p=ROOT/'protected_before.json'
    if initialize and not p.exists():
        files=set()
        for base in [REPO/'docs',PROJECT/'deformation',PROJECT/'analysis/irrigation_baseline',PROJECT/'source_assets',PROJECT/'tools',PROJECT/'scripts',PROJECT/'shaders']:
            files.update(x for x in base.rglob('*') if x.is_file() and ROOT not in x.parents
                and not x.name.startswith(('n21_','test_n21','kidney_irrigation_capacity_v2_n21'))
                and not any(z in x.parts for z in ('__pycache__','.mplconfig','source_cache','matplotlib_cache')))
        files.update(PROJECT.glob('*.tscn'));files.update([PROJECT/'project.godot',REPO/'README.md',REPO/'.gitignore'])
        write(p,{x.relative_to(REPO).as_posix():sha(x) for x in sorted(files)})
    before=read(p);changed=[n for n,h in before.items() if not (REPO/n).is_file() or sha(REPO/n)!=h]
    write(ROOT/'protected_after.json',{'files':len(before),'changed':changed})
    if changed:raise ValueError('Historical file changed: '+str(changed))
    return len(before)

def fixture(name):
    if name=='contract':folder=OLD/name;number=13;c=folder/f'cavity_{number:03}.npy';t=folder/f'tissue_{number:03}.npy'
    elif name=='expand':folder=OLD/name;number=5;c=folder/f'cavity_{number:03}.npy';t=folder/f'tissue_{number:03}.npy'
    else:
        folder=N16/'prototypes/thin_face_corrected'/name;c=folder/'research_cavity_offset.npy';t=folder/'research_tissue_offset.npy'
    return np.load(c),np.load(t),{'cavity':{'path':c.relative_to(REPO).as_posix(),'sha256':sha(c)},'tissue':{'path':t.relative_to(REPO).as_posix(),'sha256':sha(t)}}

def begin():
    protect(True);a,d2,tv,tf,resolved,approval=inputs()
    manifest=read(OLD/'delivery_manifest.json')
    bad=[n for n,r in manifest['files'].items() if sha(REPO/n)!=r['sha256']]
    if bad:raise ValueError('N2.0 frozen evidence mismatch: '+str(bad))
    write(ROOT/'authorization.json',{'stage':'N2.1-R','status':'AUTHORIZED_RESEARCH_ONLY','date':'2026-10-15',
        'authority':'User explicitly authorized finite contact, robustness, CCD and boundary sensitivity remediation',
        'targets':TARGETS,'target_kind':'MORPHOLOGY_GUIDED_UNCALIBRATED_CAPACITY_ESTIMATE','formal_N2_resources_authorized':False,
        'D2':approval['domain_id'],'accepted_source_hashes':approval['accepted_source_sha256'],'D2_hashes':approval['frozen_geometry_sha256'],
        'physiological_parameters_remain_null':True})
    return a,d2,tv,tf,resolved,approval

if __name__=='__main__':begin();print('N2.1-R protected',protect(),flush=True)
