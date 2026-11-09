"""V8-20 explicit area_search entry. Geometry is implemented in execution part 3."""
from ...contract.monitoring import Failure

INTENT = "area_search"
_LAST_TIMING = {}


def propose_and_build(ctx, group, task, states, key):
    if task.intent != INTENT:
        raise ValueError("area_search builder requires its explicit intent")
    raise NotImplementedError("V8-20 area_search geometry: execution part 3 not completed")


def last_attempt_timing():
    return dict(_LAST_TIMING)


def draw_summary(proposal, formation):
    p = proposal or {}
    keys = ("theta_idx","theta_deg","h_m","cell_index","cells_feasible","collect_D_m","mu_deg","span_deg","c","K","beta_deg","Q")
    return {"intent": INTENT,"formation":formation,**{k:p[k] for k in keys if k in p}}


def final_failure(ctx, group, task, attempt_records):
    records = list(attempt_records)
    stages = [r.get("stage") for r in records]
    empty = bool(stages) and all(s == "area_search_entry" for s in stages)
    code = "approx_empty" if empty else "budget_exhausted"
    return Failure(code,code,"area_search_entry" if empty else None,
                   {"attempts":len(records),"stages":stages},None)
