"""监视单段合同（V8-12）。第 2 部分：Family、Failure、family_from_initial；第 3 部分：合同、计划与转换。

用 dataclasses（不装 Pydantic，见 r4 13.2 第 5 条）。不在 import 时读取数据、创建目录或导入 shapely。
"""
import math
from dataclasses import dataclass, field


class ContractInvalid(ValueError):
    """合同字段非法（r4 既有 contract_invalid）。"""
    code = "contract_invalid"


@dataclass(frozen=True)
class Family:
    """一个场景族的初始条件。initial_states 保存原始按 agent_id 索引的记录，不预先覆盖 v/a。
    不使用 family 的 cruise_speed_m_s（r4 5.1：期望速度由公共抽签给出）。"""
    family_id: str
    initial_states: dict
    vehicle_count: int
    task_altitude_m: float
    lateral_spacing_m: float
    observation_profile: dict = field(default_factory=dict)
    map_side_m: float | None = None


@dataclass(frozen=True)
class Failure:
    code: str                 # proven_infeasible / approx_empty / budget_exhausted 等
    reason: str
    feasible_set: str
    witness: dict | None = None
    exact_nonempty: bool | None = None


def family_from_initial(family_id, initial):
    """从 family_initial.json 的内容建 Family；机数、坐标、间距不自洽时抛 ContractInvalid。"""
    if not isinstance(family_id, str) or not family_id:
        raise ContractInvalid("family_id 必须是非空字符串")
    if "family_id" in initial and initial["family_id"] != family_id:
        raise ContractInvalid(f"family_id {family_id!r} 与初态文件中的 {initial['family_id']!r} 不符")
    records = initial.get("initial_states")
    if not isinstance(records, list) or not records:
        raise ContractInvalid("initial_states 必须是非空列表")
    by_id = {}
    for rec in records:
        agent = rec.get("agent_id")
        if not isinstance(agent, str) or not agent or agent in by_id:
            raise ContractInvalid(f"agent_id 缺失或重复：{agent!r}")
        pos = rec.get("position_enu_m")
        if not (isinstance(pos, (list, tuple)) and len(pos) == 3 and all(isinstance(x, (int, float)) and math.isfinite(x) for x in pos)):
            raise ContractInvalid(f"{agent} 的 position_enu_m 须为三个有限数")
        by_id[agent] = dict(rec)
    count = initial.get("vehicle_count")
    if count != len(by_id):
        raise ContractInvalid(f"vehicle_count={count!r} 与初态条数 {len(by_id)} 不符")
    spacing = initial.get("lateral_spacing_m")
    altitude = initial.get("task_altitude_m")
    for name, value in (("lateral_spacing_m", spacing), ("task_altitude_m", altitude)):
        if not isinstance(value, (int, float)) or not math.isfinite(value) or (name == "lateral_spacing_m" and value <= 0):
            raise ContractInvalid(f"{name} 非法：{value!r}")
    return Family(family_id=family_id, initial_states=dict(sorted(by_id.items())), vehicle_count=int(count),
                  task_altitude_m=float(altitude), lateral_spacing_m=float(spacing),
                  observation_profile=dict(initial.get("observation_profile") or {}),
                  map_side_m=None if initial.get("map_side_m") is None else float(initial["map_side_m"]))


# ---------------------------------------------------------------- 第 3 部分：合同、计划与转换

POLICY_VERSION = "v8-12-monitoring-1"
FORMATION_PRIORS = ("abreast", "column", "echelon", "loose")


@dataclass(frozen=True)
class SpeedProfilePrior:
    initial_speed_m_s: float
    change_rate_per_min: float


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    intent: str
    target_id: str
    switch_mode: str = "auto"
    final: bool = True


@dataclass(frozen=True)
class GroupSpec:
    group_id: str
    member_ids: tuple
    speed_profile: SpeedProfilePrior
    formation_prior: str
    approach_mode: str = "single"
    member_variations: tuple = ()
    variation_probability: float = 0.0


@dataclass(frozen=True)
class CommonDraw:
    family_id: str
    draw_index: int
    groups: tuple


@dataclass(frozen=True)
class Mission:
    """公共抽签的完整副本 + 实际使用的第 0 组与单个监视任务。"""
    family_id: str
    draw_index: int
    policy_version: str
    input_sha256: dict
    business_key: dict
    common: CommonDraw
    groups: tuple
    tasks: tuple


