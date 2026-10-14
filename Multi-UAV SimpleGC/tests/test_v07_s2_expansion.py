"""S2 expansion phase 1: transit criterion, planner and truncation tests (no plotting)."""
from copy import deepcopy
import math
import unittest

import numpy as np

from task_v07.geometry import geometry_facts, offset_geometry, radial_points_exact
from task_v07.labels import measure, role_kind
from task_v07.visibility import ExactVisibilityPlanner
from task_v07.expansion.contracts import validate_route_bundle
from task_v07.expansion.evaluation import truncation_check
from task_v07.expansion.geometry_checks import check_polyline, check_retreat_point, check_endpoint_spacing
from task_v07.expansion.pipeline import exclusion_policy, forbidden_zone_ids, COMMON_CONSTANTS
from task_v07.expansion.role_evaluation import group_evaluator
from task_v07.expansion.role_planners import TransitPlanner, PlanningInfeasible, offset_polyline

CENTER = np.array([2000.0, 2000.0])


def scene():
    s = {"world": {"geometry": {"type": "Polygon", "vertices_m": [[0, 0], [4000, 0], [4000, 4000], [0, 4000]]}},
         "entities": [{"id": "f", "type": "facility", "geometry": {"type": "Circle", "center_m": CENTER.tolist(), "radius_m": 20}}]}
    for name, r in (("warning", 700), ("alert", 300), ("protected", 150)):
        s["entities"].append({"id": f"f_{name}", "type": "protection_zone", "facility_id": "f", "layer": name,
                              "offset_m": r - 20, "geometry": {"type": "Circle", "center_m": CENTER.tolist(), "radius_m": r}})
    return s


def skeleton(ids, approach="multi_direction"):
    sk = {"base_intent": "transit", "role": "transit", "execution_method": "transit", "target_id": "f",
          "group_id": "g", "members": ids, "agent_ids": ids, "approach_mode": approach, "column_seed": 7,
          **COMMON_CONSTANTS, "transit": dict(TransitPlanner.criteria), "references": {},
          "exclusion_policy": exclusion_policy(scene(), "transit", "f", ids)}
    return sk


def straight(offset, sign, speed=5.0, stop=None, loop=False):
    """Line y=c+offset traversed in direction sign; ends at warning+210 m on the extension."""
    half = math.sqrt(910 ** 2 - offset ** 2)
    start = np.array([CENTER[0] - sign * 1000, CENTER[1] + offset])
    end = np.array([CENTER[0] + sign * half, CENTER[1] + offset])
    n = int(round(np.linalg.norm(end - start) / speed * 10))
    positions = [start + (end - start) * k / n for k in range(n + 1)]
    velocities = [np.array([sign * speed, 0.0])] * n + [np.zeros(2)]
    if stop is not None:   # pause inside the zone at x offset `stop`
        k = int(np.argmin([abs(p[0] - CENTER[0] - stop) for p in positions]))
        positions[k:k] = [positions[k]] * 30
        velocities[k:k] = [np.zeros(2)] * 30
    if loop:               # one full 60 m radius circle inside the zone near the centre line
        k = int(np.argmin([abs(p[0] - CENTER[0]) for p in positions]))
        base = positions[k]
        ring = [base + 60 * np.array([math.sin(a), 1 - math.cos(a)]) for a in np.linspace(0, 2 * math.pi, 76)[1:]]
        vel = [speed * np.array([math.cos(a), math.sin(a)]) for a in np.linspace(0, 2 * math.pi, 76)[1:]]
        positions[k:k] = ring; velocities[k:k] = vel
    positions += [end] * 40; velocities += [np.zeros(2)] * 40
    return np.array(positions), np.array(velocities), end


