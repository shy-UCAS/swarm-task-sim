## 10. 接口原文（S，核对后照抄）

以下只摘原签名与已有文档字符串；`...`表示省略实现。没有docstring的不补造说明；类方法保留源码缩进。第2/3节新增签名不冒充既有接口。

### 10.1 `v08/motion/nominal.py` — `member_nominal`

```python
def member_nominal(member_plan, *, guidance=None, sim=None):
    ...
```

### 10.2 `v08/motion/nominal.py` — `release_us`

```python
def release_us(member_plan, sim=None):
    ...
```

### 10.3 `v08/motion/skeleton.py` — `NominalPVA`

```python
class NominalPVA:
    """名义分段匀加速运动（member_nominal 的弦内公式）在绝对时刻上的 p/v/a。
    释放前为起点、移动结束后为终点，v=a=0；只在 [release, release+travel] 内按弦内公式求值。"""
    ...
```

### 10.4 `v08/motion/skeleton.py` — `references_from_skeleton`

```python
def references_from_skeleton(skeleton, *, warnings=None, target_id=None, band_m=None, align_m=None):
    """返回 (TimeReference 元组, 语义直线区间, 成员站点→时间映射)。
    移动参考 = 名义分段匀加速运动，[release, release + travel]（不含末端保持；附录裁定 9.4）。"""
    ...
```

### 10.5 `v08/motion/skeleton.py` — `semantic_lines`

```python
def semantic_lines(member_id, nominal, warnings, target_id, *, band_m, align_m):
    """该成员骨架上的语义直线：每个设施实际穿越段的带（外 +10 至内 −10，按顶点区间），目标每次入圈并入前 align_m。
    返回 [(member_id, t0, t1, point_xy, unit_tangent_xy, meta)]，时间按该成员名义 t_nodes/s 映射。"""
    ...
```

### 10.6 `v08/motion/skeleton.py` — `merge_semantic_lines`

```python
def merge_semantic_lines(lines, *, knot_s, tol_m=NODE_TOL_M):
    """V8-14 指令 4.2：同一成员、时间顺序相邻、同一支撑直线、间隙严格 < 4h 的语义直线合并为一段等式。
    输入/输出六元组 (member_id, t0, t1, point_xy, unit_tangent_xy, meta)。平行/反平行都视为同一法向等式：
    单位切向叉积 ≤ γ_8（二维叉积的浮点舍入界）判平行，点到支撑线距离 ≤ tol_m 判共线。合并后沿用最早段的点与切向，
    时间取最早 t0、最晚 t1；meta 保留全部来源、原区间、gap 与最大共线残差。不跨越不共线的中间段。"""
    ...
```

### 10.7 `v08/motion/optimize.py` — `Prepared._member`

```python
    def _member(self, ref, lines):
        ...
```

### 10.8 `v08/motion/optimize.py` — `_optimize_segment_intent`

```python
def _optimize_segment_intent(ctx, skeleton, key, settings, intent):
    """V8-16 指令 2.1：非监视意图的优化外层。与监视分支建立同一 JointProblem、调用同一 solve_joint；差异只有
    约束表（layer_limits.constraints_for_task）与语义检查（intent_dispatch.semantic_checker）。过境没有掉头区间，
    turns 为空（不造伪掉头约束）。语义结果放 "semantic"；"monitoring" 键为 None。阶段距离场的缓存名含意图与
    有序约束完整身份，避免不同意图混用 route 缓存（原始距离按几何键共享磁盘缓存，不新写既有几何）。"""
    ...
```

### 10.9 `v08/motion/optimize.py` — `turns_from_skeleton`

```python
def turns_from_skeleton(skeleton, maps, monitoring_values):
    """V8-18 指令 2.1：骨架掉头表 → JointProblem.turns，只做 S 监视分支（optimize_segment）中的同一运算：成员排序、
    成员 rows 保持原顺序、key 为 None 跳过；t = np.interp(s, nom.curve.s, nom.t_nodes) + nom.release_s；R 读配置原值
    （monitoring_values[key]，未知 key 直接 KeyError，不默认半径）。没有表或空表返回 ()（旧意图不产生伪约束）。"""
    ...
```

### 10.10 `v08/motion/optimize.py` — `solve_joint`

```python
def solve_joint(problem, settings, *, knot_s=1.0):
    """单次求解物理层（增广拉格朗日外循环 + 内层 L-BFGS-B）；返回 JointSolution，不重抽骨架。
    成功 = 结果有限且原阈值硬检查全过；SciPy success 只记录。外循环用完仍不过 → optimize_residual（附最坏约束）。"""
    ...
```

