# Traj2Language v0.7 S2 搜索能力与执行前预测修订

日期：2026-10-15（America/Los_Angeles）；worktree `Simulation-v07scene`，分支 `v07-scene`。

**状态：已在快速检查 B 触发停止条件后停机。** 第 1–5 步实施与 S2 测试完成，最后一次 164/164 PASS；最终快速 A 为 32/60 规划可行，10 个意图×逼近方式组合均非零。快速 B 已保存 11 条通过审计的联合轨迹，4 个完整成功配对、2 个确定失败组合、4 个中止未完成组合。第 6/7 步与全量运行未启动，中止请求不计为任务失败。

停止直接原因是多向佯动 5 轮预算耗尽。另一已审计失败揭示了剩余缺口：佯攻计划作业点深度约 0.50，但完整规划路径最大深入比例约 0.881，候选预检尚未覆盖原角色判据中的整航线最大深度。叠加预检在小试新增拒绝 2 个组合；11 条已审计轨迹的最小间距预测最大绝对误差为 0.066845 m。详细证据、未执行项与 11 张图件见下文。

## 范围与执行登记

基线生成器提交 `f3498bb`；上一轮离线诊断原为未提交文件，本轮先保存为 `b794772`。此前复制的图件汇总目录保持原样。

本轮遵循用户最新第 1–7 步指令。角色成败判据、监视圈数/原半径范围、监视时长（只测量）、作业参数区间、首次进入目标预警区前 100 m 航向口径、公共分股与方位差、规划 10 m、实测 <2 m 生成错误、编队宽度规则不变。第 3 步集结点规则及距离区间是用户明确指定的变更。使用原分布抽样与拒绝，不采用未经等价性证明的条件抽样。

依序执行：失败记录 → 监视局部搜索 → 集结点 → 独立任务组池/组合 → 单机叠加预检 → 快速检查 A 停止判定 → 快速检查 B 停止判定 → 参数诊断 → 22 条固定回归/全部测试/冻结/全量 G-H-I。第 2、3、4、5 步分别做全 60 骨架纯规划检查；第 5 步后任一意图×逼近方式规划为零即停止。小试任一组合无完整配对即停止。固定模板回放仅第 7 步运行一次。每步 S2 单元测试、独立本地提交，不推送。

## 基线

- PowerShell 7.6.5；项目 `.conda-env` 为 `llm`。
- 修订前：`attempt_s2x_final_20261014T164338Z_4f85aaa3`，31/60 完整成功配对。
- 上一轮：`attempt_s2x_final_20261015T053115Z_a3b834e8`，16/60 完整成功配对；规划可行 19/60。
- 本轮规划可行数与历史实测成功数分开标注，不能视为同一阶段的因果比较。

## 第 1 步：失败记录

局部提案失败、搜索预算耗尽、有几何证据的不可行分别记录。几何证据限于被检查的具体提案；环线记录目标环带、世界边界、具体限制区/禁入区域及线段/距离见证，不将一次拒绝写成整张地图无解。逐组记录实际几何抽样次数与几何构造墙钟耗时（不含整 episode 组装）。耗时只进入诊断，不进入模板、标签或模型输入。

基线 S2 单元测试 151/151 PASS（17.184 s）。第 1 步测试：153 项通过；新增测试确认局部提案失败不能声称几何无解、证据作用域及预算耗尽分类。22 条固定回归未运行，依约留到第 7 步。

## 第 2 步：监视局部搜索

每个合法半径恢复原优化器 4 次重启、192 个相位向量、每次最多 900 代的能力；按 150/450/900 代分层，仅在满足原两时序相位预筛后提前结束该次重启。记录实际评分次数、阶段及耗时。原默认优化器路径保留；连续候选启用分层路径。

原范围均匀抽取的半径保留，进入局部最多 8 次提案；合法进入路线保留，再试相位候选和整体作业旋转（每相位最多 4 次）；每机完成环线后局部搜索撤离（16 个方向、每方向最多 24 个距离），保留已构造成员路线。半径不裁剪，圈数/方向规则不变，角色判据不变。局部诊断的耗时不进入模板。该步仍使用旧集结区间及约束，待第 3 步单独改变。

