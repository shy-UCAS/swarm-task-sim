# V8-01 首版诊断报告

- 工作项：V8-01（里程碑 ① 首版诊断）；执行日期 2026-10-30；执行方：Claude Code（Windows 主机）。
- 依据：`_handoff/2026-10-29_V8-01_baseline-diagnosis/V8-01_首版诊断_执行指令_20261029.md`。
- 本目录（`out/`）中的明细文件：`field_inventory.md`、`timing_records.csv`、`timing_summary.md`、`prior_profiling.md`、`failures.md`、`rejection_samples.md`、`rejection_subreasons.md`、`code_map.md`、`stage_timing.md`、`profile_sim_transit.txt`、`profile_plan_monitoring.txt`；脚本在 `../scripts/`。重跑产物在 `out/rerun/`（不提交）。
- 数据路径一律相对数据根目录 `SwarmData`；代码路径相对 `Simulation-fe-prod-r3/Multi-UAV SimpleGC/`。

---

## 0. 复述与环境

### 0.1 任务复述

本任务为下一代生成器（v0.8）收集事实：时间花在哪、失败在哪、仿真器能接收什么输入、判据能否按时间窗口使用、首版写死的衔接段在哪里。三个部分：第 3 部分只读汇总 `v07_first_edition` 9 个批次的现有记录（字段清点、耗时总表、已有剖析、失败细节）；第 4 部分只读 `Simulation-fe-prod-r3` 的代码（调用链、写死的衔接段与预算、fastsim 接口、判据）；第 5 部分在隔离目录里小规模重跑（隔离可行性检查、5 个样本分环节计时、2 个 cProfile、仿真续跑实验）。停止条件：任何时刻发现 `SwarmData\v07_*` 或冻结工作树被写入就全部停止并保留现场；若隔离重跑不可行则跳过第 5 部分其余步骤。不得修改：冻结生成器 `Simulation-fe-prod-r3`、`Simulation-fe-s3`（不读不碰）、`SwarmData\v07_*` 下一切数据、conda `llm` 环境（不装不升级包），以及判据/配置/仿真参数。报告只写事实，个人判断放在最后一节。

### 0.2 第 1 节：环境与路径核对

| 项 | 结果 |
|---|---|
| `SwarmData` | 真实目录（不是联接） |
| `SwarmData\v07_first_edition` | 联接 → `D:\T2L\SwarmData\v07_first_edition` |
| `SwarmData\v07_first_edition_logs` | 联接 → `D:\T2L\SwarmData\v07_first_edition_logs` |
| `main` 头提交 | `bb262b3`（与预期一致） |
| `Simulation-fe-prod-r3` | `fe/production-r3` @ `641a9b3`（与预期一致）；`status --porcelain` 为空 |
| 开发工作树（改名前） | `Simulation-r13`，分支 `dev/r1.3` @ `bb262b3` |
| conda `llm` | Python 3.12.3（conda-forge）、numpy 2.5.3、scipy 1.14.1、shapely 2.0.7；**装有 numba 0.61.2**。导入 scipy 时打印警告 "A NumPy version >=1.23.5 and <2.3.0 is required for this version of SciPy (detected version 2.5.3)" |
| CPU | AMD Ryzen 9 9950X3D，16 核 / 32 逻辑处理器 |
| 内存 | 63.7 GB（检查时可用 32.3 GB） |
| 剩余空间 | D: 1326.7 GB；F: 730.6 GB |

`git worktree list --porcelain`（改名前）：

```
worktree F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-dev
HEAD bb262b3b8e679613ce6c13ff205c15fd88b1d10d
branch refs/heads/main

worktree F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-fe-prod-r3
HEAD 641a9b3a851fb0494f13a479ef0a6df5a0f17f79
branch refs/heads/fe/production-r3

worktree F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-fe-s3
HEAD de4d115b63e617bea9cd23ba716d4ca508d7f28e
branch refs/heads/fe/s3-language-loader

worktree F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-r13
HEAD bb262b3b8e679613ce6c13ff205c15fd88b1d10d
branch refs/heads/dev/r1.3
```

另：`Simulation-fe-int` 目录存在但不是 git 工作树；`SwarmData` 下 `v07_final_test_20261028` 与 `v07_l1` 是真实目录，其余 `v07_*` 均为指向 `D:\T2L\SwarmData\…` 的联接。

### 0.3 第 2 节：开发工作树改名

**结论：已完成。** 三项前提都满足：工作树无改动、无未跟踪文件（含 `--ignored` 也为空）；`origin/dev/r1.3..dev/r1.3` 为 0 个提交，且 `git ls-remote` 显示远端 `dev/r1.3` = `bb262b3`；`dev/r1.3` 头提交 = `main` = `bb262b3`。

