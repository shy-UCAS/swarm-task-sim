# Traj2Language v0.7 S2 第二段总报告

本轮完成全部 126 个登记请求的处理与报告：31/60 个常规骨架形成完整成功配对，保留 64 条常规轨迹和 4 条设计中止轨迹。独立审计零差异、零未覆盖条件，未触发 P0。交叉否定实际执行的 232 项全部为“否”，其余 728 项因有效配对缺失未执行，覆盖结论为 `INCOMPLETE`；另有 2 条中止因引用骨架未生成而未执行，不能宣称全覆盖验收通过。

全量 attempt：`attempt_s2x_final_20261014T164338Z_4f85aaa3`。冻结生成代码提交 `e8fe856e51e8aa7b4b38697f811793e32fe22dd1`，工作进程 6。登记 60 个常规骨架（120 个时序请求）及 6 个中止请求，记录 126 项，未复用试点结果。

本项目输出防御方意图识别研究用的带标签合成轨迹。地图为随机抽象几何，执行后端为冻结的平动点质量模型；航点编排不针对真实地点或防御部署，不包含武器、电子压制、雷达规避或任务效果优化。

配置 SHA256：`94822513045c434dc2f713070728f1f99d18bcbea3933f8f092b85c5e4d78193`。抽样描述符 SHA256：`f2fabfae1126ebb1da5349c6255cf9a03997b58f4a6677a82e1279eaee46c615`。运行期间未修改生成代码；固定回归和试点历史见 [后续执行记录](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v07scene/Multi-UAV SimpleGC/docs/v07/S2_phase2_continuation_record.md>)。

## 1. 骨架成功率与拒绝

成功骨架要求两种时序均生成、质量有效、独立审计通过且任务成功。几何候选搜索是有限预算，拒绝不宣称地图在数学上无解。

| 意图 | 登记骨架 | 成功配对 | 成功率 | 几何拒绝 | 运动学拒绝 | 规划间距拒绝 |
|---|---|---|---|---|---|---|
| 过境 | 12 | 8 | 66.67% | 4 | 0 | 0 |
| 侦察 | 12 | 4 | 33.33% | 7 | 1 | 0 |
| 游弋监视 | 12 | 3 | 25.00% | 9 | 0 | 0 |
| 佯动 | 12 | 8 | 66.67% | 0 | 0 | 2 |
| 突防 | 12 | 8 | 66.67% | 1 | 0 | 2 |

另有 3 个骨架因至少一个时序版本出现生成错误而未形成完整成功配对，其中佯动 2 个、突防 1 个。最终规划拒绝合计 26 个骨架：几何 21、运动学 1、规划间距 4。

逐次几何尝试、拒绝细节和最后原因保存在 [统计证据](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/statistics.json>) 及各骨架的 `geometry_*/planning_rejection.json`。

## 2. 非设计失败、质量错误与时序

下表非设计失败率以质量有效且审计通过的常规 episode 为分母；生成质量错误另列。时序一致率以保留常规轨迹中的全部任务组为分母，未知时序不被删除以抬高一致率。

| 意图 | 实飞条数 | 质量有效条数 | 非设计失败数 | 非设计失败率 | 时序一致组/总组 | 一致率 |
|---|---|---|---|---|---|---|
| 过境 | 16 | 16 | 0 | 0.00% | 20/20 | 100.00% |
| 侦察 | 8 | 8 | 0 | 0.00% | 12/12 | 100.00% |
| 游弋监视 | 6 | 6 | 0 | 0.00% | 8/8 | 100.00% |
| 佯动 | 20 | 17 | 0 | 0.00% | 25/25 | 100.00% |
| 突防 | 18 | 17 | 0 | 0.00% | 30/30 | 100.00% |

失败判据逐意图统计：

| 意图 | 单机失败判据计数 | 任务组失败判据计数 |
|---|---|---|
| 过境 | {} | {} |
| 侦察 | {} | {} |
| 游弋监视 | {} | {} |
| 佯动 | {} | {} |
| 突防 | {} | {} |

