"""Frozen M2 generator parameters, separate from the M1 criteria configuration."""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs/generator/generator_v07_r1.json"


@lru_cache(maxsize=1)
def _configuration():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))


def load_generator():
    return deepcopy(_configuration())


def stop_fields():
    return {"stop_" + key: value for key, value in load_generator()["stop"].items()}
