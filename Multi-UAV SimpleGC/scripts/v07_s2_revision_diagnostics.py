"""Read-only revision matrices; one skeleton belongs to exactly one size bin.

Does not import the generator or run/relabel any trajectory. Shortcut probes
are deliberately separate and run only after the final cross-negation stage.
"""
import argparse
import ast
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

INTENTS = ('transit', 'reconnaissance', 'monitoring', 'feint', 'penetration')
NAMES = dict(zip(INTENTS, ('过境', '侦察', '游弋监视', '佯动', '突防')))
DIMENSIONS = {'approach_mode': ('same_direction', 'multi_direction'),
              'facility_count': ('1', '2', '3'), 'group_count': ('1', '2', '3'),
              'maximum_group_size': ('2–3', '4–6', '≥7')}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def successful_pair(rows):
    return (len(rows) == 2 and {r['mode'] for r in rows} == {'synchronous', 'sequential'}
            and all(r['state'] == 'generated' and r['task_result'] == 'success'
                    and r['quality_valid'] and r['audit_passed'] for r in rows))


def reasons_from_detail(detail):
    start = detail.find('{')
    if start < 0:
        return Counter({detail: 1})
    try:
        value = ast.literal_eval(detail[start:])
    except (SyntaxError, ValueError):
        return Counter({detail: 1})
    if not isinstance(value, dict) or any(not isinstance(v, int) or v < 0 for v in value.values()):
        return Counter({detail: 1})
    result = Counter()
    for key, count in value.items():
        for reason, number in reasons_from_detail(str(key)).items():
            result[reason] += count * number
    return result


def dimensions(descriptor, facilities):
    maximum = max(len(g['members']) for g in descriptor['task_groups'])
    if maximum < 2:
        raise ValueError('Every registered group must have at least two members')
    return {'approach_mode': descriptor['common_draw']['approach_mode'],
            'facility_count': str(facilities[descriptor['family_id']]),
            'group_count': str(len(descriptor['task_groups'])),
            'maximum_group_size': '2–3' if maximum <= 3 else '4–6' if maximum <= 6 else '≥7'}


def collect(attempt):
    attempt = Path(attempt).resolve()
    registration = read(attempt / 'registration.json')
    infra = Path(registration['source_attempt'])
    paths = [attempt / 'registration.json', attempt / 'episode_records.json',
             infra / 'registration.json', infra / 'private_skeleton_descriptors.json']
    hashes = {str(p): sha(p) for p in paths}
    descriptors = [d for d in read(paths[-1]) if d['subset'] == 'regular' and not d.get('diagnostic_only')]
    records = [r for r in read(attempt / 'episode_records.json') if not r.get('aborted') and not r.get('diagnostic_only')]
    if len(descriptors) != 60 or len(records) != 120 or len({r['episode_id'] for r in records}) != 120:
        raise ValueError('Expected exactly 60 skeletons and 120 distinct regular requests')
    facilities = {r['family_id']: r['facility_count'] for r in read(infra / 'registration.json')['selected']}
    grouped = defaultdict(list)
    for row in records:
        grouped[row['skeleton_id']].append(row)
    skeletons = []
    for descriptor in descriptors:
        sid = descriptor['skeleton_id']
        rows = grouped[sid]
        success = successful_pair(rows)
        rejection = next((r for r in rows if r['state'] == 'infeasible'), None)
        category = None if success else rejection['reason'] if rejection else (
            'generation_error' if any(r.get('quality_valid') is False for r in rows) else 'non_successful_pair')
        reasons, evidence = Counter(), []
        for entry in rejection.get('geometry_attempts', []) if rejection else []:
            path = attempt / sid / f"geometry_{entry['geometry_variant']:02d}" / 'planning_rejection.json'
            saved = read(path)
            if saved != entry:
                raise ValueError(f'Saved rejection and record disagree: {path}')
            reasons.update(reasons_from_detail(entry['detail']))
            evidence.append({'path': str(path), 'sha256': sha(path), 'saved': saved})
        search_path = attempt / sid / 'candidate_search.json'
        if rejection and search_path.exists():
            search = read(search_path)
            # Empty pools already quote these counts in geometry_00; avoid
            # double counting. Calibration failures are a separate later stage.
            if not search.get('actual_single_agent_calibration_rounds', 0):
                reasons.clear()
            reasons.update(search['rejection_reasons'])
            evidence.append({'path': str(search_path), 'sha256': sha(search_path),
                             'scope': 'geometry/nominal-spacing/115-percent candidate rejection counts',
                             'attempted_candidates': search['attempted_candidates']})
        skeletons.append({'skeleton_id': sid, 'family_id': descriptor['family_id'],
                          'intent': descriptor['base_intent'], **dimensions(descriptor, facilities),
                          'success': success, 'failure_category': category,
                          'candidate_reason_counts': dict(reasons), 'rejection_evidence': evidence})
    matrices = {}
    for dimension, values in DIMENSIONS.items():
        cells = []
        for intent in INTENTS:
            for value in values:
                selected = [s for s in skeletons if s['intent'] == intent and s[dimension] == value]
                successful = sum(s['success'] for s in selected)
                reasons = Counter()
                for row in selected:
                    if not row['success']:
                        reasons.update(row['candidate_reason_counts'])
                cells.append({'intent': intent, 'dimension': dimension, 'value': value,
                              'registered': len(selected), 'successful': successful,
                              'fraction': successful / len(selected) if selected else None,
                              'skeleton_ids': [s['skeleton_id'] for s in selected],
                              'failure_categories': dict(Counter(s['failure_category'] for s in selected if not s['success'])),
                              'candidate_reason_counts': dict(reasons.most_common())})
        if sum(r['registered'] for r in cells) != 60:
            raise ValueError(f'{dimension} double-counts or loses skeletons')
        matrices[dimension] = cells
    if hashes != {str(p): sha(p) for p in paths}:
        raise ValueError('Source evidence changed during read-only analysis')
    return {'source_attempt': str(attempt), 'source_commit': registration['commit'],
            'source_sha256': hashes, 'sources_unchanged': True, 'simulation_runs': 0,
            'size_definition': 'maximum merged task-group member count in each skeleton',
            'skeletons': skeletons, 'matrices': matrices,
            'zero_success_combinations': [c for rows in matrices.values() for c in rows if c['registered'] and not c['successful']]}


