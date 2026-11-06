"""单意图单段合同分派（V8-16 指令 2.1；本项新增）。

只支持两种生成意图：monitoring 直接调用旧 monitoring_mission；transit 先调用旧函数取得同一公共条件与目标
（同一 sequence 键），再用 dataclasses.replace **仅替换唯一 TaskSpec 的 intent**。policy_version 保留旧值作配对
输入身份，不以换版本重播 RNG；意图写在外部 manifest 和过境自己的输出中。其他意图抛 ContractInvalid。
"""
from dataclasses import replace

from .monitoring import ContractInvalid, monitoring_mission, validate_mission

GENERATION_INTENTS = ("monitoring", "transit")


def validate_single_mission(mission, ctx):
    """monitoring 原样走旧 validate_mission；transit 把任务临时换成 monitoring 复用旧字段约束，随后显式确认
    实际任务为 transit 且 final=True。不把旧校验放宽为任意字符串。"""
    if len(mission.tasks) != 1:
        raise ContractInvalid("单段：恰好一个任务段")
    task = mission.tasks[0]
    if task.intent == "monitoring":
        return validate_mission(mission, ctx)
    if task.intent != "transit":
        raise ContractInvalid(f"本项只支持 {GENERATION_INTENTS}：{task.intent!r}")
    validate_mission(replace(mission, tasks=(replace(task, intent="monitoring"),)), ctx)
    if mission.tasks[0].intent != "transit" or not mission.tasks[0].final:
        raise ContractInvalid(f"过境任务非法：{mission.tasks[0]!r}")
    return True


def transit_mission(ctx, common):
    mon = monitoring_mission(ctx, common)
    mission = replace(mon, tasks=(replace(mon.tasks[0], intent="transit"),))
    validate_single_mission(mission, ctx)
    return mission


def mission_for_intent(ctx, common, intent):
    if intent == "monitoring":
        return monitoring_mission(ctx, common)
    if intent == "transit":
        return transit_mission(ctx, common)
    raise ContractInvalid(f"本项只支持 {GENERATION_INTENTS}：{intent!r}")
