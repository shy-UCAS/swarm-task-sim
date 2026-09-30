"""CLI for local, managed SITL only. Legacy single-vehicle main.py is retained."""

import argparse
import json
from pathlib import Path

from swarm_sim.scenario import load

ROOT = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description="Managed local multi-UAV SITL scenarios")
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="Compile an explicit TaskSpec to event-driven AUTO phases")
    plan.add_argument("task", type=Path)
    plan.add_argument("--output", type=Path, required=True)
    analyze = sub.add_parser("analyze", help="Write a new, versioned analysis of an existing run")
    analyze.add_argument("run_directory", type=Path)
    analyze.add_argument("--quality-policy", type=Path, help="JSON quality policy overrides; never changes historical run metadata")
    dataset = sub.add_parser("dataset", help="Export analyzed runs with whole-family splits; retain failures")
    dataset.add_argument("runs", nargs="+", type=Path)
    dataset.add_argument("--output", type=Path, required=True)
    dataset.add_argument("--split-salt", default="simplegc-v02")
    audit = sub.add_parser("audit", help="Read-only check of a legacy trajectory JSON")
    audit.add_argument("scenario", type=Path)
    audit.add_argument("--time-unit", choices=["index", "seconds"], default="index")
    for command in ("validate", "run", "batch"):
        child = sub.add_parser(command)
        child.add_argument("scenario", type=Path)
        if command != "validate":
            child.add_argument("--quality-policy", type=Path)
            child.add_argument("--output", type=Path, default=ROOT / "runs")
            child.add_argument("--base-port", type=int, default=19100)
            child.add_argument("--sitl", type=Path, default=ROOT / "ArducopterSITL" / "arducopter.exe")
            child.add_argument("--parameters", type=Path, default=ROOT / "ArducopterSITL" / "copter.parm")
        if command == "batch":
            child.add_argument("--repeat", type=int, default=2)
    args = parser.parse_args(argv)
    try:
        from swarm_sim.quality import resolve_policy
        policy_path = getattr(args, "quality_policy", None)
        policy = resolve_policy(json.loads(policy_path.read_text(encoding="utf-8-sig")) if policy_path else None)
        if args.command == "plan":
            from swarm_sim.tasks import compile_task
            from swarm_sim.recording import write_json
            scene = compile_task(json.loads(args.task.read_text(encoding="utf-8-sig")))
            if args.output.exists():
                raise ValueError("plan output already exists; choose a new filename")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            write_json(args.output, scene)
            print(json.dumps(dict(output=str(args.output), planning=scene["planning"]), indent=2))
            return 0
        if args.command == "analyze":
            from swarm_sim.analysis import analyze_run
            output, quality, labels = analyze_run(args.run_directory, policy)
            print(json.dumps(dict(output=str(output), quality=quality, mission_success=labels["mission_success"]), indent=2))
            return 0
        if args.command == "dataset":
            from swarm_sim.dataset import build_dataset
            result = build_dataset(args.runs, args.output, args.split_salt)
            print(json.dumps(dict(output=str(args.output), counts=result["counts"]), indent=2))
            return 0
        if args.command == "audit":
            from swarm_sim.audit import audit_paths
            print(json.dumps(audit_paths(args.scenario, args.time_unit), ensure_ascii=False, indent=2))
            return 0
        scenario = load(args.scenario)
        if args.command == "validate":
            from swarm_sim.tasks import validate_task_binding
            validate_task_binding(scenario)
            print(json.dumps({"valid": True, "scenario": scenario["scenario_id"],
                              "vehicles": len(scenario["vehicles"]), "phases": len(scenario["phases"])}, indent=2))
            return 0
        from swarm_sim.runner import run_scene
        count = args.repeat if args.command == "batch" else 1
        if not 1 <= count <= 100:
            raise ValueError("repeat must be in [1, 100]")
        failed = False
        for _ in range(count):
            _, metadata, quality = run_scene(scenario, args.output, args.sitl, args.parameters, args.base_port, policy)
            failed |= not quality["usable"]
            if metadata["status"] == "interrupted":
                break
        return 1 if failed else 0
    except (ValueError, KeyError, TypeError, OSError, ImportError) as exc:
        parser.exit(2, f"Error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
