# S2 扩展第二阶段：四个新角色实施记录与当前阻塞

编写时间：2026-10-14
分支：`v07-scene`
用途：交接记录。说明用户历次指令、既定实现方案、当前进展、出现的问题，以及**当前一直未能解决的核心问题**。
状态：**未达标，工作树处于"部分改动已生效、几何分离改造半途"的状态，未提交。**

---

## 1. 用户历次指令

### 1.1 第一轮：独立复核、回归、规划层间距估算（三点）

1. **独立复核不能退化为自洽检查。** `approach_span_deg` 的新口径（核心事件前最后 100 m 的平均航向、组内最大夹角）应由审计脚本**直接从 10 Hz 真值轨迹独立重算**：自己定位核心事件时刻、自己截取最后 100 m 路径、自己计算平均航向和最大夹角，再与标签比较，差异须为 0（或在写明的数值容差内）。**审计脚本不得导入 `task_v07`。** 需对过境 4 条与正在运行的新角色试飞补做。
2. **确认每次修改 `labels.measure` 后都已运行固定回归**（竖切 8 条逐字节一致 ＋ 过境 4 条新基准）；如尚未运行，补跑并报告。
3. **确认规划层间距估算是否已实现**（定速插值 ＋ 出发延迟、同步与递次两个版本、阈值 6 m）；未实现则在开始多任务组之前完成，因为多组场景最需要它。

### 1.2 第二轮：四个新角色修到能稳定飞出来（六条，明确"不进入多任务组"）

1. **规划层间距估算必须在实飞前拦截**：估算最小间距 <6 m 时，先调整两个时序版本共用的几何；仍不满足则该骨架判为**规划失败**（记录原因），**不进入单机测时和实飞**。原状是间距过近仍然实飞，说明拦截没生效；需修正并**补测试**（构造一个必然重叠的骨架，验证它在实飞前被拦下）。
2. **各机独立站位，三个角色都要补**：
   - 抵近观察：每机各自的观察点，沿警戒区外缘按方位散开，相邻规划间距 ≥6 m；
   - 游弋监视：成员沿环线错开相位切入，不从同一点进入；
   - 佯攻：每机各自的进入方位、最大深度点和转向点，彼此间距 ≥6 m（速度 >7 m/s 时 ≥15 m）。
3. **突防在地图 `aa4c66be` 上"生成成功但任务失败"**：列出具体未满足的判据（是否进入禁飞区、深度、是否抵达本机目标点、撤离等），定位原因，属于规划器缺陷的修复。
4. **佯攻、突防在地图 `4d13d93f` 上的 infeasible**：输出具体拒绝原因。若是该拥挤布局本身放不下，记为**几何拒绝并统计，不放宽约束**；若是规划器缺陷，修复。
5. **修复后**：先跑固定回归；再用当前代码重跑这 8 个骨架（两张地图 × 四个新角色），**补做四个新角色的截断测试**；为每个新角色输出 1 张实飞俯视图（含各机计划站位与实际轨迹）。
6. **进入下一步的标准**：四个新角色在两张地图上**至少各有 1 对同步/递次成功**（佯攻、突防若在 `4d13d93f` 上确认为几何拒绝，可只在 `aa4c66be` 上达标）；**剩余失败只能是几何或运动学拒绝，不能有间距 <2 m 的生成错误，也不能有原因不明的任务失败。**

达标后停下汇报（结果表 ＋ 4 张俯视图），等确认再进入：区域搜索新规划器 → 多任务组 → 中止样本 → 126 条全量运行 → 交叉否定 → 报告。

### 1.3 第三轮（本次）

停止继续尝试修复，改为**写一份 md 文档**记录：指令、实现方案、进展、问题、当前一直尝试解决的问题。

---

## 2. 既定实现方案

### 2.1 第 1 条：规划层间距拦截

分两处实现，演进过程如下（**三段都被试过，均不理想**）：

| 版本 | 位置 | 判据 | 结果 |
|---|---|---|---|
| A | `pipeline.plan_group` | 零延迟虚拟计划，全路径定速插值最小间距 | **误拦全部**：所有角色共享进场走廊，同时出发时间距恒为 0 |
| B | `run_v07_s2_expansion.run_skeleton_job`（单机测时后） | 真实出发延迟，全路径插值 | 仍**拦截全部**：走廊共享使插值间距仍 <6 m |
| C | 同上 | 只查**端点**间距 `check_endpoint_spacing` | 端点已散开故不拦；但**没解决中途碰撞** |