规划采用实际单机测时得到的延迟和登记组间偏移，对全体飞机、整航线及两个时序版本按定速 10 Hz 检查；小于 \(6\,\mathrm{m}\) 的计划被拦截。该估计不保证实飞间距，实测小于 \(2\,\mathrm{m}\) 一律作为生成错误剔除，不修改任务判据。

| 排除类别 | 条数 |
|---|---|
| planning_rejections | 52 |
| generation_errors | 4 |
| not_run | 2 |
| unverified | 0 |

四条生成错误均因实测间距小于 \(2\,\mathrm{m}\)，其独立审计通过，任务和时序标签与实测一致：

| 骨架（family 简写） | 时序 | 实测最小间距 (m) |
|---|---|---|
| 502/ext_008 | 同步 | 1.300715 |
| 502/ext_008 | 递次 | 1.057904 |
| f2/ext_008 | 同步 | 1.381893 |
| f2/ext_009 | 同步 | 0.207931 |

独立明细表：[生成错误](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/views/generation_errors.csv>)、[规划拒绝](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/views/planning_rejections.csv>)、[未执行中止](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/views/not_run.csv>)；同目录 JSON 保留全部数值事实和拒绝历史。

## 3. 中止配对

同步中止继承引用常规骨架的全部公共条件和延迟。核心事件仍为进入禁飞区；只有主编组的四项实测撤离事实均满足，才标记“抵近后撤离”。其他组继续原路线。引用轨迹未生成时记 not_run，不换用另一个骨架。

| 中止请求 | 引用常规 episode | 状态/原因 | 撤离事实 | 主组时序 | 前缀相同帧 |
|---|---|---|---|---|---|
| family_s12_4d13d93f9171c446_ext_014_aborted_synchronous | family_s12_4d13d93f9171c446_ext_004_regular_synchronous | pending: referenced_regular_trajectory_not_generated | None | None | None |
| family_s12_5024cb2ccea653ae_ext_014_aborted_synchronous | family_s12_5024cb2ccea653ae_ext_004_regular_synchronous | generated: failure | True | unknown | 8909 |
| family_s12_8412c1cdb40e54b1_ext_014_aborted_synchronous | family_s12_8412c1cdb40e54b1_ext_004_regular_synchronous | generated: failure | True | unknown | 5140 |
| family_s12_8e012bf033eb6821_ext_014_aborted_synchronous | family_s12_8e012bf033eb6821_ext_004_regular_synchronous | pending: referenced_regular_trajectory_not_generated | None | None | None |
| family_s12_aa4c66be8e85d64d_ext_014_aborted_synchronous | family_s12_aa4c66be8e85d64d_ext_004_regular_synchronous | generated: failure | True | unknown | 6456 |
| family_s12_f2adfbfae12fbbad_ext_014_aborted_synchronous | family_s12_f2adfbfae12fbbad_ext_004_regular_synchronous | generated: failure | True | unknown | 6749 |

## 4. 交叉否定 960 项

结果 `INCOMPLETE`；PASS 232，出现“是”的请求 0，not_run 728；组级“是”见证共 0 项。

232 项实际执行的集群判定均为 `no`，没有 `unknown`；展开为 320 个任务组检查，其中 256 个按完全相同成员集合对应、64 个按非空交集对应，全部为 `no`。960 个模板/轨迹组合键唯一。从各 family / 公共槽位的成功配对数量独立计算出的可执行数同为 232，未执行数同为 728。

同 family、同公共骨架槽位内，A 模板判 B 轨迹；任务组先按完全相同的成员集合对应，否则逐个非空交集判定并注明。A 或 B 未形成任务成功且质量/审计有效的完整配对时记 not_run。任一组级“是”按本轮要求列为第二段验收不通过项，其他请求继续执行。部分共享角色成立不解释为整个集群基础意图相同。

[逐条“是”：模板、轨迹、成员对应与触发判据](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v07scene/Multi-UAV SimpleGC/docs/v07/S2_phase2_cross_yes_20261014T164338Z_4f85aaa3.md>)；[全部 960 项原始结果](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/cross_negation.json>)。