S2 测试 154 项通过（首次 28.346 s），六个登记反例全部通过原两时序相位预筛；夹具已提取到仓库，测试不依赖外部轨迹目录。随后运行全 60 骨架规划冒烟，覆盖同向/多向。

## 第 2 步后快速检查 A

证据 `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s2_search_step2_planning_20261015T074205Z_7bf58cf9`；源提交 `c2a137fabac175fa967e6c03b516370aea5c27b9`，另保存所有规划源码 SHA256。
纯规划可行 28/60；墙钟 860.279 s；仿真 0。历史列为实测完整成功配对，本轮列为规划可行。

| 意图 | 逼近方式 | 修订前实测 | 上一轮实测 | 本轮规划 |
|---|---|---:|---:|---:|
| 过境 | same_direction | 3/5 | 3/5 | 3/5 |
| 过境 | multi_direction | 5/7 | 1/7 | 1/7 |
| 侦察 | same_direction | 2/5 | 2/5 | 3/5 |
| 侦察 | multi_direction | 2/7 | 3/7 | 3/7 |
| 游弋监视 | same_direction | 0/5 | 0/5 | 4/5 |
| 游弋监视 | multi_direction | 3/7 | 0/7 | 4/7 |
| 佯动 | same_direction | 4/5 | 1/5 | 2/5 |
| 佯动 | multi_direction | 4/7 | 3/7 | 3/7 |
| 突防 | same_direction | 3/5 | 1/5 | 2/5 |
| 突防 | multi_direction | 5/7 | 2/7 | 3/7 |

第 5 步停止条件触发：False。


## 第 3 步：集结点

新扩展骨架集结距离从目标预警区外缘按 U(50,250) m 抽样，不叠加编队半宽到该随机参数上。集结点允许位于其他设施预警区内，仍不得进入任何警戒/禁飞区并满足限制区净空。进入前参考走廊仅将目标预警区视为禁入区域，全部警戒区仍受策略约束。旧默认参数路径保留。

短距离集结点放在最终直线上；在其外侧保留独立对齐点，使进入目标预警区前至少 100 m 可观测航向不被转弯污染。对齐点不是重新抽取或截断后的集结点，原编队半宽和净空公式保持不变。过境亦保留原宽度相关对齐航段，另记录真实抽取的集结点。新增两设施重叠预警区/警戒区反例，以及 50 m 集结距离的精确位置和最后 100 m 航向测试。

逐组 `geometry_wall_s` 已显式加入进程比较的墙钟元数据列表；几何、随机序列及轨迹差异仍按内容比较。

第 3 步 S2 单元测试 156/156 PASS，23.792 s；固定模板回放尚未运行。

## 第 3 步后快速检查 A

证据 `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s2_search_step3_planning_20261015T080240Z_5a408589`；源提交 `7fb1ba07208a734e6beccd7b88d2dc3e12cad113`，另保存所有规划源码 SHA256。
纯规划可行 27/60；墙钟 968.224 s；仿真 0。历史列为实测完整成功配对，本轮列为规划可行。

| 意图 | 逼近方式 | 修订前实测 | 上一轮实测 | 本轮规划 |
|---|---|---:|---:|---:|
| 过境 | same_direction | 3/5 | 3/5 | 3/5 |
| 过境 | multi_direction | 5/7 | 1/7 | 1/7 |
| 侦察 | same_direction | 2/5 | 2/5 | 3/5 |
| 侦察 | multi_direction | 2/7 | 3/7 | 3/7 |
| 游弋监视 | same_direction | 0/5 | 0/5 | 3/5 |
| 游弋监视 | multi_direction | 3/7 | 0/7 | 4/7 |
| 佯动 | same_direction | 4/5 | 1/5 | 2/5 |
| 佯动 | multi_direction | 4/7 | 3/7 | 3/7 |
| 突防 | same_direction | 3/5 | 1/5 | 2/5 |
| 突防 | multi_direction | 5/7 | 2/7 | 3/7 |

第 5 步停止条件触发：False。

## 第 4 步：独立任务组候选池与组合搜索

