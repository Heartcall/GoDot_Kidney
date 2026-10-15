"""Create N1.5-M source/deliverable manifest and verify offline reproducibility."""
from pathlib import Path
import sys, subprocess, platform, json, os, shutil
from n15m_sources import OUT, REPO, sha, read, write, protect
os.environ['MPLCONFIGDIR']=str(OUT/'.mplconfig')
import numpy, scipy, matplotlib
from build_n15m_evidence import metadata

def digest_outputs():
    names=['evidence_matrix.json','evidence_matrix.md','real_parameter_status.json','stage_authorization.json',
      'literature/screening_log.json','literature/review_counts.json','synthetic/fixture.json',
      'synthetic/result.json','synthetic/method_validation.png']
    return {n:sha(OUT/n) for n in names}

def finalize():
    protect()
    if '--repeat' in sys.argv:
        before=digest_outputs()
        for name in ['build_n15m_evidence.py','n15m_calibration.py']:
            subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).with_name(name))],check=True,cwd=REPO)
        after=digest_outputs();changed=[n for n,h in before.items() if after[n]!=h]
        write(OUT/'repeat_build.json',{'outputs':len(before),'before':before,'after':after,'changed':changed,'byte_identical':not changed})
        if changed:raise RuntimeError('Rebuild changed artifacts: '+str(changed))
    m=metadata();s=read(OUT/'evidence_matrix.json')['studies']
    write(OUT/'literature/source_catalog.json',{'date':'2026-10-15','records':[
      {k:r.get(k) for k in ['id','title','DOI','PMID','url','access','read_scope','locator','supplement_status','license','metadata_file','metadata_sha256']}
      for r in s],
      'literature_file_hashes':[{'file':p.relative_to(OUT).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size,
        'kind':'RAW_PUBLIC_RESPONSE' if p.suffix=='.xml' or p.name.startswith('crossref_') or '_esearch.' in p.name else 'REVIEW_LOG_OR_DERIVED'}
        for p in sorted((OUT/'literature').glob('*')) if p.is_file() and p.name not in ['source_catalog.json']],
      'full_text_sha_logs':['literature/fulltext_access_log.json','literature/supplement_access.json'],
      'note':'Cached response hash establishes retrieved version, not clinical validity. Source cache ignored, access does not imply reading or data license.'})
    tests=read(OUT/'tests.json')
    if not tests['passed']:raise RuntimeError('Tests not passed')
    real=read(OUT/'real_parameter_status.json')
    for key in ['V_min_mL','V_max_mL','pressure','compliance','real_flow_mL_s','patient_interval']:
        if real[key] is not None:raise RuntimeError('Actual value assigned')
    counts={'unique_pubmed_records':len(m),'journal_records':sum(r.get('record_type')!='BOOK_CHAPTER' for r in m.values()),
      'book_chapters':sum(r.get('record_type')=='BOOK_CHAPTER' for r in m.values())}
    write(OUT/'environment.json',{'python':sys.version,'python_executable':sys.executable,'platform':platform.platform(),
      'numpy':numpy.__version__,'scipy':scipy.__version__,'matplotlib':matplotlib.__version__,
      'seed':1515,'source_cache_required_for_offline_rebuild':False,'counts':counts})
    # Freeze the new code/tests/design within the independent research version too.
    # These are audit snapshots; canonical runnable scripts stay under tools/capacity_v2.
    originals=list(Path(__file__).parent.glob('*n15m*.py'))+list((REPO/'docs').glob('kidney_irrigation_capacity_v2_n15_m_*.md'))
    snapshots={}
    for source in originals:
        relative=source.relative_to(REPO);target=OUT/'implementation_snapshot'/relative
        if OUT.resolve() not in target.resolve().parents:raise RuntimeError('Snapshot outside research directory')
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        snapshots[relative.as_posix()]={'snapshot':target.relative_to(OUT).as_posix(),'sha256':sha(source)}
    write(OUT/'implementation_snapshot/index.json',{'role':'Byte-identical audit snapshots of NEW N1.5-M code/tests/design only; execute canonical repository commands, not relocated copies.','files':snapshots})
    files=[p for p in OUT.rglob('*') if p.is_file() and not any(x in p.parts for x in ['source_cache','__pycache__','.mplconfig']) and p.name!='deliverable_manifest.json']
    files+=list(Path(__file__).parent.glob('*n15m*.py'))
    files+=list((REPO/'docs').glob('kidney_irrigation_capacity_v2_n15_m_*.md'))
    write(OUT/'deliverable_manifest.json',{'schema':'N15M_DELIVERABLE_MANIFEST_V1','date':'2026-10-15',
      'protected_files_unchanged':protect(),'test_count':tests['tests'],'real_parameters_null':True,
      'geometry_generated':False,'runtime_or_D2_changed':False,
      'files':{p.relative_to(REPO).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(set(files))}})
    print('Manifest complete;',tests['tests'],'tests;',protect(),'protected unchanged;',counts)

if __name__=='__main__':finalize()