## 5. 独立审计、截断、进程无关性与视图

冻结前 S2 测试 120/120 PASS。最后一次三组固定回归 22/22 PASS：竖切 8 条保持逐字节一致，新角色 10 条标签逐字节一致；过境 4 条沿用已逐项列明的历史 `work_end_s` 和相应哈希变化，无新增或未解释的内容差异。回归始终走原适配层，详细比较见后续执行记录中的各回归 attempt。

| 独立审计项 | 数量 |
|---|---|
| episodes | 72 |
| region_differences | 0 |
| target_differences | 0 |
| event_or_metric_differences | 0 |
| uncovered_conditions | 0 |

截断检查：`{"PASS": 103, "not_run": 4}`。突击组的半程以自身实测终点保持完成为界，其他角色以实测作业结束为界，不把其他组继续执行的时间当成本组工作。缺失作业区间记 not_run。

全部新增条件及独立来源见 [条件 → 审计项](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v07scene/Multi-UAV SimpleGC/docs/v07/S2_phase2_condition_audit_map.md>)。审计不导入生产侧 `task_v07`，圈层、接近航向、角色事实、组内时序、跨组距离和主要目标均从 10 Hz 真值重算。

1/2 进程对比结果：`PASS`，骨架 `['family_s12_4d13d93f9171c446_ext_008_regular', 'family_s12_4d13d93f9171c446_ext_000_regular']`；内容差异 0。对比重新执行，不计入 126 个请求或训练视图。[完整比较](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/process_comparison.json>)。

| 视图 | 条数 | 索引 |
|---|---|---|
| primary | 10 | [primary.csv](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/views/primary.csv>) |
| extended | 54 | [extended.csv](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/views/extended.csv>) |
| aborted | 4 | [aborted.csv](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/views/aborted.csv>) |
| failed | 0 | [failed.csv](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/views/failed.csv>) |
| pending | 0 | [pending.csv](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/views/pending.csv>) |

主对照按 family 五意图的成功配对数最小值平衡；其余可用成功轨迹进入扩展表。中止、非设计任务失败独立成表。规划拒绝、生成质量错误、未执行和未通过审计项均不进入训练视图，诊断样本排除。

独立分区复核：126 个请求 ID 唯一；训练视图与排除表恰好覆盖全部 126 项，无重复、无遗漏；诊断样本 0；所有视图 CSV 行数与 JSON 索引一致。全量、中止及进程对比合计墙钟 6592.868 s。

## 6. 诊断分布（不设门槛）

| 角色/方法 | 含该角色骨架拒绝/登记 | 拒绝率 | 多向航向跨度 N/中位/P90/最大 | 分股数分布 |
|---|---|---|---|---|
| area_search | 6/9 | 66.67% | 4 / 180.000 / 180.000 / 180.000 | {"1": 2, "2": 4} |
| close_observation | 4/6 | 66.67% | 0 / 未测得 / 未测得 / 未测得 | {"1": 6} |
| feint | 3/18 | 16.67% | 22 / 180.000 / 180.000 / 180.000 | {"1": 18, "2": 22} |
| intrusion | 3/12 | 25.00% | 14 / 180.000 / 180.000 / 180.000 | {"2": 14, "1": 6} |
| monitoring | 10/14 | 71.43% | 10 / 177.743 / 179.274 / 179.274 | {"2": 10} |
| transit | 4/12 | 33.33% | 12 / 180.000 / 180.000 / 180.000 | {"1": 8, "2": 12} |

角色拒绝率的分母为含该角色的登记骨架；整骨架拒绝可能来自其他组或跨组冲突，不能解释为该角色单独不可行率。航向和耗时诊断包括全部已仿真的常规轨迹（含单列剔除的生成错误），跨度只统计实际可测值。

