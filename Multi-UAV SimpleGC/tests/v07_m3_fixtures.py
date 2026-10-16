"""Small deterministic M3 requests, independent of runtime data availability."""
from v07_m1_fixtures import scene


def request(multi=False, count=4):
    ids = [f"a{i}" for i in range(count)]
    family = {"family_id": "test_family", "sampling_seed": 73, "cruise_speed_m_s": 6.,
              "task_altitude_m": 120., "lateral_spacing_m": 20.,
              "initial_states": [{"agent_id": a, "position_enu_m": [-2000., 1000. + 20*i, 120.],
                                  "velocity_enu_m_s": [0., 0., 0.], "entry_id": "E1"} for i, a in enumerate(ids)]}
    group = {"group_id": "g", "members": ids, "target_id": "F1", "role": "transit",
             "execution_method": "transit", "source_units": ["unit"], "between_group_offset_s": 0.}
    descriptor = {"skeleton_id": "test_ext_000_regular", "family_id": family["family_id"], "map_id": "test_map",
                  "agent_ids": ids, "column_seed": 14, "role_seed": 71, "family_conditions": family,
                  "cruise_speed_m_s": 6., "task_altitude_m": 120., "task_groups": [group],
                  "base_intent": "transit", "main_unit_id": None,
                  "common_draw": {"slot": 0, "approach_mode": "multi_direction" if multi else "same_direction"}}
    return scene(), descriptor, group
