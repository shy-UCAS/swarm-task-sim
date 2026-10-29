"""Small synthetic on-disk episodes; no planner, simulator or external data."""
from copy import deepcopy
from pathlib import Path

import numpy as np
from scene_v07.contract import SCHEMA_VERSION, UNITS
from task_v07.io import write_csv
from task_v07.s3._common import sha256, write_json


def scene():
    polygon = {"type": "Polygon", "vertices_m": [[-100, -100], [100, -100], [100, 100], [-100, 100]]}
    result = {"schema_version": SCHEMA_VERSION, "coordinate_system": "ENU", "units": dict(UNITS),
              "world": {"id": "world", "geometry": polygon},
              "entry_zones": [{"id": "entry_01", "geometry": deepcopy(polygon)}],
              "entities": [{"id": "facility_01", "type": "facility",
                            "geometry": {"type": "Circle", "center_m": [0, 0], "radius_m": 1}},
                           {"id": "obstacle_01", "type": "hard_constraint_obstacle",
                            "geometry": {"type": "Circle", "center_m": [80, 80], "radius_m": 1}},
                           {"id": "radar_01", "type": "radar",
                            "geometry": {"type": "Point", "position_m": [50, 50]}}]}
    for layer, radius in (("protected", 5), ("alert", 10), ("warning", 30)):
        result["entities"].append({"id": "facility_01_" + layer, "type": "protection_zone",
                                  "facility_id": "facility_01", "layer": layer, "offset_m": radius,
                                  "geometry": {"type": "Circle", "center_m": [0, 0], "radius_m": radius}})
    return result


def labels():
    ids = ["uav_01", "uav_02"]
    agents = {}
    for aid in ids:
        agents[aid] = {"observed": {
            "regions_by_facility": {"facility_01": {
                name: {"entered_observed": name == "warning"} for name in ("warning", "alert", "protected")}},
            "contribution": {"observation_dwell": {"total_duration_s": 57.2}}},
            "result": {"status": "success", "conditions": {"ended_outside_warning": True}}}
    return {"agents": agents, "task_groups": {
        "task_group_01": {"assigned": {"role": "transit", "execution_method": "transit", "target": "facility_01"},
                          "observed": {"members": ids, "approach_classification": "same_direction",
                                       "approach_headings_deg": dict.fromkeys(ids, 0.0),
                                       "coordination": {"classification": "sequential",
                                                        "batches": [{"members": [a]} for a in ids]},
                                       "shared_coverage": {"coverage_fraction": .85}},
                          "result": {"status": "success"}}},
        "cluster": {"assigned": {"intent": "transit"}, "result": {"status": "success"}}}


def trajectories():
    ticks = np.arange(91, dtype=np.int64) * 100000
    t = ticks / 1e6
    ids = ["uav_01", "uav_02"]
    p, v = np.zeros((91, 2, 3)), np.zeros((91, 2, 3))
    for j, tc in enumerate((5., 6.)):
        p[:, j, 0] = np.where(t < tc, t, 10. * (j + 1))
        v[:, j, 0] = np.where(t < tc, 2., 0.)
    p[(t >= 2) & (t <= 2.5), 0, 0] = 4.
    v[(t >= 2) & (t <= 2.5), 0] = 0.
    truth = {"time_us": ticks, "p": p, "v": v, "a": np.zeros_like(p), "agent_ids": np.array(ids)}
    task = {"initial_settle_s": 1., "stop_radius_m": .1, "stop_speed_m_s": .2, "stop_hold_s": 1.,
            "terminal_radius_m": .01, "terminal_speed_m_s": .01, "terminal_hold_s": 2.,
            "references": {a: {"points_enu_m": [[0., 0., 0.], [10. * (j + 1), 0., 0.]]}
                           for j, a in enumerate(ids)}}
    source = {"departure_delays_s": {"uav_01": 0., "uav_02": 1.}, "intent": "privileged"}
    raw = {"x": np.concatenate((p, v), axis=2) + .123, "mask": np.ones((91, 2), bool),
           "t_s": t, "agent_ids": ids, "scene": scene()}
    return raw, task, source, truth


def episode(root):
    root = Path(root)
    root.mkdir(parents=True)
    raw, task, source, truth = trajectories()
    for name, value in (("public_scene.json", scene()), ("labels.json", labels()),
                        ("task.json", task), ("source.json", source)):
        write_json(root / name, value)
    np.savez_compressed(root / "truth_10hz.npz", **truth)
    np.savez_compressed(root / "model_input.npz", **{k: v for k, v in raw.items() if k != "scene"})
    write_csv(root / "observations.csv", raw["agent_ids"], truth["time_us"], raw["x"][:, :, :3], raw["x"][:, :, 3:])
    write_json(root / "manifest.json", {"protocol_version": "swarm_defense_v07a",
                                        "agent_ids": raw["agent_ids"], "end_us": 9100000,
                                        "artifact_sha256": {p.name: sha256(p) for p in root.iterdir()}})
    return raw, task, source, truth
