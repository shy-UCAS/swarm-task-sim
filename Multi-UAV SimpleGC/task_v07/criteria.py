"""Frozen criteria data, separate from planner/execution parameters."""
import json
from pathlib import Path

CRITERIA_PATH = Path(__file__).resolve().parents[1] / "configs/criteria/criteria_v07_r1.json"


def load_criteria():
    return json.loads(CRITERIA_PATH.read_text(encoding="utf-8"))
