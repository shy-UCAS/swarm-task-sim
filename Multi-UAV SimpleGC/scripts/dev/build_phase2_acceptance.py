"""Consolidate the original eight-skeleton pilot and the repaired role pairs."""
import sys,json,hashlib
from pathlib import Path
from itertools import combinations
import numpy as np
PROJECT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PROJECT))
from task_v07.geometry import geometry_facts
from task_v07.io import save_json
from task_v07.execution import FROZEN_SHA256,CONFIG_PATH


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def span(values):return [float(min(values)),float(max(values))] if len(values) else None


def main():
    base=Path(sys.argv[1]);repairs=list(map(Path,sys.argv[2:-2]));planning,regression=map(Path,sys.argv[-2:]);repair=repairs[-1]
    original=read(base/'summary.json');updates=[(root,read(root/'summary.json')) for root in repairs]
    replaced={r['skeleton_id'] for root,fixed in updates for r in fixed['episodes']}
    selected=[(base,r) for r in original['episodes'] if r['skeleton_id'] not in replaced]
    selected += [(root,r) for root,fixed in updates for r in fixed['episodes']]
    items=[];conditions={};stations={};holds=[]
    for root,row in selected:
        item={k:row.get(k) for k in ('episode_id','skeleton_id','role','intent','mode','diagnostic_only',
            'source_skeleton_id','state','task_result','reason','approach_mode','member_count','approach_span_deg',
            'minimum_separation_m','coordination_matches','batch_members_match','end_to_end_wall_s')}
        item['attempt']=str(root)
        if row['path'] is not None:
            dest=root/row['path'];lab=read(dest/'labels.json');audit=read(dest/'independent_exact_audit.json')
            sk=read(root/row['skeleton_id']/'skeleton.json');scene=read(dest/'public_scene.json')
            interval=read(root/row['skeleton_id']/'planning_layer_interval.json')
            item.update(audit_status=audit['status'],audit_differences=sum(audit[k] for k in
                ('region_difference_count','target_difference_count','event_or_metric_difference_count')),
                uncovered_conditions=audit['uncovered_conditions'],truncation=read(dest/'truncation_check.json'),
                planning_minimum_m=interval[row['mode']]['minimum_m'],
                endpoint_hold_s=span([a['observed']['endpoint_hold_s'] for a in lab['agents'].values()]))
            holds+= [a['observed']['endpoint_hold_s'] for a in lab['agents'].values()]
            group=next(iter(lab['task_groups'].values()))
            item['group_conditions']=group['result']['conditions'];item['shared_revisit']=group['observed'].get('shared_revisit')
            item['observed_role_facts']={a:r['observed']['contribution'] for a,r in lab['agents'].items()}
            for scope,table in audit['condition_audit_map'].items():
                entries=table.values() if scope=='agents' else [table]
                for entry in entries:
                    for key,facts in entry.items():conditions.setdefault(key,set()).update(facts)
            f=next(e for e in scene['entities'] if e['id']==sk['target_id'])
            offsets={e['layer']:e['offset_m'] for e in scene['entities'] if e.get('facility_id')==sk['target_id']}
            kind='close_observation' if sk['execution_method']=='close_observation' else sk['role']
            if kind in ('close_observation','feint','intrusion') and row['skeleton_id'] not in stations:
                key={'close_observation':'observation_point_enu_m','feint':'planned_depth_point_enu_m','intrusion':'endpoint_enu_m'}[kind]
                points=np.array([r[key] for r in sk['references'].values()]);distance=geometry_facts(f['geometry'],points[:,:2])['signed_distance_m']
                values=(distance-offsets['alert'] if kind=='close_observation' else
                        (offsets['alert']-distance)/(offsets['alert']-offsets['protected']) if kind=='feint' else offsets['protected']-distance)
                stations[row['skeleton_id']]={'role':kind,'geometry_type':f['geometry']['type'],
                    'contour_distance_m':span(distance),'required_quantity_range':span(values),
                    'quantity':{'close_observation':'alert_outer_clearance_m','feint':'alert_depth_fraction','intrusion':'protected_depth_m'}[kind],
                    'minimum_station_spacing_m':min(float(np.linalg.norm(a-b)) for a,b in combinations(points,2))}
        items.append(item)
    regular=[r for r in items if not r['diagnostic_only']];diagnostic=[r for r in items if r['diagnostic_only']]
    pairs={}
    for row in regular:pairs.setdefault(row['skeleton_id'],[]).append(row)
    successful=[rows for rows in pairs.values() if len(rows)==2 and all(r['task_result']=='success' for r in rows)]
    roles={rows[0]['role'] for rows in successful}
    no_failures=all(r['task_result']=='success' or r['state']=='infeasible' and r['reason'].startswith(('geometry','kinematic','planning')) for r in regular)
    generated=[r for r in items if r['state']=='generated']
    zero_audit=all(r['audit_status']=='PASS' and r['audit_differences']==0 and not r['uncovered_conditions'] for r in generated)
    safe=all(r['minimum_separation_m']>=2 and r['planning_minimum_m']>=6 for r in generated)
    truncation=all(r['truncation']['status']=='PASS' for r in generated)
    timing=all(r['coordination_matches'] and r['batch_members_match'] for r in generated)
    reg=read(regression/'regression_comparison.json');process=original['process_count_check']
    final_geometry=read(planning/'unchanged_pilot_geometry.json')
    frozen=hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest()==FROZEN_SHA256
    passed=roles=={'reconnaissance','monitoring','feint','intrusion'} and no_failures and zero_audit and safe and truncation and timing and reg['status']=='PASS' and process['status']=='PASS' and final_geometry['status']=='PASS' and frozen
    report={'status':'PASS' if passed else 'NOT_ACCEPTED','scope':'handoff section 8 only; full batch remains pending',
        'base_pilot':str(base),'repair_attempts':[str(root) for root in repairs],'regular_skeletons':len(pairs),
        'successful_regular_pairs':len(successful),'regular_episode_requests':len(regular),
        'successful_regular_episodes':sum(r['task_result']=='success' for r in regular),
        'diagnostic_episode_count':len(diagnostic),'diagnostics_excluded_from_statistics':True,
        'checks':{'four_roles':sorted(roles),'only_geometry_or_kinematic_rejections_remain':no_failures,
            'zero_independent_differences_and_uncovered_conditions':zero_audit,'separation':safe,
            'truncation':truncation,'timing':timing,'regression':reg['status'],'process_count':process['status'],
            'unchanged_other_pilot_geometry':final_geometry['status'],'frozen_config':frozen},
        'minimum_actual_separation_m':min(r['minimum_separation_m'] for r in generated),
        'endpoint_hold_range_s':span(holds),'condition_audit_map':{k:sorted(v) for k,v in conditions.items()},
        'planned_station_measurements':stations,'episodes':items,
        'prior_monitoring_failures_retained_in_base':True}
    save_json(repair/'acceptance_review.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('episodes','planned_station_measurements','condition_audit_map')},ensure_ascii=False,indent=2))
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
