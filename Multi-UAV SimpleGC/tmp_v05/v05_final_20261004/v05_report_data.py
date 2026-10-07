"""Read-only assembly of every number quoted by docs/v0.5_final_report.md.

Sources (all read-only):
  verification/v05_batch_20261002/{control.json,acceptance.json,dataset/dataset_manifest.json,
      dataset/episodes/*,dataset_language_zh_v0/{descriptions.json,facts/*}}
  verification/v05_r12b_pp_20261002/control.json
  tmp_v05/v05_final_20261004/ac4_patrol_d.json

Writes tmp_v05/v05_final_20261004/v05_report_data.json and prints the same content.
"""
import collections
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BATCH = ROOT / "verification/v05_batch_20261002"
PILOT = ROOT / "verification/v05_r12b_pp_20261002"
DS = BATCH / "dataset"
LANG = BATCH / "dataset_language_zh_v0"
SEED = 20261004

manifest = json.load(open(DS / "dataset_manifest.json", encoding="utf-8"))
eps = manifest["episodes"]
acceptance = json.load(open(BATCH / "acceptance.json", encoding="utf-8"))
batch_control = json.load(open(BATCH / "control.json", encoding="utf-8"))
pilot_control = json.load(open(PILOT / "control.json", encoding="utf-8"))
lang = json.load(open(LANG / "language_manifest.json", encoding="utf-8"))
descs = json.load(open(LANG / "descriptions.json", encoding="utf-8"))
ac4 = json.load(open(HERE / "ac4_patrol_d.json", encoding="utf-8"))


def is_pilot(entry):
    return str(entry["source_analysis_directory"]).startswith("PP")


def ratios(selection):
    qualified = [e for e in selection if e["episode_quality_eligible"]]
    by_intent = {}
    for intent in ("patrol", "reconnaissance"):
        sub = [e for e in selection if e["intent"] == intent]
        q = [e for e in sub if e["episode_quality_eligible"]]
        by_intent[intent] = dict(attempted=len(sub), qualified=len(q),
                                 success_given_quality=sum(1 for e in q if e.get("mission_success") is True),
                                 agree_given_qualified=sum(1 for e in q if e.get("semantic_consistency") == "agree"))
    return dict(runs=len(selection), qualified=len(qualified),
                qualified_fraction=(len(qualified) / len(selection)) if selection else None,
                by_intent=by_intent)


pilot_eps = [e for e in eps if is_pilot(e)]
batch_eps = [e for e in eps if not is_pilot(e)]
data = {}
data["seed"] = SEED
data["dataset_counts"] = manifest["counts"]
data["split_counts_all"] = dict(collections.Counter(e["split"] for e in eps))
data["three_columns"] = {
    "pilot": dict(ratios(pilot_eps),
                  pair_qualified=pilot_control["aggregate"]["pair_qualified"],
                  bases=10),
    "batch": dict(ratios(batch_eps),
                  pair_qualified=batch_control["aggregate"]["pair_qualified"],
                  bases=120),
    "total": dict(ratios(eps),
                  pair_qualified=acceptance["aggregate"]["pair_qualified"],
                  bases=130),
}
data["acceptance"] = dict(version=acceptance["version"], gate=acceptance["gate"],
                          aggregate=acceptance["aggregate"],
                          description_check=acceptance["description_check"],
                          audit_issues=acceptance["audit_issues"],
                          loaded_count=len(acceptance["loaded"]),
                          loaded_all_corners=all(e["corner_count"] == 4 and e["corner_dimensions"] == [2, 2, 2, 2]
                                                 for e in acceptance["loaded"]),
                          dataset_manifest_sha256=acceptance["dataset_manifest_sha256"],
                          language_manifest_sha256=acceptance["language_manifest_sha256"],
                          audit_sha256=acceptance["audit_sha256"],
                          source_control_sha256=acceptance["source_control_sha256"],
                          completed_utc=acceptance["completed_utc"],
                          rolling=acceptance["rolling"])
data["language_manifest"] = lang

