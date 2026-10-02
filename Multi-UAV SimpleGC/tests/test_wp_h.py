"""WP-H: explicit integer NAV hold semantics and phase-scoped CMD evidence."""

import copy
import json
import math
import tempfile
import unittest
from pathlib import Path

from swarm_sim.episode_loader import load_episode
from swarm_sim.generation import canonical_hash
from swarm_sim.mission_v3 import from_v2, normalize_v3
from swarm_sim.onboard_mission_params import VERSION, compare_onboard_mission_params
from swarm_sim.observation_processing import processing_versions
from swarm_sim.protocol import (V05_AC4_TIMING_VERSION, V05_EXECUTION_ARTIFACTS_VERSION,
                                V05_ROUTE_PROGRESS_VERSION, semantic_protocol)
from swarm_sim.quality import v3_eligibility
from swarm_sim.recording import write_json
from v3_artifact_fixture import make_run, rehash


ROOT = Path(__file__).parents[1]


def example(mode="semantic_phase_route_v1"):
    source = json.loads((ROOT / "missions/recon_shared_3uav.json").read_text(encoding="utf-8"))
    return from_v2(source, mode)


def simple_scene(required=True):
    vehicle = dict(id="uav_01", sysid=1, east_m=0, north_m=0)
    phases = [dict(name="p00_approach", semantic_phase="approach", speed_m_s=3,
                   terminal_hold_s=0, routes={"uav_01": [dict(east_m=1, north_m=0, up_m=8)]}),
              dict(name="p01_observe", semantic_phase="observe", speed_m_s=3,
                   terminal_hold_s=1, routes={"uav_01": [dict(east_m=2, north_m=0, up_m=8)]})]
    return dict(schema_version=2, origin=dict(lat=30, lon=120, alt_msl_m=0),
                vehicles=[vehicle], phases=phases,
                task_spec=dict(execution={"hold_semantics": "integer_seconds_v1"} if required else {}))


def events():
    return [dict(event=kind, agent_id="uav_01", phase=phase, t=stamp)
            for phase, start in (("p00_approach", 0), ("p01_observe", 10))
            for kind, stamp in (("phase_upload_started", start), ("phase_upload_complete", start+1))]


def command(time_s, hold, agent="uav_01", seq=2, total=3):
    return dict(packet=dict(mavpackettype="CMD", TimeUS=int(time_s*1e6), CTot=total,
                            CNum=seq, CId=16, Prm1=hold),
                source_boot_s=time_s, mapped_run_time_s=time_s)