- `git worktree move … Simulation-r13 … Simulation-v08`：成功（未用 `--force`）。
- `git branch -m dev/r1.3 dev/v0.8`：成功。
- `git push -u origin dev/v0.8`：成功，远端新建 `dev/v0.8` = `bb262b3`。
- **远端旧分支 `dev/r1.3` 仍然存在**（`git ls-remote` 显示 `refs/heads/dev/r1.3` = `bb262b3`），按指令未删除。
- 附注：本仓库 `remote.origin.fetch` 只登记了 `main`、`viz/ppt-animations`、`wip/episode-player`、`dev/r1.3` 四条精确 refspec，没有 `dev/v0.8`，因此本地没有 `refs/remotes/origin/dev/v0.8`，`git rev-parse dev/v0.8@{upstream}` 报 "upstream branch … not stored as a remote-tracking branch"；分支配置 `branch.dev/v0.8.remote=origin`、`merge=refs/heads/dev/v0.8` 已写入。未修改 fetch 配置。

### 0.4 停止条件

**未触发任何停止条件。**

- 冻结工作树：§5.1 前后、§5 全部运行后，`git -C Simulation-fe-prod-r3 status --porcelain` 均为空（最终输出见文末）。
- `SwarmData\v07_*`：运行前快照 `out/rerun/snapshot_before.json`（各 `v07_*` 目录的文件数、总字节、最新修改时间）；§5.1 后快照 `snapshot_after_51.json` 与之完全相同；全部重跑后的最终快照见文末。
- §5.1 判定"可以在隔离目录中重跑"，第 5 部分全部执行。

---

## 1. 时间花在哪

### 1.1 全量记录（`timing_summary.md`）

**结论：仿真阶段占记录耗时的 79%，监视意图一项占 50%；全部记录耗时中 18.4% 花在最终未保留的抽签上。** 口径：`status/B__*.json` 的 `planning_wall_s` 与 `status/C__*.json` 的骨架级 `elapsed_wall_s`；仿真耗时**按方式分开记录**（每个方式行有 `simulation_wall_s`、`amortized_skeleton_setup_s`、`episode_postprocess_wall_s`），因此没有合并为 `both`。"同步仿真耗时" = 同步行的 `simulation_wall_s`。所有耗时是 14 进程并行生产时的单进程墙钟。

| 意图 | B 规划中位数 s | B p90 | B 合计 h | C 骨架合计中位数 s | C p90 | C 合计 h | 同步仿真中位数 s | 合计 h | 占全部 |
|---|---|---|---|---|---|---|---|---|---|
| transit | 33.6 | 78.8 | 6.82 | 224.7 | 436.6 | 34.79 | 59.6 | 41.6 | 9.8% |
| reconnaissance | 53.7 | 474.8 | 26.22 | 270.6 | 567.8 | 44.65 | 66.1 | 70.9 | 16.7% |
| monitoring | 198.3 | 384.8 | 36.09 | 1,196.6 | 2,160.6 | 176.02 | 293.1 | 212.1 | 50.0% |
| feint | 53.9 | 112.4 | 10.33 | 235.5 | 447.5 | 36.21 | 63.6 | 46.5 | 11.0% |
| penetration | 39.4 | 123.4 | 8.91 | 237.4 | 657.0 | 44.37 | 63.3 | 53.3 | 12.6% |
| 合计 | | | 88.37 | | | 336.04 | | 424.4 | |

（p99、最大值及各方式分项见 `timing_summary.md` §1。）

- **仿真阶段内部**（有三项记录的骨架之和）：准备（候选池载入 + 单机预演 + 时刻安排 + 写盘）37–45%，两个方式的联合仿真 48–54%，后处理（判定 + 写盘 + 审计）4–12%（监视 12.0%），其余 ≤0.6%（`timing_summary.md` §1.1）。
- **规划阶段内部**（只有进入 C 的骨架留下分项）：各组提案池 98.7–99.7%，组合搜索 0.3–1.2%（§1.2）；提案池内部形态/衔接/整航线检查各占多少，生产记录没有分项。
- **机数分档**（同步仿真中位数，s）：4–5 / 6–8 / 9–12 机分别为 transit 38.8/57.1/85.9，reconnaissance 46.5/64.3/87.4，monitoring 179.2/285.3/431.5，feint 41.4/60.2/92.5，penetration 36.7/57.9/89.6（§2）。
- **白费的时间**（§3）：并集占全部记录耗时 18.4%（78.0 h）；分意图 transit 16.4%、reconnaissance 24.5%、monitoring 16.9%、feint 18.2%、penetration 17.9%。其中 (a) B 拒绝的规划 0.7%，(c) C 未配对的仿真 4.7%，(b) 未保留抽签的全部 18.4%；(a)(c) 都包含在 (b) 内。(b) 中最大的一块是"本意图 C 已配对、但抽签因其他意图失败"的仿真耗时（例如 monitoring 19.65 h）。全部批次没有 TIMEOUT 或 ERROR 状态。
- **口径对账**（§4）：记录耗时之和 ÷ 14 = 30.31 h，`stats.json` 的 `total_wall_s` 合计 = 33.89 h，比值 **0.895**；各批 0.567（`pilot_f000_005`）至 0.976。
- 未计入：`prod_f060_100/_aborted`、`prod_f100_140/_aborted` 中续跑前被挪走的半成品，没有对应的 status 记录。`pilot_f000_005`（提交 `debfadf6`）的数字单列在 §6，汇总中已包含。

