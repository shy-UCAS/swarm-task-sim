# M2 单机预演与时刻层报告

## 结论

- C1–C13 已落地，实施提交为 `b7d7be2` 至 `d799ed4`，基线 `e1fca53`。
- Q-A：A1–A11 全部通过（10 个测试方法，3.59 s）。
- Q-B：通过；20 个完整轮次全部算完，15 轮通过、5 轮 `rehearsal_failure`，另 3 轮 `input_missing`，仿真次数为 0。
- Q-C：竖切 8 条严格比较通过，16 个轨迹文件字节一致、16 个完整／前缀标签文件字段一致，独立审计全部通过。
- Q-D：通过；固定 10 骨架全部走完，8 个完整配对、2 个完整拒绝，19 轮预演／143 次单飞／16 条联合 episode，耗时 53.53 分钟。
- Q-A–Q-D 验收范围内无实际 P0；Q-D 审计差异、预演状态／条件不一致均为 0；Q-A 的负向审计用例按预期触发 P0_STOP。
- 主要发现：多向侦察 5 轮预演失败，多向监视 5 轮同步时刻抽样耗尽；6 条 `ended_outside_warning` 失败记录均为超时且末帧仍在预警区内。
- M2 指令规定的检查已全部完成；本次检查点 2 只新增入口／报告工具、报告和小体量证据，生成器保持检查点 1 的已审查实现。

## 条款对照

以下路径相对项目根目录；“已实现”不替代对应验收状态。

| 条款 | 内容 | 文件:函数 | 测试名／证据 | 状态 |
|---|---|---|---|---|
| C1 | 集中生成器参数 | `configs/generator/generator_v07_r1.json`；`task_v07/unified/config.py:load_generator` | Q-A 参数与时刻约束、配置核对；Q-D 配置哈希 | 通过 |
| C2 | 独立停止字段，保留驻留参数 | `task_v07/execution.py:execute,completion_budget`；`task_v07/expansion/pipeline.py:assemble_skeleton`；`episode_pipeline.py:assemble_episode` | A5、A6、A7；Q-C | 通过 |
| C3 | 单机行为与全组覆盖并集预演 | `task_v07/unified/rehearsal.py:evaluate_solos,rehearse` | A10；Q-B | 通过 |
| C4 | 按版本／draw 独立求解 | `task_v07/unified/timing.py:group_plan,episode_plan` | A1、A2、A3；Q-B | 通过 |
| C5 | 2 m 叠加门槛和首个可行 draw | `task_v07/unified/timing.py:select_timing`；`task_v07/expansion/solo_spacing.py:solo_interval_check` | A4；Q-B（含递次 draw=1 的接受实例） | 通过 |
| C6 | 删除指定两处恒速预筛 | `scripts/run_v07_s2_episode_batch.py:run_episode_job`；`task_v07/expansion/group_candidate_pool.py:independent_episode_pool` | 源码核对；Q-B `ext_008` 前四轮 | 已实现，独立接口与角色内部检查保留 |
| C7 | 同目标 30°、同向路程 130% | `task_v07/expansion/group_candidate_pool.py:independent_episode_pool`；`episode_pipeline.py:ConstrainedPlanner`；`candidate_search.py:choose_eligible` | 配置与两处调用核对；Q-D | 通过 |
| C8 | 撤离余量 50 m | `task_v07/expansion/pipeline.py:role_parameters` | 配置与参数传递核对；Q-D | 通过 |
| C9 | 部分完成时刻缺失则保守预算 | `task_v07/unified/rehearsal.py:joint_budget` | A8 | 通过 |
| C10 | 五轮预演、时刻、联合执行流程 | `scripts/run_v07_s2_episode_batch.py:run_episode_job` | A9；Q-D 10 骨架完整处理 | 通过 |
| C11 | 三类失败及最后实际类别 | `task_v07/unified/outcome.py:exhausted_failure`；批处理 `rejected` | A9；Q-B 类别范围；Q-D 两条五轮耗尽历史 | 通过 |
| C12 | 接受时刻、分段误差、预演不一致 | `task_v07/unified/diagnostics.py`；`solo_spacing.py:prediction_error`；批处理 `write_result` | Q-D 16 条联合轨迹诊断 | 通过 |
| C13 | 从独立状态和帧数审计完整性 | `scripts/audit_v07_m1.py:audit_data,audit_episode` | A11；Q-D 16 条独立审计 | 通过 |

