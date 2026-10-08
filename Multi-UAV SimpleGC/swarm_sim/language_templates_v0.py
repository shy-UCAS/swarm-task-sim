"""Chinese descriptions derived only from versioned observer facts.

Every emitted sentence has an immutable template ID and the exact fact paths
used to render it.  Validation rebuilds the sentence from the supplied facts,
so edited numbers, enums, unsupported claims and disputed facts are rejected.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any


TEMPLATE_VERSION = "templates_zh_v0"
FACTS_VERSION = "observer_facts_v0"
V06_FACTS_VERSION = "observer_facts_v06"
V06_TEMPLATE_VERSION = "templates_zh_v06"

# The fourth wording of each semantic branch is reserved for test.  Time
# expressions are deliberately present in every branch, including failures.
_WORDINGS = {
    "T2.direct": (
        "随后，轨迹从区域一侧直穿至对侧。",
        "在主要飞行阶段，可见轨迹直穿目标区域。",
        "接近区域后，飞行路径呈直穿形态。",
        "此后，轨迹以直穿方式经过目标区域并到达对侧。",
    ),
    "T3.passage_pass": (
        "按轨迹核验，已从一侧进入并从对侧离开，区域内未见停留或绕圈。",
        "到通过阶段结束时，轨迹满足直线进入、对侧离开且区域内不停留、不绕圈的条件。",
        "依据轨迹，区域内的直线通过和对侧离开条件已满足，未见停留或绕圈。",
        "通过阶段结束后核对轨迹，机群完成了一次区域内无停留、无绕圈的直线通过。",
    ),
    "T3.passage_fail": (
        "按轨迹核验，直穿区域的条件未全部满足。",
        "到通过阶段结束时，轨迹未达到全部直穿条件。",
        "依据轨迹，区域直穿的核验条件尚未全部达标。",
        "通过阶段结束后核对轨迹，仍有直穿条件未通过。",
    ),
    "T3.passage_unknown": (
        "现有轨迹尚不足以确认区域直穿条件。",
        "到通过阶段结束时，区域直穿条件仍缺少完整证据。",
        "依据现有轨迹，直穿区域的结果尚不能确定。",
        "通过阶段结束后，直穿条件仍无法完整核验。",
    ),
    "T5.rapid_match": (
        "整体行为符合区域快速通过的特征。",
        "从随后形成的轨迹看，整体行为符合区域快速通过特征。",
        "综合轨迹表现，可将其判断为符合区域快速通过特征。",
        "到主要阶段结束时，整体轨迹呈现区域快速通过特征。",
    ),
    "T1.side": (
        "由 {n} 架无人机组成的机群整体从目标区域{side}侧接近。",
        "起初，{n} 架无人机组成的机群整体由目标区域{side}侧靠近。",
        "任务开始时，可见 {n} 架无人机组成的机群整体从目标区域{side}侧进入。",
        "在飞行初段，{n} 架无人机组成的机群整体自目标区域{side}侧抵近。",
    ),
    "T1.count": (
        "该记录包含 {n} 架无人机的飞行轨迹。",
        "起初，可见 {n} 架无人机的飞行轨迹。",
        "任务开始时，记录中有 {n} 架无人机的轨迹。",
        "在飞行初段，记录包含 {n} 架无人机的轨迹。",
    ),
    "T1.generic": (
        "该记录包含飞行轨迹。",
        "起初，记录中已有飞行轨迹。",
        "任务开始时，轨迹记录已开始。",
        "在飞行初段，记录中可见轨迹。",
    ),
    "T2.parallel_dir": (
        "随后，轨迹沿{orientation}方向呈平行往返扫描。",
        "在主要飞行阶段，可见沿{orientation}方向的平行往返轨迹。",
        "接近区域后，飞行路径沿{orientation}方向多次平行折返。",
        "此后，轨迹以{orientation}方向的平行往返形式经过区域。",
    ),
    "T2.parallel": (
        "随后，轨迹呈平行往返扫描。",
        "在主要飞行阶段，可见平行往返轨迹。",
        "接近区域后，飞行路径多次平行折返。",
        "此后，轨迹以平行往返形式经过区域。",
    ),
    "T2.loop_dir": (
        "随后，轨迹沿目标区域边界{direction}环绕。",
        "在主要飞行阶段，可见沿目标区域边界{direction}绕行。",
        "接近区域后，飞行路径沿边界{direction}循环。",
        "此后，轨迹围绕目标区域边界{direction}延伸。",
    ),
    "T2.loop": (
        "随后，轨迹沿目标区域边界环绕。",
        "在主要飞行阶段，可见沿目标区域边界绕行。",
        "接近区域后，飞行路径沿边界循环。",
        "此后，轨迹围绕目标区域边界延伸。",
    ),
    "T2.neutral": (
        "主要阶段的轨迹模式尚未明确归类。",
        "到主要阶段结束时，轨迹模式仍不明确。",
        "在主要飞行阶段，轨迹模式尚不能确定。",
        "此后，主要阶段的轨迹模式仍待确认。",
    ),
    "T3.coverage_pass_ratio": (
        "按{model}估算，区域覆盖率约为 {ratio}。",
        "到观察阶段结束时，依{model}估算的区域覆盖率约为 {ratio}。",
        "依据{model}计算，区域覆盖率约为 {ratio}。",
        "完成观察后，按{model}得到的区域覆盖率约为 {ratio}。",
    ),
    "T3.coverage_pass": (
        "按设定的仿真观察模型核验，区域覆盖条件已满足。",
        "到观察阶段结束时，仿真观察模型判定覆盖达到要求。",
        "依据设定的仿真观察模型，覆盖条件得到满足。",
        "完成观察后，仿真观察模型给出覆盖达标的判定。",
    ),
    "T3.coverage_fail": (
        "按设定的仿真观察模型核验，区域覆盖未达到要求。",
        "到观察阶段结束时，仿真观察模型判定覆盖不足。",
        "依据设定的仿真观察模型，覆盖条件未得到满足。",
        "完成观察后，仿真观察模型给出覆盖未达标的判定。",
    ),
    "T3.coverage_unknown": (
        "按设定的仿真观察模型，区域覆盖结果尚不能确定。",
        "到观察阶段结束时，仿真观察模型仍无法确认覆盖结果。",
        "依据设定的仿真观察模型，覆盖条件目前未能判定。",
        "完成观察后，仿真观察模型的覆盖判定仍不确定。",
    ),
    "T3.visits_pass": (
        "按轨迹核验，边界各段的经过次数达到任务要求。",
        "到巡逻阶段结束时，边界各段的经过次数满足要求。",
        "依据轨迹统计，边界各段的经过次数已达标。",
        "巡逻结束后核对轨迹，各段经过次数符合设定条件。",
    ),
    "T3.visits_fail": (
        "按轨迹核验，边界部分区段的经过次数不足。",
        "到巡逻阶段结束时，边界各段的经过次数未全部达标。",
        "依据轨迹统计，边界经过次数没有满足设定要求。",
        "巡逻结束后核对轨迹，仍有区段经过次数不足。",
    ),
    "T3.visits_unknown": (
        "边界各段的经过次数尚不能确认。",
        "到巡逻阶段结束时，各段经过次数仍无法完整核验。",
        "依据现有轨迹，边界经过次数条件尚未确定。",
        "巡逻结束后，各段经过次数仍缺少完整证据。",
    ),
    "T3.gap_pass_number": (
        "按轨迹核验，最长重访间隔约 {gap} 秒，满足设定条件。",
        "到巡逻阶段结束时，最长重访间隔约 {gap} 秒，符合要求。",
        "依据轨迹统计，约 {gap} 秒的最长重访间隔处于设定上限内。",
        "巡逻结束后核对轨迹，最长重访间隔约 {gap} 秒且达标。",
    ),
    "T3.gap_pass": (
        "按轨迹核验，重访间隔满足设定条件。",
        "到巡逻阶段结束时，重访间隔符合要求。",
        "依据轨迹统计，重访间隔处于设定上限内。",
        "巡逻结束后核对轨迹，重访间隔条件已达标。",
    ),
    "T3.gap_fail_number": (
        "按轨迹核验，最长重访间隔约 {gap} 秒，超过设定上限。",
        "到巡逻阶段结束时，约 {gap} 秒的最长重访间隔未达标。",
        "依据轨迹统计，最长重访间隔约 {gap} 秒且超出要求。",
        "巡逻结束后核对轨迹，约 {gap} 秒的最长重访间隔过长。",
    ),
    "T3.gap_fail": (
        "按轨迹核验，重访间隔超过设定上限。",
        "到巡逻阶段结束时，重访间隔未达到要求。",
        "依据轨迹统计，重访间隔条件未得到满足。",
        "巡逻结束后核对轨迹，重访间隔仍超过上限。",
    ),
    "T3.gap_unknown": (
        "重访间隔条件尚不能确认。",
        "到巡逻阶段结束时，最长重访间隔仍无法完整核验。",
        "依据现有轨迹，重访间隔结果尚未确定。",
        "巡逻结束后，重访间隔仍缺少完整证据。",
    ),
    "T3.return_pass": (
        "任务设定的返航条件已经满足。",
        "到任务结束时，设定的返航条件得到满足。",
        "经核验，任务的返航条件已达标。",
        "飞行结束后，返航条件的核验结果为通过。",
    ),
    "T3.return_fail": (
        "任务设定的返航条件没有满足。",
        "到任务结束时，设定的返航条件仍未达标。",
        "经核验，任务的返航条件未得到满足。",
        "飞行结束后，返航条件的核验结果为未通过。",
    ),
    "T3.return_unknown": (
        "任务设定的返航条件尚不能确认。",
        "到任务结束时，返航条件仍缺少完整核验结果。",
        "经核验，任务的返航条件目前未确定。",
        "飞行结束后，返航条件的结果仍不明确。",
    ),
    "T4.return_true": (
        "最后，轨迹返回出发位置。",
        "在飞行末段，轨迹回到了出发位置。",
        "任务结束前，可见轨迹进入起点附近。",
        "此后，轨迹最终回到出发位置附近。",
    ),
    "T4.return_false": (
        "最后，机群没有全部返回各自出发位置。",
        "在飞行末段，机群未全部回到各自出发位置。",
        "任务结束前，至少一条轨迹未进入对应起点附近。",
        "此后，机群最终仍未全部返回出发位置附近。",
    ),
    "T5.recon_match": (
        "整体行为符合区域侦察的特征。",
        "从随后形成的轨迹看，整体行为符合区域侦察特征。",
        "综合轨迹表现，可将其判断为符合区域侦察特征。",
        "到主要阶段结束时，整体轨迹呈现区域侦察特征。",
    ),
    "T5.patrol_match": (
        "整体行为符合边界巡逻警戒的特征。",
        "从随后形成的轨迹看，整体行为符合边界巡逻警戒特征。",
        "综合轨迹表现，可将其判断为符合边界巡逻警戒特征。",
        "到主要阶段结束时，整体轨迹呈现边界巡逻警戒特征。",
    ),
    "T5.neutral": (
        "目前的轨迹尚不足以判断其意图。",
        "到目前为止，轨迹还不足以支持意图判断。",
        "仅凭现有轨迹，尚不能可靠判断意图。",
        "在当前观察范围内，意图判断仍不明确。",
    ),
    "T6.laps": (
        "按轨迹进度核验，各机约完成 {laps} 圈边界绕行。",
        "到主要阶段结束时，各机约完成 {laps} 圈边界绕行。",
        "依据轨迹进度，各机约绕行边界 {laps} 圈。",
        "完成主要阶段后，轨迹显示各机约绕行 {laps} 圈。",
    ),
}

_CARDINAL = {"east": "东", "south": "南", "west": "西", "north": "北"}
_ORIENTATION = {"east_west": "东西", "north_south": "南北"}
_DIRECTION = {"cw": "顺时针", "ccw": "逆时针"}
_INTERNAL = re.compile(
    r"uav[_-]|\bstrip\b|条带编号|航点|规划器|执行事件|任务\s*(?:ID|编号)|"
    r"planner|semantic_plan|execution_events?|assignment|partition_id",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _SentencePlan:
    key: str
    fact_ids: tuple[str, ...]
    slots: dict[str, Any]


def template_inventory() -> dict[str, dict[str, list[str]]]:
    """Return immutable-in-practice IDs for audit and split-disjoint checks."""
    return {key: {"train": [f"{key}.train.{i}" for i in range(1, 4)],
                  "test": [f"{key}.test.1"]} for key in sorted(_WORDINGS)}


def _disagreements(facts: dict[str, Any]) -> set[str]:
    found = set()
    for item in facts.get("channel_check", {}).get("disagreements", []):
        if isinstance(item, str):
            found.add(item)
        elif isinstance(item, dict):
            field = next((item.get(key) for key in ("field", "fact_id", "path", "name")
                          if isinstance(item.get(key), str)), None)
            if field:
                found.add(field)
    return found


def _disputed(path: str, disagreements: set[str]) -> bool:
    return path in disagreements or path.rsplit(".", 1)[-1] in disagreements


def _available_observed(facts: dict[str, Any], name: str, disagreements: set[str]) -> Any:
    path = f"observed.{name}"
    return None if _disputed(path, disagreements) else facts.get("observed", {}).get(name)


def _checked_result(facts: dict[str, Any]) -> tuple[str, bool, dict[str, bool | None]]:
    if facts.get("facts_version") not in (FACTS_VERSION, V06_FACTS_VERSION):
        raise ValueError("unsupported observer facts version")
    labels = facts.get("labels")
    if not isinstance(labels, dict) or labels.get("assigned_intent") not in ("reconnaissance", "patrol", "rapid_passage"):
        raise ValueError("unsupported or missing assigned intent")
    required = labels.get("return_required")
    if type(required) is not bool:
        raise ValueError("return_required must be boolean")
    result = labels.get("mission_result")
    if not isinstance(result, dict) or type(result.get("success")) not in (bool, type(None)):
        raise ValueError("mission_result is missing")
    raw = result.get("conditions")
    if not isinstance(raw, dict):
        raise ValueError("mission_result.conditions is missing")
    conditions = dict(raw)
    if "return" not in conditions and "return_to_launch" in conditions:
        conditions["return"] = conditions.pop("return_to_launch")
    patrol_v2 = facts.get("provenance", {}).get("versions", {}).get("semantic_validation_version") in (
        "multi_intent_validation_v3", "multi_intent_validation_v06")
    needed = ({"coverage", "return"} if labels["assigned_intent"] == "reconnaissance"
              else {"entered", "opposite_exit", "straight", "no_dwell", "no_loop", "return"}
              if labels["assigned_intent"] == "rapid_passage"
              else {"max_gap", "return"} if patrol_v2 else {"visits", "max_gap", "return"})
    if labels["assigned_intent"] == "patrol" and patrol_v2 and "visits" in conditions:
        raise ValueError("perimeter_revisit_v2 cannot use visits as a success condition")
    if not needed <= conditions.keys() or any(type(conditions[name]) not in (bool, type(None)) for name in needed):
        raise ValueError("mission_result has missing or invalid subconditions")
    values = [conditions[name] for name in sorted(needed)]
    expected = False if False in values else (True if all(value is True for value in values) else None)
    if result["success"] is not expected:
        raise ValueError("mission_result contradicts its subconditions")
    return labels["assigned_intent"], required, conditions


def _plans(facts: dict[str, Any]) -> list[_SentencePlan]:
    intent, return_required, conditions = _checked_result(facts)
    disagreements = _disagreements(facts)
    plans: list[_SentencePlan] = []
    count = _available_observed(facts, "num_uavs", disagreements)
    side = _available_observed(facts, "entry_side", disagreements)
    if type(count) is int and count > 0 and side in _CARDINAL:
        plans.append(_SentencePlan("T1.side", ("observed.num_uavs", "observed.entry_side"),
                                   {"n": count, "side": _CARDINAL[side]}))
    elif type(count) is int and count > 0:
        plans.append(_SentencePlan("T1.count", ("observed.num_uavs",), {"n": count}))
    else:
        plans.append(_SentencePlan("T1.generic", (), {}))

    pattern = _available_observed(facts, "observed_pattern", disagreements)
    orientation = _available_observed(facts, "scan_orientation", disagreements)
    direction = _available_observed(facts, "loop_direction", disagreements)
    if pattern == "parallel_strips":
        if orientation in _ORIENTATION:
            plans.append(_SentencePlan("T2.parallel_dir", ("observed.observed_pattern", "observed.scan_orientation"),
                                       {"orientation": _ORIENTATION[orientation]}))
        else:
            plans.append(_SentencePlan("T2.parallel", ("observed.observed_pattern",), {}))
    elif pattern == "perimeter_loop":
        if direction in _DIRECTION:
            plans.append(_SentencePlan("T2.loop_dir", ("observed.observed_pattern", "observed.loop_direction"),
                                       {"direction": _DIRECTION[direction]}))
        else:
            plans.append(_SentencePlan("T2.loop", ("observed.observed_pattern",), {}))
    elif pattern == "direct_passage" and facts.get("facts_version") == V06_FACTS_VERSION:
        plans.append(_SentencePlan("T2.direct", ("observed.observed_pattern",), {}))
    else:
        plans.append(_SentencePlan("T2.neutral", ("observed.observed_pattern",) if pattern == "unclear" else (), {}))

    if intent == "reconnaissance":
        coverage = conditions["coverage"]
        condition_id = "labels.mission_result.conditions.coverage"
        ratio = facts.get("model_metrics", {}).get("coverage_ratio")
        model = facts.get("model_metrics", {}).get("coverage_model")
        if coverage is True and isinstance(ratio, (int, float)) and not isinstance(ratio, bool) and math.isfinite(ratio) and 0 <= ratio <= 1 and isinstance(model, str) and model and not any(_disputed(field, disagreements) for field in ("model_metrics.coverage_ratio", "model_metrics.coverage_model")):
            model_text = ("理想水平圆盘观察模型" if "ideal_horizontal_disk" in model
                          else "设定的仿真观察模型")
            plans.append(_SentencePlan("T3.coverage_pass_ratio", (condition_id, "model_metrics.coverage_ratio", "model_metrics.coverage_model"),
                                       {"model": model_text, "ratio": f"{ratio * 100:.1f}%"}))
        else:
            key = "T3.coverage_pass" if coverage is True else "T3.coverage_fail" if coverage is False else "T3.coverage_unknown"
            plans.append(_SentencePlan(key, (condition_id,), {}))
    elif intent == "rapid_passage":
        names = ("entered", "opposite_exit", "straight", "no_dwell", "no_loop")
        values = [conditions[name] for name in names]
        passed = False if False in values else True if all(value is True for value in values) else None
        key = "T3.passage_pass" if passed is True else "T3.passage_fail" if passed is False else "T3.passage_unknown"
        plans.append(_SentencePlan(key, tuple(f"labels.mission_result.conditions.{name}" for name in names), {}))
    else:
        if "visits" in conditions:
            visits = conditions["visits"]
            key = "T3.visits_pass" if visits is True else "T3.visits_fail" if visits is False else "T3.visits_unknown"
            plans.append(_SentencePlan(key, ("labels.mission_result.conditions.visits",), {}))
        gap_result = conditions["max_gap"]
        gap = _available_observed(facts, "max_revisit_gap_s", disagreements)
        gap_available = isinstance(gap, (int, float)) and not isinstance(gap, bool) and math.isfinite(gap) and gap >= 0
        if gap_result is None:
            plans.append(_SentencePlan("T3.gap_unknown", ("labels.mission_result.conditions.max_gap",), {}))
        elif gap_available:
            key = "T3.gap_pass_number" if gap_result is True else "T3.gap_fail_number"
            plans.append(_SentencePlan(key, ("labels.mission_result.conditions.max_gap", "observed.max_revisit_gap_s"),
                                       {"gap": f"{gap:.1f}"}))
        else:
            key = "T3.gap_pass" if gap_result is True else "T3.gap_fail"
            plans.append(_SentencePlan(key, ("labels.mission_result.conditions.max_gap",), {}))

    if return_required:
        returned = conditions["return"]
        key = "T3.return_pass" if returned is True else "T3.return_fail" if returned is False else "T3.return_unknown"
        plans.append(_SentencePlan(key, ("labels.return_required", "labels.mission_result.conditions.return"), {}))

    observed_return = _available_observed(facts, "return_observed", disagreements)
    if type(observed_return) is bool:
        plans.append(_SentencePlan("T4.return_true" if observed_return else "T4.return_false",
                                   ("observed.return_observed",), {}))

    expected = {"reconnaissance": "parallel_strips", "patrol": "perimeter_loop", "rapid_passage": "direct_passage"}[intent]
    if pattern == expected:
        key = {"reconnaissance": "T5.recon_match", "patrol": "T5.patrol_match", "rapid_passage": "T5.rapid_match"}[intent]
        plans.append(_SentencePlan(key,
                                   ("labels.assigned_intent", "observed.observed_pattern"), {}))
    else:
        plans.append(_SentencePlan("T5.neutral", ("observed.observed_pattern",) if pattern == "unclear" else (), {}))

    laps = _available_observed(facts, "per_agent_laps_observed", disagreements)
    if (intent == "patrol" and pattern == "perimeter_loop" and isinstance(laps, list) and laps
            and all(type(value) is int and value >= 0 for value in laps) and len(set(laps)) == 1):
        plans.append(_SentencePlan("T6.laps", ("observed.per_agent_laps_observed",), {"laps": laps[0]}))
    return plans


def _template_id(key: str, partition: str, index: int) -> str:
    return f"{key}.{partition}.{index + 1}"


def _template_lookup(template_id: str) -> tuple[str, str, int] | None:
    for key in _WORDINGS:
        for index in range(4):
            partition = "test" if index == 3 else "train"
            if template_id == _template_id(key, partition, 0 if index == 3 else index):
                return key, partition, index
    return None


def _render(plan: _SentencePlan, index: int) -> str:
    return _WORDINGS[plan.key][index].format(**plan.slots)


def _offset(seed: Any, episode_id: str, key: str) -> int:
    data = f"{seed!r}|{episode_id}|{key}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(data).digest()[:8], "big") % 3


def validate_description(description: dict[str, Any], facts: dict[str, Any]) -> tuple[bool, list[str]]:
    """Strictly validate one description against its provenance and facts."""
    errors: list[str] = []
    try:
        plans = _plans(facts)
    except (TypeError, ValueError, KeyError) as exc:
        return False, [f"invalid_facts:{exc}"]
    if not isinstance(description, dict):
        return False, ["description_not_object"]
    if description.get("facts_version") != facts.get("facts_version"):
        errors.append("facts_version_mismatch")
    version = V06_TEMPLATE_VERSION if facts.get("facts_version") == V06_FACTS_VERSION else TEMPLATE_VERSION
    if description.get("template_version") != version:
        errors.append("template_version_mismatch")
    partition = description.get("template_partition")
    if partition not in ("train", "test"):
        errors.append("invalid_template_partition")
    if not isinstance(description.get("episode_split"), str) or not description["episode_split"]:
        errors.append("missing_episode_split")
    if not isinstance(description.get("episode_id"), str) or not description["episode_id"]:
        errors.append("missing_episode_id")
    sentences = description.get("sentences")
    if not isinstance(sentences, list) or len(sentences) != len(plans):
        return False, errors + ["sentence_inventory_mismatch"]
    disagreements = _disagreements(facts)
    rendered = []
    for ordinal, (sentence, plan) in enumerate(zip(sentences, plans)):
        if not isinstance(sentence, dict):
            errors.append(f"sentence_{ordinal}_not_object")
            continue
        template_id = sentence.get("template_id")
        lookup = _template_lookup(template_id) if isinstance(template_id, str) else None
        if lookup is None or lookup[0] != plan.key:
            errors.append(f"sentence_{ordinal}_unsupported_template")
            continue
        key, template_partition, index = lookup
        if template_partition != partition:
            errors.append(f"sentence_{ordinal}_wrong_partition")
        expected = _render(plan, index)
        if sentence.get("text") != expected:
            errors.append(f"sentence_{ordinal}_unsupported_claim")
        if sentence.get("fact_ids") != list(plan.fact_ids):
            errors.append(f"sentence_{ordinal}_fact_reference_mismatch")
        for path in sentence.get("fact_ids", []) if isinstance(sentence.get("fact_ids"), list) else []:
            if not isinstance(path, str) or _disputed(path, disagreements):
                errors.append(f"sentence_{ordinal}_disputed_fact")
        if isinstance(sentence.get("text"), str) and _INTERNAL.search(sentence["text"]):
            errors.append(f"sentence_{ordinal}_internal_information")
        rendered.append(sentence.get("text"))
    text = description.get("text")
    if text != "".join(item for item in rendered if isinstance(item, str)):
        errors.append("description_text_mismatch")
    if not isinstance(text, str) or _INTERNAL.search(text):
        errors.append("description_internal_information")
    return not errors, errors


def generate_descriptions(facts: dict[str, Any], episode_id: str, episode_split: str,
                          seed: Any) -> list[dict[str, Any]]:
    """Generate three train-only and one test-only description reproducibly.

    Any failed consistency check raises rather than returning a partial set.
    The caller is responsible for the quality/semantic-agreement eligibility
    gate and must emit a skipped record for ineligible episodes.
    """
    if not isinstance(episode_id, str) or not episode_id:
        raise ValueError("episode_id must be nonempty")
    if not isinstance(episode_split, str) or not episode_split:
        raise ValueError("episode_split must be nonempty")
    plans = _plans(facts)
    descriptions = []
    for variant in range(4):
        partition = "test" if variant == 3 else "train"
        sentences = []
        for plan in plans:
            index = 3 if partition == "test" else (_offset(seed, episode_id, plan.key) + variant) % 3
            sentences.append(dict(template_id=_template_id(plan.key, partition,
                                                            0 if partition == "test" else index),
                                  text=_render(plan, index), fact_ids=list(plan.fact_ids)))
        description = dict(description_id=f"{episode_id}:{partition}:{variant + 1}",
                           episode_id=episode_id, episode_split=episode_split,
                           template_partition=partition, facts_version=facts["facts_version"],
                           template_version=V06_TEMPLATE_VERSION if facts["facts_version"] == V06_FACTS_VERSION else TEMPLATE_VERSION,
                           sentences=sentences,
                           text="".join(sentence["text"] for sentence in sentences))
        valid, errors = validate_description(description, facts)
        if not valid:
            raise ValueError(f"description rejected: {errors}")
        descriptions.append(description)
    return descriptions