### 1.2 抽样实测（§5.2，`stage_timing.md`）

**结论：规划时间主要花在提案的衔接段（过境、侦察、佯动、突防 40–73%）或形态 + 整航线检查 + 既有输出预检（监视三者各约 30%）上；同步方式的仿真阶段约 54–58% 是单机预演，38–41% 是联合仿真，判定、审计和写盘合计不到 6%。重跑的耗时约为原记录的 0.54–0.68 倍。**

选样：每个意图在全部保留骨架中取 |ln(B/B中位)| + |ln(C同步/C同步中位)| 最小者（C同步 = 同步行 `simulation_wall_s`）。并行 5 进程，每进程单线程；规划直接调用 `worker_b`，仿真阶段按 `run_episode_job` 步骤只跑同步方式。重跑的规划结果是否与原记录逐键一致只在 §5.1 的样本上核对过（一致）；这 5 个样本未逐键比对。

| 意图 | 样本 | 机/组 | B 重跑 / 原记录 s | C同步合计 重跑 / 原记录 s | 规划占比最大的环节 | 仿真阶段：单机预演 / 联合仿真 / 审计 / 写盘 | 联合仿真 µs/步/机 |
|---|---|---|---|---|---|---|---|
| transit | `prod_f100_140/…353b8b5f4cae79d3_ext_005` | 6/1 | 24.4 / 36.4 | 105.1 / 154.4 | 衔接 72.5%（进场 70.3%）、整航线 16.9% | 57.8% / 39.3% / 1.6% / 0.8% | 152.9 |
| reconnaissance | `prod_f020_060/…dc9e63c745907aa8_ext_001` | 6/2 | 39.0 / 58.5 | 112.3 / 168.6 | 衔接 40.4%、整航线 20.7%、预检 19.6%、形态 16.1% | 53.9% / 38.3% / 3.9% / 0.9% | 128.2 |
| monitoring | `prod_f180_220/…1c1cf42fbb718d98_ext_002` | 8/1 | 135.3 / 207.8 | 440.1 / 674.8 | 预检 31.7%、形态 28.4%、整航线 28.3%、衔接 10.8% | 53.8% / 41.1% / 2.3% / 0.5% | 236.1 |
| feint | `prod_f100_140/…19db8d41d1ebea45_ext_003` | 5/1 | 36.2 / 57.5 | 98.0 / 148.0 | 衔接 41.1%、整航线 34.0%、预检 13.2% | 57.9% / 39.3% / 1.5% / 0.8% | 144.8 |
| penetration | `prod_f060_100/…617b861a82b92aa4_ext_009` | 8/2 | 31.2 / 46.0 | 86.2 / 159.6 | 衔接 63.9%、整航线 18.9% | 56.8% / 38.9% / 2.5% / 1.0% | 112.3 |

- 原记录"C同步合计" = 同步行 `simulation_wall_s` + 2×`amortized_skeleton_setup_s` + `episode_postprocess_wall_s`（重跑只跑一个方式，准备阶段完整跑一次）。§5.2 的单进程上限据此取 min(60 min, 2×(B + 该值))，而不是指令字面的 2×(B + `simulation_wall_s`)：后者没有包含准备阶段，会使只跑同步方式的进程在正常情况下被提前终止。全部 5 个进程都在上限内正常结束（最长 monitoring 580 s，上限 1765 s）。
- 单机预演按每步计费：248–335 µs/步（单机）。监视样本单机预演共 696 661 步，联合仿真 95 839 步 × 8 机、2 188 次回滚。
- 判定与标签（写 `labels.json` 的那次 `measure`）占 0.1–0.9%；独立审计（含复算、列置换、前缀标签 3 次 `measure`）1.5–3.9%；半程截断检查 0.1–1.7%。
- 重复测量（r2，同样的 5 个样本，另有 1–2 个剖析进程同时运行）合计与 r3 相差在 1–9 s 内（例如 monitoring B 138.0 / 135.3 s，C 448.9 / 440.1 s）。
- 未计时成功：每个样本都有若干计时包装调用次数为 0，全部是该执行方式用不到的分支函数（例如过境样本没有调用非过境的形态与衔接函数），逐项列在 `stage_timing.md`。另外，单机 npz 写盘和 pickle 写盘没有单独包装，计入"其余"（≤0.1%）。
- 第 1 轮（r1）因隔离目录缺 `qc/` 子目录在最后一步报错（`save_json` 不建父目录），4 个样本跑完了仿真但没有留下最终计时，已整体移到 `out/rerun/_attempt1_qc_dir_bug/`，未计入任何结果；修正驱动后重跑（r2、r3）。

### 1.3 热点（§5.3）