## Q-A

测试入口：`tests/test_v07_m2_timing_rehearsal.py`。完整证据：[qa_results.json](../evidence/m2/qa_results.json)。

| 编号 | 结果 |
|---|---|
| A1 | 200 组、400 个计划通过；同步最大跨度 5.8856 s；递次批数、间隔、批内跨度及非负 0.1 s 网格均满足预期 |
| A2 | 两版各 20 个 draw 重复结果字节一致，改变另一版 draw 不影响本版 |
| A3 | 骨架未变，两个版本与各 draw 的条件摘要一致 |
| A4 | 1.9 m 拒绝、2.1 m 通过 |
| A5 | 无新停止字段的短竖切仿真与 `e1fca53` 基线均完成，425 帧轨迹 NPZ 字节一致 |
| A6 | 新停止轨迹 373 帧为旧轨迹 425 帧的精确前缀；各机终点距离约 1.674 m、速度约 0.780 m/s |
| A7 | 两种停止条件下，抵近驻留均于 38.1 s 开始、63.1 s 结束 |
| A8 | 任一单机完成时刻缺失时使用保守预算，不抛异常 |
| A9 | 预演、时刻冲突、预演三轮历史完整，顶层 `rehearsal_failure` 且 `exhausted=true` |
| A10 | T1 过境、T3 抵近、T12 突击均成功；T1 用作抵近时失败条件包含 `observation_dwell` |
| A11 | completed／timeout 完整标签通过；running 与完整标签冲突、错误帧数、删除真值帧均触发 P0_STOP |

## Q-B

最终从头重放耗时 12.33 s。全部 20 个完整轮次算完，另 3 个批准的缺输入轮次如实标记；原始骨架、校准记录、单机 NPZ 的读取前后哈希一致，未仿真。CSV 的 `rehearsal_status` 单独记录预演结果，`status` 记录本轮最终状态，空类别单元格表示 `null`。

证据：[逐轮 CSV](../evidence/m2/qb_offline_replay.csv)、[汇总](../evidence/m2/qb_summary.json)、[预演、重抽及源文件哈希](../evidence/m2/qb_details.json)。

| 意图 | quick B 旧类别计数 | 新状态／类别计数 |
|---|---|---|
| 过境 | passed 2；planning_spacing_rejection 1 | passed 3 |
| 侦察 | passed 1；planning_spacing_rejection 2；kinematic_infeasible 2；interrupted 1 | passed 3；rehearsal_failure 2；input_missing 1 |
| 监视 | kinematic_infeasible 1；interrupted 2 | rehearsal_failure 1；input_missing 2 |
| 佯动 | passed 1；planning_spacing_rejection 4；kinematic_infeasible 1 | passed 5；rehearsal_failure 1 |
| 突防 | passed 2；planning_spacing_rejection 3 | passed 4；rehearsal_failure 1 |

多向佯动 `ext_008` 前四轮均从旧 `planning_spacing_rejection` 变为通过，两版均接受 draw 0。同步／递次最小间距分别为：22.026／22.749 m、22.026／22.749 m、22.026／8.987 m、15.924／18.249 m。第五轮因成员缺失进入戒备区的行为及核心事件而预演失败。

五轮预演失败分别来自：侦察的 `ended_outside_warning`（第二轮另有全组覆盖率 0.7872，低于 0.80）；监视的 `patrol_revisit` 和 `ended_outside_warning`；佯动的 `entered_alert`、`single_alert_visit` 与核心事件缺失；突防的 `near_facility_contour`。没有类别越界。

这些轨迹来自旧 1 m 停止条件，结果只验证重放逻辑，不代表新停止条件下的真实小试。

## Q-C

运行现有命令 `scripts/run_v07_s2_expansion.py regression --workers 8`，固定 22 条，仅比较竖切 8 条。新输出目录：`SwarmData/v07_dataset/attempt_s2x_regress_20261016T020125Z_61ce93b2`。

