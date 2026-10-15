"""Offline M1 regressions; deliberately excludes every fastsim executor test."""
import json
from pathlib import Path
import subprocess
import sys
import types
import unittest
import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(PROJECT), str(PROJECT / "tests")]


def main():
    import test_v07_s2 as base
    import test_v07_s2_precision as precision
    import test_v07_s2_sector as sector
    import test_v07_s2_infrastructure as infrastructure
    import test_v07_s2_final_helpers as helpers
    classes = [base.SemanticTests, base.LoaderAndSurveyTests, precision.ExactGeometryTests,
               precision.IndependentAuditTests, precision.RevisedOutcomeAndTimingTests]
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(c) for c in classes)
    for name in unittest.defaultTestLoader.getTestCaseNames(sector.SurveyEvidenceAndRuntimeTests):
        if name != "test_frozen_plant_can_complete_after_old_600_second_limit":
            suite.addTest(sector.SurveyEvidenceAndRuntimeTests(name))
    # Exercise view contracts using records that explicitly satisfy the new
    # required metadata; historical missing fields now intentionally fail closed.
    class CurrentViewTests(infrastructure.ViewTests):
        def records(self):
            return [{**row, "all_groups_complete": True, "execution_status": "completed"} for row in super().records()]
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(CurrentViewTests))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    source = subprocess.run(["git", "show", "54842c2:Multi-UAV SimpleGC/task_v07/labels.py"], cwd=PROJECT,
                            check=True, capture_output=True, encoding="utf-8").stdout
    baseline = types.ModuleType("task_v07._m1_baseline_labels"); baseline.__package__ = "task_v07"
    exec(compile(source, "54842c2:labels.py", "exec"), baseline.__dict__)
    from task_v07.labels import measure
    comparisons = []
    for name, fixture in (("intrusion", base.fixture), ("area_search", sector.scanned_fixture)):
        scene, task, run = fixture()
        for cutoff in (None, 1.):
            expected, frame = baseline.measure(scene, task, run, "synchronous", cutoff_s=cutoff)
            actual, observed = measure(scene, task, run, "synchronous", cutoff_s=cutoff)
            equal = expected == actual and all(np.array_equal(frame[key], observed[key]) for key in frame)
            comparisons.append({"role": name, "cutoff_s": cutoff, "labels_and_frames_identical": equal})
    passed = result.wasSuccessful() and all(r["labels_and_frames_identical"] for r in comparisons)
    evidence = {"passed": passed, "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
                "new_simulations": 0, "baseline": "54842c2", "vertical_slice_comparisons": comparisons}
    path = PROJECT / "docs/v07/evidence/m1/regression_results.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(evidence, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