现状：C 版在用。`planning_layer_interval_check` 仍然计算并写入 `planning_layer_interval.json`（供诊断），但不作为拦截门槛。

### 2.2 第 2 条：各机独立站位

已实现的部分：

- **抵近观察**：`obs_point(angle)` 从"警戒区边界上"改为"边界外移 `obs_radius`"；每机按 `min_arc = min_sep_m / alert_r` 在基准角两侧对称散开；每机**各自**调用 `find_clear_retreat` 得独立撤离点。
- **游弋监视**：每机切入角为 `chosen_angle + 2π·i/n`（相位错开），各机轨道起点不同；`planned_laps` 从"120 s ÷ 单圈时间"（3–5 圈）改为**固定 1 圈**；各机独立撤离点。
- **佯攻**：`feint_r` 从警戒带 50% 改为 **35%**（更深入，确保 `depth_in_band` 达标）；每机 `base_angle + (i-(m-1)/2)·min_arc` 独立方位；各机独立撤离点。
- `min_sep_m = max(6, 15 if speed > 7 else 6)`，全部角色统一。

### 2.3 第 3 条：`aa4c66be` 突防任务失败

**结论：不是规划器缺陷，是"最后 100 m 航向"口径与多向设计不匹配。**

诊断证据（骨架 `aa4c66be_ext_004_regular`，9 机）：

- 全部个体判据通过：`entered_protected=True`、`required_depth=True`、`exclusion_policy_respected=True`、`own_endpoint_hold=True`。
- 组级唯一失败项是 `multi_direction_span=False`，实测 `approach_span_deg = 14.78°`（要求 ≥90°）。
- 根因：9 机全部从**同一西侧入口区**出发，核心事件前最后 100 m 的航向全部近似正东，因此组内最大夹角只有 14.78°。规划层端点确实按两侧散开，但散开没有体现在最后 100 m 的轨迹方向上。

已尝试的修复：`IntrusionPlanner` 改为**按起始位置相对目标的分侧**（用与主轴的点积符号分组），使两侧成员各自从其本侧接近，而非按 `members[:half]` 顺序切分。**该修复是否生效尚未验证**（后续试飞被其它问题阻断）。

### 2.4 第 4 条：`4d13d93f` 上的两个 infeasible

| 骨架 | 拒绝原因 | 归类 |
|---|---|---|
| `4d13d93f_ext_003_regular`（佯攻） | `kinematic_infeasible:single_agent_not_completed` | **运动学拒绝**。规划层 `planning_checks=PASS`；7 机核心事件全部观察到（385–438 s），但 uav_02/04/05 的 `completed_hold_times_s=null`——单机在时限内飞到核心事件却未能在 `terminal_radius=1 m`、`terminal_speed=0.15 m/s` 下保持 `terminal_hold_s=2 s`。任一机未完成即整骨架判 infeasible。 |
| `4d13d93f_ext_004_regular`（突防） | `multi_group_not_in_phase_1` | **第一阶段范围限制**。该描述符含 **2 个任务组**（`intrusion` 5 机 ＋ `monitoring` 2 机），`run_skeleton_job` 在 `skroot.mkdir()` **之前**就返回，因此连 `planning_rejection.json` 都没留下——这不是崩溃，是预期行为。 |

### 2.5 第 5、6 条

- 回归：**已跑，PASS**（见 §3）。
- 8 骨架重跑：**跑了多次**，均未达标（见 §4）。
- 四个新角色的**截断测试：未补做。**
- 实飞俯视图：**未输出**。
- 第 6 条标准：**未达标。**

---

## 3. 当前进展

### 3.1 已完成且已独立验证

