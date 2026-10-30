# V8-01 §5.2 分环节计时

驱动：`scripts/v8_01_driver.py sample`（规划阶段直接调用 `worker_b`；仿真阶段按 `run_episode_job` 步骤只跑同步方式）；并行：`scripts/v8_01_orchestrate.py`。计时包装装在调用方查找函数的模块命名空间上（清单见各样本 `stage_timing.json` 的 `installed`）。
主数据为第 3 轮（r3，`out/rerun/s52_<意图>_r3/`，按调用方拆分耗时）；第 2 轮（r2，`out/rerun/s52_<意图>/`）作为重复测量只列合计。 第 1 轮因隔离目录缺 `qc/` 子目录在最后一步报错，未计入（`out/rerun/_attempt1_qc_dir_bug/`）。
运行环境：5 个样本进程同时运行（r2 时另有 1–2 个剖析进程），每进程单线程（OMP/OPENBLAS/MKL=1）；原记录是 14 进程并行时的耗时。

## 1. 每个样本一行

| 意图 | 批次/骨架 | 机数 | 组数 | B 重跑 s | B 原记录 s | C同步 重跑合计 s | C同步 原记录 s（仿真+2×摊分准备+后处理） | 联合仿真 重跑 s | 联合仿真 原记录 s | 准备 重跑 s | 准备 原记录 s | r2 重复：B / C 合计 s | 同步方式目录 MB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| transit | prod_f100_140/family_s15_353b8b5f4cae79d3_ext_005_regular | 6 | 1 | 24.4 | 36.4 | 105.1 | 154.4 | 41.3 | 61.9 | 60.9 | 88.2 | 25.5 / 107.1 | 18.2 |
| reconnaissance | prod_f020_060/family_s15_dc9e63c745907aa8_ext_001_regular | 6 | 2 | 39.0 | 58.5 | 112.3 | 168.6 | 43.1 | 66.4 | 60.9 | 89.7 | 40.3 / 112.9 | 22.6 |
| monitoring | prod_f180_220/family_s15_1c1cf42fbb718d98_ext_002_regular | 8 | 1 | 135.3 | 207.8 | 440.1 | 674.8 | 181.0 | 287.3 | 237.3 | 355.2 | 138.0 / 448.9 | 52.3 |
| feint | prod_f100_140/family_s15_19db8d41d1ebea45_ext_003_regular | 5 | 1 | 36.2 | 57.5 | 98.0 | 148.0 | 38.5 | 59.9 | 57.0 | 84.4 | 37.5 / 99.8 | 18.1 |
| penetration | prod_f060_100/family_s15_617b861a82b92aa4_ext_009_regular | 8 | 2 | 31.2 | 46.0 | 86.2 | 159.6 | 33.5 | 61.6 | 49.3 | 92.4 | 32.7 / 87.5 | 20.0 |

原记录列取自 `timing_records.csv`（`planning_wall_s`、同步行 `simulation_wall_s`、`2×amortized_skeleton_setup_s`、`episode_postprocess_wall_s`）。 重跑的"C同步合计"含候选池载入、单机预演、时刻安排、同步方式联合仿真、判定/审计/写盘与 qc；不含递次方式。

## transit：`prod_f100_140` / `family_s15_353b8b5f4cae79d3_ext_005_regular`

机数 6，任务组数 1；选中候选 87，试过 1 个候选；仿真时长 896.72 s；执行状态 completed；任务结果 success；是否完整结束：True。

### 规划阶段（占 B 合计 `planning_wall_s` 的比例）

| 环节 | 耗时 s | 占比 | 调用次数 |
|---|---|---|---|
| 可行空间/TaskSpec | 0.00 | 0.0% | 3 |
| 作业形态生成 | 0.80 | 3.3% | 200 |
| 衔接段（进场+撤离+作业段连接） | 17.67 | 72.5% | 200 |
|   其中 进场 _approaches | 17.15 | 70.3% | 722 |
|   其中 撤离点 retreat_endpoint（非过境） | 0.00 | 0.0% | 0 |
|   其中 作业段内连接 connect（非过境） | 0.00 | 0.0% | 0 |
| 整航线检查 plan_checks | 4.12 | 16.9% | 149 |
| 既有输出预检 precheck | 1.71 | 7.0% | 91 |
| 骨架装配 assemble_skeleton | 0.04 | 0.2% | 91 |
| 多组组合（方位+装配+长度比） | 0.02 | 0.1% | 183 |
| 写盘（planning_result/status） | 0.00 | 0.0% | 2 |
| 其余（场景加载、pickle 写盘、提案池循环本身等） | 0.00 | 0.0% |  |