@dataclass(frozen=True)
class MemberPlan:
    member_id: str
    segment_index: int
    curve_xy: tuple
    altitude_m: float
    end_s: float
    release_delay_s: float
    speed_breaks: tuple
    stops: tuple = ()


@dataclass(frozen=True)
class SegmentPlan:
    members: dict
    reference_xy: tuple
    nominal_duration_s: float
    anchors: dict
    repairs: tuple
    failure: Failure | None = None
    proposal: dict | None = None
    formation: dict | None = None          # prior / start / realized / mapped_from_loose / retreat_chain / 偏移
    topology: dict | None = None           # prior_draw / drawn / final / forced / 圈数或穿行次数
    business_key: dict | None = None
    member_nominal_s: dict | None = None
    witnesses: dict | None = None          # 所有检查的原始见证
    attempt_log: tuple = ()


def initial_states(family, member_ids):
    """第 0 段入口的静止边界状态：位置原样取 family_initial（含高度），不带入 v0.7 初速，不平移起点。"""
    from ..sim.types import MemberBoundaryState

    out = {}
    for m in member_ids:
        rec = family.initial_states.get(m)
        if rec is None:
            raise ContractInvalid(f"成员 {m!r} 不在族 {family.family_id!r} 的初始状态里")
        out[m] = MemberBoundaryState(m, 0, 0, tuple(float(x) for x in rec["position_enu_m"]),
                                     (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    return out


def validate_mission(mission, ctx):
    """r4 contract_invalid：合同字段非法时抛 ContractInvalid。"""
    fac = {f.id for f in ctx.facilities}
    if len(mission.groups) != 1 or len(mission.tasks) != 1:
        raise ContractInvalid("③ 监视单段：恰好一个编组、一个任务段")
    g, task = mission.groups[0], mission.tasks[0]
    if task.intent != "monitoring" or not task.final or task.target_id not in fac:
        raise ContractInvalid(f"任务非法：{task!r}")
    ids = set(ctx.family.initial_states)
    if not g.member_ids or not set(g.member_ids) <= ids or len(set(g.member_ids)) != len(g.member_ids):
        raise ContractInvalid(f"编组成员非法：{g.member_ids!r}")
    if g.formation_prior not in FORMATION_PRIORS:
        raise ContractInvalid(f"队形倾向非法：{g.formation_prior!r}")
    if g.approach_mode != "single" or g.member_variations != () or g.variation_probability != 0.0:
        raise ContractInvalid("③ 范围：进场方式 single、组内差异关闭（p=0）")
    if not (g.speed_profile.initial_speed_m_s > 0 and g.speed_profile.change_rate_per_min >= 0):
        raise ContractInvalid("速度先验非法")
    return True


def to_guided(member_plan):
    """逐字段转换：end_s → end_s_m；不改点列、不重新采样、不补 tail（本项全为 final）。"""
    from ..sim.guided import GuidedSegmentPlan

    return GuidedSegmentPlan(member_id=member_plan.member_id, segment_index=member_plan.segment_index,
                             curve_xy=member_plan.curve_xy, altitude_m=member_plan.altitude_m,
                             speed_breaks=member_plan.speed_breaks, end_s_m=member_plan.end_s,
                             stops=member_plan.stops, release_delay_s=member_plan.release_delay_s)


def monitoring_mission(ctx, common):
    """目标用独立 sequence 键在按 ID 排序的设施中均匀抽取，不根据可行性换目标。"""
    from ..sampler.keys import RngKey, rng_for

    rng = rng_for(RngKey(common.family_id, common.draw_index, "sequence", mission=0))
    ids = sorted(f.id for f in ctx.facilities)
    target = ids[int(rng.integers(0, len(ids)))]
    g0 = common.groups[0]
    task = TaskSpec("task0", "monitoring", target)
    key = {"family_id": common.family_id, "draw_index": common.draw_index, "mission": 0, "group": g0.group_id,
           "segment": 0, "branch": None, "policy_version": POLICY_VERSION}
    mission = Mission(common.family_id, common.draw_index, POLICY_VERSION, dict(ctx.inputs.get("sha256", {})), key,
                      common, (g0,), (task,))
    validate_mission(mission, ctx)
    return mission
