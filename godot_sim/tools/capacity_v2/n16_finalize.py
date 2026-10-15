"""Lossless contact archives, repeat build check and N1.6 provenance manifest."""
from n16_feasibility import *
import shutil,platform

def signatures():
    paths=list((OUT/'attempts/thin_face_corrected').glob('*.npy'))
    for p in (OUT/'prototypes/thin_face_corrected').iterdir():
        if p.name.startswith(('S1_','S2_','S3_')):paths+=list(p.glob('*.npy'))+[p/'preassessment.json']
    return {p.relative_to(OUT).as_posix():sha(p) for p in paths}

def run():
    protect()
    if '--repeat' in sys.argv:
        before=signatures();subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).with_name('n16_feasibility.py')),'--corrected'],check=True,cwd=REPO)
        after=signatures();changed=[p for p,h in before.items() if h!=after[p]]
        write(OUT/'repeat_build.json',{'outputs':len(before),'before_sha256':before,'after_sha256':after,'changed':changed,'byte_identical':not changed})
        if changed:raise ValueError('Repeated numerical build changed artifacts')
    archives=[]
    for p in sorted((OUT/'prototypes').glob('*/**/contacts/u*.json')):
        raw=p.read_bytes();target=p.with_suffix('.json.gz');packed=gzip.compress(raw,compresslevel=9,mtime=0);target.write_bytes(packed)
        if gzip.decompress(packed)!=raw:raise ValueError('Lossy diagnostic archive')
        archives.append({'file':target.relative_to(OUT).as_posix(),'sha256':sha(target),'raw_json_sha256':hashlib.sha256(raw).hexdigest(),'raw_bytes':len(raw),'compressed_bytes':len(packed)})
    write(OUT/'contact_archive_manifest.json',{'archives':archives,'lossless':True,'raw_contacts_are_optional_ignored_cache':True,'reader_handles_json_or_json_gz':True})
    tests=read(OUT/'python_tests.json')
    if not tests['passed']:raise ValueError('Tests failed')
    snap={}
    sources=list(Path(__file__).parent.glob('n16_*.py'))+[Path(__file__).with_name('test_n16.py')]+list((REPO/'docs').glob('kidney_irrigation_capacity_v2_n16_*.md'))
    for p in sources:
        target=OUT/'implementation_snapshot'/p.relative_to(REPO);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
        snap[p.relative_to(REPO).as_posix()]={'snapshot':target.relative_to(OUT).as_posix(),'sha256':sha(p)}
    write(OUT/'implementation_snapshot/index.json',{'role':'Versioned audit snapshots; run canonical scripts from repository root','files':snap})
    write(OUT/'environment.json',{'python':sys.version,'platform':platform.platform(),'numpy':np.__version__,'units':'mm, mm2, mL; 1000 mm3=1mL',
      'finite_intersection_tolerance_mm':1e-10,'zero_broadphase_tolerances':True,'no_runtime_performance_optimization':True})
    paths=[p for p in OUT.rglob('*') if p.is_file() and '.mplconfig' not in p.parts and '__pycache__' not in p.parts
      and p.name!='delivery_manifest.json' and not(p.parent.name=='contacts' and p.suffix=='.json')]+sources
    write(OUT/'delivery_manifest.json',{'label':LABEL,'stage':'N1.6','protected_unchanged':protect(),'tests':tests['tests'],'N2_implemented':False,
      'files':{p.relative_to(REPO).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(set(paths))}})
    print('Finalized',len(paths),'files;',tests['tests'],'tests;',protect(),'protected files; contact archive MB',round(sum(x['compressed_bytes'] for x in archives)/1e6,2),flush=True)

if __name__=='__main__':run()
