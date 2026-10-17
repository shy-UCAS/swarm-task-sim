"""D0b fixed three-arm solo experiment; never edit production or D0 evidence."""
import argparse
import copy
from contextlib import nullcontext
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import traceback
from unittest.mock import patch

import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from scripts import probe_v07_fe_corner_cap as d0
from scripts.qc_v07_fe_corner_dwell import OUT, read, save, sha, digest, require, distribution
from task_v07.execution import execute, frozen_config
from task_v07.expansion.contracts import P0ContractError
from task_v07.expansion.geometry_checks import exact_frame_geometry
from task_v07.expansion.pipeline import exclusion_policy
from swarm_sim.fast_dynamics.route_tracker import RouteTracker, _Primitive, _bezier, _curvature_bounds

ORIGINAL_BUILD = RouteTracker._build
BASE = 'd595b10afc54eb182f0f395fba4c1c4156004445'
MANIFEST = OUT / 'D0b_source_manifest.json'
MARKER = 'EXPERIMENTAL_REFERENCE_NOT_FROZEN'
BUILD_AUDIT = {}


class IntegrityError(RuntimeError):
    pass


def verify_protected():
    manifest = read(MANIFEST)
    for name, expected in manifest['protected_sha256'].items():
        if sha(name) != expected:
            raise IntegrityError('Protected file changed: ' + name)
    if sha(OUT / 'D0_probe_selection.json') != manifest['selection_sha256']:
        raise IntegrityError('D0 selection changed')
    return manifest


def validate_formula():
    rows = []
    u = np.array([1., 0.])
    for degrees in (.55, 2.6, 11.25, 45., 90., 174.9):
        angle = math.radians(degrees)
        w = np.array([math.cos(angle), math.sin(angle)])
        controls = np.array([-u, -2*u/3, -u/3, w/3, 2*w/3, w])
        numeric = float(np.linalg.norm(_bezier(controls, np.linspace(0, 1, 2001)), axis=1).min())
        analytic = (23./48.) * math.sin(angle/2.)
        tolerance = max(1e-12, 1e-9 * abs(analytic))
        require(abs(numeric-analytic) <= tolerance, 'B2 formula verification failed')
        rows.append(dict(angle_deg=degrees, numeric=numeric, analytic=analytic,
                         error=abs(numeric-analytic), tolerance=tolerance))
    return rows


def cut_distance(gate, angle, before, after):
    epsilon = .5 * gate
    m = (23./48.) * math.sin(angle/2.)
    return min(epsilon/m, .45*before, .45*after)


def _build_core(self, adaptive):
    # Literal original construction, with exactly one conditional d definition.
    if self.complete:
        return
    lengths = np.linalg.norm(np.diff(self.points[:, :2], axis=0), axis=1)
    if np.any(lengths <= 0):
        raise ValueError('zero-length raw EN legs must be cleaned by the task compiler')
    directions = np.diff(self.points[:, :2], axis=0)/lengths[:, None]
    self.short_continuations = frozenset(i for i in range(1, len(self.points)-1)
        if min(lengths[i-1], lengths[i]) < self.reference.tracking_tube_m
        and float(directions[i-1] @ directions[i]) >= 1.-1e-14)
    self.gates = np.array([min(.5, .2*min(lengths[max(0, i-1):min(len(lengths), i+1)]))
                           for i in range(len(self.points))])
    bends, stops = {}, set()
    for i in range(1, len(self.points)-1):
        u, w = directions[i-1:i+1]
        angle = math.acos(float(np.clip(u@w, -1, 1)))
        if angle >= math.radians(175):
            stops.add(i)
        elif angle > 1e-8:
            if adaptive:
                d = cut_distance(self.gates[i], angle, lengths[i-1], lengths[i])
            else:
                d = min(self.reference.corner_cut_max_m, self.reference.corner_leg_fraction*lengths[i-1],
                        self.reference.corner_leg_fraction*lengths[i])
            v = self.points[i, :2]
            e, x = v-d*u, v+d*w
            ctrl = [e, e+d*u/3, e+2*d*u/3, x-2*d*w/3, x-d*w/3, x]
            curve = _Primitive(e, x, control=ctrl, node_index=i)
            horizon = self.controller.velocity_response_time_s + self.profile.response_time_s
            k, ks = _curvature_bounds(curve.derivatives)
            curve.cap = min(self.speed, d/horizon,
                            math.sqrt(self.profile.max_accel_xy_m_s2/(2*k)),
                            (self.profile.max_jerk_m_s3/(2*(k*k+ks)))**(1/3))
            bends[i] = curve
    for k in range(len(lengths)):
        start = bends[k].end if k in bends else self.points[k, :2]
        end = bends[k+1].start if k+1 in bends else self.points[k+1, :2]
        self.primitives.append(_Primitive(start, end, stop=k+1 in stops, node_index=k+1))
        if k+1 in bends:
            self.primitives.append(bends[k+1])
    for i, primitive in enumerate(self.primitives):
        if primitive.control is None:
            primitive.exit_cap = (0. if primitive.stop or i == len(self.primitives)-1 else
                                  self.primitives[i+1].cap if self.primitives[i+1].control is not None else self.speed)
        else:
            primitive.exit_cap = primitive.cap


