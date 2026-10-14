"""Frozen-code 60 regular skeletons plus six registered abort requests."""
import argparse
from pathlib import Path
import subprocess
import sys
import time
import traceback

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from task_v07.io import read_json, save_json, sha
from task_v07.execution import FROZEN_SHA256
from task_v07.expansion.contracts import P0ContractError
from scripts.run_v07_s2_expansion import INFRA_ATTEMPT, descriptor_jobs, new_attempt
from scripts.run_v07_s2_episode_batch import run_jobs
from scripts.run_v07_s2_abort import run_aborts
from scripts.v07_s2_final_reporting import final_views, final_statistics, write_tables
from scripts.v07_s2_process_comparison import compare_process_counts


def abort_jobs(regular_jobs, descriptors, records, out):
    jobs = []
    by_id = {job['descriptor']['skeleton_id']: job for job in regular_jobs}
    by_episode = {r['episode_id']: r for r in records}
    for descriptor in descriptors:
        if descriptor['subset'] != 'aborted':
            continue
        candidates = sorted(sid for sid, job in by_id.items() if job['descriptor']['family_id'] == descriptor['family_id']
                            and job['descriptor']['base_intent'] == 'penetration')
        source_id = descriptor.get('source_skeleton_id') or descriptor.get('reference_skeleton_id') or candidates[0]
        if source_id not in candidates:
            raise P0ContractError('Abort reference does not name a registered same-family penetration skeleton')
        jobs.append({'scene': by_id[source_id]['scene'], 'descriptor': descriptor,
                     'source_descriptor': by_id[source_id]['descriptor'],
                     'source_record': by_episode[source_id + '_synchronous'], 'out': str(out)})
    return jobs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, choices=(6, 7, 8), default=6)
    args = parser.parse_args()
    status = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=PROJECT, text=True)
    if status.strip():
        raise ValueError('Commit and freeze the complete code before the final attempt; working tree must be clean')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=PROJECT, text=True).strip()
    descriptors = read_json(INFRA_ATTEMPT / 'private_skeleton_descriptors.json')
    regular = [d for d in descriptors if d['subset'] == 'regular' and not d.get('diagnostic_only')]
    aborts = [d for d in descriptors if d['subset'] == 'aborted' and not d.get('diagnostic_only')]
    if len(regular) != 60 or len(aborts) != 6:
        raise P0ContractError('Final registration is not 60 regular skeletons and six abort requests')
    out = new_attempt('attempt_s2x_final')
    print(f'OUTPUT {out}', flush=True)
    save_json(out / 'registration.json', {'commit': commit, 'code_frozen': True, 'workers': args.workers,
        'source_attempt': str(INFRA_ATTEMPT), 'descriptor_sha256': sha(INFRA_ATTEMPT / 'private_skeleton_descriptors.json'),
        'config_sha256': FROZEN_SHA256, 'regular_skeletons': [d['skeleton_id'] for d in regular],
        'abort_skeletons': [d['skeleton_id'] for d in aborts], 'regular_requests': 120, 'abort_requests': 6,
        'diagnostics_included': False, 'reused_pilot_results': False})
    start = time.perf_counter()
    try:
        jobs = descriptor_jobs(INFRA_ATTEMPT, [d['skeleton_id'] for d in regular], out)
        rows = run_jobs(jobs, args.workers)
        save_json(out / 'regular_episode_records.json', rows)
        branched_jobs = abort_jobs(jobs, descriptors, rows, out)
        save_json(out / 'abort_pairing_registration.json', [{'abort_skeleton_id': j['descriptor']['skeleton_id'],
            'source_skeleton_id': j['source_descriptor']['skeleton_id'], 'source_episode_id': j['source_record']['episode_id']}
            for j in branched_jobs])
        rows += run_aborts(branched_jobs, args.workers)
        rows.sort(key=lambda r: r['episode_id'])
        save_json(out / 'episode_records.json', rows)
        views = final_views(rows)
        save_json(out / 'view_index.json', views)
        write_tables(out, views)
        statistics = final_statistics(descriptors, rows, out)
        save_json(out / 'statistics.json', statistics)
        process = compare_process_counts(out, rows)
        if not (out / 'process_comparison.json').exists():
            save_json(out / 'process_comparison.json', process)
        save_json(out / 'execution_summary.json', {'commit': commit, 'wall_s': time.perf_counter() - start,
            'record_count': len(rows), 'view_counts': views['counts'], 'exclusion_counts': views['exclusion_counts'],
            'audit': statistics['audit'], 'process_comparison_status': process['status']})
    except P0ContractError as exc:
        save_json(out / 'P0_STOP.json', {'commit': commit, 'reason': str(exc), 'traceback': traceback.format_exc()})
        raise
    print(f'COMPLETE {out}', flush=True)


if __name__ == '__main__':
    main()
