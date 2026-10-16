"""C9: bounded read-only diagnosis of the six registered M2 solo failures."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from task_v07.io import read_json, sha
from scripts.run_v07_m3_trial import atomic


def intervals(mask):
    transitions = np.diff(np.r_[False, mask, False].astype(int))
    return list(zip(np.flatnonzero(transitions == 1), np.flatnonzero(transitions == -1)-1))


def neighborhood(points, position):
    distances = np.linalg.norm(points-position, axis=1)
    node = int(np.argmin(distances)); legs = np.diff(points, axis=0)
    lengths = np.linalg.norm(legs, axis=1)
    turns = np.degrees(np.arccos(np.clip(np.sum(legs[:-1]*legs[1:], axis=1)
                          / np.maximum(lengths[:-1]*lengths[1:], 1e-12), -1, 1)))
    return {"nearest_node": node, "node_distance_m": float(distances[node]),
            "node_enu_m": points[node].tolist(),
            "nodes_around": {str(i): points[i].tolist() for i in range(max(0, node-1), min(len(points), node+2))},
            "incoming_length_m": float(lengths[node-1]) if node else None,
            "outgoing_length_m": float(lengths[node]) if node < len(lengths) else None,
            "turn_deg": float(turns[node-1]) if 0 < node < len(points)-1 else None,
            "route_minimum_segment_m": float(lengths.min()),
            "route_maximum_turn_deg": float(turns.max()) if len(turns) else None,
            "duplicate_segment_indices": np.flatnonzero(lengths < 1e-8).tolist()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--started-utc", required=True)
    args = parser.parse_args()
    started = datetime.fromisoformat(args.started_utc)
    source = read_json(PROJECT/"docs/v07/evidence/m2/qd_summary.json")
    records = read_json(PROJECT/"docs/v07/evidence/m2/qd_ended_outside_warning.json")
    rows = []; seen = set(); status = "PASS"
    for record in records:
        if (datetime.now(timezone.utc)-started).total_seconds() >= 900:
            status = "TIME_LIMIT_STOP"; break
        sid = record["skeleton_id"]; agent = record["agent_id"]
        if sid != "family_s12_4d13d93f9171c446_ext_006_regular": continue
        directory = f"geometry_{record['round']-1:02d}"
        root = Path(source["attempt"])/sid/directory
        key = (source["attempt"], sid, directory, record["group_id"], agent)
        if key in seen: raise ValueError("Duplicate registered member-round")
        seen.add(key)
        sk = read_json(root/"skeleton.json"); rh = read_json(root/"rehearsal.json")
        ref = sk["references"][agent]; points = np.asarray(ref["points_enu_m"])
        paths = [root/"skeleton.json", root/"rehearsal.json", root/f"single_agent_{agent}.npz"]
        for path in paths:
            if sha(path) != record["source_sha256"][path.name]:
                raise ValueError(f"M2 source hash differs: {path}")
        with np.load(paths[-1], allow_pickle=False) as saved:
            if saved["agent_ids"].tolist() != [agent]: raise ValueError("Solo identity mismatch")
            times = saved["time_us"]/1e6; positions = saved["p"][:, 0]; velocities = saved["v"][:, 0]
        speed = np.linalg.norm(velocities, axis=1)
        low = []
        for begin, end in intervals(speed <= .5):
            # Diagnostic extraction only; neither value is a new acceptance gate.
            if times[end]-times[begin] < 10: continue
            center = np.mean(positions[begin:end+1], axis=0)
            low.append({"start_s": float(times[begin]), "end_s": float(times[end]),
                        "duration_s": float(times[end]-times[begin]), "center_enu_m": center.tolist(),
                        "start_enu_m": positions[begin].tolist(), "end_enu_m": positions[end].tolist(),
                        "displacement_m": float(np.linalg.norm(positions[end]-positions[begin])),
                        "position_radius_m": float(np.linalg.norm(positions[begin:end+1]-center, axis=1).max()),
                        "speed_min_m_s": float(speed[begin:end+1].min()),
                        "speed_max_m_s": float(speed[begin:end+1].max()),
                        "route_neighborhood": neighborhood(points, center)})
        # One-second moving headings, only where both endpoints are actually moving.
        active = (speed[:-10] > .5) & (speed[10:] > .5)
        cosines = np.sum(velocities[:-10]*velocities[10:], axis=1)/np.maximum(speed[:-10]*speed[10:], 1e-12)
        reversals = intervals(active & (cosines <= np.cos(np.radians(135))))
        row = {**record, "key": list(key), "geometry_directory": directory,
               "source_root": str(root), "source_hash_check": "PASS", "low_speed_intervals": low,
               "one_second_heading_reversal_ranges_s": [[float(times[a]), float(times[b+10])] for a,b in reversals],
               "last_frame_route_neighborhood": neighborhood(points, positions[-1]),
               "last_frame_speed_m_s": float(speed[-1]),
               "scan_lane_endpoints_m": ref.get("scan_lane_endpoints_m"),
               "retreat_endpoint_enu_m": ref["endpoint_enu_m"],
               "failed_conditions": [k for k,v in rh["agents"][agent]["result"]["conditions"].items() if not v],
               "evidence_level": "confirmed" if low else "unresolved",
               "confirmed_scope": "Observed low-speed geometry only; nearest waypoint is not tracker cursor",
               "root_cause_level": "unresolved", "tracker_internal_state_saved": False}
        rows.append(row)
    elapsed = (datetime.now(timezone.utc)-started).total_seconds()
    if elapsed > 900: status = "TIME_LIMIT_STOP"
    result = {"status": status, "started_utc": started.isoformat(), "wall_s": elapsed, "wall_limit_s": 900,
              "source_attempt": source["attempt"], "expected_member_rounds": 6, "analyzed_member_rounds": len(rows),
              "diagnostic_parameters": {"speed_at_most_m_s": .5, "duration_at_least_s": 10,
                  "heading_window_s": 1, "heading_reversal_deg": 135, "acceptance_gate": False},
              "simulation_runs": 0, "rows": rows,
              "limitations": "No RouteTracker primitive/node state was exported; causal attribution remains unresolved."}
    atomic(PROJECT/"docs/v07/evidence/m3/m3_c9_legacy_stall_diagnosis.json", result)
    print({"status": status, "wall_s": elapsed, "rows": len(rows),
           "low_speed_ranges": [len(r["low_speed_intervals"]) for r in rows]})
    return 0 if status == "PASS" and len(rows) == 6 else 1


if __name__ == "__main__":
    raise SystemExit(main())
