"""Private, intent-independent candidate draws and semantic group normalization.

No function in this module produces routes, event times or measured labels.
Common random numbers couple the five intents at each family/attempt slot.
"""
from copy import deepcopy
import random

from scene_v07.contract import validate_public_scene
from task_v07.planning import seed_for

INTENTS = ("transit", "reconnaissance", "monitoring", "feint", "penetration")
ROLES = ("transit", "reconnaissance", "monitoring", "feint", "intrusion")
VERSION = "traj2language.s2_infrastructure/0.7.1"


def sample_common(scene, family, slot):
    """Deliberately has no intent argument; all seeds live in private metadata."""
    validate_public_scene(scene)
    if not isinstance(slot, int) or isinstance(slot, bool) or slot < 0:
        raise ValueError("Nonnegative integer attempt slot required")
    ids = sorted(s["agent_id"] for s in family["initial_states"])
    if len(ids) != family["vehicle_count"] or len(set(ids)) != len(ids) or len(ids) < 2:
        raise ValueError("Family must contain at least two unique unchanged agents")
    facilities = sorted(e["id"] for e in scene["entities"] if e["type"] == "facility")
    seed = seed_for(family["sampling_seed"], f"expansion-common:{slot}")
    rng = random.Random(seed)
    requested = rng.randint(1, 3)
    count = min(requested, len(ids) // 2)
    members = ids[:]
    rng.shuffle(members)
    sizes = [2] * count
    for _ in range(len(ids) - 2 * count):
        sizes[rng.randrange(count)] += 1
    first_target = rng.choice(facilities)
    targets = [first_target]
    for _ in range(count - 1):
        others = [f for f in facilities if f != first_target]
        targets.append(first_target if not others or rng.random() < .5 else rng.choice(others))
    approach = rng.choice(["same_direction", "multi_direction"])
    units = []
    cursor = 0
    for i, (size, target) in enumerate(zip(sizes, targets)):
        units.append({"unit_id": f"unit_{i+1:02d}", "target_id": target,
                      "members": sorted(members[cursor:cursor+size]),
                      "between_group_offset_s": round(rng.uniform(0, 90), 1)})
        cursor += size
    return {"seed": seed, "slot": slot, "requested_unit_count": requested,
            "actual_unit_count": count, "unit_count_capped": requested != count,
            "approach_mode": approach, "multi_direction_min_span_deg": 90.0,
            "units": units, "distribution": {
                "unit_count": "uniform 1..3 then cap at floor(N/2)",
                "approach": "Bernoulli(0.5); same common draw across intents",
                "target": "first uniform; later p=0.5 first, else uniform among others",
                "member_allocation": "two each, remaining agents uniform among units",
                "between_group_offset_s": "uniform [0,90], first unit survives merge"}}


def merge_units(units):
    """Only (target, normalized role) determines identity; timing never splits."""
    result = []
    lookup = {}
    seen = set()
    for unit in units:
        members = unit["members"]
        if not members or len(set(members)) != len(members) or seen.intersection(members):
            raise ValueError("Units must be nonempty disjoint ID sets")
        seen.update(members)
        if unit["role"] not in ROLES:
            raise ValueError("Unknown normalized role")
        key = (unit["target_id"], unit["role"])
        if key not in lookup:
            group = {"group_id": f"task_group_{len(result)+1:02d}", "target_id": key[0],
                     "role": key[1], "execution_method": unit["execution_method"],
                     "between_group_offset_s": unit.get("between_group_offset_s", 0.0),
                     "members": [], "source_units": []}
            lookup[key] = group
            result.append(group)
        lookup[key]["members"].extend(members)
        lookup[key]["source_units"].append(unit["unit_id"])
    for group in result:
        group["members"].sort()
    return result


def derive_intent(groups):
    """Composition of assigned roles, never an observed behavior classifier."""
    roles = {g["role"] for g in groups}
    for intent, role in (("transit", "transit"), ("reconnaissance", "reconnaissance"),
                         ("monitoring", "monitoring"), ("feint", "feint")):
        if roles == {role}:
            return intent
    if "intrusion" in roles and roles <= {"intrusion", "feint", "monitoring"}:
        return "penetration"
    return None


def build_descriptor(scene, family, intent, slot, *, subset="regular"):
    if intent not in INTENTS or subset not in ("regular", "aborted"):
        raise ValueError("Unknown intent/subset")
    if subset == "aborted" and intent != "penetration":
        raise ValueError("Abort subset is reserved for the declared base category")
    common = sample_common(scene, family, slot)
    units = deepcopy(common["units"])
    # Randomness for private role labels cannot perturb common draws or columns.
    ordinal = slot * len(INTENTS) + INTENTS.index(intent)
    role_seed = seed_for(family["sampling_seed"], f"expansion-role-slot:{ordinal}")
    rng = random.Random(role_seed)
    primary = rng.randrange(len(units)) if intent == "penetration" else None
    for i, unit in enumerate(units):
        role = intent
        if intent == "penetration":
            role = "intrusion" if i == primary else rng.choices(
                ["intrusion", "feint", "monitoring"], [.5, .3, .2])[0]
        method = rng.choice(["area_search", "close_observation"]) if role == "reconnaissance" else role
        unit.update(role=role, execution_method=method)
    groups = merge_units(units)
    if derive_intent(groups) != intent:
        raise ValueError("P0: assigned composition disagrees with base category")
    # Fixed numeric stream slots are allocated before any group/role construction.
    column_seed = seed_for(family["sampling_seed"], f"expansion-column-slot:{ordinal}")
    ids = sorted(s["agent_id"] for s in family["initial_states"])
    random.Random(column_seed).shuffle(ids)
    family_snapshot = {k: deepcopy(v) for k, v in family.items()}
    return {"schema_version": VERSION, "skeleton_id": f"{family['family_id']}_ext_{ordinal:03d}_{subset}",
            "family_id": family["family_id"], "map_id": family["map_id"],
            "base_intent": intent, "subset": subset, "status": "awaiting_role_planner",
            "common_draw": common, "units": units, "task_groups": groups,
            "main_unit_id": units[primary]["unit_id"] if primary is not None else None,
            "agent_ids": ids, "column_seed": column_seed, "role_seed": role_seed,
            "cruise_speed_m_s": family["cruise_speed_m_s"],
            "task_altitude_m": family["task_altitude_m"],
            "family_conditions": family_snapshot,
            "role_parameters": {}, "planned_geometry": None,
            "evidence_status": "not_executed"}


def sample_family_descriptors(payload):
    """Top-level pure worker, independent of process count and completion order."""
    scene, family, attempts = payload
    records = [build_descriptor(scene, family, intent, slot)
               for slot in range(attempts) for intent in INTENTS]
    records.append(build_descriptor(scene, family, "penetration", attempts, subset="aborted"))
    return records