| 意图 | 墙钟仿真时长：N/中位/P90/最大(s) | 仿真时间轴：N/中位/P90/最大(s) |
|---|---|---|
| 过境 | 16 / 71.121 / 92.717 / 98.255 | 16 / 1096.870 / 1328.970 / 1418.720 |
| 侦察 | 8 / 56.313 / 130.726 / 131.562 | 8 / 838.720 / 1931.020 / 1933.820 |
| 游弋监视 | 6 / 388.184 / 754.619 / 757.818 | 6 / 2272.220 / 4325.470 / 4413.520 |
| 佯动 | 20 / 84.293 / 111.200 / 154.315 | 20 / 1117.420 / 1560.370 / 1650.120 |
| 突防 | 18 / 71.548 / 136.476 / 251.575 | 18 / 1018.670 / 1716.760 / 2366.420 |

| 意图 | 登记同向/多向比例 | 保留轨迹同向/多向比例 | 登记合并后任务组数分布 | 保留轨迹任务组数分布 |
|---|---|---|---|---|
| 过境 | multi_direction: 7/12 (58.33%)；same_direction: 5/12 (41.67%) | multi_direction: 10/16 (62.50%)；same_direction: 6/16 (37.50%) | {"1": 7, "2": 4, "3": 1} | {"1": 12, "2": 4} |
| 侦察 | multi_direction: 7/12 (58.33%)；same_direction: 5/12 (41.67%) | multi_direction: 4/8 (50.00%)；same_direction: 4/8 (50.00%) | {"1": 7, "2": 4, "3": 1} | {"1": 6, "3": 2} |
| 游弋监视 | multi_direction: 7/12 (58.33%)；same_direction: 5/12 (41.67%) | multi_direction: 6/6 (100.00%) | {"1": 7, "2": 4, "3": 1} | {"2": 2, "1": 4} |
| 佯动 | multi_direction: 7/12 (58.33%)；same_direction: 5/12 (41.67%) | multi_direction: 9/17 (52.94%)；same_direction: 8/17 (47.06%) | {"1": 7, "2": 4, "3": 1} | {"1": 11, "2": 4, "3": 2} |
| 突防 | multi_direction: 7/12 (58.33%)；same_direction: 5/12 (41.67%) | multi_direction: 11/17 (64.71%)；same_direction: 6/17 (35.29%) | {"1": 3, "2": 7, "3": 2} | {"3": 2, "2": 9, "1": 6} |

## 7. 实测图表与未满足项

所有曲线均为本次全量导出的实际轨迹；未生成的骨架不以规划预览替代实测图。完整来源及覆盖情况见 [图表覆盖清单](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/figures/figure_coverage.json>)。

共 13 张图，已逐张检查可读性：五种基础意图各 2 张俯视图，每种均包含多任务组和多向样本；1 张中止与对应常规轨迹并排图；2 组配对时序图分别为双任务组和三任务组。图表覆盖缺失项为 0。

![transit_1.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/figures/transit_1.png>)

![transit_2.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/figures/transit_2.png>)

![reconnaissance_1.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/figures/reconnaissance_1.png>)

![reconnaissance_2.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/figures/reconnaissance_2.png>)

![monitoring_1.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/figures/monitoring_1.png>)

![monitoring_2.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/figures/monitoring_2.png>)

![feint_1.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/figures/feint_1.png>)

![feint_2.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/figures/feint_2.png>)

![penetration_1.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/figures/penetration_1.png>)

![penetration_2.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/figures/penetration_2.png>)

![abort_vs_regular.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/figures/abort_vs_regular.png>)

![paired_timing_1.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/figures/paired_timing_1.png>)

![paired_timing_2.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/figures/paired_timing_2.png>)

验收解释：交叉否定出现“是”属于不通过项；not_run 表示未覆盖，不计为通过。图表缺失如实列明。诊断分布和骨架成功率不擅自增加门槛。原始失败、排除项和每次几何尝试均保留。

可复核证据：[运行登记](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/registration.json>)；[执行汇总](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/execution_summary.json>)；[完整统计](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/statistics.json>)；[视图索引](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261014T164338Z_4f85aaa3/view_index.json>)。
