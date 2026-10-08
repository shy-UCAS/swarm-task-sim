"""Run named unittest modules with simulator launch denied and save test IDs."""
import argparse
import json
from pathlib import Path
import sys
import time
import unittest

PROJECT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(PROJECT), str(PROJECT / "tests")]


def deny_simulator(event, args):
    if event == "subprocess.Popen":
        executable, command = args[:2]
        words = [str(executable), *(str(item) for item in command)] if isinstance(command, (list, tuple)) else [str(executable), str(command)]
        if any("arducopter" in word.lower() or "consoleapp1.exe" in word.lower() for word in words):
            raise PermissionError("offline tests must not launch a simulator")


class EvidenceResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rows = []

    def startTest(self, test):
        self.started = time.monotonic()
        super().startTest(test)

    def stopTest(self, test):
        failures = {getattr(case, "test_case", case).id() for case, _ in self.failures}
        errors = {getattr(case, "test_case", case).id() for case, _ in self.errors}
        skipped = {case.id() for case, _ in self.skipped}
        self.rows.append(dict(test=test.id(), result="failure" if test.id() in failures else
                             "error" if test.id() in errors else "skipped" if test.id() in skipped else "passed",
                             seconds=time.monotonic() - self.started))
        super().stopTest(test)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("modules", nargs="+")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("choose a new evidence file")
    sys.addaudithook(deny_simulator)
    suite = unittest.defaultTestLoader.loadTestsFromNames(args.modules)
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    report = dict(modules=args.modules, total=result.testsRun, failures=len(result.failures),
                  errors=len(result.errors), skipped=len(result.skipped), passed=result.wasSuccessful(),
                  tests=result.rows, failure_details=[(case.id(), details) for case, details in result.failures],
                  error_details=[(case.id(), details) for case, details in result.errors],
                  simulator_launch_forbidden=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return int(not result.wasSuccessful())


if __name__ == "__main__":
    raise SystemExit(main())
