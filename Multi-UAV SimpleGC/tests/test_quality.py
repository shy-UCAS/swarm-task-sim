"""Regression cases for v0.2.2 evidence, policy, and interpolation boundaries."""

import csv
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from swarm_sim import __version__

from swarm_sim.analysis import analyze_run, digest
from swarm_sim.dataset import build_dataset
from swarm_sim.evaluation import coverage_ratio, longest_dwell
from swarm_sim.observations import ObservationStream, decode_observation, live_observation
from swarm_sim.quality import clock_grade, eligibility, policy_hash, resolve_policy, summarize_clocks
from swarm_sim.recording import Recorder, export_dataset, resample, write_json
from swarm_sim.scenario import load
from swarm_sim.truth import fit_clock

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = dict(lat=37, lon=122, alt_msl_m=12)


def message(**changes):
    packet = dict(mavpackettype="GLOBAL_POSITION_INT", time_boot_ms=1000,
                  lat=370000000, lon=1220000000, alt=20000, relative_alt=8000, vx=0, vy=0, vz=0)
    packet.update(changes)
    return packet


def create_run(root, run_id="test", packets=None):
    root.mkdir(parents=True)
    (root / "raw").mkdir()
    scene = load(ROOT / "scenarios/demo_1uav.json")
    scene["origin"] = ORIGIN
    metadata = dict(run_id=run_id, version="0.2.0", status="completed", scenario=scene,
                    run_epoch_monotonic_s=100, flight_epoch_monotonic_s=100,
                    mission_end_monotonic_s=100.2, elapsed_s=0.2)
    write_json(root / "metadata.json", metadata)
    write_json(root / "scenario.json", scene)
    (root / "events.jsonl").write_text("", encoding="utf-8")
    packets = packets if packets is not None else [dict(recv_monotonic_s=100 + i / 10,
        message=message(time_boot_ms=1000 + i * 100)) for i in range(4)]
    (root / "raw/uav_01.jsonl").write_text("\n".join(json.dumps(p) for p in packets), encoding="utf-8")
    return metadata