### 仿真阶段（同步方式；占 C 合计的比例）

| 环节 | 耗时 s | 占比 | 调用次数 |
|---|---|---|---|
| 单机预演 rehearse | 60.71 | 57.8% | 1 |
|   其中 单机仿真 execute(solo) | 60.62 | 57.7% | 6 |
|   其中 单机判定 measure(solo) | 0.09 | 0.1% | 6 |
| 时刻安排 select_timing（含 2 m 间距检查） | 0.01 | 0.0% | 1 |
| 联合仿真 execute(joint) | 41.28 | 39.3% | 1 |
| 判定与标签 measure（labels.json） | 0.09 | 0.1% |  |
| 独立审计 audit_episode（含复算/列置换/前缀标签 3 次 measure） | 1.73 | 1.6% | 1 |
|   其中 审计内 measure | 0.26 | 0.3% |  |
|   其中 audit_groups（independent_exact_audit） | 0.71 | 0.7% | 1 |
|   其中 回读 load_episode | 0.50 | 0.5% | 2 |
| 半程截断检查 group_truncations | 0.18 | 0.2% |  |
| 写盘 write_episode（csv/npz/json） | 0.79 | 0.8% |  |
| 写盘 save_json（审计外） | 0.14 | 0.1% | 20 |
| 速度剖面 QC qc_episode | 0.05 | 0.0% |  |
| 叠加预测误差 prediction_error | 0.01 | 0.0% |  |
| 其余（候选池载入、单机 npz 写盘、目录创建等） | 0.07 | 0.1% |  |

联合仿真：45002 步 × 6 机，166 次回滚，41.28 s → 每步每机 152.9 µs。 单机预演：6 次单机仿真共 244432 步，60.62 s → 每步 248.0 µs。
写盘字节数：planning 566307，episodes 合计 24118466（其中同步方式目录 18193427），qc 43043。
调用次数为 0（未计时成功）的包装：B 作业形态(非过境) draw_operation, B 作业段内连接 connect, B 形态-佯动 feint_shape, B 形态-区域搜索 search_shape, B 形态-巡逻 patrol_shape, B 形态-抵近观察 observation_shape, B 形态-突入 intrusion_shape, B 形态阶段进场/撤离预检 precheck_operation, B 撤离点 retreat_endpoint, B 衔接段(非过境) route_operation（均为该样本执行方式用不到的分支函数）。

## reconnaissance：`prod_f020_060` / `family_s15_dc9e63c745907aa8_ext_001_regular`

机数 6，任务组数 2；选中候选 567，试过 1 个候选；仿真时长 1114.12 s；执行状态 completed；任务结果 success；是否完整结束：True。

### 规划阶段（占 B 合计 `planning_wall_s` 的比例）

| 环节 | 耗时 s | 占比 | 调用次数 |
|---|---|---|---|
| 可行空间/TaskSpec | 0.00 | 0.0% | 6 |
| 作业形态生成 | 6.28 | 16.1% | 400 |
| 衔接段（进场+撤离+作业段连接） | 15.76 | 40.4% | 400 |
|   其中 进场 _approaches | 12.28 | 31.5% | 469 |
|   其中 撤离点 retreat_endpoint（非过境） | 0.32 | 0.8% | 1228 |
|   其中 作业段内连接 connect（非过境） | 1.91 | 4.9% | 2456 |
| 整航线检查 plan_checks | 8.07 | 20.7% | 399 |
| 既有输出预检 precheck | 7.63 | 19.6% | 393 |
| 骨架装配 assemble_skeleton | 0.17 | 0.4% | 393 |
| 多组组合（方位+装配+长度比） | 1.00 | 2.6% | 3001 |
| 写盘（planning_result/status） | 0.00 | 0.0% | 2 |
| 其余（场景加载、pickle 写盘、提案池循环本身等） | 0.01 | 0.0% |  |

### 仿真阶段（同步方式；占 C 合计的比例）