**仿真热点**（`profile_sim_transit.txt`；过境样本 `prod_f100_140/…353b8b5f4cae79d3_ext_005_regular` 同步方式仿真阶段，cProfile 下 182.6 s）：累计时间前 10 项为 `execution.py:53 execute`（7 次，178.0 s）、`rehearsal.py:61 rehearse`（107.5 s）、`route_tracker.py:341 observe_segment`（481 358 次，79.9 s）、联合仿真（1 次，70.6 s）、`route_tracker.py:274 command`（48.0 s）、`route_tracker.py:137 _disk_intervals`（43.2 s）、`route_tracker.py:290 _command`（39.9 s）、`engine.py:69 step`（289 434 次，38.9 s）、`references.py:25 _roots`（901 093 次，29.0 s）、`plants.py:43 step`（24.8 s）。自身时间前几位是 `numpy.linalg.norm`（7.8 s）、`route_tracker.py:22 _bezier`（7.3 s）、`plants.py:18 dense_state`（6.5 s）、`_command`（5.8 s）、`contracts.py:43 _array3`（5.6 s）。

- 联合仿真：**45 002 步 × 6 架**，166 次回滚，仿真时长 896.7 s（8 968 个 10 Hz 样本）。cProfile 下 70.58 s → 每步每机 **261.4 µs**；同一样本不剖析时（§5.2 r2）42.16 s → **156.1 µs**。单机预演：6 次单机仿真共 244 432 步，61.74 s（不剖析）→ 每步 252.6 µs（单机）。

**规划热点**（`profile_plan_monitoring.txt`；监视样本 `prod_f220_260/…e891bec0170b57ed_ext_007_regular`，原记录规划耗时 300.5 s，最接近 300 s；cProfile 下 341.9 s，结果 PASS）：累计时间前 10 项为 `build_unified_pool`（337.8 s）、`geometry.py:15 geometry_facts`（6 713 406 次，301.0 s）、`free_space.py:101 segment_issues`（519 457 次，148.6 s）、`pipeline.py:100 precheck`（190 次，114.6 s）、`geometry_checks.py:81 check_polyline`（3 420 次，114.2 s）、`checks.py:68 plan_checks`（200 次，80.3 s）、`operation_shapes.py:156 draw_operation`（78.0 s）、`operation_routes.py:26 route_operation`（61.5 s）、`route.py:84 _approaches`（254 次，54.7 s）、`visibility.py:100 visible`（600 757 次，53.8 s）。`visibility.py:61 __init__`（可视图构建）30 次 41.8 s。自身时间第一位 `geometry_facts` 89.8 s。

---

## 2. 失败在哪（`failures.md`、`rejection_samples.md`、`rejection_subreasons.md`）

**结论：规划失败的 196 个骨架全部是搜索预算耗尽（没有一个记为几何不可行），其中 194 个是"某个任务组 200 个提案全部被拒"；仿真失败的 101 个骨架中 68 个是联合仿真超时，且这 68 个两个方式的任务组条件全部满足。**

### 2.1 规划失败：骨架级

| 意图 | REJECT 骨架 | 骨架内计数最多的原因（骨架数） | 失败层级 |
|---|---|---|---|
| transit | 19 | connection_search_budget_exhausted 19 | 组提案池为空 19 |
| reconnaissance | 27 | connection 21；shape 5；whole_route_check 1 | 组提案池为空 27 |
| monitoring | 52 | shape 32；connection 19；patrol_band_too_narrow 1 | 组提案池为空 52 |
| feint | 19 | connection 19 | 组提案池为空 19 |
| penetration | 79 | shape 65；connection 12；组合 approach_length_ratio_exceeded 2 | 组提案池为空 77；组合阶段被拒 2 |

- 全部 196 个的 `termination` 都是 `search_budget_exhausted / no_eligible_combination_in_registered_budgets`，`global_infeasibility_claimed=false`。
- REJECT 骨架**没有逐候选记录**：候选池为空时 `worker_b` 不写 `candidate_pool.pkl`（`run_v07_fe_production.py:328`），逐候选的 `candidates[]` 只随 pickle 保存，`planning_result.json` 只有按原因计数。因此 `rejection_samples.md` 中"每个候选失败在哪个构造环节"记为"未记录"，表中给出了按原因的计数与原因→环节对应。
- 骨架内计数（REJECT 骨架之和）：transit connection 3 805；reconnaissance connection 3 962、shape 1 257；monitoring connection 3 753、shape 6 594、patrol_band 200；penetration shape 12 930、connection 2 682、组合 approach_length_ratio 1 625、same_target_bearing 375（`failures.md` §1.1）。

### 2.2 进入 C 的骨架上的逐候选子原因（参照）

进入 C 的 2 435 个骨架在 `episodes/<sk>/candidate_search.json` 中保留了逐候选的环节（shape → connection → whole_route）和证据：

