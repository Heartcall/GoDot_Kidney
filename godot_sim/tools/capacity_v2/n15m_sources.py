"""Read-only N1.5-M source inventory and public bibliographic retrieval.
No patient records, geometry or clinical endpoint configuration are written.
"""
from pathlib import Path
import sys, json, hashlib, subprocess, urllib.request, urllib.parse, time, xml.etree.ElementTree as ET
PROJECT=Path(__file__).resolve().parents[2];REPO=PROJECT.parent
OUT=PROJECT/'deformation/capacity_v2_n15_m_v1';DATE='2026-10-15'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf8')
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))

QUERIES={
 'PM1_HEALTHY_VOLUME':'("renal pelvis"[Title/Abstract] OR "pelvicalyceal"[Title/Abstract] OR "pyelocaliceal"[Title/Abstract]) AND (volume[Title/Abstract] OR volumetry[Title/Abstract] OR capacity[Title/Abstract]) AND (normal[Title/Abstract] OR healthy[Title/Abstract])',
 'PM2_STATE_IMAGING':'("renal pelvis"[Title/Abstract] OR "collecting system"[Title/Abstract]) AND (hydration[Title/Abstract] OR diuresis[Title/Abstract]) AND (ultrasound[Title/Abstract] OR MRI[Title/Abstract] OR volume[Title/Abstract])',
 'PM3_PRESSURE_VOLUME':'("renal pelvis"[Title/Abstract] OR "collecting system"[Title/Abstract]) AND ("pressure-volume"[Title/Abstract] OR compliance[Title/Abstract] OR distensibility[Title/Abstract])',
 'PM4_URS_PRESSURE':'ureteroscopy[Title/Abstract] AND ("intrarenal pressure"[Title/Abstract] OR "intrapelvic pressure"[Title/Abstract]) AND (prospective[Title/Abstract] OR consensus[Title/Abstract] OR review[Title/Abstract])'}

def protect(initialize=False):
    OUT.mkdir(parents=True,exist_ok=True);target=OUT/'protected_before.json'
    if initialize and not target.exists():
        names=subprocess.check_output(['git','ls-files','-z'],cwd=REPO).decode('utf8').split('\0')
        paths={REPO/n for n in names if n and (REPO/n).is_file() and OUT not in (REPO/n).parents}
        for base in [PROJECT/'deformation',PROJECT/'analysis/irrigation_baseline',REPO/'docs',PROJECT/'scripts']:
            paths.update(p for p in base.rglob('*') if p.is_file() and OUT not in p.parents and '__pycache__' not in p.parts)
        write(target,{p.relative_to(REPO).as_posix():sha(p) for p in sorted(paths)})
    before=read(target);changed=[p for p,h in before.items() if not (REPO/p).is_file() or sha(REPO/p)!=h]
    write(OUT/'protected_after.json',{'files':len(before),'changed':changed})
    if changed:raise ValueError('Protected source changed: '+str(changed))
    return len(before)

def inventory():
    protect(True);extensions={'.dcm','.dicom','.nii','.nrrd','.nhdr','.mha','.mhd','.seg','.gz'}
    candidates=[]
    for p in REPO.rglob('*'):
        if any(x in p.parts for x in ['.git','.godot','__pycache__']) or not p.is_file() or OUT in p.parents:continue
        if p.suffix.lower() in extensions:
            if p.name.endswith('.json.gz'):continue
            candidates.append({'path':p.relative_to(REPO).as_posix(),'bytes':p.stat().st_size})
    headers={name:(PROJECT/'source_assets'/('kidney_'+name+'.obj')).read_text(encoding='utf8').splitlines()[:10] for name in ['cavity','tissue']}
    record={'date':DATE,'scope':'Current repository, including ignored files; no unrelated disk search or external patient retrieval.',
       'imaging_or_segmentation_candidates':candidates,'obj_headers':headers,
       'raw_imaging_found':bool(candidates),'CT_phase_available':False,'paired_states_available':False,
       'pressure_flow_data_available':False,'source_scale_independently_DICOM_verified':False,
       'documented_imaging_lead':{'source':'README.md lines10,45','source_sha256':sha(REPO/'README.md'),
         'path_as_documented':'CT-MI NIAO WAI KE-20260720/','exists_in_current_checkout':(REPO/'CT-MI NIAO WAI KE-20260720').exists(),
         'status':'README describes ignored original DICOM with patient information; directory not available here; no external-disk search, metadata or identity inferred.'},
       'known_user_context':{'adult':True,'no_reported_stone_obstruction_or_hydronephrosis':True,'CT_excretory_phase':'UNKNOWN'},
       'unknowns':['sex','age_exact','side','body_size','hydration','diuresis','bladder_status','pressure','baseline_physiological_volume'],
       'limits':'No values inferred from mesh shape, ignored-folder name, or unrelated historical documents.'}
    write(OUT/'project_data_inventory.json',record);print('Inventory candidates',len(candidates),'protected',protect(),flush=True)

