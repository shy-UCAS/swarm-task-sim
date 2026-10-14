"""Fail-closed route extension point, model input and paired-condition contracts."""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import math
from typing import Protocol

import numpy as np

from scene_v07.contract import canonical_json, validate_public_scene
from task_v07.io import INPUT_KEYS


class P0ContractError(ValueError):
    """A contract/information-leak discrepancy; callers must stop the attempt."""


class PlannerUnavailable(NotImplementedError):
    pass


@dataclass(frozen=True)
class RouteBundle:
    waypoints_by_agent: dict
    departure_delays_s: dict


class RolePlanner(Protocol):
    def plan(self, scene: dict, task_group: dict, role_parameters: dict) -> RouteBundle:
        """Map + group + parameters -> each member's ENU waypoints and delay."""
        ...


class UnimplementedRolePlanner:
    def plan(self, scene, task_group, role_parameters):
        raise PlannerUnavailable("Role waypoint arrangement is supplied by the project owner")


def validate_route_bundle(bundle, members):
    if not isinstance(bundle, RouteBundle):
        raise ValueError("Expected RouteBundle")
    if len(set(members)) != len(members) or not members:
        raise ValueError("Unique group members required")
    if set(bundle.waypoints_by_agent) != set(members) or set(bundle.departure_delays_s) != set(members):
        raise P0ContractError("Route/delay IDs do not match the group")
    for agent in members:
        points = np.asarray(bundle.waypoints_by_agent[agent], dtype=float)
        if points.ndim != 2 or points.shape[1] != 3 or len(points) < 2 or not np.isfinite(points).all():
            raise ValueError("Each route needs finite [K>=2,3] ENU waypoints")
        if np.any(np.linalg.norm(np.diff(points, axis=0), axis=1) < 1.0):
            raise ValueError("Adjacent waypoints must be at least 1 m apart")
        delay = bundle.departure_delays_s[agent]
        if isinstance(delay, bool) or not isinstance(delay, (int, float)) or not math.isfinite(delay) or delay < 0:
            raise ValueError("Finite nonnegative departure delay required")
        if abs(delay * 10 - round(delay * 10)) > 1e-8:
            raise ValueError("Departure delays must lie on the 0.1 s grid")
    return bundle


def condition_digest(skeleton, routes=None):
    """Departure delays are the only excluded route field."""
    payload = {"skeleton": skeleton, "waypoints": None if routes is None else routes.waypoints_by_agent}
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def validate_pair(left, right, left_routes=None, right_routes=None):
    if (left_routes is None) != (right_routes is None):
        raise P0ContractError("Only one paired route supplied")
    if condition_digest(left, left_routes) != condition_digest(right, right_routes):
        raise P0ContractError("Pair changed a non-time condition (including columns/geometry)")
    if left_routes is not None:
        validate_route_bundle(left_routes, left["agent_ids"])
        validate_route_bundle(right_routes, right["agent_ids"])
    return condition_digest(left, left_routes)


def validate_family_conditions(descriptor, family):
    if descriptor["family_conditions"] != family:
        raise P0ContractError("Skeleton changed immutable family conditions")
    for key in ("cruise_speed_m_s", "task_altitude_m"):
        if descriptor[key] != family[key]:
            raise P0ContractError(f"Skeleton changed family-only parameter: {key}")
    if set(descriptor["agent_ids"]) != {s["agent_id"] for s in family["initial_states"]}:
        raise P0ContractError("Skeleton changed family identity set")


def validate_model_input(value):
    if set(value) != INPUT_KEYS:
        raise P0ContractError("Default input contains non-whitelisted fields")
    try:
        validate_public_scene(value["scene"])
    except ValueError as exc:
        raise P0ContractError(f"Public scene contract violated: {exc}") from exc
    x, mask, times = (np.asarray(value[k]) for k in ("x", "mask", "t_s"))
    ids = list(value["agent_ids"])
    if not ids or len(set(ids)) != len(ids) or not all(isinstance(a, str) and a for a in ids):
        raise P0ContractError("Unique nonempty agent identity handles required")
    if x.ndim != 3 or x.shape[1:] != (len(ids), 6) or mask.shape != x.shape[:2]:
        raise P0ContractError("Model feature/ID/mask axes mismatch")
    if mask.dtype != np.bool_ or times.shape != (len(x),) or not len(times):
        raise P0ContractError("Invalid mask or common clock")
    if not np.isfinite(x).all() or not np.isfinite(times).all():
        raise P0ContractError("Nonfinite features/clock")
    ticks = np.rint(times * 1e6).astype(np.int64)
    if ticks[0] != 0 or np.any(np.diff(ticks) != 100000) or not np.allclose(times, ticks / 1e6, rtol=0, atol=1e-9):
        raise P0ContractError("Input requires unshifted common 10 Hz clock")
    return value


def permute_input(value, agent_ids):
    validate_model_input(value)
    old = list(value["agent_ids"])
    if len(agent_ids) != len(old) or set(agent_ids) != set(old):
        raise P0ContractError("Expected exact ID permutation")
    order = [old.index(a) for a in agent_ids]
    return {"x": np.array(value["x"])[:, order].copy(),
            "mask": np.array(value["mask"])[:, order].copy(),
            "t_s": np.array(value["t_s"]).copy(), "agent_ids": list(agent_ids),
            "scene": deepcopy(value["scene"])}
