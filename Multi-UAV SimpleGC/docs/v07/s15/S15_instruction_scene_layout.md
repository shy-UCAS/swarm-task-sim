# S1.5 场景布局改版：执行指令

放置位置：`docs/v07/s15/S15_instruction_scene_layout.md`
分支：从 `review/m3b-q2-failure@b035dfd66eb45709d400d953caa1692d23c8be63` 新建 `v07-s15`，所有提交推送到 `v07-s15`，不推 `v07-scene`，不使用强制推送。

## 0. 项目性质（照录）

本项目是防御方视角的意图识别研究。生成器只产出抽象随机几何场景中带标签的合成轨迹数据集，运动后端为点质量运动学模型，不控制任何真实无人机。本阶段只修改**抽象场景中设施的相对布局规则**，不涉及任何航线、规划或任务效果。

## 1. 目标与范围

**目标：** 降低设施防御圈层的过度重叠，使"内层互不侵入、外层只允许随机的轻度重叠"，从源头减少与意图无关的规划失败。改版作为新的采样修订 `s1.5`，旧修订 `s1`、`s1.1`、`s1.2` 必须保持逐字节可复现。

**本阶段只做：** S1.5 布局采样、对应的独立检查、单元测试、30 个候选的快速检查、300 个候选的静态生成与统计、代表图，然后停下。

**不做：** S2 骨架登记、任何规划（Q2/Q3）、几何层或规划器代码、M1 判据、M2 时刻逻辑、fastsim、作业段目标唯一性规则（本阶段不加，下一阶段只做诊断统计）。

## 2. 背景事实（来自现有代码，供核对）

- 当前 S1.2 在 `scene_v07/sampling_s11.py`：`facility_count` 为 1/2/3 个设施，概率 0.40/0.35/0.25；`MAP_SIDES_M = {1: 4000, 2: 5000, 3: 6000}`；多设施时布局在 `isolated / clustered / linear` 中等概率抽取。
- 圈层偏移：`d3 ~ U(50,150)`（保护），`d2 = d3 + U(150,400)`（警戒），`d1 = d2 + U(300,800)`（预警）。预警环带宽度 `W = d1 − d2 ∈ [300, 800]` m。
- 拥挤的直接原因在 `_layout_offsets`：`clustered` 与 `linear` 用"基底半径 + 警戒偏移 d2"排布，间隙仅 40–200 m。警戒区几乎相切，预警区则重叠几百米，导致诊断中 197/332 对设施存在内层侵入。
- 执行时长预算由航线长度推出（`task_v07/execution.py` 中 `max_duration_s = latest + margin`），地图放大不会触发固定超时。

## 3. 定义（全部用精确公式，不用多边形近似）

所有圈层都是凸基底（圆或凸多边形）与圆盘的 Minkowski 和。对两设施 i、j 及各自的圈层偏移 `a_i`、`b_j`，定义：

```
base_distance(i, j) = 两个设施基底轮廓之间的欧氏距离（相交时为 0）
signed_gap(i, a_i, j, b_j) = base_distance(i, j) − a_i − b_j
```

`base_distance` 的精确实现：
- 圆–圆：`max(0, |c_i − c_j| − r_i − r_j)`
- 圆–多边形：`max(0, Polygon(vertices).distance(Point(c)) − r)`
- 多边形–多边形：`Polygon(vi).distance(Polygon(vj))`

当两个基底不相交时，`signed_gap` 为正表示两圈层间的真实最短距离，为负表示"两个偏移量需要共同缩小多少才不相交"，即本文所说的**重叠量**。合法布局中基底永不相交（由 R1 保证）。

记 `W_i = d1_i − d2_i`，`W_ij = min(W_i, W_j)`，`g_ij = signed_gap(i, d1_i, j, d1_j)`（预警对预警）。

## 4. 布局规则（定义性约束与执行参数分开）

**R1（定义性，硬约束）：** 对任意有序对 i≠j，`signed_gap(i, d2_i, j, d1_j) > 0`，即任何设施的警戒区（及其内部的保护区）与其他设施的预警区不相交。由 R2 可推出 `R1 余量 ≥ 0.8·W_i`，因此 R1 只作断言，永远不应触发；一旦触发即为实现错误（P0），立即停止。

