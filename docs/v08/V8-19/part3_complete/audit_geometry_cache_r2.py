"""V8-19 real-input audits. This file is diagnostic only, never a second generator."""
import argparse
import copy
import hashlib
import json
import multiprocessing as mp
import subprocess
import sys
import time
import traceback
import types
from concurrent.futures import ProcessPoolExecutor
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import numpy as np

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
REPO = BASE / "Simulation-v08"
CODE = REPO / "Multi-UAV SimpleGC"
ROOT = BASE / "_handoff/2026-11-08_V8-19_close_observation"
RUN = ROOT / "run"
sys.path.insert(0, str(CODE))

from v08.contract.monitoring import initial_states
from v08.contract.single_intent import mission_for_intent
from v08.motion import formation as F, speed as SP, transit_chords as TC
from v08.motion.intents import close_observation as C, transit as T
from v08.runner.monitoring import canonical_json, jsonable, plan_to_record, failure_record
from v08.sampler.common import sample_common
from v08.sampler.keys import RngKey, rng_for
from v08.scene.context import load_context

ENTRIES = json.loads((REPO / "docs/v08/V8-03/devset_v08.json").read_text(encoding="utf-8"))
BY = {int(e["order"]): e for e in ENTRIES}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(jsonable(value), ensure_ascii=False, indent=1).encode() + b"\n")


def setup(order, draw, intent, cache):
    ctx = load_context(BY[order], data_root=BASE / "SwarmData", cache_dir=Path(cache))
    mission = mission_for_intent(ctx, sample_common(ctx.family, draw), intent)
    group, task = mission.groups[0], mission.tasks[0]
    states = initial_states(ctx.family, group.member_ids)
    key = RngKey(ctx.family.family_id, draw, "shape", mission=0, branch=None, group=group.group_id, segment=0)
    return ctx, group, task, states, key


def plan_doc(plan):
    rec, arrays = plan_to_record(plan)
    return jsonable({"record": rec, "arrays": arrays, "failure": failure_record(plan.failure)})


def digest(value):
    return hashlib.sha256(canonical_json(value)).hexdigest()


def first_difference(a, b, where="$"):
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            return {"where": where, "keys_a": sorted(set(a) - set(b)), "keys_b": sorted(set(b) - set(a))}
        for key in sorted(a):
            found = first_difference(a[key], b[key], where + "." + str(key))
            if found:
                return found
        return None
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return {"where": where, "length_a": len(a), "length_b": len(b)}
        for i, (x, y) in enumerate(zip(a, b)):
            found = first_difference(x, y, f"{where}[{i}]")
            if found:
                return found
        return None
    return None if a == b else {"where": where, "a": a, "b": b}


class TracedRng:
    def __init__(self, key, streams):
        self.actual = rng_for(key)
        self.row = {"key": asdict(key), "initial": copy.deepcopy(self.actual.bit_generator.state), "calls": []}
        streams.append(self.row)

    def __getattr__(self, name):
        value = getattr(self.actual, name)
        if not callable(value):
            return value
        def call(*args, **kwargs):
            out = value(*args, **kwargs)
            self.row["calls"].append({"method": name, "args": jsonable(args), "kwargs": jsonable(kwargs),
                                      "value": jsonable(out), "after": copy.deepcopy(self.actual.bit_generator.state)})
            return out
        return call


def traced_build(mod, args, *, capture=False):
    streams, before = [], {}
    factory = lambda key: TracedRng(key, streams)
    original_add = C.add_dwell
    def add(ctx, plan, rng):
        before["plan"] = plan_doc(plan)
        before["shape_calls"] = len(rng.row["calls"])
        before["shape_state"] = copy.deepcopy(rng.actual.bit_generator.state)
        return original_add(ctx, plan, rng)
    with ExitStack() as stack:
        for module in (mod, F, SP):
            # C delegates construction to T, whose imported rng_for must be traced as well.
            if hasattr(module, "rng_for"):
                stack.enter_context(patch.object(module, "rng_for", factory))
        if mod is C:
            stack.enter_context(patch.object(T, "rng_for", factory))
        if capture:
            stack.enter_context(patch.object(C, "add_dwell", add))
        plan = mod.propose_and_build(*args)
    return plan, streams, before


