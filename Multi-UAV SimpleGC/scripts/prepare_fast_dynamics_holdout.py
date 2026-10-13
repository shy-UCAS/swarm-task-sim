"""Register, then generate/freeze static M2-02B inputs; no flight execution."""
import argparse
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from swarm_sim.fast_dynamics.holdout import freeze, register
from swarm_sim.fast_dynamics.output_policy import resolve_output_root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    prepare = actions.add_parser("register")
    prepare.add_argument("--output-root")
    prepare.add_argument("--attempt", required=True)
    prepare.add_argument("--source-records", required=True)
    prepare.add_argument("--inventory", required=True)
    run = actions.add_parser("freeze")
    run.add_argument("--registration", required=True)
    run.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    if args.action == "register":
        root = resolve_output_root(args.output_root)["root"]
        result = register(args.attempt, root, PROJECT, args.source_records, args.inventory,
                          PROJECT / "docs/fast_dynamics_m2/M2-02B_method.md")
    else:
        result = freeze(args.registration, args.expected_sha256)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
