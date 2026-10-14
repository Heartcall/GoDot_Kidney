"""Compare geometry at newly indexed contacts, never use pair counts as defect depth."""
from n0_common import *
from diagnose_n0_contacts import load_pose,classify_pair
from scipy.spatial import cKDTree
from collections import Counter

def compare():
    _,a=verify_sources();summary=read_json(OUT/'contact_summary.json');locations=read_json(PROJECT/'deformation/p23/focus_locations.json')['locations']
    cloud=np.load(PROJECT/'deformation/p2/evidence/contact_sample_points.npy');tree=cKDTree(cloud);records=[]
    for space in ['actual_float32','source_float64']:
        base=read_json(OUT/'contacts'/f'u000000_{space}.json');original={(r['cavity_face'],r['tissue_face']):r for r in base['pairs'] if r['vtk_candidate']}
        if space=='actual_float32':v,_=load_pose(a,'cavity',0);tv,_=load_pose(a,'tissue',0);origin=ORIGIN
        else:v=a['cavity_reference_vertices'];tv=a['tissue_reference_vertices'];origin=np.zeros(3)
        for u in [0,.25,.5,.75,1]:
            report=read_json(OUT/'contacts'/f'u{round(u*1000000):06}_{space}.json');changed=[]
            for row in report['pairs']:
                key=(row['cavity_face'],row['tissue_face'])
                if not row['vtk_candidate'] or key in original:continue
                ref=classify_pair(v,a['cavity_faces'],tv,a['tissue_faces'],key[0],key[1],0,False,locations,origin)
                changed.append({'cavity_face':key[0],'tissue_face':key[1],'current_class':row['class'],'reference_class':ref['class'],
                   'center_mm':row['center_mm'],'reference_finite_gap_mm':ref['finite_feature_gap_mm'],'current_finite_gap_mm':row['finite_feature_gap_mm'],
                   'current_finite_segment_mm':row['finite_segment_length_mm'],'reference_finite_segment_mm':ref['finite_segment_length_mm'],
                   'distance_to_original_contact_sample_cloud_mm':float(tree.query(row['center_mm'])[0]),
                   'nearest_locations':row['nearest_locations']})
            record={'u':u,'space':space,'new_indexed_vtk_pairs':len(changed),'new_pair_current_classes':dict(Counter(r['current_class'] for r in changed)),
               'new_pair_reference_classes':dict(Counter(r['reference_class'] for r in changed)),
               'max_distance_to_original_contact_sample_cloud_mm':max([r['distance_to_original_contact_sample_cloud_mm'] for r in changed],default=0.),
               'new_confirmed_transverse_crossings':sum(r['current_class']=='FINITE_TRANSVERSE_CROSSING' for r in changed),'new_pairs':changed}
            records.append(record)
    write_json(OUT/'contact_changes.json',{'records':records,'source_hashes':AUTHORITY,
       'limits':['Contact cloud distance localizes changes, not penetration depth or anatomical permission.','New face pairs are independently reclassified in Reference; a changed pair index is not a new physical defect.','No continuous collision certificate.']})
    print('Compared new contact geometry:',[(r['u'],r['space'],r['new_indexed_vtk_pairs']) for r in records]);protected()

if __name__=='__main__':compare()
