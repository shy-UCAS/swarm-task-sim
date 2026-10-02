"""Read-only availability audit for the six prescribed v0.5 validation cases.

It inspects the frozen DR candidate set only.  It cannot select a new scene,
change a mission seed, launch SITL, or turn a rejected plan into a valid plan.
"""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def review(manifest_path):
    path = Path(manifest_path).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    candidates = data["candidates"]
    cases = {key: [] for key in ("VP1", "VP2", "VP3", "VP4", "VR1", "VR2")}
    cluster_recon_reasons = Counter()
    cluster_count = 0
    for item in candidates:
        sample = item["sampled_parameters"]
        count = sample["vehicle_count"]
        shared = item["shared_mission_params"]
        attempts = {attempt["intent"]: attempt for attempt in item["attempts"]}
        patrol = attempts["patrol"]
        recon = attempts["reconnaissance"]
        label = dict(candidate_id=item["candidate_id"], base_index=item["base_index"],
                     candidate_index=item["candidate_index"], formation=sample["formation"],
                     entry_side=sample["entry_side"], vehicle_count=count,
                     return_required=shared["return_required"], speed_m_s=shared["speed_m_s"])
        patrol_ok = patrol["status"] == "planned"
        recon_ok = recon["status"] == "planned"
        laps = patrol.get("lap_sampling", {}).get("selected_laps")
        if count == 3 and laps == 2 and shared["return_required"] and patrol_ok:
            cases["VP1"].append(dict(label, task=patrol["task"]))
        if count == 4 and patrol_ok:
            perimeter = 2 * (sample["region_width_m"] + sample["region_height_m"])
            cases["VP2"].append(dict(label, task=patrol["task"], perimeter_per_agent_m=perimeter / count))
        if count == 2 and laps == 3 and not shared["return_required"] and patrol_ok:
            cases["VP3"].append(dict(label, task=patrol["task"]))
        if count == 3 and sample["entry_side"] in ("east", "west") and recon_ok:
            cases["VR1"].append(dict(label, task=recon["task"]))
        if count == 4 and sample["formation"] == "cluster":
            cluster_count += 1
            if recon_ok:
                cases["VR2"].append(dict(label, task=recon["task"]))
            else:
                reason = recon.get("reason", "unknown")
                category = reason.partition(": ")[2].partition(": ")[0] or reason
                cluster_recon_reasons[category] += 1
    vp4_sources = [dict(entry, source_case="VP1; same scene/task seed, hold 1 second only")
                   for entry in cases["VP1"]]
    # Hold=1 is deliberately absent from the frozen formal candidate tasks.
    # VP4 needs a separate, verified compile after cloning the selected VP1.
    cases["VP4"] = []
    cases["VP2"].sort(key=lambda item: (item["perimeter_per_agent_m"], item["candidate_id"]))
    result = dict(review_version="v05_validation_candidate_preflight_v3",
                  source_manifest=str(path), source_manifest_sha256=digest(path),
                  source_profile_sha256=data.get("profile_sha256"),
                  candidate_count=len(candidates), n4_cluster_candidate_count=cluster_count,
                  n4_cluster_recon_status=dict(planned=len(cases["VR2"]),
                                               rejected=cluster_count - len(cases["VR2"]),
                                               rejection_reason_prefix_counts=dict(cluster_recon_reasons)),
                  vp4_source_candidates=len(vp4_sources),
                  vp4_status="hold_1_derived_task_requires_separate_offline_compile",
                  cases={key: dict(available=bool(rows), count=len(rows), first_three=rows[:3])
                         for key, rows in cases.items()},
                  all_prescribed_cases_available=all(cases.values()),
                  policy="No substituted scene, template, seed, sampler range, or planner threshold")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("preflight output already exists")
    result = review(args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"candidate_count": result["candidate_count"],
                      "case_counts": {key: value["count"] for key, value in result["cases"].items()},
                      "all_prescribed_cases_available": result["all_prescribed_cases_available"]}))


if __name__ == "__main__":
    main()
