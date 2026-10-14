"""Planning-only smoke test: report spatial separation of planned routes."""
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, ".")
from scripts.run_v07_s2_expansion import descriptor_jobs, INFRA_ATTEMPT
from task_v07.expansion.role_planners import planner_for, PlanningInfeasible
from task_v07.expansion.pipeline import plan_group

SKELS = [
    "family_s12_4d13d93f9171c446_ext_001_regular",
    "family_s12_4d13d93f9171c446_ext_002_regular",
    "family_s12_4d13d93f9171c446_ext_003_regular",
    "family_s12_4d13d93f9171c446_ext_004_regular",
    "family_s12_aa4c66be8e85d64d_ext_001_regular",
    "family_s12_aa4c66be8e85d64d_ext_002_regular",
    "family_s12_aa4c66be8e85d64d_ext_003_regular",
    "family_s12_aa4c66be8e85d64d_ext_004_regular",
]

jobs = descriptor_jobs(INFRA_ATTEMPT, SKELS, Path("."))
for job in jobs:
    scene, desc = job["scene"], job["descriptor"]
    for gi, group in enumerate(desc["task_groups"]):
        tag = f"{desc['skeleton_id']}[g{gi}:{group['role']}]"
        try:
            planner = planner_for(group["role"], group["execution_method"])
            sk, bundle, pre = plan_group(scene, desc, group, planner)
        except PlanningInfeasible as exc:
            print(f"{tag}: INFEASIBLE {exc.category} :: {exc.detail}")
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"{tag}: ERROR {type(exc).__name__}: {exc}")
            continue
        routes = {a: np.array(bundle.waypoints_by_agent[a])[:, :2] for a in group["members"]}
        ids = sorted(routes)
        if len(ids) < 2:
            print(f"{tag}: precheck={pre['status']} n=1 (no separation check)")
            continue
        worst = min(
            float(np.linalg.norm(routes[i][:, None, :] - routes[j][None, :, :], axis=2).min())
            for x, i in enumerate(ids) for j in ids[x + 1:]
        )
        eps = [np.array(sk["references"][a]["endpoint_enu_m"][:2]) for a in ids]
        ep_worst = min(float(np.linalg.norm(eps[x] - eps[y]))
                       for x in range(len(eps)) for y in range(x + 1, len(eps)))
        print(f"{tag}: precheck={pre['status']} spatial_min={worst:.2f}m endpoint_min={ep_worst:.2f}m")
