"""Coordinate-free task request, separate from scene and initial-state geometry."""
from copy import deepcopy

from task_v07.planning import seed_for
from task_v07.expansion.contracts import P0ContractError, PlannerUnavailable, validate_family_conditions
from task_v07.expansion.public_approach_shape import public_approach_shape
from .geometry_config import load_geometry


def build_spec(descriptor, group, geometry_config=None):
    family = descriptor["family_conditions"]
    validate_family_conditions(descriptor, family)
    registered = [g for g in descriptor["task_groups"] if g["group_id"] == group["group_id"]]
    if registered != [group] or not set(group["members"]) <= set(descriptor["agent_ids"]):
        raise P0ContractError("TaskSpec group differs from the registered descriptor")
    cfg = load_geometry() if geometry_config is None else deepcopy(geometry_config)
    method = group["execution_method"]
    allowed = {"transit": "transit", "area_search": "reconnaissance", "close_observation": "reconnaissance",
               "monitoring": "monitoring", "feint": "feint", "intrusion": "intrusion"}
    if allowed.get(method) != group["role"] or method not in cfg:
        raise PlannerUnavailable(f"Unsupported unified execution method: {method}/{group['role']}")
    mode = descriptor["common_draw"]["approach_mode"]
    slot = descriptor["common_draw"]["slot"]
    return {"schema_version": "TaskSpec/0.7-m3a", "geometry_version": cfg["version"],
            **{k: descriptor[k] for k in ("skeleton_id", "family_id", "map_id")},
            **{k: deepcopy(group[k]) for k in ("group_id", "members", "target_id", "role", "execution_method",
                                              "source_units", "between_group_offset_s")},
            "approach_mode": mode, "common_slot": slot, "params": deepcopy(cfg[method]),
            "geometry_seed": seed_for(descriptor["role_seed"], f"continuous-geometry:{group['group_id']}"),
            "criteria_version": "criteria/0.7-r1",
            "family": {k: family[k] for k in ("cruise_speed_m_s", "task_altitude_m", "lateral_spacing_m")},
            "public_split": public_approach_shape(family, slot, group["members"], mode == "multi_direction")}


def validate_spec(spec, descriptor, group, geometry_config=None):
    if spec != build_spec(descriptor, group, geometry_config):
        raise P0ContractError("TaskSpec changed identity, public conditions, parameters or seed")
    return spec


def proposal_seed(spec, index):
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise ValueError("Nonnegative integer proposal index required")
    return seed_for(spec["geometry_seed"], f"unified-geometry-r1:{index}")
