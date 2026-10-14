"""Regenerate two registered skeletons with one and two workers; compare evidence."""
from pathlib import Path
from task_v07.io import save_json
from task_v07.expansion.contracts import P0ContractError
from scripts.run_v07_s2_expansion import descriptor_jobs, INFRA_ATTEMPT, compare_episode_dirs
from scripts.run_v07_s2_episode_batch import run_jobs


def compare_process_counts(attempt, records):
    attempt = Path(attempt)
    pool = {}
    for row in records:
        if not row.get('aborted') and row['state'] == 'generated' and row.get('quality_valid') and row.get('audit_passed'):
            pool.setdefault(row['skeleton_id'], []).append(row)
    pairs = [(sid, rows) for sid, rows in sorted(pool.items()) if len(rows) == 2]
    multi = next(((sid, rows) for sid, rows in pairs if rows[0]['group_count'] > 1), None)
    if multi is None:
        return {'status': 'not_run', 'reason': 'No retained multi-group pair available for process comparison'}
    second = next(((sid, rows) for sid, rows in pairs if sid != multi[0] and rows[0]['group_count'] == 1), None)
    second = second or next(((sid, rows) for sid, rows in pairs if sid != multi[0]), None)
    if second is None:
        return {'status': 'not_run', 'reason': 'Fewer than two retained skeleton pairs'}
    selected = [multi[0], second[0]]
    roots = []
    for workers in (1, 2):
        root = attempt / f'process_{workers}'
        root.mkdir()
        roots.append(root)
        save_json(root / 'registration.json', {'workers': workers, 'selected_skeletons': selected,
                                              'selection': 'first retained multi-group pair and first distinct single-group pair, lexical order'})
        rows = run_jobs(descriptor_jobs(INFRA_ATTEMPT, selected, root), workers)
        save_json(root / 'episode_records.json', rows)
    differences = []
    for sid in selected:
        differences += [{**d, 'skeleton_id': sid, 'scope': 'skeleton'} for d in compare_episode_dirs(
            roots[0] / sid, roots[1] / sid,
            ['skeleton.json', 'timing_calibration.json', 'planning_checks.json', 'planning_layer_interval.json', 'geometry_history.json'], [], [])]
        for mode in ('synchronous', 'sequential'):
            left, right = (root / sid / mode for root in roots)
            if not left.exists() or not right.exists():
                raise P0ContractError('Previously retained skeleton disappeared in process-count regeneration')
            rows = compare_episode_dirs(left, right,
                ['task.json', 'labels.json', 'prefix_labels.json', 'source.json', 'manifest.json', 'public_scene.json',
                 'independent_exact_audit.json', 'policy_geometry_audit.json', 'truncation_check.json'],
                ['truth_10hz.npz', 'model_input.npz', 'frame_labels.npz'], ['truth.csv', 'observations.csv'])
            for row in rows:
                if row['file'] == 'independent_exact_audit.json' and row['path'].split('.')[-1] == 'directory':
                    row['class'] = 'metadata:path'
                differences.append({**row, 'skeleton_id': sid, 'mode': mode, 'scope': 'episode'})
    count = sum(row['class'] == 'content' for row in differences)
    report = {'status': 'PASS' if count == 0 else 'P0_STOP', 'skeleton_ids': selected,
              'workers': [1, 2], 'includes_multiple_groups': True, 'content_difference_count': count,
              'differences': differences, 'reused_pilot_trajectories': False}
    save_json(attempt / 'process_comparison.json', report)
    if count:
        raise P0ContractError('One/two worker runs changed generated content')
    return report
