# V8-01 §3.2 耗时汇总

由 `scripts/v8_01_scan_records.py`（扫描）与 `scripts/v8_01_summarize.py`（统计）生成；逐条记录见 `timing_records.csv`。
范围：`v07_first_edition` 下 9 个批次全部记录（含 `pilot_f000_005`，其代码提交为 `debfadf6`，其余为 `641a9b3a`；单独列出见 §6）。 不含 `prod_f060_100/_aborted`、`prod_f100_140/_aborted` 中被续跑挪走的半成品（这两个目录里的耗时没有进入任何 status 文件）。

## 0. 口径

- **规划耗时**：`status/B__*.json` 的 `planning_wall_s`（秒，按骨架；`time.monotonic`，`run_v07_fe_production.py:323-342`）。
- **仿真耗时按方式分开记录**，因此没有合并为 `both`：`status/C__*.json` 的 `detail.rows[]` 对每个方式记 `simulation_wall_s`（联合仿真 `execute` 本身）、`amortized_skeleton_setup_s`（骨架级准备耗时的一半，`run_v07_s2_episode_batch.py:154` 写死 `setup_s / 2`）、`episode_postprocess_wall_s`（判定+写盘+审计，`write_result`）。骨架级另有 `elapsed_wall_s`（整个 C 进程任务，含两个方式、配对检查与 QC）。
- **本文的"同步仿真耗时"** = 同步方式行的 `simulation_wall_s`（只含联合仿真）。§5.2 选样即用此值；§5.2 的时间上限另用"B + 同步方式的仿真 + 2×摊分准备 + 后处理"，原因见报告。
- **C 阶段全部耗时** = 骨架级 `elapsed_wall_s`；它与两个方式三项之和的差，是配对检查 `pair_result` 与 `qc_episode` 等（见 §5）。
- 所有耗时都是 14 个进程并行时的单进程墙钟。

## 1. 按意图 × 阶段（全部记录，单位秒；合计为小时）

