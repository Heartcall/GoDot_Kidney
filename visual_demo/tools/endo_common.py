"""Isolated endoscope-video work. Historical code/resources are read-only."""
from common import REPO,PROJECT,OUT,ORIGIN,sha,read,write,np,inputs
ROOT=OUT/'endoscope_v1'
BLEND=OUT/'blender/kidney_manual_v3.blend'
PATH=PROJECT/'data/organ_2_kidney/lab_6/cavity_path_stone1.json'
GLB=PROJECT/'visual_demo/assets/kidney_manual_v3.glb'
def protect(initial=False):
    p=ROOT/'reports/protected_before.json'
    if initial and not p.exists():
        names=set(read(OUT/'reports/protected_before.json'))
        names.update(read(OUT/'delivery_manifest.json')['files'])
        names.update(str(x.relative_to(REPO)).replace('\\','/') for x in [BLEND,PATH,PROJECT/'main.tscn',PROJECT/'scripts/endoscope_controller.gd'])
        write(p,{n:sha(REPO/n) for n in sorted(names)})
    r=read(p);bad=[n for n,h in r.items() if not (REPO/n).exists() or sha(REPO/n)!=h]
    write(ROOT/'reports/protected_after.json',{'checked':len(r),'changed':bad})
    if bad:raise ValueError('Historical/manual input changed '+str(bad))

if __name__=='__main__':
    if not BLEND.is_file():raise FileNotFoundError('User manual v3 missing; stop')
    protect(True);print('Authoritative manual v3 exists',sha(BLEND),flush=True)
