"""Independent per-version deterministic timing draws; never mutate geometry."""
from copy import deepcopy
import math
import random
from task_v07.planning import seed_for
from .config import load_generator

MODES = ("synchronous", "sequential")


def group_plan(group, measured, mode, draw=0):
    cfg = load_generator()["timing"]
    ids = sorted(group["members"])
    if mode not in MODES or not 0 <= draw < cfg["redraw_budget_per_version"]:
        raise ValueError("Invalid timing version or draw index")
    if set(ids) != set(measured) or any(t is None or not math.isfinite(t) for t in measured.values()):
        raise ValueError("All registered solo event times must be measured")
    if len(ids) < 2: raise ValueError("Paired timing requires at least two group members")
    seed = seed_for(group["column_seed"], f"timing_v3:{group['group_id']}:{mode}:{draw}")
    rng = random.Random(seed)
    batches = [ids]
    gaps = []
    if mode == "sequential":
        shuffled = ids[:]; rng.shuffle(shuffled)
        count = rng.randint(2, len(ids))
        cuts = [0, *sorted(rng.sample(range(1, len(ids)), count - 1)), len(ids)]
        batches = [shuffled[begin:end] for begin, end in zip(cuts[:-1], cuts[1:])]
        gaps = [rng.uniform(*cfg["sequential_gap_range_s"]) for _ in range(count - 1)]
    centers = [max(measured.values()) + cfg["first_batch_lead_s"]]
    for gap in gaps: centers.append(centers[-1] + gap)
    batch_by_agent = {a: i for i, members in enumerate(batches) for a in members}
    jitter = {a: rng.uniform(-cfg["jitter_halfwidth_s"], cfg["jitter_halfwidth_s"]) for a in ids}
    targets = {a: centers[batch_by_agent[a]] + jitter[a] for a in ids}
    quantum = cfg["quantization_s"]
    delays = {a: round(round((targets[a] - measured[a]) / quantum) * quantum, 10) for a in ids}
    grid_targets = {a: round(measured[a] + delays[a], 10) for a in ids}
    spans = [max(grid_targets[a] for a in batch) - min(grid_targets[a] for a in batch) for batch in batches]
    if min(delays.values()) < 0 or any(span > cfg["batch_span_max_s"] + 1e-9 for span in spans):
        raise ValueError("Timing draw violates delay or batch-span invariant")
    return {"schema_version": "v07_timing_plan_v3", "mode": mode, "draw": draw, "random_seed": seed,
            "batch_by_agent": batch_by_agent, "batch_count": len(batches), "batch_sizes": [len(b) for b in batches],
            "batch_centers_s": centers, "inter_batch_gaps_s": gaps, "batch_spans_s": spans,
            "jitter_s": jitter, "jitter_span_s": max(jitter.values()) - min(jitter.values()),
            "jitter_halfwidth_s": cfg["jitter_halfwidth_s"], "target_event_times_s": targets,
            "target_event_times_grid_s": grid_targets, "departure_delays_s": delays,
            "single_agent_measured_core_times_s": dict(measured), "quantization_s": quantum,
            "maximum_quantization_error_s": quantum / 2, "basis": "M1 solo core-event onset, independent version/group/draw seed"}


def episode_plan(skeleton, measured, mode, draw=0):
    groups = skeleton.get("group_skeletons", {skeleton.get("group_id"): skeleton})
    result = {"schema_version": "v07_group_timing_plan_v3", "mode": mode, "draw": draw, "by_group": {},
              "departure_delays_s": {}, "batch_by_agent": {}, "basis": "independent per-group draw plus registered group offset"}
    for gid, group in sorted(groups.items()):
        plan = deepcopy(group_plan(group, {a: measured[a] for a in group["members"]}, mode, draw))
        offset = group.get("between_group_offset_s", 0.)
        for key in ("target_event_times_s", "target_event_times_grid_s", "departure_delays_s"):
            plan[key] = {a: round(value + offset, 10) for a, value in plan[key].items()}
        plan["batch_centers_s"] = [value + offset for value in plan["batch_centers_s"]]
        plan["between_group_offset_s"] = offset
        result["by_group"][gid] = plan
        result["departure_delays_s"].update(plan["departure_delays_s"])
        result["batch_by_agent"].update(plan["batch_by_agent"])
    return result