def render(data, output, stage):
    labels = {'approach_mode': '逼近方式', 'facility_count': '设施数',
              'group_count': '合并后任务组数', 'maximum_group_size': '最大任务组成员数'}
    lines = [f'## {stage}：四维骨架成功率', '', f"来源：`{data['source_attempt']}`，生成提交 `{data['source_commit']}`。",
             '成功要求两种时序均生成、任务成功、质量有效且独立审计通过。每个维度的总分母均为 60 个骨架；规模按最大组分档，各档互斥，不跨档重复。未登记组合不计为零成功。', '']
    for dimension, cells in data['matrices'].items():
        lines += [f'### 意图 × {labels[dimension]}', '', '| 意图 | 条件 | 成功/登记 | 成功率 |', '|---|---|---|---|']
        for c in cells:
            ratio = '未登记' if c['fraction'] is None else f"{100*c['fraction']:.2f}%"
            lines.append(f"| {NAMES[c['intent']]} | {c['value']} | {c['successful']}/{c['registered']} | {ratio} |")
        lines.append('')
    lines += ['### 已登记但零成功的组合', '', '以下候选原因来自保存的拒绝记录；次数是候选计数，不能解释为独立骨架数或数学无解证明。', '']
    for c in data['zero_success_combinations']:
        reasons = '；'.join(f'`{k}` × {v}' for k, v in list(c['candidate_reason_counts'].items())[:3]) or '无规划拒绝；见质量/结果类别'
        lines.append(f"- {NAMES[c['intent']]} × {labels[c['dimension']]}={c['value']}：0/{c['registered']}；最终类别 `{json.dumps(c['failure_categories'], ensure_ascii=False)}`；主要原因：{reasons}。")
    lines += ['', f"[逐骨架证据与来源哈希](<{(output/'diagnostics.json').as_posix()}>)。", '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--stage', choices=('修订前', '修订后'), required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Use a new evidence directory')
    data = collect(args.attempt)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'diagnostics.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    marker = f'<!-- revision-matrices:{args.stage} -->'
    report = args.report.read_text(encoding='utf-8')
    if marker in report:
        raise ValueError('This stage is already recorded; do not silently replace it')
    args.report.write_text(report+'\n'+marker+'\n'+render(data, args.output.resolve(), args.stage), encoding='utf-8', newline='\n')
    print(json.dumps({'successful_pairs': sum(s['success'] for s in data['skeletons']),
                      'zero_success_cells': len(data['zero_success_combinations']),
                      'matrix_denominators': {k: sum(c['registered'] for c in v) for k, v in data['matrices'].items()}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