**R2（定义性，硬约束）：** 对任意无序对，`g_ij ≥ −0.20 · W_ij`，即预警区最多重叠较窄环带宽度的 20%。

**布局类型与执行参数（随机抽取，写入配置）：**

| 布局 | 新设施挂接方式 | 与挂接父设施的目标间距 g* | 对所有设施对的附加检查 |
|---|---|---|---|
| single | — | — | — |
| isolated | 父设施从已放置设施中均匀随机选 | `g* ~ U(40, 0.5·W_pk)` m | 所有对 `g_ij ≥ 40` m |
| clustered | 父设施从已放置设施中均匀随机选 | `g* = −u·W_pk`，`u ~ U(0.02, 0.20)` | 所有对满足 R2；预警重叠图连通（由构造保证，检查器复核） |
| linear | 父设施为上一个设施，挂接方向全链共用同一个 θ | `g* ~ U(−0.20·W_pk, 0.5·W_pk)` | 所有对满足 R2；中心共线（沿用现有检查） |

挂接方向：isolated 与 clustered 每次挂接独立抽 `θ ~ U(0, 2π)`；linear 只在第一次挂接时抽 θ，后续沿用。

## 5. 算法（按此实现，不要自行替换）

### 5.1 局部布局（世界坐标之前）

```
place_layout_s15(rng, local, layout, cfg):
    # local[k] = (contour_k, d3_k, d2_k, d1_k)，contour 以自身形心为原点
    for layout_attempt in 1..cfg.layout_attempts (=128):
        centers = [(0, 0)]
        theta_line = None
        ok = True
        for k in 1..count-1:
            placed = False
            for link_attempt in 1..cfg.link_direction_attempts (=32):
                p = (k-1) if layout == "linear" else rng.randrange(k)
                if layout == "linear":
                    if theta_line is None: theta_line = rng.uniform(0, 2π)
                    theta = theta_line
                else:
                    theta = rng.uniform(0, 2π)
                g_star = 按第 4 节表格从 rng 抽取（W_pk 用 p 与 k 的环带宽度）
                D = g_star + d1_p + d1_k          # 目标基底距离，必为正
                t = bisect_t(p, k, theta, D)      # 见 5.2
                c_k = centers[p] + t·(cosθ, sinθ)
                if 新设施 k 与所有已放置设施满足 R1、R2 与第 4 节的附加检查:
                    centers.append(c_k); 记录挂接信息; placed = True; break
                else: 记录失败原因 (r2_violation / isolated_gap / ...)
            if not placed: ok = False; break      # 整个布局重来
        if ok: return centers, records
    raise SamplingRejected("sampling_layout_s15_exhausted", ...)
```

- 每次挂接记录：`parent`、`theta_rad`、`target_gap_m`、`achieved_gap_m`、`overlap_fraction = −achieved_gap/W_pk`、`link_attempts`。
- `achieved_gap` 与 `target_gap` 之差必须 ≤ 1e-3 m，否则判为实现错误。

### 5.2 二分求放置距离

令 `f(t) = base_distance(基底_p 位于 centers[p], 基底_k 位于 centers[p] + t·u)`。t=0 时两基底同心、互相重叠，f(0)=0；两个凸集在平移下的距离是 t 的凸函数，所以 f 在 t ≥ 0 上单调不减，二分有效。

```
bisect_t(p, k, θ, D):
    lo = 0; hi = R_p + R_k + D + 1      # R 为基底外接半径（_radius），保证 f(hi) ≥ D
    重复 60 次: mid = (lo+hi)/2; if f(mid) < D: lo = mid else hi = mid
    return hi
```

### 5.3 地图尺寸与整体放置

1. 计算局部布局中所有预警区的精确外包矩形：圆为 `center ± (r + d1)`；多边形为顶点坐标极值 `± d1`。
2. `required = max(宽, 高) + 2·edge_clearance_m`，其中 `edge_clearance_m = 350`（≥ 撤离上限 300 m + 世界余量 35 m + 15 m 余量）。
3. `map_side = max(MAP_SIDES_M[count], ceil(required / 250) · 250)`；若 `map_side > 8000`，记为 `layout_exceeds_max_map`，回到 5.1 重抽布局（计入 layout_attempts）。
4. `config = replace(config, map_side_m = map_side)`，然后调用现有 `_entries(rng, config)` 生成入口。
5. 锚点：`anchor_x ~ U(edge − xmin_local, side − edge − xmax_local)`，y 同理；全部中心加上锚点。
6. 沿用现有检查：任一预警区到任一入口距离 ≤ `safety_margin_m` 则重抽锚点（最多 32 次，耗尽则回到 5.1）。在 350 m 边距下这条理论上不会触发，触发次数要记录。

