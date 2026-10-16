# 阶段 2：S1.5 上现有规划器体检报告（只规划、只统计）

## 结论

在冻结的 S1.5 地图上，用既有规划器完成 160 个骨架的纯规划检查：**160/160 落盘完成，141 成功、19 拒绝**，42000 条组提案中 10282 条被拒。没有任何骨架以异常结束，没有触发 `P0ContractError`，两次规划的源码指纹在各自运行前后均一致，按 4.3 无法解析的被拒提案为 0 条。

本阶段只做规划与统计，不涉及仿真、任务效果或任何针对防御的优化。结论由审查方写；本报告只记录执行、数字、异常与处理。

## 执行了什么

### 开工前核对

```
git diff --quiet b035dfd66eb45709d400d953caa1692d23c8be63 HEAD -- task_v07 configs/generator   # 无差异（exit 0）
```

Python 3.12.3 / NumPy 2.5.3 / Shapely 2.0.7，Conda 环境 `llm`。

### 命令

```
# 第 1 步：骨架登记（登记规则 6/层）
scripts/run_v07_s15_descriptors.py
# 第 1 步（复跑）：按第 5.1 条降级为 4/层
scripts/run_v07_s15_descriptors.py --per-layer 4

# 第 2 步：快速检查
scripts/run_v07_s15_yield.py --descriptors <desc-6> --limit 16 --wall-limit-s 600
# 第 2 步：正式批次
scripts/run_v07_s15_yield.py --descriptors <desc-4> --wall-limit-s 2700
# 第 6 条：单骨架 cProfile（正式批之后、续跑之前）
scripts/run_v07_s15_yield.py --descriptors <desc-4> --profile --profile-from <yield-formal>
# 第 2 步：续跑（清单按磁盘状态生成）
scripts/run_v07_s15_yield.py --descriptors <desc-4> \
    --skeletons-file <SwarmData>/v07_dataset/s15_resume_list_after_formal.json --wall-limit-s 5400

# 第 3 步：统计（多 attempt）
scripts/summarize_v07_s15_yield.py --descriptors <desc-4> \
    --yield <yield-formal> --yield <yield-resume>
scripts/summarize_v07_s15_yield.py --descriptors <desc-6> --yield <yield-quick> \
    --out-dir docs/v07/evidence/s15/quick_check
```

### 外部目录路径

| 用途 | 路径 |
|---|---|
| 描述目录（登记规则 6/层，240 条） | `<SwarmData>/v07_dataset/attempt_s15desc_20261016T153508Z` |
| 描述目录（第 5.1 条降级为 4/层，160 条） | `<SwarmData>/v07_dataset/attempt_s15desc_20261016T154909Z` |
| 快速检查 | `<SwarmData>/v07_dataset/attempt_s15yield_20261016T153520Z` |
| 正式批次 | `<SwarmData>/v07_dataset/attempt_s15yield_20261016T154921Z` |
| 续跑 | `<SwarmData>/v07_dataset/attempt_s15yield_20261016T163901Z` |
| cProfile | `<SwarmData>/v07_dataset/attempt_s15profile_20261016T163627Z` |
| 续跑清单 | `<SwarmData>/v07_dataset/s15_resume_list_after_formal.json` |

`<SwarmData>` = `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData`。上述目录均在仓库外，仓库内未写入任何规划样本或原始日志。

### 选中的 family

登记规则要求 24 个（四层各取 `candidate_index` 最小的 6 个）。快速检查的 16 个骨架平均墙钟 194.04 s，按 240 个骨架 / 8 进程估算约 97 min，超过第 5.1 条的 45 min，因此按该条把每层地图数降到 4，重新登记后用 16 个 family 跑正式批次。

**登记规则下的 24 个**（`attempt_s15desc_20261016T153508Z`）：

| layout | candidate_index / family_id | | | | | |
|---|---|---|---|---|---|---|
| single | 8 `family_s15_aa4c66be8e85d64d` | 11 `…cd16b042e6f088bd` | 18 `…f2adfbfae12fbbad` | 21 `…1b876e6b8b6f70c6` | 22 `…99b8c096f6bd0827` | 23 `…2721c479bd7f7340` |
| isolated | 4 `family_s15_8412c1cdb40e54b1` | 6 `…8e012bf033eb6821` | 12 `…fac1d381571b4d36` | 15 `…7a34c19b154f1faf` | 17 `…885e374f07b6a9d8` | 28 `…19d00d7e8a2f9e99` |
| clustered | 1 `family_s15_79c93b22d09e8a7a` | 2 `…38bedc9d791d547b` | 3 `…c713f51898e81011` | 5 `…1c267d4d7000043d` | 7 `…0aeede8b1f29217e` | 10 `…4d13d93f9171c446` |
| linear | 0 `family_s15_ef1ed9ff0b0e7013` | 9 `…5024cb2ccea653ae` | 13 `…7b73a7fc210d4c8f` | 20 `…ffbbf066d62e3e2f` | 25 `…bd4c42a65f2b1c1e` | 29 `…821cecaf77da180a` |