def oracle_modules():
    modules = []
    for name, relative, package in (("v08.motion._v19_oracle_chords", "v08/motion/transit_chords.py", "v08.motion"),
                                     ("v08.motion.intents._v19_oracle_transit", "v08/motion/intents/transit.py", "v08.motion.intents")):
        raw = subprocess.check_output(["git", "show", "6fe2e11:Multi-UAV SimpleGC/" + relative], cwd=REPO)
        mod = types.ModuleType(name)
        mod.__package__ = package
        sys.modules[name] = mod
        exec(compile(raw, "6fe2e11:" + relative, "exec"), mod.__dict__)
        modules.append(mod)
    modules[1].TC = modules[0]
    return modules[1]


def without_intent_identity(value):
    value = copy.deepcopy(value)
    rec = value["record"]
    rec["proposal"].pop("intent", None)
    rec["proposal"].pop("chord_query_id", None)
    for step in rec["proposal"].get("formation_steps", []):
        step.pop("query_id", None)
    rec["witnesses"].pop("intent", None)
    return value


def prefix_audit(out):
    oracle, rows = oracle_modules(), []
    for order, draw in ((1, 0), (2, 0)):
        begin = time.perf_counter()
        old, old_rng, _ = traced_build(oracle, setup(order, draw, "transit", RUN / "cache"))
        current, cur_rng, _ = traced_build(T, setup(order, draw, "transit", RUN / "cache"))
        new, new_rng, before = traced_build(C, setup(order, draw, C.INTENT, RUN / "cache"), capture=True)
        assert old.failure is None and current.failure is None, "baseline geometry failed"
        old_doc, current_doc = plan_doc(old), plan_doc(current)
        assert old_doc == current_doc, first_difference(old_doc, current_doc)
        assert old_rng == cur_rng, first_difference(old_rng, cur_rng)
        assert before, "new attempt did not reach dwell construction"
        a, b = without_intent_identity(current_doc), without_intent_identity(before["plan"])
        assert a == b, first_difference(a, b)
        assert len(cur_rng) == len(new_rng)
        for x, y in zip(cur_rng, new_rng):
            assert x["key"] == y["key"] and x["initial"] == y["initial"]
            if x["key"]["purpose"] == "shape":
                assert x["calls"] == y["calls"][:before["shape_calls"]]
                assert x["calls"][-1]["after"] == before["shape_state"]
                tail = y["calls"][before["shape_calls"]:]
                assert [c["method"] for c in tail] == ["integers", "integers"]
                assert tail[0]["args"] == [0, new.proposal["dwell"]["set_size"]]
                assert tail[1]["args"] == [200, 1201]
            else:
                assert x == y, first_difference(x, y)
        row = {"key": f"o{order:02d}_d{draw}", "baseline_geometry_equal": True, "baseline_rng_equal": True,
               "new_geometry_prefix_equal": True, "purpose_streams": len(cur_rng), "appended_shape_draws": 2,
               "old_plan_sha256": digest(old_doc), "new_before_dwell_geometry_sha256": digest(b),
               "dwell": (new.proposal or {}).get("dwell"), "failure": failure_record(new.failure),
               "wall_s": time.perf_counter() - begin, "timing": T.last_attempt_timing()}
        rows.append(row)
        write(out / (row["key"] + "_rng.json"), {"baseline": old_rng, "current": cur_rng, "close_observation": new_rng,
                                               "shape_state_before_dwell": before["shape_state"]})
        write(out / (row["key"] + "_plan.json"), plan_doc(new))
        write(out / "summary.json", {"rows": rows, "complete": len(rows) == 2})
        print(json.dumps(row, ensure_ascii=False), flush=True)
        assert new.failure is None, "real selected-curve smoke did not complete"
    return {"complete": True, "rows": rows, "oracle": "6fe2e11", "geometry_normalization":
            ["proposal.intent", "proposal.chord_query_id", "proposal.formation_steps[*].query_id", "witnesses.intent"]}


def build_for_cache(task):
    order, draw, cache = task
    args = setup(order, draw, C.INTENT, cache)
    before = dict(TC.STATS)
    started = time.perf_counter()
    plan = C.propose_and_build(*args)
    payload = plan_doc(plan)
    return {"order": order, "draw": draw, "sha256": digest(payload), "failure": failure_record(plan.failure),
            "chord_cache": {k: TC.STATS[k] - before[k] for k in before}, "wall_s": time.perf_counter() - started}