class PolicyTests(unittest.TestCase):
    def test_clock_boundaries_unknown_and_nonfinite(self):
        policy = resolve_policy()
        for residual, expected in ((0, "strict"), (0.02, "strict"), (0.020001, "acceptable"),
                                   (0.05, "acceptable"), (0.050001, "failed"), (None, "unknown"),
                                   (float("nan"), "unknown"), (float("inf"), "unknown"), (-1, "unknown")):
            with self.subTest(residual=residual):
                self.assertEqual(clock_grade(dict(available=True, receive_residual_abs_p95_s=residual), policy), expected)
        self.assertEqual(clock_grade(dict(available=False, receive_residual_abs_p95_s=0), policy), "unknown")
        self.assertFalse(fit_clock([(i / 10, i / 10) for i in range(80)] + [(8, float("nan"))])["available"])

    def test_all_vehicles_must_satisfy_grade_and_strict_requires_other_checks(self):
        policy = resolve_policy()
        clocks = dict(a=dict(available=True, receive_residual_abs_p95_s=0.01),
                      b=dict(available=True, receive_residual_abs_p95_s=0.03))
        quality = dict(data_quality_pass=True, truth_available_pass=True, run_completed=True,
                       separation_status="clear_observed", truth_separation=dict(status="clear_observed"),
                       clock_quality=summarize_clocks(clocks, policy))
        self.assertEqual(eligibility(quality, True), dict(benchmark_eligible=True, strict_benchmark_eligible=False))
        clocks["b"]["receive_residual_abs_p95_s"] = 0.02
        quality["clock_quality"] = summarize_clocks(clocks, policy)
        self.assertTrue(eligibility(quality, True)["strict_benchmark_eligible"])
        for field in ("run_completed", "data_quality_pass", "truth_available_pass"):
            broken = dict(quality, **{field: False})
            self.assertFalse(any(eligibility(broken, True).values()))
        self.assertFalse(any(eligibility(quality, None).values()))
        clocks["b"]["available"] = False
        self.assertEqual(summarize_clocks(clocks, policy)["overall"], "unknown")

    def test_policy_rejects_bad_overrides_and_hashes_effective_thresholds(self):
        for invalid in ({"clock_strict_p95_s": 0.1}, {"clock_acceptable_p95_s": float("nan")},
                        {"horizontal_velocity_sanity_m_s": 0}, {"min_truth_valid_fraction": 1.1},
                        {"invalid_sample_interpolation": "fill"}, {"unknown": 1}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                resolve_policy(invalid)
        self.assertNotEqual(policy_hash(resolve_policy()), policy_hash(resolve_policy({"clock_acceptable_p95_s": 0.04})))
        self.assertEqual(policy_hash(resolve_policy()), policy_hash(resolve_policy({"horizontal_velocity_sanity_m_s": 50})))


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.policy = resolve_policy()

    def test_axis_conversion_and_exact_sanity_boundaries(self):
        values, reason = decode_observation(message(vx=4000, vy=3000, vz=-3000), ORIGIN, self.policy)
        self.assertIsNone(reason)
        self.assertEqual(values, [0, 0, 8, 30, 40, 30])
        self.assertEqual(decode_observation(message(vx=5001), ORIGIN, self.policy)[1], "horizontal_speed_out_of_bounds")
        self.assertEqual(decode_observation(message(vz=-3001), ORIGIN, self.policy)[1], "vertical_speed_out_of_bounds")

    def test_nonfinite_missing_and_invalid_fields_have_primary_reasons(self):
        for values, reason in ((dict(vx=float("nan")), "non_finite"), (dict(vz=float("inf")), "non_finite"),
                              (dict(lat=0, vx=8000), "position_out_of_bounds"),
                              (dict(vx=8000, vz=8000), "horizontal_speed_out_of_bounds"),
                              (dict(vx=True), "invalid_type"), (dict(time_boot_ms=-1), "invalid_timestamp")):
            self.assertEqual(decode_observation(message(**values), ORIGIN, self.policy)[1], reason)
        missing = message()
        del missing["vx"]
        self.assertEqual(decode_observation(missing, ORIGIN, self.policy)[1], "missing_fields")
        for host in (None, "invalid", float("nan"), -1):
            for packet, reason in ((missing, "missing_fields"), (message(vx=float("nan")), "non_finite"),
                                   (message(vx=8000), "invalid_timestamp"), (message(), "invalid_timestamp")):
                with self.subTest(host=host, packet=packet):
                    stream = ObservationStream(ORIGIN, self.policy, 100, 101)
                    stream.append(dict(recv_monotonic_s=host, message=packet))
                    self.assertEqual(stream.statistics["whole_run"]["dropped"][reason], 1)
                    self.assertEqual(live_observation(packet, host, 100, 0.5, ORIGIN, self.policy), (None, reason))

    def test_raw_counts_conserve_messages_with_explicit_window(self):
        stream = ObservationStream(ORIGIN, self.policy, 100, 101)
        for host, msg in ((99, message()), (100, message(vx=8000, vz=8000, time_boot_ms=2000)),
                          (100.5, message(vz=4000, time_boot_ms=2500)), (101, message(time_boot_ms=3000))):
            stream.append(dict(recv_monotonic_s=host, message=msg))
        for counts in (stream.statistics["whole_run"], stream.statistics["evaluation_window"]):
            self.assertEqual(counts["total_messages"], counts["accepted"] + counts["rejected"])
            self.assertEqual(counts["rejected"], sum(counts["dropped"].values()))
        self.assertEqual(stream.statistics["whole_run"]["total_messages"], 4)
        self.assertEqual(stream.statistics["evaluation_window"]["total_messages"], 3)
        self.assertIsNone(stream.records[1][2])

    def test_unplaceable_or_reset_timestamps_cannot_leave_a_valid_timeline(self):
        for msg in (message(time_boot_ms=float("nan")), message(time_boot_ms=999)):
            stream = ObservationStream(ORIGIN, self.policy, 100, 101)
            stream.append(dict(recv_monotonic_s=100, message=message()))
            stream.append(dict(recv_monotonic_s=100.1, message=msg))
            self.assertTrue(stream.timeline_error)
            self.assertEqual(stream.samples(), [])

    def test_live_recorder_and_both_offline_exports_agree_on_content(self):
        cases = (({}, 100), (dict(vx=float("nan")), 100), (dict(vz=float("inf")), 100),
                 (dict(vx=6000), 100), (dict(vz=3100), 100), (dict(lat=0), 100), ({}, None))
        for changes, received in cases:
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                packets = [dict(recv_monotonic_s=received + i / 10 if received is not None else None,
                                message=message(time_boot_ms=1000 + i * 100, **changes))
                           for i in range(4)]
                metadata = create_run(root / "run", packets=packets)
                run = root / "run"
                recorder = Recorder(run, [], ORIGIN, 100, 10, 0.5, self.policy)
                def snapshot():
                    recorder.stop.set()
                    return {"GLOBAL_POSITION_INT": (received, SimpleNamespace(**packets[0]["message"]))}
                recorder.vehicles = [SimpleNamespace(id="uav_01", snapshot=snapshot)]
                with patch("swarm_sim.recording.time.perf_counter", return_value=100):
                    recorder._run()
                self.assertIsNone(recorder.error)
                legacy = export_dataset(run, metadata, self.policy)
                with patch("swarm_sim.analysis.read_truth", return_value=([], {}, dict(available=False))):
                    output, quality, _ = analyze_run(run)
                def rows(path):
                    with path.open(encoding="utf-8", newline="") as file:
                        return list(csv.DictReader(file))
                expected = "0" if changes or received is None else "1"
                self.assertEqual(rows(run / "samples.csv")[0]["valid_position"], expected)
                self.assertTrue(all(r["valid"] == expected for r in rows(run / "processed.csv")))
                self.assertTrue(all(r["valid"] == expected for r in rows(output / "observations.csv")))
                self.assertEqual(legacy["observation_filter"], quality["observation_filter"])


class BarrierTests(unittest.TestCase):
    def test_rejected_packet_between_grid_ticks_breaks_dwell_and_coverage(self):
        samples = [(0, [0, 1, 8]), (0.05, None), (0.1, [10, 1, 8]), (0.2, [10, 1, 8])]
        rows = resample(samples, [0, 0.1, 0.2], 0.5)
        self.assertIsNone(rows[1][1])
        self.assertEqual(longest_dwell(rows, [5, 1, 8], 10, 0.5)[0], 0)
        coverage = coverage_ratio(rows, dict(east_m=0, north_m=0),
            dict(width_m=10, height_m=2, grid_m=1, footprint_radius_m=1), 8, 1, 0.5)
        self.assertLess(coverage["ratio"], 0.5)

    def test_sparse_grid_cannot_hide_long_source_gap(self):
        self.assertIsNone(resample([(0, [0] * 6), (1, [1] * 6)], [0, 1], 0.5)[1][1])

    def test_both_exporters_preserve_a_subgrid_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp) / "run"
            packets = [dict(recv_monotonic_s=100 + t,
                message=message(time_boot_ms=1000 + round(t * 1000), vx=9000 if t == 0.05 else 0))
                for t in (0, 0.05, 0.1, 0.2, 0.3)]
            metadata = create_run(run, packets=packets)
            export_dataset(run, metadata)
            with patch("swarm_sim.analysis.read_truth", return_value=([], {}, dict(available=False))):
                output, quality, _ = analyze_run(run)
            for path in (run / "processed.csv", output / "observations.csv"):
                with path.open(encoding="utf-8") as file:
                    rows = list(csv.DictReader(file))
                self.assertEqual(rows[1]["valid"], "0")
            self.assertLess(quality["observation_valid_fraction"]["uav_01"], 1)


