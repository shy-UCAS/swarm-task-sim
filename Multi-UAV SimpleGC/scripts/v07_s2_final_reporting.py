"""Final attempt statistics and training views from retained, audited records."""
from collections import Counter
from pathlib import Path
import csv
import numpy as np

from task_v07.io import save_json, read_json
from task_v07.expansion.views import make_views, diagnostic_summary
from task_v07.expansion.sampling import INTENTS


def distribution(values):
    values = [float(v) for v in values if v is not None]
    return {"n": len(values), "median": float(np.median(values)) if values else None,
            "p90": float(np.percentile(values, 90)) if values else None,
            "maximum": max(values) if values else None,
            "minimum": min(values) if values else None}


def final_views(records):
    ordinary = [r for r in records if not r.get('diagnostic_only', False)]
    usable = [r for r in ordinary if r['state'] == 'generated' and r.get('quality_valid') is True
              and r.get('audit_passed') is True]
    result = make_views(usable)
    invalid_aborts = {r['episode_id'] for r in usable if r.get('aborted') and r.get('abort_observation_valid') is not True}
    retained_aborts = []
    for row in result['views']['aborted']:
        if row['episode_id'] in invalid_aborts:
            result['views']['failed'].append({**row, 'reason': 'abort_observed_withdrawal_not_completed'})
        else:
            retained_aborts.append(row)
    result['views']['aborted'] = retained_aborts
    result['views']['failed'].sort(key=lambda r: r['episode_id'])
    result['counts'] = {key: len(rows) for key, rows in result['views'].items()}
    result['exclusions'] = {
        'planning_rejections': [r for r in ordinary if r['state'] == 'infeasible'],
        'generation_errors': [r for r in ordinary if r['state'] == 'generation_error' or r.get('quality_valid') is False],
        'not_run': [r for r in ordinary if r['state'] == 'pending'],
        'unverified': [r for r in ordinary if r['state'] == 'generated' and r not in usable]}
    result['exclusion_counts'] = {key: len(rows) for key, rows in result['exclusions'].items()}
    result['training_view_policy'] = 'Only generated episodes with retained quality and passed independent audits; aborted requires observed withdrawal, otherwise it is a non-designed failure.'
    return result


def write_tables(attempt, views):
    root = Path(attempt) / 'views'
    root.mkdir()
    for key, rows in {**views['views'], **views['exclusions']}.items():
        save_json(root / f'{key}.json', rows)
        columns = ('episode_id', 'family_id', 'skeleton_id', 'intent', 'mode', 'path', 'state', 'reason', 'task_result')
        with (root / f'{key}.csv').open('x', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, columns, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)


