from n21_common import *
from n21_features import FiniteTissue,ContactState

def run(names):
    protect();a,d2,tv,tf,resolved,approval=inputs();tm=FiniteTissue(a,tv,tf,resolved);reports=[]
    output=ROOT/('contact_final' if '--final' in names else 'contact');names=[x for x in names if x!='--final']
    for name in names:
        c,t,sources=fixture(name);pairs={(34852,181160)} if name=='expand' else set()
        if name.startswith('S'):
            old=read(N16/f'prototypes/thin_face_corrected/{name}/contacts/u100.json')['results']['cavity_tissue']
            pairs={(r['cavity_face'],r['tissue_face']) for r in old['rows'] if r['class']=='FINITE_TRANSVERSE_CROSSING'}
        root=output/name;root.mkdir(parents=True,exist_ok=True);state=ContactState()
        current,report=tm.solve_finite(c,pairs,state)
        np.save(root/'cavity_offset.npy',c);np.save(root/'tissue_offset.npy',current)
        report.update({'fixture':name,'sources':sources,'actual_D2_algebraic_integral_mL':volume(d2['reference_vertices']+map_d2(c,d2),d2['faces']),
            'cavity_quality':quality(a['vertices'],a['faces'],c),'tissue_quality':quality(tv,tf,current),
            'formal_N2':False,'source_triangles_unchanged':True})
        gzip_write(root/'contact_report.json.gz',report)
        settings={'activation_mm':.01,'predicate_mm':1e-10,'solver':'FINITE_FEATURE_V1'}
        state.save(root/'contact_state.json',sources,settings)
        reports.append({'name':name,'crossings':report['finite_crossings']['confirmed_transverse_crossings'],'static_candidate_pass':report['static_candidate_pass'],
            'qp_pass':report['trace'][-1]['qp']['qp_converged'],'tissue_quality_pass':report['tissue_quality']['quality_gate_passed'],
            'cavity_quality_pass':report['cavity_quality']['quality_gate_passed']})
        print('CONTACT RESULT',reports[-1],flush=True)
    write(output/'summary.json',reports);protect()

if __name__=='__main__':run(sys.argv[1:] or ['S1_expand','S2_expand','S3_expand','expand'])
