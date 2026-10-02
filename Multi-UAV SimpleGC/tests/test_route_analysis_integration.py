"""Successful schema-2 analysis from hand-authored source evidence, without SITL."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from swarm_sim import __version__
from swarm_sim.analysis import analyze_run, digest
from swarm_sim.dataset import build_dataset
from swarm_sim.episode_loader import FEATURE_COLUMNS, load_episode
from swarm_sim.observation_processing import processing_versions
from swarm_sim.recording import write_json
from swarm_sim.scenario import enu_to_geo
from swarm_sim.tasks import compile_task


ROOT = Path(__file__).resolve().parents[1]


class RouteAnalysisIntegrationTests(unittest.TestCase):
    def test_successful_route_evidence_survives_analysis_export_and_loading(self):
        task = json.loads((ROOT / "missions/v3/recon_shared_3uav_route.json").read_text(encoding="utf-8"))
        task["task_id"] = "hand_authored_route_success"
        task.pop("family_id", None)
        task["scenario"]["regions"][0].update(width_m=3.0, height_m=3.0)
        task["scenario"]["vehicles"] = [dict(id="uav_01", sysid=1, east_m=1.5,
                                             north_m=-2.0, heading_deg=0.0)]
        task["mission"]["return_required"] = False
        scene = compile_task(task)
        self.assertEqual(scene["schema_version"], 2)
        self.assertEqual([p["name"] for p in scene["phases"]], ["p00_approach", "p01_observe"])

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = root / "run"
            (run / "raw").mkdir(parents=True)
            metadata = dict(version=__version__, run_id="hand_authored_route_success",
                            scenario=scene, status="completed", run_epoch_monotonic_s=100.0,
                            flight_epoch_monotonic_s=103.0, mission_end_monotonic_s=110.0,
                            elapsed_s=15.0)
            write_json(run / "metadata.json", metadata)
            write_json(run / "scenario.json", scene)
            events = [dict(event=kind, agent_id="uav_01", t=stamp) for kind, stamp in (
                ("armed_confirmed", 1.0), ("airborne_ready", 3.0),
                ("landing_started", 10.0), ("landed", 12.1))]
            for name, release, arrival, planner_index in (
                    ("p00_approach", 3.0, 5.0, 0), ("p01_observe", 6.0, 9.0, 1)):
                events.append(dict(event="phase_release_scheduled", phase=name, t=release,
                                   release_t=release))
                events.extend(dict(event=kind, agent_id="uav_01", phase=name, t=stamp)
                              for kind, stamp in (("phase_start_sent", release),
                                                  ("phase_auto_confirmed", release),
                                                  ("phase_finished", arrival),
                                                  ("task_target_verified", arrival + .5)))
                events.append(dict(event="waypoint_reached", agent_id="uav_01", phase=name,
                                   t=arrival, recv_monotonic_s=100 + arrival, seq=2,
                                   route_index=0, planner_index=planner_index, terminal=True,
                                   time_source="single_rx_host_receive"))
            events.sort(key=lambda event: event["t"])
            (run / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")

            # Hand-authored observations are independent of the planner: travel
            # north at 1 m/s from -2 to 0, pause, then travel from 0 to 3. Every
            # cell center of the 3 x 3 region is within radius 4 of this path.
            # Actual arrival is deliberately later than the 3 m/s nominal plan.
            packets, truth_packets = [], []
            for index in range(151):
                stamp = index / 10
                north = -2.0 if stamp <= 3 else stamp - 5 if stamp < 5 else 0.0 if stamp <= 6 else stamp - 6 if stamp < 9 else 3.0
                up = 0.0 if stamp <= 1 else 4 * (stamp - 1) if stamp < 3 else 8.0 if stamp <= 10 else 8 - 4 * (stamp - 10) if stamp < 12 else 0.0
                north_speed = 1.0 if 3 <= stamp < 5 or 6 <= stamp < 9 else 0.0
                up_speed = 4.0 if 1 <= stamp < 3 else -4.0 if 10 <= stamp < 12 else 0.0
                lat, lon = enu_to_geo(1.5, north, scene["origin"])
                packets.append(dict(recv_monotonic_s=100 + stamp,
                                    message=dict(mavpackettype="SYSTEM_TIME", time_boot_ms=index * 100)))
                packets.append(dict(recv_monotonic_s=100 + stamp, message=dict(
                    mavpackettype="GLOBAL_POSITION_INT", time_boot_ms=index * 100,
                    lat=round(lat * 1e7), lon=round(lon * 1e7), alt=round((12 + up) * 1000),
                    vx=round(north_speed * 100), vy=0, vz=round(-up_speed * 100))))
                truth_packets.append(dict(TimeUS=index * 100000, Lat=lat, Lng=lon,
                                          Alt=12 + up, Q1=1, Q2=0, Q3=0, Q4=0))
            raw = run / "raw/uav_01.jsonl"
            raw.write_text("\n".join(json.dumps(p) for p in packets), encoding="utf-8")
            binary = run / "sitl/uav_01/logs/synthetic.BIN"
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"Hand-authored SIM fixture; only DFReader is mocked")
            source_hashes = {path: digest(path) for path in (raw, binary, run / "events.jsonl",
                                                           run / "metadata.json", run / "scenario.json")}

            def reader(_):
                messages = iter(SimpleNamespace(get_type=lambda: "SIM", to_dict=lambda p=p: p)
                                for p in truth_packets)
                return SimpleNamespace(recv_match=lambda **_: next(messages, None), close=lambda: None)

            # All processing above the binary decoder is production code:
            # full-stream validation, passive clocks, interpolation, windows,
            # intent and lifecycle gates, versioned artifacts, export and load.
            with patch("pymavlink.DFReader.DFReader_binary", side_effect=reader):
                output, quality, labels = analyze_run(run)
            self.assertTrue(labels["mission_success"], labels)
            self.assertTrue(labels["mission_success_observation"])
            self.assertEqual(labels["semantic_consistency"], "agree")
            self.assertTrue(quality["execution_constraints_pass"], quality)
            self.assertTrue(quality["episode_quality_eligible"], quality)
            self.assertTrue(quality["benchmark_eligible"], quality)
            self.assertEqual(quality["frames"], 71)
            for channel in ("truth", "observation"):
                coverage = labels["mission_metrics"][channel]["coverage"]
                self.assertEqual(coverage["covered_cells"], 9)
                self.assertEqual(coverage["global_coverage_ratio"], 1.0)

            windows = json.loads((output / "phase_windows.json").read_text(encoding="utf-8"))
            self.assertEqual(windows["schema_version"], 2)
            self.assertEqual(windows["windows"], windows["channels"]["observation"])
            for channel, offset in (("observation", 0.0), ("truth", .1)):
                approach, observe = windows["channels"][channel]
                self.assertEqual((approach["start_s"], observe["start_s"]), (0.0, 3.0))
                self.assertEqual((approach["end_s"], observe["end_s"]), (3.0, 7.0))
                self.assertFalse(approach["service_enabled"])
                self.assertTrue(observe["service_enabled"])
                for window, arrival in ((approach, 2.0), (observe, 6.0)):
                    self.assertAlmostEqual(window["arrival_s"], arrival + offset, places=6)
                    self.assertEqual(window["arrival_source"], "trajectory_stop")
                    self.assertTrue(window["arrival_verified"])
                    self.assertTrue(window["complete_execution_window"])
                    self.assertTrue(window["trajectory_evidence_complete"])
                    self.assertAlmostEqual(window["barrier_wait_host_s"], 1.0 - offset, places=6)
                self.assertEqual(observe["waypoint_events"][0]["planner_index"], 1)

            metrics = json.loads((output / "execution_metrics.json").read_text(encoding="utf-8"))
            nominal = metrics["nominal_timing_deviation_s"]["assessment"]
            self.assertTrue(nominal["complete"])
            self.assertTrue(nominal["within_tau"])
            self.assertEqual(nominal["expected_waypoints"], 2)
            self.assertEqual(nominal["paired_waypoints"], 2)
            self.assertEqual(nominal["missing"], [])
            for row, actual, expected in zip(nominal["records"], (2.0, 3.0), (2 / 3, 1.0)):
                self.assertEqual(row["seq"], 2)
                self.assertEqual(row["route_index"], 0)
                self.assertEqual(row["actual_s"], actual)
                self.assertAlmostEqual(row["nominal_s"], expected, places=6)
                self.assertAlmostEqual(row["deviation_s"], actual - expected, places=6)
                self.assertEqual(row["tau_s"], 3.0)

            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["control_mode"], "semantic_phase_route_v1")
            self.assertFalse(manifest["partial_window"])
            self.assertEqual(manifest["time_epoch_host_s"], 103.0)
            for name in ("manifest.json", "quality.json", "phase_windows.json", "execution_metrics.json"):
                artifact = json.loads((output / name).read_text(encoding="utf-8"))
                self.assertEqual({key: artifact[key] for key in processing_versions()}, processing_versions())
            for name, fingerprint in manifest["artifact_sha256"].items():
                self.assertEqual(digest(output / name), fingerprint, name)
            for path, fingerprint in source_hashes.items():
                self.assertEqual(digest(path), fingerprint)
                self.assertEqual(manifest["source_sha256"][str(path.relative_to(run))], fingerprint)

            dataset = build_dataset([run], root / "dataset")
            self.assertEqual(dataset["counts"]["total"], 1)
            self.assertEqual(dataset["counts"]["episode_quality_eligible"], 1)
            loaded = load_episode(root / "dataset" / dataset["episodes"][0]["directory"])
            self.assertEqual(len(loaded["x"]), 71)
            self.assertEqual(loaded["agent_ids"], ["uav_01"])
            self.assertTrue(all(mask == [True] for mask in loaded["mask"]))
            self.assertTrue(all(len(frame) == 1 and len(frame[0]) == 6 for frame in loaded["x"]))
            self.assertEqual(loaded["metadata"]["feature_columns"], list(FEATURE_COLUMNS))
            self.assertTrue(loaded["targets"]["mission_success"])
            self.assertTrue(loaded["metadata"]["episode_quality_eligible"])
            self.assertEqual(loaded["metadata"]["control_mode"], "semantic_phase_route_v1")


if __name__ == "__main__":
    unittest.main()