- **衔接失败的子原因**（每个被拒提案 10 次尝试）：transit 以 `retreat_outside_available_domain`（86 956 次尝试 / 10 383 个提案，只出现在过境）为主，其次 `no_exterior_connection`、`lane_swallowtail`、`alignment_consumed_by_lane_turn`；reconnaissance 以 `alignment_consumed_by_lane_turn`（23 083）与 `no_interior_connection`（10 962）为主；monitoring 以 `lane_swallowtail`（18 247）与 `no_exterior_connection`（12 039）为主。
- **形态失败的子原因**（每个被拒提案 20 次尝试）：monitoring `ingress_line_blocked` 71 086、`patrol_arc_too_short` 34 965；penetration `intrusion_contour_unavailable` 38 577、`intrusion_interior_unavailable` 31 471、`intrusion_endpoint_spacing` 7 796；reconnaissance `survey_area_unavailable` 55 255。
- **整航线检查的问题 code**：`collection_clearance`（transit 15 682、monitoring 15 978 个候选）、`terminal_endpoint_spacing`（reconnaissance 11 282 个候选）、`constraint_clearance`（transit 1 931）、`warning_visit_count`（reconnaissance 48）。
- 逐候选环节计数（PASS 骨架）：transit connection 18 277、whole_route 17 319；monitoring shape 5 336、connection 3 973、whole_route 18 071；penetration shape 4 206（`failures.md` §1.2）。

### 2.3 仿真失败全量（C 为 NOT_PAIRED 的 101 个骨架）

| first_failure | 骨架数 | 意图分布 | 失败方式 |
|---|---|---|---|
| execution / timeout | 68 | penetration 22、feint 16、transit 12、reconnaissance 9、monitoring 9 | 全部同步+递次两个方式都超时；68 个两方式的 `all_groups_complete` 都为 True |
| rehearsal_failure | 20 | reconnaissance 13、monitoring 3、penetration 2、feint 1、transit 1 | 两方式（5 个候选的单机预演全部失败） |
| timing_conflict | 10 | reconnaissance 8、monitoring 2 | 两方式（某方式 20 次出发延迟抽取都 <2 m） |
| generation_error / minimum_separation_below_2m | 3 | reconnaissance 3 | 仅递次方式 |

逐骨架明细（status 文件路径、机数、组数、各方式状态、预演/时刻失败的候选序列、未满足的组条件）见 `failures.md` §3。

---

## 3. 写死的衔接段与预算（`code_map.md` §4.2）

**结论：衔接段的几何形状由少数固定规则 + 均匀抽样参数决定，部分常数写在代码里而不在配置中；配置中的 `group_proposals`、`combination_budget` 两个键没有被代码读取。**

- 进场：同股同入口成员合成一块，块中线上取汇合点（预警区外 U[50,250] m，`collection_clearance_m`）、对齐点（入口前 100 m + 半宽，`alignment_length_m`），编队点深度依次试 `(max(100, 2·半宽+50), 100, 150, 200, 60)` m（**代码常量** `route.py:114`），编队点 → 对齐点用外部可视图最短路，再按横向偏移平移为各机车道（`route.py:84-151`）。
- 作业段连接（非过境）：门 → 门内 100 m → 作业起点前 `lateral_spacing` → 作业起点，内部可视图 + 半径 `lateral_spacing/2` 倒圆角（`operation_routes.py:41-53`）。
- 撤离：过境沿出口方向射到预警区外 U[50,300] m 的轮廓（`route.py:172-182`）；其他方式在名义出口方向上依次旋转 `(0, ±30, ±60, ±90)`°（**代码常量** `construction.py:46`），取首个距所有预警区 ≥50 m 的点；突入无撤离段。
- 多股：仅 multi_direction 分股；≤5 机 2 股、否则随机 2/3 股；2 股相邻方位差 U[100,180]°、3 股各 U[50,120]°（**代码常量** `public_approach_shape.py:15-19`）；多向入口夹角只做诊断，不拒绝（`checks.py:180-185`）。
- 多组：同目标两组作业区方位差 ≥30°；same_direction 抽签进场长度 ≤ 最小值 ×1.30；组间出发偏移 U[0,90] s（`sampling.py:50`）。
- 预算：每组 200 提案（`candidate_search.py:18` 常量）、组合 1000（`group_candidate_pool.py:14` 常量）、形态 20 次、衔接 10 次（geometry 配置）、候选轮数 5、出发延迟抽取 20（generator 配置）、进程超时 3600 s / 5400 s、联合仿真时限 = 最晚计划完成 + max(120 s, 20%)。全表与各拒绝原因的抛出位置及触发条件见 `code_map.md` §4.2.2–4.2.3。
- `patrol_band_too_narrow` 不消耗形态重试，直接抛出（`operation_shapes.py:176`），其条件只取决于成员数和场景几何，因此一旦触发，该组 200 个提案全部同样失败（全部记录中 1 个骨架、200 次）。

---

## 4. 仿真执行接口（`code_map.md` §4.3）与续跑实验（§5.4）

**结论：fastsim 接受任意初始 (p, v, a)，且这三个量就是两个一阶滞后环节的全部状态，以 A 在中点的 (p, v, a) 为初值续跑，位置最大差 4.4 mm；但参考航线只接受航点 + 单一巡航速度，不支持逐段速度。**