def run_for(specs):
    ids = sorted(specs)
    tracks = {a: straight(*specs[a]) if len(specs[a]) == 2 else specs[a] for a in ids}
    length = max(len(tr[0]) for tr in tracks.values())
    p = np.zeros((length, len(ids), 3)); v = np.zeros_like(p)
    for i, a in enumerate(ids):
        pos, vel, _ = tracks[a]
        pos = np.vstack([pos, np.repeat(pos[-1:], length - len(pos), 0)])
        vel = np.vstack([vel, np.zeros((length - len(vel), 2))])
        p[:, i, :2] = pos; p[:, i, 2] = 100; v[:, i, :2] = vel
    sk = skeleton(ids)
    for a in ids:
        sk["references"][a] = {"endpoint_enu_m": [*tracks[a][2].tolist(), 100.0], "retreat_required": True,
                               "retreat_warning_clearance_m": 210.0}
    run = {"agent_ids": ids, "time_us": np.arange(length, dtype=np.int64) * 100000, "p": p, "v": v,
           "execution_status": "completed", "end_us": length * 100000}
    return sk, run


class TransitCriterionTests(unittest.TestCase):
    def test_role_kind_keeps_vertical_slice_branches(self):
        self.assertEqual(role_kind({"base_intent": "penetration", "role": "intrusion"}), "intrusion")
        self.assertEqual(role_kind({"base_intent": "reconnaissance", "role": "reconnaissance",
                                    "execution_method": "annular_sector_lawnmower"}), "area_search")
        self.assertEqual(role_kind({"base_intent": "reconnaissance", "role": "reconnaissance",
                                    "execution_method": "equal_strip_lawnmower"}), "area_search")
        with self.assertRaises(ValueError):
            role_kind({"base_intent": "patrol", "role": "patrol"})

    def test_two_sided_crossing_succeeds_with_measured_facts(self):
        sk, run = run_for({"a": (450, 1), "b": (-450, -1)})
        labels, frame = measure(scene(), sk, run, "synchronous")
        group = labels["task_groups"]["g"]
        self.assertEqual(group["result"]["status"], "success", group["result"])
        c = labels["agents"]["a"]["observed"]["contribution"]
        self.assertAlmostEqual(c["chord_length_m"], 2 * math.sqrt(700 ** 2 - 450 ** 2), delta=6)
        self.assertAlmostEqual(c["entry_exit_azimuth_difference_deg"], 180 - 2 * math.degrees(math.asin(450 / 700)), delta=1)
        self.assertEqual(labels["agents"]["a"]["observed"]["core_event"]["raw_event_type"], "enter_warning_zone")
        self.assertGreaterEqual(group["observed"]["approach_span_deg"], 170)
        self.assertTrue(group["result"]["conditions"]["multi_direction_span"])
        self.assertEqual(labels["schema_version"], "traj2language.labels/0.7-s2x.2")
        self.assertTrue((frame["phase"][-1] == 4).all())

    def test_small_entry_exit_azimuth_difference_fails(self):
        sk, run = run_for({"a": (650, 1), "b": (-450, -1)})
        labels, _ = measure(scene(), sk, run, "synchronous")
        conditions = labels["agents"]["a"]["result"]["conditions"]
        self.assertTrue(conditions["chord_length"])
        self.assertFalse(conditions["entry_exit_azimuth_difference"])
        self.assertEqual(labels["task_groups"]["g"]["result"]["status"], "failure")

    def test_stop_and_loop_inside_warning_fail(self):
        sk, run = run_for({"a": straight(450, 1, stop=100), "b": straight(-450, -1, loop=True)})
        labels, _ = measure(scene(), sk, run, "synchronous")
        self.assertGreater(labels["agents"]["a"]["observed"]["contribution"]["longest_low_speed_in_warning_s"], 2)
        self.assertFalse(labels["agents"]["a"]["result"]["conditions"]["no_stop_in_warning"])
        self.assertGreaterEqual(labels["agents"]["b"]["observed"]["contribution"]["cumulative_turn_in_warning_deg"], 350)
        self.assertFalse(labels["agents"]["b"]["result"]["conditions"]["no_loop_in_warning"])

    def test_alert_entry_violates_explicit_policy(self):
        sk, run = run_for({"a": (200, 1), "b": (-450, -1)})
        labels, _ = measure(scene(), sk, run, "synchronous")
        self.assertFalse(labels["agents"]["a"]["result"]["conditions"]["exclusion_policy_respected"])
        self.assertTrue(labels["agents"]["b"]["result"]["conditions"]["exclusion_policy_respected"])

    def test_mid_chord_prefix_is_unknown_and_never_success(self):
        sk, run = run_for({"a": (450, 1), "b": (-450, -1)})
        full, _ = measure(scene(), sk, run, "synchronous")
        entry = min(x["observed"]["core_event"]["t_s"] for x in full["agents"].values())
        exit_ = max(x["observed"]["contribution"]["warning_exit_s"] for x in full["agents"].values())
        cutoff = round((entry + exit_) / 2, 1)
        prefix, _ = measure(scene(), sk, run, "synchronous", cutoff_s=cutoff)
        conditions = prefix["agents"]["a"]["result"]["conditions"]
        self.assertIsNone(conditions["exited_warning"]); self.assertIsNone(conditions["chord_length"])
        self.assertIsNone(conditions["no_loop_in_warning"])
        self.assertEqual(prefix["task_groups"]["g"]["result"]["status"], "unknown")
        result = truncation_check(group_evaluator, scene(), sk, run, cutoff)
        self.assertEqual((result["status"], result["full_verdict"], result["prefix_verdict"]), ("PASS", "yes", "unknown"))