def build_original_equivalent(self):
    _build_core(self, False)


def structure(tracker):
    return [(q.control is not None, q.stop, q.node_index) for q in tracker.primitives]


def validate_geometry(tracker, original):
    require(type(tracker) is RouteTracker, 'P0 RouteTracker type changed')
    require(structure(tracker) == structure(original), 'B2 primitive structure changed')
    require(np.array_equal(tracker.points, original.points), 'B2 raw route changed')
    require(np.array_equal(tracker.gates, original.gates), 'B2 gates changed')
    require(tracker.short_continuations == original.short_continuations, 'B2 short continuations changed')
    lengths = np.linalg.norm(np.diff(tracker.points[:, :2], axis=0), axis=1)
    cuts = {}; rows = []
    for q in tracker.primitives:
        require(math.isfinite(q.length) and q.length > 0, 'B2 nonpositive primitive length')
        if q.control is None:
            continue
        i = q.node_index; v = tracker.points[i, :2]
        u = (v-tracker.points[i-1, :2])/lengths[i-1]
        w = (tracker.points[i+1, :2]-v)/lengths[i]
        angle = math.acos(float(np.clip(u@w, -1, 1)))
        require(1e-8 < angle < math.radians(175), 'B2 curve node is not ordinary curve')
        epsilon = .5 * tracker.gates[i]
        distance = q.project(v)[1]
        require(distance <= epsilon+1e-9, 'B2 nearest vertex distance exceeds epsilon')
        d = cut_distance(tracker.gates[i], angle, lengths[i-1], lengths[i])
        cuts[i] = d
        rows.append(dict(node_index=i, angle_deg=math.degrees(angle), d_m=d, epsilon_m=epsilon,
                         curve_vertex_nearest_m=distance, curve_length_m=q.length))
    margins = [float(lengths[i]-cuts.get(i, 0.)-cuts.get(i+1, 0.)) for i in range(len(lengths))]
    require(all(x > 0 for x in margins), 'B2 adjacent curves overlap')
    return dict(status='PASS', curves=rows, residual_raw_leg_lengths_m=margins,
                structure_unchanged=True, gates_unchanged=True, stop_flags_unchanged=True)


def adaptive_build(self):
    original = copy.copy(self)
    original.primitives = []
    ORIGINAL_BUILD(original)
    _build_core(self, True)
    BUILD_AUDIT[id(self)] = validate_geometry(self, original)


