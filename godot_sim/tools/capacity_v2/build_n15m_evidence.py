"""Rebuild reviewed N1.5-M evidence records from cached primary metadata.
Manual extraction below is an audit, not automated clinical inference.
"""
from n15m_sources import OUT, REPO, DATE, sha, read, write, protect
import xml.etree.ElementTree as ET
from collections import Counter

def metadata():
    records={}
    for path in sorted((OUT/'literature').glob('pubmed*.xml')):
        root=ET.parse(path).getroot()
        for book in root.findall('PubmedBookArticle'):
            b=book.find('BookDocument');pmid=b.findtext('PMID')
            records[pmid]={'PMID':pmid,'title':''.join(b.find('ArticleTitle').itertext()),'DOI':None,
              'authors':None,'journal':b.findtext('Book/BookTitle'),'year':b.findtext('Book/PubDate/Year'),
              'url':'https://pubmed.ncbi.nlm.nih.gov/'+pmid+'/', 'record_type':'BOOK_CHAPTER',
              'metadata_file':path.relative_to(OUT).as_posix(),'metadata_sha256':sha(path)}
        for article in root.findall('PubmedArticle'):
            pmid=article.findtext('./MedlineCitation/PMID');a=article.find('./MedlineCitation/Article')
            # PubMed reference lists also contain ArticleId elements. Never use .//ArticleId.
            doi=article.findtext('./PubmedData/ArticleIdList/ArticleId[@IdType="doi"]')
            journal=a.find('Journal');date=journal.find('JournalIssue/PubDate')
            records[pmid]={'PMID':pmid,'title':''.join(a.find('ArticleTitle').itertext()),'DOI':doi,
              'authors':[' '.join(filter(None,[x.findtext('ForeName'),x.findtext('LastName')])) or x.findtext('CollectiveName') for x in a.findall('AuthorList/Author')],
              'journal':journal.findtext('Title'),'year':date.findtext('Year') or date.findtext('MedlineDate'),
              'volume':journal.findtext('JournalIssue/Volume'),'issue':journal.findtext('JournalIssue/Issue'),
              'pages':a.findtext('Pagination/StartPage') or a.findtext('Pagination/MedlinePgn'),
              'url':'https://pubmed.ncbi.nlm.nih.gov/'+pmid+'/',
              'abstract_present':bool(a.findall('Abstract/AbstractText')),
              'metadata_file':path.relative_to(OUT).as_posix(),'metadata_sha256':sha(path)}
    return records