class TransitPlannerTests(unittest.TestCase):
    def family(self, n):
        states = [{"agent_id": f"u{i}", "position_enu_m": [60.0, 1500 + 25 * i, 100.0],
                   "velocity_enu_m_s": [0, 0, 0], "acceleration_enu_m_s2": [0, 0, 0]} for i in range(n)]
        return {"initial_states": states, "lateral_spacing_m": 20.0, "task_altitude_m": 100.0}

    def plan(self, approach, n=5):
        family = self.family(n)
        group = {"group_id": "g", "target_id": "f", "role": "transit", "execution_method": "transit",
                 "members": [s["agent_id"] for s in family["initial_states"]]}
        return group, TransitPlanner().plan_with_template(scene(), group, {"family": family, "approach_mode": approach,
                                                                            "planning_seed": 11})

    def test_same_and_multi_direction_routes_meet_planning_constraints(self):
        for approach in ("same_direction", "multi_direction"):
            group, (bundle, template) = self.plan(approach)
            validate_route_bundle(bundle, group["members"])
            policy = exclusion_policy(scene(), "transit", "f", group["members"])
            chords = [r["planned_chord"] for r in template["references"].values()]
            for a, route in bundle.waypoints_by_agent.items():
                self.assertEqual({p[2] for p in route}, {100.0})
                self.assertTrue(check_polyline(scene(), route, forbidden_regions=forbidden_zone_ids(scene(), policy[a]))["valid"])
                self.assertTrue(check_retreat_point(scene(), template["references"][a]["endpoint_enu_m"][:2])["valid"])
            self.assertTrue(all(c["chord_length_m"] >= 430 and c["entry_exit_azimuth_difference_deg"] >= 95 for c in chords))
            directions = {round(c["travel_direction_deg"], 6) for c in chords}
            span = template["approach_geometry"]["planned_entry_span_deg"]
            if approach == "same_direction":
                self.assertEqual(len(directions), 1)
                self.assertLess(span, 90)
            else:
                self.assertEqual(len(directions), 2)
                self.assertGreaterEqual(span, 90)
            offsets = sorted(c["lateral_offset_m"] * (1 if c["side"] == 0 else -1) for c in chords)
            self.assertEqual(len(set(np.round(offsets, 6))), len(offsets))
            self.assertEqual(template["approach_geometry"]["work_area_center_m"], CENTER.tolist())

    def test_same_direction_lanes_do_not_share_waypoints(self):
        s = scene()
        s["entities"].append({"id": "obstacle_01", "type": "hard_constraint_obstacle",
                              "geometry": {"type": "Circle", "center_m": [700, 1700], "radius_m": 150}})
        family = self.family(5)
        group = {"group_id": "g", "target_id": "f", "role": "transit", "execution_method": "transit",
                 "members": [st["agent_id"] for st in family["initial_states"]]}
        bundle, template = TransitPlanner().plan_with_template(s, group, {"family": family, "approach_mode": "same_direction",
                                                                          "planning_seed": 3})
        routes = {a: np.array(r)[1:-1, :2] for a, r in bundle.waypoints_by_agent.items()}
        for a in routes:
            for b in routes:
                if a < b:
                    gap = np.linalg.norm(routes[a][:, None] - routes[b][None], axis=2).min()
                    self.assertGreaterEqual(gap, 0.9 * family["lateral_spacing_m"], (a, b))
        lanes = sorted(r["formation_lane"]["lane_offset_m"] for r in template["references"].values())
        self.assertTrue(np.allclose(np.diff(lanes), family["lateral_spacing_m"]))
        policy = exclusion_policy(s, "transit", "f", group["members"])
        for a, route in bundle.waypoints_by_agent.items():
            self.assertTrue(check_polyline(s, route, forbidden_regions=forbidden_zone_ids(s, policy[a]))["valid"])

    def test_band_too_narrow_is_geometry_infeasible(self):
        with self.assertRaises(PlanningInfeasible) as caught:
            self.plan("same_direction", n=40)
        self.assertEqual(caught.exception.category, "geometry_infeasible")


