# Traj2Language v0.7 S2 修订轮全量统计

全量 attempt：`attempt_s2x_final_20261015T053115Z_a3b834e8`。冻结生成代码提交 `b7de35d71a60ada8dd4ab5055aac6cebc2f3035e`，工作进程 8。登记 60 个常规骨架（120 个时序请求）及 6 个中止请求，记录 126 项，未复用试点结果。

本项目输出防御方意图识别研究用的带标签合成轨迹。地图为随机抽象几何，执行后端为冻结的平动点质量模型；航点编排不针对真实地点或防御部署，不包含武器、电子压制、雷达规避或任务效果优化。

配置 SHA256：`94822513045c434dc2f713070728f1f99d18bcbea3933f8f092b85c5e4d78193`。抽样描述符 SHA256：`f2fabfae1126ebb1da5349c6255cf9a03997b58f4a6677a82e1279eaee46c615`。运行期间未修改生成代码；固定回归与分步记录见 [执行记录](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v07scene/Multi-UAV SimpleGC/docs/v07/S2_revision_report.md>)。

## 1. 骨架成功率与拒绝

成功骨架要求两种时序均生成、质量有效、独立审计通过且任务成功。几何候选搜索是有限预算，拒绝不宣称地图在数学上无解。

| 意图 | 登记骨架 | 成功配对 | 成功率 | 几何拒绝 | 运动学拒绝 | 规划间距拒绝 |
|---|---|---|---|---|---|---|
| 过境 | 12 | 4 | 33.33% | 8 | 0 | 0 |
| 侦察 | 12 | 5 | 41.67% | 6 | 0 | 0 |
| 游弋监视 | 12 | 0 | 0.00% | 12 | 0 | 0 |
| 佯动 | 12 | 4 | 33.33% | 7 | 0 | 1 |
| 突防 | 12 | 3 | 25.00% | 8 | 0 | 1 |

逐次几何尝试、拒绝细节和最后原因保存在 [统计证据](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/statistics.json>) 及各骨架的 `geometry_*/planning_rejection.json`。

## 2. 非设计失败、质量错误与时序

下表非设计失败率以质量有效且审计通过的常规 episode 为分母；生成质量错误另列。时序一致率以保留常规轨迹中的全部任务组为分母，未知时序不被删除以抬高一致率。

| 意图 | 实飞条数 | 质量有效条数 | 非设计失败数 | 非设计失败率 | 时序一致组/总组 | 一致率 |
|---|---|---|---|---|---|---|
| 过境 | 8 | 8 | 0 | 0.00% | 10/10 | 100.00% |
| 侦察 | 12 | 11 | 0 | 0.00% | 11/11 | 100.00% |
| 游弋监视 | 0 | 0 | 0 | 无可用分母 | 0/0 | 无可用分母 |
| 佯动 | 8 | 8 | 0 | 0.00% | 8/8 | 100.00% |
| 突防 | 6 | 6 | 0 | 0.00% | 6/6 | 100.00% |

失败判据逐意图统计：

| 意图 | 单机失败判据计数 | 任务组失败判据计数 |
|---|---|---|
| 过境 | {} | {} |
| 侦察 | {} | {} |
| 游弋监视 | {} | {} |
| 佯动 | {} | {} |
| 突防 | {} | {} |

规划采用实际单机测时得到的延迟和登记组间偏移，对全体飞机、整航线及两个时序版本按定速 10 Hz 检查；小于 \(10\,\mathrm{m}\) 的计划被拦截（名义预筛与真实延迟检查均适用，含中途悬停）。该估计不保证实飞间距，实测小于 \(2\,\mathrm{m}\) 一律作为生成错误剔除，不修改任务判据。

| 排除类别 | 条数 |
|---|---|
| planning_rejections | 86 |
| generation_errors | 1 |
| not_run | 3 |
| unverified | 0 |

## 3. 中止配对

同步中止继承引用常规骨架的全部公共条件和延迟。核心事件仍为进入禁飞区；只有主编组的四项实测撤离事实均满足，才标记“抵近后撤离”。其他组继续原路线。原引用规划失败时，按骨架编号升序尝试同地图的其他常规突防骨架，全部规划失败记 not_run；替换关系保存在 abort_pairing_registration.json。

