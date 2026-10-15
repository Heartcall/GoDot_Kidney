"""Known non-transverse research mappings are warm starts, NOT new cures or
automatically certified states. Compare finite constraints with old halfspaces."""
from n21_common import *
from n21_features import FiniteTissue,ContactState

def run():
    protect();a,d2,tv,tf,resolved,approval=inputs();tm=FiniteTissue(a,tv,tf,resolved);rows=[]
    for name in ['S1_expand','S2_expand','expand']:
        c,_,sources=fixture(name)
        if name.startswith('S'):t=np.load(OLD/f'regression/{name}/best_tissue_offset_RESEARCH_ONLY.npy')
        else:_,t,_=fixture(name)
        if name.startswith('S'):
            old=read(N16/f'prototypes/thin_face_corrected/{name}/contacts/u100.json')['results']['cavity_tissue']
            pairs={(r['cavity_face'],r['tissue_face']) for r in old['rows'] if r['class']=='FINITE_TRANSVERSE_CROSSING'}
        else:pairs={(34852,181160)}
        state=ContactState();new,report=tm.solve_finite(c,pairs,state,warm_cavity=c,warm_tissue=t)
        root=ROOT/'warm_contact'/name;root.mkdir(parents=True,exist_ok=True)
        np.save(root/'cavity_offset.npy',c);np.save(root/'tissue_offset.npy',new);gzip_write(root/'contact_report.json.gz',report)
        state.save(root/'state.json',sources,{'activation_mm':.01,'solver':'WARM_FINITE_V1'})
        rows.append({'name':name,'static_candidate_pass':report['static_candidate_pass'],'crossings':report['finite_crossings']['confirmed_transverse_crossings'],
            'qp_pass':report['trace'][-1]['qp']['qp_converged'],'max_tissue_change_mm':float(np.linalg.norm(new-t,axis=1).max()),
            'warm_start_is_previous_N20_research_mapping':True,'not_a_new_independent_mapping_cure':True,'continuous_certificate':False})
        print('WARM FINITE',rows[-1],flush=True)
    write(ROOT/'warm_contact/summary.json',rows);protect()

if __name__=='__main__':run()
