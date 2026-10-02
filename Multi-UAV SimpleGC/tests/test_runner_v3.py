"""E05/E06/E08/R06: mock transport and process ownership, never launch SITL."""

import json
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from swarm_sim.quality import resolve_policy
from swarm_sim.runner import run_scene
from swarm_sim.runner_v3 import execute_phases, phase_time_budget
from swarm_sim.run_provenance import PARAMETER_COMPARISON_VERSION, STAT_RESET_EPOCH, digest, verify_preflight_files
from swarm_sim.tasks import compile_task
from swarm_sim.vehicle import Vehicle


ROOT = Path(__file__).resolve().parents[1]


def task(mode="route"):
    return json.loads((ROOT / f"missions/v3/recon_shared_3uav_{mode}.json").read_text(encoding="utf-8"))


class RunnerV3Tests(unittest.TestCase):
    def phase_run(self, scene, confirm_error=None, events=None):
        calls, barriers = [], []
        events = [] if events is None else events
        clients = []
        for vehicle in scene["vehicles"]:
            agent = vehicle["id"]
            client = SimpleNamespace(id=agent, cancel=threading.Event(), check=lambda: None)
            client.upload = lambda plan, aid=agent, **kw: calls.append(("upload", aid, len(plan)))
            client.execute = lambda release, count, timeout, phase, aid=agent: calls.append(("execute", aid, count, phase))
            def confirm(*args, aid=agent, **kw):
                calls.append(("confirm", aid, args[3], args[4]))
                if confirm_error:
                    raise confirm_error
            client.confirm_target = confirm
            clients.append(client)
        def parallel(function, **kwargs):
            barriers.append(kwargs["context"])
            for client, vehicle in zip(clients, scene["vehicles"]): function(client, vehicle)
        def event(kind, agent=None, **fields): events.append(dict(event=kind, agent=agent, **fields))
        metadata = dict(quality_policy=resolve_policy())
        execute_phases(scene, clients, parallel, event, metadata, time.perf_counter(), time.perf_counter() + 1000, lambda: None)
        return calls, events, barriers, metadata

    def test_E05_schema1_barrier_and_schema2_route_use_distinct_mission_shapes(self):
        for mode, expected_phases in (("barrier", 12), ("route", 3)):
            scene = compile_task(task(mode))
            calls, events, barriers, metadata = self.phase_run(scene)
            self.assertEqual(len(scene["phases"]), expected_phases)
            self.assertEqual(len(barriers), 3 * expected_phases)
            self.assertEqual([entry[0] for entry in calls[:9]], ["upload"] * 3 + ["execute"] * 3 + ["confirm"] * 3)
            counts = [call[2] for call in calls if call[0] == "upload"]
            self.assertEqual(max(counts), 3 if mode == "barrier" else 11)
            self.assertEqual(len([e for e in events if e["event"] == "phase_release_scheduled"]), expected_phases)
            self.assertEqual(len([c for c in calls if c[0] == "execute"]), expected_phases * 3)
            self.assertTrue(all(row["status"] == "completed" for row in metadata["phase_timing"].values()))

    def test_E05_noop_skips_upload_auto_and_confirms_current_endpoint(self):
        spec = task()
        spec.pop("family_id")
        for index, vehicle in enumerate(spec["scenario"]["vehicles"]):
            vehicle.update(east_m=1.8 + 18 * index, north_m=0.)
        scene = compile_task(spec)
        calls, events, barriers, _ = self.phase_run(scene)
        self.assertEqual([call[0] for call in calls[:3]], ["confirm"] * 3)
        self.assertEqual([call[2] for call in calls[:3]], [.5] * 3)
        self.assertEqual(len([e for e in events if e["event"] == "phase_no_op_started"]), 3)
        self.assertEqual(len([e for e in events if e["event"] == "phase_no_op_ready"]), 3)
        self.assertTrue(all(not e["service_enabled"] for e in events if e["event"] == "phase_no_op_ready"))
        self.assertEqual(len([call for call in calls if call[0] == "upload"]), 6)

    def test_E05_noop_ready_requires_successful_geometric_confirmation(self):
        spec = task()
        spec.pop("family_id")
        for index, vehicle in enumerate(spec["scenario"]["vehicles"]):
            vehicle.update(east_m=1.8 + 18 * index, north_m=0.)
        events = []
        with self.assertRaisesRegex(TimeoutError, "missing position"):
            self.phase_run(compile_task(spec), TimeoutError("missing position"), events)
        self.assertEqual(len([e for e in events if e["event"] == "phase_no_op_started"]), 3)
        self.assertFalse(any(e["event"] == "phase_no_op_ready" for e in events))

    def test_E08_budget_defaults_and_bound_override_only_shortens(self):
        spec = task()
        scene = compile_task(spec)
        phase = scene["phases"][1]
        nominal = scene["planning"]["nominal_phase_timing"][phase["name"]]["duration_s"]
        self.assertEqual(phase_time_budget(scene, phase, 9999)["effective_timeout_s"], 3 * nominal + 30)
        self.assertEqual(phase_time_budget(scene, phase, 2)["effective_timeout_s"], 2)
        spec["execution"]["phase_timeout_override_s"] = .03
        shortened = compile_task(spec)
        self.assertEqual(phase_time_budget(shortened, shortened["phases"][1], 2)["effective_timeout_s"], .03)
        spec["execution"]["phase_timeout_override_s"] = 3600
        extended = compile_task(spec)
        self.assertEqual(phase_time_budget(extended, extended["phases"][1], 2)["effective_timeout_s"], 2)

    def test_E06_R06_single_receive_owner_records_all_seq_without_extra_mode_commands(self):
        for shared in (False, True):
            with self.subTest(shared=shared), tempfile.TemporaryDirectory() as tmp:
                events, modes = [], []
                vehicle = Vehicle(dict(id="uav_01", sysid=1), Path(tmp) / "raw.jsonl", threading.Event(),
                    lambda kind, agent=None, **fields: events.append(dict(event=kind, **fields)), record_lifecycle=shared)
                vehicle.execution_waypoint_indices = [10, 11, 12]
                messages = []
                for seq in (1, 2, 2, 3, 4):
                    messages.append(SimpleNamespace(seq=seq, get_type=lambda: "MISSION_ITEM_REACHED", get_srcSystem=lambda: 1,
                        to_dict=lambda seq=seq: dict(mavpackettype="MISSION_ITEM_REACHED", seq=seq)))
                def receive(**kwargs):
                    message = messages.pop(0)
                    if not messages: vehicle.stop.set()
                    return message
                vehicle.master = SimpleNamespace(recv_match=receive)
                vehicle.send = Mock()
                def mode(name):
                    modes.append(name)
                    if name == "AUTO": vehicle._receive()
                vehicle.mode = mode
                vehicle.execute(0, 5, 1, "observe")
                reached = [e for e in events if e["event"] == "waypoint_reached"]
                self.assertEqual([e["seq"] for e in reached], [1, 2, 2, 3, 4])
                self.assertEqual([e["terminal"] for e in reached], [False] * 4 + [True])
                self.assertEqual([e["planner_index"] for e in reached], [None, 10, 10, 11, 12])
                raw = [json.loads(line) for line in vehicle.raw_path.read_text().splitlines()]
                self.assertEqual([e["recv_monotonic_s"] for e in reached], [p["recv_monotonic_s"] for p in raw])
                self.assertEqual(modes, ["AUTO"] if shared else ["AUTO", "LOITER"])
                self.assertEqual(len(vehicle.inbox), 5)
                self.assertEqual(vehicle.wait_message(["MISSION_ITEM_REACHED"], lambda m: m.seq == 4, timeout=.01).seq, 4)

    def test_R06_legacy_analysis_ignores_new_waypoint_and_unknown_events(self):
        import test_v03_integration as fixtures
        from swarm_sim.analysis import analyze_run
        helper = fixtures.FinalEligibilityTests()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, expected_quality, expected_labels = helper.analyze_handmade_evidence(root / "before", "control")
            def analyze_with_extra_events(path):
                events_path = path / "events.jsonl"
                with events_path.open("a", encoding="utf-8") as stream:
                    for event in (dict(event="waypoint_reached", agent_id="uav_01", phase="leg_001", seq=2,
                                       terminal=True, t=5.5, recv_monotonic_s=105.5),
                                  dict(event="future_diagnostic_only", agent_id="uav_01", t=5.6)):
                        stream.write("\n" + json.dumps(event))
                return analyze_run(path)
            with patch("test_v03_integration.analyze_run", side_effect=analyze_with_extra_events):
                _, actual_quality, actual_labels = helper.analyze_handmade_evidence(root / "after", "control")
            self.assertEqual(actual_quality, expected_quality)
            self.assertEqual(actual_labels, expected_labels)

    def test_E08_phase_timeout_retains_failure_evidence_and_cleans_owned_processes(self):
        spec = task()
        spec["execution"]["phase_timeout_override_s"] = .03
        scene = compile_task(spec)
        process = Mock()
        process.instances = [dict(id=v["id"], sysid=v["sysid"]) for v in scene["vehicles"]]
        process.processes = [Mock(poll=Mock(return_value=0)) for _ in scene["vehicles"]]
        process.start.return_value = process.instances
        binary, params = ROOT / "ArducopterSITL/arducopter.exe", ROOT / "ArducopterSITL/copter.parm"
        provenance = verify_preflight_files(binary, params)
        process.metadata.return_value = dict(sha256=provenance["actual"]["firmware"]["sha256"], instances=process.instances)
        clients = []
        def vehicle(instance, raw_path, cancel, event, **kw):
            raw_path.write_text("", encoding="utf-8")
            client = Mock(id=instance["id"], sysid=instance["sysid"], cancel=cancel)
            def execute(*args):
                event("waypoint_reached", instance["id"], recv_monotonic_s=time.perf_counter(),
                      phase="p00_approach", seq=2, terminal=True)
                cancel.wait(1)
                if cancel.is_set(): raise RuntimeError("run cancelled")
            client.execute.side_effect = execute
            clients.append(client)
            return client
        def read(client, firmware, evidence):
            reference = provenance["baseline"]["baselines"][0]["agents"]["uav_01"]["all_parameters"]
            evidence.update(complete=True, status="complete", all_parameters=dict(reference, SYSID_THISMAV=float(client.sysid),
                            STAT_RESET=(datetime.now(timezone.utc) - STAT_RESET_EPOCH).total_seconds()),
                            parameter_count=len(reference), received_count=len(reference), missing_indices=[])
            return evidence
        with tempfile.TemporaryDirectory() as tmp, patch("swarm_sim.runner_v3.SITLProcesses", return_value=process), \
                patch("swarm_sim.runner_v3.Vehicle", side_effect=vehicle), patch("swarm_sim.runner_v3.Recorder") as recorder, \
                patch("swarm_sim.runner_v3.read_firmware_parameters", side_effect=read), patch("builtins.print"):
            recorder.return_value.error = None
            directory, metadata, quality = run_scene(scene, tmp, binary, params)
            self.assertEqual(metadata["status"], "failed")
            self.assertIn("phase p00_approach execute timeout", metadata["error"])
            self.assertFalse(quality["episode_quality_eligible"])
            self.assertNotIn("analysis_error", quality)
            self.assertTrue((directory / "events.jsonl").exists())
            self.assertTrue((directory / "firmware_parameters.json").exists())
            self.assertTrue((directory / "analysis_latest.json").exists())
            self.assertEqual(metadata["run_provenance"]["parameter_evidence"]["sha256"], digest(directory / "firmware_parameters.json"))
            self.assertEqual(len(metadata["phase_timing"]), 1)
            self.assertEqual(metadata["phase_timing"]["p00_approach"]["status"], "failed")
            self.assertEqual(metadata["run_provenance"]["status"], "verified_before_takeoff")
            self.assertEqual(metadata["parameter_comparison_version"], PARAMETER_COMPARISON_VERSION)
            self.assertEqual(metadata["run_provenance"]["parameter_comparison_version"], PARAMETER_COMPARISON_VERSION)
            evidence = json.loads((directory / "firmware_parameters.json").read_text(encoding="utf-8"))
            self.assertTrue(all(row["parameter_comparison_version"] == PARAMETER_COMPARISON_VERSION
                                and row["parameter_comparison"]["stat_reset"]["pass"] for row in evidence.values()))
            events = [json.loads(line) for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines()]
            reached = [event for event in events if event["event"] == "waypoint_reached"]
            self.assertEqual(len(reached), 3)
            self.assertTrue(all(e["t"] == e["recv_monotonic_s"] - metadata["run_epoch_monotonic_s"] for e in reached))
            process.close.assert_called_once()
            for client in clients:
                client.prepare_airborne.assert_called_once()
                client.execute.assert_called_once()
                client.land.assert_not_called()
                client.close.assert_called_once()

    def test_preflight_parameter_failure_on_one_agent_blocks_takeoff_for_every_agent(self):
        self.check_preflight_failure(partial=False)

    def test_cancelled_partial_readback_keeps_v2_checks_and_never_arms(self):
        self.check_preflight_failure(partial=True)

    def check_preflight_failure(self, partial):
        scene = compile_task(task("barrier"))
        binary, params = ROOT / "ArducopterSITL/arducopter.exe", ROOT / "ArducopterSITL/copter.parm"
        provenance = verify_preflight_files(binary, params)
        process = Mock()
        process.instances = [dict(id=v["id"], sysid=v["sysid"]) for v in scene["vehicles"]]
        process.processes = [Mock(poll=Mock(return_value=0)) for _ in scene["vehicles"]]
        process.start.return_value = process.instances
        process.metadata.return_value = dict(sha256=provenance["actual"]["firmware"]["sha256"], instances=process.instances)
        clients = []
        def make_vehicle(instance, raw_path, cancel, event, **kwargs):
            raw_path.write_text("", encoding="utf-8")
            client = Mock(id=instance["id"], sysid=instance["sysid"])
            clients.append(client)
            return client
        def read(client, firmware, evidence):
            reference = provenance["baseline"]["baselines"][0]["agents"]["uav_01"]["all_parameters"]
            evidence.update(complete=True, status="complete", all_parameters=dict(reference, SYSID_THISMAV=float(client.sysid),
                            STAT_RESET=(datetime.now(timezone.utc) - STAT_RESET_EPOCH).total_seconds()),
                            parameter_count=len(reference), received_count=len(reference), missing_indices=[])
            if client.id == "uav_02":
                if partial:
                    evidence.update(complete=False, status="failed", received_count=len(reference) - 1,
                                    missing_indices=[0], error="RuntimeError: run cancelled")
                    evidence["all_parameters"].pop("WPNAV_SPEED")
                    raise RuntimeError("run cancelled")
                evidence["all_parameters"]["WPNAV_SPEED"] += 1
            return evidence
        with tempfile.TemporaryDirectory() as tmp, patch("swarm_sim.runner_v3.SITLProcesses", return_value=process), \
                patch("swarm_sim.runner_v3.Vehicle", side_effect=make_vehicle), patch("swarm_sim.runner_v3.Recorder") as recorder, \
                patch("swarm_sim.runner_v3.read_firmware_parameters", side_effect=read), patch("builtins.print"):
            recorder.return_value.error = None
            directory, metadata, quality = run_scene(scene, tmp, binary, params)
            self.assertEqual(metadata["status"], "failed")
            self.assertEqual(metadata["run_provenance"]["status"], "failed")
            self.assertIn("run cancelled" if partial else "WPNAV_SPEED", metadata["error"])
            self.assertEqual(metadata["parameter_comparison_version"], PARAMETER_COMPARISON_VERSION)
            self.assertEqual(metadata["run_provenance"]["parameter_comparison_version"], PARAMETER_COMPARISON_VERSION)
            evidence = json.loads((directory / "firmware_parameters.json").read_text(encoding="utf-8"))
            self.assertFalse(evidence["uav_02"]["parameter_comparison"]["pass"])
            self.assertEqual(evidence["uav_02"]["parameter_comparison_version"], PARAMETER_COMPARISON_VERSION)
            self.assertTrue(evidence["uav_02"]["parameter_comparison"]["stat_reset"]["pass"])
            self.assertEqual(evidence["uav_02"]["parameter_comparison"]["collection_complete"], not partial)
            self.assertNotIn("flight_epoch_monotonic_s", metadata)
            for client in clients:
                client.prepare_airborne.assert_not_called()
                client.close.assert_called_once()
            process.close.assert_called_once()