**正式批次实际使用的 16 个**（`attempt_s15desc_20261016T154909Z`，各层 `candidate_index` 最小的 4 个）：

| layout | candidate_index / family_id | | | |
|---|---|---|---|---|
| single | 8 `family_s15_aa4c66be8e85d64d` | 11 `…cd16b042e6f088bd` | 18 `…f2adfbfae12fbbad` | 21 `…1b876e6b8b6f70c6` |
| isolated | 4 `family_s15_8412c1cdb40e54b1` | 6 `…8e012bf033eb6821` | 12 `…fac1d381571b4d36` | 15 `…7a34c19b154f1faf` |
| clustered | 1 `family_s15_79c93b22d09e8a7a` | 2 `…38bedc9d791d547b` | 3 `…c713f51898e81011` | 5 `…1c267d4d7000043d` |
| linear | 0 `family_s15_ef1ed9ff0b0e7013` | 9 `…5024cb2ccea653ae` | 13 `…7b73a7fc210d4c8f` | 20 `…ffbbf066d62e3e2f` |

16 个 family × 2 抽签槽 × 5 意图 = 160 个骨架；每 family 另有 1 条 `aborted` 描述被丢弃，共 16 条。

## 运行状态与墙钟

| 批次 | 计划 | 完成 | 状态 | 墙钟 | 上限 | 运行前后指纹一致 |
|---|---:|---:|---|---:|---:|---|
| 快速检查（16 骨架） | 16 | 15 | `TIME_LIMIT_STOP` | 600.1 s | 600 s | 是 |
| 正式批次（160 骨架） | 160 | **99** | `TIME_LIMIT_STOP` | 2700.1 s | 2700 s | 是 |
| 续跑（61 骨架） | 61 | **61** | `completed` | 3889.6 s | 5400 s | 是 |
| cProfile（1 骨架） | 1 | 1 | 状态 PASS | 131.3 s | — | 是 |

正式批与续跑合计 **160/160** 完成，两次墙钟合计 6589.7 s。续跑清单由磁盘状态（`<attempt>/<skeleton_id>/planning_result.json` 是否存在）生成，共 61 条；与正式批 `run_result.json` 声明的 `unfinished` **完全一致**，无差异，因此没有产生 `attempt_completion_disagreement` 异常。

## 表格

T1–T6、T6b 与附录 A 全文见 [s15_yield_tables.md](s15_yield_tables.md)（机器可读版本见 [s15_yield_summary.json](s15_yield_summary.json)）。要点：

- 骨架成功率 141/160（88.13%）；按意图×布局见 T1，其中 `reconnaissance` 在 `single` 与 `linear` 两列为 4/8（50.00%），其余三意图多数为 7/8–8/8。
- 组提案接受率 31718/42000；`reconnaissance/area_search` 在 `single` 为 365/1200、`linear` 为 586/1600，而 `reconnaissance/close_observation` 同布局为 365/400 与 597/600（T3）。
- 被拒提案归因（T4）多标签合计：`reconnaissance/area_search` 的 1837 条证据指向其**自身目标**（`target_facility`），是全表最大单类；`transit/transit` 的 2558/2693 与 `monitoring/monitoring` 的 2318/3374 未收集到实体 ID，记为 `unattributed:<reason>`（全表 7067/10282）。
- 每骨架规划墙钟（T6）：全体中位数 91.24 s、p90 397.18 s、最大 2991.33 s；`reconnaissance` 的 p90 为 2049.02 s，`monitoring` 中位数 266.68 s。
- T5：160 个骨架中 141 个有 `selected_skeleton.json`；可测 **110** 个，**进入非目标预警区的为 0 个**。40 个单设施骨架记 `not_applicable`（其中 31 个有该文件，另 9 个因被拒而无该文件）；19 个骨架无 `selected_skeleton.json`（全部 19 个即被拒骨架），按 4.4 不统计，在 T5 单元格中以 `[not_counted n]` 标出。作业段扫描覆盖 912 名成员，其中 225 名的 `work_points_enu_m` 只有 1 个点。
- 附录 A（按公共抽签）：32 次抽签中 20 次全成功、1 次全失败、11 次部分成功；**抽签口径产量 20/32 = 62.5%**，按布局分别为 single 4/8、isolated 6/8、clustered 6/8、linear 4/8。11 次部分成功的抽签中有 9 次含 `reconnaissance` 失败，其组层终止原因几乎都是 `shape_search_budget_exhausted`（充满 200 次预算）。
- cProfile（[s15_planning_profile.txt](s15_planning_profile.txt)）：选中 `family_s15_79c93b22d09e8a7a_ext_006_regular`（该批已完成骨架的墙钟中位数 95.61 s，该骨架即中位数本身）；223038080 次函数调用中 `geometry_facts` 1733071 次累计 123.4 s（约 94%），其中 `visibility.visible` 402033 次累计 99.0 s。