def replay_with_capture(group, agent, arm):
    # Same committed-object method as D0: read-only return tracing, not event wrappers.
    captured = []; code = RouteTracker.__init__.__code__; previous = sys.gettrace()
    def trace(frame, event, arg):
        if event == 'call' and frame.f_code is code:
            frame.f_trace_lines = False
            return on_return
        return None
    def on_return(frame, event, arg):
        if event == 'return':
            captured.append(frame.f_locals['self'])
        return on_return
    require(arm in ('A', 'B1', 'B2'), 'Unknown arm')
    context = nullcontext() if arm == 'A' else patch.object(
        RouteTracker, '_build', d0.experimental_build if arm == 'B1' else adaptive_build)
    try:
        with context:
            sys.settrace(trace)
            run = execute(group, {a: 0. for a in group['members']}, only_agent=agent)
    finally:
        sys.settrace(previous)
    require(RouteTracker._build is ORIGINAL_BUILD, 'Patch failed to restore')
    points = np.asarray(group['references'][agent]['points_enu_m'])
    intermediate = group['references'][agent].get('intermediate_dwell')
    if intermediate:
        n = intermediate['waypoint_index']
        require(len(captured) in (2, 3), 'Unexpected dwell tracker construction sequence')
        require(np.array_equal(captured[0].points, points) and not captured[0].witnesses,
                'Unexpected unused full-route tracker activity')
        active = [(0, captured[1])]
        require(np.array_equal(captured[1].points, points[:n+1]), 'Wrong approach route')
        if len(captured) == 3:
            require(np.array_equal(captured[2].points, points[n:]), 'Wrong departure route')
            active.append((n, captured[2]))
    else:
        require(len(captured) == 1 and np.array_equal(captured[0].points, points), 'Unexpected tracker sequence')
        active = [(0, captured[0])]
    snapshots = []; witnesses = []
    for offset, tracker in active:
        snapshots.append(dict(original_node_offset=offset, geometry=d0.tracker_geometry(tracker),
                              diagnostics=tracker.diagnostics, curves=curve_facts(tracker, arm, offset),
                              B2_geometry_check=BUILD_AUDIT.get(id(tracker)),
                              primitive_caps=[dict(cap=q.cap if math.isfinite(q.cap) else None,
                                                   exit_cap=q.exit_cap) for q in tracker.primitives]))
        for event in tracker.witnesses:
            if offset and event['node_index'] == 0:
                continue
            witnesses.append({**event, 'node_index': offset+event['node_index']})
    return run, snapshots, witnesses


def curve_facts(tracker, arm, offset):
    rows = []; lengths = np.linalg.norm(np.diff(tracker.points[:, :2], axis=0), axis=1)
    for index, q in enumerate(tracker.primitives):
        if q.control is None:
            continue
        i = q.node_index; u = tracker.points[i, :2]-tracker.points[i-1, :2]
        w = tracker.points[i+1, :2]-tracker.points[i, :2]
        angle = math.acos(float(np.clip((u/lengths[i-1])@(w/lengths[i]), -1, 1)))
        old_d = min(tracker.reference.corner_cut_max_m, tracker.reference.corner_leg_fraction*lengths[i-1],
                    tracker.reference.corner_leg_fraction*lengths[i])
        d = cut_distance(tracker.gates[i], angle, lengths[i-1], lengths[i]) if arm == 'B2' else old_d
        k, ks = _curvature_bounds(q.derivatives)
        h = tracker.controller.velocity_response_time_s+tracker.profile.response_time_s
        limits = dict(cruise=tracker.speed, horizon=d/h,
                      acceleration=math.sqrt(tracker.profile.max_accel_xy_m_s2/(2*k)),
                      jerk=(tracker.profile.max_jerk_m_s3/(2*(k*k+ks)))**(1/3))
        active = {key: value for key, value in limits.items() if not (arm == 'B1' and key == 'horizon')}
        require(abs(q.cap-min(active.values())) <= 1e-10, 'Reported curve cap mismatch')
        rows.append(dict(primitive_index=index, node_index=offset+i, angle_deg=math.degrees(angle),
                         original_vertex_enu_m=tracker.points[i].tolist(), d_m=float(d), original_d_m=float(old_d),
                         cap_m_s=q.cap, exit_cap_m_s=q.exit_cap, limits_m_s=limits,
                         removed_limits=['horizon'] if arm == 'B1' else [],
                         dominant_terms=[key for key, value in active.items() if abs(value-q.cap) <= 1e-10],
                         curvature_bound=k, curvature_derivative_bound=ks, curve_length_m=q.length))
    return rows


