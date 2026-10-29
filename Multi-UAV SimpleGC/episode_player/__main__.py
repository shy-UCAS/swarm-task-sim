import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Read-only offline ENU episode player")
    parser.add_argument("--source", type=Path, help="Episode, examples, dataset, or finalized batch directory")
    args = parser.parse_args()
    from .window import launch
    return launch(args.source)


if __name__ == "__main__":
    raise SystemExit(main())
