"""Pure helpers for the v0.7 first_edition production pipeline.

No planner, criteria, audit or simulator code lives here.  The functions
operate on already-produced descriptors, status records and run directories so
the retention and reporting rules can be tested without running a simulation.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from task_v07.expansion.contracts import P0ContractError

INTENTS = ("transit", "reconnaissance", "monitoring", "feint", "penetration")
MODES = ("synchronous", "sequential")
SLOTS_PER_FAMILY = 2
REGULAR_PER_FAMILY = 10

VERSION_FIELDS = (
    "run_id", "created_utc", "families_range", "code_commit", "git_clean",
    "code_hashes_sha256", "reference_version", "r3_config_sha256",
    "r2_frozen_sha256", "criteria_version", "criteria_sha256",
    "generator_config_sha256", "baseline_path", "baseline_sha256",
    "scene_layout", "workers", "planning_timeout_s", "episode_timeout_s",
    "FE_SCOPE", "python_version", "numpy_version",
)


class ProductionError(RuntimeError):
    """A startup or harness error with an explicit process exit code."""

    def __init__(self, code, message, detail=None):
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def atomic_json(path, value):
    """Same write pattern as scripts.audit_m3_r3_r0.atomic."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    temp.replace(path)


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc_stamp(now=None):
    return (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")


def utc_iso(now=None):
    return (now or datetime.now(timezone.utc)).isoformat()


def percentile(values, q):
    values = sorted(float(v) for v in values if v is not None)
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * q
    low, high = int(math.floor(position)), int(math.ceil(position))
    if low == high:
        return values[low]
    return values[low] + (values[high] - values[low]) * (position - low)


def summary(values):
    clean = [v for v in values if v is not None]
    if not clean:
        return {"count": 0, "median": None, "p90": None, "max": None}
    return {"count": len(clean), "median": percentile(clean, .5),
            "p90": percentile(clean, .9), "max": max(clean)}


def ratio(numerator, denominator):
    return None if not denominator else numerator / denominator


def vehicle_bucket(count):
    count = int(count)
    if count <= 3:
        return "2-3"
    if count <= 5:
        return "4-5"
    return ">=6"


def family_range(baseline, start, end):
    """Half-open [start, end) over candidate_index, ascending."""
    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
        raise ProductionError(3, f"Invalid family range {start!r}:{end!r}")
    selected = [row for row in baseline["families"]
                if start <= int(row["candidate_index"]) < end]
    selected.sort(key=lambda row: int(row["candidate_index"]))
    if not selected:
        raise ProductionError(3, f"Family range {start}:{end} selects no registered family")
    return selected


def split_regular(records):
    regular = [row for row in records if row.get("subset") == "regular"]
    aborted = [row for row in records if row.get("subset") == "aborted"]
    unexpected = [row for row in records if row.get("subset") not in ("regular", "aborted")]
    if unexpected:
        raise P0ContractError("Descriptor subset is neither regular nor aborted")
    return regular, len(aborted)


def draw_key(descriptor):
    return descriptor["family_id"], int(descriptor["common_draw"]["slot"])


def draw_key_text(key):
    return f"{key[0]}:{key[1]}"


def group_draws(descriptors):
    grouped = defaultdict(list)
    for descriptor in descriptors:
        grouped[draw_key(descriptor)].append(descriptor)
    draws = []
    for key in sorted(grouped):
        rows = sorted(grouped[key], key=lambda row: INTENTS.index(row["base_intent"]))
        intents = [row["base_intent"] for row in rows]
        if len(intents) != len(INTENTS) or set(intents) != set(INTENTS):
            raise P0ContractError(f"Draw {draw_key_text(key)} does not contain exactly five intents")
        draws.append({"draw_key": key, "draw_key_text": draw_key_text(key),
                      "family_id": key[0], "slot": key[1],
                      "descriptors": rows,
                      "intents": {row["base_intent"]: row for row in rows}})
    return draws


def intent_statuses(draw, statuses, stage):
    return {intent: statuses.get(stage, {}).get(descriptor["skeleton_id"])
            for intent, descriptor in draw["intents"].items()}


def status_text(record):
    return None if not record else record.get("status")


def first_failure(record):
    if not record or record.get("status") in ("PASS", "PAIRED"):
        return None
    value = record.get("first_failure") or record.get("detail") or record.get("reason")
    return value if value is not None else record.get("status")


def classify_draw(draw, b_statuses, c_statuses):
    """Return INCOMPLETE, B_REJECT, RETAINED or C_NOT_PAIRED."""
    b_values = [status_text(b_statuses.get(intent)) for intent in draw["intents"]]
    if any(value is None for value in b_values):
        return "INCOMPLETE"
    if any(value != "PASS" for value in b_values):
        return "B_REJECT"
    c_values = [status_text(c_statuses.get(intent)) for intent in draw["intents"]]
    if any(value is None for value in c_values):
        return "INCOMPLETE"
    if all(value == "PAIRED" for value in c_values):
        return "RETAINED"
    return "C_NOT_PAIRED"


def draw_detail(draw, b_statuses, c_statuses):
    return {
        "draw_key": draw["draw_key_text"],
        "family_id": draw["family_id"],
        "slot": draw["slot"],
        "status": classify_draw(draw, b_statuses, c_statuses),
        "intents": {
            intent: {
                "b": status_text(b_statuses.get(intent)),
                "c": status_text(c_statuses.get(intent)),
                "first_failure": first_failure(b_statuses.get(intent))
                if status_text(b_statuses.get(intent)) not in (None, "PASS")
                else first_failure(c_statuses.get(intent)),
            }
            for intent in draw["intents"]
        },
    }


def ready_c_descriptors(draw, b_statuses):
    values = [status_text(b_statuses.get(intent)) for intent in draw["intents"]]
    return list(draw["descriptors"]) if values and all(value == "PASS" for value in values) else []


def episode_entry(run_dir, descriptor, row):
    relative = row["path"]
    root = Path(run_dir) / "episodes" / relative
    return {
        "episode_id": row["episode_id"],
        "family_id": descriptor["family_id"],
        "slot": int(descriptor["common_draw"]["slot"]),
        "skeleton_id": descriptor["skeleton_id"],
        "intent": descriptor["base_intent"],
        "mode": row["mode"],
        "path": f"episodes/{relative}",
        "episode_manifest_sha256": sha256_file(root / "manifest.json"),
        "labels_sha256": sha256_file(root / "labels.json"),
    }


def manifest_rows(run_dir, descriptors, statuses):
    draws = group_draws(descriptors)
    retained, non_retained, draw_rows = [], [], []
    for draw in draws:
        b_statuses = intent_statuses(draw, statuses, "B")
        c_statuses = intent_statuses(draw, statuses, "C")
        detail = draw_detail(draw, b_statuses, c_statuses)
        draw_rows.append(detail)
        for intent, descriptor in draw["intents"].items():
            record = c_statuses.get(intent)
            if not record:
                continue
            for row in record.get("rows", []):
                if not row.get("path"):
                    continue
                entry = episode_entry(run_dir, descriptor, row)
                if detail["status"] == "RETAINED":
                    retained.append(entry)
                else:
                    non_retained.append({**entry, "draw_status": detail["status"]})
    retained.sort(key=lambda row: row["episode_id"])
    non_retained.sort(key=lambda row: row["episode_id"])
    return retained, non_retained, sorted(draw_rows, key=lambda row: row["draw_key"])


def build_manifest(run_dir, registration, descriptors, statuses):
    retained, non_retained, draws = manifest_rows(run_dir, descriptors, statuses)
    manifest = {field: registration.get(field) for field in VERSION_FIELDS}
    manifest.update({
        "descriptor_count": registration.get("descriptor_count"),
        "slots_per_family": registration.get("slots_per_family"),
        "subset": registration.get("subset"),
        "retained_episodes": retained,
        "non_retained_episodes": non_retained,
        "draws": draws,
    })
    return manifest


def _family_index(registration):
    return {row["family_id"]: row for row in registration.get("family_rows", [])}


def _draw_attributes(draw, families):
    family = families.get(draw["family_id"], {})
    descriptor = draw["descriptors"][0]
    return {
        "layout": family.get("layout"),
        "facility_count": family.get("facility_count"),
        "vehicle_count": family.get("vehicle_count"),
        "vehicle_bucket": vehicle_bucket(family.get("vehicle_count", 0)),
        "actual_unit_count": descriptor.get("common_draw", {}).get("actual_unit_count"),
        "approach_mode": descriptor.get("common_draw", {}).get("approach_mode"),
    }


def _distribution(rows, key):
    counts = Counter(str(row.get(key)) if row.get(key) is not None else "None" for row in rows)
    return dict(sorted(counts.items()))


def _yield_for(rows):
    total = len(rows)
    b_pass = sum(row["b_all_pass"] for row in rows)
    retained = sum(row["retained"] for row in rows)
    return {"draws": total, "b_all_pass": b_pass, "retained": retained,
            "b_all_pass_ratio": ratio(b_pass, total), "retention_ratio": ratio(retained, total)}


def _stats_yield(registration, draws, statuses):
    families = _family_index(registration)
    family_rows = registration.get("family_rows", [])
    rows = []
    for draw in draws:
        b_statuses = intent_statuses(draw, statuses, "B")
        c_statuses = intent_statuses(draw, statuses, "C")
        state = classify_draw(draw, b_statuses, c_statuses)
        rows.append({**_draw_attributes(draw, families),
                     "b_all_pass": all(status_text(b_statuses.get(i)) == "PASS" for i in draw["intents"]),
                     "retained": state == "RETAINED"})
    by_layout = defaultdict(list)
    by_facility = defaultdict(list)
    by_vehicle = defaultdict(list)
    for row in rows:
        by_layout[str(row["layout"])].append(row)
        by_facility[str(row["facility_count"])].append(row)
        by_vehicle[row["vehicle_bucket"]].append(row)
    return {
        "families": len(family_rows),
        "family_unsampleable": len(registration.get("family_unsampleable", [])),
        "descriptors": registration.get("descriptor_count"),
        "draws": len(draws),
        "b_all_pass_draws": sum(row["b_all_pass"] for row in rows),
        "retained_draws": sum(row["retained"] for row in rows),
        "draw_retention_ratio": ratio(sum(row["retained"] for row in rows), len(rows)),
        "b_all_pass_ratio": ratio(sum(row["b_all_pass"] for row in rows), len(rows)),
        "by_layout": {key: _yield_for(value) for key, value in sorted(by_layout.items())},
        "by_facility_count": {key: _yield_for(value) for key, value in sorted(by_facility.items())},
        "by_vehicle_count": {key: _yield_for(value) for key, value in sorted(by_vehicle.items())},
    }


def _stats_intents(registration, draws, statuses):
    result = {}
    for intent in INTENTS:
        b_records = [statuses["B"].get(descriptor["skeleton_id"])
                     for draw in draws for descriptor in [draw["intents"][intent]]]
        b_denominator = len(b_records)
        b_pass = sum(status_text(record) == "PASS" for record in b_records)
        reasons = Counter()
        for record in b_records:
            if not record or record.get("status") == "PASS":
                continue
            detail = record.get("detail")
            if isinstance(detail, dict):
                reasons.update(detail.get("rejection_reasons", {}))
            elif detail:
                reasons[str(detail)] += 1
        b_pass_draws = [draw for draw in draws
                        if all(status_text(intent_statuses(draw, statuses, "B").get(i)) == "PASS"
                               for i in draw["intents"])]
        c_records = [statuses["C"].get(draw["intents"][intent]["skeleton_id"])
                     for draw in b_pass_draws]
        c_in_b_pass = [record for record in c_records
                       if record and status_text(record) in ("PAIRED", "NOT_PAIRED", "P0_STOP", "ERROR", "TIMEOUT")]
        paired = sum(status_text(record) == "PAIRED" for record in c_in_b_pass)
        failures = Counter()
        for record in c_in_b_pass:
            if status_text(record) != "PAIRED":
                failure = first_failure(record)
                failures[str(failure)] += 1
        retained_episodes = sum(
            len([row for row in (statuses["C"].get(descriptor["skeleton_id"]) or {}).get("rows", [])
                 if row.get("path")])
            for draw in draws
            if classify_draw(draw, intent_statuses(draw, statuses, "B"),
                             intent_statuses(draw, statuses, "C")) == "RETAINED"
            for descriptor in [draw["intents"][intent]])
        result[intent] = {
            "b_total": b_denominator,
            "b_pass": b_pass,
            "b_pass_ratio": ratio(b_pass, b_denominator),
            "b_rejection_top5": dict(reasons.most_common(5)),
            "c_in_b_pass": len(c_in_b_pass),
            "c_paired": paired,
            "c_pair_ratio": ratio(paired, len(c_in_b_pass)),
            "c_first_failure_top5": dict(failures.most_common(5)),
            "retained_episodes": retained_episodes,
        }
    return result


def _coverage_column(draws, statuses, families):
    rows = []
    groups = defaultdict(lambda: {"draws": 0, "groups": 0, "members": 0})
    for draw in draws:
        attrs = _draw_attributes(draw, families)
        rows.append(attrs)
        for intent, descriptor in draw["intents"].items():
            task_groups = descriptor.get("task_groups", [])
            bucket = groups[intent]
            bucket["draws"] += 1
            bucket["groups"] += len(task_groups)
            bucket["members"] += sum(len(group.get("members", [])) for group in task_groups)
    return {
        "layouts": _distribution(rows, "layout"),
        "facility_counts": _distribution(rows, "facility_count"),
        "vehicle_counts": _distribution(rows, "vehicle_count"),
        "vehicle_buckets": _distribution(rows, "vehicle_bucket"),
        "actual_unit_counts": _distribution(rows, "actual_unit_count"),
        "approach_modes": _distribution(rows, "approach_mode"),
        "task_groups_by_intent": {
            intent: {"draws": value["draws"],
                     "groups": value["groups"],
                     "members": value["members"],
                     "mean_groups": ratio(value["groups"], value["draws"]),
                     "mean_members": ratio(value["members"], value["groups"])}
            for intent, value in sorted(groups.items())
        },
    }


def _stats_coverage(registration, draws, statuses):
    families = _family_index(registration)
    all_draws = list(draws)
    b_pass = [draw for draw in draws if any(ready_c_descriptors(draw, intent_statuses(draw, statuses, "B")))]
    retained = [draw for draw in draws
                if classify_draw(draw, intent_statuses(draw, statuses, "B"),
                                 intent_statuses(draw, statuses, "C")) == "RETAINED"]
    return {
        "all_draws": _coverage_column(all_draws, statuses, families),
        "b_all_pass_draws": _coverage_column(b_pass, statuses, families),
        "retained_draws": _coverage_column(retained, statuses, families),
    }


def _stats_low_speed(run_dir, retained_episodes, qc_summary):
    qc_rows = []
    seen = set()
    for entry in retained_episodes:
        sid = entry["skeleton_id"]
        if sid in seen:
            continue
        seen.add(sid)
        path = Path(run_dir) / "qc" / f"{sid}.json"
        if path.exists():
            qc_rows.extend(read_json(path))
    return qc_summary(qc_rows)


def _velocity_horizontal(truth):
    velocity = truth["v"]
    return np.linalg.norm(velocity[:, :, :2], axis=2)


def _waiting_records(run_dir, retained_episodes):
    records = []
    for entry in retained_episodes:
        root = Path(run_dir) / entry["path"]
        task = read_json(root / "task.json")
        source = read_json(root / "source.json")
        with np.load(root / "truth_10hz.npz", allow_pickle=False) as truth:
            time_s = truth["time_us"] / 1e6
            speed = _velocity_horizontal(truth)
            agent_ids = truth["agent_ids"].tolist()
        settle = float(task["initial_settle_s"])
        delays = source["departure_delays_s"]
        releases = [settle + float(delays[agent]) for agent in agent_ids]
        episode_span = max(releases) - min(releases)
        for column, agent in enumerate(agent_ids):
            moving = np.flatnonzero(speed[:, column] > 1.)
            motion_end = float(time_s[moving[-1]]) if len(moving) else None
            release = releases[column]
            if motion_end is None:
                low_share = None
                end_dwell = None
            else:
                window = (time_s >= release) & (time_s <= motion_end)
                low_share = float(np.mean(speed[window, column] < 1.)) if np.any(window) else None
                end_dwell = float(time_s[-1] - motion_end)
            records.append({
                "episode_id": entry["episode_id"],
                "intent": entry["intent"],
                "mode": entry["mode"],
                "agent_id": agent,
                "release_s": release,
                "episode_release_span_s": episode_span,
                "low_speed_share_after_release": low_share,
                "end_dwell_s": end_dwell,
                "initial_speed_gt_1": bool(speed[0, column] > 1.),
            })
    return records


def _stats_waiting(run_dir, retained_episodes):
    records = _waiting_records(run_dir, retained_episodes)
    grouped = defaultdict(list)
    episode_spans = defaultdict(list)
    seen_episodes = set()
    for record in records:
        grouped[(record["intent"], record["mode"])].append(record)
        key = (record["intent"], record["mode"], record["episode_id"])
        if key not in seen_episodes:
            seen_episodes.add(key)
            episode_spans[(record["intent"], record["mode"])].append(record["episode_release_span_s"])
    result = {}
    for (intent, mode), rows in sorted(grouped.items()):
        result[f"{intent}/{mode}"] = {
            "members": len(rows),
            "release_s": summary([row["release_s"] for row in rows]),
            "episode_release_span_s": summary(episode_spans[(intent, mode)]),
            "low_speed_share_after_release": summary([row["low_speed_share_after_release"] for row in rows]),
            "end_dwell_s": summary([row["end_dwell_s"] for row in rows]),
            "initial_speed_gt_1_share": ratio(sum(row["initial_speed_gt_1"] for row in rows), len(rows)),
            "evaluable_members": sum(row["end_dwell_s"] is not None for row in rows),
        }
    return result


def _directory_bytes(path):
    return sum(item.stat().st_size for item in Path(path).rglob("*") if item.is_file())


def _stats_timing(run_dir, registration, descriptors, statuses, retained_episodes):
    by_intent = {}
    for intent in INTENTS:
        b_times = [statuses["B"].get(descriptor["skeleton_id"], {}).get("planning_wall_s")
                   for descriptor in descriptors if descriptor["base_intent"] == intent]
        c_times = [statuses["C"].get(descriptor["skeleton_id"], {}).get("elapsed_wall_s")
                   for descriptor in descriptors if descriptor["base_intent"] == intent]
        by_intent[intent] = {"b_wall_s": summary(b_times), "c_wall_s": summary(c_times)}
    progress_path = Path(run_dir) / "progress.json"
    total_wall = read_json(progress_path).get("elapsed_wall_s") if progress_path.exists() else None
    run_bytes = _directory_bytes(run_dir)
    retained_bytes = sum(_directory_bytes(Path(run_dir) / entry["path"])
                         for entry in retained_episodes)
    return {
        "by_intent": by_intent,
        "total_wall_s": total_wall,
        "run_dir_bytes": run_bytes,
        "retained_episode_bytes": retained_bytes,
        "mean_retained_episode_bytes": ratio(retained_bytes, len(retained_episodes)),
    }


def build_stats(run_dir, registration, descriptors, statuses, qc_summary):
    retained, _non_retained, _draws = manifest_rows(run_dir, descriptors, statuses)
    draws = group_draws(descriptors)
    return {
        "yield": _stats_yield(registration, draws, statuses),
        "intents": _stats_intents(registration, draws, statuses),
        "coverage_bias": _stats_coverage(registration, draws, statuses),
        "low_speed_and_dwell": _stats_low_speed(run_dir, retained, qc_summary),
        "waiting_and_end_dwell": _stats_waiting(run_dir, retained),
        "timing_and_size": _stats_timing(run_dir, registration, descriptors, statuses, retained),
    }


def _markdown_table(rows, columns):
    lines = ["| " + " | ".join(columns) + " |",
             "|" + "|".join("---" for _ in columns) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(column)) for column in columns) + " |")
    return "\n".join(lines)