class HoldSemanticsTests(unittest.TestCase):
    def test_H01_integer_hold_in_both_modes_and_legacy_omission(self):
        for mode, field in (("semantic_phase_route_v1", "terminal_hold_s"),
                            ("waypoint_barrier_v1", "waypoint_hold_s")):
            for value in (0, 1, 60, 1.0):
                with self.subTest(mode=mode, value=value):
                    spec = example(mode)
                    spec["execution"].update(hold_semantics="integer_seconds_v1", **{field: value})
                    self.assertEqual(normalize_v3(spec)["execution"][field], float(value))
            for value in (-1, 0.5, 60.5, True, math.nan, math.inf):
                with self.subTest(mode=mode, invalid=value):
                    spec = example(mode)
                    spec["execution"].update(hold_semantics="integer_seconds_v1", **{field: value})
                    with self.assertRaises(ValueError):
                        normalize_v3(spec)
            spec = example(mode)
            spec["execution"][field] = 0.5
            self.assertNotIn("hold_semantics", normalize_v3(spec)["execution"])
            spec["execution"]["hold_semantics"] = "unknown"
            with self.assertRaises(ValueError):
                normalize_v3(spec)

    def test_H02_original_task_normalization_hashes(self):
        expected_path = ROOT / "tests/fixtures/h02_v04_normalization_hashes.json"
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        self.assertEqual(len(expected), 16)
        for relative, digest in expected.items():
            with self.subTest(relative=relative):
                source = json.loads((ROOT / relative).read_text(encoding="utf-8-sig"))
                self.assertEqual(canonical_hash(normalize_v3(source)), digest)

    def test_H03_stage_and_sequence_are_both_required(self):
        scene = simple_scene()
        records = {"uav_01": [command(.5, 0), command(10.5, 1)]}
        result = compare_onboard_mission_params(scene, events(), records)
        self.assertEqual(result["status"], "pass")
        self.assertEqual([(r["phase"], r["mission_seq"], r["onboard_records"][0]["packet"]["Prm1"])
                          for r in result["rows"]], [("p00_approach", 2, 0), ("p01_observe", 2, 1)])
        bad = copy.deepcopy(records)
        bad["uav_01"][1]["packet"]["Prm1"] = 0
        result = compare_onboard_mission_params(scene, events(), bad)
        self.assertEqual(result["status"], "mismatch")
        self.assertEqual(result["counts"]["pass_count"], 1)
        self.assertEqual(result["counts"]["mismatch_count"], 1)

    def test_H03_missing_conflicting_and_wrong_command_fail_closed(self):
        scene = simple_scene()
        complete = {"uav_01": [command(.5, 0), command(10.5, 1)]}
        for records, status in (({"uav_01": [command(.5, 0)]}, "unknown"),
                                ({"uav_01": [command(.5, 0), command(10.5, 1), command(10.6, 0)]}, "mismatch"),
                                ({"uav_01": [command(.5, 0), command(10.5, 1, total=4)]}, "mismatch"),
                                (complete, "pass")):
            with self.subTest(status=status, records=records):
                self.assertEqual(compare_onboard_mission_params(scene, events(), records)["status"], status)
        result = compare_onboard_mission_params(scene, events(), {}, {"uav_01": "BIN unavailable"})
        self.assertEqual(result["status"], "unknown")
        self.assertFalse(result["pass_gate"])
        old = compare_onboard_mission_params(simple_scene(required=False), events(), {}, {"uav_01": "BIN unavailable"})
        self.assertEqual(old["status"], "unknown")
        self.assertIsNone(old["pass_gate"])

    def test_H03_aircraft_key_and_overlapping_upload_windows(self):
        scene = dict(schema_version=1, origin=dict(lat=30, lon=120, alt_msl_m=0),
                     vehicles=[dict(id="uav_01", sysid=1, east_m=0, north_m=0),
                               dict(id="uav_02", sysid=2, east_m=10, north_m=0)],
                     phases=[dict(name="leg_000", targets={
                         "uav_01": dict(east_m=1, north_m=0, up_m=8, speed_m_s=3, hold_s=0),
                         "uav_02": dict(east_m=11, north_m=0, up_m=8, speed_m_s=3, hold_s=1)})],
                     task_spec=dict(execution={"hold_semantics": "integer_seconds_v1"}))
        uploads = [dict(event=kind, agent_id=agent, phase="leg_000", t=stamp)
                   for agent in ("uav_01", "uav_02")
                   for kind, stamp in (("phase_upload_started", 0), ("phase_upload_complete", 1))]
        packets = {"uav_01": [command(.5, 0)], "uav_02": [command(.5, 1, "uav_02")]}
        self.assertEqual(compare_onboard_mission_params(scene, uploads, packets)["status"], "pass")
        packets["uav_02"][0]["packet"]["Prm1"] = 0
        result = compare_onboard_mission_params(scene, uploads, packets)
        self.assertEqual(result["counts"]["pass_count"], 1)
        self.assertEqual(result["counts"]["mismatch_count"], 1)

        overlapping = simple_scene()
        overlapping_events = events()
        for event in overlapping_events:
            if event["phase"] == "p01_observe":
                event["t"] -= 8.9
        ambiguous = compare_onboard_mission_params(overlapping, overlapping_events,
            {"uav_01": [command(1.05, 0)]})
        self.assertEqual(ambiguous["status"], "unknown")
        self.assertIn("overlapping phase", ambiguous["rows"][0]["reason"])

    def test_H03_integer_semantics_fail_closed_without_degrading_old_semantics(self):
        quality = dict(run_completed=True, data_quality_pass=True, truth_available_pass=True,
                       timing_diagnostic_pass=True, execution_constraints_pass=True,
                       separation_status="clear_observed", truth_separation={"status": "clear_observed"},
                       clock_quality={"overall": "strict"}, onboard_mission_param_check_required=True,
                       onboard_mission_param_check_pass=None)
        labels = dict(mission_success=True, mission_success_observation=True, semantic_consistency="agree")
        result = v3_eligibility(quality, labels)
        self.assertFalse(result["benchmark_eligible"])
        self.assertFalse(result["episode_quality_eligible"])
        quality["onboard_mission_param_check_pass"] = True
        self.assertTrue(v3_eligibility(quality, labels)["episode_quality_eligible"])
        quality["onboard_mission_param_check_required"] = False
        quality["onboard_mission_param_check_pass"] = None
        self.assertTrue(v3_eligibility(quality, labels)["episode_quality_eligible"])

    def test_H03_hashed_artifact_and_gate_claims_are_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            run, analysis = make_run(Path(temp) / "run", mode="semantic_phase_route_v1")
            task = json.loads((analysis / "task.json").read_text(encoding="utf-8"))
            task["execution"]["terminal_hold_s"] = 0.0
            task["execution"]["hold_semantics"] = "integer_seconds_v1"
            write_json(analysis / "task.json", task)
            # The new hold field opts the task into the v0.5 semantic contract.
            # Keep every other synthetic fixture claim in that same contract;
            # the test below then isolates the onboard-parameter hash gate.
            protocol = semantic_protocol({"task_spec": task})
            route_versions = dict(route_progress_version=V05_ROUTE_PROGRESS_VERSION,
                                  ac4_timing_version=V05_AC4_TIMING_VERSION,
                                  execution_artifacts_version=V05_EXECUTION_ARTIFACTS_VERSION)
            labels = json.loads((analysis / "labels.json").read_text(encoding="utf-8"))
            labels["label_provenance"].update(route_versions,
                semantic_validation_version=protocol["semantic_validation_version"])
            write_json(analysis / "labels.json", labels)
            validation = json.loads((analysis / "semantic_validation.json").read_text(encoding="utf-8"))
            validation["semantic_validation_version"] = protocol["semantic_validation_version"]
            write_json(analysis / "semantic_validation.json", validation)
            constraints = json.loads((analysis / "execution_constraints.json").read_text(encoding="utf-8"))
            constraints["constraint_validation_version"] = protocol["execution_constraints_version"]
            write_json(analysis / "execution_constraints.json", constraints)
            write_json(analysis / "execution_metrics.json", dict(version=V05_EXECUTION_ARTIFACTS_VERSION,
                                                                **processing_versions()))
            channels = {name: dict(version=V05_AC4_TIMING_VERSION,
                                   mapping_version=V05_ROUTE_PROGRESS_VERSION)
                        for name in ("truth", "observation")}
            write_json(analysis / "ac4_timing_v3.json", dict(**route_versions,
                                                              **processing_versions(), channels=channels))
            artifact = dict(version=VERSION, required=True, status="pass", pass_gate=True)
            write_json(analysis / "onboard_mission_param_check.json", artifact)
            claims = dict(onboard_mission_param_check_version=VERSION,
                          onboard_mission_param_check_required=True,
                          onboard_mission_param_check_status="pass",
                          onboard_mission_param_check_pass=True)
            for name in ("manifest.json", "quality.json"):
                data = json.loads((analysis / name).read_text(encoding="utf-8"))
                data.update(claims, **protocol, **route_versions)
                write_json(analysis / name, data)
            rehash(run)
            load_episode(analysis)
            artifact["pass_gate"] = False
            write_json(analysis / "onboard_mission_param_check.json", artifact)
            rehash(run)
            with self.assertRaisesRegex(ValueError, "onboard mission parameter evidence"):
                load_episode(analysis)


if __name__ == "__main__":
    unittest.main()