| 中止请求 | 引用常规 episode | 状态/原因 | 撤离事实 | 主组时序 | 前缀相同帧 |
|---|---|---|---|---|---|
| family_s12_4d13d93f9171c446_ext_014_aborted_synchronous | family_s12_4d13d93f9171c446_ext_004_regular_synchronous | pending: all_same_map_penetration_references_planning_failed | None | None | None |
| family_s12_5024cb2ccea653ae_ext_014_aborted_synchronous | family_s12_5024cb2ccea653ae_ext_004_regular_synchronous | pending: all_same_map_penetration_references_planning_failed | None | None | None |
| family_s12_8412c1cdb40e54b1_ext_014_aborted_synchronous | family_s12_8412c1cdb40e54b1_ext_004_regular_synchronous | generated: failure | True | unknown | 4897 |
| family_s12_8e012bf033eb6821_ext_014_aborted_synchronous | family_s12_8e012bf033eb6821_ext_004_regular_synchronous | pending: all_same_map_penetration_references_planning_failed | None | None | None |
| family_s12_aa4c66be8e85d64d_ext_014_aborted_synchronous | family_s12_aa4c66be8e85d64d_ext_004_regular_synchronous | generated: failure | True | unknown | 8224 |
| family_s12_f2adfbfae12fbbad_ext_014_aborted_synchronous | family_s12_f2adfbfae12fbbad_ext_004_regular_synchronous | generated: failure | True | unknown | 7506 |

## 4. 交叉否定 960 项

结果 `INCOMPLETE`；PASS 88，出现“是”的请求 0，not_run 872；组级“是”见证共 0 项。

同 family、同公共骨架槽位内，A 模板判 B 轨迹；任务组先按完全相同的成员集合对应，否则逐个非空交集判定并注明。A 或 B 未形成任务成功且质量/审计有效的完整配对时记 not_run。任一组级“是”按本轮要求列为验收不通过项，其他请求继续执行。部分共享角色成立不解释为整个集群基础意图相同。

[逐条“是”：模板、轨迹、成员对应与触发判据](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v07scene/Multi-UAV SimpleGC/docs/v07/S2_revision_cross_yes_20261015T053115Z_a3b834e8.md>)；[全部 960 项原始结果](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/cross_negation.json>)。

## 5. 独立审计、截断、进程无关性与视图

| 独立审计项 | 数量 |
|---|---|
| episodes | 37 |
| region_differences | 0 |
| target_differences | 0 |
| event_or_metric_differences | 0 |
| uncovered_conditions | 0 |

截断检查：`{"PASS": 36, "not_run": 3}`。突击组的半程以自身实测终点保持完成为界，其他角色以实测作业结束为界，不把其他组继续执行的时间当成本组工作。缺失作业区间记 not_run。

全部新增条件及独立来源见 [条件 → 审计项](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v07scene/Multi-UAV SimpleGC/docs/v07/S2_phase2_condition_audit_map.md>)。审计不导入生产侧 `task_v07`，圈层、接近航向、角色事实、组内时序、跨组距离和主要目标均从 10 Hz 真值重算。

1/2 进程对比结果：`PASS`，骨架 `['family_s12_5024cb2ccea653ae_ext_000_regular', 'family_s12_4d13d93f9171c446_ext_000_regular']`；内容差异 0。对比重新执行，不计入 126 个请求或训练视图。[完整比较](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/process_comparison.json>)。 实际轨迹比较 4 对；仅规划输出比较 0 项。仅规划一致不证明实际轨迹一致；以下未生成项的实测进程对比未覆盖：[]

| 视图 | 条数 | 索引 |
|---|---|---|
| primary | 0 | [primary.csv](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/views/primary.csv>) |
| extended | 33 | [extended.csv](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/views/extended.csv>) |
| aborted | 3 | [aborted.csv](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/views/aborted.csv>) |
| failed | 0 | [failed.csv](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/views/failed.csv>) |
| pending | 0 | [pending.csv](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/views/pending.csv>) |

主对照按 family 五意图的成功配对数最小值平衡；其余可用成功轨迹进入扩展表。中止、非设计任务失败独立成表。规划拒绝、生成质量错误、未执行和未通过审计项均不进入训练视图，诊断样本排除。

## 6. 诊断分布（不设门槛）

| 角色/方法 | 含该角色骨架拒绝/登记 | 拒绝率 | 多向航向跨度 N/中位/P90/最大 | 分股数分布 |
|---|---|---|---|---|
| area_search | 4/9 | 44.44% | 6 / 128.671 / 152.436 / 152.436 | {"1": 4, "3": 2, "2": 4} |
| close_observation | 5/6 | 83.33% | 0 / 未测得 / 未测得 / 未测得 | {"1": 2} |
| feint | 14/18 | 77.78% | 6 / 128.671 / 143.903 / 143.903 | {"1": 2, "3": 4, "2": 2} |
| intrusion | 9/12 | 75.00% | 4 / 127.203 / 143.903 / 143.903 | {"1": 2, "3": 2, "2": 2} |
| monitoring | 14/14 | 100.00% | 0 / 未测得 / 未测得 / 未测得 | {} |
| transit | 8/12 | 66.67% | 2 / 110.502 / 110.502 / 110.502 | {"1": 8, "2": 2} |