| 环节 | 耗时 s | 占比 | 调用次数 |
|---|---|---|---|
| 单机预演 rehearse | 60.51 | 53.9% | 1 |
|   其中 单机仿真 execute(solo) | 59.12 | 52.6% | 6 |
|   其中 单机判定 measure(solo) | 1.08 | 1.0% | 6 |
| 时刻安排 select_timing（含 2 m 间距检查） | 0.01 | 0.0% | 1 |
| 联合仿真 execute(joint) | 43.06 | 38.3% | 1 |
| 判定与标签 measure（labels.json） | 1.02 | 0.9% |  |
| 独立审计 audit_episode（含复算/列置换/前缀标签 3 次 measure） | 4.37 | 3.9% | 1 |
|   其中 审计内 measure | 2.09 | 1.9% |  |
|   其中 audit_groups（independent_exact_audit） | 1.41 | 1.3% | 1 |
|   其中 回读 load_episode | 0.66 | 0.6% | 2 |
| 半程截断检查 group_truncations | 1.90 | 1.7% |  |
| 写盘 write_episode（csv/npz/json） | 0.99 | 0.9% |  |
| 写盘 save_json（审计外） | 0.30 | 0.3% | 20 |
| 速度剖面 QC qc_episode | 0.05 | 0.0% |  |
| 叠加预测误差 prediction_error | 0.02 | 0.0% |  |
| 其余（候选池载入、单机 npz 写盘、目录创建等） | 0.06 | 0.1% |  |

联合仿真：55971 步 × 6 机，265 次回滚，43.06 s → 每步每机 128.2 µs。 单机预演：6 次单机仿真共 236851 步，59.12 s → 每步 249.6 µs。
写盘字节数：planning 1206510，episodes 合计 32867290（其中同步方式目录 22620102），qc 36101。
调用次数为 0（未计时成功）的包装：B 形态-佯动 feint_shape, B 形态-巡逻 patrol_shape, B 形态-突入 intrusion_shape（均为该样本执行方式用不到的分支函数）。

## monitoring：`prod_f180_220` / `family_s15_1c1cf42fbb718d98_ext_002_regular`

机数 8，任务组数 1；选中候选 87，试过 1 个候选；仿真时长 1873.02 s；执行状态 completed；任务结果 success；是否完整结束：True。

### 规划阶段（占 B 合计 `planning_wall_s` 的比例）

| 环节 | 耗时 s | 占比 | 调用次数 |
|---|---|---|---|
| 可行空间/TaskSpec | 0.00 | 0.0% | 3 |
| 作业形态生成 | 38.37 | 28.4% | 200 |
| 衔接段（进场+撤离+作业段连接） | 14.60 | 10.8% | 200 |
|   其中 进场 _approaches | 9.98 | 7.4% | 387 |
|   其中 撤离点 retreat_endpoint（非过境） | 0.30 | 0.2% | 1600 |
|   其中 作业段内连接 connect（非过境） | 1.87 | 1.4% | 1600 |
| 整航线检查 plan_checks | 38.24 | 28.3% | 190 |
| 既有输出预检 precheck | 42.84 | 31.7% | 124 |
| 骨架装配 assemble_skeleton | 0.51 | 0.4% | 124 |
| 多组组合（方位+装配+长度比） | 0.60 | 0.4% | 249 |
| 写盘（planning_result/status） | 0.00 | 0.0% | 2 |
| 其余（场景加载、pickle 写盘、提案池循环本身等） | 0.03 | 0.0% |  |

### 仿真阶段（同步方式；占 C 合计的比例）

