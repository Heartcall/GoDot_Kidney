"""Hash/freeze N2.0 delivery only. Never run old phase finalizers."""
from n20_model import *
import shutil

def run():
    protected()
    summary=read(OUT/'summary.json');tests=read(OUT/'python_tests.json')
    if not tests['passed']:raise ValueError('Tests failed')
    for side in ['contract','expand']:
        if not summary['results'][side]['all_solver_checkpoint_tissue_transverse_checked']:raise ValueError('Missing checkpoint scan')
        root=OUT/side;tr=read(root/'trajectory.json');n=len(tr['states']);p=root/'ccd_reference_chord.json.gz';r=read(p)
        r['sources']={'cavity_offset_sha256':sha(root/f'cavity_{n:03}.npy'),'tissue_offset_sha256':sha(root/f'tissue_{n:03}.npy'),
            'reference_and_faces_sha256':read(OUT/'authorization_and_targets.json')['protected_source_hashes']}
        gzip_write(p,r)
    snapshot=OUT/'implementation_snapshot';snapshot.mkdir(exist_ok=True)
    sources=list((PROJECT/'tools/capacity_v2').glob('n20_*.py'))+list((PROJECT/'tools/capacity_v2').glob('test_n20.py'))+list((REPO/'docs').glob('kidney_irrigation_capacity_v2_n20*.md'))
    for source in sources:shutil.copyfile(source,snapshot/source.name)
    write(OUT/'repeat_build.json',{'first_cavity_predictor':'BYTE_IDENTICAL_NUMPY_VALUES','first_tissue_predictor':'BYTE_IDENTICAL_NUMPY_VALUES',
        'S1_finite_contact_QP':'BYTE_IDENTICAL_NUMPY_VALUES','complete_adaptive_search_repeated':False,
        'recorded_checkpoint_replay':read(OUT/'trajectory_replay.json'),
        'authority':'Executed test_repeat_first_predictor and recorded checkpoint replay; not a claim of two complete adaptive searches'})
    write(OUT/'validation_incidents.json',{'resolved':[{'issue':'Missing reason on early quality rejection caused KeyError','fix':'Explicit rejection reason; restart from stored checkpoint'},
        {'issue':'QP strict-point conflict omitted from redistribution diagnostics','fix':'Map conflict cavity faces back to response supports; keep original attempt and separate redistributed retry'},
        {'issue':'Float64 far-origin cancellation tripped old independent integration threshold','fix':'New Decimal40 independent integral; no geometry threshold relaxed'},
        {'issue':'Bulky duplicated full finite rows in summary','fix':'Full row evidence retained losslessly in gzip; summaries reference hashes'}],
        'unresolved':['Contract cavity float32 face7680 area ratio <0.8','Permanent contacts lack continuous CCD certificate',
            'Conservative contact plane conflicts with true shared point','Targets -30/+30 not reached'],
        'all_protected_files_unchanged':True})
    files={}
    for p in sorted(OUT.rglob('*')):
        if p.is_file() and '.mplconfig' not in p.parts and p.name!='delivery_manifest.json':
            files[p.relative_to(REPO).as_posix()]={'sha256':sha(p),'bytes':p.stat().st_size}
    for source in sources:files[source.relative_to(REPO).as_posix()]={'sha256':sha(source),'bytes':source.stat().st_size}
    write(OUT/'delivery_manifest.json',{'stage':'N2.0','files':files,'total_bytes':sum(x['bytes'] for x in files.values()),
        'protected_checked_files':protected(),'runtime_eligible':False,'formal_N2_resources_created':False,
        'target_reached':False,'continuous_safety_certified':False})
    print('Frozen N2.0 files',len(files),'protected',protected(),flush=True)

if __name__=='__main__':run()
