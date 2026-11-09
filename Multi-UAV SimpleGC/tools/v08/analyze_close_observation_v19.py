"""Read saved V8-19 outputs: five-intent outer join, failure tables, geometry and dwell diagnostics."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

PROJ = Path(__file__).resolve().parents[2]
if str(PROJ) not in sys.path:
    sys.path.insert(0, str(PROJ))


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def failure_tables(documents):
    semantic, first_semantic, physical, stages = Counter(), Counter(), Counter(), Counter()
    for doc in documents:
        failed = sorted((a for a in doc.get("attempt_log", []) if not a["ok"]), key=lambda a: a["attempt"])
        for a in failed:
            stages[a.get("skeleton_stage") or a["stage"]] += 1
            opt = a.get("optimize") or {}
            if a["stage"] == "optimize_close_observation":
                semantic.update({f["kind"] for f in (opt.get("semantic_failures") or [])})
            if a["stage"] == "optimize":
                physical.update({f["kind"] for f in (opt.get("physical_failures") or [])})
        if failed and failed[0]["stage"] == "optimize_close_observation":
            first_semantic.update({f["kind"] for f in ((failed[0].get("optimize") or {}).get("semantic_failures") or [])})
    return {"all_failed_attempt_semantic_once_per_subclass": dict(semantic),
            "first_failed_attempt_per_contract_if_semantic": dict(first_semantic),
            "physical_once_per_attempt_subclass": dict(physical), "failure_stages": dict(stages)}


def selected_geometry(skeleton):
    # Business geometry only: all member curves/speed events/delays, LP, connections and formation.
    import copy
    proposal = copy.deepcopy(skeleton["proposal"])
    for k in ("intent", "chord_query_id", "dwell"):
        proposal.pop(k, None)
    for step in proposal.get("formation_steps", []):
        step.pop("query_id", None)
    return {"members": skeleton["members"], "arrays": skeleton["arrays"], "anchors": skeleton["anchors"],
            "formation": skeleton["formation"], "proposal": proposal}


def analyze(roots):
    from v08.runner.close_observation_report import five_intent_pairs
    from v08.runner.skeleton_monitoring import _distribution
    paired = five_intent_pairs(roots)
    full = Path(roots["close_observation"])
    geometry, docs, stats = [], [], {}
    def add(k, value):
        if value is not None:
            stats.setdefault(k, []).append(value)
    for label, directory in (("main", full), ("diversity", full / "diversity")):
        for row in read(directory / "records.json"):
            folder = directory / "contracts" / row["contract_id"]
            doc = read(folder / "result.json")
            # Failure tables retain only the fields needed for counts, not large nominal levels.
            count_log = []
            for a in doc["attempt_log"]:
                item = {k: a.get(k) for k in ("attempt", "ok", "stage", "skeleton_stage")}
                item["optimize"] = {k: (a.get("optimize") or {}).get(k) for k in ("semantic_failures", "physical_failures")}
                count_log.append(item)
            docs.append({"attempt_log": count_log})
            if not doc["success"]:
                if label == "main":
                    old_result = read(Path(roots["transit"]) / "contracts" / row["contract_id"] / "result.json")
                    geometry.append({"contract_id": row["contract_id"], "close_attempt": None,
                        "transit_attempt": old_result["attempts"] - 1 if old_result["success"] else None,
                        "geometry_equal": None, "same_attempt": False, "classification": "close_failed", "close_dwell": None})
                continue
            skeleton = read(folder / "skeleton.json")
            diag = skeleton["witnesses"]["dwell_diagnostics"]
            add("set_size", diag["set_size"])
            add("duration_ticks", doc["close_observation"]["duration_ticks"])
            add("member_arrival_span_s", diag["member_arrival_span_s"])
            add("pd_min_pair_distance_m", diag["pd_min_pair_distance_m"])
            for m, values in doc["phase_durations"].items():
                add("nominal_endpoint_distance_m", diag["members"][m]["endpoint_distance_m"])
                for k, v in values.items():
                    add(k, v)
                for k, v in doc["phase_metrics"][m].items():
                    if k not in ("phases", "member_arrival_span_s") and isinstance(v, (int, float)):
                        add(k, v)
                for k, v in doc["close_observation"]["members"][m].items():
                    if k.endswith("_sdf_m") or k == "base_min_margin_m":
                        add(k, v)
            if label == "main":
                other = Path(roots["transit"]) / "contracts" / row["contract_id"]
                old_result = read(other / "result.json")
                selected = lambda p: {k: p.get(k) for k in ("cell_index", "theta_deg", "h_m", "collect_D_m", "formation",
                    "curved", "fallback_reason", "lp", "start_connections", "speed_events")}
                record = {"contract_id": row["contract_id"], "close_attempt": doc["attempts"] - 1,
                          "transit_attempt": old_result["attempts"] - 1 if old_result["success"] else None,
                          "close_dwell": skeleton["proposal"]["dwell"], "close_selected": selected(skeleton["proposal"])}
                if old_result["success"]:
                    old_skeleton = read(other / "skeleton.json")
                    equal = selected_geometry(skeleton) == selected_geometry(old_skeleton)
                    record["transit_selected"] = selected(old_skeleton["proposal"])
                    record.update(geometry_equal=equal, same_attempt=doc["attempts"] == old_result["attempts"],
                                  classification="same_attempt" if doc["attempts"] == old_result["attempts"] else "different_retained_attempt")
                else:
                    record.update(geometry_equal=None, same_attempt=False, classification="transit_failed")
                geometry.append(record)
    # Remove large semantic member arrays before retaining per-attempt count inputs.
    for doc in docs:
        for a in doc["attempt_log"]:
            opt = a.get("optimize")
            if opt is not None:
                a["optimize"] = {k: opt.get(k) for k in ("semantic_failures", "physical_failures")}
    return paired, {"failure_tables_scope": "all main200 and diversity100 contracts; failed attempts deduplicated by subclass",
        "failure_tables": failure_tables(docs), "retained_distributions": {k: _distribution(v) for k, v in stats.items()},
        "geometry_pairs": geometry, "same_attempt_geometry_differences": [r for r in geometry if r["same_attempt"] and not r["geometry_equal"]],
        "note": "same-attempt geometry prefix is separately audited; independently retained attempts may differ"}


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ("monitoring", "transit", "intrusion", "feint", "close-observation", "out"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    from v08.runner.monitoring import guard_path, write_json
    out = guard_path(args.out, label="分析输出", must_not_exist=True)
    out.mkdir(parents=True, exist_ok=False)
    roots = {name: getattr(args, name) for name in ("monitoring", "transit", "intrusion", "feint", "close_observation")}
    pairs, diagnostics = analyze(roots)
    write_json(out / "five_intent_pairs.json", pairs, indent=1)
    write_json(out / "diagnostics.json", diagnostics, indent=1)
    print(json.dumps({"contracts": pairs["contracts"], "common_differences": len(pairs["common_differences"]),
                      "same_attempt_geometry_differences": len(diagnostics["same_attempt_geometry_differences"])}, ensure_ascii=False))
    return 0 if pairs["contracts"] == 200 and not pairs["common_differences"] and not diagnostics["same_attempt_geometry_differences"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