class DatasetPolicyTests(unittest.TestCase):
    def test_legacy_policy_requires_reanalysis_and_version_records_do_not_relabel_history(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = root / "run"
            create_run(run)
            original_metadata = (run / "metadata.json").read_bytes()
            with patch("swarm_sim.analysis.read_truth", return_value=([], {}, dict(available=False))):
                output, _, _ = analyze_run(run)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["simulator_version"], "0.2.0")
            self.assertEqual(manifest["analysis_version"], __version__)
            self.assertEqual((run / "metadata.json").read_bytes(), original_metadata)
            del manifest["quality_policy"]
            del manifest["quality_policy_sha256"]
            write_json(output / "manifest.json", manifest)
            write_json(run / "analysis_latest.json", dict(directory=output.name, manifest_sha256=digest(output / "manifest.json")))
            with self.assertRaisesRegex(ValueError, "reanalyze legacy"):
                build_dataset([run], root / "legacy")
            self.assertFalse((root / "legacy").exists())

    def test_mixed_policies_refused_without_creating_output_and_defaults_propagate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runs = [root / "a", root / "b"]
            for i, run in enumerate(runs):
                create_run(run, run_id=str(i))
                with patch("swarm_sim.analysis.read_truth", return_value=([], {}, dict(available=False))):
                    analyze_run(run, {"horizontal_velocity_sanity_m_s": 50 - i})
            with self.assertRaisesRegex(ValueError, "mixed quality policies"):
                build_dataset(runs, root / "mixed")
            self.assertFalse((root / "mixed").exists())
            dataset = build_dataset([runs[0]], root / "single")
            self.assertEqual(dataset["quality_policy_sha256"], policy_hash(resolve_policy()))
            self.assertEqual(dataset["counts"]["strict_eligible"], 0)
            self.assertIn("strict_benchmark_eligible", dataset["episodes"][0])


if __name__ == "__main__":
    unittest.main()
