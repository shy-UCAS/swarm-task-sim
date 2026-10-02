"""Read-only replay of accepted WP-S packets and the failed V01 parameter gate."""

import copy
import json
import unittest
from pathlib import Path

from swarm_sim.run_provenance import (PARAMETER_COMPARISON_VERSION, check_stat_reset,
                                     compare_parameter_readback, digest, verified_wp_s_baseline)


ROOT = Path(__file__).resolve().parents[1]
STARTED = "2026-10-01T15:32:48+00:00"
RESET = 339262368.0


def fixture():
    actual = {"STAT_RESET": RESET, "STAT_BOOTCNT": 1., "STAT_FLTTIME": 0., "STAT_RUNTIME": 0.,
              "WPNAV_SPEED": 500., "WPNAV_ACCEL": 100., "SYSID_THISMAV": 1.}
    evidence = dict(complete=True, status="complete", parameter_count=len(actual), received_count=len(actual),
                    missing_indices=[], all_parameters=actual)
    baseline = dict(baselines=[dict(agents=dict(uav_01=copy.deepcopy(evidence)))])
    return evidence, baseline


class ParameterComparisonV2Tests(unittest.TestCase):
    def compare(self, evidence, baseline, started=STARTED):
        compare_parameter_readback(evidence, baseline, 1, run_started_utc=started)
        return evidence["parameter_comparison"]

    def test_reset_is_checked_even_when_equal_to_baseline(self):
        evidence, baseline = fixture()
        with self.assertRaisesRegex(ValueError, "STAT_RESET"):
            self.compare(evidence, baseline, "2026-10-01T15:37:49+00:00")
        report = evidence["parameter_comparison"]
        self.assertEqual(report["stat_reset"]["delta_s"], -301.)
        self.assertFalse(report["pass"])

    def test_reset_different_from_baseline_has_inclusive_300_second_limits(self):
        for offset in (-300., 300., -300.001, 300.001):
            evidence, baseline = fixture()
            evidence["all_parameters"]["STAT_RESET"] += offset
            with self.subTest(offset=offset):
                if abs(offset) <= 300:
                    report = self.compare(evidence, baseline)
                    self.assertTrue(report["pass"])
                else:
                    with self.assertRaisesRegex(ValueError, "STAT_RESET"):
                        self.compare(evidence, baseline)
                check = evidence["parameter_comparison"]["stat_reset"]
                self.assertEqual(check["raw_value"], RESET + offset)
                self.assertAlmostEqual(check["delta_s"], offset, places=5)
                self.assertIsNotNone(check["converted_utc"])
                self.assertEqual(check["boundary"], "inclusive")

    def test_naive_missing_invalid_and_nonfinite_timestamp_rejected(self):
        for raw, started in ((None, STARTED), (True, STARTED), (float("nan"), STARTED),
                             (float("inf"), STARTED), (1e99, STARTED),
                             (RESET, "2026-10-01T15:32:48"), (RESET, "nonsense"), (RESET, None)):
            with self.subTest(raw=raw, started=started):
                result = check_stat_reset(raw, started)
                self.assertFalse(result["pass"])
                self.assertIsNotNone(result["error"])

    def test_reset_start_offset_is_normalized_to_utc(self):
        result = check_stat_reset(RESET, "2026-10-01T08:32:48-07:00")
        self.assertTrue(result["pass"])
        self.assertEqual(result["converted_utc"], STARTED)
        self.assertEqual(result["delta_s"], 0.)

    def test_fresh_statistics_are_constants_even_with_a_polluted_reference(self):
        for name, bad in (("STAT_BOOTCNT", 2.), ("STAT_BOOTCNT", 0.), ("STAT_FLTTIME", 1.), ("STAT_RUNTIME", 1.)):
            evidence, baseline = fixture()
            evidence["all_parameters"][name] = bad
            baseline["baselines"][0]["agents"]["uav_01"]["all_parameters"][name] = bad
            with self.subTest(name=name, bad=bad), self.assertRaisesRegex(ValueError, name):
                self.compare(evidence, baseline)
            self.assertFalse(evidence["parameter_comparison"]["fresh_instance"][name]["pass"])

    def test_navigation_changes_are_still_rejected(self):
        for name in ("WPNAV_SPEED", "WPNAV_ACCEL"):
            evidence, baseline = fixture()
            evidence["all_parameters"][name] += 1
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, name):
                self.compare(evidence, baseline)

    def test_partial_counts_names_status_and_indices_cannot_pass(self):
        mutations = (
            lambda row: row.update(complete=False),
            lambda row: row.update(received_count=6),
            lambda row: row.update(parameter_count=8),
            lambda row: row.update(missing_indices=[0]),
            lambda row: row.update(status="failed"),
            lambda row: row["all_parameters"].pop("WPNAV_SPEED"),
            lambda row: row["all_parameters"].update(EXTRA=0.),
            lambda row: row.update(parameter_entries={}),
            lambda row: row.update(parameter_count=None),
        )
        for index, mutate in enumerate(mutations):
            evidence, baseline = fixture()
            mutate(evidence)
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, "incomplete|collection"):
                self.compare(evidence, baseline)
            self.assertFalse(evidence["parameter_comparison"]["collection_complete"])
            self.assertFalse(evidence["parameter_comparison"]["pass"])
            self.assertEqual(evidence["parameter_comparison_version"], PARAMETER_COMPARISON_VERSION)

    def test_real_wp_s_and_v01_readbacks_have_valid_reset_but_partial_v01_stays_rejected(self):
        baseline = verified_wp_s_baseline(ROOT)
        run_paths = [ROOT / "runs" / row["run"] for row in baseline["baselines"]]
        run_paths.append(ROOT / "verification/v04_v1_20261001/runs/recon_shared_demo_3uav_20261001T182936Z_6bca981d")
        expected_times = ["2026-10-01T15:32:48+00:00", "2026-10-01T15:38:08+00:00", "2026-10-01T18:29:52+00:00"]
        accepted, rejected = 0, 0
        for path, converted in zip(run_paths, expected_times):
            sources = [path / "metadata.json", path / "firmware_parameters.json"]
            before = {str(source): digest(source) for source in sources}
            metadata, parameters = [json.loads(source.read_text(encoding="utf-8-sig")) for source in sources]
            for agent, source in sorted(parameters.items()):
                evidence = copy.deepcopy(source)
                sysid = int(evidence["all_parameters"]["SYSID_THISMAV"])
                with self.subTest(run=path.name, agent=agent):
                    if source["complete"]:
                        compare_parameter_readback(evidence, baseline, sysid, run_started_utc=metadata["started_utc"])
                        self.assertTrue(evidence["parameter_comparison"]["pass"])
                        accepted += 1
                    else:
                        self.assertEqual((evidence["received_count"], evidence["parameter_count"]), (1105, 1202))
                        with self.assertRaisesRegex(ValueError, "incomplete"):
                            compare_parameter_readback(evidence, baseline, sysid, run_started_utc=metadata["started_utc"])
                        self.assertFalse(evidence["parameter_comparison"]["pass"])
                        rejected += 1
                    check = evidence["parameter_comparison"]["stat_reset"]
                    self.assertTrue(check["pass"])
                    self.assertEqual(check["converted_utc"], converted)
                    self.assertTrue(0 < check["delta_s"] < 16)
            self.assertEqual({str(source): digest(source) for source in sources}, before)
        self.assertEqual((accepted, rejected), (8, 1))
        self.assertEqual(metadata["status"], "failed")  # no relabeling of the historical failed run
