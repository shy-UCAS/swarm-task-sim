"""WP-L visible-fact tests; all trajectories are synthetic, with no SITL."""

import copy
import csv
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path

from swarm_sim.dataset import build_dataset
from swarm_sim.language_v0 import describe_dataset
from swarm_sim.observer_facts_v0 import (PATTERN_PARAMETERS, _channel_facts, _compare,
                                         _cumulative_turn_radians, _return_observed, detect_pattern,
                                         extract_observer_facts)
from swarm_sim.recording import write_json
from swarm_sim.protocol import semantic_protocol
from swarm_sim.onboard_mission_params import VERSION as ONBOARD_VERSION
from swarm_sim.observation_processing import processing_versions
from swarm_sim.language_templates_v0 import generate_descriptions
from test_wp_l_templates import _facts
from v3_artifact_fixture import make_run, rehash


REGION = dict(min_east_m=0.0, min_north_m=0.0, width_m=20.0, height_m=10.0)


def _perimeter_points(laps=2):
    corners = [(0.0, 0.0), (20.0, 0.0), (20.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
    points = []
    for lap in range(laps):
        for first, second in zip(corners, corners[1:]):
            length = int(math.dist(first, second))
            for index in range(length):
                fraction = index / length
                points.append((len(points) * .1,
                               [first[0] + fraction * (second[0] - first[0]),
                                first[1] + fraction * (second[1] - first[1]), 8.0]))
    points.append((len(points) * .1, [0.0, 0.0, 8.0]))
    return points


def _strip_points():
    coordinates = []
    for row, reverse in ((2, False), (4, True), (6, False)):
        xs = range(21) if not reverse else range(20, -1, -1)
        for x in xs:
            coordinates.append((float(x), float(row)))
    return [(index * .1, [x, y, 8.0]) for index, (x, y) in enumerate(coordinates)]


def _densify_vertices(vertices):
    """Synthetic positions at at most 0.3 m / 0.1 s spacing; no planner input."""
    rows = [(0., [*vertices[0], 8.])]
    for first, second in zip(vertices, vertices[1:]):
        length = math.dist(first, second)
        count = max(1, math.ceil(length / .3))
        start = rows[-1][0]
        rows.extend((start + length / 3 * index / count,
                     [a + (b-a) * index / count for a, b in zip(first, second)] + [8.])
                    for index in range(1, count+1))
    return rows


def _measured_facts(rows, region, task):
    end = rows[-1][0]
    windows = [dict(agent_id="a", semantic_phase="approach", start_s=0., arrival_s=0.,
                    complete_execution_window=True),
               dict(agent_id="a", semantic_phase="observe", start_s=0., arrival_s=end,
                    complete_execution_window=True)]
    return _channel_facts({"a": rows}, windows, task, region, dict(duration_s=end), {}, ["a"])


class V06MeasuredScanTests(unittest.TestCase):
    def setUp(self):
        self.region = dict(min_east_m=0., min_north_m=0., width_m=54., height_m=30.)
        self.task = dict(mission=dict(intent="reconnaissance", intent_params={}),
                         execution=dict(protocol_version="v0.6", max_gap_s=.5, record_hz=10.))
        self.rectangle = [(3.5, 2.), (3.5, 28.), (14.5, 28.), (14.5, 2.), (3.5, 2.)]
        self.spiral = self.rectangle[:-1] + [(7.5, 2.), (7.5, 6.), (7.5, 24.),
                                           (10.5, 24.), (10.5, 6.), (7.5, 6.)]

    def test_v06_rectangular_scan_uses_unclear_and_never_parallel_description(self):
        for vertices in (self.rectangle, self.spiral):
            with self.subTest(vertices=vertices):
                rows = _densify_vertices(vertices)
                measured = _measured_facts(rows, self.region, self.task)
                self.assertEqual(measured["observed_pattern"], "unclear")
                self.assertIsNone(measured["scan_orientation"])
                self.assertIsNone(measured["loop_direction"])
                facts = _facts(pattern="unclear")
                facts["facts_version"] = "observer_facts_v06b"
                facts["observed"].update(measured)
                for description in generate_descriptions(facts, "measured_spiral", "test", 7):
                    self.assertNotIn("平行往返", description["text"])
                    self.assertTrue(any(s["template_id"].startswith("T2.neutral")
                                        for s in description["sentences"]))

    def test_v06_regular_scan_with_small_jitter_keeps_parallel_in_both_directions(self):
        for reverse in (False, True):
            for jitter in (0., .3):
                with self.subTest(reverse=reverse, jitter=jitter):
                    points = [point for _, point in _strip_points()]
                    if reverse:
                        points.reverse()
                    rows = [(index * .1, [p[0], p[1] + jitter * math.sin(index / 10), p[2]])
                            for index, p in enumerate(points)]
                    measured = _measured_facts(rows, REGION, self.task)
                    self.assertEqual(measured["observed_pattern"], "parallel_strips")
                    self.assertEqual(measured["scan_orientation"], "east_west")

    def test_v06_noisy_sweep_with_turnaround_overshoot_keeps_parallel_strips(self):
        """A real sweep overshoots at every turnaround without becoming a loop.

        The v0.6 downgrade uses the signed cumulative turn, so sample noise and a
        turnaround overshoot must not push an ordinary sweep over the threshold.
        """
        limit = math.radians(PATTERN_PARAMETERS["downgrade_cumulative_turn_deg"])
        rows = ((2.0, False), (4.0, True), (6.0, False))
        vertices = []
        for index, (y, reverse) in enumerate(rows):
            strip = [(float(x), y) for x in (range(21) if not reverse else range(20, -1, -1))]
            vertices.extend(strip)
            if index < len(rows) - 1:
                end = strip[-1]
                hook = (end[0] + (1.0 if not reverse else -1.0), end[1])
                vertices.extend([hook, (hook[0], (end[1] + rows[index + 1][0]) / 2)])
        base = _densify_vertices(vertices)
        for jitter in (.2, .5):
            with self.subTest(jitter=jitter):
                noisy = [(stamp, [p[0], p[1] + jitter * math.sin(index / 7.0), p[2]])
                         for index, (stamp, p) in enumerate(base)]
                measured = _measured_facts(noisy, REGION, self.task)
                self.assertEqual(measured["observed_pattern"], "parallel_strips")
                self.assertEqual(measured["scan_orientation"], "east_west")
                self.assertLess(_cumulative_turn_radians({"a": noisy}), limit)

    def test_v06_single_loop_narrow_scan_downgrades_to_unclear(self):
        """One narrow loop already accumulates a full turn; two loops do too."""
        limit = math.radians(PATTERN_PARAMETERS["downgrade_cumulative_turn_deg"])
        narrow_loop = [(8.0, 4.0), (8.0, 6.0), (12.0, 6.0), (12.0, 4.0), (8.0, 4.0)]
        narrow_spiral = [(8.0, 4.0), (8.0, 6.0), (12.0, 6.0), (12.0, 4.0), (9.5, 4.0),
                         (9.5, 4.8), (9.5, 5.2), (10.5, 5.2), (10.5, 4.8), (9.5, 4.8)]
        wide_loop = [(17.0, 13.0), (17.0, 17.0), (37.0, 17.0), (37.0, 13.0), (17.0, 13.0)]
        for region, vertices in ((REGION, narrow_loop), (REGION, narrow_spiral),
                                 (self.region, wide_loop), (self.region, self.rectangle),
                                 (self.region, self.spiral)):
            with self.subTest(vertices=vertices):
                rows = _densify_vertices(vertices)
                # The measured geometry on its own still looks like a scan: the
                # downgrade, not the raw detector, is what withholds the claim.
                self.assertEqual(detect_pattern({"a": rows}, region)["observed_pattern"],
                                 "parallel_strips")
                measured = _measured_facts(rows, region, self.task)
                self.assertEqual(measured["observed_pattern"], "unclear")
                self.assertIsNone(measured["scan_orientation"])
                self.assertGreaterEqual(_cumulative_turn_radians({"a": rows}), limit)
        sweep = _densify_vertices([(float(x), y) for y, reverse in rows
                                   for x in (range(21) if not reverse else range(20, -1, -1))])
        self.assertLess(_cumulative_turn_radians({"a": sweep}), limit)

    def test_v06_pattern_metadata_cannot_override_measured_scan_geometry(self):
        for rows, region in ((_densify_vertices(self.spiral), self.region), (_strip_points(), REGION)):
            expected = _measured_facts(rows, region, self.task)
            for pattern in ("equal_strip_rectangular_spiral", "equal_strip_lawnmower", "untrusted_label"):
                changed = copy.deepcopy(self.task)
                changed["flight_pattern"] = pattern
                self.assertEqual(_measured_facts(rows, region, changed), expected)
                del changed["flight_pattern"]
                self.assertEqual(_measured_facts(rows, region, changed), expected)

    def test_v05_frozen_scan_results_and_legacy_classifier_are_unchanged(self):
        task = copy.deepcopy(self.task)
        del task["execution"]["protocol_version"]
        self.assertEqual(_measured_facts(_strip_points(), REGION, task), dict(
            num_uavs=1, entry_side="west", observed_pattern="parallel_strips", scan_orientation="east_west",
            loop_direction=None, per_agent_laps_observed=None, return_observed=False, max_revisit_gap_s=None))
        for vertices in (self.rectangle, self.spiral):
            rows = _densify_vertices(vertices)
            legacy = detect_pattern({"a": rows}, self.region)
            self.assertEqual(legacy, dict(observed_pattern="parallel_strips", scan_orientation="north_south",
                                          loop_direction=None))
            measured = _measured_facts(rows, self.region, task)
            self.assertEqual({key: measured[key] for key in legacy}, legacy)


class PatternDetectorTests(unittest.TestCase):
    def test_l01_perimeter_and_parallel_strips_come_from_measured_geometry(self):
        perimeter = detect_pattern({"agent": _perimeter_points()}, REGION, visit_radius_m=1.0)
        self.assertEqual(perimeter["observed_pattern"], "perimeter_loop")
        self.assertEqual(perimeter["loop_direction"], "ccw")
        self.assertIsNone(perimeter["scan_orientation"])
        strips = detect_pattern({"agent": _strip_points()}, REGION, visit_radius_m=1.0)
        self.assertEqual(strips["observed_pattern"], "parallel_strips")
        self.assertEqual(strips["scan_orientation"], "east_west")
        self.assertIsNone(strips["loop_direction"])
        ambiguous = detect_pattern({"agent": _strip_points()[:12]}, REGION, visit_radius_m=1.0)
        self.assertEqual(ambiguous["observed_pattern"], "unclear")

    def test_recon_assigned_loop_is_still_detected_as_perimeter_loop(self):
        rows = _perimeter_points()
        task = dict(mission=dict(intent="reconnaissance", intent_params={}),
                    execution=dict(max_gap_s=.2, record_hz=10.0))
        windows = [dict(agent_id="agent", semantic_phase="approach", start_s=0.0),
                   dict(agent_id="agent", semantic_phase="observe", start_s=0.0,
                        arrival_s=rows[-1][0], complete_execution_window=True)]
        facts = _channel_facts({"agent": rows}, windows, task, REGION,
                               dict(duration_s=rows[-1][0]), {}, ["agent"])
        self.assertEqual(facts["observed_pattern"], "perimeter_loop")

    def test_l02_return_observed_requires_trajectory_evidence(self):
        windows = [dict(agent_id="a", semantic_phase="approach", start_s=0.0),
                   dict(agent_id="a", semantic_phase="observe", arrival_s=2.0,
                        complete_execution_window=True)]
        no_return = {"a": [(0.0, [0.0, -10.0, 8.0]), (1.0, [0.0, 0.0, 8.0]),
                           (2.0, [5.0, 5.0, 8.0]), (3.0, [5.0, 5.0, 8.0])]}
        self.assertIs(_return_observed(no_return, windows, ["a"], "observe", 1.0, 3.0, 1.0), False)
        returned = copy.deepcopy(no_return)
        returned["a"][-1] = (3.0, [0.0, -10.0, 8.0])
        self.assertIs(_return_observed(returned, windows, ["a"], "observe", 1.0, 3.0, 1.0), True)
        incomplete = {"a": no_return["a"][:-1]}
        self.assertIsNone(_return_observed(incomplete, windows, ["a"], "observe", 1.0, 3.0, 1.0))

    def test_l04_disagreements_withhold_lap_and_numeric_facts(self):
        fields, disagreements = [], []
        self.assertIsNone(_compare("per_agent_laps_observed", [2, 2], [2, 1], fields, disagreements))
        self.assertIsNone(_compare("max_revisit_gap_s", 10.0, 11.0, fields, disagreements))
        self.assertEqual([row["field"] for row in disagreements],
                         ["per_agent_laps_observed", "max_revisit_gap_s"])
        self.assertEqual(_compare("max_revisit_gap_s", 10.0, 10.4, fields, disagreements), 10.0)


class ManifestBoundFactTests(unittest.TestCase):
    def test_positive_synthetic_export_facts_and_manifest_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            # A quality-eligible but mission-failed v0.5 episode must still
            # receive a description; coverage and return both fail here.
            run, analysis = make_run(workspace / "synthetic_eligible_failure", success=False)
            task = json.loads((analysis / "task.json").read_text(encoding="utf-8"))
            task["execution"]["waypoint_hold_s"] = 1.0
            task["execution"]["hold_semantics"] = "integer_seconds_v1"
            write_json(analysis / "task.json", task)
            protocol = semantic_protocol({"task_spec": task})
            claims = dict(onboard_mission_param_check_version=ONBOARD_VERSION,
                          onboard_mission_param_check_required=True,
                          onboard_mission_param_check_status="pass",
                          onboard_mission_param_check_pass=True)
            for name in ("quality.json", "manifest.json"):
                payload = json.loads((analysis / name).read_text(encoding="utf-8"))
                payload.update(protocol, **claims)
                write_json(analysis / name, payload)
            write_json(analysis / "onboard_mission_param_check.json",
                       dict(version=ONBOARD_VERSION, required=True, status="pass", pass_gate=True))
            region = next(r for r in task["scenario"]["regions"]
                          if r["id"] == task["mission"]["target_region_id"])
            center = (region["min_east_m"] + region["width_m"] / 2,
                      region["min_north_m"] + region["height_m"] / 2)
            home = (center[0], region["min_north_m"] - 20.0)
            agents = sorted(v["id"] for v in task["scenario"]["vehicles"])
            windows = []
            for agent in agents:
                windows.extend((dict(agent_id=agent, semantic_phase="approach", start_s=0.0,
                                     arrival_s=1.0, complete_execution_window=True),
                                dict(agent_id=agent, semantic_phase="observe", start_s=1.0,
                                     arrival_s=3.9, complete_execution_window=True)))
            write_json(analysis / "phase_windows.json", dict(channels=dict(truth=windows, observation=windows),
                                                            **processing_versions()))
            labels = json.loads((analysis / "labels.json").read_text(encoding="utf-8"))
            labels["label_provenance"]["semantic_validation_version"] = protocol["semantic_validation_version"]
            labels["mission_metrics"]["truth"]["coverage"].update(
                model_version="ideal_horizontal_disk_v1", requested_grid_m=1.0)
            labels["mission_metrics"]["observation"]["coverage"].update(
                model_version="ideal_horizontal_disk_v1", requested_grid_m=1.0)
            write_json(analysis / "labels.json", labels)
            semantic = json.loads((analysis / "semantic_validation.json").read_text(encoding="utf-8"))
            semantic["semantic_validation_version"] = protocol["semantic_validation_version"]
            semantic["condition_results"] = dict(truth=dict(coverage=False, return_to_launch=False),
                                                 observation=dict(coverage=False, return_to_launch=False))
            write_json(analysis / "semantic_validation.json", semantic)
            constraints = json.loads((analysis / "execution_constraints.json").read_text(encoding="utf-8"))
            constraints["constraint_validation_version"] = protocol["execution_constraints_version"]
            write_json(analysis / "execution_constraints.json", constraints)
            manifest = json.loads((analysis / "manifest.json").read_text(encoding="utf-8"))
            manifest["duration_s"] = 4.0
            write_json(analysis / "manifest.json", manifest)
            for filename, columns in (("truth.csv", ("east_m", "north_m", "up_m")),
                                      ("observations.csv", ("east_m", "north_m", "up_m",
                                                            "ve_m_s", "vn_m_s", "vu_m_s"))):
                with (analysis / filename).open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(("t_s", "agent_id", "valid", *columns))
                    for agent in agents:
                        for tick in range(41):
                            time = tick / 10
                            xy = home if time < 1 else center
                            values = [xy[0], xy[1], 8.0]
                            if filename == "observations.csv":
                                values.extend((0.0, 0.0, 0.0))
                            writer.writerow((time, agent, 1, *values))
            rehash(run)
            dataset_root = workspace / "dataset"
            exported = build_dataset([run], dataset_root)
            episode = dataset_root / exported["episodes"][0]["directory"]
            frozen = hashlib.sha256((dataset_root / "dataset_manifest.json").read_bytes()).hexdigest()
            facts = extract_observer_facts(episode, frozen)
            self.assertEqual(facts["facts_version"], "observer_facts_v0")
            self.assertEqual(facts["observed"]["num_uavs"], len(agents))
            self.assertEqual(facts["observed"]["entry_side"], "south")
            self.assertIs(facts["observed"]["return_observed"], False)
            self.assertEqual(facts["provenance"]["dataset_manifest_sha256"], frozen)
            self.assertEqual(facts["model_metrics"]["coverage_ratio"], 0.5)
            self.assertIn("ideal_horizontal_disk_v1", facts["model_metrics"]["coverage_model"])
            self.assertEqual(facts["channel_check"]["disagreements"], [])
            self.assertEqual(facts["labels"]["mission_result"]["conditions"],
                             dict(coverage=False, **{"return": False}))
            self.assertFalse(facts["labels"]["mission_result"]["success"])
            language = describe_dataset(dataset_root)
            self.assertEqual(language["eligible_agree_episodes"], 1)
            self.assertEqual(language["descriptions"], 4)
            with self.assertRaisesRegex(ValueError, "dataset manifest changed"):
                extract_observer_facts(episode, "0" * 64)


if __name__ == "__main__":
    unittest.main()