## 异常与处理

### 运行与协议

1. **快速检查触发 `TIME_LIMIT_STOP`（15/16，600 s）**。第 5.1 条未把超时列为停止条件，故按该条继续；未完成的那 1 个骨架不进统计分母，也不参与其被中断的 `proposals.jsonl`。
2. **45 分钟估算超限**。快速检查 16 个骨架平均墙钟 194.04 s，240 个骨架 / 8 进程估算约 97 min，按第 5.1 条把每层地图数从 6 降到 4（各层仍取 `candidate_index` 最小的 4 个），重新登记后跑正式批次。正式批次仍以 `TIME_LIMIT_STOP` 结束（99/160），故按补充指令 1 不用部分结果出最终统计，改以续跑补齐。
3. **`facility_count` 不在 `family_initial.json` 中**（该文件键为 config、cruise_speed_m_s、facility_sampling、family_id、generator_version、initial_states、lateral_spacing_m、layout、layout_config_sha256、layout_s15、map_id、map_side_m、observation_profile、obstacle_placements、obstacle_sampling、radar_placements、sampling_policy、sampling_revision、sampling_seed、schema_version、task_altitude_m、vehicle_count）。改以 `public_scene.json` 中 `type == "facility"` 的实体数为准，并与 `candidates.json` 的 `facility_count`、`len(family_sampling.links) + 1` 三方交叉核对；24 个与 16 个 family 上交叉核对异常均为 0。
4. **`selected_skeleton.json` 中 `"references"` 出现两次**（顶层与 `group_skeletons[gid]` 下，内容相同）。按 agent 去重合并，成员到组的归属由描述的 `task_groups` 判定，避免同一成员被计两次。
5. **`rejection` 字段**：本阶段走 unified 后端，实测 42000 行 `proposals.jsonl` 中 `rejection` 0 缺失，按 4.3 无法解析的比例 0.0000%，未触发 5% 止损。
6. **多 attempt 的源码指纹差异**：统计脚本逐条比对各 attempt 的 `runtime_sha256` 中 `task_v07/` 与 `configs/` 前缀条目，完全一致；`scripts/` 下有 2 处差异，属预期（续跑与统计用新代码），已列出：

| 路径 | 正式批 | 续跑 |
|---|---|---|
| `scripts/run_v07_s15_yield.py` | `47ee1642…` | `2ee2f8fa…` |
| `scripts/summarize_v07_s15_yield.py` | `6216a0d0…` | `46ba0df6…` |

### 口径

7. **单点作业段**：225 名成员的 `work_points_enu_m` 只有 1 个点。按 4.4 的登记判据（`intersects` 且交集长度 > 1e-6 m）字面执行——单点连成的折线长度为 0，必然判为未进入，使每名成员都留在分母内；同时按 `single_point_work_set` 逐条记录，并另计"该单点落在非目标预警区内"的成员数（0 名）。
8. **单设施地图**：按 4.4 记为 `not_applicable`（逐骨架输出与 T5 单元格口径一致）。40 个骨架属此类。
9. **T5 的非统计情形**：无 `selected_skeleton.json` 记 `[not_counted n]`（按 4.4 只统计有该文件的骨架），找不到 `references` 或 `work_points_enu_m` 记 `[not_available n]`。本次逐骨架状态为 measured 110、not_applicable 31、not_available 19，其中 19 个 `not_available` 全部是"缺 `selected_skeleton.json`"（即被拒骨架），故在 T5 单元格中一律显示为 `[not_counted n]`，没有单元格出现 `[not_available n]`；`warning_members_unavailable` 为 0，即所有在册成员的 `work_points_enu_m` 都取到了。
10. **`--limit 16` 只覆盖字典序最小的 2 个 family**（每个 family 10 条描述），因此快速检查的布局覆盖有限，只作冒烟与计时用途，不代表批次。最终表格不使用快速检查的数据。
11. **附录 A 的抽签分类增设两类**：`未完成`（5 个意图都在范围内但未全部测到）与 `范围不全`（少于 5 个意图在范围内，只出现在限定范围的运行中）。补充指令只给了三类，但这两类若不入表只能被丢弃，与补充指令 4 冲突，故单列并仍留在分母内。最终 32 次抽签中两类均为 0。
12. **A5（全失败抽签）为追加内容**：补充指令只要求列部分成功抽签，但全失败抽签恰有 1 个（`family_s15_1b876e6b8b6f70c6` slot0），不列出则该格不可读，已在表中注明。

