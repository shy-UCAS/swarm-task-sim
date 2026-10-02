"""Read-only WP-H census of every official v0.4 route SITL run and WP-S spike.

Original run directories are never modified. Results are written only to a new
tmp_v05/h evidence file. Verification runs are taken from their original roots;
tmp_v04 reproductions and input snapshots are deliberately not counted twice.
"""

import json
import sys
import argparse
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from swarm_sim.observation_processing import prepare_v3_observations
from swarm_sim.onboard_mission_params import diagnose_onboard_mission_params


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def events(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def official_runs():
    roots = [ROOT / "verification", ROOT / "runs"]
    candidates = []
    for path in roots[0].glob("v04*/**/metadata.json"):
        metadata = read(path)
        scene = metadata.get("scenario", {})
        if scene.get("schema_version") == 2 and scene.get("control_mode") == "semantic_phase_route_v1":
            candidates.append((path.parent, "v04_route", metadata))
    for path in roots[1].glob("spike_v04_*/metadata.json"):
        candidates.append((path.parent, "WP-S_spike_route", read(path)))
    identities = [metadata["run_id"] for _, _, metadata in candidates]
    if len(identities) != len(set(identities)):
        raise ValueError("official run roots contain duplicate run IDs")
    return sorted(candidates, key=lambda entry: (entry[1], entry[2]["run_id"]))


def prepare(run, kind, metadata):
    if kind == "WP-S_spike_route":
        plan = read(run / metadata["executed_plan"])
        scene = dict(schema_version=2, origin=metadata["scenario"]["origin"],
                     vehicles=metadata["scenario"]["vehicles"], phases=plan["phases"],
                     task_spec={"execution": {}})
        clock_models = read(run / "spike_metrics.json")["clock_models"]
        changed = {"spike_phase_upload_start": "phase_upload_started",
                   "spike_phase_upload_end": "phase_upload_complete"}
        run_events = [dict(item, event=changed.get(item.get("event"), item.get("event")))
                      for item in events(run / "events.jsonl")]
        return scene, run_events, clock_models
    scene = metadata["scenario"]
    run_events = events(run / "events.jsonl")
    clocks = {}
    for vehicle in scene["vehicles"]:
        agent = vehicle["id"]
        raw = run / "raw" / f"{agent}.jsonl"
        packets = events(raw) if raw.exists() else []
        model = prepare_v3_observations(packets, scene["origin"], metadata["quality_policy"],
            metadata["run_epoch_monotonic_s"],
            metadata["run_epoch_monotonic_s"]+metadata["elapsed_s"])["clock_model"]
        clocks[agent] = model
    return scene, run_events, clocks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "tmp_v05/h/v04_route_param_census.json")
    args = parser.parse_args()
    results = []
    for run, kind, metadata in official_runs():
        scene, run_events, clocks = prepare(run, kind, metadata)
        check = diagnose_onboard_mission_params(run, scene, run_events, clocks)
        result = dict(run_id=metadata["run_id"], run_directory=run.relative_to(ROOT).as_posix(),
                      kind=kind, status=metadata["status"], aircraft_count=len(scene["vehicles"]),
                      phase_count=len(scene["phases"]), comparison=check)
        results.append(result)
        print(json.dumps(dict(run_id=result["run_id"], kind=kind, status=result["status"],
                              verdict=check["status"], **check["counts"]), ensure_ascii=False), flush=True)
    aggregate = Counter()
    for result in results:
        aggregate.update(result["comparison"]["counts"])
    payload = dict(version="wp_h_v04_route_census_v1", scope="original verification/v04* route runs and original runs/spike_v04_*",
                   run_count=len(results), v04_route_run_count=sum(r["kind"] == "v04_route" for r in results),
                   spike_run_count=sum(r["kind"] == "WP-S_spike_route" for r in results),
                   aggregate=dict(aggregate), runs=results)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps(dict(output=str(output), run_count=len(results), aggregate=dict(aggregate)), ensure_ascii=False))


if __name__ == "__main__":
    main()
