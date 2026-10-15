"""Observed branch of a referenced regular synchronous episode, on the frozen plant."""
from copy import deepcopy
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import time
import numpy as np

from task_v07.io import read_json, save_json
from task_v07.execution import execute, completion_budget
from task_v07.expansion.abort_planning import plan_abort, verify_abort_prefix
from task_v07.expansion.episode_pipeline import episode_interval_check
from task_v07.expansion.role_planners import PlanningInfeasible
from task_v07.expansion.contracts import P0ContractError
from scripts.run_v07_s2_episode_batch import write_result


def run_aborts(jobs, workers):
    pool=ProcessPoolExecutor(max_workers=workers)
    futures=[pool.submit(run_abort_job,job) for job in jobs]
    rows=[]
    try:
        for future in as_completed(futures):
            rows.append(future.result())
    except BaseException:
        for future in futures:
            future.cancel()
        for process in list(pool._processes.values()):
            process.terminate()
        pool.shutdown(wait=True,cancel_futures=True)
        raise
    pool.shutdown(wait=True)
    return rows


def unavailable(descriptor, source, reason, state='infeasible'):
    return {'episode_id': descriptor['skeleton_id'] + '_synchronous', 'skeleton_id': descriptor['skeleton_id'],
            'family_id': descriptor['family_id'], 'intent': 'penetration', 'mode': 'synchronous',
            'aborted': True, 'diagnostic_only': False, 'source_episode_id': source['episode_id'],
            'state': state, 'path': None, 'quality_valid': None, 'audit_passed': None, 'task_result': None,
            'reason': reason, 'coordination_by_group': {}, 'common_slot': descriptor['common_draw']['slot']}


def run_abort_job(payload):
    scene, requested, source_record = (payload[key] for key in ('scene', 'descriptor', 'source_record'))
    out = Path(payload['out'])
    source_attempt = Path(payload.get('source_attempt', out))
    root = out / requested['skeleton_id']
    root.mkdir()
    save_json(root / 'registered_abort_descriptor.json', requested)
    if source_record['path'] is None:
        row = unavailable(requested, source_record, 'referenced_regular_trajectory_not_generated', 'pending')
        save_json(root / 'not_run.json', row)
        return row
    source_directory = source_attempt / source_record['path']
    source_task = read_json(source_directory / 'task.json')
    source_private = read_json(source_directory / 'source.json')
    with np.load(source_directory / 'truth_10hz.npz', allow_pickle=False) as loaded:
        source_run = {key: loaded[key].copy() for key in ('time_us', 'p', 'v', 'a')}
        source_run['agent_ids'] = loaded['agent_ids'].tolist()
    descriptor = deepcopy(payload['source_descriptor'])
    descriptor.update(skeleton_id=requested['skeleton_id'], subset='aborted',
                      abort_registration=deepcopy(requested), source_skeleton_id=source_task['skeleton_id'])
    started = time.perf_counter()
    try:
        task, bundle, registration = plan_abort(scene, payload['source_descriptor'], source_task, source_run, requested)
        unchanged_groups=[gid for gid in task['group_skeletons'] if gid!=task['main_group_id']]
        for gid in unchanged_groups:
            if task['group_skeletons'][gid]['references']!=source_task['group_skeletons'][gid]['references']:
                raise P0ContractError('Abort changed another task group route')
        plan = source_private['timing_plan']
        intervals = episode_interval_check(task, bundle, {'synchronous': plan, 'sequential': plan})
        intervals['applicable_modes'] = ['synchronous']
        intervals['sequential'] = {'not_applicable': True, 'reason': 'abort registration requires synchronous version only'}
        save_json(root / 'planning_layer_interval.json', intervals)
        save_json(root / 'skeleton.json', task)
        save_json(root / 'abort_pairing.json', registration)
        if intervals['synchronous']['below_warning']:
            raise PlanningInfeasible('planning_spacing_rejection',
                f"Abort full-route constant-speed estimate below {intervals['warning_threshold_m']:g}m; referenced prefix and delays are immutable")
    except PlanningInfeasible as exc:
        row = unavailable(requested, source_record, exc.category)
        row['rejection_detail'] = exc.detail
        save_json(root / 'planning_rejection.json', row)
        return row
    setup = time.perf_counter() - started
    run = execute(task, plan['departure_delays_s'], time_budget=completion_budget(task, plan['departure_delays_s']),
                  route_switch=task['route_switch'])
    prefix = verify_abort_prefix(source_run, run, registration['branch_time_us'])
    if not run.get('route_switch_applied'):
        raise P0ContractError('Abort route switch was never applied')
    save_json(root / 'exact_prefix_comparison.json', prefix)
    extras = {'source_episode_id': source_record['episode_id'], 'source_skeleton_id': source_task['skeleton_id'],
              'abort_pairing': registration, 'exact_prefix_comparison': prefix, 'amortized_skeleton_setup_s': setup,
              'other_group_routes_unchanged': unchanged_groups, 'departure_delays_reused_exactly': True}
    row = write_result(scene, descriptor, task, bundle, run, plan,
                       source_private['single_agent_measured_core_times_s'], 'synchronous', out, setup,
                       extra_metrics=extras)
    return row
