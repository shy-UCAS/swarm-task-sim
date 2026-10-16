"""M3 geometry parameters; M2 settings remain owned by unified.config."""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "configs/generator/geometry_v07_r1.json"


@lru_cache(maxsize=1)
def _geometry():
    return json.loads(PATH.read_text(encoding="utf-8"))


def load_geometry():
    return deepcopy(_geometry())
