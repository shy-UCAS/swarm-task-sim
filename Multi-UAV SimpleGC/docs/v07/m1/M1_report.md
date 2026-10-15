# M1 判据层改写报告

## 结论

- C1–C12 已实施；Q0 全部通过，当前未发现 P0。
- Q0 共 8 个测试方法，覆盖 71 个角色判定、T13 质量、P1–P3、G1–G5、事件时刻、独立审计、列置换及篡改检出；最终运行 21.946 s。
- T5 三检测器合计 0.286 s（9319 帧，单进程），满足 2 s 门槛。
- 独立审计在 Q0 样例上差异为 0；另 38 项离线回归通过。
- 竖切突击、搜索及各自前缀，与 `54842c2` 的完整标签和逐帧数组完全一致。
- Q1 尚未开始；检查点 1 推送后按指令执行，不提前宣称存量重标通过。

## 条款对照

路径相对 `Multi-UAV SimpleGC/`；测试名均位于 `tests/test_v07_m1_criteria.py`，回归入口为 `scripts/check_v07_m1_regression.py`。

| 条款 | 内容 | 文件:函数 | 测试名 | 状态 |
|---|---|---|---|---|
| C1 | 冻结配置 | `configs/criteria/criteria_v07_r1.json`；`task_v07/criteria.py:load_criteria` | Q0 全部 | 完成 |
| C2 | 三检测器 | `task_v07/detectors.py:dwell,revisit,coverage` | `test_T1_T13_role_matrix_and_audit`、`test_performance_and_cross_negation` | 完成 |
| C3 | 六角色与中止条件 | `task_v07/labels.py:measure` → `criteria_labels.py:measure_criteria`；`expansion/abort_measurement.py:observed_abort` | 角色矩阵、`test_P1_P3_prefixes` | 完成 |
| C4 | 起点与确认时刻 | `task_v07/criteria_labels.py:measure_criteria` | `test_event_times_and_diagnostics`、前缀测试 | 完成 |
| C5 | 旧量降诊断 | `task_v07/criteria_diagnostics.py:role_diagnostics,group_revisit_diagnostic` | 角色矩阵、事件与折返诊断 | 完成 |
| C6 | 组贡献、覆盖、实测逼近 | `task_v07/criteria_labels.py:measure_criteria,approach_classification` | `test_G1_shared_coverage`、`test_G5_measured_headings_do_not_gate_success` | 完成 |
| C7 | 集群结果与两个独立标志 | `task_v07/expansion/multi_labels.py:measure_groups` | `test_G2_G3_groups_and_G4_G5_views_approach` | 完成 |
| C8 | 限制区质量违规 | `task_v07/criteria.py:quality_facts` | T13、质量篡改检出 | 完成 |
| C9 | 配对和扩展视图 | `task_v07/expansion/views.py:_paired`；`scripts/run_v07_s2_episode_batch.py:write_result` | G2、G4；8 项视图回归 | 完成 |
| C10 | 独立实现与交叉否定 | `scripts/audit_v07_m1_detectors.py`；`audit_v07_m1.py:audit_data`；`cross_v07_m1.py:cross_group` | Q0 全部、`test_dwell_erratum_and_audit_rejects_mutations` | 完成 |
| C11 | 标签新版本 | `task_v07/labels.py`；`expansion/multi_labels.py` | Q0 输出与竖切基线逐字段对照 | 完成 |
| C12 | 规范单行勘误 | `docs/v07/v07_spec_r4a1_errata.md` | 原规范文件无差异 | 完成 |

## Q0 证据

逐样例原始事件、检测器结果与数值见 [q0_results.json](../evidence/m1/q0_results.json)；离线回归及竖切对照见 [regression_results.json](../evidence/m1/regression_results.json)。

| 样例 | 驻留／重访 | 成功角色（其余被测试角色均失败） | 核对 |
|---|---|---|---|
| T1、T2 | 否／否 | 过境 | 通过 |
| T3、T4 | 是／否 | 抵近观察 | 通过 |
| T5、T6 | 否／是 | 监视 | 通过 |
| T7 | 否／否 | 过境；作业段折返 1 次 | 通过 |
| T8 | 否／否 | 过境、区域搜索 | 通过 |
| T9 两速度、T9c | 否／否 | 过境 | 通过 |
| T10 | 不测／不测 | 佯动 | 通过 |
| T11 | 不测／不测 | 无 | 通过 |
| T12 | 不测／不测 | 突击 | 通过 |
| T13 | — | `constraint_violation`，`retained=false` | 通过 |
| P1、P2、P3 | 未确认行为不出现 | 抵近观察、监视、过境均未知 | 通过 |
| G1 | 两机足迹并集 | 组覆盖达到 0.80，组成功 | 通过 |
| G2、G3 | 主任务与全组分别汇总 | 突防主组成功可保留集群成功，非突防任一组失败则失败 | 通过 |
| G4 | 一版超时 | 配对排除、扩展保留 | 通过 |
| G5 | 实测跨度 20°、75°、45°、缺失 | 同向、多向、中间、未知；均不影响任务成功 | 通过 |

T1 事件取交点后首个 10 Hz 采样。T3 驻留起点在悬停前约 4.97 s，确认晚 20 s。T5 重访确认为 580.0 s，落在用户批准的 \(580.1\pm0.1\,\mathrm{s}\) 内；圆周连接帧 112.5 s 使用该圆周段的解析切向速度。监视核心事件起点与确认均为预警进入 76.3 s，重访事件另存。

T9 使用冻结配置 `94822513045c434dc2f713070728f1f99d18bcbea3933f8f092b85c5e4d78193`：

| 巡航速度 | 拐角附近最低速度 | 跨拐角 20 s 窗口最小首尾距离 | 仿真墙钟 |
|---|---|---|---|
| 10 m/s | 0.184597 m/s | 91.209021 m | 3.547 s |
| 4 m/s | 0.411291 m/s | 51.289106 m | 8.207 s |

最低速度测量范围为所有跨越最近拐角帧的 20 s 窗口并集；具体帧范围见 JSON。T9c 同时验证：只检查到均值的距离会误判，加入首尾距离后不判驻留。

## Q1

待执行：按指令三个 attempt 的全部已生成 episode（含中止）重标；原目录只读，派生结果另存。初步记录行盘点分别为 72、37、11 个有路径记录；正式分母以实际 episode 文件核对为准，区别于设计文档中的历史计数。

## 异常与未决

- 首次完整 Q0 因弧段往返的候选筛选耗时偏长而中止；加入方位范围上界剪枝，仍用精确圆周间隙作最终判断。重跑与最终扩展测试均通过，未改阈值或测试预期。
- 用户已批准 T5 预期勘误及监视事件字段口径，按新版指令执行。仓库中设计导出的驻留段仍未列首尾条件，以指令 §7.2 和本轮用户确认优先；未修改设计阈值。
- 中止保留“指定突击任务未完成”的结果，同时独立输出撤离事实与 `abort_group_withdrawal_observed`；到撤离点仅为诊断，不作为中止行为成立条件。该行为将在 Q1 中止样本上继续核对。
- 没有修改规划器、执行器、fastsim、S1 或公共抽样；只运行 Q0 所需 T9 两速度，没有其他新仿真。未使用 SciPy（本地 SciPy 对当前 NumPy 有版本警告），检测器仅依赖项目现有 NumPy。