| 项 | 状态 | 证据 |
|---|---|---|
| 审计脚本独立重算 `approach_span_deg` | **完成** | `scripts/audit_v07_s2_roles.py`：新增 `_approach_heading_deg`（从 10 Hz 原始位置反向累积 100 m，取首末向量航向）、`_heading_span_deg`（最大两两圆形夹角）；**不导入任何 `task_v07` 模块**；新增四个角色各自的独立审计函数 `audit_close_observation_episode` / `audit_monitoring_episode` / `audit_feint_episode` / `audit_intrusion_episode` |
| 固定回归 | **PASS ×2** | `attempt_s2x_regress_20261014T103650Z_972377d1`、`attempt_s2x_regress_20261014T091950Z_332da3cf`，两者均 `status=PASS episodes=8 content_diffs=0 labels_identical=8` |
| 规划层间距估算实现 | **完成** | `task_v07/expansion/geometry_checks.py::planning_layer_interval_check`：定速插值（10 Hz 采样）＋ 叠加同步/递次两版出发延迟 ＋ 阈值 6 m；每骨架写 `planning_layer_interval.json` |
| 单元测试 | **15/15 通过** | `tests/test_v07_s2_expansion.py`，含新增的 `PlanningIntervalInterceptTests`（端点重叠必被标记、抵近观察观察点间距 ≥6 m） |
| 语法完整性 | **OK** | 6 个改动文件全部通过 `ast.parse` |

### 3.2 未完成

- 第 2 条"各机独立站位"**接线未完成**：抵近观察接了车道（但当前必然失败，见 §4）；**监视、佯攻尚未接车道**，实测 `spatial_min` 仍为 0.00 m。
- 第 1 条拦截**未真正生效**（C 版只查端点，放过了中途碰撞）。
- 第 3 条修复未验证；第 5 条截断测试、俯视图未做。
- 第 6 条未达标。

---

## 4. 出现的问题

### 4.1 最新一次完整试飞结果（`attempt_s2x_p1_20261014T093058Z_5860b099`，exit 0，`process_check=PASS`）

| 骨架 | 角色 | 递次版 | 同步版 |
|---|---|---|---|
| `4d13d93f_ext_001` | 抵近观察 | generated / **failure**，sep=13.53 m | **generation_error**，sep=0.63 m |
| `4d13d93f_ext_002` | 游弋监视 | generated / **failure**，sep=5.39 m | **generation_error**，sep=0.25 m |
| `4d13d93f_ext_003` | 佯攻 | infeasible（运动学） | infeasible（运动学） |
| `4d13d93f_ext_004` | 突防 | infeasible（多任务组，第一阶段不支持） | 同 |
| `aa4c66be_ext_001` | 抵近观察 | **generation_error**，sep=0.025 m | **generation_error**，sep=0.089 m |
| `aa4c66be_ext_002` | 游弋监视 | infeasible（`polyline:uav_02:constraint_clearance`） | 同 |
| `aa4c66be_ext_003` | 佯攻 | generated / **failure**，sep=19.59 m | **generation_error**，sep=0.08 m |
| `aa4c66be_ext_004` | 突防 | infeasible（`intrusion_endpoint_spacing`） | 同 |

### 4.2 核心问题：同步版共享走廊碰撞（间距 <2 m 生成错误）

**这是唯一挡住第 6 条达标的问题，其它多为次要问题。**

**证据一 —— 规划航迹纯空间最小距离 = 0.000 m**（`4d13d93f_ext_001`）：

```
uav_01-uav_03: 0.000 m
uav_01-uav_06: 0.000 m
uav_01-uav_07: 0.000 m
uav_03-uav_06: 0.000 m
uav_03-uav_07: 0.000 m
```

西侧四机（uav_01/03/06/07）的规划航迹**完全重合**。

**证据二 —— 真值同步版两机位于同一点**：

```
synchronous: min=0.029 m at t=476.0s between uav_02 and uav_01
   uav_02 at [3015.1, 3507.8]
   uav_01 at [3015.1, 3507.8]
```

**根因链**：

1. **`role_planner(scene, survey=False)` 的精确可见图，对起点终点相近的飞机返回同一条折线。**（主要根因）
2. 同步时序把所有核心事件压到同一时刻；航程长度相近 ⇒ 出发延迟相近 ⇒ 全程同速同行。
3. 递次版因批次时间错开而幸免（13.53 / 5.39 / 19.59 m 均合格）。
4. 已确认：`bundle.departure_delays_s` **从不参与执行**——`single_agent_timing` 传 `{m: 0}`，`paired_run` 用 `plan["departure_delays_s"]`；bundle 里那个字段只在 `validate_route_bundle` 被校验。因此**任何在规划器里写 bundle 延迟的做法都是死代码**。

### 4.3 次要问题（各自根因已定位）