def trailing_true_count(mask):
    bad = np.flatnonzero(~np.asarray(mask, bool))
    return len(mask)-1-int(bad[-1]) if len(bad) else len(mask)


def stop_diagnostics(run, group, agent):
    radius = group.get('stop_radius_m', group['terminal_radius_m'])
    speed = group.get('stop_speed_m_s', group['terminal_speed_m_s'])
    hold = group.get('stop_hold_s', group['terminal_hold_s'])
    distance = np.linalg.norm(run['p'][:, 0]-group['references'][agent]['points_enu_m'][-1], axis=1)
    velocity = np.linalg.norm(run['v'][:, 0], axis=1)
    released = run['time_us'] >= round((group['initial_settle_s'])*1e6)
    effective = (distance <= radius) & (velocity <= speed) & released
    terminal = (distance <= group['terminal_radius_m']) & (velocity <= group['terminal_speed_m_s']) & released
    count = trailing_true_count(effective); terminal_count = trailing_true_count(terminal)
    return dict(execution_status=run['execution_status'], effective_stop_radius_m=radius,
                effective_stop_speed_m_s=speed, effective_stop_hold_s=hold,
                terminal_radius_m=group['terminal_radius_m'], terminal_speed_m_s=group['terminal_speed_m_s'],
                terminal_hold_s=group['terminal_hold_s'], final_distance_m=float(distance[-1]),
                final_speed_m_s=float(velocity[-1]), effective_final_conditions=bool(effective[-1]),
                effective_hold_frames=count, effective_required_hold_frames=round(hold*10)+1,
                effective_stop_satisfied=count >= round(hold*10)+1,
                terminal_final_conditions=bool(terminal[-1]), terminal_hold_frames=terminal_count,
                terminal_hold_satisfied=terminal_count >= round(group['terminal_hold_s']*10)+1,
                terminal_is_diagnostic_only=True)


def ordered_witnesses(witnesses, node_count):
    ids = [e['node_index'] for e in witnesses if 0 < e['node_index'] < node_count-1]
    expected = list(range(1, node_count-1))
    prefix = 0
    for got, wanted in zip(ids, expected):
        if got != wanted:
            break
        prefix += 1
    return dict(internal_waypoints=len(expected), observed_indices=ids, expected_indices=expected,
                ordered_prefix_count=prefix, all_waypoints_witnessed=ids == expected,
                missing_waypoint_indices=sorted(set(expected)-set(ids)),
                duplicate_waypoint_indices=sorted(x for x in set(ids) if ids.count(x) > 1))


def scene_audit(run, group, scene, agent):
    policy = exclusion_policy(scene, group['role'], group['target_id'], [agent])
    if policy[agent] != group['exclusion_policy'][agent]:
        raise P0ContractError('Saved exclusion policy differs from original role policy')
    frames, facts = exact_frame_geometry(scene, run, targets={agent: group['target_id']}, forbidden_layers=policy)
    details = {}
    for name in ('inside_hard_obstacle', 'outside_world', 'forbidden_region'):
        indices = np.flatnonzero(frames[name][:, 0]); first = int(indices[0]) if len(indices) else None
        details[name] = dict(frame_count=len(indices), first_frame=first,
                             first_time_s=None if first is None else float(run['time_us'][first]/1e6))
    violation = any(x['frame_count'] for x in details.values())
    return dict(violation=violation, classification='NOT_PRODUCTION_ELIGIBLE' if violation else 'NO_SAMPLED_SCENE_VIOLATION',
                evidence_grid_hz=10, continuous_or_multiagent_safety_claim=False,
                exclusion_policy=policy, details=details, original_geometry_facts=facts), frames


