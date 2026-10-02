"""WP-L L03/L05/L06: safe Chinese descriptions and independent wording split."""

import copy
import unittest

from swarm_sim.language_templates_v0 import (_WORDINGS, generate_descriptions,
                                             template_inventory,
                                             validate_description)


def _facts(intent="reconnaissance", *, pattern=None, return_required=True,
           result=None, conditions=None):
    if pattern is None:
        pattern = "parallel_strips" if intent == "reconnaissance" else "perimeter_loop"
    if conditions is None:
        conditions = ({"coverage": True, "return": True} if intent == "reconnaissance"
                      else {"visits": True, "max_gap": True, "return": True})
    if result is None:
        values = list(conditions.values())
        result = False if False in values else (True if all(value is True for value in values) else None)
    return dict(facts_version="observer_facts_v0",
                labels=dict(assigned_intent=intent, return_required=return_required,
                            mission_result=dict(success=result, conditions=conditions)),
                observed=dict(num_uavs=3, entry_side="south", observed_pattern=pattern,
                              scan_orientation="north_south" if intent == "reconnaissance" else None,
                              loop_direction="ccw" if intent == "patrol" else None,
                              per_agent_laps_observed=[2, 2, 2] if intent == "patrol" else None,
                              return_observed=True, max_revisit_gap_s=13.1 if intent == "patrol" else None),
                model_metrics=dict(coverage_ratio=.875 if intent == "reconnaissance" else None,
                                   coverage_model="ideal_horizontal_disk_v1, r=8m" if intent == "reconnaissance" else None),
                channel_check=dict(fields_checked=[], disagreements=[]),
                segments=[], events=[], provenance={})