### 5.4 其余部分

设施实体与圈层构造、障碍物（`place_obstacles_s12`）、雷达、编队数量、高度、速度、横向间距、初始状态、观测噪声参数，**全部沿用 s1.2 的写法与参数**，不做任何修改。

## 6. 代码落点

| 文件 | 改动 |
|---|---|
| 新建 `configs/scene/scene_s15_layout_r1.json` | 第 4、5 节的全部数值：`warning_overlap_max_fraction: 0.20`、`clustered_overlap_fraction: [0.02, 0.20]`、`isolated_gap_m: [40, "0.5*W"]`、`linear_gap_fraction: [-0.20, 0.50]`、`edge_clearance_m: 350`、`map_side_quantum_m: 250`、`max_map_side_m: 8000`、`layout_attempts: 128`、`link_direction_attempts: 32`、`anchor_attempts: 32`；每项注明"定义性约束"或"执行参数"及来源 |
| 新建 `scene_v07/layout_s15.py` | `base_distance`、`signed_gap`、`bisect_t`、`place_layout_s15`、`warning_bbox` 等纯函数 |
| 新建 `scene_v07/sampling_s15.py` | `sample_family_s15(seed, config, policy)`：按 5.1→5.3→5.4 组装。5.4 部分从 `sample_family_s11` **复制**相应代码段，不重构、不修改 `sampling_s11.py`。`revision="s1.5"`，`family_id = f"family_s15_{seed:016x}"`，`map_id = f"map_s15_{seed:016x}"`，`generator_version = "traj2language.scene_sampler/0.7-s1.5"`；family 中写入 `layout_s15`（挂接记录、尝试次数、失败原因）、`layout_config_sha256`、`map_side_m` |
| `scene_v07/sampling.py` | `sample_family` 分派增加 `"s1.5"`，其余分支不变 |
| `scene_v07/checks.py` | 仅当 `family["sampling_revision"] == "s1.5"` 时，增加独立检查：R1（所有有序对）、R2（所有无序对，容差 1e-6 m）、isolated 所有对 `g ≥ 40 − 1e-6`、预警区到世界边界 ≥ 350 − 1e-6 m；新问题代码分别为 `s15_inner_layer_intrudes_warning`、`s15_warning_overlap_exceeds_bound`、`s15_isolated_gap_below_min`、`s15_warning_edge_clearance`。检查器必须自己重算距离，不读取采样记录。其余现有检查照常运行 |
| `scene_v07/batch.py`、`scripts/sample_v07_scenes.py` | 允许 `--sampling-revision s1.5`，`SamplingPolicy` 原样传入；summary 中 `map_side_by_facility_count_m` 在 s1.5 时写 `null`，并新增 `map_side_m` 分布 |
| 新建 `scripts/summarize_v07_s15.py` | 只读统计，见第 8 节 |
| 新建 `tests/test_v07_scene_s15.py` | 见第 7 节 |

**不得修改：** `SamplingPolicy` 的字段（新增字段会改变 s1.2 family JSON 的 `sampling_policy`，破坏可复现性）、`sampling_s11.py` 的逻辑、公共场景 schema、`task_v07/` 下任何文件、`configs/criteria`、`configs/generator`、`configs/fast_dynamics`。

## 7. 测试（测试预期由本指令给定，不得修改）

