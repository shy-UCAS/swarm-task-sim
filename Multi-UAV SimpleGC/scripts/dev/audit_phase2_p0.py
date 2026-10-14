"""Read-only independent P0 verification of existing phase-2 exported truth.

No task_v07 imports. Exact original contours use analytic circle distances or
GEOS polygon boundary/filled-polygon distance. Original files are never edited.
"""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from shapely.geometry import Polygon, Point

BASE=Path('F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_p1_20261014T093058Z_5860b099')


def signed_distance(geometry, xy):
    if geometry['type']=='Circle':
        return np.linalg.norm(xy-np.asarray(geometry['center_m']), axis=1)-geometry['radius_m']
    primitive=Polygon(geometry['vertices_m'])
    return np.asarray([-primitive.boundary.distance(Point(q)) if primitive.covers(Point(q))
                       else primitive.distance(Point(q)) for q in xy])


def longest_run(mask):
    best=run=0
    for value in mask:
        run=run+1 if value else 0; best=max(best,run)
    return best/10.


def verify_p0(output):
    witnesses=[]
    for root in sorted(BASE.glob('*/sequential')):
        task=json.loads((root/'task.json').read_text(encoding='utf-8'))
        if task['role'] not in ('feint', 'monitoring'): continue
        labels=json.loads((root/'labels.json').read_text(encoding='utf-8'))
        scene=json.loads((root/'public_scene.json').read_text(encoding='utf-8'))
        facility=next(e for e in scene['entities'] if e['id']==task['target_id'])
        offsets={e['layer']:e['offset_m'] for e in scene['entities'] if e.get('facility_id')==task['target_id']}
        with np.load(root/'truth_10hz.npz', allow_pickle=False) as tr:
            p,v,t,ids=tr['p'],tr['v'],tr['time_us'],tr['agent_ids'].tolist()
        for i,a in enumerate(ids):
            observed=labels['agents'][a]['observed']
            if task['role']=='feint':
                sd=signed_distance(facility['geometry'], p[:,i,:2])
                band=(sd<=offsets['alert']) & (sd>offsets['protected'])
                depth=np.where(band, offsets['alert']-sd, 0.)
                k=int(depth.argmax())
                exact=float(depth[k]); stored=observed['contribution']['max_depth_in_alert_m']
                if abs(exact-stored)>.001:
                    witnesses.append({'episode_directory': str(root), 'agent_id': a,
                                      'field': 'max_depth_in_alert_m', 'stored': stored,
                                      'independent': exact, 'independent_depth_fraction': exact/(offsets['alert']-offsets['protected']),
                                      'frame_index': k, 'time_s': float(t[k]/1e6), 'position_enu_m': p[k,i].tolist(),
                                      'contour_signed_distance_m': float(sd[k]), 'layer': 2,
                                      'truth_sha256': hashlib.sha256((root/'truth_10hz.npz').read_bytes()).hexdigest()})
            else:
                ref=task['references'][a]
                hold=(np.linalg.norm(p[:,i]-ref['endpoint_enu_m'], axis=1)<=task['terminal_radius_m']) & (np.linalg.norm(v[:,i], axis=1)<=task['terminal_speed_m_s'])
                core=observed['core_event']['t_s']
                if core is not None: hold &= t/1e6>=core
                exact=longest_run(hold); stored=observed['endpoint_hold_s']
                if exact>=task['terminal_hold_s'] and stored==0.:
                    k=int(np.flatnonzero(hold)[0])
                    witnesses.append({'episode_directory': str(root), 'agent_id': a,
                                      'field': 'endpoint_hold_s', 'stored': stored, 'independent': exact,
                                      'stored_retreat_condition': labels['agents'][a]['result']['conditions'].get('reached_retreat_point'),
                                      'core_time_s': core, 'frame_index': k, 'time_s': float(t[k]/1e6),
                                      'position_enu_m': p[k,i].tolist(),
                                      'truth_sha256': hashlib.sha256((root/'truth_10hz.npz').read_bytes()).hexdigest()})
    result={'status': 'P0_STOP' if witnesses else 'PASS', 'source_attempt': str(BASE),
            'method': 'analytic circle/GEOS original polygon; direct 10Hz endpoint distance/speed; no task_v07 imports',
            'witness_count': len(witnesses), 'witnesses': witnesses}
    (output/'independent_p0_witnesses.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result

if __name__=='__main__':
    print(json.dumps({k:v for k,v in verify_p0(Path(sys.argv[1])).items() if k!='witnesses'}, ensure_ascii=False, indent=2))