def final_statistics(descriptors, records, attempt=None):
    records = [r for r in records if not r.get('diagnostic_only', False)]
    regular = [r for r in records if not r.get('aborted', False)]
    generated = [r for r in regular if r['state'] in ('generated', 'generation_error')]
    valid = [r for r in generated if r.get('quality_valid') and r.get('audit_passed')]
    skeletons = {d['skeleton_id']: d for d in descriptors if d['subset'] == 'regular'}
    by_skeleton = {sid: [r for r in regular if r['skeleton_id'] == sid] for sid in skeletons}
    by_intent = {}
    for intent in INTENTS:
        chosen = [rows for sid, rows in by_skeleton.items() if skeletons[sid]['base_intent'] == intent]
        episodes = [r for r in generated if r['intent'] == intent]
        valid_episodes = [r for r in valid if r['intent'] == intent]
        successes = sum(len(rows) == 2 and all(r['state'] == 'generated' and r['task_result'] == 'success'
                        and r['quality_valid'] and r['audit_passed'] for r in rows) for rows in chosen)
        rejected = [rows[0] for rows in chosen if rows and rows[0]['state'] == 'infeasible']
        reasons = Counter(r['reason'] for r in rejected)
        failures = [r for r in valid_episodes if r['task_result'] == 'failure']
        failed_conditions = Counter(f'{g["role"]}:{name}' for r in failures for g in r['groups'].values()
                                    for name, value in g['result']['conditions'].items() if value is False)
        failed_agent_conditions = Counter()
        if attempt is not None:
            for row in failures:
                labels = read_json(Path(attempt) / row['path'] / 'labels.json')
                for agent in labels['agents'].values():
                    failed_agent_conditions.update(f'{agent["assigned"]["execution_method"]}:{name}'
                        for name, value in agent['result']['conditions'].items() if value is False)
        group_timing = [g['coordination']['classification'] == r['mode'] for r in valid_episodes for g in r['groups'].values()]
        by_intent[intent] = {
            'registered_skeletons': len(chosen), 'successful_pairs': successes,
            'skeleton_success_fraction': successes / len(chosen) if chosen else None,
            'rejected_skeletons': len(rejected), 'final_rejection_categories': dict(reasons),
            'rejection_details': [{'skeleton_id': r['skeleton_id'], 'history': r['geometry_attempts']} for r in rejected],
            'generated_episodes': len(episodes), 'retained_valid_episodes': len(valid_episodes),
            'retained_approach_mode': dict(Counter(r['approach_mode'] for r in valid_episodes)),
            'retained_group_count': dict(Counter(str(r['group_count']) for r in valid_episodes)),
            'non_designed_task_failures': len(failures),
            'non_designed_failure_fraction': len(failures) / len(valid_episodes) if valid_episodes else None,
            'failed_group_conditions': dict(failed_conditions),
            'failed_agent_conditions': dict(failed_agent_conditions),
            'timing_groups': len(group_timing), 'timing_group_matches': sum(group_timing),
            'timing_group_agreement_fraction': sum(group_timing) / len(group_timing) if group_timing else None,
            'simulation_wall_seconds': distribution([r['simulation_wall_s'] for r in episodes]),
            'simulated_duration_seconds': distribution([r['duration_s'] for r in episodes])}
    roles = sorted({g['execution_method'] for d in skeletons.values() for g in d['task_groups']})
    role_diagnostics = {}
    for role in roles:
        containing = [sid for sid, d in skeletons.items() if any(g['execution_method'] == role for g in d['task_groups'])]
        rejected = sum(bool(by_skeleton[sid]) and by_skeleton[sid][0]['state'] == 'infeasible' for sid in containing)
        groups = [(r, g) for r in generated for g in r['groups'].values() if g['execution_method'] == role]
        role_diagnostics[role] = {
            'registered_skeletons_containing_role': len(containing), 'rejected_skeletons_containing_role': rejected,
            'rejection_fraction_for_skeletons_containing_role': rejected / len(containing) if containing else None,
            'rejection_denominator_note': 'A whole-episode rejection can be caused by another group or a cross-group conflict; this is not an isolated planner infeasibility rate.',
            'multi_direction_last_100m_heading_span_deg': distribution([g['approach_span_deg'] for r, g in groups if r['approach_mode'] == 'multi_direction']),
            'formation_split_count_distribution': dict(Counter(str(g['formation_split_count']) for _, g in groups))}
    audits = [r['audit'] for r in records if 'audit' in r]
    truncations = [check for r in records for check in r.get('truncation', {}).values()]
    return {'by_intent': by_intent, 'role_diagnostics': role_diagnostics,
            'public_sampling_diagnostics': diagnostic_summary(descriptors, records),
            'audit': {'episodes': len(audits), 'region_differences': sum(a['region_difference_count'] for a in audits),
                      'target_differences': sum(a['target_difference_count'] for a in audits),
                      'event_or_metric_differences': sum(a['event_or_metric_difference_count'] for a in audits),
                      'uncovered_conditions': sum(len(a['uncovered_conditions']) for a in audits)},
            'truncation': dict(Counter(c['status'] for c in truncations)),
            'abort_records': [r for r in records if r.get('aborted', False)]}
