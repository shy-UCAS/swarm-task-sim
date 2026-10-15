"""Frozen criteria data, separate from planner/execution parameters."""
import json
from pathlib import Path

CRITERIA_PATH = Path(__file__).resolve().parents[1] / "configs/criteria/criteria_v07_r1.json"


def load_criteria():
    return json.loads(CRITERIA_PATH.read_text(encoding="utf-8"))


def quality_facts(minimum, restricted_count, outside_count):
    rules = load_criteria()["quality"]
    error = minimum is not None and minimum < rules["min_separation_error_m"]
    restricted = restricted_count > 0
    return {"status": rules["restricted_zone_entry"] if restricted else "generation_error" if error else "valid",
            "retained": not (error or restricted),
            "exclusion_reasons": (["minimum_separation_below_2m"] if error else []) + (["restricted_zone_entry"] if restricted else []),
            "minimum_separation_m": minimum, "separation_error_threshold_m": rules["min_separation_error_m"],
            "separation_affects_task_result": False, "hard_obstacle_sample_count": int(restricted_count),
            "outside_world_sample_count": int(outside_count)}
