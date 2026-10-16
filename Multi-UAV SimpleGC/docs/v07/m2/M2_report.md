# M2 单机预演与时刻层报告

## 结论

- C1–C13 已落地，实施提交为 `b7d7be2` 至 `d799ed4`，基线 `e1fca53`。
- Q-A：A1–A11 全部通过（10 个测试方法，3.59 s）。
- Q-B：通过；20 个完整轮次全部算完，15 轮通过、5 轮 `rehearsal_failure`，另 3 轮 `input_missing`，仿真次数为 0。
- Q-C：竖切 8 条严格比较通过，16 个轨迹文件字节一致、16 个完整／前缀标签文件字段一致，独立审计全部通过。
- Q-A／Q-B／Q-C 验收范围内无实际 P0；Q-A 的负向审计用例按预期触发 P0_STOP。
- Q-D：尚未运行；C10 联合执行与 C12 真实轨迹诊断的端到端验收仍待 Q-D。
- 本报告为检查点 1 的阶段报告，不表示整个 M2 已验收完成。

## 条款对照

以下路径相对项目根目录；“已实现”不替代对应验收状态。

| 条款 | 内容 | 文件:函数 | 测试名／证据 | 状态 |
|---|---|---|---|---|
| C1 | 集中生成器参数 | `configs/generator/generator_v07_r1.json`；`task_v07/unified/config.py:load_generator` | Q-A 参数与时刻约束、配置核对 | 已实现 |
| C2 | 独立停止字段，保留驻留参数 | `task_v07/execution.py:execute,completion_budget`；`task_v07/expansion/pipeline.py:assemble_skeleton`；`episode_pipeline.py:assemble_episode` | A5、A6、A7；Q-C | 通过 |
| C3 | 单机行为与全组覆盖并集预演 | `task_v07/unified/rehearsal.py:evaluate_solos,rehearse` | A10；Q-B | 通过 |
| C4 | 按版本／draw 独立求解 | `task_v07/unified/timing.py:group_plan,episode_plan` | A1、A2、A3；Q-B | 通过 |
| C5 | 2 m 叠加门槛和首个可行 draw | `task_v07/unified/timing.py:select_timing`；`task_v07/expansion/solo_spacing.py:solo_interval_check` | A4；Q-B（含递次 draw=1 的接受实例） | 通过 |
| C6 | 删除指定两处恒速预筛 | `scripts/run_v07_s2_episode_batch.py:run_episode_job`；`task_v07/expansion/group_candidate_pool.py:independent_episode_pool` | 源码核对；Q-B `ext_008` 前四轮 | 已实现，独立接口与角色内部检查保留 |
| C7 | 同目标 30°、同向路程 130% | `task_v07/expansion/group_candidate_pool.py:independent_episode_pool`；`episode_pipeline.py:ConstrainedPlanner`；`candidate_search.py:choose_eligible` | 配置与两处调用核对；Q-D 待运行 | 已实现 |
| C8 | 撤离余量 50 m | `task_v07/expansion/pipeline.py:role_parameters` | 配置与参数传递核对；Q-D 待运行 | 已实现 |
| C9 | 部分完成时刻缺失则保守预算 | `task_v07/unified/rehearsal.py:joint_budget` | A8 | 通过 |
| C10 | 五轮预演、时刻、联合执行流程 | `scripts/run_v07_s2_episode_batch.py:run_episode_job` | A9；Q-D 待运行 | 单元检查通过，真实小试待完成 |
| C11 | 三类失败及最后实际类别 | `task_v07/unified/outcome.py:exhausted_failure`；批处理 `rejected` | A9；Q-B 类别范围 | 通过 |
| C12 | 接受时刻、分段误差、预演不一致 | `task_v07/unified/diagnostics.py`；`solo_spacing.py:prediction_error`；批处理 `write_result` | Q-D 待运行 | 已实现，真实轨迹验收待完成 |
| C13 | 从独立状态和帧数审计完整性 | `scripts/audit_v07_m1.py:audit_data,audit_episode` | A11 | 通过 |

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

尚未运行。固定 quick B 10 骨架、8 进程、60 分钟硬上限的真实小试不包含在当前检查点 1 验收结果中。

## 异常与未决

1. Q-B 首次运行时，自写重放脚本的 `geometry_*` 匹配了文件 `geometry_history.json`，将其当作目录读取而退出，产生 1 行部分 CSV。已改为只枚举 `geometry_[0-9][0-9]` 目录，并从头重跑成功；完整 CSV 已覆盖部分输出。[首次中断及修复记录](../evidence/m2/qb_stop.json)保留。按用户补充，这类工具脚本编程错误直接修复、记录后继续。
2. 缺输入的 3 个轮次不计行为失败，不补跑；名单与 Q-B 汇总一致。
3. CSV 初稿遗漏独立的“预演结果”列，预演详情已存在于 JSON。已补入 `rehearsal_status` 并从头重放，20 轮结果不变；同时检查通过／缺输入行类别为空、拒绝行类别属于 C11 三类。
4. Q-D 尚未运行，不作端到端完成或成功率承诺。
5. Q-C 的完整 22 条命令耗时 18.71 分钟，超过 15 分钟预估；该预估不是硬停止上限，运行未重启。范围外扩展样本造成的整体旧参考比较 FAIL 与竖切 8 条 PASS 分别保留。
