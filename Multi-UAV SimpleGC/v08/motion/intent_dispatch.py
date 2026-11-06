"""骨架构造、优化后语义检查与名义预筛的意图分派（V8-16 指令 2.1；本项新增）。

启用 monitoring、transit 与 intrusion（V8-17 指令 2.2）；其他意图明确拒绝。每次调用时按模块属性取函数（不缓存函数对象），
监视仍是旧函数本身（`is` 相同）。
"""
SUPPORTED = ("monitoring", "transit", "intrusion")


def _unsupported(intent):
    return ValueError(f"本项只启用 {SUPPORTED} 的生成分派：{intent!r}")


def skeleton_builder(intent):
    if intent == "monitoring":
        from .intents import monitoring
        return monitoring.propose_and_build
    if intent == "transit":
        from .intents import transit
        return transit.propose_and_build
    if intent == "intrusion":
        from .intents import intrusion
        return intrusion.propose_and_build
    raise _unsupported(intent)


def semantic_checker(intent):
    from . import optimize_checks
    if intent == "monitoring":
        return optimize_checks.check_monitoring
    if intent == "transit":
        return optimize_checks.check_transit
    if intent == "intrusion":
        return optimize_checks.check_intrusion
    raise _unsupported(intent)


def nominal_screen(intent):
    from . import nominal_checks
    if intent == "monitoring":
        return nominal_checks.screen_member
    if intent == "transit":
        return nominal_checks.screen_transit_member
    if intent == "intrusion":
        return nominal_checks.screen_intrusion_member
    raise _unsupported(intent)


def skeleton_intent(skeleton):
    """优化外层从骨架见证取意图；旧监视骨架没有该字段时按 monitoring 解释（不给旧骨架补字段）。"""
    return (skeleton.witnesses or {}).get("intent", "monitoring")
