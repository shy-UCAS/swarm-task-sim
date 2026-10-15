"""Audit registered public stock geometry without planning or simulation."""
from collections import defaultdict
from pathlib import Path
import json
import sys
import numpy as np

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from scripts.run_v07_s2_expansion import INFRA_ATTEMPT, new_attempt
from task_v07.io import read_json, save_json, sha
from task_v07.expansion.public_approach_shape import public_approach_shape


def main():
    source=INFRA_ATTEMPT/'private_skeleton_descriptors.json';before=sha(source)
    descriptors=[d for d in read_json(source) if d['subset']=='regular' and not d.get('diagnostic_only')]
    rows=[];cohorts=defaultdict(list);summaries=defaultdict(list)
    for d in descriptors:
        for g in d['task_groups']:
            multi=d['common_draw']['approach_mode']=='multi_direction'
            shape=public_approach_shape(d['family_conditions'],d['common_draw']['slot'],g['members'],multi)
            key=(d['family_id'],d['common_draw']['slot'],tuple(sorted(g['members'])))
            angles=shape['relative_bearings_deg']
            span=max(abs((a-b+180)%360-180) for a in angles for b in angles)
            row={'skeleton_id':d['skeleton_id'],'intent':d['base_intent'],'group_id':g['group_id'],
                 'role':g['execution_method'],'approach_mode':d['common_draw']['approach_mode'],
                 'shape':shape,'planned_max_pair_angle_deg':span}
            rows.append(row);cohorts[key].append(row)
            summaries[(g['execution_method'],shape['split_count'])].append(span)
    for cohort in cohorts.values():
        if any(r['shape']!=cohort[0]['shape'] for r in cohort):raise ValueError('Intent-dependent public stock geometry')
    result={'status':'PASS','registered_skeletons':len(descriptors),'registered_groups':len(rows),'rows':rows,
        'equal_key_cohorts':[{'family_id':key[0],'common_slot':key[1],'member_set':key[2],
                             'intents':sorted({r['intent'] for r in values}),'shape_identical':True}
                            for key,values in cohorts.items()],
        'planned_spans_by_role_and_stocks':[{'role':role,'stock_count':stocks,'n':len(values),
            'minimum':min(values),'median':float(np.median(values)),'p90':float(np.percentile(values,90)),'maximum':max(values)}
            for (role,stocks),values in sorted(summaries.items())],
        'source_sha256':before,'simulations':0,'scope':'registered planning condition; measured spans follow full execution'}
    if sha(source)!=before:raise ValueError('Source descriptors changed')
    out=new_attempt('attempt_s2_revision_D_public_shape');save_json(out/'public_shape_audit.json',result)
    print(json.dumps({'status':result['status'],'groups':len(rows),'output':str(out),
                      'planned_spans':result['planned_spans_by_role_and_stocks']},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