class LanguageTemplateTests(unittest.TestCase):
    def test_L03_coverage_pass_and_return_failure_are_separate(self):
        facts = _facts(conditions={"coverage": True, "return": False}, result=False)
        facts["observed"]["return_observed"] = False
        descriptions = generate_descriptions(facts, "episode1", "train", 42)
        self.assertEqual(len(descriptions), 4)
        for description in descriptions:
            ids = [item["template_id"] for item in description["sentences"]]
            self.assertTrue(any(key.startswith("T3.coverage_pass_ratio") for key in ids))
            self.assertTrue(any(key.startswith("T3.return_fail") for key in ids))
            self.assertFalse(any("T3.coverage_fail" in key for key in ids))
            self.assertIn("87.5%", description["text"])
            self.assertIn("观察模型", description["text"])

    def test_L03_unclear_pattern_has_neutral_intent(self):
        facts = _facts(pattern="unclear")
        descriptions = generate_descriptions(facts, "episode2", "test", 7)
        for description in descriptions:
            self.assertTrue(any(item["template_id"].startswith("T2.neutral")
                                for item in description["sentences"]))
            self.assertTrue(any(item["template_id"].startswith("T5.neutral")
                                for item in description["sentences"]))
            self.assertNotIn("符合区域侦察", description["text"])

    def test_L05_inventory_is_disjoint_and_generation_reproducible(self):
        inventory = template_inventory()
        self.assertTrue(all(len(group["train"]) >= 3 and group["test"]
                            for group in inventory.values()))
        self.assertTrue(all(not set(group["train"]) & set(group["test"])
                            for group in inventory.values()))
        temporal_markers = ("起初", "任务开始时", "飞行初段", "随后", "主要飞行阶段",
                            "结束时", "结束后", "末段", "结束前", "此后", "到目前为止")
        for key, wordings in _WORDINGS.items():
            with self.subTest(template_branch=key):
                self.assertEqual(len(wordings), 4)
                self.assertTrue(any(marker in wording for wording in wordings
                                    for marker in temporal_markers))
        facts = _facts("patrol")
        first = generate_descriptions(facts, "ep_patrol", "validation", 789)
        second = generate_descriptions(facts, "ep_patrol", "validation", 789)
        self.assertEqual(first, second)
        self.assertEqual([d["template_partition"] for d in first],
                         ["train", "train", "train", "test"])
        self.assertEqual(len({d["text"] for d in first[:3]}), 3)
        self.assertTrue(all(d["episode_split"] == "validation" for d in first))
        for description in first:
            self.assertEqual(description["episode_id"], "ep_patrol")
            self.assertEqual(description["facts_version"], "observer_facts_v0")
            self.assertEqual(description["template_version"], "templates_zh_v0")
            self.assertTrue(all(sentence["fact_ids"] is not None for sentence in description["sentences"]))
            self.assertTrue(validate_description(description, facts)[0])
            for sentence in description["sentences"]:
                self.assertIn(sentence["template_id"], inventory[sentence["template_id"].split(".")[0] + "." + sentence["template_id"].split(".")[1]][description["template_partition"]])

    def test_L06_numeric_intent_internal_and_fact_reference_edits_rejected(self):
        facts = _facts()
        original = generate_descriptions(facts, "episode1", "train", 42)[0]
        variants = []
        numeric = copy.deepcopy(original)
        numeric["sentences"][2]["text"] = numeric["sentences"][2]["text"].replace("87.5%", "99.9%")
        numeric["text"] = "".join(item["text"] for item in numeric["sentences"])
        variants.append(numeric)
        intent = copy.deepcopy(original)
        intent["sentences"][-1]["text"] = "整体行为符合边界巡逻警戒的特征。"
        intent["text"] = "".join(item["text"] for item in intent["sentences"])
        variants.append(intent)
        internal = copy.deepcopy(original)
        internal["sentences"][0]["text"] += "uav_01 经过条带编号 3。"
        internal["text"] = "".join(item["text"] for item in internal["sentences"])
        variants.append(internal)
        reference = copy.deepcopy(original)
        reference["sentences"][0]["fact_ids"] = ["observed.max_revisit_gap_s"]
        variants.append(reference)
        for variant in variants:
            with self.subTest(text=variant["text"][:20]):
                accepted, reasons = validate_description(variant, facts)
                self.assertFalse(accepted)
                self.assertTrue(reasons)

    def test_L04_disagreement_withholds_gap_and_laps(self):
        facts = _facts("patrol")
        facts["channel_check"]["disagreements"] = [
            dict(field="max_revisit_gap_s", sim=13.1, fcu=15.5, reason="outside_tolerance"),
            dict(field="per_agent_laps_observed", sim=[2, 2, 2], fcu=[2, 1, 2], reason="different_laps"),
        ]
        facts["observed"]["max_revisit_gap_s"] = None
        facts["observed"]["per_agent_laps_observed"] = None
        descriptions = generate_descriptions(facts, "patrol1", "test", 8)
        for description in descriptions:
            self.assertNotIn("13.1", description["text"])
            self.assertFalse(any(item["template_id"].startswith("T6.laps")
                                 for item in description["sentences"]))
            self.assertFalse(any("observed.max_revisit_gap_s" in item["fact_ids"]
                                 for item in description["sentences"]))
            self.assertTrue(validate_description(description, facts)[0])

    def test_L02_return_observed_is_not_return_requirement(self):
        facts = _facts(return_required=False)
        facts["observed"]["return_observed"] = False
        descriptions = generate_descriptions(facts, "no_return", "train", 1)
        for description in descriptions:
            ids = [sentence["template_id"] for sentence in description["sentences"]]
            self.assertTrue(any(key.startswith("T4.return_false") for key in ids))
            self.assertFalse(any(key.startswith("T3.return_") for key in ids))
            self.assertNotIn("最后返回", description["text"])

    def test_all_observed_values_can_be_withheld(self):
        facts = _facts("patrol")
        fields = ("num_uavs", "entry_side", "observed_pattern", "loop_direction",
                  "per_agent_laps_observed", "return_observed", "max_revisit_gap_s")
        facts["channel_check"]["disagreements"] = [dict(field=field, sim="x", fcu="y", reason="mismatch")
                                                      for field in fields]
        for field in fields:
            facts["observed"][field] = None
        descriptions = generate_descriptions(facts, "unknowns", "test", 1)
        self.assertEqual(len(descriptions), 4)
        self.assertTrue(all(validate_description(description, facts)[0] for description in descriptions))
        for description in descriptions:
            referenced = [fact for sentence in description["sentences"] for fact in sentence["fact_ids"]]
            self.assertFalse(any(f"observed.{field}" in referenced for field in fields))


if __name__ == "__main__":
    unittest.main()
