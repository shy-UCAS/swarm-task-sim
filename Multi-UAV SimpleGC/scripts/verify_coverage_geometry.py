"""Recompute frozen development runs without changing any historical artifact."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from swarm_sim.fast_dynamics.adapter import analyze_semantics, reuse_semantics, traces_from_samples
from swarm_sim.fast_dynamics.artifacts import _read_support
from swarm_sim.fast_dynamics.output_policy import assert_created_within, assert_new_attempt_path, resolve_output_root
from swarm_sim.episode_loader import load_episode
from swarm_sim.dataset_audit import audit_dataset
from swarm_sim.language_v0 import describe_dataset
from swarm_sim.recording import write_json


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def differences(before, after, path="$", floats=None):
    """Exact decisions/counts/structure; enumerate every differing float leaf."""
    floats = {} if floats is None else floats
    if type(before) is not type(after):
        raise AssertionError(f"type mismatch at {path}")
    if isinstance(before, dict):
        if before.keys() != after.keys():
            raise AssertionError(f"key mismatch at {path}")
        for key in before:
            differences(before[key], after[key], path + "." + key, floats)
    elif isinstance(before, list):
        if len(before) != len(after):
            raise AssertionError(f"length mismatch at {path}")
        for i, (a, b) in enumerate(zip(before, after)):
            differences(a, b, f"{path}[{i}]", floats)
    elif before != after:
        if isinstance(before, float):
            floats[path] = max(floats.get(path, 0.0), abs(before - after))
        else:
            raise AssertionError(f"value mismatch at {path}: {before!r} != {after!r}")
    return floats


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, action="append", required=True,
                        help="existing development verification.json; repeat for additional batches")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    root = resolve_output_root(args.output_root)["root"]
    output = assert_new_attempt_path(args.output, root, kind="geometry verification")
    output.mkdir(parents=True)
    assert_created_within(output, root)
    report = dict(status="RUNNING", rows=[], floating_differences={}, preserved_historical_inputs=True)
    write_json(output / "verification.json", report)
    for batch in args.baseline:
        for row in read(batch)["rows"]:
            started = time.perf_counter()
            attempt = Path(row["attempt"])
            episode = attempt / "dataset/episodes" / row["case_id"]
            dest = output / f'{len(report["rows"]):02d}_{row["case_id"]}'
            dest.mkdir()
            manifest = read(episode / "manifest.json")
            agents = manifest["agent_ids"]
            ticks, p, v, _ = _read_support(episode / "support_truth.csv", agents)
            scene, events = read(episode / "compiled_scene.json"), read(episode / "events.json")["events"]
            byte_checks = []
            with reuse_semantics():
                values = analyze_semantics(scene, traces_from_samples(agents, ticks, p, v), events,
                                           manifest["end_us"] / 1e6, manifest["run_status"])
                for name, value in zip(("labels.json", "semantic_validation.json", "phase_windows.json"), values):
                    delta = differences(read(episode / name), value, name)
                    for key, magnitude in delta.items():
                        report["floating_differences"][key] = max(report["floating_differences"].get(key, 0), magnitude)
                    write_json(dest / name, value)
                    byte_checks.append(dict(file=name, identical=(dest / name).read_bytes() == (episode / name).read_bytes()))
                # Strict public loading/audit independently recheck contracts and claims.
                load_episode(episode)
                audit = audit_dataset(attempt / "dataset")
                if audit.get("issues"):
                    raise AssertionError(audit["issues"])
                describe_dataset(attempt / "dataset", dest / "language")
                for old in sorted((attempt / "language").rglob("*.json")):
                    relative = old.relative_to(attempt / "language")
                    new = dest / "language" / relative
                    differences(read(old), read(new), "language/" + relative.as_posix(), report["floating_differences"])
                    byte_checks.append(dict(file="language/" + relative.as_posix(), identical=old.read_bytes() == new.read_bytes()))
            item = dict(case_id=row["case_id"], baseline=str(batch), source_attempt=str(attempt),
                        source_manifest_sha256=hashlib.sha256((episode / "manifest.json").read_bytes()).hexdigest(),
                        exact_fields=not report["floating_differences"], files=byte_checks,
                        elapsed_s=time.perf_counter() - started)
            report["rows"].append(item)
            write_json(output / "verification.json", report)
            print(json.dumps(item), flush=True)
    report.update(status="PASS", runs=len(report["rows"]),
                  byte_identical_files=sum(f["identical"] for r in report["rows"] for f in r["files"]),
                  compared_files=sum(len(r["files"]) for r in report["rows"]))
    write_json(output / "verification.json", report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