def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'CapacityV2-literature-audit/1.0 (public bibliographic research)'})
    with urllib.request.urlopen(req,timeout=45) as response:return response.read()

def search():
    inventory();directory=OUT/'literature';directory.mkdir(exist_ok=True);logs=[];ids=[]
    for name,query in QUERIES.items():
        full=query+' AND ("1800/01/01"[Date - Publication] : "2026/10/15"[Date - Publication])'
        url='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?'+urllib.parse.urlencode({'db':'pubmed','term':full,'retmode':'json','retmax':1000,'sort':'pub date'})
        try:
            raw=fetch(url);(directory/(name+'_esearch.json')).write_bytes(raw);result=json.loads(raw)['esearchresult']
            row={'id':name,'database':'PubMed via NCBI E-utilities','date':DATE,'query':full,'url':url,'count':int(result['count']),
                 'retrieved':len(result['idlist']),'truncated':int(result['count'])>len(result['idlist']),'PMIDs':result['idlist'],'query_translation':result.get('querytranslation')}
            ids+=result['idlist'];print(name,row['count'],flush=True)
        except Exception as error:row={'id':name,'database':'PubMed via NCBI E-utilities','date':DATE,'query':full,'url':url,'error':str(error)};print(name,'failed',error,flush=True)
        logs.append(row);write(directory/'pubmed_search_log.json',{'searches':logs});time.sleep(.4)
    unique=sorted(set(ids),key=int)
    write(directory/'deduplication.json',{'retrieved_query_records':len(ids),'unique_PMIDs':len(unique),'duplicate_PMID_occurrences':len(ids)-len(unique),'PMIDs':unique,
        'scope':'Exact PMID deduplication of actually retrieved PubMed search IDs, not all world literature.'})
    for start in range(0,len(unique),100):
        batch=unique[start:start+100]
        url='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?'+urllib.parse.urlencode({'db':'pubmed','id':','.join(batch),'retmode':'xml'})
        try:
            raw=fetch(url);(directory/f'pubmed_records_{start:04d}.xml').write_bytes(raw);print('metadata',start,len(batch),flush=True)
        except Exception as error:write(directory/f'pubmed_records_{start:04d}_failure.json',{'url':url,'error':str(error)})
        time.sleep(.4)
    protect()

