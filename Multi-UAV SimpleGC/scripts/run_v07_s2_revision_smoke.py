"""All 60 registered skeletons: geometry and nominal spacing only, never flights."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from scripts.run_v07_s2_expansion import INFRA_ATTEMPT, descriptor_jobs, new_attempt
from scripts.v07_s2_revision_diagnostics import INTENTS, DIMENSIONS, NAMES, dimensions
from task_v07.expansion.candidate_search import episode_candidate_pool
from task_v07.io import read_json, save_json, sha


def worker(job):
    started = time.perf_counter()
    descriptor, scene = job['descriptor'], job['scene']
    out = Path(job['out']) / descriptor['skeleton_id']
    out.mkdir()
    pool, search = episode_candidate_pool(scene, descriptor)
    save_json(out/'candidate_search.json', search)
    if pool:
        save_json(out/'selected_skeleton.json', pool[0]['skeleton'])
        save_json(out/'planning_checks.json', pool[0]['checks'])
    count = sum(e['type'] == 'facility' for e in scene['entities'])
    result = {'skeleton_id': descriptor['skeleton_id'], 'family_id': descriptor['family_id'],
              'intent': descriptor['base_intent'], **dimensions(descriptor, {descriptor['family_id']: count}),
              'success': bool(pool), 'candidate_reason_counts': search['rejection_reasons'],
              'candidate_budget': search['candidate_budget'], 'attempted_candidates': search['attempted_candidates'],
              'eligible_candidates': len(pool), 'solo_flights_run': 0, 'planning_wall_s': time.perf_counter()-started,
              'evidence': str(out/'candidate_search.json')}
    save_json(out/'planning_result.json', result)
    print(json.dumps({'stage': 'planning_smoke_complete', **{k: result[k] for k in
          ('skeleton_id', 'success', 'attempted_candidates', 'eligible_candidates', 'planning_wall_s')}}, ensure_ascii=False), flush=True)
    return result


def matrices(skeletons):
    result = {}
    for dimension, values in DIMENSIONS.items():
        cells = []
        for intent in INTENTS:
            for value in values:
                selected = [s for s in skeletons if s['intent'] == intent and s[dimension] == value]
                successes = sum(s['success'] for s in selected)
                reasons = Counter()
                for row in selected:
                    if not row['success']:
                        reasons.update(row['candidate_reason_counts'])
                cells.append({'intent': intent, 'dimension': dimension, 'value': value,
                              'registered': len(selected), 'successful': successes,
                              'fraction': successes/len(selected) if selected else None,
                              'candidate_reason_counts': dict(reasons.most_common())})
        if sum(c['registered'] for c in cells) != 60:
            raise ValueError('Planning matrix must partition all 60 skeletons')
        result[dimension] = cells
    return result


def render(data, out):
    lines = ['## 任务 G：全 60 骨架规划冒烟', '',
             f"规划代码提交 `{data['source_commit']}`；证据目录 `{out}`。",
             '只做连续候选纯几何、两种时序的名义整 episode 间距预筛及同向 115% 路程筛选；没有单机测时或联合仿真。规划可行不代表最终任务成功。本步不设通过门槛。', '',
             f"可行 {sum(s['success'] for s in data['skeletons'])}/60；每骨架尝试至少 200 个候选，实际单机仿真数 0。", '']
    for dimension, cells in data['matrices'].items():
        lines += [f'### 规划可行率：{dimension}', '', '| 意图 | 条件 | 可行/登记 | 可行率 |', '|---|---|---|---|']
        for c in cells:
            ratio = '未登记' if c['fraction'] is None else f"{100*c['fraction']:.2f}%"
            lines.append(f"| {NAMES[c['intent']]} | {c['value']} | {c['successful']}/{c['registered']} | {ratio} |")
        lines.append('')
    lines += [f"[全部候选与淘汰原因索引](<{(out/'diagnostics.json').as_posix()}>)；修订前、规划、修订后并排对照将在任务 I 后汇总。", '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, choices=(6, 7, 8), default=8)
    parser.add_argument('--report', type=Path, default=PROJECT/'docs/v07/S2_revision_report.md')
    args = parser.parse_args()
    descriptors = [d for d in read_json(INFRA_ATTEMPT/'private_skeleton_descriptors.json')
                   if d['subset'] == 'regular' and not d.get('diagnostic_only')]
    if len(descriptors) != 60:
        raise ValueError('Expected all 60 regular skeletons')
    out = new_attempt('attempt_s2_revision_planning')
    print(f'OUTPUT {out}', flush=True)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=PROJECT, text=True).strip()
    source_hash = sha(INFRA_ATTEMPT/'private_skeleton_descriptors.json')
    save_json(out/'registration.json', {'commit': commit, 'source_attempt': str(INFRA_ATTEMPT),
               'source_descriptor_sha256': source_hash, 'workers': args.workers, 'registered_skeletons': 60,
               'single_agent_calibration': False, 'joint_simulation': False})
    jobs = descriptor_jobs(INFRA_ATTEMPT, [d['skeleton_id'] for d in descriptors], out)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(worker, job) for job in jobs]
        records = [future.result() for future in as_completed(futures)]
    records.sort(key=lambda r: r['skeleton_id'])
    if len(records) != 60 or any(r['attempted_candidates'] < 200 or r['solo_flights_run'] != 0 for r in records):
        raise ValueError('Incomplete planning-only execution evidence')
    if source_hash != sha(INFRA_ATTEMPT/'private_skeleton_descriptors.json'):
        raise ValueError('Registered descriptors changed')
    data = {'source_attempt': str(out), 'source_commit': commit, 'skeletons': records,
            'matrices': matrices(records), 'simulation_runs': 0, 'source_descriptors_unchanged': True}
    save_json(out/'diagnostics.json', data)
    report = args.report.read_text(encoding='utf-8')
    if '<!-- revision-planning-smoke -->' in report:
        raise ValueError('Planning report already recorded')
    args.report.write_text(report+'\n<!-- revision-planning-smoke -->\n'+render(data, out), encoding='utf-8', newline='\n')
    print(json.dumps({'planning_feasible_skeletons': sum(r['success'] for r in records), 'registered': 60,
                      'solo_flights': 0, 'output': str(out)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