# --- ineligible runs with the recorded reason ------------------------------------
ineligible = []
for e in eps:
    if e["episode_quality_eligible"]:
        continue
    q = json.load(open(DS / "episodes" / e["run_id"] / "quality.json", encoding="utf-8"))
    vp = q.get("validation_policy") or {}
    ineligible.append(dict(
        run_id=e["run_id"], scenario_id=e["scenario_id"], intent=e["intent"], split=e["split"],
        run_status=e["run_status"], source_analysis_directory=e["source_analysis_directory"],
        logical_label=e["source_analysis_directory"].replace("_attempt_0", "").replace("_inherited", ""),
        hard_failures=vp.get("hard_failures"),
        onboard_mission_param_check_pass=q.get("onboard_mission_param_check_pass"),
        run_completed=q.get("run_completed"),
        episode_quality_eligible=q.get("episode_quality_eligible"),
        mission_success=q.get("mission_success"),
        semantic_consistency=q.get("semantic_consistency"),
        minimum_separation_m=q.get("minimum_separation_m"),
        data_quality_pass=q.get("data_quality_pass"),
        truth_available_pass=q.get("truth_available_pass"),
        timing_diagnostic_pass=q.get("timing_diagnostic_pass"),
        ac4_truth_within_tau=q.get("ac4_v3_truth_within_tau"),
        ac4_observation_within_tau=q.get("ac4_v3_observation_within_tau"),
    ))
data["ineligible"] = ineligible

# --- qualified split composition -------------------------------------------------
rows = collections.Counter()
for e in eps:
    if not e["episode_quality_eligible"]:
        continue
    d = DS / "episodes" / e["run_id"]
    facts = json.load(open(LANG / "facts" / (e["run_id"] + ".json"), encoding="utf-8"))
    task = json.load(open(d / "task.json", encoding="utf-8"))
    rows[(e["split"], e["intent"], len(e["agent_ids"]),
          (facts.get("observed") or {}).get("entry_side"),
          bool(task["mission"].get("return_required")))] += 1
table = {}
for (split, intent, agents, side, ret), count in sorted(rows.items(), key=str):
    table.setdefault(split, {}).setdefault(intent, {"agents": collections.Counter(),
                                                    "entry_side": collections.Counter(),
                                                    "return_required": collections.Counter(),
                                                    "total": 0})
    cell = table[split][intent]
    cell["agents"][str(agents)] += count
    cell["entry_side"][str(side)] += count
    cell["return_required"][str(ret)] += count
    cell["total"] += count
for split in table:
    for intent in table[split]:
        for key in ("agents", "entry_side", "return_required"):
            table[split][intent][key] = dict(sorted(table[split][intent][key].items()))
data["qualified_split_composition"] = table
data["qualified_split_totals"] = {s: sum(v["total"] for v in table[s].values()) for s in table}
data["qualified_intent_totals"] = {s: {i: v["total"] for i, v in table[s].items()} for s in table}

# --- description samples (documented seed, 3 per intent) -------------------------
by_episode = collections.defaultdict(list)
for d in descs["descriptions"]:
    by_episode[d["episode_id"]].append(d)


def resolve(facts, dotted):
    node = facts
    for part in dotted.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node


rng = random.Random(SEED)
samples = {}
for intent in ("patrol", "reconnaissance"):
    pool = sorted(e["run_id"] for e in eps
                  if e["episode_quality_eligible"] and e["intent"] == intent
                  and e["semantic_consistency"] == "agree")
    picks = rng.sample(pool, 3)
    out = []
    for rid in picks:
        entry = [d for d in by_episode[rid] if d["template_partition"] == "train"][0]
        facts = json.load(open(LANG / "facts" / (rid + ".json"), encoding="utf-8"))
        sentences = [dict(template_id=s["template_id"], text=s["text"],
                          facts=[dict(id=f, value=resolve(facts, f)) for f in s["fact_ids"]])
                     for s in entry["sentences"]]
        out.append(dict(run_id=rid, episode_split=entry["episode_split"],
                        description_id=entry["description_id"], text=entry["text"],
                        sentences=sentences))
    samples[intent] = dict(pool_size=len(pool), picks=out)
data["description_samples"] = samples
data["description_partition_counts"] = {
    "|".join(k): v for k, v in collections.Counter(
        (d["episode_split"], d["template_partition"]) for d in descs["descriptions"]).items()}
data["skipped_descriptions"] = len(descs["skipped"])

data["ac4_patrol_d"] = ac4

out_path = HERE / "v05_report_data.json"
out_path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
print(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True))
print("written:", out_path)
