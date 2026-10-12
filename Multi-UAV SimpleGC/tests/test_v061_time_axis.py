"""Offline common-source contracts: real analysis and predicates at 1/2/4x."""
import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from swarm_sim.analysis_v3 import analyze_run_v3
from swarm_sim.dataset import build_dataset
from swarm_sim.episode_loader import load_episode
from swarm_sim.language_v0 import describe_dataset
from swarm_sim.mission_evaluation import _return_result
from swarm_sim.patrol_validation import evaluate_channel as patrol
from swarm_sim.rapid_passage import measure_passage
from swarm_sim.recording import resample, write_json
from swarm_sim.registry import component_versions
from swarm_sim.route_windows import build_route_windows
from swarm_sim.tasks import compile_task
from swarm_sim.scenario import enu_to_geo
from swarm_sim.time_contract import CommonTimeAxis, REFERENCE_SELECTION_RULE, is_sim_time, sim_speedup
from swarm_sim.truth import fit_clock
from test_rapid_passage import REGION, trajectory
from test_route_windows import fixture as route_fixture, row
from test_wp_p_validation import _case as patrol_case

ROOT = Path(__file__).resolve().parents[1]


def axis_for(speed, agents=("uav_01", "uav_02"), duration=200.):
    offsets = {agent: 10. + 20.*index for index, agent in enumerate(agents)}
    models = {agent: fit_clock([(offset + index*.1, (index*.1-5.)/speed)
              for index in range(int(duration*10)+1)], speed, source_time_contract=True)
              for agent, offset in offsets.items()}
    return CommonTimeAxis(models, 100.), offsets


def common_traces(axis, offsets, traces):
    return {agent: [(axis.source(agent, offsets[agent]+5.+t), values) for t,values in rows]
            for agent,rows in traces.items()}