class OffsetLaneTests(unittest.TestCase):
    def test_right_angle_lanes_keep_parallel_offset(self):
        centre = [[0, 0], [100, 0], [100, 100]]
        for o in (-20.0, 20.0):
            lane = np.array(offset_polyline(centre, o))
            self.assertGreaterEqual(len(lane), 3)
            # First leg is the line y=o, last leg is the line x=100-o.
            self.assertAlmostEqual(lane[0][1], o); self.assertAlmostEqual(lane[-1][0], 100 - o)
        inner = np.array(offset_polyline(centre, 20.0))   # left turn: +20 is inside
        self.assertEqual(len(inner), 3)
        self.assertTrue(np.allclose(inner[1], [80, 20]))
        self.assertIsNone(offset_polyline([[0, 0], [10, 0], [10, 10]], 30.0))  # inner lane would reverse

    def test_outer_lane_keeps_distance_from_sharp_corner(self):
        # 144 deg turn: a bevel would pass 22.8*cos(72 deg) = 7.0 m from the centre corner.
        corner = np.array([100.0, 0.0])
        heading = math.radians(144)
        centre = [[0, 0], corner.tolist(), (corner + 100 * np.array([math.cos(heading), math.sin(heading)])).tolist()]
        lane = np.array(offset_polyline(centre, -22.8))           # left turn -> negative offset is outside
        from shapely.geometry import LineString, Point
        self.assertGreaterEqual(LineString(lane).distance(Point(corner)), 22.8 * math.cos(math.radians(15)) - 1e-9)
        self.assertTrue(all(np.linalg.norm(np.diff(lane, axis=0), axis=1) >= 1))


class GeometryToleranceTests(unittest.TestCase):
    def test_exactly_tangent_planner_edge_passes_and_closer_edge_fails(self):
        s = scene()
        s["entities"].append({"id": "obstacle_01", "type": "hard_constraint_obstacle",
                              "geometry": {"type": "Polygon", "vertices_m": [[700, 1650], [900, 1650], [900, 1850], [700, 1850]]}})
        path = ExactVisibilityPlanner(s, 35.0).path([500, 1750], [1100, 1750])
        self.assertGreater(len(path), 2)
        route = [[*p, 100.0] for p in path]
        clearances = [geometry_facts(s["entities"][-1]["geometry"], np.array([a[:2], b[:2]]), footprint=True)["clearance_m"]
                      for a, b in zip(route, route[1:])]
        self.assertLess(abs(min(clearances) - 35.0), 1e-9)
        self.assertTrue(check_polyline(s, route)["valid"])
        self.assertFalse(check_polyline(s, [[650, 1615.001, 100.0], [950, 1615.001, 100.0]])["valid"])
        self.assertFalse(check_polyline(s, [[650, 1650, 100.0], [950, 1650, 100.0]], margin_m=0)["valid"])

    def test_retreat_exactly_on_200m_boundary_passes(self):
        s = scene()
        warning = next(e for e in s["entities"] if e.get("layer") == "warning")["geometry"]
        boundary = radial_points_exact(offset_geometry(warning, 200.0), CENTER, [0.7])[0]
        self.assertLess(abs(float(geometry_facts(warning, boundary)["signed_distance_m"]) - 200), 1e-9)
        self.assertTrue(check_retreat_point(s, boundary)["valid"])
        inside = CENTER + (np.linalg.norm(boundary - CENTER) - 1e-3) * (boundary - CENTER) / np.linalg.norm(boundary - CENTER)
        self.assertFalse(check_retreat_point(s, inside)["valid"])