严格比较入口为 `scripts/check_v07_m2_regression.py`：两种轨迹文件逐字节比较，`labels.json` 与 `prefix_labels.json` 逐字段比较，并保存哈希。旧竖切标签路径及 `execution.departure_delays`、`pipeline.timing_plans` 未修改。

竖切 8 条全部通过：16 个轨迹文件字节一致，16 个完整／前缀标签文件字段一致，8 条独立审计均 PASS。逐条哈希和差异列表见 [qc_regression.json](../evidence/m2/qc_regression.json)。

现有命令共完成 22 条，耗时 1122.87 s（18.71 分钟），全部独立审计 PASS。其整体旧参考比较返回 `FAIL`／退出码 1：记录 9015 项内容差异，其中竖切 episode 与骨架均为 0；过境 episode 2406 项、新角色 episode 6203 项，另有扩展骨架／校准记录 406 项。按 §8.3，本阶段只比较竖切 8 条，扩展 14 条不计入 Q-C 一致性通过条件，未逐项验收这些范围外差异，也未为消除差异修改实现或基线。Q-C 严格比较脚本返回 PASS／退出码 0。

## Q-D

结果：**PASS**。固定 10 个骨架、8 进程，一次运行，墙钟 3211.99 s（53.53 分钟），硬上限 60 分钟。输出：`attempt_m2_trial_20261016T022948423699Z`。

结果计数：8 个完整配对、2 个完整拒绝。单机仿真 143 次（精确计数）；预演 19 轮；联合 episode 16 条；审计差异 0。8 对 `condition_digest` 一致，16 条模型输入白名单全部通过，均为 `generated`／`completed`／`success`。

全局实测最小间距为 2.122347 m；各 episode 分段最小间距预测误差的绝对值最大分别为结束前 0.115669 m、结束后 0.028559 m。这是本次样本的实测结果，不消除指令 §7.5 所述结束后位置误差的已知局限。

S 为同步，Q 为递次；最后列为结果状态不一致的机次。分段误差单位 m，定义为 \(d_{\mathrm{pred}}-d_{\mathrm{actual}}\)，每版按“单机记录结束前／后”列出。通过轮次的类别为 `null`。结束前指机对两成员均未超出各自平移后的单飞末帧，结束后指至少一成员超出。— 表示未产生或未接受。

| 骨架简写 | 意图／登记逼近方式 | 结果 | 轮数 | 每轮类别 | 接受 draw | 执行状态 | 实测最小间距 m | 分段预测误差 m（前／后） | 预演不一致 |
|---|---|---|---:|---|---|---|---|---|---:|
| 5024…/ext_000 | 过境／同向 | paired；S:success；Q:success | 1 | 1:null | 1:S0/Q0 | S:completed；Q:completed | S:11.135；Q:11.135 | S:-7.16575e-06/2.02409e-08；Q:-3.70058e-10/-1.20646e-06 | S:0；Q:0 |
| f2ad…/ext_000 | 过境／多向 | paired；S:success；Q:success | 1 | 1:null | 1:S0/Q0 | S:completed；Q:completed | S:4.06794；Q:17.8474 | S:2.58485e-06/1.1391e-05；Q:0.000113356/-0.000917414 | S:0；Q:0 |
| 4d13…/ext_001 | 侦察／同向 | paired；S:success；Q:success | 1 | 1:null | 1:S0/Q0 | S:completed；Q:completed | S:22.3604；Q:18.8211 | S:0.00540264/0.000320925；Q:-0.115669/8.60798e-05 | S:0；Q:0 |
| 4d13…/ext_006 | 侦察／多向 | rejected | 5 | 1:rehearsal_failure；2:rehearsal_failure；3:rehearsal_failure；4:rehearsal_failure；5:rehearsal_failure | — | — | — | — | — |
| 5024…/ext_002 | 监视／同向 | paired；S:success；Q:success | 1 | 1:null | 1:S11/Q0 | S:completed；Q:completed | S:2.53802；Q:3.52108 | S:-0.00261056/0.0168913；Q:-0.00184513/0.0168683 | S:0；Q:0 |
| 4d13…/ext_007 | 监视／多向 | rejected | 5 | 1:timing_conflict；2:timing_conflict；3:timing_conflict；4:timing_conflict；5:timing_conflict | 1:S—/Q8；2:S—/Q2；3:S—/Q3；4:S—/Q2；5:S—/Q0 | — | — | — | — |
| 4d13…/ext_003 | 佯动／同向 | paired；S:success；Q:success | 1 | 1:null | 1:S0/Q0 | S:completed；Q:completed | S:2.41325；Q:2.12235 | S:-0.00791226/-0.000203216；Q:-0.00167772/-0.000806921 | S:0；Q:0 |
| 4d13…/ext_008 | 佯动／多向 | paired；S:success；Q:success | 1 | 1:null | 1:S1/Q0 | S:completed；Q:completed | S:5.61643；Q:5.61453 | S:2.07854e-06/-0.00527512；Q:-1.31025e-10/-0.00556279 | S:0；Q:0 |
| 4d13…/ext_004 | 突防／同向 | paired；S:success；Q:success | 1 | 1:null | 1:S0/Q0 | S:completed；Q:completed | S:6.07504；Q:16.6483 | S:0.00306414/0.0236098；Q:-0.00050541/0.0285589 | S:0；Q:0 |
| 4d13…/ext_009 | 突防／多向 | paired；S:success；Q:success | 2 | 1:timing_conflict；2:null | 1:S—/Q—；2:S0/Q0 | S:completed；Q:completed | S:12.0656；Q:15.7638 | S:-0.00944606/-0.0253769；Q:-9.46374e-05/-0.0267946 | S:0；Q:0 |