def metrics(run, group, agent, scene, snapshots, witnesses, probe):
    result, distances, segments = d0.metrics(run, group, agent, scene, snapshots, witnesses, probe)
    stop = stop_diagnostics(run, group, agent)
    # D0 terminal checks are retained only in stop diagnostics; effective contract is authoritative here.
    checks = {k: v for k, v in result['physical_checks'].items() if k not in ('terminal_position', 'terminal_speed')}
    state = next(s for s in group['initial_states'] if s['agent_id'] == agent)
    checks['initial_pva'] = all(np.array_equal(run[k][0, 0], np.asarray(state[field])) for k, field in (
        ('p', 'position_enu_m'), ('v', 'velocity_enu_m_s'), ('a', 'acceleration_enu_m_s2')))
    checks['effective_stop'] = stop['effective_stop_satisfied']
    order = ordered_witnesses(witnesses, len(group['references'][agent]['points_enu_m']))
    result['tracking'].update(order)
    result['tracking']['classification'] = ('TRACKING_ACCURACY_PRESERVED' if order['all_waypoints_witnessed']
        and distances.max() <= result['tracking']['tracking_tube_m'] else 'TRACKING_ACCURACY_DEGRADED')
    safety, scene_frames = scene_audit(run, group, scene, agent)
    curves = [c for s in snapshots for c in s['curves']]
    result.update(stop_diagnostics=stop, physical_checks=checks, physical_status='PASS' if all(checks.values()) else 'FAIL',
                  scene=safety, curve_summary=dict(curve_count=len(curves),
                  explicit_stop_count=sum(q['stop'] for s in snapshots for q in s['geometry']['primitives']),
                  d_m=distribution(c['d_m'] for c in curves), cap_m_s=distribution(c['cap_m_s'] for c in curves)),
                  production_eligibility='NOT_PRODUCTION_ELIGIBLE' if not all(checks.values()) or safety['violation'] or result['tracking']['classification'] == 'TRACKING_ACCURACY_DEGRADED' else 'EXPERIMENT_ONLY_NOT_APPROVED',
                  original_route_sha256=digest(group['references'][agent]['points_enu_m']),
                  actual_engine_end_s=run['end_us']/1e6)
    return result, distances, segments, scene_frames


def worker(probe_id, arm, destination):
    manifest = verify_protected(); probe = next(p for p in manifest['probes'] if p['probe_id'] == probe_id)
    root = Path(manifest['external_output']); registration = read(root/'registration.json')
    if sha(__file__) != registration['script_sha256']:
        raise IntegrityError('Registered experimental script changed')
    task = read(Path(probe['episode'])/'task.json'); group = copy.deepcopy(task['group_skeletons'][probe['group_id']])
    before = digest(group); destination.mkdir(parents=True, exist_ok=False)
    try:
        run, snapshots, witnesses = replay_with_capture(group, probe['agent_id'], arm)
        if digest(group) != before:
            raise IntegrityError('Execution mutated source input')
        np.savez_compressed(destination/'run.npz', **{k: run[k] for k in ('time_us', 'p', 'v', 'a', 'agent_ids', 'execution_status')})
        result, deviations, segments, scene_frames = metrics(run, group, probe['agent_id'],
            read(Path(probe['episode'])/'public_scene.json'), snapshots, witnesses, probe)
        np.savez_compressed(destination/'tracking_frames.npz', time_us=run['time_us'], distance_m=deviations,
                            nearest_segment_index=segments, **{k: scene_frames[k] for k in (
                            'inside_hard_obstacle', 'outside_world', 'forbidden_region', 'region_all_facilities', 'facility_ids')})
        if arm == 'A':
            episode = Path(probe['episode']); cal = read(episode.parent/'timing_calibration.json')
            archive = episode.parent/f"geometry_{cal['calibration_round']-1:02d}"/f"single_agent_{probe['agent_id']}.npz"
            result['baseline_reproduction'] = d0.baseline_compare(run, archive)
        result.update(probe_id=probe_id, arm=arm, input_group_sha256=before,
                      config_sha256=run['config_sha256'], patch_restored=RouteTracker._build is ORIGINAL_BUILD,
                      status='COMPLETE' if result['physical_status'] == 'PASS' else arm+'_FAILED',
                      raw_sha256={f: sha(destination/f) for f in ('run.npz', 'tracking_frames.npz')})
        save(destination/'result.json', result)
    except Exception as exc:
        save(destination/'error.json', dict(status=arm+'_FAILED', type=type(exc).__name__, message=str(exc),
             fatal=isinstance(exc, (P0ContractError, IntegrityError)) or arm == 'A',
             patch_restored=RouteTracker._build is ORIGINAL_BUILD, traceback=traceback.format_exc()))
        raise


