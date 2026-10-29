"""Read-only diagnosis of the selected PPT fixtures and in-memory replay."""
import json
import pickle
import random
import hashlib
import numpy as np
import viz2_render as vr
from task_v07.unified.spec import build_spec, proposal_seed
from task_v07.unified.free_space import free_space, work_region
from task_v07.unified.shapes import draw_shape
from task_v07.unified.route import route_group


def replay(ep, group_id='task_group_01'):
    root = vr.DATA_ROOT / vr.B_RUN
    skeleton = ep['dir'].parent.name
    descriptor_path = root / 'descriptors' / 'descriptors.json'
    descriptors = vr.read_json(descriptor_path)
    if isinstance(descriptors, dict):
        descriptors = descriptors['descriptors']
    descriptor = next(d for d in descriptors if d['skeleton_id'] == skeleton)
    task = vr.read_json(ep['dir'] / 'task.json')
    with (root / 'planning' / skeleton / 'candidate_pool.pkl').open('rb') as f:
        pool = pickle.load(f)['pool']
    selected = next(c for c in pool if all(
        np.array_equal(c['skeleton']['references'][a]['points_enu_m'], r['points_enu_m'])
        for a, r in task['references'].items()))
    group = next(g for g in descriptor['task_groups'] if g['group_id'] == group_id)
    spec = build_spec(descriptor, group)
    free = free_space(ep['scene'], spec)
    region = work_region(ep['scene'], spec, free)
    index = selected['group_candidate_indices'][group_id]
    rng = random.Random(proposal_seed(spec, index))
    shape = draw_shape(spec, region, rng, free)
    bundle, template = route_group(ep['scene'], spec, shape, free,
                                  descriptor['family_conditions']['initial_states'], rng)
    errors = {}
    for agent in group['members']:
        a = np.asarray(bundle.waypoints_by_agent[agent])
        b = np.asarray(task['references'][agent]['points_enu_m'])
        errors[agent] = float(np.max(np.abs(a-b))) if a.shape == b.shape else None
    return free, pool, selected, group, errors, descriptor_path, index


def main():
    for mode in ('synchronous', 'sequential'):
        for intent in vr.INTENT_ORDER:
            ep = vr.av.load_episode(vr.vp.episode_for(vr.B_RUN, vr.B_FAMILY, vr.B_SLOT, intent, mode))
            print(mode, intent, ep['t'][-1], 'core', [round(ep['t'][v], 1) if v is not None else None for v in ep['core'].values()],
                  'groups', [g['members'] for g in ep['groups']], flush=True)
    ep = vr.av.load_episode(vr.vp.episode_for(vr.B_RUN, vr.B_FAMILY, vr.B_SLOT, 'reconnaissance', 'synchronous'))
    result = replay(ep)
    free, pool, selected, group, errors, path, index = result
    print('REPLAY', errors, 'proposal', index, 'descriptor', path, flush=True)
    print('PLANNERS', [(k, len(p.vertices)) for k,p in free._planners.items()])
    pairs = vr.read_json(vr.M3_ROOT/'m3_r3_r2_attempt01'/'paired_results.json')
    for name, *_ in vr.D_TASKS:
        pair = next(p for p in pairs if p['mission_id'] == name)
        print('PAIR', name, json.dumps(pair, ensure_ascii=False)[:6000])


if __name__ == '__main__':
    main()
