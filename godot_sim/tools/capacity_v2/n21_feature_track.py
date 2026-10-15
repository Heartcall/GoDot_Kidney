"""Finite contact feature history on a real known trajectory. Sampled tracking
is explicitly distinct from exact continuous transverse certificates."""
from n21_common import *
from n21_features import ContactState,finite_features

def run():
    protect();a,d2,tv,tf,resolved,approval=inputs();c=np.load(OLD/'regression_S1_expand/cavity_001.npy');t=np.load(OLD/'regression_S1_expand/tissue_001.npy')
    baseline=read(PROJECT/'deformation/capacity_v2_n0_research/contacts/u000000_source_float64.json')
    pairs={(r['cavity_face'],r['tissue_face']) for r in baseline['pairs'] if r['class']=='COPLANAR_OVERLAP'}
    old=read(N16/'prototypes/thin_face_corrected/S1_expand/contacts/u100.json')['results']['cavity_tissue']
    pairs|={(r['cavity_face'],r['tissue_face']) for r in old['rows'] if r['class']=='FINITE_TRANSVERSE_CROSSING'};pairs.add((34852,181160))
    sources={'cavity_endpoint_bytes':hashlib.sha256(c.tobytes()).hexdigest(),'tissue_endpoint_bytes':hashlib.sha256(t.tobytes()).hexdigest()}
    settings={'frames':9,'activation_mm':.01,'method':'SAMPLED_FINITE_FEATURE_TRACK_V1'};root=ROOT/'feature_tracking';root.mkdir(exist_ok=True)
    def step(state,k,previous_c,previous_t):
        u=k/8;cv=a['vertices']+u*c;tt=tv+u*t;features=[]
        for ci,ti in sorted(pairs):
            values,_=finite_features(cv,tt,a['faces'][ci],tf[ti],ci,ti,previous_c,previous_t);features.extend(values)
        angles=[];parameter=[];orientation_events=[]
        for value in features:
            old=state.features.get(value['key'])
            if old:
                angle=float(np.degrees(np.arccos(np.clip(np.dot(value['normal'],old['normal']),-1,1))));angles.append(angle)
                if angle>90:orientation_events.append({'key':value['key'],'kind':value['kind'],'pair':value['pair'],'old_normal':old['normal'],'new_normal':value['normal'],'angle_deg':angle,
                    'status':'UNRESOLVED_FEATURE_NORMAL_OR_SUPPORT_CHANGE'})
                parameter.append(float(np.linalg.norm(np.array(value['cavity_weights'])-old['cavity_weights'])+np.linalg.norm(np.array(value['tissue_weights'])-old['tissue_weights'])))
        state.iteration=k;state.outer_index=k;state.update(features);state.stage='GEOMETRY_TRACK_ONLY'
        state.numerical={'previous_cavity':cv.copy(),'previous_tissue':tt.copy()}
        row={'u':u,'features_at_sample':len(features),'retained_inactive_features':sum(not x['active'] for x in state.features.values()),
            'maximum_normal_change_deg':max(angles,default=0),'normal_flips_over_90':sum(x>90 for x in angles),
            'maximum_parameter_change':max(parameter,default=0),'orientation_events':orientation_events,
            'actual_D2_mL':volume(d2['reference_vertices']+u*map_d2(c,d2),d2['faces'])}
        return cv,tt,row
    state=ContactState();state.pairs=pairs.copy();previous_c=a['vertices'];previous_t=tv;rows=[]
    for k in range(9):
        previous_c,previous_t,row=step(state,k,previous_c,previous_t);rows.append(row)
        if k==4:state.save(root/'midpoint_checkpoint.json',sources,settings)
    restored=ContactState.load(root/'midpoint_checkpoint.json',sources,settings)
    pc=restored.numerical['previous_cavity'];pt=restored.numerical['previous_tissue']
    for k in range(5,9):pc,pt,row=step(restored,k,pc,pt)
    equal=state.features==restored.features and np.array_equal(pc,previous_c) and np.array_equal(pt,previous_t)
    write(root/'summary.json',{'pairs':len(pairs),'frames':rows,'all_active_and_inactive_history_retained':True,
        'uninterrupted_vs_resumed_history_exactly_equal':equal,'continuous_feature_manifold_tracking_certified':False,
        'normal_flips_require_feature_orientation_review':sum(x['normal_flips_over_90'] for x in rows)})
    state.save(root/'final_state.json',sources,settings);protect();print('FEATURE TRACK real timeline restored exactly',equal,flush=True)

if __name__=='__main__':run()