def cache_audit(out):
    cache = RUN / "cache/part3_cache_audit_r1"
    assert not cache.exists(), "fresh cache required"
    cold, hot = [], []
    for order, draw in ((1, 0), (2, 0)):
        args = setup(order, draw, C.INTENT, cache)
        ctx, group, task, states, key = args
        before = dict(TC.STATS)
        p = C.propose_and_build(*args)
        cold.append({"order": order, "draw": draw, "sha256": digest(plan_doc(p)), "failure": failure_record(p.failure),
                     "chord_cache": {k: TC.STATS[k] - before[k] for k in before}})
        seq = T.formation_probe_sequence(ctx, group, task, key)
        written = TC.prewarm_transit(ctx, [(task.target_id, offsets) for _, _, offsets in seq], cache, intent=C.INTENT)
        write(out / f"o{order:02d}_prewarm.json", written)
        new = build_for_cache((order, draw, str(cache)))
        hot.append(new)
        assert cold[-1]["sha256"] == new["sha256"] and new["failure"] is None
        assert cold[-1]["chord_cache"]["cache_misses_computed"] > 0 and new["chord_cache"]["cache_hits"] > 0
    tasks = [(o, 0, str(cache)) for o in (1, 2)]
    parallel = {}
    for workers in (1, 2):
        with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as ex:
            parallel[str(workers)] = list(ex.map(build_for_cache, tasks))
        assert [r["sha256"] for r in parallel[str(workers)]] == [r["sha256"] for r in hot]
    return {"complete": True, "cold": cold, "hot": hot, "worker_comparison": parallel,
            "scope": "entire plan JSON plus complete geometry arrays; runtime data is external"}


def enumerate_queries(out):
    # These prior transit probe identities are used only to enumerate diagnostic queries, never by new production.
    prior = json.loads((RUN / "out/gates_2_r1/transit/prewarm.json").read_text(encoding="utf-8"))
    rows, unique = [], {}
    for fam in prior["per_family"]:
        order = int(fam["order"])
        for draw_string, evidence in fam["probes"].items():
            draw = int(draw_string)
            ctx, group, task, states, key = setup(order, draw, C.INTENT, RUN / "cache")
            assert task.target_id == evidence["target"]
            start = F.mapped_start(group.formation_prior)
            base_slots = F.formation_slots(group, ctx.family, key, formation=start)
            for name, step, _ in evidence["probes"]:
                slots = F.formation_slots(group, ctx.family, key, formation=name, lateral_step_m=step, order=base_slots.order)
                offsets = [slots.offsets[m] for m in slots.order]
                old_id, _ = TC.query_identity(ctx, task.target_id, offsets)
                assert old_id in {r["query_id"] for r in fam["queries"]}
                new_id, _ = TC.query_identity(ctx, task.target_id, offsets, intent=C.INTENT)
                row = {"order": order, "draw": draw, "target": task.target_id, "n": len(group.member_ids),
                       "formation_prior": group.formation_prior, "formation": name, "lateral_step_m": step,
                       "max_abs_lateral_m": max(abs(d) for _, d in offsets), "map_side_m": BY[order]["map_side_m"],
                       "old_query_id": old_id, "new_query_id": new_id}
                rows.append(row)
                unique[(order, new_id)] = row
    assert len(unique) == prior["queries_total"]
    maximum = max(rows, key=lambda r: (r["n"], r["max_abs_lateral_m"], r["map_side_m"], -r["order"], -r["draw"]))
    counts = {int(e["order"]): sum(order == int(e["order"]) for order, _ in unique) for e in ENTRIES}
    return {"complete": True, "query_count": len(unique), "family_query_counts": counts, "maximum": maximum, "rows": rows,
            "source": "first-round transit's deterministic 40-family 5-draw probe identities, re-derived without chord/LP/dwell computation"}