### 10.11 `v08/motion/optimize_checks.py` — `check_physical`

```python
def check_physical(problem, trajectories, settings):
    """dict: passed, failures, separation, clearances, dynamic_extrema, endpoints。从最终系数重算。"""
    ...
```

### 10.12 `v08/motion/optimize_checks.py` — `check_transit`

```python
def check_transit(ctx, skeleton, trajectories, settings):
    """dict: passed, failures, boundaries, nominal_members。均在优化后的曲线上重算（时间网格照录 check_monitoring）：
    1) 冻结 crossing_analysis 查全部 warning（完整曲线、不传 skip_ranges）：单次直线穿越、两侧 10 m、目标入圈前 100 m、
       未穿越部分离边界 10 m；目标恰一入一出；
    2) 终点离所有 warning ≥ retreat_clearance_m；
    3) 名义判据：释放起至移动结束 + 末端保持的 10 Hz p/v 调 screen_transit_member，全部条件成立。
    过境没有掉头区间，不调用监视"必须重访"。成功由这些检查与 solve_joint 原阈值物理检查共同决定。"""
    ...
```

### 10.13 `v08/motion/intents/transit.py` — `propose_and_build`

```python
def propose_and_build(ctx, group, task, states, key):
    """一次随机构造（一个 attempt）：宽度先定队形（width_then_build；队形 probe = 该队形全部真实车道的离散弦集合
    是否非空）→ 可行格均匀抽一格 → 集合站点均匀抽一个 → 精确弦检查 → 走廊与一次曲线 LP（不可用即本格直线）→
    曲线精确复核 → 初始可视图路由 → 候选构造与检查。下游任何失败原样返回，不改队形、不换格。"""
    ...
```

### 10.14 `v08/motion/intents/transit.py` — `build_candidate`

```python
def build_candidate(ctx, group, task, states, key, proposal):
    """给定完整提案确定性地构造骨架：参考 → 槽位/成员车道 → 起点连接 → 速度事件 → 释放延迟 → 逐成员精确几何、
    边界穿越（目标恰一次入、一次出）与终点撤离。任一检查不过返回 candidate_rejected（保留原始见证）。
    V8-17 指令 3.6：proposal["intent"] == "intrusion" 时，参考/起点拼接/速度事件/释放延迟/成员装配仍共享，仅成员域
    （按成员终点 clip）、逐成员语义检查、成员映射与见证转入 intents.intrusion.finish_candidate；过境分支不变。"""
    ...
```

### 10.15 `v08/motion/intents/transit.py` — `formation_probe_sequence`

```python
def formation_probe_sequence(ctx, group, task, key):
    """确定性的选队形 probe 序列（主进程预建与 worker 共用）：返回 [(formation, lateral_step, offsets)]，
    按 width_then_build 的实际调用次序，直到第一个非空集合为止。用于 prewarm_transit 的请求清单。"""
    ...
```

### 10.16 `v08/motion/transit_chords.py` — `get_lanes`

```python
def get_lanes(ctx, target_id, theta_idx, ys, *, memo=True, intent="transit"):
    """按 (目标, 航向, 横向偏移) 的进程内缓存取单车道（解析部分）；memo=False 时逐车道直接重算（裁定 2 的门禁对照）。
    V8-17：不同意图的 base 采样结果不同，Lane 按意图分开缓存（transit 用原键）。"""
    ...
```

### 10.17 `v08/motion/transit_chords.py` — `assess_cell`

```python
def assess_cell(ctx, target_id, theta_idx, h, offsets, *, memo=True, field_grids=None, lanes=None):
    """offsets：((l_i, d_i), …)。可行返回 dict（x_t、x_in、候选 D 列表、各车道入/出圈），否则 (None, 原因)。"""
    ...
```

### 10.18 `v08/motion/transit_chords.py` — `assess_formation`

```python
def assess_formation(ctx, target_id, offsets, *, memo=True):
    """全部 (θ, h) 格按 θ、h 升序；返回 {"cells": [[θ_idx, h, x_t, x_in, [D…]], …], "reasons": {原因: 格数}, "n_cells",
    "seconds"}。每个航向先批量取解析车道，再对通过目标穿越检查的格批量采样。"""
    ...
```

### 10.19 `v08/motion/transit_chords.py` — `query_identity`

```python
def query_identity(ctx, target_id, offsets):
    ...
```

### 10.20 `v08/motion/transit_chords.py` — `load_chord_set`

```python
def load_chord_set(ctx, target_id, slots, cache_dir):
    """worker 只读：命中预建文件直接读；缺失时进程内计算（不写回、计数 cache_misses_computed），结果与预建相同。"""
    ...
```

