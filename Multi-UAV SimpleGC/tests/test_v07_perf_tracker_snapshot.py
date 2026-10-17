"""Real plant steps and strict old/new transaction equivalence (FE-P0 G3)."""
from copy import deepcopy
import json
import unittest

import numpy as np
from swarm_sim.fast_dynamics.contracts import PlantState
from swarm_sim.fast_dynamics.engine import SynchronousEngine
from swarm_sim.fast_dynamics.route_tracker import RouteTracker
from task_v07.dwell import DwellRouteTracker
from task_v07 import execution
from test_v07_m2_timing_rehearsal import short_vertical


def bindings(obj):
    return {"keys": set(vars(obj)), "ids": {k: id(v) for k, v in vars(obj).items()},
            "lists": {k: deepcopy(getattr(obj, k)) for k in ("witnesses", "events") if hasattr(obj, k)}}


class SnapshotTests(unittest.TestCase):
    def assert_restored(self, obj, before):
        self.assertEqual(set(vars(obj)), before["keys"])
        self.assertEqual({k: id(v) for k, v in vars(obj).items()}, before["ids"])
        for key, values in before["lists"].items():
            self.assertEqual(getattr(obj, key), values)
        if isinstance(obj, RouteTracker):
            for witness in obj.witnesses:
                self.assertTrue(any(witness is event for event in obj.events))

    def exercise(self, dwell=False):
        cfg = execution.frozen_config()
        points = np.array([[0., 0., 120.], [20., 0., 120.], [20., 20., 120.], [0., 20., 120.]])
        engine = SynchronousEngine(cfg, PlantState(points[:1].copy(), np.zeros((1, 3)), np.zeros((1, 3))))
        tracker = (DwellRouteTracker(points, 4., cfg, {"waypoint_index": 2, "duration_s": 2.}) if dwell else
                   RouteTracker(points, 4., cfg.vehicle_profile, cfg.controller, cfg.reference, cfg.engine.step_us))
        # Warm up with actual steps so the checkpoint includes an existing witness.
        found = False
        for _ in range(4000):
            desired = tracker.command(engine.state.p[0], engine.state.v[0], engine.state.a[0])
            inner = tracker.tracker if dwell else tracker
            before, inside = bindings(tracker), bindings(inner)
            stage = (tracker.stage, tracker.since_us) if dwell else None
            snapshot = execution._snapshot_tracker(tracker)
            engine.step(desired[None, :])
            tracker.observe_segment(engine.last_segment)
            if inside["lists"]["witnesses"] and len(inner.events) > len(inside["lists"]["events"]):
                execution._restore_tracker(snapshot)
                self.assert_restored(tracker, before)
                self.assert_restored(inner, inside)
                if dwell:
                    self.assertIs(tracker.tracker, inner)
                    self.assertEqual((tracker.stage, tracker.since_us), stage)
                found = True
                break
        self.assertTrue(found, "No actual event-producing step was restored")

    def test_route_snapshot_real_step(self):
        self.exercise()

    def test_dwell_snapshot_real_step(self):
        self.exercise(True)

    def test_unknown_tracker_rejected(self):
        with self.assertRaises(TypeError):
            execution._snapshot_tracker(object())

    def test_execute_old_new_exact(self):
        multi = short_vertical()
        ordinary = deepcopy(multi)
        agent = ordinary["members"][0]
        state = next(s for s in ordinary["initial_states"] if s["agent_id"] == agent)
        origin = np.array(state["position_enu_m"])
        points = [(origin + offset).tolist() for offset in ([0, 0, 0], [-100, 0, 0], [-100, -100, 0], [0, -100, 0])]
        ordinary.update(members=[agent], agent_ids=[agent], initial_states=[state])
        ordinary["references"] = {agent: {"points_enu_m": points, "endpoint_enu_m": points[-1]}}
        dwell = deepcopy(ordinary)
        dwell["references"][agent]["intermediate_dwell"] = {"waypoint_index": 1, "duration_s": 25.}
        receipts = []
        try:
            for name, sk in (("ordinary_multicorner", ordinary), ("intermediate_dwell", dwell), ("multi_agent", multi)):
                runs, stats = [], []
                for legacy in (True, False):
                    execution._LEGACY_DEEPCOPY_TRANSACTIONS = legacy
                    execution._TRANSACTION_STATS.update(steps=0, rollbacks=0)
                    runs.append(execution.execute(sk, dict.fromkeys(sk["agent_ids"], 0.)))
                    stats.append(dict(execution._TRANSACTION_STATS))
                for key in ("time_us", "p", "v", "a"):
                    self.assertTrue(np.array_equal(runs[0][key], runs[1][key]), (name, key))
                for key in ("end_us", "execution_status", "release_s", "time_budget", "agent_ids"):
                    self.assertEqual(runs[0][key], runs[1][key], (name, key))
                self.assertEqual(stats[0], stats[1])
                receipts.append({"fixture": name, "legacy": stats[0], "snapshot": stats[1], "equal": True})
        finally:
            execution._LEGACY_DEEPCOPY_TRANSACTIONS = False
        print("S2_RECEIPTS " + json.dumps(receipts), flush=True)
        self.assertGreater(sum(r["snapshot"]["rollbacks"] for r in receipts), 0)


if __name__ == "__main__":
    unittest.main()