| 环节 | 耗时 s | 占比 | 调用次数 |
|---|---|---|---|
| 单机预演 rehearse | 236.55 | 53.8% | 1 |
|   其中 单机仿真 execute(solo) | 233.52 | 53.1% | 8 |
|   其中 单机判定 measure(solo) | 3.02 | 0.7% | 8 |
| 时刻安排 select_timing（含 2 m 间距检查） | 0.02 | 0.0% | 1 |
| 联合仿真 execute(joint) | 181.00 | 41.1% | 1 |
| 判定与标签 measure（labels.json） | 3.05 | 0.7% |  |
| 独立审计 audit_episode（含复算/列置换/前缀标签 3 次 measure） | 10.27 | 2.3% | 1 |
|   其中 审计内 measure | 6.13 | 1.4% |  |
|   其中 audit_groups（independent_exact_audit） | 2.10 | 0.5% | 1 |
|   其中 回读 load_episode | 1.52 | 0.3% | 2 |
| 半程截断检查 group_truncations | 6.04 | 1.4% |  |
| 写盘 write_episode（csv/npz/json） | 2.22 | 0.5% |  |
| 写盘 save_json（审计外） | 0.52 | 0.1% | 20 |
| 速度剖面 QC qc_episode | 0.17 | 0.0% |  |
| 叠加预测误差 prediction_error | 0.03 | 0.0% |  |
| 其余（候选池载入、单机 npz 写盘、目录创建等） | 0.18 | 0.0% |  |

联合仿真：95839 步 × 8 机，2188 次回滚，181.00 s → 每步每机 236.1 µs。 单机预演：8 次单机仿真共 696661 步，233.52 s → 每步 335.2 µs。
写盘字节数：planning 2929863，episodes 合计 75914755（其中同步方式目录 52348767），qc 40174。
调用次数为 0（未计时成功）的包装：B 形态-佯动 feint_shape, B 形态-区域搜索 search_shape, B 形态-抵近观察 observation_shape, B 形态-突入 intrusion_shape（均为该样本执行方式用不到的分支函数）。

## feint：`prod_f100_140` / `family_s15_19db8d41d1ebea45_ext_003_regular`

机数 5，任务组数 1；选中候选 146，试过 1 个候选；仿真时长 1061.12 s；执行状态 completed；任务结果 success；是否完整结束：True。

### 规划阶段（占 B 合计 `planning_wall_s` 的比例）

| 环节 | 耗时 s | 占比 | 调用次数 |
|---|---|---|---|
| 可行空间/TaskSpec | 0.00 | 0.0% | 3 |
| 作业形态生成 | 4.02 | 11.1% | 200 |
| 衔接段（进场+撤离+作业段连接） | 14.88 | 41.1% | 200 |
|   其中 进场 _approaches | 13.80 | 38.1% | 345 |
|   其中 撤离点 retreat_endpoint（非过境） | 0.40 | 1.1% | 1000 |
|   其中 作业段内连接 connect（非过境） | 0.15 | 0.4% | 1000 |
| 整航线检查 plan_checks | 12.33 | 34.0% | 200 |
| 既有输出预检 precheck | 4.78 | 13.2% | 197 |
| 骨架装配 assemble_skeleton | 0.10 | 0.3% | 197 |
| 多组组合（方位+装配+长度比） | 0.10 | 0.3% | 395 |
| 写盘（planning_result/status） | 0.00 | 0.0% | 2 |
| 其余（场景加载、pickle 写盘、提案池循环本身等） | -0.00 | -0.0% |  |

### 仿真阶段（同步方式；占 C 合计的比例）

| 环节 | 耗时 s | 占比 | 调用次数 |
|---|---|---|---|
| 单机预演 rehearse | 56.77 | 57.9% | 1 |
|   其中 单机仿真 execute(solo) | 56.70 | 57.9% | 5 |
|   其中 单机判定 measure(solo) | 0.07 | 0.1% | 5 |
| 时刻安排 select_timing（含 2 m 间距检查） | 0.01 | 0.0% | 1 |
| 联合仿真 execute(joint) | 38.52 | 39.3% | 1 |
| 判定与标签 measure（labels.json） | 0.06 | 0.1% |  |
| 独立审计 audit_episode（含复算/列置换/前缀标签 3 次 measure） | 1.43 | 1.5% | 1 |
|   其中 审计内 measure | 0.16 | 0.2% |  |
|   其中 audit_groups（independent_exact_audit） | 0.63 | 0.6% | 1 |
|   其中 回读 load_episode | 0.48 | 0.5% | 2 |
| 半程截断检查 group_truncations | 0.11 | 0.1% |  |
| 写盘 write_episode（csv/npz/json） | 0.80 | 0.8% |  |
| 写盘 save_json（审计外） | 0.19 | 0.2% | 20 |
| 速度剖面 QC qc_episode | 0.04 | 0.0% |  |
| 叠加预测误差 prediction_error | 0.01 | 0.0% |  |
| 其余（候选池载入、单机 npz 写盘、目录创建等） | 0.07 | 0.1% |  |

