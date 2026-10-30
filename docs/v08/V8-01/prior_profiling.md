# V8-01 §3.3 已有的性能剖析证据

查找范围：分支 `main`（bb262b3）、`fe/first-edition-int`（81f804a）、`fe/production-r3`（641a9b3）下 `Multi-UAV SimpleGC/docs/`；文件名关键词 `profil|cprofile|perf|speed|bench|剖析|耗时`，内容关键词 `cProfile|剖析|cumtime|tottime`（`git ls-tree` / `git grep`，只读）。三个分支上找到的剖析文件相同（下列路径均相对 `Multi-UAV SimpleGC/`）。本文只摘录，不重新计算。

## 0. 线索核对

| 线索 | 核对结果 |
|---|---|
| 提交 `81f804a`（10-17，"FE-INT-d evidence: speed profile check"） | 内容是**飞行速度剖面**质量检查（`scripts/qc_v07_fe_speed_profile.py`、`docs/v07/evidence/fe_int/quality_check/qc_speed_report.{md,json}`），不是计算耗时剖析。 |
| "事务快照 + 包围盒预筛选"提速 | 分支 `perf/v07-first-edition-p0`：`b2fdb0f FE-P0-G3`（事务快照替换跟踪器深拷贝）、`c1675cd FE-P0-G2`（包围盒预筛选）、`ae67257 FE-P0-G4`（基准与验收）；经 `4c15846 FE-INT merge P0 performance into P1 monitoring fix` 合入，`perf/v07-first-edition-p0` 是 `fe/production-r3` 的祖先（`git merge-base --is-ancestor` 为真）。即首版生产代码已包含该提速。证据在 `docs/v07/perf/`。 |

## 1. 找到的文件

| 文件 | 性质 | 时间点 |
|---|---|---|
| `docs/v07/perf/FE_P0_implementation_report.md` | P0 提速实施报告（含 base/perf 计时对照） | P0（合入首版前） |
| `docs/v07/perf/FE_P0_benchmark.json` | 30 次测量原始记录、诊断计数、内存 | 同上 |
| `docs/v07/perf/FE_P0_gate_times.json`、`G2_*`、`G3_*`、`G4_*`、`baseline_test_*` | 门禁、等价性与回归测试输出 | 同上 |
| `docs/v07/evidence/s15/s15_planning_profile.txt` | 单骨架规划 cProfile（前 25 项，按累计时间） | S1.5，P0 之前 |
| `docs/v07/s15/S15_stage2_report.md` 第 6 条 | 上一项的文字结论 | 同上 |
| `docs/v07/evidence/s15/diagnosis/d3_profile.txt` | 单骨架 `run_episode_job`（规划+仿真阶段）cProfile（前 40 项） | S1.5，P0 之前（仍为深拷贝版本） |
| `docs/fast_dynamics_coverage_performance_report.md` | fast_dynamics 覆盖几何向量化前后耗时（旧数据线，非 v0.7 生成器） | 早于 v0.7 |
| `docs/fast_dynamics_m2/M2_runtime_resume_report.md` | M2 后处理分段剖析（旧数据线） | 早于 v0.7 |
| `docs/v07/evidence/fe_int/quality_check/qc_speed_report.md` | 飞行速度剖面检查（非计算剖析，见 §0） | 10-17 |

## 2. 主要结论（原文摘录）

### 2.1 S1.5 单骨架规划 cProfile（`docs/v07/evidence/s15/s15_planning_profile.txt`，P0 之前）

> 选中骨架：family_s15_79c93b22d09e8a7a_ext_006_regular（该骨架规划墙钟 95.61485149999862 s，最接近中位数）
> 单进程运行 planning_job；进程数 1；每组 200 提案、组合预算 1000（规划器内置值，未改）
> 223038080 function calls (219137528 primitive calls) in 131.298 seconds

