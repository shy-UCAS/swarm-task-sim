import unittest

from swarm_sim.route_timing import nominal_arrival_evidence


class RouteTimingTests(unittest.TestCase):
    def fixture(self):
        scene=dict(phases=[dict(name="p")],planning=dict(nominal_phase_timing={"p":dict(
            duration_s=12,tau_s=3,per_agent_waypoint_arrival_s={"a":[5,10],"no_op":[]})}))
        events=[dict(event="phase_release_scheduled",phase="p",t=3.7,release_t=4),
                dict(event="waypoint_reached",phase="p",agent_id="a",seq=2,t=10),
                dict(event="waypoint_reached",phase="p",agent_id="a",seq=3,t=16)]
        return scene,events

    def test_phase_relative_pairing_and_missing_evidence(self):
        scene,events=self.fixture()
        result=nominal_arrival_evidence(scene,events,dict(run_epoch_monotonic_s=100,elapsed_s=20),102)
        self.assertEqual([r["deviation_s"] for r in result["records"]],[1,2])
        self.assertEqual(result["per_phase"]["p"]["max_abs_s"],2)
        self.assertTrue(result["within_tau"])
        self.assertEqual(result["expected_waypoints"],2)
        missing=nominal_arrival_evidence(scene,events[:-1],dict(run_epoch_monotonic_s=100,elapsed_s=20),102)
        self.assertIsNone(missing["within_tau"])
        self.assertFalse(missing["complete"])

    def test_strict_tau_boundary_is_not_silently_accepted(self):
        scene,events=self.fixture(); events[-1]["t"]=17
        result=nominal_arrival_evidence(scene,events,dict(run_epoch_monotonic_s=100,elapsed_s=20),102)
        self.assertFalse(result["within_tau"])
        self.assertEqual(result["per_phase"]["p"]["max_abs_s"],3)

    def test_waypoint_after_phase_mission_or_run_end_cannot_complete_timing(self):
        for boundary in ("next_phase", "mission_end", "run_end", "no_end"):
            with self.subTest(boundary=boundary):
                scene,events=self.fixture()
                metadata=dict(run_epoch_monotonic_s=100)
                if boundary=="next_phase":
                    scene["phases"].append(dict(name="next"))
                    events.append(dict(event="phase_release_scheduled",phase="next",t=10.8,release_t=11))
                    metadata["elapsed_s"]=20
                elif boundary=="mission_end":
                    metadata.update(mission_end_monotonic_s=111,elapsed_s=20)
                elif boundary=="run_end":
                    metadata["elapsed_s"]=11
                result=nominal_arrival_evidence(scene,events,metadata,102)
                self.assertFalse(result["complete"])
                self.assertIsNone(result["within_tau"])
                self.assertEqual(result["paired_waypoints"],0 if boundary=="no_end" else 1)


if __name__=="__main__": unittest.main()
