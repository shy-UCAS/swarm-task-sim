"""Read-only margin evidence for zero-width reference corridors."""
from pathlib import Path
import sys, json, random
import numpy as np
PROJECT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(PROJECT))
from task_v07.io import read_json, sha
from scripts.run_v07_m3_trial import atomic
from scripts.run_v07_s2_expansion import descriptor_jobs
from task_v07.geometry import geometry_facts
from task_v07.unified.spec import build_spec, proposal_seed
from task_v07.unified.free_space import free_space, work_region
from task_v07.unified.shapes import draw_shape
from task_v07.unified.route import route_group
from task_v07.unified.checks import plan_checks
registration = read_json(PROJECT/'docs/v07/evidence/m3/m3_inputs.json')
q2 = read_json(PROJECT/'docs/v07/evidence/m3/m3a_q2.json'); root = Path(q2['attempt'])
q3 = read_json(PROJECT/'docs/v07/evidence/m3/m3a_trial.json'); q3_root = Path(q3['attempt'])
q3_links = []
for fixed in registration['selected']:
    if not fixed['q3']: continue
    sid = fixed['skeleton_id']
    planned = root/sid/'selected_skeleton.json'
    executed = q3_root/sid/'geometry_00'/'skeleton.json'
    q3_links.append({'skeleton_id': sid, 'q2_skeleton_sha256': sha(planned),
                     'q3_skeleton_sha256': sha(executed), 'identical': sha(planned) == sha(executed)})
jobs = descriptor_jobs(registration['descriptor_attempt'], [r['skeleton_id'] for r in registration['selected']], PROJECT)
rows = []; replay = []
for job in jobs:
    sid = job['descriptor']['skeleton_id']; sk = read_json(root/sid/'selected_skeleton.json'); checks = read_json(root/sid/'selected_checks.json')
    for gid, group in sk['group_skeletons'].items():
        registered_group = next(g for g in job['descriptor']['task_groups'] if g['group_id'] == gid)
        spec = build_spec(job['descriptor'], registered_group); free = free_space(job['scene'], spec)
        index = sk['candidate_selection']['group_candidate_indices'][gid]
        rng = random.Random(proposal_seed(spec, index))
        shape = draw_shape(spec, work_region(job['scene'], spec, free), rng, free)
        bundle, template = route_group(job['scene'], spec, shape, free, job['descriptor']['family_conditions']['initial_states'], rng)
        result = plan_checks(job['scene'], spec, bundle, template, free, job['descriptor']['family_conditions']['initial_states'])
        identical = all(bundle.waypoints_by_agent[a] == group['references'][a]['points_enu_m'] for a in group['members'])
        replay.append({'skeleton_id':sid,'group_id':gid,'candidate_index':index,'routes_exactly_identical':identical,'checks_status':result['status']})
        for agent, ref in group['references'].items():
            if ref['reference_obstacle_margin_m'] != 37.: continue
            points = np.array(ref['points_enu_m'])[:, :2]
            entry = checks[gid]['members'][agent]['first_warning_entry']
            approach = [*points[:entry['segment']+1], np.array(entry['point'])]
            distance = min(geometry_facts(e['geometry'], np.array([a,b]), footprint=True)['clearance_m']
                           for a,b in zip(approach,approach[1:]) for e in job['scene']['entities'] if e['type']=='hard_constraint_obstacle')
            rows.append({'skeleton_id':sid,'agent_id':agent,'minimum_obstacle_clearance_m':distance})
passed = (all(r['routes_exactly_identical'] and r['checks_status']=='PASS' for r in replay)
          and all(r['identical'] for r in q3_links))
evidence = {'status':'PASS' if passed else 'FAIL',
            'scope':'Replay only previously accepted proposals after zero-width corridor implementation correction; no new pool sampling or simulation',
            'q2_attempt': str(root), 'q3_attempt': str(q3_root), 'q2_q3_skeleton_identity': q3_links,
            'singleton_clearances':rows,'accepted_proposal_replay':replay}
atomic(PROJECT/'docs/v07/evidence/m3/m3a_corridor_recheck.json', evidence)
print(json.dumps(evidence, ensure_ascii=False))
raise SystemExit(0 if passed else 1)
