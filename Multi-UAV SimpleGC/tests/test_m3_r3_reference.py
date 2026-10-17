"""Independent D0b geometry oracle, version contracts and real dwell execution."""
import copy,json,math,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
from swarm_sim.fast_dynamics.contracts import M2Config,ReferenceConfig
from swarm_sim.fast_dynamics.route_tracker import RouteTracker,_bezier
from swarm_sim.fast_dynamics.reference_r3 import candidate_config,cut_distance,CONFIG_SHA256
from task_v07.execution import frozen_config,execute,FROZEN_SHA256
from task_v07.dwell import DwellRouteTracker
from scripts.m3_r3_support import d0b_oracle

class R3ReferenceTests(unittest.TestCase):
    def tracker(self,points,version='r3'):
        cfg=candidate_config() if version=='r3' else frozen_config()
        return RouteTracker(points,6.,cfg.vehicle_profile,cfg.controller,cfg.reference,cfg.engine.step_us)
    def route(self,angle):
        a=math.radians(angle)
        return np.array([[-100.,0.,30.],[0.,0.,30.],[100*math.cos(a),100*math.sin(a),30.]])
    def test_default_r2_and_explicit_r2_identical(self):
        self.assertEqual(ReferenceConfig().policy,'continuous_route_v2')
        cfg=frozen_config();points=self.route(45)
        a=RouteTracker(points,6.,cfg.vehicle_profile,cfg.controller)
        b=self.tracker(points,'r2')
        oracle=d0b_oracle()
        self.assertEqual(oracle.d0.tracker_geometry(a),oracle.d0.tracker_geometry(b))
        self.assertEqual([(p.cap,p.exit_cap) for p in a.primitives],[(p.cap,p.exit_cap) for p in b.primitives])
    def test_candidate_config_only_changes_policy(self):
        a=frozen_config().to_dict();b=candidate_config().to_dict()
        self.assertEqual(b['reference']['policy'],'continuous_route_v3')
        b['reference']['policy']=a['reference']['policy'];self.assertEqual(a,b)
        self.assertNotEqual(CONFIG_SHA256,FROZEN_SHA256)
        self.assertEqual(M2Config.from_dict(candidate_config().to_dict()),candidate_config())
    def test_unknown_versions_rejected(self):
        with self.assertRaises(ValueError):ReferenceConfig(policy='continuous_route_v4')
        with self.assertRaises(ValueError):execute({}, {},reference_version='unknown')
    def test_seven_angles_match_original_b2_primitive_values(self):
        oracle=d0b_oracle()
        for angle in (.55,2.6,11.25,45.,90.,174.9,175.,179.9):
            with self.subTest(angle=angle):
                actual=self.tracker(self.route(angle));expected=self.tracker(self.route(angle),'r2')
                expected.primitives=[];oracle._build_core(expected,True)
                self.assertEqual(oracle.d0.tracker_geometry(actual),oracle.d0.tracker_geometry(expected))
                self.assertEqual([(p.cap,p.exit_cap) for p in actual.primitives],[(p.cap,p.exit_cap) for p in expected.primitives])
                oracle.validate_geometry(actual,self.tracker(self.route(angle),'r2'))
                self.assertEqual(actual.diagnostics['reference_version'],'continuous_route_v3')
    def test_curve_vertex_distance_formula_independently_sampled(self):
        for angle in (.55,2.6,11.25,45.,90.,174.9):
            t=self.tracker(self.route(angle));curve=next(p for p in t.primitives if p.control is not None)
            numeric=np.linalg.norm(_bezier(curve.control,np.linspace(0,1,2001)),axis=1).min()
            d=cut_distance(t.gates[1],math.radians(angle),100.,100.)
            self.assertAlmostEqual(numeric,(23./48.)*d*math.sin(math.radians(angle)/2),places=9)
            self.assertLessEqual(numeric,.5*t.gates[1]+1e-9)
    def test_adjacent_curves_and_tiny_legs_preserve_order(self):
        oracle=d0b_oracle()
        for points in ([[0,0,30],[100,0,30],[200,.5,30],[300,1.1,30],[400,2,30]],
                       [[0,0,30],[10,0,30],[10,.01,30],[10,.02,30],[10,10,30],[10,.02,30]]):
            a=self.tracker(points);b=self.tracker(points,'r2')
            oracle.validate_geometry(a,b)
            self.assertEqual(oracle.structure(a),oracle.structure(b))
    def test_dwell_selects_r3_for_both_route_halves(self):
        points=np.array([[0,0,30],[30,0,30],[30,30,30]],float)
        t=DwellRouteTracker(points,5.,candidate_config(),dict(waypoint_index=1,duration_s=2.))
        self.assertEqual(t.tracker.reference.policy,'continuous_route_v3')
        t.tracker.complete=True
        sample=lambda us:SimpleNamespace(t_us=us,p=points[1:2],v=np.zeros((1,3)))
        t.observe_sample(sample(0),0);t.observe_sample(sample(1900000),0)
        self.assertEqual(t.stage,'hold');t.observe_sample(sample(2000000),0)
        self.assertEqual(t.stage,'departure');self.assertEqual(t.tracker.reference.policy,'continuous_route_v3')
        np.testing.assert_array_equal(t.tracker.points,points[1:])
    def test_real_r3_plant_retains_observation_dwell(self):
        points=[[0.,0.,50.],[60.,0.,50.],[120.,0.,50.]]
        sk=dict(agent_ids=['a'],initial_states=[dict(agent_id='a',position_enu_m=points[0],velocity_enu_m_s=[0.,0.,0.],acceleration_enu_m_s2=[0.,0.,0.])],
            references={'a':dict(points_enu_m=points,intermediate_dwell=dict(waypoint_index=1,duration_s=25.))},
            cruise_speed_m_s=5.,initial_settle_s=20.,terminal_hold_s=2.,terminal_radius_m=1.,terminal_speed_m_s=.15)
        run=execute(sk,{'a':0.},reference_version='r3')
        self.assertEqual(run['execution_status'],'completed');self.assertEqual(run['config_sha256'],CONFIG_SHA256)
        stationary=(np.linalg.norm(run['p'][:,0]-points[1],axis=1)<=1.)&(np.linalg.norm(run['v'][:,0],axis=1)<=.15)
        times=run['time_us'][stationary]/1e6
        self.assertGreaterEqual(times[-1]-times[0],25.)
    def test_r3_artifact_identity_roundtrip_and_mixed_version_rejected(self):
        from swarm_sim.fast_dynamics.mission_executor import run_mission
        from swarm_sim.fast_dynamics.artifacts import write_episode,validate_episode
        from swarm_sim.fast_dynamics.adapter import reuse_semantics
        from swarm_sim.generation import file_hash
        fixture=Path(__file__).parent/'fixtures/fast_dynamics/rapid_passage_0000_v00.json'
        task=json.loads(fixture.read_text());cfg=candidate_config()
        with tempfile.TemporaryDirectory() as temp,reuse_semantics():
            r=run_mission(task,cfg)
            manifest=write_episode(r.scene,r,Path(temp)/'run',run_id=task['task_id'],input_hashes={str(fixture):file_hash(fixture)},config=cfg,seed=task['seed'])
            self.assertEqual(manifest['reference_version'],'continuous_route_v3')
            self.assertEqual(r.diagnostics['reference_version'],'continuous_route_v3')
            validate_episode(manifest,Path(temp)/'run/analysis')
            bad=copy.deepcopy(manifest);bad['reference_version']='continuous_route_v2'
            with self.assertRaises(ValueError):validate_episode(bad,Path(temp)/'run/analysis')