| 问题 | 现象 | 根因 | 处置 |
|---|---|---|---|
| `no_alert_entry=False` | 抵近观察全部 `failure` | `obs_point` 原落在警戒区**边界**上，飞机进入警戒区 | 已改为边界外移 `obs_radius`（**效果未验证**） |
| `reached_retreat_point=False`、`own_endpoint_hold=False` | 游弋监视 `failure` | 轨道圈数 3–5 圈过长，时限内未到撤离点 | 已改为固定 1 圈（**效果未验证**） |
| `depth_in_band=False` | 佯攻 `failure` | 实测 `max_depth_in_alert_m=0.0`——航迹几乎没深入警戒带 | `feint_r` 50%→35%（**效果未验证**） |
| `polyline:uav_02:constraint_clearance` | `aa4c66be_ext_002` 拒 | 监视规划器产出的航迹不满足硬障碍净空 | **未处理** |
| `intrusion_endpoint_spacing` | `aa4c66be_ext_004` 拒 | `_pick_spread_angles` 在该布局找不到满足 15 m 端点间距的组合 | **未处理** |

---

## 5. 当前一直尝试解决的问题

**核心目标：让同一进场走廊内的多机航迹产生 ≥6 m 的几何分离（同步版也安全）。**

已经试过三种思路，都失败：

| 思路 | 做法 | 失败原因 |
|---|---|---|
| **A. 时序错开** | 新增 `_stagger_delays(routes, speed)`，按航程长度给每机算错开的出发延迟，写进 `RouteBundle` | **无效**：`bundle.departure_delays_s` 是死字段，真实延迟由 `departure_delays()` 从单机实测重算。该函数目前仍被三个规划器调用，属**待回退的无效改动** |
| **B. 横向车道偏移** | 新增 `lane_routes()`（用 `offset_polyline` 把参考航迹按 `(i-(n-1)/2)·spacing` 横向偏移）＋ `build_lane()`（按 1.0/0.75/0.5 降级重试）＋ `routes_clear()`（净空校验） | **失败**：参考航迹贴着障碍的 35 m 净空，任何横向偏移都切进障碍（实测净空 −256 ~ −314 m） |
| **C. 按物理入口侧分组再建车道** | 新增 `split_by_side()`：先用"起点相对目标的主轴点积符号"把成员分成东/西两侧，每侧各取参考航迹、各建车道 | **仍失败**：同一根因——参考航迹贴边，偏移即破净空。且抵近观察因此从"能飞但碰撞"退化成 **INFEASIBLE**（比改造前更差） |

**下一步设想（尚未实施）**：

- **方案 D：顺序规划 ＋ 走廊排除区。** 逐机规划；每规划完一架，把它的航迹**截去末端汇聚段后**缓冲成一条窄多边形，作为 `hard_constraint_obstacle` 加入场景副本，后续飞机自然绕开。这样分离是规划出来的，不依赖后处理偏移，也不受"参考航迹贴边"影响。需注意：近目标处各机站位本来就只相距约 6–20 m，排除区必须在末端截断，否则必然不可行。
- **方案 E：航程长度差 ≡ 沿走廊间距。** 数学上，同走廊两机在同步时序下的**沿程间距 = 两者航程长度之差**（延迟差 = 航程差 ÷ 速度）。若把各机航程长度按 `spacing` 递增拉开，即可获得分离。实现上需要人为加长航程（例如每机一段不同的预备航段），形态较不自然。
- **方案 F：接受"该布局放不下"，按第 4 条记为几何拒绝并统计。** 若确认 `4d13d93f` 的拥挤布局在同步时序下无法容纳 7 机 ≥6 m 间距，则按用户第 4 条"记为几何拒绝并统计，不放宽约束"处理，只在 `aa4c66be` 上争取达标（用户第 6 条已预留此路径）。

---

## 6. 代码改动清单与已知缺陷

### 6.1 已改动文件（`git status`，全部未提交）

```
 M scripts/audit_v07_s2_roles.py       — 独立重算 approach_span_deg ＋ 四个角色独立审计
 M scripts/run_v07_s2_expansion.py     — 端点间距拦截（C 版）＋ planning_layer_interval 落盘
 M task_v07/expansion/geometry_checks.py — 新增 planning_layer_interval_check、check_endpoint_spacing、常量
 M task_v07/expansion/pipeline.py      — 角色规划/预检接线调整
 M task_v07/expansion/role_planners.py — 四个角色规划器改写 ＋ 车道机制（半成品）
 M task_v07/labels.py                  — （第一阶段起）角色判据
 M tests/test_v07_s2_expansion.py      — 15 项测试，含新增拦截测试
```

