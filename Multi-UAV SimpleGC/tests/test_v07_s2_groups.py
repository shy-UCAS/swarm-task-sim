"""Known-answer group composition, cross-group distances and shared-clock tests."""
from copy import deepcopy
import unittest
import tempfile
from pathlib import Path
import numpy as np

from test_v07_s2_expansion import scene, run_for
from task_v07.expansion.multi_labels import measure_groups
from task_v07.expansion.pipeline import exclusion_policy
from task_v07.expansion.episode_pipeline import compose_timing_plans, episode_interval_check
from task_v07.expansion.contracts import RouteBundle, P0ContractError
from task_v07.execution import departure_delays


def fixture():
    public = scene()
    shift = np.array([-1000., -900.])
    for entity in deepcopy(public["entities"]):
        entity["id"] = entity["id"].replace("f", "q", 1)
        if "facility_id" in entity:
            entity["facility_id"] = "q"
        entity["geometry"]["center_m"] = (np.asarray(entity["geometry"]["center_m"]) + shift).tolist()
        public["entities"].append(entity)
    first, first_run = run_for({"a": (450, 1), "b": (-450, -1)})
    second, second_run = run_for({"c": (450, 1), "d": (-450, -1)})
    first.update(group_id="g1", between_group_offset_s=12.3)
    second.update(group_id="g2", target_id="q", between_group_offset_s=45.6)
    second_run["p"][:, :, :2] += shift
    for ref in second["references"].values():
        ref["endpoint_enu_m"][:2] = (np.asarray(ref["endpoint_enu_m"][:2]) + shift).tolist()
    for group in (first, second):
        group["exclusion_policy"] = exclusion_policy(public, "transit", group["target_id"], group["members"])
    run = {**first_run, "agent_ids": ["a", "b", "c", "d"],
           "p": np.concatenate([first_run["p"], second_run["p"]], axis=1),
           "v": np.concatenate([first_run["v"], second_run["v"]], axis=1)}
    root = {"base_intent": "transit", "members": run["agent_ids"], "agent_ids": run["agent_ids"],
            "group_skeletons": {"g1": first, "g2": second}}
    return public, root, run


class GroupEvidenceTests(unittest.TestCase):
    def test_independent_group_audit_and_condition_coverage(self):
        from task_v07.io import save_json, write_csv
        from scripts.audit_v07_s2_groups import audit_groups
        public, root, run = fixture()
        labels, frame = measure_groups(public, root, run, 'synchronous')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            for name, value in [('public_scene.json', public), ('task.json', root), ('labels.json', labels),
                                ('source.json', {'execution_status': run['execution_status']})]:
                save_json(path / name, value)
            write_csv(path / 'truth.csv', run['agent_ids'], run['time_us'], run['p'], run['v'])
            np.savez_compressed(path / 'truth_10hz.npz', **{k: run[k] for k in ('agent_ids', 'time_us', 'p', 'v')})
            np.savez_compressed(path / 'frame_labels.npz', **frame)
            from debt_line_evidence import line_evidence
            from scripts.audit_v07_m1 import audit_episode, audit_data
            with line_evidence(self.id(), audit_groups, audit_episode, audit_data):
                audited = audit_groups(path)
        self.assertEqual(audited['status'], 'PASS', audited)
        self.assertEqual(audited['uncovered_conditions'], [])

    def test_cross_group_collision_is_generation_error_not_role_failure(self):
        public, root, run = fixture()
        labels, frame = measure_groups(public, root, run, "synchronous")
        self.assertLess(labels["cluster"]["observed"]["minimum_separation_m"], 2.)
        self.assertFalse(labels["generation_quality"]["retained"])
        self.assertEqual(labels["cluster"]["result"]["status"], "success")
        self.assertEqual(set(labels["task_groups"]), {"g1", "g2"})
        self.assertIsNone(labels["cluster"]["observed"]["primary_target"])
        self.assertEqual(frame["region_assigned_target"].shape, run["p"].shape[:2])

    def test_group_semantics_are_id_aligned_under_column_permutation(self):
        public, root, run = fixture()
        original, _ = measure_groups(public, root, run, "synchronous")
        permutation = [3, 1, 0, 2]
        alternate = {**run, "agent_ids": [run["agent_ids"][i] for i in permutation],
                     "p": run["p"][:, permutation], "v": run["v"][:, permutation]}
        changed, _ = measure_groups(public, root, alternate, "synchronous")
        for key in ("agents", "task_groups", "cluster"):
            self.assertEqual(original[key], changed[key])

    def test_role_composition_mismatch_is_p0(self):
        public, root, run = fixture()
        root["base_intent"] = "penetration"
        with self.assertRaises(P0ContractError):
            measure_groups(public, root, run, "synchronous")

    def test_single_shared_target_rule_also_holds_before_core_events(self):
        public, root, run = fixture()
        root["group_skeletons"].pop("g2")
        root["members"] = root["agent_ids"] = ["a", "b"]
        run = {**run, "agent_ids": ["a", "b"], "p": run["p"][:, :2], "v": run["v"][:, :2]}
        labels, _ = measure_groups(public, root, run, "synchronous", cutoff_s=1.)
        self.assertEqual(labels["cluster"]["observed"]["primary_target"], "f")
        self.assertTrue(all(a["observed"]["core_event"]["t_s"] is None for a in labels["agents"].values()))