完整骨架 ID、逐轮成员／条件、接受时刻参数、两段误差及实测证据见 [qd_summary.json](../evidence/m2/qd_summary.json) 和 [qd_skeletons.csv](../evidence/m2/qd_skeletons.csv)。

预演结果状态不一致共 0 机次，条件不一致共 0 机次；逐条条件变化见 [qd_rehearsal_inconsistencies.json](../evidence/m2/qd_rehearsal_inconsistencies.json)。

两个最终拒绝均为 `exhausted=true`，顶层类别保留最后一轮的实际类别，逐轮历史完整。多向侦察第 1 轮仅 `uav_02` 未撤出预警区；第 2 轮 `uav_04` 未撤出且组覆盖率为 0.7872；第 3 轮 `uav_04` 缺少有效观察和核心事件，覆盖率为 0.520367；第 4、5 轮 `uav_02`、`uav_04` 未撤出，覆盖率分别为 0.582567、0.309229。后四轮覆盖率均低于 0.80。

多向监视 5 轮单机预演全部通过，每轮递次版分别在 draw 8、2、3、2、0 接受；同步版每轮均用尽 20 次抽样，逐轮“20 次中最大的叠加最小间距”依次为 0.444024、0.691183、0.511718、0.691183、0.624461 m，均低于 2 m。这仅说明本次采样组合被拒绝，不代表不存在可行组合。同向监视同步版在 draw 11 接受，多向佯动在 draw 1 接受，多向突防第 2 轮接受，记录验证了按版本重抽和换组合流程。

### ended_outside_warning 成员诊断

状态、观测时长来自同轮 `rehearsal.json` 的 `execution_status`、`last_sample_s`；时长为从 0 起的末个 10 Hz 观测时刻。预算按用户批准，从同轮 `skeleton.json` 的组骨架和全员零延迟调用 `completion_budget` 恢复保守估计。距离按用户批准，由同轮单机 NPZ 末帧 EN 坐标与注册场景的目标预警区，通过 `geometry_facts` 计算；表内为边界距离绝对值，另列内／外。未改生成器、未补仿真。

逐列来源和未取绝对值的有符号距离见 [CSV](../evidence/m2/qd_ended_outside_warning.csv)，源文件 SHA256 见 [JSON](../evidence/m2/qd_ended_outside_warning.json)。

| 骨架简写 | 轮次 | 成员 | 单飞状态 | 单飞观测时长 s | 保守预算 s | 距预警区边界 m | 终帧位置 |
|---|---:|---|---|---:|---:|---:|---|
| 4d13…/ext_006 | 1 | uav_02 | timeout | 2964.0 | 2964.1 | 98.179968 | 内 |
| 4d13…/ext_006 | 2 | uav_04 | timeout | 3061.0 | 3061.1 | 511.540460 | 内 |
| 4d13…/ext_006 | 4 | uav_02 | timeout | 3383.6 | 3383.7 | 512.268061 | 内 |
| 4d13…/ext_006 | 4 | uav_04 | timeout | 3383.6 | 3383.7 | 511.543482 | 内 |
| 4d13…/ext_006 | 5 | uav_02 | timeout | 3422.1 | 3422.2 | 511.374489 | 内 |
| 4d13…/ext_006 | 5 | uav_04 | timeout | 3422.1 | 3422.2 | 99.699532 | 内 |