每个任务组独立完成 200 次私有几何提案，保留全部通过组内几何和语义预检的候选；一个组为空也不提前截断其他组。按组 ID 建池，各池笛卡尔积中以登记的私有种子无放回随机检查最多 1,000 个组合。组合依次检查同目标作业方位差 ≥60°、两时序整 episode 名义 10 m 间距，以及原有同向逐组 115% 路程上限；逐组最短路程仍取整 episode 名义可行池中的最小值，没有改成总路程上限或放松比例。

候选记录区分组提案和 episode 组合，逐组登记 200 次实际尝试、合法候选数、总耗时、几何耗时、相位评分次数与相位耗时；组合记录独立预算、笛卡尔积规模、实际检查数、随机种子、耗时与拒绝原因。组候选、组合和最终随机选择分别留存索引。组预算保持固定 200，没有按机器速度自适应随机预算。

S2 单元测试 158/158 PASS（24.102 s）。新增测试覆盖第一组为空仍完成所有组预算、组合无重复且固定种子可重现；原逐组 115% 判据测试保留。22 条固定回归仍未运行。

## 第 4 步后快速检查 A

证据 `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s2_search_step4_planning_20261015T082113Z_be8a7770`；源提交 `af368d8787c1abdfc83478a827532d336ed086e5`，另保存所有规划源码 SHA256。
纯规划可行 32/60；墙钟 1214.436 s；仿真 0。历史列为实测完整成功配对，本轮列为规划可行。

| 意图 | 逼近方式 | 修订前实测 | 上一轮实测 | 本轮规划 |
|---|---|---:|---:|---:|
| 过境 | same_direction | 3/5 | 3/5 | 3/5 |
| 过境 | multi_direction | 5/7 | 1/7 | 1/7 |
| 侦察 | same_direction | 2/5 | 2/5 | 3/5 |
| 侦察 | multi_direction | 2/7 | 3/7 | 4/7 |
| 游弋监视 | same_direction | 0/5 | 0/5 | 4/5 |
| 游弋监视 | multi_direction | 3/7 | 0/7 | 5/7 |
| 佯动 | same_direction | 4/5 | 1/5 | 2/5 |
| 佯动 | multi_direction | 4/7 | 3/7 | 4/7 |
| 突防 | same_direction | 3/5 | 1/5 | 2/5 |
| 突防 | multi_direction | 5/7 | 2/7 | 4/7 |

第 5 步停止条件触发：False。

## 第 5 步：保存单机轨迹的整航线叠加预检

单机测时后重新读取每机保存的 10 Hz NPZ，核对物理 ID、完整 0.1 s 时间格和坐标形状。仅加入真实出发延迟，不重复增加已经包含在单机轨迹中的 20 s 等待。公共时间轴从零到最晚平移后的单机结束时刻；出发前和完成后继续保持该机首/末位置，因此覆盖全部组、进入、作业、撤离及等待段。同步和递次任一版本最小间距 <10 m 就拒绝该组合，进入下一个组合，单机测时最多 5 轮。

原名义预筛、实际延迟恒速预筛、联合仿真及最终 <2 m 质量检查保留。叠加拒绝附具体模式、机对、时刻、距离及 10 m 约束；该见证仅针对该候选的叠加预测，不声称地图整体无解。预算耗尽单独记录。每个实际执行版本记录预测与实测最小间距之差、位置误差和 10 m 分类是否一致；新诊断文件也加入后续 1/2 进程内容比较。

S2 单元测试 164/164 PASS（19.152 s），覆盖真实延迟平移、出发前/完成后保持、物理 ID 对齐、轨迹时间格校验、叠加拒绝后的五轮上限和快速 B 的固定选样规则。22 条固定模板回放尚未运行。

### 已存 0.689 m 样本的提前拦截验证

证据 `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s2_search_overlay_witness_20261015T084451Z_ffc26da3`；新仿真 0。8412/ext_001 递次版本原预筛通过，新叠加预测 0.689434415 m，存档实测 0.689364238 m，预测误差 +0.000070177 m；10 m 预检将整对提前拒绝。源轨迹与时间计划哈希验证未变。