### 10.21 `v08/motion/transit_chords.py` — `prewarm_transit`

```python
def prewarm_transit(ctx, requests, cache_dir):
    """主进程预建：requests = [(target_id, offsets), …]（由确定性的选队形 probe 序列给出）。已存在的文件不覆盖。
    返回每个查询的身份、格数、可行格数、构建耗时与文件散列。"""
    ...
```

### 10.22 `v08/motion/transit_chords.py` — `entry_planner`

```python
def entry_planner(ctx, target_id, delta_m):
    """可视图骨架规划器（过境首次入圈前）：world 内缩 35 + Δ，障碍外扩 35 + Δ，所有设施 alert 外扩 10 + Δ，
    再加目标 warning 外扩 10 + Δ（指令 3.1：图搜索本身绕过目标 warning）。缓存键含目标、Δ 与有序 blockers 身份。"""
    ...
```

### 10.23 `v08/motion/transit_chords.py` — `corridor_rows`

```python
def corridor_rows(ctx, task, chord, slots):
    """chord = {"theta_idx", "h"}。返回 {"available", "reason", "x", "lo", "hi", "D", "inset_interval", "rows_total",
    "certified_rows", "run": (首, 末下标), "certified_length_m", "inset_length_m"}。
    行：x = 5 m 网格上、条带 [x − 2.5, x + 2.5] 完全落在中心线目标 warning 内缩 10 + D 区间内的行；列：y = h + 2k；
    单元中心用 field 下界 ≥ q_cell = sqrt(2.5² + 1²)（ε_f 已扣，不重复）。某行包含 h 的单元（k = 0）通过即"已认证行"；
    其所在连续已认证单元的并给出该行 [lo, hi]。曲线范围取已认证行组成的最长连续段（等长取靠前）；
    段长（首末行中心距）< 80 m 记 curve_range_short；没有已认证行记 corridor_unavailable。"""
    ...
```

### 10.24 `v08/motion/transit_numeric.py` — `curve_lp`

```python
def curve_lp(x_m, lo_m, hi_m, h_m, logit_coefficients, *, D_m, kappa_star=KAPPA_STAR, r_turn_m=R_TURN_M,
             knot_spacing_m=KNOT_SPACING_M, slope_max=None):
    """见模块说明第二节。x_m 为等距 5 m 行中心（升序），lo_m/hi_m 为每行包含 h 的连续已认证区间（绝对横向坐标）。
    返回 {"feasible", "spline"(物理坐标 BSpline), "target_m", "fallback_reason", "lp_status", "lp_message",
    "lp_nit", "objective", "max_residual", "kappa_max", "slope_max", "n_controls", "seconds"}。"""
    ...
```

### 10.25 `v08/runner/transit_report.py` — `group_reference_curves`

```python
def group_reference_curves(ctx, group, res, *, intent="transit"):
    """c_after(s) = c_before(s) + (1/N)Σ_i[p_i^opt(t_i(s)) − p_i^ref(t_i(s))]（沿用 joint_monitoring.group_reference_curves
    的编组位移定义；t_i(s) 由保存的 member_map_transit（reference_s → member_s）与该成员名义弧长—时间给出）。
    先在完整 collect → terminal 编组曲线上构造 before/after，各自与目标 warning 精确求交、截出唯一的单次穿越段，
    再分别按自身几何弧长 5 m 重采样。返回 {"before", "after", "info"}；不能唯一截出时 before/after 为 None 并给原因。
    V8-17 指令 7.3：intrusion 用 member_map_intrusion（成员域外取端点值，与 np.interp 边界行为一致），唯一目标 warning
    入点（方向只 ["in"]）至编组曲线末端截出作业段。"""
    ...
```

### 10.26 `v08/runner/joint_intent.py` — `save_intent_contract`

```python
def save_intent_contract(out, rec, result, last_failed=None):
    """共享序列化（明确字段白名单）：用 rec["intent"] 选择附加块。过境保持原文件 bytes（不补 intrusion:null、crossing
    表、版本号或新默认字段）；intrusion 的 result.json 增加 "intrusion" 块（σ、x_e 来自保留提案，成员事件来自实测释放后
    窗口；失败为 None），失败见证另含实测三层进入次数。墙钟、缓存命中、traceback 只进合同目录外的 telemetry。"""
    ...
```

### 10.27 `v08/criteria/segment.py` — `verify_segments`

```python
def verify_segments(scene, tracks, release_us, tasks, *, criteria=None, segment_config=None):
    ...
```

### 10.28 `v08/criteria/validity.py` — `check_validity`

```python
def check_validity(scene, tracks, *, criteria=None) -> ValidityReport:
    ...
```