以上为 2 名成员在不同轮次的 6 条失败记录，目标均为 `facility_02`。终帧距边界 98.18–512.27 m 且均在区内，与失败条件一致；这些超时轨迹的末个 10 Hz 观测时刻均比保守预算少 0.1 s。

### Q-D 补充验收：实测时序与严格配对资格

基于 `bb7670b` 的只读补充验收为 **PASS**。从标签中每名成员的实际 `core_event.t_s` 独立重算，16/16 条 episode、28/28 个任务组次（同步 14、递次 14）的分类、事件时间及分批结构均与指定模式、标签和指标一致；14/14 个递次任务组的批次成员、完整性和批次顺序一致。同步最大实测跨度为 5.4 s，递次最小实测批间空隙为 42.3 s，递次最大批内跨度为 4.9 s。逐组实测时刻、指定／实测批次和逐项比较见 [qd_coordination_check.json](../evidence/m2/qd_coordination_check.json) 的 `episode_checks`。

8/8 对原始记录通过正式 `_paired()`，各项独立配对条件均满足。完整 20 条记录调用 `make_views()` 后计数为 `primary=0`、`extended=16`、`aborted=0`、`failed=4`、`pending=0`；三个 family 的五意图均衡配额均为 0，故 16 条有效 episode 全部进入 extended，两个拒绝骨架的四条记录进入 failed，未误计为成功配对。family 平衡与逐条视图归属见证据的 `views`。

不一致为 0；Q-D 全部 585 个原始文件的核验前后内容哈希一致，生产／测试代码及配置未改动，未运行任何仿真。**M2 最终补充验收通过，M2 正式关闭，允许进入 M3。** 本任务未启动 M3。

## 异常与未决

1. Q-B 首次运行时，自写重放脚本的 `geometry_*` 匹配了文件 `geometry_history.json`，将其当作目录读取而退出，产生 1 行部分 CSV。已改为只枚举 `geometry_[0-9][0-9]` 目录，并从头重跑成功；完整 CSV 已覆盖部分输出。[首次中断及修复记录](../evidence/m2/qb_stop.json)保留。按用户补充，这类工具脚本编程错误直接修复、记录后继续。
2. 缺输入的 3 个轮次不计行为失败，不补跑；名单与 Q-B 汇总一致。
3. CSV 初稿遗漏独立的“预演结果”列，预演详情已存在于 JSON。已补入 `rehearsal_status` 并从头重放，20 轮结果不变；同时检查通过／缺输入行类别为空、拒绝行类别属于 C11 三类。
4. Q-D 用时 53.53 分钟，超过 30–45 分钟预估，未超过 60 分钟硬上限；一次运行完成，未重启或补仿真。两类完整拒绝已在上文解释，本阶段不修改几何、判据或预算来提升成功率。
5. Q-C 的完整 22 条命令耗时 18.71 分钟，超过 15 分钟预估；该预估不是硬停止上限，运行未重启。范围外扩展样本造成的整体旧参考比较 FAIL 与竖切 8 条 PASS 分别保留。
6. Q-D 离线探查中，Conda 不接受带实际换行的 `python -c` 参数，改为单行后继续；一次 PowerShell 核验把两个空 `episodes` 对象的 null 管道输出计入数量，过滤 null 后核对为 16，与正式汇总及 16 份审计回执一致。提交命令曾在运行 Git 前检查尚未初始化的退出码而误报，已将检查限定在 Git 命令之后。这些工具调用问题均已修复，未改动仿真输入或结果。正式报告脚本首次完整收集返回 PASS。
7. `rehearsal.json` 不保存时长预算与边界距离，已依用户明确批准从同轮骨架、单机 NPZ 和注册场景离线补算，未增加生成器字段。当前没有阻塞 M2 指令验收的未决项。