class GroupTimingTests(unittest.TestCase):
    def test_intrusion_half_work_cutoff_uses_own_measured_hold_completion(self):
        from unittest.mock import patch
        from scripts.run_v07_s2_episode_batch import group_truncations
        constants={'terminal_radius_m':1.,'terminal_speed_m_s':.15,'terminal_hold_s':2.}
        group={**constants,'role':'intrusion','members':['a','b'],
               'references':{'a':{'endpoint_enu_m':[0.,0.,100.]},'b':{'endpoint_enu_m':[100.,0.,100.]}}}
        t=np.arange(1001,dtype=np.int64)*100000
        p=np.zeros((len(t),2,3));p[:,:,2]=100.;p[:,1,0]=100.;p[:100,:,1]=5.
        v=np.zeros_like(p);v[:100,:,0]=1.
        run={'agent_ids':['a','b'],'time_us':t,'p':p,'v':v}
        labels={'agents':{a:{'observed':{'core_event':{'t_s':8.},'work_end_s':8.}} for a in ['a','b']}}
        with patch('scripts.run_v07_s2_episode_batch.truncation_check',return_value={'status':'PASS'}) as callback:
            checks=group_truncations({}, {'group_skeletons':{'g':group}},run,labels)
        self.assertEqual(checks['g']['measured_work_interval_s'],[8.,12.])
        self.assertEqual(callback.call_args.args[-1],10.)

    def test_offsets_shift_each_group_without_changing_its_batches(self):
        _, root, _ = fixture()
        measured = {"g1": {"a": 30., "b": 40.}, "g2": {"c": 50., "d": 60.}}
        plans = compose_timing_plans(root, measured)
        for gid, group in root["group_skeletons"].items():
            base = departure_delays(group, measured[gid])
            for mode in plans:
                actual = plans[mode]["by_group"][gid]
                self.assertEqual(actual["batch_by_agent"], base[mode]["batch_by_agent"])
                for a in group["members"]:
                    self.assertAlmostEqual(actual["departure_delays_s"][a] - base[mode]["departure_delays_s"][a], group["between_group_offset_s"])

    def test_full_clock_gate_checks_cross_group_mid_route_and_waiting(self):
        routes = {"a": [[0., 0., 100.], [100., 100., 100.]],
                  "b": [[0., 100., 100.], [100., 0., 100.]]}
        bundle = RouteBundle(routes, {"a": 0., "b": 0.})
        plans = {mode: {"departure_delays_s": {"a": 40., "b": 40.}} for mode in ("synchronous", "sequential")}
        report = episode_interval_check({"initial_settle_s": 20., "cruise_speed_m_s": 5.}, bundle, plans)
        for mode in plans:
            self.assertTrue(report[mode]["below_warning"])
            self.assertGreater(report[mode]["closest_pair"]["t_s"], 60.)


if __name__ == "__main__":
    unittest.main()
