"""T1–T12: all fixtures are local temporary synthetic data."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from task_v07.io import INPUT_KEYS
from task_v07.s3._common import P0ContractError, RunNotReady, TEMPLATE_PATH, read_run, sha256, write_json
from task_v07.s3.describe import description_variants, render_description
from task_v07.s3.facts import extract_facts, from_sector
from task_v07.s3.loader import load_inputs, load_targets
from task_v07.s3.normalize import compute_anchors, normalized_view
from task_v07.s3.split import family_split
from task_v07.s3.verify import check_forbidden, load_templates, verify_description
from scripts import run_v07_s3_export as exporter
from test_v07_s3_fixtures import episode, labels, scene, trajectories


class S3UnitTests(unittest.TestCase):
    def test_T01_sectors_and_missing_member_heading(self):
        for headings, expected in (([0.], "正西"), ([45.], "西南"), ([90.], "正南"),
                                   ([135.], "东南"), ([180.], "正东"), ([225.], "东北"),
                                   ([270.], "正北"), ([315.], "西北"),
                                   ([202.4], "正东"), ([202.6], "东北"), ([359., 1.], "正西")):
            with self.subTest(headings=headings):
                members = [str(i) for i in range(len(headings))]
                self.assertEqual(from_sector(dict(zip(members, headings)), members), expected)
        for heading, expected in ((0., "正西"), (90., "正南"), (180., "正东"), (270., "正北")):
            value = labels()
            value["task_groups"]["task_group_01"]["observed"]["approach_headings_deg"] = dict.fromkeys(value["agents"], heading)
            extracted = extract_facts(value, scene())
            self.assertEqual(extracted["slots"]["from_sector"], expected)
            record = render_description(extracted["facts"], "x", "A")
            self.assertIn(expected + "方向", record["text"])
            self.assertTrue(verify_description(record, value, scene()))
        for missing in ("uav_01", "uav_02"):
            value = labels()
            value["task_groups"]["task_group_01"]["observed"]["approach_headings_deg"][missing] = None
            with self.subTest(missing=missing), self.assertRaisesRegex(P0ContractError, "None member heading"):
                extract_facts(value, scene())

    def test_T02_gates_and_subjects(self):
        cases = [
            ("failure", True, True, "sequential", "role_"),
            ("unknown", True, True, "sequential", "role_"),
            ("success", False, True, "sequential", "approach_"),
            ("success", True, None, "sequential", "exit_"),
            ("success", True, "mixed", "sequential", "exit_"),
            ("success", True, True, "unknown", "coord_"),
        ]
        for status, entered, exit_value, coordination, omitted in cases:
            value = labels()
            group = value["task_groups"]["task_group_01"]
            group["result"]["status"] = status
            group["observed"]["coordination"]["classification"] = coordination
            for aid, agent in value["agents"].items():
                agent["observed"]["regions_by_facility"]["facility_01"]["warning"]["entered_observed"] = entered
                agent["result"]["conditions"]["ended_outside_warning"] = (
                    aid == "uav_01" if exit_value == "mixed" else exit_value)
            facts = extract_facts(value, scene())["facts"]
            record = render_description(facts, "synthetic/episode", "A")
            with self.subTest(omitted=omitted, status=status):
                self.assertFalse(any(s["type"].startswith(omitted) for s in record["sentences"]))
                self.assertTrue(verify_description(record, value, scene()))
                if not entered:
                    first = next(s for s in record["sentences"] if s["group_id"] is not None)
                    self.assertTrue(first["text"].startswith("该编组"))
        # r2 order is fixed; omitted approach gives the first remaining sentence its subject.
        for entered, coordination, status, expected in (
            (True, "sequential", "success", ["approach_same", "coord_seq", "role_transit", "exit_out"]),
            (True, "synchronous", "success", ["approach_same", "coord_sync", "role_transit", "exit_out"]),
            (False, "sequential", "success", ["coord_seq", "role_transit", "exit_out"]),
            (False, "unknown", "success", ["role_transit", "exit_out"]),
            (False, "unknown", "failure", ["exit_out"]),
        ):
            for n_groups in (1, 2):
                value = labels()
                first_group = value["task_groups"]["task_group_01"]
                if n_groups == 2:
                    value["task_groups"]["task_group_02"] = deepcopy(first_group)
                    first_group["observed"]["members"] = ["uav_01"]
                    value["task_groups"]["task_group_02"]["observed"]["members"] = ["uav_02"]
                for group in value["task_groups"].values():
                    group["observed"]["coordination"]["classification"] = coordination
                    group["result"]["status"] = status
                for agent in value["agents"].values():
                    agent["observed"]["regions_by_facility"]["facility_01"]["warning"]["entered_observed"] = entered
                facts = extract_facts(value, scene())["facts"]
                for template_group in ("A", "B"):
                    with self.subTest(entered=entered, coordination=coordination, status=status,
                                      n_groups=n_groups, template_group=template_group):
                        record = render_description(facts, "synthetic/episode", template_group)
                        self.assertTrue(verify_description(record, value, scene()))
                        for index, gid in enumerate(sorted(value["task_groups"]), 1):
                            sentences = [s for s in record["sentences"] if s["group_id"] == gid]
                            self.assertEqual([s["type"] for s in sentences], expected)
                            subject = "该编组" if n_groups == 1 else f"第{index}编组（1架）"
                            self.assertTrue(sentences[0]["text"].startswith(subject))
                            if not entered:
                                self.assertEqual(sentences[0]["values"]["subj"], subject)
                                self.assertEqual(sentences[0]["values"].get("subj2", ""), "")
                        if entered and coordination == "sequential":
                            old_order = deepcopy(record)
                            old_order["sentences"][2:4] = reversed(old_order["sentences"][2:4])
                            old_order["text"] = "".join(s["text"] for s in old_order["sentences"])
                            with self.assertRaisesRegex(P0ContractError, "Sentence order/type/group"):
                                verify_description(old_order, value, scene())
        value = labels()
        g = value["task_groups"]["task_group_01"]
        g["assigned"]["role"] = g["assigned"]["execution_method"] = "intrusion"
        for a in value["agents"].values():
            del a["result"]["conditions"]["ended_outside_warning"]
        facts = extract_facts(value, scene())["facts"]
        self.assertIsNone(facts["groups"][0]["exit_state"])
        self.assertFalse(any(s["type"].startswith("exit_") for s in render_description(facts, "x", "A")["sentences"]))

    def test_T03_intent_sentence(self):
        names = {"transit": "过境", "reconnaissance": "侦察", "monitoring": "监视", "feint": "佯动", "penetration": "突防"}
        for intent, chinese in names.items():
            for status in ("success", "failure", "unknown"):
                value = labels()
                value["cluster"] = {"assigned": {"intent": intent}, "result": {"status": status}}
                record = render_description(extract_facts(value, scene())["facts"], "x", "A")
                sentence = record["sentences"][-1]
                with self.subTest(intent=intent, status=status):
                    self.assertEqual(sentence["type"], "intent_conforms" if status == "success" else "intent_insufficient")
                    if status == "success":
                        self.assertIn(chinese, sentence["text"])
                    else:
                        self.assertNotIn("intent", sentence["values"])
                    self.assertTrue(verify_description(record, value, scene()))

    def test_T04_rounding(self):
        for fraction, expected in ((.874, 85), (.876, 90)):
            value = labels()
            g = value["task_groups"]["task_group_01"]
            g["assigned"]["execution_method"] = "area_search"
            g["observed"]["shared_coverage"]["coverage_fraction"] = fraction
            self.assertEqual(extract_facts(value, scene())["facts"]["groups"][0]["coverage_pct"], expected)
        # Python round uses nearest-even at the halfway case: 75 / 10 -> 8.
        for duration, expected in ((4., 10), (74., 70), (75., 80)):
            value = labels()
            value["task_groups"]["task_group_01"]["assigned"]["execution_method"] = "close_observation"
            for agent in value["agents"].values():
                agent["observed"]["contribution"]["observation_dwell"]["total_duration_s"] = duration
            self.assertEqual(extract_facts(value, scene())["facts"]["groups"][0]["dwell_s"], expected)

    def test_T05_template_split_and_determinism(self):
        value = labels()
        facts = extract_facts(value, scene())["facts"]
        for split in ("train", "val", "test"):
            records = description_variants(facts, "run/episode", split)
            self.assertEqual(len(records), 2 if split == "test" else 3)
            self.assertEqual(records, description_variants(facts, "run/episode", split))
            for record in records:
                expected = "B" if split == "test" and not record["diagnostic_template_A"] else "A"
                self.assertTrue(all(s["template_id"].startswith(expected) for s in record["sentences"]))
                self.assertTrue(verify_description(record, value, scene()))
            if split == "test":
                self.assertFalse(records[0]["diagnostic_template_A"])
                self.assertTrue(records[1]["diagnostic_template_A"])

    def test_T06_forbidden_words(self):
        templates = load_templates()
        self.assertEqual(TEMPLATE_PATH.name, "templates_v07_s3_r2.json")
        original = load_templates(TEMPLATE_PATH.with_name("templates_v07_s3_r1.json"))
        differences = [(kind, tid) for kind in original for tid in original[kind]
                       if original[kind][tid] != templates[kind][tid]]
        self.assertEqual(differences, [("role_feint", "B2")])
        self.assertEqual(templates["role_feint"]["B2"], "随后抵近并进入设施{f}的警戒区，之后折返。")
        check_forbidden(templates)
        facts = extract_facts(labels(), scene())["facts"]
        for group in ("A", "B"):
            check_forbidden(render_description(facts, "x", group)["text"])
        contaminated = deepcopy(templates)
        contaminated["overview"]["A1"] += "天气"
        with self.assertRaisesRegex(P0ContractError, "Forbidden word"):
            render_description(facts, "x", "A", templates=contaminated)

    def test_T07_independent_fact_binding(self):
        value = labels()
        value["task_groups"]["task_group_01"]["assigned"]["execution_method"] = "area_search"
        record = render_description(extract_facts(value, scene())["facts"], "x", "A")
        self.assertTrue(verify_description(record, value, scene()))
        changed = deepcopy(value)
        changed["task_groups"]["task_group_01"]["observed"]["shared_coverage"]["coverage_fraction"] = .4
        with self.assertRaisesRegex(P0ContractError, "Fact binding mismatch"):
            verify_description(record, changed, scene())
        changed_record = deepcopy(record)
        changed_record["sentences"][0]["fact_refs"]["n"] = ["/task_groups"]
        with self.assertRaisesRegex(P0ContractError, "Fact binding mismatch"):
            verify_description(changed_record, value, scene())

    def test_T08_normalized_intervals_and_column_order(self):
        raw, task, source, truth = trajectories()
        anchors = compute_anchors(task, source, truth)
        self.assertEqual(anchors["members"], {
            "uav_01": {"release_s": 1., "t_c": 5., "visible_end": 6.},
            "uav_02": {"release_s": 2., "t_c": 6., "visible_end": 7.}})
        self.assertEqual((anchors["t0"], anchors["t1"], anchors["keep_start_index"], anchors["keep_end_index"]),
                         (1., 7., 10, 70))
        for order in ([0, 1], [1, 0]):
            permuted = dict(raw, x=raw["x"][:, order], agent_ids=[raw["agent_ids"][i] for i in order])
            result = normalized_view(permuted, anchors)
            self.assertEqual(result["t_s"][0], 0.)
            self.assertEqual(result["mask"].sum(axis=0).tolist(), [51, 51])
            self.assertTrue(np.all(result["x"][~result["mask"]] == 0))
            self.assertTrue(np.array_equal(result["x"][result["mask"]],
                                           permuted["x"][10:71][result["mask"]]))
            for col, aid in enumerate(result["agent_ids"]):
                visible = result["t_s"][result["mask"][:, col]] + anchors["t0"]
                self.assertEqual(visible[0], anchors["members"][aid]["release_s"])
                self.assertEqual(visible[-1] - anchors["members"][aid]["t_c"], 1.)
            first_agent = result["agent_ids"].index("uav_01")
            self.assertTrue(np.all(result["mask"][10:16, first_agent]))  # absolute t=2..2.5 mid-route dwell.

    def test_T09_normalization_errors(self):
        raw, task, source, truth = trajectories()
        bad = deepcopy(truth)
        bad["p"][-1, 0] = [100., 0., 0.]
        with self.assertRaisesRegex(P0ContractError, "Terminal continuous stop"):
            compute_anchors(task, source, bad)
        short = deepcopy(truth)
        short["v"][-11, 0] = [5., 0., 0.]  # leaves only 10 ok frames; 11 are required.
        with self.assertRaisesRegex(P0ContractError, "Terminal continuous stop"):
            compute_anchors(task, source, short)
        source["departure_delays_s"]["uav_01"] = .05
        with self.assertRaisesRegex(P0ContractError, "0.1 s grid"):
            compute_anchors(task, source, truth)

    def test_T10_loader_whitelist_and_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, task, source, truth = episode(root / "run" / "episode")
            row = {"path": "run/episode", "episode_key": "run/episode",
                   "episode_manifest_sha256": sha256(root / "run/episode/manifest.json"),
                   "anchors": compute_anchors(task, source, truth),
                   "intent": "transit", "family_id": "family_01", "split": "train",
                   **extract_facts(labels(), scene())}
            def inspect(value):
                if isinstance(value, dict):
                    self.assertTrue(set(value).isdisjoint({"intent", "role", "assigned", "target"}))
                    for child in value.values():
                        inspect(child)
                elif isinstance(value, list):
                    for child in value:
                        inspect(child)
            for view in ("raw", "normalized"):
                inputs = load_inputs(row, root, view)
                self.assertEqual(set(inputs), INPUT_KEYS)
                inspect(inputs["scene"])
            with (root / "descriptions.jsonl").open("w", encoding="utf-8") as stream:
                for record in description_variants(row["facts"], row["episode_key"], "train"):
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            self.assertEqual(set(load_targets(row, root, "A", 0)),
                             {"text", "slots", "intent", "family_id", "split"})
            with patch("task_v07.s3.loader.load_episode", return_value={"intent": "transit"}):
                with self.assertRaisesRegex(P0ContractError, "whitelist"):
                    load_inputs(row, root)

    def test_T11_fixed_family_split(self):
        for family in ("family_a", "family_b", "family_s15_79c93b22d09e8a7a"):
            u = int(hashlib.sha256(f"traj2language-v07-fe-split-v1:{family}".encode()).hexdigest()[:8], 16) / 2**32
            expected = "train" if u < .7 else "val" if u < .85 else "test"
            outcomes = [family_split(family) for _draw in range(3) for _intent in range(5) for _mode in range(2)]
            self.assertEqual(set(outcomes), {expected})

    def test_T12_hash_and_incomplete_run_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episode(root / "run" / "episode")
            row = {"path": "run/episode", "episode_key": "run/episode", "episode_manifest_sha256": "0" * 64}
            with self.assertRaisesRegex(P0ContractError, "manifest SHA256"):
                load_inputs(row, root, "raw")
            run = root / "incomplete"
            run.mkdir()
            for case in ("missing_manifest", "incomplete_progress", "active", "pending", "P0_STOP"):
                for p in run.iterdir():
                    p.unlink()  # confined to this test's own temporary directory.
                if case != "missing_manifest":
                    write_json(run / "manifest.json", {"retained_episodes": []})
                write_json(run / "progress.json", {"completed": 0 if case == "incomplete_progress" else 1,
                           "total": 1, "active": ["x"] if case == "active" else [],
                           "pending": ["x"] if case == "pending" else []})
                if case == "P0_STOP":
                    write_json(run / "P0_STOP.json", {})
                with self.subTest(case=case), self.assertRaises(RunNotReady):
                    read_run(root, "incomplete")
            (root / "existing").mkdir()
            with self.assertRaises(RunNotReady):
                exporter.export_runs(["unused"], "existing", root, root)
        with patch.object(exporter, "export_runs", side_effect=RunNotReady("incomplete")), patch("sys.stderr", io.StringIO()):
            self.assertEqual(exporter.main(["--runs", "fixture", "--export-id", "fixture"]), 3)


if __name__ == "__main__":
    unittest.main()
