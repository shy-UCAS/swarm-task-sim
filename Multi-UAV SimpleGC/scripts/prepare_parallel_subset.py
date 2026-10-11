"""Prepare an imported pilot subset without changing the production prepare CLI."""
import argparse
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from swarm_sim.parallel_batch import read
from swarm_sim.parallel_subset import prepare_subset


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-bundle", type=Path, required=True)
    parser.add_argument("--mission-ids", type=Path, required=True, help="JSON array; complete families only")
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--shards", type=int, default=4)
    parser.add_argument("--base-port", type=int, default=19100)
    parser.add_argument("--max-attempts", type=int, required=True)
    parser.add_argument("--storage-bytes-per-attempt", type=int, required=True)
    parser.add_argument("--export-reserve-bytes", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        plan = prepare_subset(args.source_bundle, read(args.mission_ids), args.batch_id,
            shards=args.shards, max_attempts=args.max_attempts, base_port=args.base_port,
            storage_bytes_per_attempt=args.storage_bytes_per_attempt,
            export_reserve_bytes=args.export_reserve_bytes)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"Error: {exc}\n")
    print(json.dumps(dict(batch_directory=plan["root"], tasks=len(plan["tasks"]),
                         shards=plan["shards"], purpose="pilot", training_data=False), indent=2))


if __name__ == "__main__":
    main()