class TimeAxisTests(unittest.TestCase):
    def test_reference_selection_is_natural_deterministic_and_fails_closed(self):
        axis, _ = axis_for(2, ("uav_10", "uav_02", "uav_01"))
        models = copy.deepcopy(axis.models)
        models["uav_01"]["available"] = False
        for ordered in (models, dict(reversed(list(models.items())))):
            selected = CommonTimeAxis(ordered, 100.)
            self.assertEqual(selected.reference_agent_id, "uav_02")
            self.assertEqual(selected.metadata["reference_selection_rule"], REFERENCE_SELECTION_RULE)
            self.assertEqual(selected.metadata["rejected_reference_candidates"], ["uav_01"])
        for model in models.values():
            model["available"] = False
        missing = CommonTimeAxis(models, 100.)
        self.assertFalse(missing.available)
        self.assertIsNone(missing.host(0.))
        self.assertFalse(missing.evaluation_model("uav_01")["available"])
        self.assertEqual(missing.grid(None, 10), [])

    def test_no_extrapolation_or_host_fallback_and_exact_piecewise_composition(self):
        models = {"uav_01": dict(available=True, knots=[(10.,-2.),(12.,0.),(14.,1.),(16.,3.)]),
                  "uav_02": dict(available=True, knots=[(30.,-1.),(34.,2.)])}
        axis=CommonTimeAxis(models)
        self.assertIsNone(axis.source("uav_02",29.))
        self.assertIsNone(axis.host(4.))
        aligned=axis.aligned_model("uav_02")
        self.assertIn(14.-12.,[p[1] for p in aligned["knots"]])
        self.assertEqual(axis.source("uav_01",14.),2.)
        self.assertFalse(axis.metadata["extrapolation"])

    def test_speedup_is_explicit_v061_only_and_validated(self):
        self.assertFalse(is_sim_time({"execution":{"sim_speedup":4}}))
        self.assertEqual(sim_speedup({"execution":{"protocol_version":"v0.5","sim_speedup":4}}),1)
        for value in (0,-1,True,float("nan"),float("inf"),"2"):
            with self.assertRaises(ValueError):
                sim_speedup({"execution":{"protocol_version":"v0.6.1","sim_speedup":value}})

    def test_clock_rate_window_and_source_evidence_gap_at_1_2_4(self):
        for speed in (1,2,4):
            for multiplier,expected in ((.6,True),(1.,True),(1.9,True),(.4,False),(2.1,False)):
                pairs=[(i*.1, i*.1*multiplier/speed) for i in range(100)]
                self.assertEqual(fit_clock(pairs,speed,source_time_contract=True)["available"],expected)
            gap=[(i*.1, i*.1/speed) for i in range(120) if not 20<=i<50]
            self.assertFalse(fit_clock(gap,speed,source_time_contract=True)["available"])

    def test_same_grid_positions_velocities_and_relative_departures_at_1_2_4(self):
        outputs=[]
        for speed in (1,2,4):
            axis,offsets=axis_for(speed)
            grid=axis.grid(axis.host(8./speed),10)
            traces={a:[(i*.1,[i*.2, j*10.,8.,2.,0.,0.]) for i in range(81)]
                    for j,a in enumerate(offsets)}
            mapped=common_traces(axis,offsets,traces)
            samples={a:resample(rows,grid,.5) for a,rows in mapped.items()}
            raw=[dict(event="phase_start_sent",agent_id=a,t=(5.+delay)/speed)
                 for a,delay in zip(offsets,(0.,1.7))]
            events=axis.event_view(raw,{"run_epoch_monotonic_s":100.-5./speed})
            outputs.append((grid,samples,[e["t"] for e in events]))
            self.assertEqual(len(grid),81)
            self.assertEqual([e["t"] for e in events],[0.,1.7])
        self.assertEqual(outputs[0],outputs[1])
        self.assertEqual(outputs[0],outputs[2])

    def test_velocity_jacobian_preserves_fcu_measurement_units_at_1_2_4(self):
        outputs=[]
        for speed in (1,2,4):
            models={"uav_01":dict(available=True,knots=[(10.,0.),(20.,10./speed)]),
                    "uav_02":dict(available=True,knots=[(30.,0.),(40.,11./speed)])}
            axis=CommonTimeAxis(models)
            native=[(30.+i*.05,[30.+i*.05,0.,0.,1.,2.,-3.]) for i in range(101)]
            common=[(axis.source("uav_02",stamp),values) for stamp,values in native]
            grid=axis.grid(5.,10)
            samples=axis.observation_velocities("uav_02",resample(common,grid,.2))
            for index,(stamp,values) in enumerate(samples):
                self.assertAlmostEqual(values[0],30.+stamp/1.1,places=10)
                self.assertAlmostEqual(values[3],1./1.1,places=12)
                self.assertAlmostEqual(values[4],2./1.1,places=12)
                self.assertAlmostEqual(values[5],-3./1.1,places=12)
                if index:
                    self.assertAlmostEqual((values[0]-samples[index-1][1][0])/.1,values[3],places=10)
            self.assertEqual(native[0][1],[30.,0.,0.,1.,2.,-3.])
            self.assertFalse(axis.metadata["velocity_conversion"]["position_difference_substitution"])
            outputs.append(samples)
        self.assertEqual(outputs[0],outputs[1]); self.assertEqual(outputs[0],outputs[2])

    def test_piecewise_velocity_derivative_has_declared_bounded_knot_semantics(self):
        for speed in (1,2,4):
            models={"uav_01":dict(available=True,knots=[(10.,0.),(30.,20./speed)]),
                    "uav_02":dict(available=True,knots=[(30.,0.),(40.,10./speed),(45.,20./speed)])}
            axis=CommonTimeAxis(models)
            self.assertIsNone(axis.velocity_factor("uav_02",29.9))
            self.assertEqual(axis.velocity_factor("uav_02",30.),1.)
            self.assertEqual(axis.velocity_factor("uav_02",40.),1.)
            self.assertEqual(axis.velocity_factor("uav_02",40.001),.5)
            self.assertEqual(axis.velocity_factor("uav_02",45.),.5)
            self.assertIsNone(axis.velocity_factor("uav_02",45.1))
            rows=[(10.,[0.,0.,0.,1.,0.,0.]),(10.1,[0.,0.,0.,1.,0.,0.]),(21.,[0.,0.,0.,1.,0.,0.])]
            converted=axis.observation_velocities("uav_02",rows)
            self.assertEqual(converted[0][1][3],1.)
            self.assertEqual(converted[1][1][3],.5)
            self.assertIsNone(converted[2][1])

    def test_velocity_scaling_is_not_position_difference_substitution(self):
        axis=CommonTimeAxis({"uav_01":dict(available=True,knots=[(10.,0.),(20.,10.)]),
                             "uav_02":dict(available=True,knots=[(30.,0.),(40.,11.)])})
        rows=[(0.,[99.,99.,99.,3.,0.,0.]),(1.,[99.,99.,99.,3.,0.,0.])]
        converted=axis.observation_velocities("uav_02",rows)
        self.assertEqual(converted[0][1][:3],[99.,99.,99.])
        self.assertAlmostEqual(converted[0][1][3],3./1.1)
        self.assertEqual(rows[0][1][3],3.)

    def test_real_patrol_revisit_pass_and_fail_are_invariant_at_1_2_4(self):
        for end,expected in ((80.,True),(160.,False)):
            outputs=[]
            for speed in (1,2,4):
                scene,traces,windows=patrol_case(end=end)
                axis,offsets=axis_for(speed,tuple(traces))
                result=patrol(scene,common_traces(axis,offsets,traces),windows,{},validator_version="perimeter_revisit_v2")
                self.assertIs(result["conditions"]["max_gap"],expected)
                outputs.append(result)
            self.assertEqual(outputs[0],outputs[1])
            self.assertEqual(outputs[0],outputs[2])

    def test_real_rapid_passage_low_speed_dwell_pass_and_fail_at_1_2_4(self):
        for hold,expected in ((.5,True),(2.,False)):
            traces=trajectory([(-6,10),(15,10)])
            end=traces[-1][0]
            traces.extend((end+i*.1,[15.,10.,8.]) for i in range(1,int(hold*10)+1))
            traces.extend((end+hold+t,p) for t,p in trajectory([(15,10),(36,10)])[1:])
            results=[]
            for speed in (1,2,4):
                axis,offsets=axis_for(speed,("uav_01",))
                result=measure_passage(common_traces(axis,offsets,{"uav_01":traces})["uav_01"],REGION)
                self.assertIs(result["conditions"]["no_dwell"],expected)
                results.append(result)
            self.assertEqual(results[0],results[1])
            self.assertEqual(results[0],results[2])

    def test_real_return_dwell_and_frame_allowance_at_1_2_4(self):
        for duration,expected in ((.3,False),(.9,True),(1.2,True)):
            outputs=[]
            for speed in (1,2,4):
                axis,offsets=axis_for(speed,("uav_01",))
                scene=dict(vehicles=[dict(id="uav_01",east_m=0.,north_m=0.)],task_spec=dict(
                    mission=dict(return_required=True), execution=dict(protocol_version="v0.6.1",sim_speedup=speed,
                    takeoff_alt_m=8.,confirmation_dwell_s=1.,record_hz=10,max_gap_s=.5,arrival_tolerance_m=1.)))
                rows=[(i/10,[0.,0.,8.]) for i in range(round(duration*10)+1)]
                window=[dict(agent_id="uav_01",role="return",start_s=0.,end_s=duration,complete_execution_window=True)]
                result=_return_result(scene,common_traces(axis,offsets,{"uav_01":rows}),window,
                                      {"uav_01":axis.evaluation_model("uav_01")})
                self.assertIs(result["success"],expected)
                self.assertAlmostEqual(result["per_agent"]["uav_01"]["dwell_allowance_s"],.1)
                outputs.append(result)
            self.assertEqual(outputs[0],outputs[1])
            self.assertEqual(outputs[0],outputs[2])

    def test_real_phase_windows_are_invariant_at_1_2_4(self):
        outputs=[]
        for speed in (1,2,4):
            scene,events,metadata=route_fixture(two_phases=True)
            axis,offsets=axis_for(speed,("a",))
            scene["task_spec"]["execution"].update(protocol_version="v0.6.1",sim_speedup=speed)
            raw_events=copy.deepcopy(events)
            for event in raw_events:
                for key in ("t","release_t"):
                    if key in event: event[key]/=speed
            raw_meta=dict(metadata,mission_end_monotonic_s=100.+6./speed,elapsed_s=8./speed)
            traces={"a":[row(1,0),row(2,2),row(3,2),row(4,2),row(5,0),row(6,0)]}
            outputs.append(build_route_windows(scene,common_traces(axis,offsets,traces),
                axis.event_view(raw_events,raw_meta),axis.metadata_view(raw_meta),0.,"observation",
                {"a":axis.evaluation_model("a")}))
        self.assertEqual(outputs[0],outputs[1])
        self.assertEqual(outputs[0],outputs[2])

    def test_unmapped_event_stays_unknown_and_never_becomes_zero(self):
        scene,events,metadata=route_fixture()
        axis,_=axis_for(2,("a",))
        events[1]["t"]=-100.
        converted=axis.event_view(events,metadata)
        self.assertIsNone(converted[1]["t"])
        windows=build_route_windows(scene,{"a":[row(1,0),row(2,2),row(6,2)]},
            converted,axis.metadata_view(metadata),0.,"observation",{"a":axis.evaluation_model("a")})
        self.assertIsNone(windows[0]["start_s"])
        self.assertFalse(windows[0]["complete_execution_window"])

    def _run_synthetic_analysis(self,root,speed,invalid_agents=(),host_scale=1.,clock_rates=None,moving=False):
        task=json.loads((ROOT/"missions/v3/recon_route_v06.json").read_text(encoding="utf-8"))
        task["execution"].update(protocol_version="v0.6.1",sim_speedup=speed)
        task["component_versions"]=component_versions(task["mission"]["intent"],task["flight_pattern"],"v0.6.1")
        scene=compile_task(task)
        root.mkdir(); (root/"raw").mkdir()
        metadata=dict(version="0.6.1",run_id="synthetic",scenario=scene,status="completed",
            run_epoch_monotonic_s=100.,flight_epoch_monotonic_s=100.+10.*host_scale/speed,
            mission_end_monotonic_s=100.+70.*host_scale/speed,elapsed_s=80.*host_scale/speed)
        write_json(root/"metadata.json",metadata); write_json(root/"scenario.json",scene)
        (root/"events.jsonl").write_text("",encoding="utf-8")
        truths={}
        for number,vehicle in enumerate(scene["vehicles"]):
            agent=vehicle["id"]; offset=10.+20.*number; packets=[]; truth=[]
            rate=(clock_rates or {}).get(agent,1.)
            for i in range(801):
                t=i/10; host=100.+t*host_scale/speed; source=offset+t/rate
                lat,lon=enu_to_geo(source,number*10.,scene["origin"]) if moving else (scene["origin"]["lat"],scene["origin"]["lon"])
                if agent not in invalid_agents:
                    packets.append(dict(recv_monotonic_s=host,message=dict(mavpackettype="SYSTEM_TIME",time_boot_ms=source*1000)))
                packets.append(dict(recv_monotonic_s=host,message=dict(mavpackettype="GLOBAL_POSITION_INT",
                    time_boot_ms=source*1000,lat=round(lat*1e7),
                    lon=round(lon*1e7),alt=round((scene["origin"]["alt_msl_m"]+8.)*1000),vx=0,vy=100 if moving else 0,vz=0)))
                truth.append((source,[source if moving else number*10.,number*10. if moving else 0.,8.,1.,0.,0.,0.]))
            (root/"raw"/f"{agent}.jsonl").write_text("\n".join(json.dumps(p) for p in packets),encoding="utf-8")
            truths[agent]=(truth,{},dict(available=True))
        with patch("swarm_sim.analysis_v3.read_truth",side_effect=lambda _,a,*args,**kw:truths[a]):
            return analyze_run_v3(root)

    def test_production_analyzer_exports_identical_601_frames_and_sim_metadata_at_1_2_4(self):
        grids=[]
        with tempfile.TemporaryDirectory() as tmp:
            for speed in (1,2,4):
                output,quality,_=self._run_synthetic_analysis(Path(tmp)/str(speed),speed)
                manifest=json.loads((output/"manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(quality["frames"],601)
                self.assertEqual(manifest["duration_s"],60.)
                self.assertEqual(manifest["time_base"],"sim_source")
                self.assertEqual(manifest["common_time_axis"]["reference_agent_id"],"uav_01")
                with (output/"observations.csv").open(encoding="utf-8") as stream:
                    grids.append([(r["t_s"],r["agent_id"]) for r in csv.DictReader(stream)])
                dataset_root=Path(tmp)/f"dataset_{speed}"
                dataset=build_dataset([Path(tmp)/str(speed)],dataset_root)
                loaded=load_episode(dataset_root/dataset["episodes"][0]["directory"])
                self.assertEqual(loaded["metadata"]["time_base"],"sim_source")
                self.assertEqual(len(loaded["x"]),601)
                language=describe_dataset(dataset_root)
                self.assertEqual(language["skipped_episodes"],1)
        self.assertEqual(grids[0],grids[1]); self.assertEqual(grids[0],grids[2])

    def test_production_analysis_reference_fallback_and_all_invalid_exports_ineligible(self):
        with tempfile.TemporaryDirectory() as tmp:
            output,quality,_=self._run_synthetic_analysis(Path(tmp)/"fallback",2,("uav_01",))
            self.assertEqual(quality["common_time_axis"]["reference_agent_id"],"uav_02")
            self.assertFalse(quality["episode_quality_eligible"])
            output,quality,_=self._run_synthetic_analysis(Path(tmp)/"unavailable",4,("uav_01","uav_02","uav_03","uav_04"))
            self.assertFalse(quality["common_time_axis"]["available"])
            self.assertEqual(quality["frames"],0)
            self.assertFalse(quality["episode_quality_eligible"])
            self.assertTrue((output/"manifest.json").is_file())

    def test_declared_one_x_does_not_substitute_host_seconds_for_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            output,quality,_=self._run_synthetic_analysis(Path(tmp)/"host_drift",1,host_scale=1.025)
            manifest=json.loads((output/"manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(quality["frames"],601)
            self.assertEqual(manifest["duration_s"],60.)
            self.assertAlmostEqual(manifest["duration_host_s"],61.5)

    def test_real_analyzer_scales_nonreference_fcu_velocity_at_1_2_4(self):
        with tempfile.TemporaryDirectory() as tmp:
            for speed in (1,2,4):
                output,quality,_=self._run_synthetic_analysis(Path(tmp)/str(speed),speed,
                    clock_rates={"uav_02":1.1},moving=True)
                models=json.loads((output/"clock_models.json").read_text(encoding="utf-8"))
                self.assertAlmostEqual(models["uav_02"]["slope"],1.1/speed,places=10)
                with (output/"observations.csv").open(encoding="utf-8") as stream:
                    rows=[r for r in csv.DictReader(stream) if r["agent_id"]=="uav_02" and r["valid"]=="1"]
                self.assertEqual(len(rows),601)
                for record in rows:
                    self.assertAlmostEqual(float(record["ve_m_s"]),1./1.1,places=8)
                with (output/"truth.csv").open(encoding="utf-8") as stream:
                    truth=[r for r in csv.DictReader(stream) if r["agent_id"]=="uav_02" and r["valid"]=="1"]
                derivative=(float(truth[100]["east_m"])-float(truth[99]["east_m"]))/0.1
                self.assertAlmostEqual(derivative,float(rows[100]["ve_m_s"]),places=8)
                self.assertTrue(quality["common_time_axis"]["velocity_conversion"]["raw_packets_preserved"])


if __name__ == "__main__":
    unittest.main()
