"""Verify saved phase-2 role points with the authoritative contour query.

This diagnostic deliberately calls geometry_facts as requested; the separate
P0 trajectory audit uses analytic circles and GEOS without task_v07 imports.
"""
import csv
import json
from pathlib import Path
import sys
import numpy as np
PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))
from scripts.run_v07_s2_expansion import descriptor_jobs, INFRA_ATTEMPT, DEFAULT_DATA
from task_v07.geometry import geometry_facts


def verify_points(output):
    ids = [f'family_s12_{m}_ext_{s:03d}_regular'
           for m in ('4d13d93f9171c446', 'aa4c66be8e85d64d') for s in (1, 3, 4)]
    rows, missing, maps = [], [], {}
    for job in descriptor_jobs(INFRA_ATTEMPT, ids, output):
        desc, scene = job['descriptor'], job['scene']
        facilities = [e for e in scene['entities'] if e['type'] == 'facility']
        maps[desc['map_id']] = {e['id']: e['geometry']['type'] for e in facilities}
        # Keep both latest saved geometries and the latest complete trial when available.
        sources = [f for attempt in sorted(DEFAULT_DATA.glob('attempt_s2x_p1_*'), reverse=True)
                   if (f := attempt / desc['skeleton_id'] / 'skeleton.json').exists()][:2]
        complete = DEFAULT_DATA / 'attempt_s2x_p1_20261014T093058Z_5860b099' / desc['skeleton_id'] / 'skeleton.json'
        if complete.exists() and complete not in sources:
            sources.append(complete)
        if not sources:
            missing.append({'skeleton_id': desc['skeleton_id'], 'reason': 'no saved skeleton: multi-group skipped before directory creation'})
        for source in sources:
            sk = json.loads(source.read_text(encoding='utf-8'))
            for a, ref in sk['references'].items():
                if sk['execution_method'] == 'close_observation':
                    point, kind = ref.get('observation_point_enu_m'), 'observation_point'
                elif sk['role'] == 'feint':
                    point, kind = ref['points_enu_m'][-2], 'feint_depth_point'
                else:
                    point, kind = ref['endpoint_enu_m'], 'intrusion_endpoint'
                if point is None:
                    missing.append({'source': str(source), 'agent_id': a, 'reason': 'point not saved'})
                    continue
                for facility in facilities:
                    offsets = {e['layer']: e['offset_m'] for e in scene['entities'] if e.get('facility_id') == facility['id']}
                    facts = geometry_facts(facility['geometry'], point[:2], layer_offsets=offsets)
                    signed = float(facts['signed_distance_m'])
                    is_target = facility['id'] == sk['target_id']
                    expected, ok, quantity, bounds = None, None, None, None
                    if is_target and kind == 'observation_point':
                        expected, quantity, bounds = 'alert exterior by 1–2 planning margins', signed-offsets['alert'], [35., 70.]
                    elif is_target and kind == 'feint_depth_point':
                        expected, quantity, bounds = '30%–70% alert-band penetration', (offsets['alert']-signed)/(offsets['alert']-offsets['protected']), [.3, .7]
                    elif is_target:
                        expected, quantity, bounds = 'protected entry with depth >=20m', float(facts['protected_depth_m']), [20., None]
                    if quantity is not None:
                        ok = quantity >= bounds[0]-1e-6 and (bounds[1] is None or quantity <= bounds[1]+1e-6)
                    rows.append({'source': str(source), 'attempt': source.parent.parent.name,
                                 'skeleton_id': desc['skeleton_id'], 'map_id': desc['map_id'],
                                 'agent_id': a, 'point_kind': kind, 'point_enu_m': point,
                                 'facility_id': facility['id'], 'facility_shape': facility['geometry']['type'],
                                 'is_target': is_target, 'signed_contour_distance_m': signed,
                                 'layer': int(facts['layer']), 'protected_depth_m': float(facts['protected_depth_m']),
                                 'layer_offsets_m': offsets, 'expected': expected,
                                 'measured_requirement_quantity': quantity, 'required_bounds': bounds, 'matches_requirement': ok})
    result = {'method': 'geometry_facts on original facility contour; closed layer boundaries',
              'layers': {'0': 'outside_warning', '1': 'warning_only', '2': 'alert_only', '3': 'protected'},
              'maps': maps, 'missing': missing, 'points': rows}
    (output/'previous_role_point_verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    fields = ['attempt', 'skeleton_id', 'agent_id', 'point_kind', 'facility_id', 'facility_shape', 'is_target',
              'signed_contour_distance_m', 'layer', 'protected_depth_m', 'expected', 'measured_requirement_quantity', 'matches_requirement']
    with (output/'previous_role_point_verification.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer=csv.DictWriter(stream, fields, extrasaction='ignore'); writer.writeheader(); writer.writerows(rows)
    return result

if __name__ == '__main__':
    verify_points(Path(sys.argv[1]))