### 只读核实：单组 intrusion + `same_direction` 在形态阶段全败

`intrusion_shape` 按成员 lane 逐个检查，遇到第一个不可达的 lane 即抛出，因此最外侧成员决定整次抽签。lane 距轴线 `(最宽侧成员数−1)/2 × lateral_spacing_m`，从 lane 出发的平行内射射线要触及目标外扩轮廓需 `signed ≥ 半跨度 − R`，而 `signed ~ U(−10, 25)`（`configs/generator/geometry_v07_r1.json` 的 `endpoint_distance_m`）。只读读取记录到的拒绝码并复算：

| 骨架 | mode | 成员数 | spacing | 半跨度 | 目标设施基底 | 可用 reach = R+25 | 所需 signed | 预测每次抽签命中率 | 实测 |
|---|---|---:|---:|---:|---|---:|---:|---:|---|
| `…8b6f70c6_ext_004` | same | 10 | 17.890 | 80.50 | Circle R=53.53 | 78.53 | 26.97（>25） | 0.00% | 4000/4000 形态失败，0.44 s，拒绝 |
| `…791d547b_ext_004` | same | 7 | 19.198 | 57.59 | Circle R=33.00 | 58.00 | 24.59 | 1.16% | 4000/4000 失败，0.49 s，拒绝 |
| `…154f1faf_ext_004` | same | 9 | 23.942 | 95.77 | Circle R=28.04 | 53.04 | 67.73（>25） | 0.00% | 4000/4000 失败，0.57 s，拒绝 |
| `…b40e54b1_ext_004` | same | 11 | 20.879 | 104.39 | Polygon 平均半径 85.73 | 110.73 | 18.66 | 18.10% | 3960 次失败，仅 2 个合格提案，11.1 s，通过 |
| 对照 `…8b6f70c6_ext_009` | **multi** | 10 | 17.890 | 26.83（分 3 侧） | Circle R=53.53 | 78.53 | −26.70 | 100% | 0 次形态失败，59.8 s，通过 |
| 对照 `…154f1faf_ext_009` | same | 5 | 23.942 | 47.88 | Polygon 平均半径 28.58 | 53.58 | 19.30 | 16.29% | 2854 次失败，28.0 s，通过 |

两点佐证：四个骨架中唯一预测命中率非零的那个正是唯一通过的；拒绝码分布亦吻合——`intrusion_interior_unavailable` 只由 `signed < 0` 触发，理论占比 `10/35 = 28.57%`，三个全败骨架实测 27.4%、27.95%、28.45%。按第 1 节仅记录，未修改规划器。

### 自编脚本的编程错误（按第 7 节直接修复，均未在任何批次运行前进入证据）

13. `summarize_v07_s15_yield.py` 统计 T3 角色集合时误用骨架级 `rows`，会 `KeyError: 'role'`；改为从组提案行取角色集合。
14. 同一脚本的 markdown 表头未字符串化，`facility_count` 为整数列时会 `TypeError`；改为统一字符串化。
15. 同一脚本的附录 A1 在"抽签组不足 5 个意图"（限定范围运行）时会 `KeyError`；改为区分"不在范围内"与"在范围内但未测到"。

三项均由提交前的独立复核或端到端夹具发现，修复后经 5 组夹具（单/双 attempt、含未完成、含范围不全）与真实快查、真实正式批各跑通一次。

## 提交范围

| 提交 | 内容 |
|---|---|
| `3973009` S15-Y0 | 登记阶段 2 指令与执行复述 |
| `e406821` S15-Y1 | 骨架登记脚本 |
| `a88fa30` S15-Y2 | 批量规划脚本 |
| `0df3400` S15-Y3 | 统计脚本 |
| `069e4c4` S15-Y1b | 登记脚本支持 `--per-layer` |
| `dc3fcc5` S15-Y3b | 单点作业段按登记口径判定 |
| `4c2ba52` S15-Y2b | 续跑入口与 cProfile 模式 |
| `baf7291` S15-Y3c | 多 attempt 统计、未完成口径、抽签附录 |
| `8eb4523` S15-Y4a | 单骨架 cProfile 证据 |
| 本提交 S15-Y4 | 快速检查与正式批次证据、抽签附录、本报告 |

分支 `v07-s15`；未推送到 `v07-scene`，未使用强制推送。
