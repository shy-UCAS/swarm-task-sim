"""Q1: read-only source attempts -> new criteria-r1 labels, audits and evidence."""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import argparse
import csv
import hashlib
import json
import shutil
import sys
import time
import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from task_v07.io import read_json, save_json, sha
from task_v07.labels import measure
from task_v07.expansion.views import make_views
from scripts.audit_v07_m1 import audit_episode
from scripts.cross_v07_m1 import cross_group, role_kind

ATTEMPTS = ("attempt_s2x_final_20261014T164338Z_4f85aaa3",
            "attempt_s2x_final_20261015T053115Z_a3b834e8",
            "attempt_s2_search_quick_b_20261015T090658Z_5ac915b5")
COPY = ("truth_10hz.npz", "truth.csv", "model_input.npz", "observations.csv", "public_scene.json", "task.json", "source.json")


def write_evidence(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def agent_witness(agent, labels, frame, task):
    value = labels["agents"][agent]; ob = value["observed"]; i = frame["agent_ids"].tolist().index(agent)
    target = frame["region_assigned_target"][:, i]
    groups = task.get("group_skeletons", {task.get("group_id"): task})
    group = groups[value["assigned"]["task_group"]]
    fids = frame["facility_ids"].tolist(); levels = frame["region_all_facilities"][:, i]
    from task_v07.criteria import load_criteria
    cfg = load_criteria(); limits = cfg["exclusion_max_layer"]
    violation = np.zeros(len(target), bool)
    for j, fid in enumerate(fids): violation |= levels[:, j] > (limits[group["role"]] if fid == group["target_id"] else limits["other_facilities"])
    bad = np.flatnonzero(violation)
    visits = np.flatnonzero((target >= 1) & ~np.r_[False, target[:-1] >= 1]).tolist()
    alerts = np.flatnonzero((target >= 2) & ~np.r_[False, target[:-1] >= 2]).tolist()
    c = ob["contribution"]
    return {"last_frame": len(target) - 1, "last_time_s": float(frame["time_us"][-1] / 1e6), "last_target_layer": int(target[-1]),
        "warning_visit_start_frames": visits, "alert_visit_start_frames": alerts,
        "first_forbidden_frame": int(bad[0]) if len(bad) else None,
        "first_forbidden_time_s": float(frame["time_us"][bad[0]] / 1e6) if len(bad) else None,
        "core_event": ob["core_event"], "minimum_contour_distance_m": c["minimum_contour_distance_m"],
        "minimum_contour_distance_frame": c["minimum_contour_distance_frame"],
        "dwell": c["dwell"], "observation_dwell": c.get("observation_dwell"), "revisit": c["revisit"],
        "abort": c.get("abort_observation"), "failed_conditions": [k for k, v in value["result"]["conditions"].items() if v is False]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=PROJECT.parent.parent / "SwarmData/v07_dataset")
    args = parser.parse_args(); data = args.data_root.resolve()
    output = data / ("relabel_m1_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    if output.exists() or output.resolve().parent != data: raise ValueError("Output must be a new direct child of dataset root")
    for name in ATTEMPTS:
        if not (data / name / "episode_records.json").is_file(): raise FileNotFoundError(name)
    output.mkdir(); evidence_root = PROJECT / "docs/v07/evidence/m1"; evidence_root.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter(); changes = []; new_failures = []; episodes = []; cross_rows = []
    counts = Counter(); detector_counts = Counter(); approach = defaultdict(Counter); summaries = []
    pending = None
    try:
        for name in ATTEMPTS:
            source_attempt = data / name; destination = output / name; destination.mkdir()
            records = read_json(source_attempt / "episode_records.json"); updated = []; processed = 0
            for row in records: row["inventory_scope"] = "main"
            for registry in sorted(source_attempt.glob("process_*/episode_records.json")):
                relative = registry.parent.relative_to(source_attempt).as_posix()
                for original in read_json(registry):
                    row = deepcopy(original)
                    row.update(inventory_scope=relative, diagnostic_only=True, source_episode_id=row["episode_id"],
                               episode_id=relative + ":" + row["episode_id"])
                    if row.get("path"): row["path"] = relative + "/" + row["path"]
                    records.append(row)
            # Rows with artifact paths include quality-excluded and aborted episodes.
            source_paths = [row["path"] for row in records if row.get("path")]
            if len(set(source_paths)) != len(source_paths): raise ValueError("P0: duplicate episode paths")
            actual_paths = {p.parent.relative_to(source_attempt).as_posix() for p in source_attempt.glob("**/labels.json")
                            if (p.parent / "truth_10hz.npz").is_file() and (p.parent / "manifest.json").is_file()}
            if set(source_paths) != actual_paths:
                raise ValueError(f"P0: record/file inventory differs: missing={set(source_paths)-actual_paths}, unlisted={actual_paths-set(source_paths)}")
            for record in records:
                row = deepcopy(record)
                collection = row["inventory_scope"]
                if not row.get("path"):
                    updated.append(row); continue
                source = (source_attempt / row["path"]).resolve(); dest = destination / row["path"]
                if not source.is_relative_to(source_attempt.resolve()) or not dest.resolve().is_relative_to(destination.resolve()):
                    raise ValueError("P0: episode path escaped attempt")
                pending = {"attempt": name, "episode_id": row["episode_id"], "source": str(source), "destination": str(dest)}
                manifest = read_json(source / "manifest.json")
                source_hashes = {}
                for filename, digest in manifest["artifact_sha256"].items():
                    if Path(filename).name != filename: raise ValueError("P0: invalid manifest path")
                    actual = sha(source / filename); source_hashes[filename] = actual
                    if actual != digest: raise ValueError("P0: source manifest hash mismatch: " + filename)
                task, scene, metadata, old = (read_json(source / filename) for filename in ("task.json", "public_scene.json", "source.json", "labels.json"))
                with np.load(source / "truth_10hz.npz", allow_pickle=False) as saved:
                    run = {key: saved[key].copy() for key in ("time_us", "p", "v", "a") if key in saved.files}
                    run["agent_ids"] = saved["agent_ids"].tolist()
                run["execution_status"] = metadata["execution_status"]
                labels, frame = measure(scene, task, run, metadata["planned_coordination"], timing_plan=metadata.get("timing_plan"))
                dest.mkdir(parents=True)
                for filename in COPY:
                    shutil.copy2(source / filename, dest / filename)
                    if sha(dest / filename) != source_hashes[filename]: raise ValueError("P0: copied source mismatch")
                save_json(dest / "labels.json", labels); np.savez_compressed(dest / "frame_labels.npz", **frame)
                save_json(dest / "relabel_source.json", {"source_directory": str(source), "source_artifact_sha256": source_hashes,
                    "criteria_version": "criteria/0.7-r1", "no_simulation": True})
                receipt = audit_episode(dest); save_json(dest / "independent_exact_audit.json", receipt)
                if receipt["status"] != "PASS":
                    raise ValueError("P0: independent audit mismatch; see " + str(dest / "independent_exact_audit.json"))
                group_templates = task.get("group_skeletons", {task.get("group_id"): task})
                for gid, group in group_templates.items():
                    columns = [i for i, a in enumerate(run["agent_ids"]) if a in group["members"]]
                    sub = {**run, "agent_ids": [run["agent_ids"][i] for i in columns], "p": run["p"][:, columns], "v": run["v"][:, columns]}
                    success = labels["task_groups"][gid]["result"]["status"] == "success" and labels["generation_quality"]["retained"]
                    checks = [{"attempt": name, "episode_id": row["episode_id"], "group_id": gid, **item}
                              for item in cross_group(scene, group, sub, source_success=success)]
                    cross_rows.extend(checks)
                    if any(r["status"] == "FAIL" for r in checks): raise ValueError("P0: mandatory cross-negation contradiction")
                for scope, section in (("agent", "agents"), ("task_group", "task_groups")):
                    for entity, value in labels[section].items():
                        gid = value["assigned"].get("task_group", entity)
                        kind = role_kind(group_templates[gid]); old_result = old[section][entity]["result"]; new_result = value["result"]
                        counts[(name, collection, row["intent"], kind, scope, "old", old_result["status"])] += 1
                        counts[(name, collection, row["intent"], kind, scope, "new", new_result["status"])] += 1
                        if old_result["status"] != new_result["status"]:
                            old_c, new_c = old_result["conditions"], new_result["conditions"]
                            reasons = {k: {"old": old_c.get(k, "removed_or_absent"), "new": new_c.get(k, "removed_or_absent")}
                                       for k in sorted(set(old_c) | set(new_c)) if old_c.get(k, "absent") != new_c.get(k, "absent")}
                            witness = agent_witness(entity, labels, frame, task) if scope == "agent" else {
                                "shared_coverage": value["observed"].get("shared_coverage"),
                                "members": {a: agent_witness(a, labels, frame, task) for a in value["assigned"]["members"]},
                                "failed_conditions": [k for k, v in new_c.items() if v is False]}
                            change = {"attempt": name, "collection": collection, "episode_id": row["episode_id"], "intent": row["intent"], "role": kind,
                                "scope": scope, "entity_id": entity, "old_result": old_result["status"], "new_result": new_result["status"],
                                "changed_conditions": json.dumps(reasons, ensure_ascii=False, separators=(",", ":")),
                                "evidence": json.dumps(witness, ensure_ascii=False, separators=(",", ":"))}
                            changes.append(change)
                            if new_result["status"] == "failure": new_failures.append(change)
                        if scope == "agent":
                            con = value["observed"]["contribution"]
                            for metric, number in (("dwell", int(con["dwell"]["detected"])), ("revisit", int(con["revisit"]["detected"])), ("reversal_count", con["work_reversal_count"])):
                                detector_counts[(name, collection, row["intent"], metric, number)] += 1
                        else:
                            observed = value["observed"]["approach_classification"]
                            assigned = group_templates[gid].get("approach_mode")
                            counter = approach[(name, collection, row["intent"])]; counter["total"] += 1
                            counter["matches"] += observed == assigned; counter["measured_" + observed] += 1
                            counter["assigned_" + str(assigned)] += 1
                result = labels["cluster"]["result"]; quality = labels["generation_quality"]
                groups = labels["task_groups"]
                row.update(criteria_version="criteria/0.7-r1", state="generated" if quality["retained"] else "generation_error",
                    quality_valid=quality["retained"], quality_status=quality["status"], audit_passed=True, audit={k: v for k, v in receipt.items() if k not in ("independent_role_facts", "event_or_metric_witnesses")},
                    task_result=result["status"], primary_task_success=result["primary_task_success"], all_groups_complete=result["all_groups_complete"],
                    reason=None if quality["retained"] else ";".join(quality["exclusion_reasons"]),
                    execution_status=run["execution_status"], coordination_by_group={g: v["observed"]["coordination"]["classification"] for g, v in groups.items()},
                    measured_approach_by_group={g: v["observed"]["approach_classification"] for g, v in groups.items()},
                    event_times_s={a: v["observed"]["core_event"]["t_s"] for a, v in labels["agents"].items()},
                    coordination_matches=all(v["observed"]["timing_diagnostics"]["coordination_matches_assignment"] is True for v in groups.values()),
                    batch_members_match=all(v["observed"]["timing_diagnostics"]["batch_members_match_assignment"] is True for v in groups.values()))
                for gid, value in groups.items():
                    row.setdefault("groups", {}).setdefault(gid, {}).update(result=value["result"], coordination=value["observed"]["coordination"],
                        timing_diagnostics=value["observed"]["timing_diagnostics"], approach_span_deg=value["observed"]["approach_span_deg"],
                        approach_classification=value["observed"]["approach_classification"])
                # Historical prefix/truncation receipts cannot describe new labels.
                row.pop("truncation", None)
                if task.get("abort_observation"):
                    main = groups[task["main_group_id"]]
                    row["abort_observation_valid"] = main["result"]["conditions"]["abort_group_withdrawal_observed"] is True
                    row["main_group_observed_coordination"] = main["observed"]["coordination"]["classification"]
                save_json(dest / "metrics.json", row)
                new_manifest = {**manifest, "label_schema_version": labels["schema_version"], "generation_quality": quality,
                                "artifact_sha256": {p.name: sha(p) for p in dest.iterdir() if p.is_file()}}
                save_json(dest / "manifest.json", new_manifest)
                # Recheck the source labels and truth after all writes.
                for filename in ("labels.json", "truth_10hz.npz", "frame_labels.npz"):
                    if sha(source / filename) != source_hashes[filename]: raise ValueError("P0: original attempt changed")
                updated.append(row); processed += 1
                episodes.append({**pending, "collection": collection, "intent": row["intent"], "aborted": bool(row.get("aborted")), "old_result": old["cluster"]["result"]["status"],
                    "new_result": result["status"], "quality_status": quality["status"], "execution_status": run["execution_status"], "audit_differences": 0})
                print(json.dumps({"stage": "relabel", "attempt": name, "done": processed, "total": len(source_paths), "episode": row["episode_id"],
                                  "old": old["cluster"]["result"]["status"], "new": result["status"], "elapsed_s": round(time.perf_counter() - started, 2)}), flush=True)
            save_json(destination / "episode_records.json", updated)
            for collection in sorted({r["inventory_scope"] for r in updated} - {"main"}):
                local_rows = []
                for row in updated:
                    if row["inventory_scope"] != collection: continue
                    local = deepcopy(row)
                    if local.get("path"): local["path"] = local["path"][len(collection) + 1:]
                    local_rows.append(local)
                save_json(destination / collection / "episode_records.json", local_rows)
            views = make_views(updated); save_json(destination / "dataset_views.json", views)
            summaries.append({"attempt": name, "episodes": processed, "source_state_counts": dict(Counter(r["state"] for r in records if r.get("path"))),
                              "aborted": sum(bool(r.get("aborted")) for r in updated if r.get("path")), "views": views["counts"]})
        status = "PASS"; stop = None
    except Exception as exc:
        status = "P0_STOP"; stop = {"reason": str(exc), "episode": pending}
        write_evidence(evidence_root / "q1_stop.json", stop)
    table = [{"attempt": a, "collection": collection, "intent": i, "role": r, "scope": s, "version": v, "result": result, "count": number}
             for (a, collection, i, r, s, v, result), number in sorted(counts.items())]
    summary = {"status": status, "output_directory": str(output), "wall_s": time.perf_counter() - started,
        "source_attempts": list(ATTEMPTS), "completed_episodes": len(episodes), "attempts": summaries, "counts": table,
        "main_episode_count": sum(e["collection"] == "main" for e in episodes),
        "diagnostic_episode_count": sum(e["collection"] != "main" for e in episodes),
        "changed_entities": len(changes), "new_failures": len(new_failures), "audit_differences": 0 if status == "PASS" else None,
        "constraint_violation_episodes": sum(e["quality_status"] == "constraint_violation" for e in episodes),
        "generation_error_episodes": sum(e["quality_status"] == "generation_error" for e in episodes),
        "timeout_episodes": sum(e["execution_status"] == "timeout" for e in episodes), "stop": stop, "episodes": episodes,
        "cluster_transitions": dict(Counter(e["old_result"] + "->" + e["new_result"] for e in episodes))}
    write_evidence(evidence_root / "q1_summary.json", summary)
    fields = ["attempt", "collection", "episode_id", "intent", "role", "scope", "entity_id", "old_result", "new_result", "changed_conditions", "evidence"]
    write_csv(evidence_root / "q1_changes.csv", fields, changes)
    write_csv(evidence_root / "q1_new_failures.csv", fields, new_failures)
    write_csv(evidence_root / "q1_detectors.csv", ["attempt", "collection", "intent", "metric", "value", "count"],
        [dict(attempt=a, collection=collection, intent=i, metric=m, value=v, count=c) for (a, collection, i, m, v), c in sorted(detector_counts.items())])
    write_evidence(evidence_root / "q1_approach.json", [{"attempt": a, "collection": collection, "intent": i, **dict(c), "agreement_fraction": c["matches"] / c["total"]}
                                                      for (a, collection, i), c in sorted(approach.items())])
    violations = [r for r in cross_rows if r["status"] == "FAIL"]
    write_evidence(evidence_root / "q1_cross_negation.json", {"status": "FAIL" if violations else status, "checked_rows": len(cross_rows),
        "counts": dict(Counter(r["status"] for r in cross_rows)), "violations": violations})
    save_json(output / "summary.json", summary)
    print(json.dumps({k: summary[k] for k in ("status", "output_directory", "completed_episodes", "changed_entities", "new_failures", "wall_s", "stop")}, ensure_ascii=False), flush=True)
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