1. 入口 `task_v07/execution.py:53 execute(skeleton, delays_s, *, only_agent, time_budget, route_switch, reference_version="r2")`；生产在 `worker_c` 的 payload 里写死 `"reference_version": "r3"`（`run_v07_fe_production.py:401`），r3 配置 `configs/fast_dynamics/m3_r3_candidate_v1.json`（SHA256 核对）。
2. 输入：每机航点列表 `references[a].points_enu_m` + 一个标量 `cruise_speed_m_s`；**不支持逐段/逐航点速度**（`RouteTracker` 只收一个速度，`route_tracker.py:162,178`），转角限速由曲率等自动求；跟踪管 0.5 m、航点见证圆 min(0.5, 0.2×相邻航段长)；转角 ≥175° 的航点为显式停车点（`route_tracker.py:221-222,302-303`）；航线高度须恒定。
3. 初始状态：`initial_states[a]` 的位置、速度、加速度 → `PlantState(p, v, a)`；不从静止开始（生产骨架初速度非零）；控制器/对象无其他隐藏状态；跟踪器内部进度不能外部传入。
4. 等待与悬停：出发延迟 = `initial_settle_s`（20 s）+ delay，释放前用端点速度律保持在初始位置；中途悬停只有 `intermediate_dwell`（仅抵近观察用，`dwell.py`）；无通用"在某点停 T 秒"参数。另有 `route_switch`：在 10 Hz 边界替换指定飞机的航线（`execution.py:67-72,100-110`）。
5. 多机：同一循环推进，`SynchronousEngine.step` 对 (N,3) 数组向量化积分；跟踪器逐机 Python 调用；**仿真中不检查机间间距**（时刻安排用平移单机轨迹预测 2 m，事后判定中计算最小间距）。
6. 实现：每步逐机 `command`、逐机事务快照（复制跟踪器 `__dict__`）、向量化积分、逐机 `observe_segment`（对三次多项式求航点见证圆进出根）、必要时截断回滚；积分步 20 ms。
7. 输出：只保存 10 Hz 网格上的 (t, p, v, a)，降采样在 `engine.py:81-83`；20 ms 积分状态不保存。

**§5.4 续跑实验**（`out/rerun/s54_resume/resume_result.json`；脚本 `scripts/v8_01_driver.py resume`）：

- 对象：过境样本原记录 `v07_first_edition/prod_f100_140/episodes/family_s15_353b8b5f4cae79d3_ext_005_regular/synchronous/task.json`（只读）中 `agent_ids[0]` = `uav_01`，13 个航点，r3 参数，按生产方式（`execute(group, {…:0}, only_agent=…, reference_version="r3")`，与单机预演相同）完整仿真得 A（completed，结束于 806.32 s）。
- t_s = 释放（20 s）与结束之间的中点，对齐到 10 Hz 样本：**413.1 s**（第 4131 帧）；此时 v = (8.23, −5.51, 0) m/s，a ≈ (0.005, 0.007, 0) m/s²（巡航段）。
- B 的输入：`initial_states[uav_01]` 的 position/velocity/acceleration = A 在 t_s 的 p/v/a；`initial_settle_s = 0`、出发延迟 0；参考航线 = [A 在 t_s 的平面位置（航线高度）] + 第 3 个航点之后的原航点（共 11 点）。这些都是 `execute` 已有的输入，未改代码。
- 结果（t_s 之后 3 933 个公共样本）：

| 传入的状态 | 位置最大差 | 速度最大差 | 结束时刻（A 806.32 s） |
|---|---|---|---|
| p、v、a | 0.0044 m | 0.0047 m/s | 806.32 s |
| p、v（a=0） | 0.0044 m | 0.0047 m/s | 806.32 s |
| 仅 p（v=a=0） | 14.88 m | 9.90 m/s | 807.82 s |

- 接口允许传入两个滞后环节的状态（即 v 与 a）。本次中点处于匀速巡航段、a≈0，所以 "p、v" 与 "p、v、a" 差别不可见；不传 v、a（从静止起步）造成 14.9 m 位置差和 9.9 m/s 速度差。剩余 4.4 mm 差异的来源未进一步分解（跟踪器从新航线首点重建，首步对首点的指令与原跟踪器不同）。
- **逐段速度**：接口不支持（`route_tracker.py:162,178`、`execution.py:76-77`），按指令不做该实验。

---

## 5. 判据（`code_map.md` §4.4）

**结论：判据只能对前缀 [0, cutoff) 计算，不能直接对 t0>0 的窗口计算；"恰好一次""未驻留/未重访""未违反禁入"和"结束时在圈外"都要等整段结束才有结论；几乎所有角色判据都用到生成时指定的目标，覆盖判据还用到生成时的搜索扇形。**