| 意图 | 阶段/字段 | 条数 | 中位数 | p90 | p99 | 最大 | 合计 h |
|---|---|---|---|---|---|---|---|
| transit | B 规划 planning_wall_s | 600 | 33.6 | 78.8 | 140.6 | 198.2 | 6.82 |
| transit | C synchronous simulation_wall_s | 486 | 59.6 | 112.2 | 154.8 | 179.3 | 8.93 |
| transit | C synchronous episode_postprocess_wall_s | 486 | 4.8 | 11.6 | 24.9 | 38.3 | 0.84 |
| transit | C sequential simulation_wall_s | 486 | 62.9 | 116.7 | 157.6 | 194.8 | 9.31 |
| transit | C sequential episode_postprocess_wall_s | 486 | 5.8 | 14.1 | 24.9 | 43.8 | 0.98 |
| transit | C 骨架准备 2×amortized_skeleton_setup_s | 486 | 89.4 | 193.3 | 383.4 | 653.5 | 14.46 |
| transit | C 骨架合计 elapsed_wall_s | 487 | 224.7 | 436.6 | 650.6 | 917.2 | 34.79 |
| reconnaissance | B 规划 planning_wall_s | 600 | 53.7 | 474.8 | 827.3 | 1,421.4 | 26.22 |
| reconnaissance | C synchronous simulation_wall_s | 466 | 66.1 | 118.9 | 164.2 | 190.5 | 9.23 |
| reconnaissance | C synchronous episode_postprocess_wall_s | 466 | 6.8 | 16.8 | 38.3 | 43.0 | 1.16 |
| reconnaissance | C sequential simulation_wall_s | 466 | 69.2 | 123.3 | 168.8 | 204.2 | 9.64 |
| reconnaissance | C sequential episode_postprocess_wall_s | 466 | 7.8 | 18.2 | 37.8 | 42.3 | 1.27 |
| reconnaissance | C 骨架准备 2×amortized_skeleton_setup_s | 466 | 103.6 | 232.2 | 656.9 | 1,334.8 | 17.74 |
| reconnaissance | C 骨架合计 elapsed_wall_s | 487 | 270.6 | 567.8 | 1,362.9 | 2,466.8 | 44.65 |
| monitoring | B 规划 planning_wall_s | 600 | 198.3 | 384.8 | 611.7 | 746.4 | 36.09 |
| monitoring | C synchronous simulation_wall_s | 482 | 293.1 | 547.8 | 807.1 | 1,066.3 | 43.77 |
| monitoring | C synchronous episode_postprocess_wall_s | 482 | 63.8 | 145.1 | 255.7 | 376.8 | 10.37 |
| monitoring | C sequential simulation_wall_s | 482 | 294.8 | 549.1 | 794.1 | 1,061.3 | 43.93 |
| monitoring | C sequential episode_postprocess_wall_s | 482 | 63.9 | 144.7 | 249.4 | 383.1 | 10.40 |
| monitoring | C 骨架准备 2×amortized_skeleton_setup_s | 482 | 412.9 | 816.1 | 1,811.2 | 2,704.4 | 64.05 |
| monitoring | C 骨架合计 elapsed_wall_s | 487 | 1,196.6 | 2,160.6 | 3,318.2 | 3,919.5 | 176.02 |
| feint | B 规划 planning_wall_s | 600 | 53.9 | 112.4 | 187.7 | 240.4 | 10.33 |
| feint | C synchronous simulation_wall_s | 486 | 63.6 | 112.9 | 157.7 | 207.0 | 9.43 |
| feint | C synchronous episode_postprocess_wall_s | 486 | 4.3 | 9.0 | 13.7 | 20.3 | 0.68 |
| feint | C sequential simulation_wall_s | 486 | 65.5 | 117.5 | 163.2 | 210.0 | 9.77 |
| feint | C sequential episode_postprocess_wall_s | 486 | 5.1 | 10.6 | 15.8 | 22.0 | 0.80 |
| feint | C 骨架准备 2×amortized_skeleton_setup_s | 486 | 93.1 | 193.3 | 334.4 | 855.2 | 15.03 |
| feint | C 骨架合计 elapsed_wall_s | 487 | 235.5 | 447.5 | 681.7 | 1,127.7 | 36.21 |
| penetration | B 规划 planning_wall_s | 600 | 39.4 | 123.4 | 231.1 | 325.7 | 8.91 |
| penetration | C synchronous simulation_wall_s | 485 | 63.3 | 167.2 | 333.4 | 524.4 | 11.29 |
| penetration | C synchronous episode_postprocess_wall_s | 485 | 4.9 | 34.8 | 87.7 | 144.3 | 1.67 |
| penetration | C sequential simulation_wall_s | 485 | 65.9 | 168.8 | 322.1 | 503.1 | 11.61 |
| penetration | C sequential episode_postprocess_wall_s | 485 | 6.2 | 34.6 | 87.0 | 145.3 | 1.81 |
| penetration | C 骨架准备 2×amortized_skeleton_setup_s | 485 | 93.6 | 233.3 | 636.8 | 941.7 | 17.09 |
| penetration | C 骨架合计 elapsed_wall_s | 487 | 237.4 | 657.0 | 1,395.6 | 1,943.3 | 44.37 |

说明：C 行只包括进入仿真阶段的骨架（抽签 5 个意图都 B 通过才进入 C，`run_v07_fe_production.py:497-515`）。 三项方式级耗时只在进入联合仿真的行上有记录（几何/预演/时刻阶段耗尽的行缺这三项，见 §5）。

### 1.1 仿真阶段内部占比（按意图，全部有三项记录的骨架之和）

| 意图 | 骨架数 | C 合计 h | 准备（预演+时刻+候选池载入+写盘） | 联合仿真（两方式） | 后处理（两方式） | 其余（配对检查、QC 等） |
|---|---|---|---|---|---|---|
| transit | 486 | 34.70 | 41.7% | 52.5% | 5.2% | 0.6% |
| reconnaissance | 466 | 39.24 | 45.2% | 48.1% | 6.2% | 0.5% |
| monitoring | 482 | 173.04 | 37.0% | 50.7% | 12.0% | 0.3% |
| feint | 486 | 35.90 | 41.9% | 53.5% | 4.1% | 0.5% |
| penetration | 485 | 43.71 | 39.1% | 52.4% | 8.0% | 0.5% |

### 1.2 规划阶段内部（只有进入 C 的骨架在 `episodes/<sk>/candidate_search.json` 留有分项，单位秒）