class PlanningIntervalInterceptTests(unittest.TestCase):
    """Verify the planning-layer interval gate fires before simulation."""

    def _make_overlapping_descriptor(self):
        """Descriptor whose planner sends all agents to the exact same waypoints."""
        agents = ["uav_01", "uav_02", "uav_03"]
        states = [{"agent_id": a, "position_enu_m": [200.0 + i * 5, 200.0, 100.0],
                   "velocity_enu_m_s": [0, 0, 0], "acceleration_enu_m_s2": [0, 0, 0]}
                  for i, a in enumerate(agents)]
        family = {
            "family_id": "test_family",
            "sampling_seed": 1,
            "task_altitude_m": 100.0,
            "lateral_spacing_m": 20.0,
            "cruise_speed_m_s": 5.0,
            "initial_states": states,
        }
        return {
            "schema_version": "traj2language.s2x_vertical_request/0.7.1",
            "skeleton_id": "test_overlap_sk00",
            "family_id": "test_family",
            "map_id": "test_map",
            "base_intent": "reconnaissance",
            "subset": "regular",
            "cruise_speed_m_s": 5.0,
            "task_altitude_m": 100.0,
            "role_seed": 42,
            "common_draw": {"approach_mode": "same_direction"},
            "task_groups": [{"group_id": "g", "target_id": "f",
                             "role": "reconnaissance",
                             "execution_method": "close_observation",
                             "members": agents}],
            "family_conditions": family,
            "agent_ids": agents,
            "column_seed": 42,
            **COMMON_CONSTANTS,
        }

    def test_overlapping_routes_intercepted_before_simulation(self):
        """A bundle where all agents share identical endpoints must be flagged
        by check_endpoint_spacing before any single-agent timing run."""
        from task_v07.expansion.contracts import RouteBundle

        agents = ["uav_01", "uav_02", "uav_03"]
        shared_route = [[200.0, 200.0, 100.0],
                        [2000.0, 2000.0, 100.0],
                        [3500.0, 2000.0, 100.0]]
        routes = {a: shared_route for a in agents}
        bundle = RouteBundle(routes, {a: 0.0 for a in agents})
        result = check_endpoint_spacing(bundle, agents)
        self.assertTrue(result["below_warning"],
                        f"Expected below_warning=True for identical endpoints, got {result}")
        self.assertAlmostEqual(result["minimum_m"], 0.0, places=3)

    def test_spread_close_observation_points_have_minimum_separation(self):
        """After the fix, close-observation agents must be at least 6 m apart
        at their individual observation points."""
        from task_v07.expansion.role_planners import CloseObservationPlanner
        s = scene()
        agents = [f"uav_{i+1:02d}" for i in range(4)]
        states = [{"agent_id": a,
                   "position_enu_m": [200.0 + i * 30, 200.0, 100.0],
                   "velocity_enu_m_s": [0, 0, 0], "acceleration_enu_m_s2": [0, 0, 0]}
                  for i, a in enumerate(agents)]
        group = {"group_id": "g", "target_id": "f", "role": "reconnaissance",
                 "execution_method": "close_observation", "members": agents}
        params = {"family": {"task_altitude_m": 100.0, "lateral_spacing_m": 20.0,
                              "cruise_speed_m_s": 5.0, "initial_states": states},
                  "approach_mode": "same_direction", "planning_seed": 7}
        bundle, template = CloseObservationPlanner().plan_with_template(s, group, params)
        obs_pts = [np.array(template["references"][a]["observation_point_enu_m"][:2])
                   for a in agents]
        for i in range(len(obs_pts)):
            for j in range(i + 1, len(obs_pts)):
                dist = float(np.linalg.norm(obs_pts[i] - obs_pts[j]))
                self.assertGreaterEqual(dist, 6.0,
                    f"obs points {agents[i]}/{agents[j]} only {dist:.2f} m apart")


if __name__ == "__main__":
    unittest.main()
