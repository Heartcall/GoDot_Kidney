"""New-only N2.1-R source/evidence snapshot and hash manifest."""
from n21_common import *
import shutil

def finalize():
    protected=protect();tests=read(ROOT/'python_tests.json')
    if not tests['passed']:raise ValueError('Python tests failed')
    files=list((PROJECT/'tools/capacity_v2').glob('n21_*.py'))+[PROJECT/'tools/capacity_v2/test_n21.py']
    files+=list((REPO/'docs').glob('kidney_irrigation_capacity_v2_n21r_*.md'))
    snapshot=ROOT/'source_snapshot'
    for p in files:
        q=snapshot/p.relative_to(REPO);q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q)
    manifest={}
    for p in sorted(set(files+list(ROOT.rglob('*')))):
        if not p.is_file() or any(x in p.parts for x in ('.mplconfig','__pycache__')):continue
        if p.name=='delivery_manifest.json':continue
        manifest[p.relative_to(REPO).as_posix()]={'sha256':sha(p),'bytes':p.stat().st_size}
    write(ROOT/'delivery_manifest.json',{'stage':'N2.1-R','research_only':True,
        'protected_historical_files':protected,'historical_changed_files':[],
        'file_count':len(manifest),'files':manifest,
        'formal_N2_resources':False,'complete_continuous_safety':False})
    verify()

def verify():
    r=read(ROOT/'delivery_manifest.json')
    bad=[n for n,row in r['files'].items() if not (REPO/n).is_file() or sha(REPO/n)!=row['sha256']]
    if bad:raise ValueError('N2.1-R manifest mismatch '+str(bad))
    # protect() writes the same deterministic protected_after.json bytes.
    protect();print('FINAL MANIFEST',r['file_count'],'new files verified;',r['protected_historical_files'],'historical unchanged',flush=True)

if __name__=='__main__':
    if '--verify' in sys.argv:verify()
    else:finalize()
