"""Fixed D0b B2 reference policy; candidate only, without parameter search."""
import hashlib
import json
import math
from pathlib import Path
from .contracts import M2Config

POLICY = "continuous_route_v3"
CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs/fast_dynamics/m3_r3_candidate_v1.json"
CONFIG_SHA256 = "0fe3efff6f97ed88c665374d0280aef571b92399ac3711184f13e5c6a3de3b30"


def cut_distance(gate, angle, before, after):
    epsilon = .5 * gate
    m = (23./48.) * math.sin(angle/2.)
    return min(epsilon/m, .45*before, .45*after)


def candidate_config():
    raw = CONFIG_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CONFIG_SHA256:
        raise ValueError("M3 r3 candidate configuration hash mismatch")
    result = M2Config.from_dict(json.loads(raw))
    if result.reference.policy != POLICY:
        raise ValueError("M3 r3 candidate policy mismatch")
    return result
