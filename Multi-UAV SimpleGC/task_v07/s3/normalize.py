"""Remove only pre-release invisibility and the surplus final stop tail."""
import numpy as np

from ._common import P0ContractError


def _tick(seconds, context):
    value = float(seconds)
    if not np.isfinite(value):
        raise P0ContractError(f"Nonfinite grid time: {context}={seconds}")
    tick = round(value * 10)
    if abs(value - tick / 10) > 1e-6:
        raise P0ContractError(f"Not on the 0.1 s grid: {context}={seconds}")
    return tick * 100000


def compute_anchors(task, source, truth):
    time_us = np.asarray(truth["time_us"], dtype=np.int64)
    ids = [str(a) for a in truth["agent_ids"]]
    if not len(time_us) or np.any(np.diff(time_us) != 100000):
        raise P0ContractError("Truth is not a continuous 10 Hz grid")
    radius = task.get("stop_radius_m", task["terminal_radius_m"])
    speed = task.get("stop_speed_m_s", task["terminal_speed_m_s"])
    hold = task.get("stop_hold_s", task["terminal_hold_s"])
    hold_us = _tick(hold, "stop_hold_s")
    members = {}
    for j, agent in enumerate(ids):
        release = _tick(task["initial_settle_s"] + source["departure_delays_s"][agent], agent)
        endpoint = np.asarray(task["references"][agent]["points_enu_m"][-1], float)
        ok = ((np.linalg.norm(truth["p"][:, j] - endpoint, axis=1) <= radius)
              & (np.linalg.norm(truth["v"][:, j], axis=1) <= speed)
              & (time_us >= release))
        bad = np.flatnonzero(~ok)
        start = int(bad[-1] + 1) if len(bad) else 0
        if not ok[-1] or len(ok) - start < round(hold * 10) + 1:
            raise P0ContractError(f"Terminal continuous stop not observed: {agent}")
        tc = int(time_us[start])
        members[agent] = {"release_s": release / 1e6, "t_c": tc / 1e6,
                          "visible_end": (tc + hold_us) / 1e6}
    t0 = min(v["release_s"] for v in members.values())
    t1 = max(v["visible_end"] for v in members.values())
    take = np.flatnonzero((time_us >= _tick(t0, "t0")) & (time_us <= _tick(t1, "t1")))
    if not len(take) or time_us[take[0]] != _tick(t0, "t0") or time_us[take[-1]] != _tick(t1, "t1"):
        raise P0ContractError("Normalization endpoints are not observed")
    return {"members": members, "t0": t0, "t1": t1, "stop_hold_s": hold,
            "keep_start_index": int(take[0]), "keep_end_index": int(take[-1])}


def normalized_view(raw, anchors):
    ids = list(raw["agent_ids"])
    if set(ids) != set(anchors["members"]):
        raise P0ContractError("Anchor/input member identities differ")
    full_ticks = np.rint(np.asarray(raw["t_s"]) * 1e6).astype(np.int64)
    first, last = anchors["keep_start_index"], anchors["keep_end_index"]
    if not 0 <= first <= last < len(full_ticks):
        raise P0ContractError("Invalid stored keep indices")
    ticks = full_ticks[first:last + 1]
    if (ticks[0] != _tick(anchors["t0"], "t0") or ticks[-1] != _tick(anchors["t1"], "t1")
            or np.any(np.diff(ticks) != 100000)):
        raise P0ContractError("Stored normalization window differs from input grid")
    original = raw["x"][first:last + 1]
    x = original.copy()
    mask = np.zeros(x.shape[:2], dtype=bool)
    releases, ends = [], []
    for j, agent in enumerate(ids):
        anchor = anchors["members"][agent]
        release = _tick(anchor["release_s"], agent + ".release")
        tc = _tick(anchor["t_c"], agent + ".t_c")
        end = _tick(anchor["visible_end"], agent + ".end")
        if tc < release or end - tc != _tick(anchors["stop_hold_s"], "stop_hold"):
            raise P0ContractError(f"Stored terminal visibility changed: {agent}")
        releases.append(release)
        ends.append(end)
        mask[:, j] = (ticks >= release) & (ticks <= end)
        visible_ticks = ticks[mask[:, j]]
        if (not len(visible_ticks) or visible_ticks[0] != release
                or visible_ticks[-1] != end or not np.any(ticks == tc)):
            raise P0ContractError(f"Incomplete visible interval: {agent}")
    if min(releases) != ticks[0] or max(ends) != ticks[-1]:
        raise P0ContractError("Episode window does not match member anchors")
    x[~mask] = 0.0
    if not np.array_equal(x[mask], original[mask]):
        raise P0ContractError("Visible observations changed")
    return {"x": x, "mask": mask, "t_s": (ticks - ticks[0]) / 1e6,
            "agent_ids": ids, "scene": raw["scene"]}