| 意图 | 骨架数 | planning_wall_s 合计 h | 各组提案池 wall_s | 组合搜索 wall_s | phase_search（unified 后端恒为 0） | 其余（场景加载、pickle 写盘等） |
|---|---|---|---|---|---|---|
| transit | 487 | 5.79 | 99.4% | 0.52% | 0.0% | 0.1% |
| reconnaissance | 487 | 22.53 | 99.7% | 0.29% | 0.0% | 0.0% |
| monitoring | 487 | 31.16 | 99.0% | 0.97% | 0.0% | 0.0% |
| feint | 487 | 8.62 | 99.4% | 0.56% | 0.0% | 0.1% |
| penetration | 487 | 8.08 | 98.7% | 1.24% | 0.0% | 0.1% |

`group_search_metrics.*.wall_s` 与 `geometry_wall_s` 在 unified 后端是同一个值（`task_v07/unified/adapter.py:58-61`），其中形态、衔接、整航线检查各占多少没有分别记录。

## 2. 按机数分档 × 意图：同步仿真耗时中位数（`simulation_wall_s`，秒；括号内为条数）

| 意图 | 4–5 | 6–8 | 9–12 |
|---|---|---|---|
| transit | 38.8 (112) | 57.1 (216) | 85.9 (158) |
| reconnaissance | 46.5 (107) | 64.3 (208) | 87.4 (151) |
| monitoring | 179.2 (113) | 285.3 (213) | 431.5 (156) |
| feint | 41.4 (113) | 60.2 (216) | 92.5 (157) |
| penetration | 36.7 (113) | 57.9 (216) | 89.6 (156) |

同一分档的规划耗时中位数（秒）：

| 意图 | 4–5 | 6–8 | 9–12 |
|---|---|---|---|
| transit | 26.2 (118) | 31.5 (246) | 41.8 (236) |
| reconnaissance | 46.2 (118) | 51.4 (246) | 63.4 (236) |
| monitoring | 143.2 (118) | 192.1 (246) | 256.4 (236) |
| feint | 39.1 (118) | 50.4 (246) | 71.4 (236) |
| penetration | 32.1 (118) | 37.9 (246) | 45.3 (236) |

## 3. 白费的时间

全部记录耗时 = Σ`planning_wall_s` + Σ骨架级 C `elapsed_wall_s`。三类（同一条耗时只计一次，取并集）：
(a) B 为 REJECT/TIMEOUT/ERROR 的规划耗时；(b) 抽签最终未保留（`draw_status` ≠ RETAINED）的骨架的全部规划与仿真耗时；(c) C 为 NOT_PAIRED/TIMEOUT/ERROR 的仿真耗时。全部批次中没有 TIMEOUT 或 ERROR 状态。

| 意图 | 全部记录耗时 h | (a) B 拒绝的规划 | (b) 未保留抽签的全部 | (c) C 未配对的仿真 | 并集占比 | 并集 h |
|---|---|---|---|---|---|---|
| transit | 41.6 | 0.2% | 16.4% | 2.6% | 16.4% | 6.8 |
| reconnaissance | 70.9 | 1.2% | 24.5% | 10.3% | 24.5% | 17.4 |
| monitoring | 212.1 | 0.7% | 16.9% | 3.1% | 16.9% | 35.8 |
| feint | 46.5 | 0.3% | 18.2% | 3.7% | 18.2% | 8.5 |
| penetration | 53.3 | 0.5% | 17.9% | 5.9% | 17.9% | 9.5 |
| 合计 | 424.4 | 0.7% | 18.4% | 4.7% | 18.4% | 78.0 |

(a) 与 (c) 的骨架所在抽签必然未保留，因此并集等于 (b)。

(b) 的组成（小时）：

