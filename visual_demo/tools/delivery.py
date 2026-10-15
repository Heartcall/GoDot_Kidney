from common import *
if __name__=='__main__':
    protect();assert read(OUT/'reports/python_tests.json')['passed']
    files=[x for root in [OUT,PROJECT/'visual_demo'] for x in root.rglob('*') if x.is_file()
           and '__pycache__' not in x.parts and x.suffix not in ('.blend1','.blend2','.pyc') and x.name!='delivery_manifest.json']
    files.append(PROJECT/'visual_demo_kidney.tscn')
    manifest={x.relative_to(REPO).as_posix():{'sha256':sha(x),'bytes':x.stat().st_size} for x in sorted(files)}
    write(OUT/'delivery_manifest.json',{'stage':'V-Demo.1','status':'READY_FOR_USER_MANUAL_SCULPT',
        'final_visual_approved':False,'files':manifest,'protected':read(OUT/'reports/protected_after.json')})
    print('V-Demo.1 delivery:',len(files),'files; history unchanged',flush=True)