- 时间范围：`measure(..., cutoff_s)` 只截前缀（`criteria_labels.py:24-26`），`validate_grid` 要求时间从 0 开始（`labels.py:50-53`）；`complete=False` 时"未发生"类条件为 None。
- 可在任意窗口逐帧计算的量：圈层等级、驻留滑窗、覆盖累积、最小机间距。
- 依赖整段结束状态：`ended_outside_warning`（最后一帧圈层）、`single_warning_visit`/`single_alert_visit`、`no_dwell`、`no_revisit`、`exclusion_policy_respected` 的"成立"结论；`work_mask` 与 `work_end`（最后一次在预警区内）也依赖窗口端点；`revisit` 的最小时间间隔用整段 `speed.max()`。
- 依赖指定信息：角色（决定核心事件和用哪组条件）、指定目标（圈层、目标中心、禁入层）、区域搜索的生成扇形 `skeleton["survey"]`、组成员、计划方式与计划批次（`coordination_matches_assignment`）、突防主组 `main_group_id`。
- 同步/递次分类：需组内全部成员的核心事件都已发生；同步 = 事件极差 ≤10 s，递次 = 按 >20 s 间隔分批且每批极差 ≤10 s。
- `prefix_labels.json`：`audit_episode` 中以 `cutoff = 最早核心事件 − 0.1 s`（否则 1.0 s）对前缀重算**全部字段**；另有 `truncation_check.json` 在每组作业区间中点截断检查前缀不得判成功。

---

## 6. 角色与意图在代码中的定义；迂回可用的已有逐帧量

- 意图 `INTENTS`（`task_v07/expansion/sampling.py:12`）：transit、reconnaissance、monitoring、feint、penetration。角色 `ROLES`（`:13`）：transit、reconnaissance、monitoring、feint、intrusion。执行方式：transit、area_search、close_observation、monitoring、feint、intrusion（`task_v07/unified/spec.py:182-183`；侦察在 area_search/close_observation 中随机取一，`sampling.py:115`）。代码中没有 `approach_observation`，对应的是 `close_observation`。
- 突防的组成在 `sampling.py:98 build_descriptor` 组装：主单元为 intrusion，其余单元按 0.5/0.3/0.2 取 intrusion/feint/monitoring（`:109-114`），`merge_units` 按（目标, 角色）合并为任务组，`derive_intent`（`:86-95`）规定含 intrusion 且角色 ⊆ {intrusion, feint, monitoring} 即为 penetration；集群结论以主组为准（`multi_labels.py:84-89`）。
- 已有逐帧量：`truth_10hz.npz`（p/v/a）、`frame_labels.npz` 的 `region_all_facilities`（T×N×F 圈层 0–3）、`region_assigned_target`、`phase`（0–4）。已有但非逐帧：每机 `approach_headings_deg`（进入预警区前 100 m 航向）、`approach_span_deg`、过境进/出预警区方位角及差与预警区内累计转角、突入进入方位角、重访方位覆盖角、作业期折返次数、`work_area_center_m`。**未存盘**：逐帧相对设施中心的方位角、逐帧到目标的有符号距离（均可由 p 与已存中心/几何算出）。

---

## 7. 输出体积与写盘耗时

**结论：每个方式目录约 28–71 MB，监视最大；全部批次方式目录合计 181 GB，另有骨架级辅助文件（单机 npz、candidate_search.json 等）30 GB。**

| 意图 | 方式目录数 | 每个方式目录 MB | 方式目录合计 GB | 骨架级辅助 GB | planning/ GB |
|---|---|---|---|---|---|
| transit | 972 | 28.0 | 27.17 | 4.09 | 0.48 |
| reconnaissance | 932 | 28.9 | 26.90 | 6.14 | 0.78 |
| monitoring | 964 | 70.6 | 68.04 | 9.72 | 1.38 |
| feint | 972 | 27.5 | 26.72 | 5.82 | 0.78 |
| penetration | 970 | 33.4 | 32.39 | 4.40 | 0.51 |

（`timing_summary.md` §7；`candidate_search.json` 单个可达约 4 MB。）生产记录中写盘耗时没有单独字段，包含在 `episode_postprocess_wall_s`（判定 + 写盘 + 审计）里。§5.2 实测的写盘耗时见 1.2 节与 `stage_timing.md`。

§5.2 实测（同步方式一个方式目录）：`write_episode`（truth/observations csv、3 个 npz、5 个 json）0.79–2.22 s，占仿真阶段 0.5–1.0%；审计外的 `save_json` 共 20 次 0.14–0.52 s。写盘字节：方式目录 18.1–52.3 MB，整个 `episodes/<sk>`（含骨架级辅助文件、只一个方式）24.1–75.9 MB，`planning/<sk>` 0.57–2.93 MB。

---

## 8. 已有剖析证据（`prior_profiling.md`）

**结论：已有两份 cProfile 都早于 P0 提速；P0（事务快照 + 包围盒预筛选）已合入首版生产代码；线索提交 `81f804a` 是飞行速度剖面检查，不是耗时剖析。**