## 第 5 步后快速检查 A

证据 `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s2_search_step5_planning_20261015T084510Z_f58b31c5`；源提交 `d2befc1c067a6ba36a86a9ed6523da9f6bf8c84e`，另保存所有规划源码 SHA256。
纯规划可行 32/60；墙钟 1242.805 s；仿真 0。历史列为实测完整成功配对，本轮列为规划可行。

| 意图 | 逼近方式 | 修订前实测 | 上一轮实测 | 本轮规划 |
|---|---|---:|---:|---:|
| 过境 | same_direction | 3/5 | 3/5 | 3/5 |
| 过境 | multi_direction | 5/7 | 1/7 | 1/7 |
| 侦察 | same_direction | 2/5 | 2/5 | 3/5 |
| 侦察 | multi_direction | 2/7 | 3/7 | 4/7 |
| 游弋监视 | same_direction | 0/5 | 0/5 | 4/5 |
| 游弋监视 | multi_direction | 3/7 | 0/7 | 5/7 |
| 佯动 | same_direction | 4/5 | 1/5 | 2/5 |
| 佯动 | multi_direction | 4/7 | 3/7 | 4/7 |
| 突防 | same_direction | 3/5 | 1/5 | 2/5 |
| 突防 | multi_direction | 5/7 | 2/7 | 4/7 |

第 5 步停止条件触发：False。

第 4/5 步的 32 份选中规划骨架 SHA256 逐一相同；第 5 步新增预检未改变纯规划结果。

## 快速检查 B：停止报告

证据 `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s2_search_quick_b_20261015T090658Z_5ac915b5`；停止收据 `FAST_B_STOP.json`。
多向佯动 4d13/ext_008 在第 5 轮后没有完整成功配对，触发用户指定的快速 B 停止条件。仅终止已核实的本批主进程及其 8 个子进程，在途请求按中止记录；没有继续第 6/7 步。

登记 10 个组合、20 个请求；完成审计的联合轨迹 11 条；完整成功配对 4 个，确定失败组合 2 个，中止未完成组合 4 个。中止项不计任务失败；本次部分结果不能当作全 20 请求的无删失成功率。

| 意图 | 方式 | 骨架 | 组数 | 结果 | 已完成/已启动测时轮数 | 叠加新增拒绝组合 |
|---|---|---|---:|---|---:|---:|
| 过境 | same_direction | family_s12_5024cb2ccea653ae_ext_000_regular | 2 | 完整成功配对 | 1/1 | 0 |
| 过境 | multi_direction | family_s12_f2adfbfae12fbbad_ext_000_regular | 1 | 完整成功配对 | 2/2 | 0 |
| 侦察 | same_direction | family_s12_4d13d93f9171c446_ext_001_regular | 1 | 完整成功配对 | 3/3 | 1 |
| 侦察 | multi_direction | family_s12_4d13d93f9171c446_ext_006_regular | 2 | 中止未完成 | 2/3 | 0 |
| 游弋监视 | same_direction | family_s12_5024cb2ccea653ae_ext_002_regular | 2 | 中止未完成 | 0/1 | 0 |
| 游弋监视 | multi_direction | family_s12_4d13d93f9171c446_ext_007_regular | 2 | 中止未完成 | 1/2 | 0 |
| 佯动 | same_direction | family_s12_4d13d93f9171c446_ext_003_regular | 1 | 完整成功配对 | 1/1 | 0 |
| 佯动 | multi_direction | family_s12_4d13d93f9171c446_ext_008_regular | 2 | 确定失败 | 5/5 | 0 |
| 突防 | same_direction | family_s12_4d13d93f9171c446_ext_004_regular | 2 | 中止未完成 | 2/2 | 1 |
| 突防 | multi_direction | family_s12_4d13d93f9171c446_ext_009_regular | 3 | 确定失败 | 3/3 | 0 |

### 触发停止与其他已确认失败