def summarize(results, manifest, stop, elapsed):
    complete = {arm: [r for r in results if r['arm'] == arm and r.get('physical_status') == 'PASS'] for arm in manifest['arms']}
    by_probe = {(r['probe_id'], r['arm']): r for r in results}
    unfinished = [dict(probe_id=p, arm=arm) for p in manifest['order'] for arm in manifest['arms']
                  if (p, arm) not in by_probe or by_probe[p, arm].get('physical_status') != 'PASS']
    roles = {p['probe_id']: p['probe_kind'] for p in manifest['probes']}
    outcomes = {}
    for arm in ('B1', 'B2'):
        feint = [r for r in complete[arm] if roles[r['probe_id']] == 'feint' and
                 by_probe.get((r['probe_id'], 'A'), {}).get('physical_status') == 'PASS']
        removed = [r['probe_id'] for r in feint if by_probe[r['probe_id'], 'A']['dwell']['detected'] and not r['dwell']['detected']]
        all_valid = len(complete[arm]) == 7
        degraded = [r['probe_id'] for r in results if r['arm'] == arm and r.get('tracking', {}).get('classification') == 'TRACKING_ACCURACY_DEGRADED']
        outcomes[arm] = dict(effect='INCOMPLETE' if not all_valid else 'CORNER_CAP_EFFECT_OBSERVED' if removed else 'CORNER_CAP_EFFECT_NOT_OBSERVED',
            observed_completed_feint_effect='CORNER_CAP_EFFECT_OBSERVED' if removed else 'CORNER_CAP_EFFECT_NOT_OBSERVED',
            completed_feint_denominator=len(feint), feint_dwell_removed=removed, valid_probes=len(complete[arm]),
            tracking='INCOMPLETE' if not all_valid else 'TRACKING_ACCURACY_DEGRADED' if degraded else 'TRACKING_ACCURACY_PRESERVED',
            completed_tracking_degraded=degraded)
    summary = {}
    for arm, rows in complete.items():
        measured = [r for r in results if r['arm'] == arm and 'tracking' in r]
        subset = lambda kind: [r for r in rows if roles[r['probe_id']] == kind]
        summary[arm] = dict(valid_probes=len(rows), feint_positive=sum(r['dwell']['detected'] for r in subset('feint')),
            feint_denominator=len(subset('feint')), monitoring_positive=sum(r['dwell']['detected'] for r in subset('monitoring')),
            monitoring_denominator=len(subset('monitoring')), events_per_km_p50=distribution(r['low_speed']['events_per_km'] for r in rows if r['low_speed']['events_per_km'] is not None)['p50'],
            trajectory_duration_s_p50=distribution(r['exported_duration_s'] for r in rows)['p50'],
            execution_wall_s_p50=distribution(r['wall_s'] for r in rows)['p50'],
            measured_arms=len(measured), all_waypoints_count=sum(r['tracking']['all_waypoints_witnessed'] for r in measured),
            maximum_lateral_deviation_m=max((r['tracking']['max_lateral_deviation_m'] for r in measured), default=None),
            physical_or_scene_violation_count=sum(r.get('physical_status') == 'FAIL' or r.get('scene', {}).get('violation', False) for r in results if r['arm'] == arm),
            failed_or_unfinished_arms=7-len(rows))
    return dict(marker=MARKER, scope='solo_probe', status='COMPLETE' if not unfinished and not stop else 'INCOMPLETE',
                outcomes=outcomes, summary=summary, results=results, unfinished=unfinished, stop=stop,
                elapsed_wall_s=elapsed, fixed_selection_sha256=manifest['selection_sha256'])


