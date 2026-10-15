"""New isolated five-state verification. Full float64 physical self/relative
checks, all-face float32 quality and relative intersection diagnostics.
No partial gate promotes any research resource.
"""
from n21_common import *
from n20_stage_audit import fast_classify,shared_one_pairs
from n16_contacts import self_bbox_pairs,classify
from audit_tissue_cavity import contact_pairs,classify_contacts
from n16_closure_and_regions import closure_variants,local_quality
from n20_verify import independent_volume
from n21_robust_patch import display_quality

def run(name):
    protect();a,d2,tv,tf,resolved,approval=inputs()
    folder=ROOT/name if name.startswith('robust_contract') else ROOT/'warm_contact'/name
    c=np.load(folder/'cavity_offset.npy');t=np.load(folder/'tissue_offset.npy');out=ROOT/'verification'/name;out.mkdir(parents=True,exist_ok=True)
    sources={'cavity':sha(folder/'cavity_offset.npy'),'tissue':sha(folder/'tissue_offset.npy')}
    shared=shared_one_pairs(tf,len(tv));rows=[];origin=np.array([16,16,-81.]);rC=(a['vertices']-origin).astype(np.float32);rT=(tv-origin).astype(np.float32)
    for u in [0,.25,.5,.75,1.]:
        p=out/f'u{round(u*100):03}.json.gz'
        if p.exists():
            cached=read(p)
            if cached['sources']!=sources:raise ValueError('Stale N2.1-R verification')
            rows.append(cached['summary']);continue
        v=a['vertices']+u*c;w=tv+u*t;dv=d2['reference_vertices']+u*map_d2(c,d2);results={}
        for kind,x,f,y,g in [('cavity_self',v,a['faces'],v,a['faces']),('tissue_self',w,tf,w,tf),('D2_self',dv,d2['faces'],dv,d2['faces']),('cavity_tissue',v,a['faces'],w,tf)]:
            pairs=self_bbox_pairs(x,f) if kind.endswith('self') else contact_pairs(x,f,y,g)
            results[kind]=fast_classify(x,f,y,g,pairs)
            print('N21 VERIFY',name,u,kind,results[kind]['confirmed_transverse_crossings'],flush=True)
        proper,_=classify_contacts(w,tf,w,tf,shared,tolerance=1e-10)
        results['tissue_shared_vertex_transverse']=classify(w,tf,w,tf,shared[proper])
        vc=(rC+np.float32(u)*c.astype(np.float32)).astype(float)+origin
        wt=(rT+np.float32(u)*t.astype(np.float32)).astype(float)+origin
        results['float32_cavity_tissue']=fast_classify(vc,a['faces'],wt,tf,contact_pairs(vc,a['faces'],wt,tf))
        integral=independent_volume(dv,d2['faces']);cap=closure_variants(dv,d2,approval)
        counts={k:r['confirmed_transverse_crossings'] for k,r in results.items()}
        summary={'u':u,'counts':counts,'D2_oriented_integral_mL':integral['volume_mL'],
            'sampled_measurement_domain_valid':bool(integral['numerically_valid'] and all(x['geometrically_valid_at_sample'] for x in cap) and not counts['D2_self']),
            'source_float64_crossings':sum(n for k,n in counts.items() if not k.startswith('float32')),
            'float32_relative_crossings':counts['float32_cavity_tissue'],
            'fixed_cavity_maximum_mm':float(np.linalg.norm(u*c[a['port_fixed_masks'].any(0)],axis=1).max())}
        gzip_write(p,{'sources':sources,'results':results,'volume':integral,'cap_comparisons':cap,'summary':summary});rows.append(summary)
    report={'name':name,'sources':sources,'five_levels':rows,'cavity_quality':quality(a['vertices'],a['faces'],c),'tissue_quality':quality(tv,tf,t),
        'cavity_float32_quality':display_quality(a['vertices'],a['faces'],c),'tissue_float32_quality':display_quality(tv,tf,t),
        'all_float64_sampled_crossings_zero':all(r['source_float64_crossings']==0 for r in rows),
        'all_float32_relative_crossings_zero':all(r['float32_relative_crossings']==0 for r in rows),
        'complete_self_CCD_certified':False,'float32_self_intersections_at_all_times_certified':False,'formal_N2':False}
    write(out/'summary.json',report);write(out/'local_quality.json',local_quality(a,resolved,c,tv,tf,t));protect()
    print('FINAL VERIFY',name,report['all_float64_sampled_crossings_zero'],report['all_float32_relative_crossings_zero'],flush=True)

if __name__=='__main__':run(sys.argv[1])
