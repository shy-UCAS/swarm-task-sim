"""Reject newly submitted Git blobs over 5 MiB; leave unchanged history alone."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess


MAX_FILE_BYTES = 5 * 1024 * 1024


def git(repo: Path, *arguments: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *arguments])


def oversized_files(repo: Path, base: str, head: str = "HEAD",
                    max_bytes: int = MAX_FILE_BYTES) -> list[tuple[str, int]]:
    """Compare committed trees, including additions, copies, renames and edits."""
    if max_bytes < 0:
        raise ValueError("max_bytes must be nonnegative")
    changed = set(git(repo, "diff", "--name-only", "-z", "--no-renames",
                      "--diff-filter=ACMRT", base, head, "--").split(b"\0"))
    failures = []
    # ls-tree reports stored blob sizes; sparse checkouts and Git filters do not
    # change the verdict. NUL delimiters also preserve spaces and Unicode names.
    for record in git(repo, "ls-tree", "-r", "-l", "-z", head).split(b"\0"):
        if not record:
            continue
        attributes, path = record.split(b"\t", 1)
        _, kind, _, size = attributes.split()
        if path in changed and kind == b"blob" and int(size) > max_bytes:
            failures.append((os.fsdecode(path), int(size)))
    return sorted(failures)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--base", required=True, help="Base commit/tree to compare")
    parser.add_argument("--head", default="HEAD", help="Submitted commit/tree")
    parser.add_argument("--max-bytes", type=int, default=MAX_FILE_BYTES)
    args = parser.parse_args(argv)
    try:
        failures = oversized_files(args.repo, args.base, args.head, args.max_bytes)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"File-size check could not inspect Git trees: {error}\n")
    for path, size in failures:
        print(f"Oversized submitted file: {path!r}: {size} bytes > {args.max_bytes} bytes")
    if failures:
        return 1
    print(f"Changed-file size check passed (limit: {args.max_bytes} bytes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
