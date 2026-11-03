"""公共抽签（V8-12 第 3 部分；r4 5.1）。签名只有 family、draw_index 两个参数：
不接受 intent、task、target、**kwargs，所以同一公共抽签可以配不同意图；形态重试不会影响它。
"""
from ..config import load_config
from ..contract.monitoring import CommonDraw, GroupSpec, SpeedProfilePrior
from .keys import RngKey, rng_for

FORMATION_PRIORS = ("abreast", "column", "echelon", "loose")


def sample_common(family, draw_index):
    M = load_config("monitoring").values
    rng = rng_for(RngKey(family.family_id, draw_index, "common"))
    ids = sorted(family.initial_states)
    n = len(ids)
    # 1. 从 {1,2,3} 等概率抽整数再 min(机数)（不是对 {1..min(3,n)} 重新均匀抽）
    g = min(int(rng.integers(1, int(M["group_count_max"]) + 1)), n)
    # 2. 每组先 1 人，剩余成员逐个均匀抽组号
    counts = [1] * g
    for _ in range(n - g):
        counts[int(rng.integers(0, g))] += 1
    # 3. 对排序后的全体 agent_id 做一次 permutation，按人数切片（人数与成员身份分配分离）
    perm = rng.permutation(n)
    groups, pos = [], 0
    for k in range(g):
        members = tuple(sorted(ids[int(perm[pos + i])] for i in range(counts[k])))
        pos += counts[k]
        # 4. 每组依组序：初始速度 U[4,10]、变速率 U[0,1]、四种队形倾向均匀；全部抽签值保留
        speed = float(rng.uniform(M["speed_min_m_s"], M["speed_max_m_s"]))
        rate = float(rng.uniform(0.0, M["change_rate_max_per_min"]))
        prior = FORMATION_PRIORS[int(rng.integers(0, len(FORMATION_PRIORS)))]
        groups.append(GroupSpec(f"g{k}", members, SpeedProfilePrior(speed, rate), prior,
                                approach_mode="single", member_variations=(), variation_probability=float(
                                    M["member_variation_probability"])))
    return CommonDraw(family.family_id, int(draw_index), tuple(groups))
