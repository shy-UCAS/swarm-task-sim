"""Read-only R0 audit of the frozen M3 tuning cohort; never runs a simulation.

Writes a new external audit attempt and atomic gate/state files. A zero-known
motion stratum is BLOCKED under the new all-pattern gate, even though the
original tiers function marks it inapplicable. No historical rule is changed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from swarm_sim.fast_dynamics.calibration import paired_metrics, aggregate_pairs, tuning_tasks
from scripts.tune_fast_dynamics_m3 import tiers, SPLIT_SHA

BASE = '81f804a969192790d89100528e3f802bc06446b1'
CONFIG_SHA = '94822513045c434dc2f713070728f1f99d18bcbea3933f8f092b85c5e4d78193'
BRANCH = 'fe/m3-r3-p2-candidate'
DATA = PROJECT.parents[1] / 'SwarmData'
TUNING = DATA / 'fast_dynamics/m3/calibration_20261013/attempt_03_closeout/tuning'
BASELINE = DATA / 'fast_dynamics/m3/calibration_20261013/attempt_02_resume/default_baseline'
REPORT = PROJECT / 'docs/v07/evidence/m3_r3'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    temp.replace(path)


def required_metric_availability(pairs):
    """Do not replace an unmeasurable per-pattern rate with 0, 1, or aggregate."""
    by_pattern = {p: aggregate_pairs([r for r in pairs if r['flight_pattern'] == p])
                  for p in sorted({r['flight_pattern'] for r in pairs})}
    absent = []
    for pattern, values in by_pattern.items():
        for channel in ('truth', 'observation'):
            rate = values['motion_reference_known'][channel]
            if rate['total'] == 0 or rate['all_task_rate'] is None:
                absent.append(dict(metric=f'{channel}.motion.{pattern}', pattern=pattern,
                    tasks=values['tasks'], reference_known=rate['total'], rate=None,
                    mission_ids=sorted(r['mission_id'] for r in pairs if r['flight_pattern'] == pattern)))
    return by_pattern, absent


def gate_status(checks, unavailable):
    if any(v is False for v in checks.values()):
        return 'FAIL'
    if unavailable or any(v is None for v in checks.values()):
        return 'BLOCKED'
    return 'PASS'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    allowed_output = (DATA / 'fast_dynamics/m3').resolve()
    if not out.is_relative_to(allowed_output) or out.exists():
        raise ValueError('require a NEW external M3 audit attempt')
    if (REPORT / 'R0/gate.json').exists():
        raise ValueError('existing stage gate: inspect it; do not overwrite or automatically resume')
    git = lambda *a: subprocess.check_output(['git', *a], cwd=PROJECT, text=True).strip()
    head, branch = git('rev-parse', 'HEAD'), git('branch', '--show-current')
    if head != BASE or branch != BRANCH:
        raise ValueError('unexpected candidate baseline/branch')
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    inventory, problems, records, pairs = {}, [], [], []
    def bind(path, expected=None):
        path = Path(path).resolve()
        actual = digest(path)
        key = str(path)
        if key in inventory and inventory[key]['sha256'] != actual:
            raise ValueError('input changed during audit: ' + key)
        inventory[key] = dict(path=key, sha256=actual, bytes=path.stat().st_size)
        if expected is not None and actual != expected:
            raise ValueError('historical hash mismatch: ' + key)
        return actual
    def load(path, expected=None):
        bind(path, expected)
        return read(path)
    split_index = load(PROJECT / 'verification/fast_dynamics_m3/r2_split_index.json')
    split = load(split_index['external_split'], SPLIT_SHA)
    allowed = {r['mission_id']: r for r in tuning_tasks(split)}
    freeze = load(TUNING / 'freeze_record.json')
    config = load(TUNING / 'frozen_m3_v1.json', CONFIG_SHA)
    load(PROJECT / 'configs/fast_dynamics/m3_r2_20261013_v1.json', CONFIG_SHA)
    evaluation = load(TUNING / 'config_020_full/evaluation.json')
    old_baseline = load(BASELINE / 'baseline.json')
    registration = load(TUNING / 'registration.json')
    names = sorted(r['mission_id'] for r in evaluation['rows'])
    if len(names) != 282 or len(set(names)) != 282 or set(names) - allowed.keys():
        raise ValueError('frozen cohort is not 282 unique allowed tuning tasks')
    if set(names) != {r['mission_id'] for r in old_baseline['rows']}:
        raise ValueError('frozen cohort and baseline identities differ')
    for i, name in enumerate(names, 1):
        row = allowed[name]
        record = dict(mission_id=name, family_id=row['family_id'], flight_pattern=row['flight_pattern'])
        try:
            left = load(BASELINE / name / 'sitl_r2.json')
            right = load(TUNING / 'config_020_full' / name / 'fast.json')
            task_path = BASELINE / name / 'input_task.json'
            task = load(task_path, row['task_sha256'])
            if any(x['family_id'] != row['family_id'] or x['mission_id'] != name for x in (left, right)):
                raise ValueError('SITL/r2/split identity mismatch')
            if task['family_id'] != row['family_id'] or task['task_id'] != name:
                raise ValueError('input task identity mismatch')
            if left['input_task_sha256'] != row['task_sha256']:
                raise ValueError('reference input digest mismatch')
            analysis = Path(left['source']['analysis']).resolve()
            reference_root = Path(split['source_roots']['r2']).resolve()
            parent = reference_root / 'shards' / f"shard_{row['shard_id']:02d}" / 'attempts'
            if not analysis.is_relative_to(parent) or analysis.name != 'analysis':
                raise ValueError('reference is outside its tuning shard attempt')
            for path, expected in left['evidence_sha256'].items():
                path = Path(path).resolve()
                input_original = (reference_root / 'bundle' / row['task']).resolve()
                if not path.is_relative_to(analysis.parent) and path != input_original:
                    raise ValueError('reference binding escapes allowed tuning attempt')
                bind(path, expected)
            manifest = load(analysis / 'manifest.json')
            if manifest['family_id'] != row['family_id'] or manifest['run_id'] != left['source']['run_id']:
                raise ValueError('reference manifest identity mismatch')
            ra = TUNING / 'config_020_full' / name / 'run/analysis'
            rm = load(ra / 'manifest.json')
            for filename, expected in rm['artifact_sha256'].items():
                p = (ra / filename).resolve()
                if not p.is_relative_to(ra.resolve()):
                    raise ValueError('r2 artifact path escape')
                bind(p, expected)
            source = load(ra / 'source.json')
            if source['config'] != config or rm['family_id'] != row['family_id'] or rm['run_id'] != name:
                raise ValueError('r2 frozen config/manifest identity mismatch')
            if row['task_sha256'] not in source['input_sha256'].values():
                raise ValueError('r2 source did not bind the original input task')
            paired = paired_metrics(left, right)
            paired.update(intent=row['intent'], flight_pattern=row['flight_pattern'])
            stored = load(TUNING / 'config_020_full' / name / 'paired.json')
            if paired != stored:
                raise ValueError('recomputed original paired_metrics differs from frozen paired.json')
            pairs.append(paired)
            record.update(status='VERIFIED', task_path=str(task_path), task_sha256=row['task_sha256'],
                          reference_run_id=left['source']['run_id'], reference_analysis=str(analysis),
                          r2_analysis=str(ra), motion_slots=paired['motion_slots'])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            record.update(status='BLOCKED', error=str(exc))
            problems.append(record)
        records.append(record)
        if i % 25 == 0 or i == len(names):
            print(json.dumps(dict(audited=i, total=len(names), comparable=len(pairs), errors=len(problems))), flush=True)
    aggregate = aggregate_pairs(pairs)
    original = tiers(pairs, 282)
    by_pattern, absent = required_metric_availability(pairs)
    for rel in ('swarm_sim/fast_dynamics/calibration.py', 'scripts/tune_fast_dynamics_m3.py',
                'swarm_sim/fast_dynamics/route_tracker.py', 'swarm_sim/fast_dynamics/contracts.py',
                'tests/test_fast_dynamics_tracking.py', 'tests/test_fast_dynamics_m3_postfreeze.py',
                'docs/fast_dynamics_m3_method.md', 'docs/fast_dynamics_m3_closeout.md', '.conda-env'):
        bind(PROJECT / rel)
    request = Path(r'C:\Users\shy\.codex\attachments\6a8c1cbe-214d-4971-a32d-1cc7e65d922c\Pasted text.txt')
    bind(request)
    values = dict(total_duration_abs_relative_median=aggregate['duration_absolute_relative_error']['task']['median'],
        total_duration_abs_relative_p95=aggregate['duration_absolute_relative_error']['task']['p95'],
        observe_duration_abs_relative_median=aggregate['phase_absolute_relative_error'].get('p01_observe', {}).get('task', {}).get('median'),
        turn_min_speed_abs_difference_median=aggregate['turn_minimum_speed_m_s']['absolute_difference']['task']['median'],
        lateral_task_p95_median_m=aggregate['lateral_task_p95_m']['task']['median'])
    unavailable = absent + [dict(metric=k, reason='missing numerical baseline') for k,v in values.items() if v is None or not math.isfinite(v)]
    checks = dict(exact_base_and_branch=head == BASE and branch == BRANCH, cohort_282=len(names)==282,
        all_282_identity_hash_and_pair_verified=len(pairs)==282 and not problems,
        frozen_aggregate_reproduced=aggregate == freeze['tiers']['aggregate'],
        original_m3_hard_pass=original['hard']['passed'],
        required_metric_availability=None if unavailable else True)
    # Data/identity unavailability is BLOCKED, rather than algorithmic FAIL.
    if problems:
        checks['all_282_identity_hash_and_pair_verified'] = None
    stages = dict(
        R1=dict(input='D0b fixed seven probes at 432c6de0bfef60e066ae952a1aed0dc83c299072',
                budget_s=None, budget_note='Not finalized: R0 prerequisite blocked; no R1 execution authorized by gate'),
        R2=dict(full_mission_ids=names, functionality_mission_ids=registration['subset']['mission_ids'], wall_limit_s=28800),
        R3=dict(p2_commit='fa7518b7fa850771c9d863b23d8893b27a343d5f', budget_s=None),
        R4=dict(input='FE-INT fixed 30 plus P2 recovered 8, deduplicate with provenance',
                modes=['synchronous', 'sequential'], wall_limit_s=21600,
                registration_complete=False, reason='Stopped on R0 missing mandatory motion metric before locking downstream inputs'))
    plan = dict(schema='m3_r3_r0_validation_plan_v1', status='BLOCKED' if unavailable or problems else 'INCOMPLETE',
        code_commit=head, branch=branch, worktree=str(PROJECT.parent), request=str(request),
        input_files=list(inventory.values()), tuning_tasks=records, expected_tasks=282, verified_tasks=len(pairs),
        original_hard_gates=original['hard'], r2_baseline=values, r2_aggregate=aggregate,
        by_pattern=by_pattern, comparison=dict(float_tolerance=1e-9, hard='original tiers(pairs,282).hard.passed',
            success_minimum=.995, observation_success_minimum=.995, motion_overall_minimum=.98,
            motion_each_pattern_minimum=.95, motion_denominator='original SITL reference-known task identities',
            non_regression={k: dict(maximum=v, tolerance=1e-9) for k,v in values.items()},
            missing_rule='BLOCKED; do not turn a zero-denominator per-pattern metric into PASS',
            ambiguity='Original tiers marks zero-reference-known patterns inapplicable. New request requires all per-pattern thresholds and BLOCKED on missing metrics. Human resolution required.'),
        future_stages=stages, downstream_inputs_fully_locked=False,
        unavailable_required_metrics=unavailable, input_problems=problems,
        no_simulation_executed=True, no_internal_holdout_run=True, m2_02b_accessed=False)
    # This first audit implementation must not unlock R1 with an incomplete plan.
    checks['downstream_input_registration_complete'] = None
    status = gate_status(checks, unavailable)
    import numpy, shapely
    environment = dict(python=platform.python_version(), numpy=numpy.__version__, shapely=shapely.__version__, executable=sys.executable)
    audit = dict(status=status, checks=checks, environment=environment, metrics=values,
        unavailable_required_metrics=unavailable, input_problems=problems, original_tiers=original,
        elapsed_wall_s=time.monotonic()-started, audited_input_files=len(inventory),
        later_stages_executed=False, audit_script_sha256=digest(__file__))
    atomic(out / 'audit.json', audit)
    atomic(out / 'tuning_tasks.json', records)
    atomic(out / 'input_manifest.json', list(inventory.values()))
    atomic(REPORT / 'R0_validation_plan.json', plan)
    plan_sha = digest(REPORT / 'R0_validation_plan.json')
    gate = dict(stage='R0', status=status, input_sha256=plan_sha, code_commit=head,
        required_checks=checks, metrics=values, evidence_paths=[str(out / 'audit.json'), str(out / 'tuning_tasks.json'), str(out / 'input_manifest.json')],
        evidence_sha256={str(out / f):digest(out/f) for f in ('audit.json','tuning_tasks.json','input_manifest.json')},
        next_stage=None, blockers=unavailable + problems,
        interpretation='Missing mandatory per-pattern rate; original historical hard PASS is retained, not rewritten.',
        plan_frozen_for_later_execution=False)
    atomic(REPORT / 'R0/gate.json', gate)
    atomic(REPORT / 'pipeline_state.json', dict(schema='m3_r3_pipeline_v1', status=status, last_pass_stage=None,
        current_stage='R0', next_stage=None, plan_sha256=plan_sha, code_commit=head, external_attempt=str(out),
        stages={'R0':dict(status=status, executed=True, gate=str(REPORT/'R0/gate.json')),
                **{s:dict(status='BLOCKED', executed=False, reason='R0_NOT_PASS') for s in ('R1','R2','R3','R4')}}))
    print(json.dumps(dict(status=status, verified=len(pairs), missing_metrics=len(unavailable), input_problems=len(problems),
                         metrics=values, evidence=str(out)), ensure_ascii=False), flush=True)
    return 0 if status == 'PASS' else 2

if __name__ == '__main__':
    raise SystemExit(main())