| 意图 | 记录类别 | 耗时 h |
|---|---|---|
| transit | B PASS / 抽签 B_REJECT | 0.94 |
| transit | B PASS / 抽签 C_NOT_PAIRED | 0.79 |
| transit | B REJECT / 抽签 B_REJECT | 0.09 |
| transit | C NOT_PAIRED / 抽签 C_NOT_PAIRED | 1.08 |
| transit | C PAIRED / 抽签 C_NOT_PAIRED | 3.93 |
| reconnaissance | B PASS / 抽签 B_REJECT | 2.80 |
| reconnaissance | B PASS / 抽签 C_NOT_PAIRED | 3.42 |
| reconnaissance | B REJECT / 抽签 B_REJECT | 0.88 |
| reconnaissance | C NOT_PAIRED / 抽签 C_NOT_PAIRED | 7.30 |
| reconnaissance | C PAIRED / 抽签 C_NOT_PAIRED | 2.95 |
| monitoring | B PASS / 抽签 B_REJECT | 3.36 |
| monitoring | B PASS / 抽签 C_NOT_PAIRED | 4.59 |
| monitoring | B REJECT / 抽签 B_REJECT | 1.57 |
| monitoring | C NOT_PAIRED / 抽签 C_NOT_PAIRED | 6.66 |
| monitoring | C PAIRED / 抽签 C_NOT_PAIRED | 19.65 |
| feint | B PASS / 抽签 B_REJECT | 1.55 |
| feint | B PASS / 抽签 C_NOT_PAIRED | 1.22 |
| feint | B REJECT / 抽签 B_REJECT | 0.16 |
| feint | C NOT_PAIRED / 抽签 C_NOT_PAIRED | 1.73 |
| feint | C PAIRED / 抽签 C_NOT_PAIRED | 3.81 |
| penetration | B PASS / 抽签 B_REJECT | 0.55 |
| penetration | B PASS / 抽签 C_NOT_PAIRED | 1.32 |
| penetration | B REJECT / 抽签 B_REJECT | 0.28 |
| penetration | C NOT_PAIRED / 抽签 C_NOT_PAIRED | 3.14 |
| penetration | C PAIRED / 抽签 C_NOT_PAIRED | 4.24 |

## 4. 口径对账（诊断项）

| 批次 | 并行数 | 记录耗时之和 h | ÷ 并行数 h | stats.json total_wall_s h | 比值 |
|---|---|---|---|---|---|
| pilot_f000_005 | 14 | 9.51 | 0.68 | 1.20 | 0.567 |
| pilot_f005_020d | 14 | 22.02 | 1.57 | 1.89 | 0.831 |
| prod_f020_060 | 14 | 62.72 | 4.48 | 5.20 | 0.862 |
| prod_f060_100 | 14 | 62.39 | 4.46 | 4.57 | 0.976 |
| prod_f100_140 | 14 | 55.29 | 3.95 | 4.32 | 0.915 |
| prod_f140_180 | 14 | 47.49 | 3.39 | 3.67 | 0.925 |
| prod_f180_220 | 14 | 54.56 | 3.90 | 4.24 | 0.919 |
| prod_f220_260 | 14 | 52.21 | 3.73 | 4.26 | 0.876 |
| prod_f260_300 | 14 | 58.21 | 4.16 | 4.55 | 0.915 |
| 合计 | 14 | 424.40 | 30.31 | 33.89 | 0.895 |

`total_wall_s` 由 `scripts/v07_fe_production_core.py` 的 `build_stats` 计算（未进一步核对其定义）。不一致不作解释。

## 5. 无仿真耗时字段的 C 行

共 60 行（均为 `state` = infeasible 的方式行：几何/预演/时刻阶段耗尽，未进入联合仿真，`run_v07_s2_episode_batch.py:32-42` 的 `rejected()` 不写耗时字段）。这些骨架只有骨架级 `elapsed_wall_s`。

| state | reason | 行数 |
|---|---|---|
| infeasible | rehearsal_failure | 40 |
| infeasible | timing_conflict | 20 |

## 6. `pilot_f000_005`（代码提交 debfadf6）单列

| 意图 | B 条数 | B 中位数 s | 同步仿真条数 | 同步仿真中位数 s |
|---|---|---|---|---|
| transit | 10 | 56.1 | 8 | 86.8 |
| reconnaissance | 10 | 67.0 | 6 | 79.0 |
| monitoring | 10 | 264.3 | 8 | 460.7 |
| feint | 10 | 89.2 | 8 | 96.1 |
| penetration | 10 | 55.7 | 8 | 88.7 |

以上 §1–§4 的统计都包含该批。

## 7. 输出体积（字节，按意图，全部批次合计）

| 意图 | planning/ GB | episodes/<sk> 方式目录以外 GB（geometry_XX、candidate_search.json 等） | 方式目录 GB | 方式目录数 | 每个方式目录 MB | qc/ MB |
|---|---|---|---|---|---|---|
| transit | 0.48 | 4.09 | 27.17 | 972 | 28.0 | 40.0 |
| reconnaissance | 0.78 | 6.14 | 26.90 | 932 | 28.9 | 45.4 |
| monitoring | 1.38 | 9.72 | 68.04 | 964 | 70.6 | 45.5 |
| feint | 0.78 | 5.82 | 26.72 | 972 | 27.5 | 41.3 |
| penetration | 0.51 | 4.40 | 32.39 | 970 | 33.4 | 36.7 |