联合仿真：53194 步 × 5 机，138 次回滚，38.52 s → 每步每机 144.8 µs。 单机预演：5 次单机仿真共 240438 步，56.70 s → 每步 235.8 µs。
写盘字节数：planning 770748，episodes 合计 25360671（其中同步方式目录 18078909），qc 22941。
调用次数为 0（未计时成功）的包装：B 形态-区域搜索 search_shape, B 形态-巡逻 patrol_shape, B 形态-抵近观察 observation_shape, B 形态-突入 intrusion_shape（均为该样本执行方式用不到的分支函数）。

## penetration：`prod_f060_100` / `family_s15_617b861a82b92aa4_ext_009_regular`

机数 8，任务组数 2；选中候选 688，试过 1 个候选；仿真时长 743.22 s；执行状态 completed；任务结果 success；是否完整结束：True。

### 规划阶段（占 B 合计 `planning_wall_s` 的比例）

| 环节 | 耗时 s | 占比 | 调用次数 |
|---|---|---|---|
| 可行空间/TaskSpec | 0.00 | 0.0% | 6 |
| 作业形态生成 | 1.58 | 5.1% | 400 |
| 衔接段（进场+撤离+作业段连接） | 19.96 | 63.9% | 400 |
|   其中 进场 _approaches | 19.29 | 61.8% | 599 |
|   其中 撤离点 retreat_endpoint（非过境） | 0.00 | 0.0% | 0 |
|   其中 作业段内连接 connect（非过境） | 0.00 | 0.0% | 0 |
| 整航线检查 plan_checks | 5.92 | 18.9% | 400 |
| 既有输出预检 precheck | 3.08 | 9.9% | 398 |
| 骨架装配 assemble_skeleton | 0.10 | 0.3% | 398 |
| 多组组合（方位+装配+长度比） | 0.49 | 1.6% | 3001 |
| 写盘（planning_result/status） | 0.00 | 0.0% | 2 |
| 其余（场景加载、pickle 写盘、提案池循环本身等） | 0.01 | 0.0% |  |

### 仿真阶段（同步方式；占 C 合计的比例）

| 环节 | 耗时 s | 占比 | 调用次数 |
|---|---|---|---|
| 单机预演 rehearse | 48.98 | 56.8% | 1 |
|   其中 单机仿真 execute(solo) | 48.92 | 56.8% | 8 |
|   其中 单机判定 measure(solo) | 0.06 | 0.1% | 8 |
| 时刻安排 select_timing（含 2 m 间距检查） | 0.01 | 0.0% | 1 |
| 联合仿真 execute(joint) | 33.53 | 38.9% | 1 |
| 判定与标签 measure（labels.json） | 0.15 | 0.2% |  |
| 独立审计 audit_episode（含复算/列置换/前缀标签 3 次 measure） | 2.15 | 2.5% | 1 |
|   其中 审计内 measure | 0.34 | 0.4% |  |
|   其中 audit_groups（independent_exact_audit） | 1.01 | 1.2% | 1 |
|   其中 回读 load_episode | 0.55 | 0.6% | 2 |
| 半程截断检查 group_truncations | 0.14 | 0.2% |  |
| 写盘 write_episode（csv/npz/json） | 0.88 | 1.0% |  |
| 写盘 save_json（审计外） | 0.22 | 0.2% | 20 |
| 速度剖面 QC qc_episode | 0.06 | 0.1% |  |
| 叠加预测误差 prediction_error | 0.02 | 0.0% |  |
| 其余（候选池载入、单机 npz 写盘、目录创建等） | 0.06 | 0.1% |  |

联合仿真：37317 步 × 8 机，156 次回滚，33.53 s → 每步每机 112.3 µs。 单机预演：8 次单机仿真共 209024 步，48.92 s → 每步 234.0 µs。
写盘字节数：planning 887042，episodes 合计 28189962（其中同步方式目录 20033651），qc 31898。
调用次数为 0（未计时成功）的包装：B 作业段内连接 connect, B 形态-佯动 feint_shape, B 形态-区域搜索 search_shape, B 形态-巡逻 patrol_shape, B 形态-抵近观察 observation_shape, B 撤离点 retreat_endpoint（均为该样本执行方式用不到的分支函数）。

