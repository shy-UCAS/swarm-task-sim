"""Post-freeze access guards and synthetic diagnostic geometry, no holdout runs."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from swarm_sim.fast_dynamics.calibration import evaluation_tasks,reference_summary,SPLIT_ID,SPLIT_SEED,sha256
from swarm_sim.fast_dynamics.contracts import M2Config,PlantState
from swarm_sim.fast_dynamics.engine import StepSegment
from scripts.tune_fast_dynamics_m3 import SPLIT_SHA
from scripts.verify_fast_dynamics_m3_internal import fallback_decision
from scripts.verify_fast_dynamics_highspeed import scenarios,segment_minimum_separation,segment_max_speed,maneuver_diagnostics

def split():
    return dict(split_id=SPLIT_ID,seed=SPLIT_SEED,
       groups=dict(tuning=["t"],internal_holdout=["h"],development_reference=["d"]),
       tasks=[dict(family_id=f,mission_id=f+"0",group=g) for f,g in (("t","tuning"),("h","internal_holdout"),("d","development_reference"))])

class PostFreezeTests(unittest.TestCase):
    def test_internal_requires_freeze_before_any_reference_file_open(self):
        with self.assertRaises(ValueError):evaluation_tasks(split(),group="internal_holdout")
        row=dict(task=dict(family_id="h",mission_id="h0"),status="ELIGIBLE",attempt={})
        with patch("swarm_sim.fast_dynamics.calibration.read_json",side_effect=AssertionError("reference opened")):
            with self.assertRaises(ValueError):reference_summary(row,split(),"never_open")
        with self.assertRaises(ValueError):evaluation_tasks(dict(split(),split_id="M2-02B"),group="internal_holdout")

    def test_freeze_allows_only_internal_and_rejects_modified_parameters(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);config=root/"config.json";record=root/"freeze.json"
            config.write_text(json.dumps(M2Config().to_dict()),encoding="utf-8")
            record.write_text(json.dumps(dict(status="FROZEN",eligible_tasks=282,split_sha256=SPLIT_SHA,
                tiers=dict(hard=dict(passed=True)),config_path=str(config),config_sha256=sha256(config))),encoding="utf-8")
            rows=evaluation_tasks(split(),group="internal_holdout",freeze_record=record)
            self.assertEqual([r["family_id"] for r in rows],["h"])
            config.write_text("{}",encoding="utf-8")
            with self.assertRaises(ValueError):evaluation_tasks(split(),group="internal_holdout",freeze_record=record)

    def test_fallback_is_only_frozen_fail_default_pass(self):
        self.assertTrue(fallback_decision(False,True))
        for frozen,default in ((True,True),(True,False),(False,False)):
            self.assertFalse(fallback_decision(frozen,default))

    def test_registered_convergence_has_equal_distances_and_separated_goals(self):
        cases=[c for c in scenarios() if c["kind"]=="convergence"]
        self.assertEqual({c["speed"] for c in cases},{4.,7.,10.})
        for case in cases:
            routes=np.array(case["routes"])
            np.testing.assert_allclose(np.linalg.norm(routes[:,1]-routes[:,0],axis=1),100.,atol=1e-12)
            for i in range(4):
                for j in range(i):self.assertGreaterEqual(np.linalg.norm(routes[i,1]-routes[j,1]),6.)

    def test_continuous_minimum_detects_crossing_between_endpoints(self):
        state=PlantState([[-1.,0,8],[1.,0,8]],[[2.,0,0],[-2.,0,0]],np.zeros((2,3)))
        self.assertAlmostEqual(segment_minimum_separation(StepSegment(0,1_000_000,state,np.zeros((2,3)))),0.,places=12)

    def test_velocity_peak_between_step_endpoints_is_measured(self):
        state=PlantState([[0.,0,8]],[[1.,0,0]],[[2.,0,0]])
        # v(t)=1+2t-2t^2: endpoints 1, interior maximum 1.5.
        segment=StepSegment(0,1_000_000,state,np.array([[-4.,0,0]]))
        self.assertAlmostEqual(segment_max_speed(segment),1.5,places=12)

    def test_delayed_turn_stop_is_not_missed_by_witness_time_window(self):
        route=np.array([[0.,0,8],[10.,0,8],[0.,0,8]])
        times=np.arange(9,dtype=float)
        positions=np.array([[x,0,8] for x in (0,8,10,11,12,12,11,5,0)],float)
        velocities=np.array([[v,0,0] for v in (0,2,2,1,.2,0,-1,-2,0)],float)
        witnesses=[dict(node_index=n,t_us=t) for n,t in ((0,0),(1,2_000_000),(2,8_000_000))]
        result=maneuver_diagnostics(route,witnesses,times,positions,velocities)
        # The actual stop is three seconds after the node witness.
        self.assertEqual(result["turn_neighborhoods"][0]["minimum_speed_m_s"],0.)

    def test_terminal_overrun_and_return_are_measured_beyond_route_endpoint(self):
        route=np.array([[0.,0,8],[10.,0,8]])
        positions=np.array([[x,0,8] for x in (8,10,14,12,10)],float)
        velocities=np.array([[v,0,0] for v in (2,2,0,-2,0)],float)
        witnesses=[dict(node_index=0,t_us=0),dict(node_index=1,t_us=1_000_000)]
        result=maneuver_diagnostics(route,witnesses,np.arange(5,dtype=float),positions,velocities)["terminal"]
        self.assertEqual(result["maximum_overshoot_m"],4.)
        self.assertEqual(result["return_distance_m"],4.)
        self.assertEqual(result["velocity_direction_reversals"],1)

if __name__=="__main__":unittest.main()
