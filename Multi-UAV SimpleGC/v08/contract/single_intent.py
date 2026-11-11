"""单意图单段合同分派（V8-16 指令 2.1；本项新增）。

生成意图：monitoring 直接调用旧 monitoring_mission；transit、intrusion（V8-17 指令 2.2）、feint（V8-18 指令 2.2）先调用旧函数取得同一
公共条件与目标（同一 sequence 键），再用 dataclasses.replace **仅替换唯一 TaskSpec 的 intent**。policy_version 保留
旧值作配对输入身份，不以换版本重播 RNG；意图写在外部 manifest 和各意图自己的输出中。其他意图抛 ContractInvalid。
"""
from dataclasses import dataclass, replace
from typing import Optional

from .monitoring import ContractInvalid, TaskSpec, monitoring_mission, validate_mission

GENERATION_INTENTS = ("monitoring", "transit", "intrusion", "feint", "close_observation", "area_search", "detour")


@dataclass(frozen=True)
class AreaSearchTaskSpec(TaskSpec):
    """Only area_search carries a private candidate survey; old TaskSpec is unchanged."""
    survey: Optional[dict] = None


def validate_single_mission(mission, ctx):
    """monitoring 原样走旧 validate_mission；transit/intrusion/feint 把任务临时换成 monitoring 复用旧字段约束，随后显式
    确认实际任务为该意图且 final=True。不把旧校验放宽为任意字符串。"""
    if len(mission.tasks) != 1:
        raise ContractInvalid("单段：恰好一个任务段")
    task = mission.tasks[0]
    if task.intent == "monitoring":
        return validate_mission(mission, ctx)
    if task.intent not in ("transit", "intrusion", "feint", "close_observation", "area_search", "detour"):
        raise ContractInvalid(f"本项只支持 {GENERATION_INTENTS}：{task.intent!r}")
    intent = task.intent
    validate_mission(replace(mission, tasks=(replace(task, intent="monitoring"),)), ctx)
    if mission.tasks[0].intent != intent or not mission.tasks[0].final:
        what = {"transit": "过境", "intrusion": "突入", "feint": "佯动", "close_observation": "抵近观察", "area_search": "区域侦察",
                "detour": "迂回"}[intent]
        raise ContractInvalid(f"{what}任务非法：{mission.tasks[0]!r}")
    return True


def transit_mission(ctx, common):
    mon = monitoring_mission(ctx, common)
    mission = replace(mon, tasks=(replace(mon.tasks[0], intent="transit"),))
    validate_single_mission(mission, ctx)
    return mission


def intrusion_mission(ctx, common):
    """V8-17 指令 2.2：先调用 monitoring_mission，再仅替换唯一 TaskSpec 的 intent；任务编号、target、
    policy_version、group、成员、速度、队形与 RNG 键均不变。"""
    mon = monitoring_mission(ctx, common)
    mission = replace(mon, tasks=(replace(mon.tasks[0], intent="intrusion"),))
    validate_single_mission(mission, ctx)
    return mission


def feint_mission(ctx, common):
    """V8-18 指令 2.2：先调用 monitoring_mission，再仅替换唯一 TaskSpec 的 intent；目标、组、速度、队形、键、
    policy_version 均不变。"""
    mon = monitoring_mission(ctx, common)
    mission = replace(mon, tasks=(replace(mon.tasks[0], intent="feint"),))
    validate_single_mission(mission, ctx)
    return mission


def close_observation_mission(ctx, common):
    """V8-19: only replace the task intent, preserving the public draw and RNG identity."""
    mon = monitoring_mission(ctx, common)
    mission = replace(mon, tasks=(replace(mon.tasks[0], intent="close_observation"),))
    validate_single_mission(mission, ctx)
    return mission


def area_search_mission(ctx, common):
    """Preserve the original public and sequence draws; attach no candidate survey yet."""
    mon = monitoring_mission(ctx, common)
    old = mon.tasks[0]
    task = AreaSearchTaskSpec(old.task_id, "area_search", old.target_id, old.switch_mode, old.final)
    mission = replace(mon, tasks=(task,))
    validate_single_mission(mission, ctx)
    return mission


def detour_mission(ctx, common):
    """V8-21 指令 2.4：先调用 monitoring_mission，再仅替换唯一 TaskSpec 的 intent（单段 final=True，不加 survey）；
    目标、成员、组、初速、高度、倾向、policy_version、sequence 键不变。"""
    mon = monitoring_mission(ctx, common)
    mission = replace(mon, tasks=(replace(mon.tasks[0], intent="detour"),))
    validate_single_mission(mission, ctx)
    return mission


def mission_for_intent(ctx, common, intent):
    if intent == "detour":
        return detour_mission(ctx, common)
    if intent == "area_search":
        return area_search_mission(ctx, common)
    if intent == "monitoring":
        return monitoring_mission(ctx, common)
    if intent == "transit":
        return transit_mission(ctx, common)
    if intent == "intrusion":
        return intrusion_mission(ctx, common)
    if intent == "feint":
        return feint_mission(ctx, common)
    if intent == "close_observation":
        return close_observation_mission(ctx, common)
    raise ContractInvalid(f"本项只支持 {GENERATION_INTENTS}：{intent!r}")
