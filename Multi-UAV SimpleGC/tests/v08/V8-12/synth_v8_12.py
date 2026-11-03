"""V8-12不可修改的合成夹具；不导入shapely。"""
from v08.contract.monitoring import (
    GroupSpec, TaskSpec, SpeedProfilePrior, family_from_initial, initial_states,
)
from v08.scene.context import build_context
from v08.sampler.keys import RngKey
from v08.motion.intents.monitoring import build_candidate


def scene_and_family():
    entities = [{
        "id": "fac_a", "type": "facility",
        "geometry": {"type": "Circle", "center_m": [0.0, 0.0], "radius_m": 100.0},
    }]
    for layer, offset in (("protected", 50.0), ("alert", 200.0), ("warning", 750.0)):
        entities.append({
            "id": "fac_a_" + layer, "type": "protection_zone",
            "facility_id": "fac_a", "layer": layer, "offset_m": offset,
            "geometry": {"type": "Circle", "center_m": [0.0, 0.0],
                         "radius_m": 100.0 + offset},
        })
    scene = {
        "schema_version": "synthetic", "coordinate_system": "ENU",
        "units": {"length": "m", "angle": "rad", "speed": "m/s",
                  "acceleration": "m/s^2"},
        "world": {"id": "world", "geometry": {
            "type": "Polygon",
            "vertices_m": [[-3000.0, -3000.0], [3000.0, -3000.0],
                           [3000.0, 3000.0], [-3000.0, 3000.0]],
        }},
        "entry_zones": [], "entities": entities,
    }
    initial = {
        "vehicle_count": 2, "task_altitude_m": 120.0,
        "lateral_spacing_m": 20.0, "map_side_m": 6000.0,
        "observation_profile": {}, "cruise_speed_m_s": 9.0,
        "initial_states": [
            {"agent_id": "a", "entry_id": "entry",
             "position_enu_m": [-1500.0, -20.0, 120.0],
             "velocity_enu_m_s": [1.0, 2.0, 0.0],
             "acceleration_enu_m_s2": [1.0, 0.0, 0.0]},
            {"agent_id": "b", "entry_id": "entry",
             "position_enu_m": [-1500.0, 20.0, 120.0],
             "velocity_enu_m_s": [-1.0, 2.0, 0.0],
             "acceleration_enu_m_s2": [0.0, 1.0, 0.0]},
        ],
    }
    return scene, family_from_initial("fixture_v8_12", initial)


def fixture_plan(topology="loop"):
    import math
    scene, family = scene_and_family()
    ctx = build_context(scene, family, cache_dir=None)
    group = GroupSpec("g0", ("a", "b"), SpeedProfilePrior(6.0, 0.0), "abreast")
    task = TaskSpec("t0", "monitoring", "fac_a")
    states = initial_states(family, group.member_ids)
    key = RngKey(family.family_id, 0, "shape", mission=0, group="g0", segment=0)
    proposal = {
        "center_xy": (0.0, -155.0), "rho0_m": 500.0,
        "coefficients_m": (0.0, 0.0, 0.0, 0.0),
        "phase_rad": math.pi, "direction": 1,
        "topology": topology, "laps": 1.5, "traversals": 2,
        "arc_span_rad": math.pi, "turn_kind": "teardrop", "turn_radius_m": 50.0,
        "collection_xy": (-1000.0, 0.0),
        "entry_point_xy": (-850.0, 0.0),
        "exit_point_xy": (850.0, 0.0),
        "terminal_xy": (1300.0, 0.0),
        "member_slot_order": ("a", "b"),
        "collection_bezier_controls": {
            "a": ((-1500.0, -20.0), (-1400.0, -20.0), (-1300.0, -20.0),
                  (-1200.0, -10.0), (-1100.0, -10.0), (-1000.0, -10.0)),
            "b": ((-1500.0, 20.0), (-1400.0, 20.0), (-1300.0, 20.0),
                  (-1200.0, 10.0), (-1100.0, 10.0), (-1000.0, 10.0)),
        },
        "reference_ingress": (
            ("line", (-1000.0, 0.0), (-650.0, 0.0)),
            ("arc", (-650.0, -150.0), 150.0, math.pi / 2, -math.pi / 2),
            ("line", (-500.0, -150.0), (-500.0, -155.0)),
        ),
        "reference_egress": (
            ("line", (500.0, -155.0), (500.0, -150.0)),
            ("arc", (650.0, -150.0), 150.0, math.pi, -math.pi / 2),
            ("line", (650.0, 0.0), (1300.0, 0.0)),
        ),
    }
    plan = build_candidate(ctx, group, task, states, (), key, proposal)
    return ctx, group, task, states, plan
