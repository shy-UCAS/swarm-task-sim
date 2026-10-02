"""M04: ordered stop attribution without changing frozen v1 diagnostics."""

import copy
import unittest

from swarm_sim.execution_metrics import compute_execution_metrics, compute_execution_metrics_v2


def repeated_corner_fixture():
    start = dict(east_m=0., north_m=0., up_m=8.)
    corner_a = dict(east_m=10., north_m=0., up_m=8.)
    corner_b = dict(east_m=10., north_m=10., up_m=8.)
    corner_c = dict(east_m=0., north_m=10., up_m=8.)
    route = [corner_a, corner_b, corner_c, start, corner_a, corner_b, corner_c, start]
    scene = dict(record_hz=10, max_gap_s=.2, vehicles=[dict(id="a")],
        task_spec=dict(execution=dict(control_mode="semantic_phase_route_v1")),
        phases=[dict(name="p00_patrol", semantic_phase="patrol", routes={"a": route})],
        semantic_plan=dict(execution_phases=dict(p00_patrol=dict(agents=dict(a=dict(
            start_point=start, waypoint_planner_indices=list(range(1, 9))))))),
        planning=dict(per_agent_reference_routes=dict(a=dict(patrol=[start, *route])),
            nominal_phase_timing=dict(p00_patrol=dict(per_agent_waypoint_arrival_s=dict(a=list(range(1, 9)))))))
    # The first A visit includes one four-tick stop. The second A visit is fast.
    anchors = [(0., start), (.8, corner_a), (1.2, corner_a), (2., corner_b),
               (3., corner_c), (4., start), (5., corner_a), (6., corner_b),
               (7., corner_c), (8., start)]
    rows = []
    for tick in range(81):
        stamp = round(tick / 10, 10)
        before, after = next(((a, b) for a, b in zip(anchors, anchors[1:])
                             if a[0] <= stamp <= b[0]), (anchors[-2], anchors[-1]))
        fraction = (stamp - before[0]) / (after[0] - before[0])
        x = before[1]["east_m"] + fraction * (after[1]["east_m"] - before[1]["east_m"])
        y = before[1]["north_m"] + fraction * (after[1]["north_m"] - before[1]["north_m"])
        speed = 0. if .8 <= stamp <= 1.2 else 2.
        rows.append((stamp, [x, y, 8., speed, 0., 0.]))
    windows = [dict(agent_id="a", phase="p00_patrol", semantic_phase="patrol",
                    start_s=0., end_s=8., complete_execution_window=True)]
    return scene, {"a": rows}, windows


class ExecutionArtifactsV2Tests(unittest.TestCase):
    def test_nonrepeated_route_is_exact_v1_except_version(self):
        scene, traces, windows = repeated_corner_fixture()
        scene["phases"][0]["routes"]["a"] = scene["phases"][0]["routes"]["a"][:3]
        scene["planning"]["per_agent_reference_routes"]["a"]["patrol"] = (
            scene["planning"]["per_agent_reference_routes"]["a"]["patrol"][:4])
        args = scene, traces, windows
        before = copy.deepcopy(args)
        old = compute_execution_metrics(*args)
        new = compute_execution_metrics_v2(*args)
        self.assertEqual(args, before)
        self.assertEqual(old.pop("version"), "execution_artifacts_v1")
        self.assertEqual(new.pop("version"), "execution_artifacts_v2")
        self.assertEqual(new, old)

    def test_one_stop_is_attributed_only_to_first_visit(self):
        args = repeated_corner_fixture()
        before = copy.deepcopy(args)
        old = compute_execution_metrics(*args)
        new = compute_execution_metrics_v2(*args)
        self.assertEqual(args, before)
        self.assertEqual(new["version"], "execution_artifacts_v2")
        records = [r for r in new["intermediate_waypoints"]["records"]
                   if r["point"]["east_m"] == 10 and r["point"]["north_m"] == 0]
        self.assertEqual([r["route_index"] for r in records], [0, 4])
        self.assertEqual([r["stopped"] for r in records], [True, False])
        self.assertEqual(sum(bool(r["stop_intervals_s"]) for r in records), 1)
        self.assertEqual(new["thresholds"]["0.3"]["per_agent"]["a"]["counts_by_location"],
                         dict(intermediate_waypoint=1, semantic_endpoint=0, other=0))
        self.assertEqual(old["intermediate_waypoints"]["stopped_count"] > 1, True)
        self.assertTrue(new["ordered_visit_attribution"]["phase_evidence"]["a:p00_patrol"]["evidence_complete"])

    def test_missing_visit_evidence_makes_location_unknown(self):
        scene, traces, windows = repeated_corner_fixture()
        traces["a"] = [(t, p) for t, p in traces["a"] if not (3.1 <= t <= 4.1)]
        report = compute_execution_metrics_v2(scene, traces, windows)
        agent = report["thresholds"]["0.3"]["per_agent"]["a"]
        self.assertEqual(agent["unknown_location_count"], 1)
        self.assertIsNone(agent["stops"][0]["location"])
        self.assertIsNone(report["intermediate_waypoints"]["stop_rate"])

    def test_stop_after_next_phase_release_is_not_assigned_to_patrol(self):
        scene, traces, windows = repeated_corner_fixture()
        scene["phases"].append(dict(name="p01_return", semantic_phase="return",
                                    routes={"a": [dict(east_m=-5., north_m=0., up_m=8.)]}))
        windows.append(dict(agent_id="a", phase="p01_return", semantic_phase="return",
                            start_s=8., end_s=8.5, complete_execution_window=True))
        traces["a"].extend((t / 10, [0., 0., 8., 0., 0., 0.]) for t in range(81, 86))
        report = compute_execution_metrics_v2(scene, traces, windows)
        stops = report["thresholds"]["0.3"]["per_agent"]["a"]["stops"]
        self.assertEqual(len(stops), 2)
        self.assertIsNone(stops[1].get("ordered_visit_assignment"))
        self.assertEqual(stops[1]["location"], "semantic_endpoint")

    def test_same_entry_point_is_intermediate_then_terminal_by_visit_time(self):
        scene, traces, windows = repeated_corner_fixture()
        for stamp, values in traces["a"]:
            if 3.9 <= stamp <= 4.2 or 7.8 <= stamp <= 8.:
                values[3] = 0.
        report = compute_execution_metrics_v2(scene, traces, windows)
        stops = report["thresholds"]["0.3"]["per_agent"]["a"]["stops"]
        self.assertEqual([s["location"] for s in stops],
                         ["intermediate_waypoint", "intermediate_waypoint", "semantic_endpoint"])
        self.assertEqual([s["ordered_visit_assignment"]["route_index"] for s in stops], [0, 3, 7])


if __name__ == "__main__":
    unittest.main()
