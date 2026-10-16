"""New geometry production adapter; no old Context or role-draw calls."""
from collections import Counter
import random
import time

from task_v07.expansion.pipeline import assemble_skeleton, exclusion_policy, precheck
from task_v07.expansion.search_diagnostics import rejection
from .spec import build_spec, proposal_seed
from .free_space import free_space, work_region
from .shapes import draw_shape
from .route import route_group, GeometryRejected
from .checks import plan_checks


def build_unified_pool(scene, descriptor, group, budget, *, on_record=None):
    spec = build_spec(descriptor, group)
    started = time.perf_counter()
    free = free_space(scene, spec)
    region = work_region(scene, spec, free)
    records = []; pool = []; reasons = Counter()
    for index in range(budget):
        rng = random.Random(proposal_seed(spec, index))
        record = {"candidate_index": index, "proposal_id": f"{group['group_id']}:{index}", "group_id": group["group_id"],
                  "stage": "shape", "reason": None, "rejection": None,
                  "draws_by_group": {group["group_id"]: {"proposal_seed": proposal_seed(spec, index)}}}
        try:
            shape = draw_shape(spec, region, rng, free)
            record["draws_by_group"][group["group_id"]]["shape"] = shape["draw"]
            record["stage"] = "connection"
            bundle, template = route_group(scene, spec, shape, free, descriptor["family_conditions"]["initial_states"], rng)
            template["task_spec"] = spec
            record["stage"] = "whole_route"
            checks = plan_checks(scene, spec, bundle, template, free, descriptor["family_conditions"]["initial_states"])
            record["whole_route_checks"] = checks
            if checks["status"] != "PASS":
                raise GeometryRejected("whole_route_check", checks["issues"])
            # Assemble directly so P0ContractError is never caught as a ValueError.
            skeleton = assemble_skeleton(descriptor, group, bundle, template, False)
            policy = exclusion_policy(scene, group["role"], group["target_id"], group["members"])
            skeleton["exclusion_policy"] = policy
            existing = precheck(scene, skeleton, bundle, policy)
            if existing["status"] != "PASS":
                raise GeometryRejected("existing_output_precheck", [existing])
            skeleton["agent_ids"] = [a for a in descriptor["agent_ids"] if a in group["members"]]
            skeleton["between_group_offset_s"] = group["between_group_offset_s"]
            checks["existing_precheck"] = existing
            pool.append({"index": index, "cost": template["approach_length_m"], "skeleton": skeleton,
                         "bundle": bundle, "checks": checks, "bearing_deg": template["work_area_bearing_deg"],
                         "target_id": group["target_id"]})
            record.update(stage="group_feasible", approach_length_m=template["approach_length_m"])
        except GeometryRejected as exc:
            record.update(reason=exc.reason, rejection=rejection(exc.reason, scope="proposal",
                evidence=exc.evidence, exhausted=exc.reason.endswith("budget_exhausted")))
            reasons[exc.reason] += 1
        records.append(record)
        if on_record is not None:
            on_record(record)
    wall = time.perf_counter()-started
    return pool, {"records": records, "rejection_reasons": dict(reasons),
        "metrics": {"attempts": len(records), "budget": budget, "feasible_candidates": len(pool),
                    "wall_s": wall, "geometry_wall_s": wall, "backend": "unified", "phase_search": {"evaluations": 0, "wall_s": 0.}},
        "termination": rejection("group_pool_empty_after_registered_budget", scope="group_search", exhausted=True) if not pool else None}
