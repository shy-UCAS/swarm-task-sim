"""Read-only audit of optional-return language against frozen pilot trajectories."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))

from swarm_sim.language_templates_v0 import validate_description
from swarm_sim.observer_facts_v0 import (
    EPS, _point_at, _return_observed, _traces, _window_by_agent,
    extract_observer_facts,
)
from swarm_sim.mission_evaluation import window_evidence

ROOT = PROJECT / "verification/v05_r12b_pp_20261002"
DATASET = ROOT / "dataset"
LANGUAGE = ROOT / "dataset_language_zh_v0"
OUTPUT = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory():
    return {p.relative_to(PROJECT).as_posix(): sha(p)
            for root in (DATASET, LANGUAGE) for p in sorted(root.rglob("*")) if p.is_file()}


def trajectory_evidence(episode, task, facts):
    manifest = read(episode / "manifest.json")
    windows = read(episode / "phase_windows.json")["channels"]
    agents = manifest["agent_ids"]
    phase = "patrol" if task["mission"]["intent"] == "patrol" else "observe"
    max_gap = task["execution"]["max_gap_s"]
    hz = task["execution"]["record_hz"]
    result = {}
    for channel, file in (("truth", "truth.csv"), ("observation", "observations.csv")):
        traces = _traces(episode / file, agents)
        main = _window_by_agent(windows[channel], phase, agents)
        approach = _window_by_agent(windows[channel], "approach", agents)
        observed = _return_observed(traces, windows[channel], agents, phase,
                                    max_gap, manifest["duration_s"], hz)
        agent_evidence = []
        for agent in agents:
            home = _point_at(traces[agent], approach[agent]["start_s"], max_gap)
            evidence = window_evidence(traces[agent], main[agent]["arrival_s"],
                                       manifest["duration_s"], max_gap, edge_allowance=1 / hz)
            points = sorted(evidence["points"], key=lambda row: row[0])
            distances = [math.dist(point[:3], home[:3]) for _, point in points]
            assert distances, (episode.name, channel, agent)
            agent_evidence.append(dict(agent_id=agent, source=file,
                departure_time_s=approach[agent]["start_s"], start_position_m=home,
                post_main_start_s=main[agent]["arrival_s"],
                final_sample_time_s=points[-1][0],
                final_distance_to_start_m=distances[-1],
                minimum_post_main_distance_to_start_m=min(distances),
                complete_post_main_trajectory=evidence["complete"],
                return_radius_m=3.0,
                final_within_return_radius=distances[-1] <= 3.0 + EPS))
        result[channel] = dict(return_observed=observed, agents=agent_evidence)
    result["matches_saved_fact"] = (result["truth"]["return_observed"] is
        result["observation"]["return_observed"] is facts["observed"]["return_observed"])
    return result


def main():
    result_path = OUTPUT / "audit.json"
    if result_path.exists():
        raise ValueError("audit output exists; preserve the previous evidence")
    before = inventory()
    manifest_path = DATASET / "dataset_manifest.json"
    manifest = read(manifest_path)
    language_manifest = read(LANGUAGE / "language_manifest.json")
    exported = read(LANGUAGE / "descriptions.json")
    manifest_hash = sha(manifest_path)
    assert exported["dataset_manifest_sha256"] == language_manifest["dataset_manifest_sha256"] == manifest_hash
    for relative, expected in language_manifest["artifact_sha256"].items():
        assert sha(LANGUAGE / relative) == expected, relative
    descriptions = exported["descriptions"]
    assert len(descriptions) == 80
    assert len({d["description_id"] for d in descriptions}) == 80
    valid_count = 0
    false_rows = []
    all_rows = []
    issues = []
    for entry in manifest["episodes"]:
        episode = DATASET / entry["directory"]
        task = read(episode / "task.json")
        facts = read(LANGUAGE / "facts" / (entry["run_id"] + ".json"))
        fresh = extract_observer_facts(episode, manifest_hash)
        assert fresh == facts, (entry["run_id"], "saved facts differ from fresh trajectory extraction")
        required = task["mission"]["return_required"]
        assert facts["labels"]["return_required"] is required
        selected = [d for d in descriptions if d["episode_id"] == entry["run_id"]]
        assert len(selected) == 4
        assert Counter(d["template_partition"] for d in selected) == {"train": 3, "test": 1}
        row = dict(episode_id=entry["run_id"], intent=task["mission"]["intent"],
                   return_required=required, return_observed=facts["observed"]["return_observed"],
                   facts_recomputed_equal=True, descriptions=[])
        for description in selected:
            valid, errors = validate_description(description, facts)
            valid_count += int(valid)
            if not valid:
                issues.append(dict(description_id=description["description_id"], errors=errors))
            returns = [s for s in description["sentences"]
                       if ".return_" in s["template_id"] or re.search("返航|返回|回到|起点", s["text"])]
            if required is False:
                if re.search(r"返航条件|返航[^。]*(?:满足|达标|通过)", description["text"]):
                    issues.append(dict(description_id=description["description_id"], error="optional_return_condition_claim"))
                for sentence in returns:
                    expected_key = "T4.return_true." if facts["observed"]["return_observed"] is True else "T4.return_false."
                    if (not sentence["template_id"].startswith(expected_key)
                            or sentence["fact_ids"] != ["observed.return_observed"]):
                        issues.append(dict(description_id=description["description_id"], error="return_sentence_not_trajectory_bound", sentence=sentence))
            row["descriptions"].append(dict(description_id=description["description_id"],
                template_partition=description["template_partition"], consistency_pass=valid,
                return_sentences=returns,
                forbidden_condition_claim=bool(re.search(r"返航条件|返航[^。]*(?:满足|达标|通过)", description["text"])) if required is False else None))
        all_rows.append(row)
        if required is False:
            row["trajectory_evidence"] = trajectory_evidence(episode, task, facts)
            assert row["trajectory_evidence"]["matches_saved_fact"]
            false_rows.append(row)
    after = inventory()
    assert before == after, "original dataset or language bytes changed"
    sources = [PROJECT / "swarm_sim" / name for name in (
        "language_templates_v0.py", "language_v0.py", "observer_facts_v0.py")]
    result = dict(result="PASS" if not issues else "FAIL", simulation_started=False,
        source_dataset=str(DATASET), source_language=str(LANGUAGE),
        dataset_manifest_sha256=manifest_hash,
        episodes_total=len(all_rows), descriptions_total=len(descriptions),
        descriptions_consistency_pass=valid_count,
        optional_return_episodes=len(false_rows),
        optional_return_descriptions=sum(len(row["descriptions"]) for row in false_rows),
        optional_return_by_intent=dict(Counter(row["intent"] for row in false_rows)),
        optional_return_observed_values=dict(Counter(str(row["return_observed"]) for row in false_rows)),
        source_sha256={p.relative_to(PROJECT).as_posix(): sha(p) for p in sources},
        original_files_preserved=len(before), original_sha256=before,
        template_change_required=bool(issues), description_regeneration_required=bool(issues),
        issues=issues, optional_return_episodes_detail=false_rows,
        all_episode_summary=[{key: row[key] for key in ("episode_id", "intent", "return_required", "return_observed", "facts_recomputed_equal")} for row in all_rows])
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {k: result[k] for k in ("result", "episodes_total", "descriptions_total",
        "descriptions_consistency_pass", "optional_return_episodes", "optional_return_descriptions",
        "optional_return_by_intent", "optional_return_observed_values", "original_files_preserved",
        "template_change_required", "description_regeneration_required", "issues")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if issues:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