### 6.2 工作树里遗留的临时脚本（需清理或收编）

```
_tmp_check_zones.py      查圈层 offset_m 语义
_tmp_diag.py             航迹重合/碰撞点诊断（有用，建议收编）
_tmp_inspect.py          被杀试飞的残留结果检查（有用）
_tmp_list_skeletons.py   列骨架 ID
_tmp_smoke_plan.py       规划层冒烟测试，只规划不仿真，秒级迭代（**建议保留**）
```

### 6.3 已知缺陷（交给下一轮处理，本轮不再动）

1. **`_stagger_delays` 是死代码**：三个规划器仍在调用，但写入的 bundle 延迟不参与执行，具误导性，应回退为 `{a: 0.0 for a in members}` 或删除该函数。
2. **`role_planners.py` 的车道机制当前恒返回 None**：`lane_routes` / `build_lane` / `split_by_side` / `routes_clear` 已加入但在此布局下必然失败，导致**抵近观察比改造前更差（INFEASIBLE）**。
3. **监视、佯攻尚未接车道**，`spatial_min` 仍为 0.00 m。
4. **第 1 条拦截未真正生效**：C 版只查端点，同步版中途碰撞仍会实飞。
5. 本轮我误删过 `split_by_side` 的 docstring 起始 `"""`（已修复），6 个文件现均通过 `ast.parse`。

---

## 7. 证据与复现

### 7.1 关键 attempt

| attempt | 说明 |
|---|---|
| `attempt_s2x_p1_20261014T093058Z_5860b099` | **最新一次完整试飞**（16 条全跑完，见 §4.1） |
| `attempt_s2x_p1_20261014T103824Z_2741f4ee` | 最近一次试飞，**被会话结束中断**（6 条审计 PASS，无 `summary.json`） |
| `attempt_s2x_regress_20261014T103650Z_972377d1` | 回归 PASS（8/8、0 差异、8 条逐字节一致） |
| `attempt_s2x_regress_20261014T091950Z_332da3cf` | 回归 PASS（同上） |
| `attempt_s2infra_20261014T023604Z_d2566191` | 描述符/场景基础设施（`private_skeleton_descriptors.json` 等） |

### 7.2 复现命令

```bash
# 单元测试（约 1 s）
cd "Multi-UAV SimpleGC"
conda run -n llm --no-capture-output python -B -m unittest discover -s tests -p "test_v07_s2_expansion.py"

# 固定回归（约 3 min）
conda run -n llm --no-capture-output python -B scripts/run_v07_s2_expansion.py regression --workers 2

# 八个新角色骨架试飞（约 6 min）
conda run -n llm --no-capture-output python -B scripts/run_v07_s2_expansion.py pilot --workers 2 \
  --skeletons family_s12_4d13d93f9171c446_ext_001_regular family_s12_4d13d93f9171c446_ext_002_regular \
              family_s12_4d13d93f9171c446_ext_003_regular family_s12_4d13d93f9171c446_ext_004_regular \
              family_s12_aa4c66be8e85d64d_ext_001_regular family_s12_aa4c66be8e85d64d_ext_002_regular \
              family_s12_aa4c66be8e85d64d_ext_003_regular family_s12_aa4c66be8e85d64d_ext_004_regular

# 规划层冒烟（秒级，只规划不仿真）
conda run -n llm --no-capture-output python -B _tmp_smoke_plan.py
```

---

## 8. 结论与待确认事项

**结论**：第一轮的 3 项要求已完成（审计独立重算、回归 PASS、规划层估算实现）。第二轮的 6 条标准**均未达标**：核心阻塞是**同步版共享走廊碰撞**，其根因是可见图对相近起点终点返回重合航迹，而三条已试的修复路线（时序错开 / 横向偏移 / 分侧偏移）都没能解决。

**待用户确认的方向（三选一或另行指定）**：

1. **走方案 D**（顺序规划 ＋ 走廊排除区）继续攻几何分离；
2. **走方案 F**（把 `4d13d93f` 的拥挤布局记为几何拒绝并统计），只在 `aa4c66be` 上争取达标；
3. 先**回退本轮半成品改动**（尤其是 `role_planners.py` 的车道机制与 `_stagger_delays`），使工作树回到 `5860b099` 那版"能飞但同步版碰撞"的可复现基线，再重新决定路线。

在用户确认前，不继续改动代码。