角色拒绝率的分母为含该角色的登记骨架；整骨架拒绝可能来自其他组或跨组冲突，不能解释为该角色单独不可行率。航向和耗时诊断包括全部已仿真的常规轨迹（含单列剔除的生成错误），跨度只统计实际可测值。

| 意图 | 墙钟仿真时长：N/中位/P90/最大(s) | 仿真时间轴：N/中位/P90/最大(s) |
|---|---|---|
| 过境 | 8 / 89.035 / 157.418 / 160.626 | 8 / 1103.320 / 1397.430 / 1654.820 |
| 侦察 | 12 / 82.852 / 117.776 / 127.189 | 12 / 997.420 / 1311.660 / 1420.620 |
| 游弋监视 | 0 / 未测得 / 未测得 / 未测得 | 0 / 未测得 / 未测得 / 未测得 |
| 佯动 | 8 / 96.946 / 112.376 / 117.140 | 8 / 1025.820 / 1323.570 / 1483.520 |
| 突防 | 6 / 65.643 / 82.802 / 85.520 | 6 / 882.370 / 1098.620 / 1111.320 |

| 意图 | 登记同向/多向比例 | 保留轨迹同向/多向比例 | 登记合并后任务组数分布 | 保留轨迹任务组数分布 |
|---|---|---|---|---|
| 过境 | multi_direction: 7/12 (58.33%)；same_direction: 5/12 (41.67%) | multi_direction: 2/8 (25.00%)；same_direction: 6/8 (75.00%) | {"1": 7, "2": 4, "3": 1} | {"1": 6, "2": 2} |
| 侦察 | multi_direction: 7/12 (58.33%)；same_direction: 5/12 (41.67%) | multi_direction: 6/11 (54.55%)；same_direction: 5/11 (45.45%) | {"1": 7, "2": 4, "3": 1} | {"1": 11} |
| 游弋监视 | multi_direction: 7/12 (58.33%)；same_direction: 5/12 (41.67%) | 无可用样本 | {"1": 7, "2": 4, "3": 1} | {} |
| 佯动 | multi_direction: 7/12 (58.33%)；same_direction: 5/12 (41.67%) | multi_direction: 6/8 (75.00%)；same_direction: 2/8 (25.00%) | {"1": 7, "2": 4, "3": 1} | {"1": 8} |
| 突防 | multi_direction: 7/12 (58.33%)；same_direction: 5/12 (41.67%) | multi_direction: 4/6 (66.67%)；same_direction: 2/6 (33.33%) | {"1": 3, "2": 7, "3": 2} | {"1": 6} |

## 7. 实测图表与未满足项

所有曲线均为本次全量导出的实际轨迹；未生成的骨架不以规划预览替代实测图。完整来源及覆盖情况见 [图表覆盖清单](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/figures/figure_coverage.json>)。

![transit_1.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/figures/transit_1.png>)

![transit_2.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/figures/transit_2.png>)

![reconnaissance_1.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/figures/reconnaissance_1.png>)

![reconnaissance_2.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/figures/reconnaissance_2.png>)

![feint_1.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/figures/feint_1.png>)

![feint_2.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/figures/feint_2.png>)

![penetration_1.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/figures/penetration_1.png>)

![penetration_2.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/figures/penetration_2.png>)

![three_stock_multidirection.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/figures/three_stock_multidirection.png>)

![abort_vs_regular.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/figures/abort_vs_regular.png>)

![paired_timing_1.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/figures/paired_timing_1.png>)

![paired_timing_2.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/figures/paired_timing_2.png>)

缺失的图表要求：

- {"intent": "reconnaissance", "requirement": "multiple-group topdown", "reason": "no retained generated example"}
- {"intent": "monitoring", "requirement": "same_direction topdown", "reason": "no retained generated example"}
- {"intent": "monitoring", "requirement": "multi_direction topdown", "reason": "no retained generated example"}
- {"intent": "monitoring", "requirement": "multiple-group topdown", "reason": "no retained generated example"}
- {"intent": "monitoring", "requirement": "two topdowns", "reason": "fewer than two retained trajectories"}
- {"intent": "feint", "requirement": "multiple-group topdown", "reason": "no retained generated example"}
- {"intent": "penetration", "requirement": "multiple-group topdown", "reason": "no retained generated example"}
- {"requirement": "same_direction_monitoring_deployment.png", "reason": "no retained generated example"}

验收解释：交叉否定出现“是”属于不通过项；not_run 表示未覆盖，不计为通过。图表缺失如实列明。诊断分布和骨架成功率不擅自增加门槛。原始失败、排除项和每次几何尝试均保留。

可复核证据：[运行登记](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/registration.json>)；[执行汇总](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/execution_summary.json>)；[完整统计](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/statistics.json>)；[视图索引](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/view_index.json>)。
