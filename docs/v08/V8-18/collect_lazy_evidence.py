"""只读整理 V8-18 按需判空骨架证据，不参与生成器决策。"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np

REPO = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-v08")
sys.path.insert(0, str(REPO / "Multi-UAV SimpleGC"))

BAD = {"seconds", "wall_s", "wall_time", "elapsed_s", "elapsed_seconds", "cpu_s", "prepare_s", "solve_s",
       "check_s", "optimization_s", "timing", "stage_timing", "skeleton_detail", "build_seconds", "attempt_wall_s",
       "attempt_s", "skeleton_s", "optimize_s", "simulation_s", "verify_s", "lp_s", "chord_set_s", "chord_exact_s",
       "corridor_s", "route_s", "candidate_s", "prewarm_s", "cache_hits", "cache_misses_computed", "traceback",
       "tracebacks", "pid", "path", "cache_dir", "data_root", "out_dir", "probe_s", "root_pid"}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def scan(value, at=""):
    if isinstance(value, dict):
        for key, child in value.items():
            loc = at + "/" + key
            if key in BAD or key.endswith("_path"):
                yield loc
            yield from scan(child, loc)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from scan(child, at + "/" + str(i))
    elif isinstance(value, str) and (re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith("file://")
                                    or "Traceback (most recent call last)" in value):
        yield at


def distribution(values):
    values = [float(x) for x in values if x is not None]
    if not values:
        return None
    quantiles = np.quantile(values, [0, .25, .5, .75, .9, .95, 1])
    return {"n": len(values), "mean": float(np.mean(values)),
            **dict(zip(("min", "p25", "median", "p75", "p90", "p95", "max"), map(float, quantiles)))}


def scene_audit(root, row, entries, data, cache):
    from v08.contract.monitoring import TaskSpec
    from v08.motion import feint_turn as FT
    from v08.motion.connect import crossing_analysis
    from v08.motion.intrusion_numeric import preentry_clearance_ok
    from v08.motion.layer_limits import constraints_for_task
    from v08.motion.path import sample_primitives
    from v08.scene.context import load_context
    from v08.scene.exact import signed_distance
    ctx = load_context(entries[row["family_id"]], data_root=data, cache_dir=cache)
    doc = read(root / "contracts" / row["contract_id"] / "skeleton.json")
    proposal, witness = doc["proposal"], doc["witnesses"]
    target = ctx.facility_by_id[row["target_id"]]
    cons = constraints_for_task(ctx, TaskSpec("task0", "feint", target.id))
    lanes, members = {}, {}
    for mid, member in doc["members"].items():
        xy = np.asarray(doc["arrays"][member["curve_xy"]["npz"]], float)
        cumulative = np.r_[0.0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))]
        mapping = witness["member_map_feint"]["members"][mid]
        stations = np.asarray(mapping["member_s"])
        # member_s 是原曲线顶点的真实累计弧长；相同公式定位，避免新插值导致几何扰动。
        indices = np.searchsorted(cumulative, stations)
        exact_nodes = np.array_equal(cumulative[indices], stations)
        lane_xy = xy[indices]
        lanes[mid] = NS(xy=lane_xy, s_ref=np.asarray(mapping["shifted_reference_s"]),
                        s_group=np.asarray(mapping["reference_s"]))
        violations, crossings = crossing_analysis(xy, cons["crossing_boundaries"], target.id,
            band_m=ctx.params["pre_entry_warning_clearance_m"], align_m=ctx.params["alignment_length_m"])
        directions = {k: [c.direction for c in crossings if c.facility_id == k]
                      for k in (target.id, "__crossing__" + target.id + "::alert")}
        entry = sample_primitives(proposal["start_connections"][mid], ctx.params["curve_spacing_m"]).xy
        terminal = {f.id: float(signed_distance(f.layers["warning"], xy[-1])) for f in ctx.facilities}
        turn = witness["turn_ranges"].get(mid) or []
        members[mid] = {"exact_mapping_nodes": exact_nodes, "base_pass": FT.clearance_passes(cons["base"], xy),
            "crossing_violations": violations, "directions": directions,
            "preentry_ok": preentry_clearance_ok(target.layers["warning"], entry, 10.0),
            "terminal_warning_sdf_m": terminal, "turn_nonempty": bool(turn) and all(t[2] > t[1] for t in turn),
            "min_protected_sdf_m": float(np.min(signed_distance(target.layers["protected"], xy)))}
    support, first = FT.deformation_passes(lanes, witness["schedule_feint"], target.layers["alert"],
        target.layers["protected"], cons["crossing_boundaries"], band_m=10.0, detail=True)
    upper = proposal["corridor"].get("inset_interval")
    alert = proposal["corridor"].get("alert_interval")
    lp_upper = upper is None or alert is None or upper[1] <= alert[0]
    passed = support and lp_upper and all(m["exact_mapping_nodes"] and m["base_pass"]
        and not m["crossing_violations"] and all(ds == ["in", "out"] for ds in m["directions"].values())
        and m["preentry_ok"] and m["turn_nonempty"] and min(m["terminal_warning_sdf_m"].values()) >= 50.0
        for m in members.values())
    return {"passed": bool(passed), "support_pass": support, "support_first_failure": first,
            "lp_upper_pass": lp_upper, "members": members}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", action="append", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--scene-audit", action="store_true")
    args = parser.parse_args()
    entries_doc = read(REPO / "docs/v08/V8-03/devset_v08.json")
    entries = {e["family_id"]: e for e in (entries_doc["families"] if isinstance(entries_doc, dict) else entries_doc)}
    data = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData")
    cache = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-06_V8-18_feint\run\cache")
    from v08.scene.context import load_context
    from v08.scene.exact import polyline_clearance
    rows, probes, contracts, bad, audits, turn_rows, protected_rows = [], [], [], [], [], [], []
    contexts, screen_stats = {}, Counter()
    for text in args.root:
        root = Path(text)
        for row in read(root / "records.json"):
            rows.append(row)
            tele = read(root / "telemetry" / (row["contract_id"] + ".json"))
            contract_probes = [p for tm in tele["timing"] for p in tm.get("cell_probes", [])]
            probes.extend(contract_probes)
            for probe in contract_probes:
                screen_stats.update(probe.get("stats", {}))
            contract = {"contract_id": row["contract_id"], "success": row["success"], "attempts": row["attempts"],
                        "wall_s": row.get("wall_s"), "formation": row.get("formation"), "probes": contract_probes}
            if row["success"]:
                skeleton = read(root / "contracts" / row["contract_id"] / "skeleton.json")
                contract["repairs"] = skeleton["repairs"]
                proposal = skeleton["proposal"]
                turn_rows.append({"contract_id": row["contract_id"], "group_size": row["group_size"],
                    "formation": row["formation"]["realized"], "L_m": proposal["L_m"],
                    "turn": proposal["turn"], "nonempty_combos": proposal["nonempty_combos"]})
                fid = row["family_id"]
                if fid not in contexts:
                    contexts[fid] = load_context(entries[fid], data_root=data, cache_dir=cache)
                protected = contexts[fid].facility_by_id[row["target_id"]].layers["protected"]
                for mid, member in skeleton["members"].items():
                    xy = np.asarray(skeleton["arrays"][member["curve_xy"]["npz"]], float)
                    minimum = float(np.min(polyline_clearance(protected, xy, sense=1, minimum_m=0,
                                                             fast_far_m=None)))
                    protected_rows.append({"contract_id": row["contract_id"], "member": mid,
                                           "min_protected_sdf_m": minimum})
                if args.scene_audit:
                    audit = {"contract_id": row["contract_id"], **scene_audit(root, row, entries, data, cache)}
                    audits.append(audit)
            for file in (root / "contracts" / row["contract_id"]).rglob("*.json"):
                bad.extend({"file": str(file), "location": at} for at in scan(read(file)))
            contracts.append(contract)
    pairs = Counter((r["formation"].get("prior"), r["formation"].get("realized"))
                    for r in rows if r.get("success"))
    output = {"contracts": len(rows), "successes": sum(r["success"] for r in rows),
        "exceptions": sum(r.get("exceptions", 0) for r in rows), "contract_wall_s": distribution(r.get("wall_s") for r in rows),
        "probes_total": len(probes), "cells_examined": distribution(p["cells_examined"] for p in probes),
        "successful_probe_positions": distribution(p["nonempty_position"] for p in probes),
        "empty_probes": sum(p["nonempty_position"] is None for p in probes),
        "formation_pairs": [{"prior": p, "realized": r, "n": n} for (p, r), n in sorted(pairs.items())],
        "retreated_contracts": sum(any(r.get("kind") in ("formation_retreat", "echelon_lateral_step")
                                      for r in c.get("repairs", [])) for c in contracts),
        "kind_side": dict(Counter(f"{r['turn']['kind']}:{r['turn']['side']}" for r in turn_rows)),
        "kind_side_by_nonempty_combos": {str(n): dict(Counter(f"{r['turn']['kind']}:{r['turn']['side']}"
            for r in turn_rows if r["nonempty_combos"] == n)) for n in sorted({r["nonempty_combos"] for r in turn_rows})},
        "A_m": distribution(r["turn"]["A_m"] for r in turn_rows),
        "radius_m": distribution(r["turn"]["radius_m"] for r in turn_rows),
        "L_by_formation_size": {f"{f}|n{n}": distribution(r["L_m"] for r in turn_rows
            if r["formation"] == f and r["group_size"] == n) for f, n in
            sorted({(r["formation"], r["group_size"]) for r in turn_rows})},
        "min_protected_sdf_m": distribution(r["min_protected_sdf_m"] for r in protected_rows),
        "screen_stats_existence_only": dict(screen_stats),
        "screen_stats_scope": "首次逐格存在性查询；内存命中不重复计数；不含组合随机抽样中的调用",
        "protected_members": protected_rows, "turn_rows": turn_rows,
        "payload_violations": bad, "scene_audits": audits, "rows": contracts}
    Path(args.out).write_text(json.dumps(output, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in output.items() if k not in ("rows", "scene_audits", "payload_violations",
                      "protected_members", "turn_rows", "L_by_formation_size", "screen_stats_existence_only")},
                     ensure_ascii=False))
    if bad or output["exceptions"] or any(r.get("error") for r in rows) or any(not a["passed"] for a in audits):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