def render_stats_markdown(stats):
    sections = []
    yield_stats = stats["yield"]
    sections.append("# v0.7 first_edition production statistics\n")
    sections.append("## 1. Yield\n")
    sections.append(_markdown_table([yield_stats], [
        "families", "family_unsampleable", "descriptors", "draws",
        "b_all_pass_draws", "retained_draws", "b_all_pass_ratio", "draw_retention_ratio"]))
    for name in ("by_layout", "by_facility_count", "by_vehicle_count"):
        sections.append(f"\n### {name}\n")
        rows = [{"bucket": key, **value} for key, value in yield_stats[name].items()]
        sections.append(_markdown_table(rows, ["bucket", "draws", "b_all_pass", "retained",
                                                "b_all_pass_ratio", "retention_ratio"]))
    sections.append("\n## 2. Intents\n")
    intent_rows = [{"intent": key, **value} for key, value in stats["intents"].items()]
    sections.append(_markdown_table(intent_rows, [
        "intent", "b_total", "b_pass", "b_pass_ratio", "c_in_b_pass", "c_paired",
        "c_pair_ratio", "retained_episodes"]))
    sections.append("\n## 3. Coverage bias\n")
    for column in ("all_draws", "b_all_pass_draws", "retained_draws"):
        sections.append(f"\n### {column}\n")
        value = stats["coverage_bias"][column]
        for key in ("layouts", "facility_counts", "vehicle_counts", "vehicle_buckets",
                    "actual_unit_counts", "approach_modes"):
            sections.append(f"- {key}: {value[key]}")
        sections.append(f"- task_groups_by_intent: {value['task_groups_by_intent']}")
    sections.append("\n## 4. Low speed and dwell (retained only)\n")
    sections.append(_markdown_table(stats["low_speed_and_dwell"], [
        "role", "execution_method", "mode", "members", "events_per_km",
        "low_speed_time_share", "dwell_positive", "dwell_evaluable"]))
    sections.append("\n## 5. Waiting and end dwell (retained only)\n")
    waiting = [{"group": key, **value} for key, value in stats["waiting_and_end_dwell"].items()]
    sections.append(_markdown_table(waiting, [
        "group", "members", "evaluable_members", "initial_speed_gt_1_share",
        "release_s", "episode_release_span_s", "low_speed_share_after_release", "end_dwell_s"]))
    sections.append("\n## 6. Timing and size\n")
    sections.append(_markdown_table([stats["timing_and_size"]], [
        "total_wall_s", "run_dir_bytes", "retained_episode_bytes", "mean_retained_episode_bytes"]))
    timing_rows = [{"intent": key, **value} for key, value in stats["timing_and_size"]["by_intent"].items()]
    sections.append("\n" + _markdown_table(timing_rows, ["intent", "b_wall_s", "c_wall_s"]))
    return "\n".join(sections) + "\n"