def launch():
    manifest = verify_protected(); root = Path(manifest['external_output'])
    require(not (root/'registration.json').exists(), 'D0b already started; never rerun or change budget')
    tests = read(OUT/'D0b_test_results.json')
    require(tests['status'] == 'PASS' and tests['existing_tests'] == 51, 'Required tests not passed')
    formula = validate_formula()
    save(root/'registration.json', dict(base=BASE, script_sha256=sha(__file__), tests_sha256=sha(OUT/'D0b_test_results.json'),
         selection_sha256=manifest['selection_sha256'], order=manifest['order'], arms=manifest['arms'], wall_limit_s=2400,
         formula_verification=formula, B1_source_sha256=sha(PROJECT/'scripts/probe_v07_fe_corner_cap.py')))
    start = time.monotonic(); deadline = start+2400; results = []; stop = None
    try:
        for probe_id in manifest['order']:
            for arm in manifest['arms']:
                verify_protected()
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    stop = dict(reason='WALL_LIMIT', probe_id=probe_id, arm=arm); break
                dest = root/probe_id/arm; log = root/f'{probe_id}_{arm}.log'
                with log.open('w', encoding='utf-8') as stream:
                    proc = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), '--worker', probe_id,
                        '--arm', arm, '--out', str(dest)], cwd=PROJECT, stdout=stream, stderr=subprocess.STDOUT)
                    try:
                        code = proc.wait(timeout=remaining)
                    except subprocess.TimeoutExpired:
                        proc.kill(); proc.wait()
                        stop = dict(reason='WALL_LIMIT', probe_id=probe_id, arm=arm, incomplete_directory=str(dest)); break
                if code:
                    error = read(dest/'error.json') if (dest/'error.json').exists() else dict(type='WorkerFailure', fatal=True, log=str(log))
                    results.append(dict(probe_id=probe_id, arm=arm, status=arm+'_FAILED', error=error))
                    if error.get('fatal', True):
                        stop = dict(reason='FATAL_ERROR', probe_id=probe_id, arm=arm, error=error); break
                else:
                    actual = read(dest/'result.json'); results.append(actual)
                    if arm == 'A' and actual['baseline_reproduction']['status'] != 'BITWISE_IDENTICAL':
                        stop = dict(reason='A_REPLAY_MISMATCH', probe_id=probe_id, details=actual['baseline_reproduction']); break
                    if arm == 'A' and actual['physical_status'] != 'PASS':
                        stop = dict(reason='A_BASIC_CONTRACT_FAILED', probe_id=probe_id, checks=actual['physical_checks']); break
                    print(json.dumps(dict(probe=probe_id, arm=arm, status=actual['physical_status'],
                         dwell=actual['dwell']['detected'], tracking=actual['tracking']['classification'],
                         scene_violation=actual['scene']['violation'], remaining_s=round(deadline-time.monotonic(), 1))), flush=True)
                save(root/'progress.json', summarize(results, manifest, stop, time.monotonic()-start))
            if stop:
                break
    except (IntegrityError, P0ContractError) as exc:
        stop = dict(reason='FATAL_INTEGRITY', message=str(exc))
    final = summarize(results, manifest, stop, time.monotonic()-start)
    try:
        verify_protected(); final['protected_hashes_unchanged'] = True
    except IntegrityError as exc:
        final['protected_hashes_unchanged'] = False; final['stop'] = dict(reason='FATAL_INTEGRITY', message=str(exc))
        final['status'] = 'EXPERIMENT_INVALID'
    save(root/'probe_results.json', final); save(OUT/'D0b_probe_results.json', final)
    print(json.dumps({k:v for k,v in final.items() if k != 'results'}, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker'); parser.add_argument('--arm', choices=['A', 'B1', 'B2'])
    parser.add_argument('--out', type=Path); parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.arm, args.out)
    elif args.run:
        launch()
    else:
        parser.error('choose --run or --worker')


if __name__ == '__main__':
    main()