多向佯动：前 4 轮为实际延迟恒速间距预筛拒绝；第 5 轮单机核心事件/完成停留未观测。最终性质是 5 轮搜索预算耗尽，没有整体几何无解证明。
多向突防 4d13/ext_009 的两版已完成且任务失败：佯攻组 task_group_02 的 uav_01/uav_05 实测最大深入比例均为 0.881，违反原范围 \(0.3\leq d\leq0.7\)。标签与独立审计一致，保持失败结论。

- family_s12_4d13d93f9171c446_ext_009_regular / uav_01：计划作业点深入比例 0.495712，保存的完整规划折线按不超过 1 m 步长取样，最大深入比例约 0.880949。
- family_s12_4d13d93f9171c446_ext_009_regular / uav_05：计划作业点深入比例 0.508911，保存的完整规划折线按不超过 1 m 步长取样，最大深入比例约 0.880949。

上述对照只读取已有折线，没有新增仿真；说明检查计划作业点深度不能替代检查完整航线的最大深入程度。本轮不修改角色判据或作业参数。

### 叠加预检与实测误差

本次小试完成 20 轮单机测时，新增拦截 2 个原预筛已通过的组合。被拦截组合没有联合实测，不能据此统计误报率。
在 11 条已审计联合轨迹上，最小间距预测绝对误差：均值 0.009841 m，最大 0.066845 m；最大逐机位置误差 0.763671 m；10 m 分类一致 11/11。

| 骨架/时序 | 预测最小间距/m | 实测最小间距/m | 预测减实测/m |
|---|---:|---:|---:|
| family_s12_5024cb2ccea653ae_ext_000_regular/synchronous | 11.135036 | 11.135053 | -0.000017 |
| family_s12_5024cb2ccea653ae_ext_000_regular/sequential | 11.135044 | 11.135044 | -0.000000 |
| family_s12_f2adfbfae12fbbad_ext_000_regular/synchronous | 21.105821 | 21.105708 | +0.000113 |
| family_s12_f2adfbfae12fbbad_ext_000_regular/sequential | 17.864776 | 17.865722 | -0.000946 |
| family_s12_4d13d93f9171c446_ext_001_regular/synchronous | 22.742156 | 22.713635 | +0.028521 |
| family_s12_4d13d93f9171c446_ext_001_regular/sequential | 19.103084 | 19.101729 | +0.001354 |
| family_s12_4d13d93f9171c446_ext_003_regular/synchronous | 21.708419 | 21.708162 | +0.000258 |
| family_s12_4d13d93f9171c446_ext_003_regular/sequential | 21.228795 | 21.228834 | -0.000039 |
| family_s12_4d13d93f9171c446_ext_004_regular/synchronous | 13.782713 | 13.789399 | -0.006686 |
| family_s12_4d13d93f9171c446_ext_009_regular/synchronous | 17.776523 | 17.779997 | -0.003474 |
| family_s12_4d13d93f9171c446_ext_009_regular/sequential | 22.780480 | 22.713635 | +0.066845 |

### 全量统计的三轮对照

本轮全量未启动；小试和规划结果不填入全量分母。

| 项目 | 修订前 | 上一轮 | 本轮全量 |
|---|---:|---:|---|
| 常规骨架 | 60 | 60 | 未运行 |
| 常规请求 | 120 | 120 | 未运行 |
| 生成常规轨迹 | 68 | 34 | 未运行 |
| 质量与审计通过的常规轨迹 | 64 | 33 | 未运行 |
| 完整成功配对 | 31 | 16 | 未运行 |
| 保留轨迹中的任务失败 | 0 | 0 | 未运行 |
| 生成质量错误 | 4 | 1 | 未运行 |
| 规划拒绝请求 | 52 | 86 | 未运行 |
| 中止请求 | 6 | 6 | 未运行 |

### 未执行项与边界

- 第 6 步三阶段参数分布统计未执行；提出候选和可选候选的原始取值已在候选池中留存，但尚无本轮全量最终保留骨架。
- 第 7 步 22 条固定模板回放、全部测试、冻结后全量 120+6 请求、960 项交叉否定与 1/2 进程比较均未执行。
- 任务 I 后的时长捷径检查及每类召回率、平衡准确率未执行。监视时长、圈数、半径范围及角色参数保持原要求。
- 本轮各实施步骤的 S2 测试均通过，最后一次为 164/164。已完成审计的输出未发现 P0；未完成的请求不据此宣称审计通过。
- 外层兼容状态仍有 geometry_infeasible / planning_spacing_rejection 等名称；本轮三类原因以 search_rejection、group_terminations 和 calibration_termination 的作用域及见证为准。

