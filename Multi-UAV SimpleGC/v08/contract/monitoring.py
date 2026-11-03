"""监视单段合同（V8-12）。第 2 部分：Family、Failure、family_from_initial；第 3 部分补合同与初态转换。

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