前几项（cumtime，秒）：`geometry.py:15(geometry_facts)` 1733071 次 123.364；`route.py:154(route_group)` 200 次 106.608；`visibility.py:66(visible)` 402033 次 98.951；`route.py:84(_approaches)` 391 次 97.671；`free_space.py:115(planner)` 982 次 86.459；`visibility.py:38(__init__)` 21 次 86.453；`checks.py:68(plan_checks)` 200 次 11.736。

`docs/v07/s15/S15_stage2_report.md` 的文字结论：

> 223038080 次函数调用中 `geometry_facts` 1733071 次累计 123.4 s（约 94%），其中 `visibility.visible` 402033 次累计 99.0 s。

同报告：

> 每骨架规划墙钟（T6）：全体中位数 91.24 s、p90 397.18 s、最大 2991.33 s；`reconnaissance` 的 p90 为 2049.02 s，`monitoring` 中位数 266.68 s。

### 2.2 S1.5 下游（规划+仿真阶段）cProfile（`docs/v07/evidence/s15/diagnosis/d3_profile.txt`，P0 之前）

> 对象：`family_s15_1c267d4d7000043d_ext_005_regular`（试点中 setup 约 64 s、仿真约 92 s）
> 观测墙钟：532.4 s（上限 900 s）

cumtime 前几项（秒）：`run_episode_job` 532.289；`execute`（execution.py:26，8 次）467.881；`rehearse` 181.409；`deepcopy` 157.031（114792902 次）；`route_tracker.py:191(__deepcopy__)` 152.475；`observe_segment` 151.326；`_disk_intervals` 86.751；`engine.py:69(step)` 69.095（335710 次）；`references.py:25(_roots)` 57.224；`episode_candidate_pool` 42.941；`write_result`（2 次）17.928。指定函数：`select_timing` 0.008 s，`solo_interval_check` 0.007 s。

### 2.3 P0 提速报告（`docs/v07/perf/FE_P0_implementation_report.md`）

> **最终结论：PASS。** G0、G3、G2、G4 通过；G1 经预检按规则跳过。规划总体中位耗时改善 20.90%，监视单机改善 41.30%，全部指定输出对照通过。

> 仅改两处生产文件：execution.py 的事务快照/恢复，visibility.py 的包围盒预筛选。

G4 计时表（秒，三次运行中位数）：过境规划 25.407→19.628；突防规划 21.354→20.097（改善 5.89%）；多向区域搜索规划 84.940→66.249；监视单机 48.965→28.743；过境 synchronous 联合执行 54.480→46.561（改善 14.54%）。

> 突防规划单项仅改善 5.89%；不能把总体改善解释为每个样本都达到 15%。联合执行的三次耗时波动较大，完整范围已列出，不以最佳单次代表收益。

G1（跨骨架可视图缓存）预检：

> A 组跨骨架可省比例 9.0138%，因此按规则跳过缓存。

诊断计数：联合执行 G3 steps / rollbacks = 48470 / 134；监视单机 77166 / 215；多向区域搜索规划 G2 exact_calls / skipped = 527923 / 645347。

### 2.4 旧数据线（非 v0.7 生成器，仅供参照）

`docs/fast_dynamics_m2/M2_runtime_resume_report.md`：

> 跨上述阶段，完全相同输入的 `analyze_semantics` 调用 7 次，累计 331.110 s，占全链约 96.5%。

`docs/fast_dynamics_coverage_performance_report.md`：4 机往返扫描分段剖析总计 41.504 秒，前五个互斥阶段 describe_dataset 17.910、run_mission 10.637、write_episode 6.936、audit_dataset 2.049、load_episode 1.985 秒。

## 3. 未找到的内容

- 未找到针对**首版生产代码**（`641a9b3`，P0 合入之后）的 cProfile 结果；2.1、2.2 两份 cProfile 都早于 P0。
- 未找到按环节（单机预演 / 时刻安排 / 联合仿真 / 判定 / 审计 / 写盘）划分的生产期计时，生产记录里只有 `simulation_wall_s`、`amortized_skeleton_setup_s`、`episode_postprocess_wall_s` 三项（见 field_inventory.md）。