- `docs/v07/evidence/s15/s15_planning_profile.txt`：单骨架规划 131.3 s，`geometry_facts` 累计 123.4 s（约 94%），其中 `visibility.visible` 99.0 s。
- `docs/v07/evidence/s15/diagnosis/d3_profile.txt`：单骨架规划+仿真阶段 532.4 s，`execute` 467.9 s，`deepcopy` 157.0 s（P0 前的跟踪器深拷贝）。
- `docs/v07/perf/FE_P0_implementation_report.md`：规划总体中位耗时改善 20.90%，监视单机改善 41.30%；过境 synchronous 联合执行 54.48→46.56 s。
- 本次 §5.3 的剖析是第一份针对首版生产代码（`641a9b3`）的 cProfile。

---

## 9. 执行方观察（个人判断，与以上事实分开）

以下是执行方的判断，未经单独验证，仅供设计参考。

1. **生产记录里的单进程耗时偏高。** 同一骨架在 5 进程并行下重跑，规划和联合仿真大约只用原记录（14 进程并行）的 0.54–0.68 倍（§1.2）。规划结果逐键一致（§5.1），所以差别更像机器负载造成的，不是算法变化。用生产记录估算 v0.8 的吞吐时，需要把并行度的影响单独考虑。
2. **仿真阶段的成本大致等于"单机预演 + 每个方式各一次联合仿真"，三份的规模相近。** 单机预演对每架飞机单独跑一遍完整航线，按机·步计的单价（248–335 µs/步，单机）比联合仿真（112–236 µs/步/机）还高。按记录，准备阶段占仿真阶段的 37–45%。如果 v0.8 分段生成、能复用中间状态（§4 已证实可以从 (p, v, a) 续跑），这一块是否还要整段重复，值得在设计时确认。
3. **监视意图占了一半的总耗时，原因是它仿真时间长、机数多、准备也重**（同步仿真中位数约为其他意图的 4–5 倍）。机数分档的趋势在各意图上都近似线性。
4. **规划时间几乎全部在单个提案的几何构造与检查上，组合搜索可以忽略。** 监视样本的剖析中，`precheck`（既有输出预检）占约三分之一，但在全部生产记录里，它从未拒绝过任何候选（`existing_output_precheck` 计数为 0）。
5. **规划失败全部是"某个组的 200 个提案用完"，没有一个被证明为几何不可行。** 失败集中在少数几处写死的衔接规则：过境的撤离射线（`retreat_outside_available_domain`）、巡逻的进场线与可用弧长、突入终点的轮廓求解、区域搜索的扇形面积。`patrol_band_too_narrow` 只由成员数和场景决定，属于确定性失败，200 次重试没有意义。
6. **抽签级耦合是"白费时间"的主要来源。** 18.4% 的白费时间里，最大一块是本意图已经配对成功、但因为同一抽签中另一个意图失败而被丢弃的仿真。
7. **68 个仿真超时的骨架，任务判据其实都已满足。** 超时的原因在终止条件（全部到达终点并保持、跟踪器完成），不在任务行为本身；这 68 个骨架占仿真失败的三分之二。
8. **判据只支持前缀，且多个条件以"整段结束"作为否定结论的依据。** 若 v0.8 需要按时间窗口打标签，至少 `ended_outside_warning`、各"恰好一次/未发生"条件、`work_mask`/`work_end`，以及 `revisit` 中用整段最大速度计算的时间间隔，需要重新定义窗口语义。
9. **口径对账比值 0.895** 说明 `stats.json` 的 `total_wall_s` 比"记录耗时 ÷ 14"多出约 12%，可能包含调度空闲或收尾时间；本次没有核对 `build_stats` 的定义。

---

## 提交与最终核对

- 开发分支 `dev/v0.8` 头提交 = `main` = `bb262b3`，在开发工作树 `Simulation-v08` 中由它新建 `review/v08/V8-01-diagnosis`。
- 提交到 `docs/v08/V8-01/`：本报告、`code_map.md`、`failures.md`、`field_inventory.md`、`prior_profiling.md`、`profile_plan_monitoring.txt`、`profile_sim_transit.txt`、`rejection_samples.md`、`rejection_subreasons.md`、`stage_timing.md`、`timing_records.csv`（1.9 MB）、`timing_summary.md`，以及 `scripts/` 下全部 10 个脚本。没有超过 5 MB 的文件被排除；`out/rerun/`（重跑产物、`.prof`、快照、日志，约 0.6 GB）不提交。
- 最终 `SwarmData\v07_*` 快照（`out/rerun/snapshot_final.json`）与运行前快照逐目录相同（文件数、字节数、最新修改时间）。
- 冻结工作树最终 `git -C Simulation-fe-prod-r3 status --porcelain` 输出：**空**。（`--ignored` 只列出原有的 `scripts/__pycache__/`、`task_v07/unified/__pycache__/`，其中没有任何文件晚于本任务开始时间。）
- 推送后的远端提交号：`d8573127c47153fe1f71fb80c9284ad3c01fa811`（内容提交 `docs(v08): V8-01 首版诊断报告与脚本`；`git ls-remote origin refs/heads/review/v08/V8-01-diagnosis` 核对一致）。本行由随后的补记提交写入，补记提交自身的提交号见本地 `out/REPORT_V8-01.md`。
