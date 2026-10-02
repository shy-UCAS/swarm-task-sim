"""Run the offline test suite and save per-test WP-G evidence (never launches SITL)."""
import argparse
import hashlib
import json
import subprocess
import sys
import time
import unittest
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class EvidenceResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = {}

    def startTest(self, test):
        self.records[test.id()] = dict(id=test.id(), status="RUNNING")
        super().startTest(test)

    def addSuccess(self, test):
        self.records[test.id()]["status"] = "PASS"
        super().addSuccess(test)

    def addFailure(self, test, err):
        self.records[test.id()]["status"] = "FAIL"
        super().addFailure(test, err)

    def addError(self, test, err):
        self.records[test.id()]["status"] = "ERROR"
        super().addError(test, err)

    def addSkip(self, test, reason):
        self.records[test.id()].update(status="SKIP", reason=reason)
        super().addSkip(test, reason)

    def addSubTest(self, test, subtest, err):
        if err is not None:
            self.records[test.id()]["status"] = "FAIL"
        super().addSubTest(test, subtest, err)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    tracked = subprocess.check_output(["git", "-c", f"safe.directory={ROOT.parent.as_posix()}",
                                       "ls-files", "tests"], cwd=ROOT, text=True)
    original_modules = {Path(p).stem for p in tracked.splitlines() if Path(p).name.startswith("test_")}
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    started = time.perf_counter()
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    duration = time.perf_counter() - started
    records = list(result.records.values())
    original = [r for r in records if r["id"].split(".")[0] in original_modules]
    groups = {}
    for row in records:
        module = row["id"].split(".")[0]
        counts = groups.setdefault(module, Counter())
        counts[row["status"]] += 1
    source_hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                     for folder in ("swarm_sim", "tests") for p in sorted((ROOT / folder).glob("*.py"))}
    report = dict(recorded_utc=datetime.now(timezone.utc).isoformat(), duration_s=duration,
                  interpreter=sys.version, status="PASS" if result.wasSuccessful() else "FAIL",
                  tests_run=result.testsRun, outcomes=dict(Counter(r["status"] for r in records)),
                  R01=dict(count=len(original), expected_count=150,
                           status="PASS" if len(original) == 150 and all(r["status"] == "PASS" for r in original) else "FAIL"),
                  modules=groups, tests=records, source_sha256=source_hashes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    print(json.dumps({k: report[k] for k in ("status", "tests_run", "outcomes", "R01", "duration_s")}))
    return 0 if result.wasSuccessful() and report["R01"]["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