def supplement():
    directory=OUT/'literature';logs=[]
    terms=['35764436[PMID] OR 40866865[PMID] OR 38384795[PMID] OR 38337463[PMID]',
      '("renal calyces and pelvis"[Title/Abstract] OR "renal collecting system"[Title/Abstract] OR pelvicaliceal[Title/Abstract]) AND (volume[Title/Abstract] OR volumetry[Title/Abstract]) AND (normal[Title/Abstract] OR healthy[Title/Abstract])',
      '10.1371/journal.pone.0208209[DOI] OR 10.1093/imamat/hxaa020[DOI]',
      'Mann[Author] AND hydronephrosis AND 1990[Date - Publication]',
      'Morse[Author] AND hydration AND 1999[Date - Publication]']
    existing=set(read(directory/'deduplication.json')['PMIDs']);ids=set()
    for index,term in enumerate(terms):
        url='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?'+urllib.parse.urlencode({'db':'pubmed','term':term,'retmode':'json','retmax':1000})
        raw=fetch(url);(directory/f'supplement_{index}_esearch.json').write_bytes(raw);result=json.loads(raw)['esearchresult'];ids.update(result['idlist'])
        logs.append({'query':term,'date':DATE,'database':'PubMed supplementary citation/synonym search','url':url,'count':int(result['count']),'PMIDs':result['idlist']});time.sleep(.4)
    new=sorted(ids-existing,key=int)
    url='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?'+urllib.parse.urlencode({'db':'pubmed','id':','.join(new),'retmode':'xml'})
    (directory/'pubmed_supplement.xml').write_bytes(fetch(url))
    write(directory/'supplement_log.json',{'searches':logs,'new_PMIDs':new,'new_unique':len(new),'all_unique':len(existing|ids)})
    for doi in ['10.1093/imamat/hxaa020','10.1016/j.crad.2022.05.023','10.62347/YZCG3056']:
        url='https://api.crossref.org/works/'+urllib.parse.quote(doi,safe='')
        try:
            raw=fetch(url);(directory/('crossref_'+doi.replace('/','_')+'.json')).write_bytes(raw)
            print('Crossref',doi,flush=True)
        except Exception as error:logs.append({'doi':doi,'error':str(error)})
        time.sleep(.5)
    cache=OUT/'source_cache';cache.mkdir(exist_ok=True)
    (OUT/'.gitignore').write_text('source_cache/\n__pycache__/\n.mplconfig/\n',encoding='utf8')
    url='https://people.maths.ox.ac.uk/moulton/Papers/FullSystemPaperFinal.pdf'
    try:
        raw=fetch(url);(cache/'Williams2020_author_manuscript.pdf').write_bytes(raw)
        logs.append({'url':url,'file':'source_cache/Williams2020_author_manuscript.pdf','sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'access':'Downloaded author manuscript for local reading only; redistribution permission not assumed.'})
    except Exception as error:logs.append({'url':url,'error':str(error)})
    write(directory/'supplement_access.json',logs);print('Supplement new',len(new),'total',len(existing|ids),flush=True);protect()

def fulltexts():
    cache=OUT/'source_cache';cache.mkdir(exist_ok=True);records=[]
    sources={
      'Leuschke2026.pdf':'https://e-century.us/files/ajceu/14/2/ajceu0170543.pdf',
      'Croghan2023.pdf':'https://www.bostonscientific.com/content/dam/bostonscientific/eu/urology/stonesmart/bju-international-2023-croghan-in-vivo-ureteroscopic-intrarenal-pressures-and-clinical-outcomes.pdf',
      'Delphi2025.pdf':'https://www.bostonscientific.com/content/dam/bostonscientific/eu/urology/stone-manangement/european-urology-open-science-2025-intrarenal-pressure-monitoring-during-ureteroscopy-a-delphi-panel-consensus.pdf',
      'Rousan2025.html':'https://pmc.ncbi.nlm.nih.gov/articles/PMC12381993/',
      'Oratis2018.html':'https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0208209',
      'Wolf2024.html':'https://www.frontiersin.org/journals/physiology/articles/10.3389/fphys.2024.1327407/full',
      'Mann1990_crossref.json':'https://api.crossref.org/works/10.1177%2F875617939000600204'}
    for name,url in sources.items():
        row={'file':'source_cache/'+name,'url':url,'retrieved_date':DATE,'redistributed':False}
        try:
            raw=fetch(url);(cache/name).write_bytes(raw);row.update(bytes=len(raw),sha256=sha(cache/name),status='FETCHED_NOT_AUTOMATICALLY_READ');print(name,len(raw),flush=True)
        except Exception as error:row.update(status='FETCH_FAILED',error=str(error));print(name,error,flush=True)
        records.append(row);write(OUT/'literature/fulltext_access_log.json',records);time.sleep(.5)
    protect()

def citation_followup():
    term='24477602[PMID] OR 10.1002/mrm.70288[DOI]'
    directory=OUT/'literature'
    url='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?'+urllib.parse.urlencode({'db':'pubmed','term':term,'retmode':'json','retmax':100})
    raw=fetch(url);(directory/'citation_esearch.json').write_bytes(raw);ids=json.loads(raw)['esearchresult']['idlist']
    url2='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?'+urllib.parse.urlencode({'db':'pubmed','id':','.join(ids),'retmode':'xml'})
    time.sleep(.4);(directory/'pubmed_citation_followup.xml').write_bytes(fetch(url2))
    write(directory/'citation_followup_log.json',{'date':DATE,'database':'PubMed','query':term,'url':url,'efetch_url':url2,'PMIDs':ids,
      'discovery':'Nakagawa2025 reference34 (Will2014); targeted renal pelvis MRI search found Ghoul2026 explicitly excluding pelvis',
      'scope':'New citation trail, not part of original four-query deduplication totals'})
    print('Citation follow-up',ids);protect()

if __name__=='__main__':
    if '--supplement' in sys.argv:supplement()
    elif '--fulltexts' in sys.argv:fulltexts()
    elif '--citations' in sys.argv:citation_followup()
    elif '--pubmed' in sys.argv:search()
    elif '--protect' in sys.argv:print('Unchanged protected',protect())
    else:inventory()