## 快速检查 A 的组合耗时明细

各单元格为“可行/登记；累计工作进程秒”。累计耗时包含成功与失败骨架，不能当作并行墙钟时间。

| 意图 | 逼近方式 | 第 2 步 | 第 3 步 | 第 4 步 | 第 5 步 |
|---|---|---:|---:|---:|---:|
| 过境 | same_direction | 3/5；65.85 s | 3/5；73.46 s | 3/5；154.65 s | 3/5；157.48 s |
| 过境 | multi_direction | 1/7；123.33 s | 1/7；164.52 s | 1/7；217.73 s | 1/7；220.01 s |
| 侦察 | same_direction | 3/5；196.56 s | 3/5；215.02 s | 3/5；298.85 s | 3/5；303.15 s |
| 侦察 | multi_direction | 3/7；650.39 s | 3/7；683.99 s | 4/7；732.22 s | 4/7；729.03 s |
| 游弋监视 | same_direction | 4/5；2195.63 s | 3/5；2072.57 s | 4/5；2516.85 s | 4/5；2557.43 s |
| 游弋监视 | multi_direction | 4/7；983.34 s | 4/7；1499.61 s | 5/7；1552.24 s | 5/7；1621.18 s |
| 佯动 | same_direction | 2/5；166.85 s | 2/5；196.79 s | 2/5；250.06 s | 2/5；254.69 s |
| 佯动 | multi_direction | 3/7；120.61 s | 3/7；203.90 s | 4/7；234.02 s | 4/7；238.38 s |
| 突防 | same_direction | 2/5；135.98 s | 2/5；151.48 s | 2/5；244.10 s | 2/5；246.07 s |
| 突防 | multi_direction | 3/7；152.79 s | 3/7；233.06 s | 4/7；361.82 s | 4/7；362.60 s |

## 本轮图件

规划图仅表示规划可行；实测图使用导出的 10 Hz 轨迹，图题保留实际成功/失败结果。

![planning_coverage.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v07scene/Multi-UAV SimpleGC/docs/v07/S2_search_revision_assets/planning_coverage.png>)

![planning_wall_time.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v07scene/Multi-UAV SimpleGC/docs/v07/S2_search_revision_assets/planning_wall_time.png>)

![solo_overlay_prediction.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v07scene/Multi-UAV SimpleGC/docs/v07/S2_search_revision_assets/solo_overlay_prediction.png>)

![quick_b_reconnaissance_same_direction.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v07scene/Multi-UAV SimpleGC/docs/v07/S2_search_revision_assets/quick_b_reconnaissance_same_direction.png>)

![quick_b_feint_same_direction.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v07scene/Multi-UAV SimpleGC/docs/v07/S2_search_revision_assets/quick_b_feint_same_direction.png>)

![quick_b_penetration_same_direction.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v07scene/Multi-UAV SimpleGC/docs/v07/S2_search_revision_assets/quick_b_penetration_same_direction.png>)

![quick_b_penetration_multi_direction.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v07scene/Multi-UAV SimpleGC/docs/v07/S2_search_revision_assets/quick_b_penetration_multi_direction.png>)

![quick_b_transit_same_direction.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v07scene/Multi-UAV SimpleGC/docs/v07/S2_search_revision_assets/quick_b_transit_same_direction.png>)

![quick_b_transit_multi_direction.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v07scene/Multi-UAV SimpleGC/docs/v07/S2_search_revision_assets/quick_b_transit_multi_direction.png>)

![quick_b_timing_1.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v07scene/Multi-UAV SimpleGC/docs/v07/S2_search_revision_assets/quick_b_timing_1.png>)

![quick_b_timing_2.png](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v07scene/Multi-UAV SimpleGC/docs/v07/S2_search_revision_assets/quick_b_timing_2.png>)
