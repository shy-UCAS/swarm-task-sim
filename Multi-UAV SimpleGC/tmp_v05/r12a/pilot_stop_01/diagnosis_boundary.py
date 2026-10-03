"""Read-only reproduction of preserved patrol segment visit evidence.

Writes only a new diagnosis JSON beside this script; never rewrites analyses.
"""
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from swarm_sim.patrol_validation import _distance_to_segment, _service_points, segment_visits
from swarm_sim.route_windows import service_window_view

def read(p):
    return json.loads(p.read_text(encoding="utf-8"))

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

control_path = ROOT / 'verification/v05_r12_pp_20261002/control.json'
control = read(control_path)
record = control['records'][-1]
directory = Path(record['run_directory'])
analysis = Path(record['analysis_directory'])
labels = read(analysis / 'labels.json')
windows = read(analysis / 'phase_windows.json')
scene = read(directory / 'scenario.json')
manifest = read(analysis / 'manifest.json')
params = scene['task_spec']['mission']['intent_params']
source_paths = {str(control_path): sha(control_path)}
for name, digest in manifest['source_sha256'].items():
    p = directory / name
    assert sha(p) == digest, str(p)
    source_paths[str(p)] = digest
for name, digest in manifest['artifact_sha256'].items():
    p = analysis / name
    assert sha(p) == digest, str(p)
    source_paths[str(p)] = digest
for filename in ('patrol_validation.py', 'route_windows.py', 'mission_evaluation_v3.py', 'patrol.py'):
    p = ROOT / 'swarm_sim' / filename
    assert sha(p) == manifest['analysis_source_sha256'][filename]
    source_paths[str(p)] = sha(p)

report = dict(version='v05_r12a_pilot_stop_boundary_diagnosis_v1',
    run_id=record['run_id'], analysis_directory=str(analysis), source_sha256=source_paths,
    original_disposition={k: labels[k] for k in ('mission_success','mission_success_observation','semantic_consistency')},
    method='Reproduce segment_visits from existing exported CSVs using original per-channel service_window_view; no analyze_run call, no altered thresholds, no updated label or disposition.',
    radius_m=params['visit_radius_m'], leave_radius_m=params['visit_radius_m']+1.0,
    channels={}, source_preservation_rechecked=False)
for channel, filename in (('truth','truth.csv'), ('observation','observations.csv')):
    traces = {}
    with (analysis / filename).open(encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            traces.setdefault(row['agent_id'], []).append((float(row['t_s']),
                [float(row[k]) for k in ('east_m','north_m','up_m')] if row['valid']=='1' else None))
    perim = labels['mission_metrics'][channel]['perimeter_revisit']
    full = {w['agent_id']: w for w in windows['channels'][channel] if w['semantic_phase']=='patrol'}
    service = {w['agent_id']: w for w in service_window_view(windows['channels'][channel]) if w['semantic_phase']=='patrol'}
    out = dict(laps=perim['per_agent_laps_observed'], evidence_complete=perim['evidence_complete'],
        evidence_issues=perim['evidence_issues'], visits_pass=perim['visits_pass'],
        max_gap_pass=perim['max_gap_pass'], max_revisit_gap_s=perim['max_revisit_gap_s'],
        allowed_gap_s=perim['allowed_gap_s'], required_visits_per_segment=perim['required_visits_per_segment'],
        windows={a: {k: full[a][k] for k in ('start_s','end_s','arrival_s','arrival_source','arrival_reason','arrival_verified')} for a in full},
        affected_segments={})
    for segment in perim['segments']:
        if segment['segment_id'] not in ('side_00_part_000','side_02_part_000'):
            continue
        detail=dict(original_count=segment['count'], initially_occupied_by=segment['initially_occupied_by'],
            original_visits=segment['visits'], start_xy_m=segment['start_xy_m'], end_xy_m=segment['end_xy_m'], per_agent={})
        reconstructed=[]
        for agent in sorted(traces):
            w=service[agent]
            points, error=_service_points(traces[agent],w['start_s'],w['end_s'],scene['max_gap_s'])
            assert error is None, error
            visits,initial=segment_visits(points,segment,params['visit_radius_m'],agent)
            reconstructed.extend(visits)
            def describe(point):
                t, xyz=point
                return dict(t_s=t,xyz_m=list(xyz),distance_to_segment_m=_distance_to_segment(xyz,segment))
            late=[p for p in points if p[0]>=w['end_s']-5.]
            exported_late=[p for p in traces[agent] if p[1] is not None and w['end_s']-5.<=p[0]<=full[agent]['end_s']]
            initial_points=[p for p in points if p[0]<=w['start_s']+3.]
            late_inside=[p for p in exported_late if _distance_to_segment(p[1],segment)<=params['visit_radius_m']+1e-8]
            target=full[agent]['terminal_point']
            target_xyz=[target[k] for k in ('east_m','north_m','up_m')]
            detail['per_agent'][agent]=dict(service_start_s=w['start_s'],service_end_s=w['end_s'],
                initial=initial, reconstructed_visits=visits, first=describe(points[0]),last=describe(points[-1]),
                nominal_entry_distance_to_segment_m=_distance_to_segment(target_xyz,segment),
                first_three_seconds=[describe(p) for p in initial_points],
                final_five_service_seconds=[describe(p) for p in late],
                final_five_seconds_through_full_window=[describe(p) for p in exported_late],
                final_five_service_seconds_nearest=describe(min(late,key=lambda p:_distance_to_segment(p[1],segment))),
                first_late_inside_in_export=describe(late_inside[0]) if late_inside else None)
        reconstructed.sort(key=lambda r:(r['start_s'],r['agent_id']))
        assert reconstructed==segment['visits'], (channel,segment['segment_id'])
        detail['reproduced_exact_original_visits']=True
        out['affected_segments'][segment['segment_id']]=detail
    report['channels'][channel]=out

assert all(sha(Path(p))==h for p,h in source_paths.items())
report['source_preservation_rechecked']=True
report['code_references']={
    'segment_entry_exit_hysteresis':'swarm_sim/patrol_validation.py:68-93',
    'required_count_and_mission_condition':'swarm_sim/patrol_validation.py:177-225',
    'service_end_is_channel_arrival':'swarm_sim/route_windows.py:200-211',
    'mission_channels_and_disagreement':'swarm_sim/mission_evaluation_v3.py:44-71',
    'lap_route':'swarm_sim/patrol.py:87-100'}
output=Path(__file__).with_name('diagnosis_boundary.json')
if output.exists():
    raise FileExistsError('never overwrite existing diagnosis: '+str(output))
output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
summary={ch:{seg:{a:{k:d[k] for k in ('initial','service_start_s','service_end_s','first','last','nominal_entry_distance_to_segment_m','final_five_service_seconds_nearest','first_late_inside_in_export')} for a,d in v['per_agent'].items()} for seg,v in c['affected_segments'].items()} for ch,c in report['channels'].items()}
print(json.dumps(dict(output=str(output),summary=summary),ensure_ascii=False,indent=2))
