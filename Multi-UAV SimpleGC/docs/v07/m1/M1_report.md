# M1 判据层改写报告

## 结论

- C1–C12 已实施；Q0、Q1 均通过，未发现标签、轨迹或审计 P0。
- Q0 共 8 个测试方法，覆盖 71 个角色判定、T13 质量、P1–P3、G1–G5、事件时刻、独立审计、列置换及篡改检出；最终运行 21.946 s。
- T5 三检测器合计 0.286 s（9319 帧，单进程），满足 2 s 门槛。
- 独立审计在 Q0 样例上差异为 0；另 38 项离线回归通过。
- 竖切突击、搜索及各自前缀，与 `54842c2` 的完整标签和逐帧数组完全一致。
- Q1 重标 136 条（120 条主样本、16 条对照副本），含 7 条中止，耗时 558.689 s；审计差异为 0，交叉否定矛盾为 0。
- 120 个突击单机、18 个任务组新增失败，均由实际最近轮廓距离超过 50 m 解释；原轨迹独立复算并逐项留证。
- quick B 指定佯动样例的两个时序版本均由失败转为成功（4 个单机、2 个组）；原始 attempt 未改写。

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

## Q1 证据与结果

重标入口为 `scripts/relabel_v07_m1.py`，复核入口为 `scripts/review_v07_m1_evidence.py`。全部派生文件保存在 `F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/relabel_m1_20261015T171027158043Z/`，镜像三个源 attempt。原始文件按 manifest 校验，复制后校验哈希，写入后再次检查原标签、真值与逐帧标签未变化；Q1 未执行仿真。

[q1_summary.json](../evidence/m1/q1_summary.json) 按 attempt、意图、角色、层级和主样本／对照副本区分新旧结果。下表仅统计已经生成的主样本，成功与质量有效是独立口径；所有未知结果均为 0。

| attempt | 主样本／对照副本 | 旧集群成功／失败 | 新集群成功／失败 | 质量错误 | 中止 |
|---|---|---|---|---|---|
| `attempt_s2x_final_20261014T164338Z_4f85aaa3` | 72／8 | 68／4 | 56／16 | 4 | 4 |
| `attempt_s2x_final_20261015T053115Z_a3b834e8` | 37／8 | 34／3 | 30／7 | 1 | 3 |
| `attempt_s2_search_quick_b_20261015T090658Z_5ac915b5` | 11／0 | 9／2 | 11／0 | 0 | 0 |
| 合计 | 120／16 | 111／9 | 97／23 | 5 | 7 |

16 条对照副本全部保持成功，单独列入 `collection=process_1/process_2`，不重复计入主样本及视图。136 条均通过独立审计；限制区违规为 0、超时为 0，5 条质量错误来自间距不足。完整统计包括不保留的质量错误样本。

结果变化逐项见 [q1_changes.csv](../evidence/m1/q1_changes.csv)，新增失败子集见 [q1_new_failures.csv](../evidence/m1/q1_new_failures.csv)。

| 层级与角色 | 变化 | 数量 | 原因 |
|---|---|---|---|
| 突击单机 | 成功 → 失败 | 120 | `near_facility_contour=false`，最近轮廓距离为 53.267796–106.148610 m，全部大于 50 m |
| 突击任务组 | 成功 → 失败 | 18 | 组内存在上述失败成员，分布于 16 条 episode |
| 佯动单机 | 失败 → 成功 | 4 | 删除旧深入比例上限；实际深入比例均为 0.881，未进入禁飞区 |
| 佯动任务组 | 失败 → 成功 | 2 | 全员满足新版条件；即指令所列 quick B `family_s12_4d13d93f9171c446_ext_009_regular` 的两个时序版本 |

[q1_review.json](../evidence/m1/q1_review.json) 对全部 120 个新增失败单机再次从保存的真值独立计算距离，记录最小值、帧号、时刻、位置和设施几何；18 个新增失败组记录对应失败成员。新失败只有轮廓距离这一类原因，没有检测器系统性误判证据。集群层为 16 条成功转失败、2 条失败转成功、95 条保持成功、7 条保持失败。7 条中止的撤离事实均成立，主编组核心事件起点与确认时刻均缺失，指定突击任务结果仍为失败。

[q1_detectors.csv](../evidence/m1/q1_detectors.csv) 给出各意图的驻留、重访与折返分布；[q1_cross_negation.json](../evidence/m1/q1_cross_negation.json) 共记录 940 个定向格：713 个检查通过、62 个不适用、165 个因源角色未成功、质量不保留或中止而未执行，要求为“否”的格中无“是”。

[q1_approach.json](../evidence/m1/q1_approach.json) 的主样本任务组指定／实测逼近一致率为：过境 36/36，侦察 22/26，监视 8/8，佯动 28/40，突防 48/54。该分类不参与成败门禁。

三个 attempt 在均衡抽样前分别有 20、11、5 对满足配对条件；沿用原有家族内五意图均衡后，`primary` 均为 0，扩展视图分别有 52、29、11 条。视图还保留原登记表中未生成的 infeasible/pending 项，因此不能用视图的 `failed` 数量作为重标失败分母。[q1_io_check.json](../evidence/m1/q1_io_check.json) 确认代表性样本对通过 manifest、成对加载、观测重建与模型输入白名单检查。

## 异常与未决

- 首次完整 Q0 因弧段往返的候选筛选耗时偏长而中止；加入方位范围上界剪枝，仍用精确圆周间隙作最终判断。重跑与最终扩展测试均通过，未改阈值或测试预期。
- 用户已批准 T5 预期勘误及监视事件字段口径，按新版指令执行。仓库中设计导出的驻留段仍未列首尾条件，以指令 §7.2 和本轮用户确认优先；未修改设计阈值。
- 首次 Q1 盘点只读顶层登记表，将有独立登记表的 `process_1/process_2` 对照副本误报为未登记。该次尚未处理任何轨迹，不属于标签 P0；纠正目录盘点后在另一个全新目录完整执行。原始误报记录保留于 [q1_preflight_inventory.json](../evidence/m1/q1_preflight_inventory.json) 和 [q1_preflight_stop.json](../evidence/m1/q1_preflight_stop.json)，其中历史 `P0_STOP` 是当时脚本的错误分类，不代表最终 Q1 状态。
- 中止保留“指定突击任务未完成”的结果，同时独立输出撤离事实与 `abort_group_withdrawal_observed`；到撤离点仅为诊断，不作为中止行为成立条件。Q1 的 7 条中止样本均完成核对。
- 没有修改规划器、执行器、fastsim、S1 或公共抽样；只运行 Q0 所需 T9 两速度，没有其他新仿真。未使用 SciPy（本地 SciPy 对当前 NumPy 有版本警告），检测器仅依赖项目现有 NumPy。