1. **精确距离**：圆–圆、圆–多边形、多边形–多边形各一组手算用例，`base_distance` 误差 ≤ 1e-9 m。
2. **二分**：随机 200 组（固定种子）基底对和目标 D，`|f(t) − D| ≤ 1e-3` m，且 t 为满足条件的最小值（检查 `f(t − 0.01) < D`）。
3. **R2 边界**：构造 `g = −0.20·W + 0.01` 与 `g = −0.20·W − 0.01` 两个用例，检查器分别 PASS、报 `s15_warning_overlap_exceeds_bound`。
4. **R1 推导**：对 1000 个随机满足 R2 的设施对，断言 R1 余量 ≥ `0.8·W_i − 1e-6`。
5. **各布局**：每种布局固定种子各 20 个家族，采样器输出通过检查器的全部 s1.5 检查；clustered 的预警重叠图连通；linear 中心共线。
6. **旧修订不变**：对 s1、s1.1、s1.2 各取 5 个固定种子，改动前后的 public scene 与 family JSON 的 `canonical_json` SHA256 完全一致（改动前先生成基准值存入测试数据）。
7. **地图尺寸**：所有 s1.5 家族 `map_side ≤ 8000`、为 250 的整数倍、`≥ MAP_SIDES_M[count]`，所有预警区到边界 ≥ 350 m。

M1/M2/M3 的既有短测试全部重跑通过（证明本阶段没有影响下游代码）。

## 8. 运行与止损（先快查，再全量）

主种子：读取现有登记源 `attempt_s12_20261013_s2_vertical` 中 `provenance.json` 的 `master_seed`，s1.5 使用同一主种子与候选编号，以便逐编号对比。

**第 1 步：快速检查（≤ 3 分钟）。** 30 个候选，无绘图。以下任一情况即停下汇报：
- 出现任何 R1 或 R2 违反（P0：实现错误）；
- 接受率 < 70%；
- 任何 s1.2 回归测试失败。

**第 2 步：全量静态生成（预计 15–30 分钟，含绘图）。** 300 个候选，`attempt_s15_<UTC>`，输出在仓库外原数据根目录。完成后运行 `summarize_v07_s15.py`，写入 `docs/v07/evidence/s15/s15_scene_summary.json`，内容包括：
- 接受数、拒绝数及原因分布（含 `sampling_layout_s15_exhausted`、`layout_exceeds_max_map`、锚点重试次数）；
- 设施数与布局分布（与 s1.2 登记源对比）；
- 每种布局下，所有设施对与挂接对的 `g_ij / W_ij` 分布（min/p25/median/p75/max），以及按诊断口径的分档计数（重叠 >50%、0–50%、留空 0–200 m、>200 m），与 s1.2 并列；
- R1 余量最小值（应 ≥ 0.8·W）；
- `map_side_m` 分布，按设施数分列；
- 每个入口到每个设施预警区边界的直线距离分布（p50/p90/max），与 s1.2 对比；
- 现有 `check_family` 的路线诊断（绕行比、可达角跨度）与 s1.2 对比；
- 每个阶段的墙钟时间。

代表图：沿用 `select_representatives`，另保证每种布局（isolated/clustered/linear）各至少 3 张、3 设施至少 3 张，复制到 `docs/v07/evidence/s15/gallery/`（PNG 总大小超过 20 MB 时只提交缩略图，原图留在外部目录）。

## 9. 提交与报告

提交顺序（每项单独提交，提交信息以 `S15-` 开头）：
1. `S15-1` 配置文件与 `layout_s15.py`，附测试 1–4；
2. `S15-2` `sampling_s15.py`、分派与批处理接线，附测试 5–7（含 s1.2 基准）；
3. `S15-3` 检查器的 s1.5 检查；
4. `S15-4` 统计脚本、快速检查与全量结果证据、代表图、报告。

报告写入 `docs/v07/s15/S15_report.md`：结论、异常、证据路径，以及"与 s1.2 的差异"一节。完成后推送 `v07-s15`，报告提交范围与远端 HEAD 完整 SHA，然后**停下等待用户审查代表图与统计**。用户确认后，S1.5 冻结；S2 骨架重建与 Q2 属于下一阶段，另行下达指令。

## 10. 规则

- 本指令给定的数值、算法、检查口径和测试预期不得自行修改；如认为不可行，停下并给出证据。
- 自编工具脚本中的编程错误（路径、字段名、格式）直接修复并在报告"异常"中记录，不必停下。
- 只在以下情况停下：R1/R2 违反、s1.2 回归失败、快速检查接受率 < 70%、需要修改第 6 节"不得修改"清单中的内容、全量墙钟超过 60 分钟。
- 开工前写约半页 `docs/v07/s15/00_restatement.md`（拟改文件、主种子来源、发现的冲突）。**若无冲突，写完直接继续执行**；有冲突则停下汇报。