def build():
    protect();meta=metadata();studies=[]
    def add(key,pmid,grade,pop,n,domain,method,conditions,reason,**extra):
        r=dict(meta[pmid]) if pmid else {'PMID':None,'DOI':None,'authors':None,'journal':None,'year':None,'title':None,'url':None}
        r.update(id=key,grade=grade,grade_reason=reason,population=pop,sample_size=n,
          measured_domain=domain,method=method,boundary_conditions=conditions,
          access='ABSTRACT_ONLY',read_scope='PubMed original abstract; full methods/tables not obtained',
          age_years=None,sex=None,side=None,health_exclusions=None,ureter_cutoff=None,
          capacity_definition=None,capacity_unit=None,measurement_times=None,capacity_distribution=None,
          paired_change=False,individual_raw_data_obtained=False,complete_pressure_volume_data_obtained=False,
          absolute_initial_capacity_obtained=False,inflow_data_obtained=False,outflow_data_obtained=False,
          leakage_data_obtained=False,hysteresis_information=None,measurement_uncertainty=None,
          numeric_claims=[],locator='Original abstract',supplement_status='NOT_OBTAINED_OR_NOT_ESTABLISHED',
          patient_endpoint_usable_now=False,domain_mapping_to_D2='UNRESOLVED',
          license='Metadata/abstract for audit; full-text redistribution permission not assumed',
          unknown_policy='null means not established from the material actually read, not a measured zero or proof that the paper did not report it.')
        r.update(extra);studies.append(r);return r
    add('M01','42180432','E3','HUMAN_EX_VIVO_AND_CADAVER',{'ex_vivo_kidneys':20,'cadaver_kidneys':4,'cadavers':2},
        'Pelvicalyceal collecting system sealed just below UPJ; separate UAS outflow experiment',
        'Pressure and inflow integration; separate pressure/outflow resistance measurement',
        'Organ donors declined for transplant; storage and perfusion, sealed outlet, leakage, repeated loading differ from living physiology',
        'Supports route C model structure; not healthy in-vivo endpoints, unknown absolute offset/domain/leak prevents transfer',
        access='FULL_TEXT_READ',read_scope='Publisher PDF pp45–54, methods/results/discussion; no raw individual time series acquired',
        url='https://e-century.us/files/ajceu/14/2/ajceu0170543.pdf',age_years={'mean':62.5,'SD':12.2},
        capacity_definition='Integrated injected volume under experimental loading, not independently mapped absolute D2 lumen',capacity_unit='mL',
        measurement_times='Repeated loading; 100 ms pressure recording',hysteresis_information='Prior runs/conditioning and leakage discussed',
        measurement_uncertainty='Manually regulated study inflow within ±10%; substantial unmeasured internal leakage; no patient prediction interval',
        locator='pp46–48 Methods; pp49–52 Figures4–6 and Discussion',numeric_claims=[{'name':'sample','value':'20 ex-vivo kidneys + 4 kidneys in 2 cadavers','at':'pp46–47 Methods'}])
    add('M02','40866865','E3','HEALTHY_ADULT',{'people':56},'Renal pelvic AP diameter/dilatation grades; bladder volume is separate',
        '2D ultrasound grades and AP diameter, not 3D collecting system volumetry',
        'Baseline and post hydration; pre/post void; study-specific oral water load',
        'State dependence supported; no D2 mL endpoint; inconsistent percentages/labels require clarification',
        access='FULL_TEXT_READ',read_scope='PMC complete article, Tables1–5 and data availability',url='https://pmc.ncbi.nlm.nih.gov/articles/PMC12381993/',
        age_years={'range':[19,45]},sex={'male':30,'female':26},side='Both; right/left reported separately',
        health_exclusions='Chronic renal/cardiovascular disease, diabetes, hypertension, obstruction, pregnancy and interfering medicines among exclusions',
        capacity_definition='No 3D renal lumen capacity extracted',measurement_times='Baseline, 60 and 90 min; pre/post void',paired_change=True,
        measurement_uncertainty='No D2 volumetric error; single center; reporting discrepancies',
        numeric_claims=[{'name':'healthy_n','value':56,'at':'Methods; Table1'}],
        limitations=['Abstract p<0.005 vs methods p<0.05','Abstract/results and Tables2–4 percentages/denominators are inconsistent; no pooled rate used',
          'Table1 bladder-volume label (1470 mL) differs markedly from later time-specific bladder volumes; no silent relabelling'],
        supplement_status='Individual data available on reasonable request; not acquired',license='CC BY-NC-ND 4.0; no adapted paper figures redistributed')
    add('M03','35764436','E2','HEALTHY_DONOR_AND_HYDRONEPHROSIS_SEPARATE',{'healthy_left_donor_kidneys':67,'hydronephrotic_kidneys':111},
        'Separate renal parenchyma and renal calyces/pelvis sRCPV', '3D CT volumetry; renal function prediction',
        'Static clinical imaging; full acquisition/domain definition not obtained',
        'Potential healthy static 3D reference after full tables, cutoffs and state mapping; not paired dynamic endpoints',
        side='Healthy donor left kidney; pathological cohort separate',capacity_definition='sRCPV, not sRPV or GFR',capacity_unit='Original volume unit/cutoffs require full methods',
        locator='Original PubMed abstract Methods; publisher abstract/partial preview',
        url='https://doi.org/10.1016/j.crad.2022.05.023',
        numeric_claims=[{'name':'cohorts','value':'67 healthy donors; 111 hydronephrosis patients','at':'Abstract Methods'}],
        limitations=['Healthy sRCPV distribution/table not obtained','Mixed cohort summary must not be presented as normal adult reference'])
    add('M04','37656050','E3','ADULT_CLINICAL_URS',{'patients':120,'baseline_pressure_available':95},
        'Renal pelvic pressure; no collecting lumen volumetry','Pressure guidewire recordings; observational outcomes',
        'Emptied bladder, instrumented urinary tract, heterogeneous scopes/UAS/irrigation; 109 stone and 11 diagnostic cases',
        'B condition pressure context, not A healthy noninstrumented capacity; no paired pressure-volume observations',
        access='FULL_TEXT_READ',read_scope='Original paper PDF pp531–540; supplementary S4 not obtained',
        url='https://doi.org/10.1111/bju.16169',age_years={'mean':57.48,'SD':13.36},sex={'male':70,'female':50},
        measurement_times='Baseline before irrigation plus intraoperative pressure traces',
        measurement_uncertainty='Pressure measurement calibration described; observational confounding; no volume uncertainty',
        locator='p533 Methods, p534 Tables1–2; discussion pp536–538',
        numeric_claims=[{'name':'baseline_pressure','value':'16.45 ± 5.99 mmHg; n=95, not 120','at':'p534 Table2'}])
    add('M05','30496287','E3','MATHEMATICAL_MODEL_WITH_PRIOR_HUMAN_PORCINE_DATA',None,
        'Idealized pelvis/ureter/UAS network','Lumped pressure ODE, constant compliance hypothesis',
        'Specified inlet, outlet resistance and instrument geometry; not a new healthy adult volume cohort',
        'Conservation/resistance structure useful; published coefficients cannot identify this patient or normal endpoints',
        access='FULL_TEXT_READ',read_scope='PLOS main text, equations and figures; no patient-level reanalysis',
        url='https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0208209',locator='Methods Eqs1–7, representative parameter section, Results/Discussion',
        capacity_definition='Model volume/pressure relation, not measured D2 absolute capacity',license='CC BY; original figures not reused',
        limitations=['A representative-parameter paragraph has an apparent flow-unit inconsistency; no coefficient transferred'])
    cross=read(OUT/'literature/crossref_10.1093_imamat_hxaa020.json')['message']
    r=add('M06',None,'E3','PORCINE_EX_VIVO_AND_MATHEMATICAL_MODEL',{'kidneys':3},
        'Instrumented pelvis; change in fluid mass after drainage','Mass balances, pressure sensors, nonlinear lumped model',
        'Room temperature harvested porcine kidneys; scope/UAS; repeated loading and unloading',
        'Mechanistic nonlinear/hysteresis example; species, absolute baseline and boundary mismatch block healthy adult endpoints',
        access='FULL_TEXT_RELEVANT_SECTIONS_READ',read_scope='Author manuscript 21 pages obtained; main methods/results/discussion and Appendix A reviewed; Appendix B optimization not a clinical dataset',
        capacity_definition='Fluid mass converted by density; drained baseline does not establish this D2 initial capacity',capacity_unit='mL',
        hysteresis_information='Appendix A.2 documents loading/unloading separation and cycle conditioning',
        measurement_uncertainty='Appendix A.4 describes balance/sensor error; no transfer uncertainty for this patient',
        locator='Author manuscript pp4–6 Table1/Eqs3.1–3.5, pp8–14, pp16–18 AppendixA',
        supplement_status='Raw numerical time series not acquired',url='https://people.maths.ox.ac.uk/moulton/Papers/FullSystemPaperFinal.pdf')
    r.update(title=cross['title'][0],authors=[x.get('given','')+' '+x['family'] for x in cross['author']],DOI='10.1093/imamat/hxaa020',year='2020',journal=cross['container-title'][0],metadata_file='literature/crossref_10.1093_imamat_hxaa020.json',metadata_sha256=sha(OUT/'literature/crossref_10.1093_imamat_hxaa020.json'))
    add('M07','39107937','E3','ADULT_CLINICAL_URS',{'patients':100},'Renal pelvic baseline pressure/peristalsis',
        'Pressure guidewire pre/post stent','Bladder emptied; before irrigation but urinary tract already instrumented',
        'No volume; subgroup without hydronephrosis is not uninstrumented healthy volunteers',
        paired_change=True,measurement_times='Before/after ureteric stent',locator='Abstract Methods/Results',
        numeric_claims=[{'name':'n','value':100,'at':'Abstract Results'}],limitations=['Potential clinical cohort overlap with M04 not ruled out; no pooling'])
    add('M08','31984761','E2','ADULT_STONE_PATIENT',{'enrolled':20,'completed':13},
        'Segmented collecting system','Paired 3D CT volume/surface versus previous noncontrast CT',
        'Water plus diuretic under published clinical protocol; stone population and prior-scan timing',
        'Useful paired volumetry approach; full segmentation cutoffs/raw pairs/state coverage missing; not healthy endpoints',
        paired_change=True,capacity_unit='mL/percent change as reported',capacity_definition='3D collecting-system segmentation; no verified D2 cutoff',
        numeric_claims=[{'name':'reported_group_volume_increase','value':'63%','at':'Abstract Results; n=13 completed'}],
        limitations=['Never multiply D2 by 1.63','No individual paired distribution acquired'])
    add('M09','40824463','E2','HEALTHY_ADULT',{'volunteers':11},
        'Total kidney/cortex/medulla and separately renal pelvis','Multi-posture MRI volumetry',
        'Supine versus upright; no endpoint loading coverage verified',
        'Potential state-specific paired pelvis dataset; abstract gives no pelvis numerical result or D2 mapping',
        age_years={'mean':23.1},sex={'male':8,'female':3},paired_change=True,measurement_times='Supine/upright',
        limitations=['Do not substitute whole-kidney volume changes for pelvis','Publisher page accessible only abstract/metadata; full tables not obtained'],
        url='https://link.springer.com/article/10.1007/s12194-025-00952-9')
    add('M10','38384795','E3','HEALTHY_ADULT',{'volunteers':10},
        'Kidney/cortex/medulla/sinus/vessels; sinus includes fat, collecting system and slow-flow vessels',
        'High resolution MRE and manually segmented composite ROIs','Fasting/hydration, empty bladder before each session',
        'Sinus ROI and shear modulus are not isolated lumen volume or dV/dP; mechanism only',
        access='FULL_TEXT_RELEVANT_SECTIONS_READ',read_scope='Publisher Methods, segmentation definition, Results and data availability; supplement not acquired',
        age_years={'mean':26,'SD':5},sex={'male':5,'female':5},side='Both',paired_change=True,
        locator='Materials and methods: MR setup/segmentation; Supplementary TableS1 cited but not acquired',
        url='https://www.frontiersin.org/journals/physiology/articles/10.3389/fphys.2024.1327407/full',
        license='CC BY; no source figures adapted',limitations=['ROI voxel counts cannot be interpreted as D2 capacity'])
    add('M11','110840','E3','APPARENTLY_NORMAL_VOLUNTEER',{'volunteers':23},'Sonographic hydronephrosis',
        'Baseline versus hydrated ultrasound','Hydration and bladder distension',
        'Physiological appearance confounder, no verified 3D mL endpoint',paired_change=True)
    add('M12','10424912','E3','HEALTHY_ADULT',{'volunteers':35},'Right renal hydronephrosis grade',
        'Bedside ultrasound ordinal grades','Baseline and post-hydration, before/after void',
        'No 3D lumen volume; ordinal grades/water intake cannot calibrate D2',
        age_years={'range':[18,50]},side='Right',measurement_times='0,60,90 min',paired_change=True,
        numeric_claims=[{'name':'ever_hydronephrosis_after_hydration','value':'28/35 (80%) at least once, not 80% at each time','at':'Abstract Results'}],
        limitations=['Rousan discussion time-specific paraphrase is not substituted for original abstract'])
    add('M13','16750255','E2','ADULT_STONE_AND_HEALTHY_CONTROL_SEPARATE',{'stone_patients':42,'healthy_controls':42,'healthy_control_kidneys':84},
        'Pelvicaliceal volume estimated from IVP','Previously described formula from projection urography',
        'Static excretory urography; full acquisition and formula not obtained',
        'Healthy control static summary available, but projection-formula domain/bias and dynamic conditions unknown',
        sex={'healthy_male':22,'healthy_female':20},side='Both controls; bilateral kidneys are correlated observations',
        capacity_unit='mm3',capacity_definition='Formula-estimated pelvicaliceal volume, not independently verified 3D capacity',
        health_exclusions='Patient exclusions include hydronephrosis, anatomic/metabolic abnormalities, recurrent disease and renal surgery; control full screening unavailable',
        capacity_distribution='Healthy control kidneys mean±SD only; raw distribution and quantiles unavailable',
        numeric_claims=[{'name':'healthy_control_static_formula_volume','value':'1709.5 ± 989.1 mm3; n=84 kidneys in 42 people','at':'Original abstract Results'}],
        limitations=['Not D2 reference percentiles or within-person dynamic endpoints','No arbitrary conversion factor from this estimate to D2'])
    add('M14','16813671','E4','ADULT_STONE_WITH_CONTRALATERAL_CONTROL',{'patients':78},
        'IVP pelvicaliceal geometry','Formula-estimated IVP volume','Stone-bearing versus contralateral kidneys',
        'Contralateral normal appearance in stone patients is not a healthy population endpoint dataset',paired_change=False)
    add('M15','16406924','E4','PEDIATRIC_STONE_AND_CONTROL',{'stone_patients':25,'healthy_children':15},
        'IVP pelvicaliceal volume','Projection formula','Pediatric stone/contralateral/control groups',
        'Age and method mismatch; never merge with healthy adults')
    add('M16','3976115','E4','PEDIATRIC_OBSTRUCTIVE_HYDRONEPHROSIS',{'children':8},
        'Obstructed pelvis before pyeloplasty','Closed pressure-volume testing','UPJ obstruction and operative boundary',
        'Pathology, pediatric and closed-system conditions do not define healthy adult endpoints')
    add('M17','15947672','E4','PEDIATRIC_HYDRONEPHROSIS',{'children':18},
        'Hydronephrotic pelvis with contralateral comparison','Ultrasound dimensions during diuretic renography',
        'Unilateral hydronephrosis, diuretic and repeated measurements','Pediatric pelvis/obstruction differs from adult D2; no normal adult mL transfer',
        age_years={'range_description':'1 month–10 years'},paired_change=True,
        limitations=['Old 0.75→1.16 mL claim not verified from current original abstract; not reused'])
    add('M18','3944923','E4','PORCINE',{'pigs':5},'Ligated pig renal pelvis',
        'Infusion/drainage pressure-volume curves','UPJ ligated',
        'Animal closed system; mechanism of nonlinearity/hysteresis only',hysteresis_information='Clockwise loading/unloading curve and variation reported in abstract')
    add('M19','7372440','E4','RABBIT',None,'Rabbit renal pelvis','Radiographic contrast/layer-thickness estimate',
        'Free flow versus ureteral stasis','Species and indirect volume method; not healthy human endpoint')
    add('M20','37515665','E4','PORCINE_IN_VIVO',None,'Instrumented renal pelvic pressure',
        'Irrigation/outflow resistance experiment','Modified UAS outlet resistance',
        'Porcine pressure-flow evidence, not adult capacity; not human merely because title says in-vivo')
    add('M21','39944399','E3','EXPERT_CONSENSUS',{'initial_panel':12,'final_panel':11},
        'Intrarenal pressure monitoring, not capacity','Delphi consensus','Clinical URS scope',
        'No agreed universal pressure threshold; consensus cannot supply Vmin/Vmax',
        access='FULL_TEXT_READ',read_scope='PMC main text including Methods/Table1/Discussion; supplement not obtained',
        locator='Methods, Table1 and section3.2',url='https://pmc.ncbi.nlm.nih.gov/articles/PMC11815979/',license='CC BY')
    add('M22','39896048','E3','SCOPING_REVIEW',{'included_studies':17},'IRP management across heterogeneous studies',
        'Scoping review','Preclinical/clinical instrumentation heterogeneous',
        'Context only, no D2 volume calibration',numeric_claims=[{'name':'studies','value':17,'at':'Abstract Results'}])
    add('M23','35485243','E3','SYSTEMATIC_REVIEW',{'included_studies':52},'Upper urinary tract pressures',
        'Systematic review','Mixed in-vitro/animal/human endourological boundary conditions',
        'Pressure ranges and associated risks are not capacity endpoints',numeric_claims=[{'name':'studies','value':52,'at':'Abstract Results'}])
    add('M24','38337463','E4','GENERAL_ADULT_POPULATION_NO_KIDNEY_DISEASE',{'people':1815},
        'Whole renal organ volume','MRI renal volumetry','Static population imaging',
        'Wrong measurement compartment: organ volume is not collecting lumen',age_years={'range':[21,81]},sex={'female':930})
    r=add('M25',None,'E3','PROFESSIONAL_GUIDELINE',None,'URS pressure/irrigation guidance','EAU online guideline',
        'Endourological treatment','Scope and pressure-risk context only; no same-domain capacity distribution',
        title='EAU Guidelines on Urolithiasis — Guidelines chapter',authors=['EAU Guidelines Panel'],year='2026 online accessed',journal='EAU',
        url='https://uroweb.org/guidelines/urolithiasis/chapter/guidelines',access='RELEVANT_GUIDELINE_SECTIONS_READ',
        read_scope='Sections on URS/IRP/access sheaths; not a claim to have read all chapters',locator='3.4.6 ureteroscopy/IRP and access sheaths')
    r=add('M26',None,'E3','CITATION_ONLY_POPULATION_NOT_REVERIFIED',None,'Hydronephrosis/bladder distension',
        'Citation only; original abstract/full text not obtained','Not independently verified',
        'Only bibliographic lead; secondary cohort numbers not extracted as primary verified facts',
        title='Hydronephrosis secondary to bladder distention: myth or reality?',authors=['M. J. Mann'],year='1990',journal='Journal of Diagnostic Medical Sonography',DOI='10.1177/875617939000600204',
        url='https://doi.org/10.1177/875617939000600204',access='CITATION_METADATA_ONLY',read_scope='Rousan reference2 plus Crossref metadata; no original outcomes verified',locator='Crossref metadata / Rousan reference2')
    r.update(read_scope='Rousan reference2 only; Crossref DOI request returned 404 and publisher access failed; original outcomes not verified',
      locator='Rousan original article reference2',DOI_verification='CITED_DOI_NOT_RESOLVED')
    cache=OUT/'source_cache/Mann1990_crossref.json'
    if cache.exists():
        c=read(cache)['message'];r.update(title=c['title'][0],authors=[x.get('given','')+' '+x.get('family','') for x in c.get('author',[])],metadata_file='source_cache/Mann1990_crossref.json',metadata_sha256=sha(cache))
        # Persist bibliographic metadata, not copyrighted full text, for offline reproducibility.
        write(OUT/'literature/Mann1990_crossref_metadata.json',{'DOI':c.get('DOI'),'title':c.get('title'),'author':c.get('author'),'container-title':c.get('container-title'),'published':c.get('published')})
        r['metadata_file']='literature/Mann1990_crossref_metadata.json';r['metadata_sha256']=sha(OUT/r['metadata_file'])
    add('M27','24477602','E2','HEALTHY_VOLUNTEER_AGE_NOT_VERIFIED',{'volunteers':12},
        'Separately labelled renal pelvis versus cortex and medulla','Noncontrast T1/T2 MRI; automated versus manual segmentation',
        'Static method validation, breath-hold/coregistration; full state/cutoff methods unavailable',
        'Relevant pelvis segmentation validation; age, domain and dynamic coverage need full methods; not patient endpoint evidence',
        measurement_uncertainty='Abstract reports compartment-specific automated-versus-manual volume error; not a universal clinical uncertainty',
        numeric_claims=[{'name':'pelvis_automated_manual_volume_error','value':'17.57 ± 14.47%','at':'Original abstract Results'}],
        limitations=['4.76% repeatability concerns whole kidney in one volunteer, not verified pelvis repeatability','No raw masks/pelvis volume distribution obtained'],
        url='https://link.springer.com/article/10.1007/s10334-014-0429-4')
    add('M28','41639936','E4','ONCOLOGY_PATIENT_AND_HEALTHY_SUBJECT',{'patients':24,'healthy_subjects':10},
        'Parenchyma/cortex/medulla; indexed Methods explicitly exclude pelvis','Deep-learning multiparametric renal MRI segmentation',
        'Repeated scans for algorithm validation, mixed oncology and healthy population',
        'Current 2026 segmentation study is not lumen capacity/physiological endpoint data',
        read_scope='PubMed original abstract plus indexed primary Methods fragment, not full article read',
        locator='Original abstract; primary section2 Methods exclusion of renal pelvis',
        url='https://pmc.ncbi.nlm.nih.gov/articles/PMC13049282/')
    write(OUT/'evidence_matrix.json',{'schema':'N15M_EVIDENCE_V1','date':DATE,'grading_target':'Applicability to current adult D2 physiological capacity endpoints, not overall study quality',
        'grades':{'E1':'Potential direct same-domain calibration','E2':'Conditional method/data candidate requiring domain/state/bias evidence','E3':'Mechanism/context only for present endpoints','E4':'Inapplicable population/compartment for adult normal endpoints'},
        'studies':studies})
    selected={s['PMID'] for s in studies if s['PMID']}
    screening=[]
    for pmid,r in sorted(meta.items(),key=lambda kv:int(kv[0])):
        screening.append({'PMID':pmid,'title':r['title'],'DOI':r['DOI'],
          'decision':'FOCUSED_EXTRACTION_OR_EXCLUSION_COMPARATOR' if pmid in selected else ('EXCLUDED_BOOK_CHAPTER' if r.get('record_type')=='BOOK_CHAPTER' else 'NOT_SELECTED_IN_FOCUSED_TITLE_TRIAGE'),
          'reason':'Prioritized for domain/state/volume/mechanism review; applicability in matrix' if pmid in selected else 'Title not prioritized for adult same-domain paired capacity or key pressure-volume context; not a full-text eligibility decision',
          'screening_level':'Title triage; extracted sources have separately recorded reading level','reviewer':'Single Codex-assisted review; no independent dual screening'})
    write(OUT/'literature/screening_log.json',screening)
    write(OUT/'literature/review_counts.json',{'pubmed_unique_retrieved':len(meta),'pubmed_focused_extraction':len(selected),'non_pubmed_added':len(studies)-len(selected),
      'matrix_rows':len(studies),'grade_counts':dict(Counter(s['grade'] for s in studies)),'access_counts':dict(Counter(s['access'] for s in studies)),
      'not_full_systematic_review':'Focused reproducible evidence review; no exhaustive eligibility assessment or meta-analysis claimed'})
    rows=['# N1.5-M 医学证据矩阵（可读索引）','', '日期：2026-10-15。逐字段版本见同目录 evidence_matrix.json；null 表示未从已读材料核实。E等级针对本例端点适用性，不是论文质量分数。','',
      '| ID / 原始来源 | 人群与样本 | 阅读情况 | 适用性 / 原因 |','| --- | --- | --- | --- |']
    for s in studies:rows.append(f"| {s['id']} [{s['title']}]({s['url']}) ({s['year']}) | {s['population']} / {s['sample_size']} | {s['access']} | **{s['grade']}** {s['grade_reason']} |")
    (OUT/'evidence_matrix.md').write_text('\n'.join(rows)+'\n',encoding='utf8')
    write(OUT/'stage_authorization.json',{'date':DATE,'stage':'N1.5-M','authority':'Direct user instruction in this chat',
      'N0_closed':True,'N1_engineering_accepted':True,'physiological_calibration_priority':True,'D2_reopen':False,
      'nested_branch_net_areas_remain_unresolved':True,'N2_authorized':False,'actual_endpoints_authorized':False})
    approval=REPO/'godot_sim/deformation/capacity_v2_n1_v1/D2_approval_2026_10_14_v1.json'
    a=read(approval)
    write(OUT/'real_parameter_status.json',{'schema':'N15M_REAL_UNCALIBRATED_V1','status':'NOT_IDENTIFIABLE_WITH_AVAILABLE_EVIDENCE',
      'domain_id':a['domain_id'],'D2_approval_path':approval.relative_to(REPO).as_posix(),'D2_approval_sha256':sha(approval),
      'V_reference_D2_mL':a['V_reference_D2_mL'],'V_min_mL':None,'V_max_mL':None,'pressure':None,'compliance':None,'real_flow_mL_s':None,
      'endpoint_condition_A':None,'endpoint_condition_B':None,'patient_interval':None,'model_version':'n15m-v1',
      'source':'Approved geometric reference only; no physiological fitting to project mesh',
      'warning':'No synthetic result is eligible for import into real configuration; no runtime import implemented.'})
    print('Evidence',len(studies),'PubMed',len(meta),'grades',Counter(s['grade'] for s in studies));protect()

if __name__=='__main__':build()