def maximum_audit(out):
    enumeration = json.loads((RUN / "diagnostics/part3_query_enumeration_r1/summary.json").read_text(encoding="utf-8"))
    row = enumeration["maximum"]
    order, draw = row["order"], row["draw"]
    cache = RUN / "cache/part3_max_query_r1"
    assert not cache.exists()
    ctx, group, task, states, key = setup(order, draw, C.INTENT, cache)
    slots0 = F.formation_slots(group, ctx.family, key, formation=F.mapped_start(group.formation_prior))
    slots = F.formation_slots(group, ctx.family, key, formation=row["formation"], lateral_step_m=row["lateral_step_m"], order=slots0.order)
    ys = [d for _, d in slots.offsets.values()]
    began = time.perf_counter()
    lanes = TC.get_lanes(ctx, task.target_id, 0, ys, intent=C.INTENT)
    TC._sample_lanes(ctx, task.target_id, lanes, intent=C.INTENT)
    lane_cold = time.perf_counter() - began
    began = time.perf_counter()
    TC._sample_lanes(ctx, task.target_id, TC.get_lanes(ctx, task.target_id, 0, ys, intent=C.INTENT), intent=C.INTENT)
    lane_hot = time.perf_counter() - began
    ctx, group, task, states, key = setup(order, draw, C.INTENT, cache)
    started = time.perf_counter()
    cold = TC.load_chord_set(ctx, task.target_id, slots, cache, intent=C.INTENT)
    cold_s = time.perf_counter() - started
    offsets = [slots.offsets[m] for m in slots.order]
    written = TC.prewarm_transit(ctx, [(task.target_id, offsets)], cache, intent=C.INTENT)
    fresh = setup(order, draw, C.INTENT, cache)
    started = time.perf_counter()
    hot = TC.load_chord_set(fresh[0], task.target_id, slots, cache, intent=C.INTENT)
    hot_s = time.perf_counter() - started
    assert all(cold[k] == hot[k] for k in ("cells", "reasons", "n_cells", "query_id"))
    # Compare new intent's cell geometry with the separate, previously built transit identity.
    old_ctx = setup(order, draw, "transit", RUN / "cache")[0]
    old = TC.load_chord_set(old_ctx, task.target_id, slots, RUN / "cache")
    assert all(cold[k] == old[k] for k in ("cells", "reasons", "n_cells"))
    began = time.perf_counter()
    plan = C.propose_and_build(*fresh)
    skeleton_s = time.perf_counter() - began
    timing = T.last_attempt_timing()
    result = {"complete": True, "source": row, "lane_cold_s": lane_cold, "lane_hot_s": lane_hot,
              "chord_cold_s": cold_s, "chord_hot_s": hot_s, "n_cells": cold["n_cells"], "feasible_cells": len(cold["cells"]),
              "cold_hot_equal": True, "transit_cell_geometry_equal": True, "whole_skeleton_s": skeleton_s,
              "attempt_timing": timing, "failure": failure_record(plan.failure), "dwell": (plan.proposal or {}).get("dwell"),
              "prewarm_written": written, "estimated_total_work_s": cold_s * enumeration["query_count"],
              "estimated_total_divided_by24_s": cold_s * enumeration["query_count"] / 24,
              "estimated_max_family_work_s": cold_s * max(enumeration["family_query_counts"].values()),
              "estimate_scope": "maximum actual query times deterministic query counts, not a measured upper bound; LP/dwell excluded from prewarm"}
    write(out / "plan.json", plan_doc(plan))
    return result


def main():
    mode = argparse.ArgumentParser()
    mode.add_argument("mode", choices=("prefix", "cache", "enumeration", "maximum"))
    arg = mode.parse_args().mode
    names = {"prefix": "part3_geometry_rng_r2", "cache": "part3_cache_audit_r1", "enumeration": "part3_query_enumeration_r1", "maximum": "part3_maximum_r1"}
    out = RUN / "diagnostics" / names[arg]
    out.mkdir(exist_ok=False)
    started = time.perf_counter()
    try:
        result = {"prefix": prefix_audit, "cache": cache_audit, "enumeration": enumerate_queries, "maximum": maximum_audit}[arg](out)
        result["wall_s"] = time.perf_counter() - started
        write(out / "summary.json", result)
        print(json.dumps({k: v for k, v in result.items() if k not in ("rows", "worker_comparison")}, ensure_ascii=False), flush=True)
    except Exception as exc:
        write(out / "failure.json", {"error": repr(exc), "traceback": traceback.format_exc(), "wall_s": time.perf_counter() - started})
        raise


if __name__ == "__main__":
    main()
