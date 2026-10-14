# S2 第二段现有数据：抽样偏差与捷径审计

来源 attempt：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s2x_final_20261014T164338Z_4f85aaa3`；冻结生成提交：`e8fe856e51e8aa7b4b38697f811793e32fe22dd1`。
本报告只读取已有结果，没有修改规划器、判据、标签或随机流，没有重新仿真。A–C 及航线候选扩展未实施，因此没有修订后的结果；不得将本报告作为本轮完整修订的验收报告。

## 1. 分母与复核口径

骨架成功要求同步、递次两版均生成、任务成功、质量有效且独立审计通过。分母为全部 60 个登记常规骨架。
任务组规模按合并后组成员数分档：骨架含某档任务组就计入该档一次；含不同档任务组的骨架会跨档重复，三档不得相加作为总样本数。另提供以任务组为单位的补充表。
保留轨迹与捷径检查采用质量有效且独立审计通过的常规单条轨迹，排除中止、诊断、规划拒绝和生成错误。两个时序版本始终在同一个 family 留出折中。

## 2. 修订前骨架成功率矩阵

### 意图 × 逼近方式

| 意图 | 逼近方式 | 成功/登记 | 成功率 |
|---|---|---|---|
| 过境 | same_direction | 3/5 | 60.00% |
| 过境 | multi_direction | 5/7 | 71.43% |
| 侦察 | same_direction | 2/5 | 40.00% |
| 侦察 | multi_direction | 2/7 | 28.57% |
| 游弋监视 | same_direction | 0/5 | 0.00% |
| 游弋监视 | multi_direction | 3/7 | 42.86% |
| 佯动 | same_direction | 4/5 | 80.00% |
| 佯动 | multi_direction | 4/7 | 57.14% |
| 突防 | same_direction | 3/5 | 60.00% |
| 突防 | multi_direction | 5/7 | 71.43% |

### 意图 × 地图设施数

| 意图 | 地图设施数 | 成功/登记 | 成功率 |
|---|---|---|---|
| 过境 | 1 | 4/4 | 100.00% |
| 过境 | 2 | 2/4 | 50.00% |
| 过境 | 3 | 2/4 | 50.00% |
| 侦察 | 1 | 2/4 | 50.00% |
| 侦察 | 2 | 0/4 | 0.00% |
| 侦察 | 3 | 2/4 | 50.00% |
| 游弋监视 | 1 | 2/4 | 50.00% |
| 游弋监视 | 2 | 0/4 | 0.00% |
| 游弋监视 | 3 | 1/4 | 25.00% |
| 佯动 | 1 | 3/4 | 75.00% |
| 佯动 | 2 | 2/4 | 50.00% |
| 佯动 | 3 | 3/4 | 75.00% |
| 突防 | 1 | 3/4 | 75.00% |
| 突防 | 2 | 4/4 | 100.00% |
| 突防 | 3 | 1/4 | 25.00% |

### 意图 × 合并后任务组数

| 意图 | 合并后任务组数 | 成功/登记 | 成功率 |
|---|---|---|---|
| 过境 | 1 | 6/7 | 85.71% |
| 过境 | 2 | 2/4 | 50.00% |
| 过境 | 3 | 0/1 | 0.00% |
| 侦察 | 1 | 3/7 | 42.86% |
| 侦察 | 2 | 0/4 | 0.00% |
| 侦察 | 3 | 1/1 | 100.00% |
| 游弋监视 | 1 | 2/7 | 28.57% |
| 游弋监视 | 2 | 1/4 | 25.00% |
| 游弋监视 | 3 | 0/1 | 0.00% |
| 佯动 | 1 | 5/7 | 71.43% |
| 佯动 | 2 | 2/4 | 50.00% |
| 佯动 | 3 | 1/1 | 100.00% |
| 突防 | 1 | 3/3 | 100.00% |
| 突防 | 2 | 4/7 | 57.14% |
| 突防 | 3 | 1/2 | 50.00% |

### 意图 × 任务组规模

| 意图 | 任务组规模 | 成功/登记 | 成功率 |
|---|---|---|---|
| 过境 | 2–3 | 1/3 | 33.33% |
| 过境 | 4–6 | 1/4 | 25.00% |
| 过境 | 7以上 | 8/10 | 80.00% |
| 侦察 | 2–3 | 1/3 | 33.33% |
| 侦察 | 4–6 | 1/4 | 25.00% |
| 侦察 | 7以上 | 3/10 | 30.00% |
| 游弋监视 | 2–3 | 0/3 | 0.00% |
| 游弋监视 | 4–6 | 1/4 | 25.00% |
| 游弋监视 | 7以上 | 3/10 | 30.00% |
| 佯动 | 2–3 | 3/3 | 100.00% |
| 佯动 | 4–6 | 2/4 | 50.00% |
| 佯动 | 7以上 | 6/10 | 60.00% |
| 突防 | 2–3 | 4/6 | 66.67% |
| 突防 | 4–6 | 2/6 | 33.33% |
| 突防 | 7以上 | 6/7 | 85.71% |

任务组口径补充（成功仍要求所属整个骨架两版成功）：

| 意图 | 成员数 | 成功组/登记组 | 比例 |
|---|---|---|---|
| 过境 | 2–3 | 1/3 | 33.33% |
| 过境 | 4–6 | 1/5 | 20.00% |
| 过境 | 7以上 | 8/10 | 80.00% |
| 侦察 | 2–3 | 1/3 | 33.33% |
| 侦察 | 4–6 | 2/5 | 40.00% |
| 侦察 | 7以上 | 3/10 | 30.00% |
| 游弋监视 | 2–3 | 0/3 | 0.00% |
| 游弋监视 | 4–6 | 1/5 | 20.00% |
| 游弋监视 | 7以上 | 3/10 | 30.00% |
| 佯动 | 2–3 | 3/3 | 100.00% |
| 佯动 | 4–6 | 3/5 | 60.00% |
| 佯动 | 7以上 | 6/10 | 60.00% |
| 突防 | 2–3 | 6/8 | 75.00% |
| 突防 | 4–6 | 2/8 | 25.00% |
| 突防 | 7以上 | 6/7 | 85.71% |

## 3. 零成功组合与保存的拒绝证据

只列有登记骨架但成功数为 0 的组合；未抽中的组合标为“未登记”，不计零成功。以下是已保存原因的统计，不表示地图数学上无解。
最终类别按骨架计数；候选原因是解析已保存嵌套计数后的出现次数，不是独立骨架数，不用于跨角色比较拒绝概率。相同骨架可能出现在多个交叉表中。

- **游弋监视 × 逼近方式=same_direction**：0/5。最终类别 `{"geometry_infeasible": 5}`；保存的主要原因：`orbit_phase_approach_unavailable` × 1977；`same_direction_parallel_phase_entries_do_not_fit` × 1215；`closed_orbit_cannot_clear_exact_restrictions_and_alert_policy` × 360。
- **侦察 × 地图设施数=2**：0/4。最终类别 `{"geometry_infeasible": 4}`；保存的主要原因：`sector_area` × 576；`insufficient_strips` × 267；`offset_lane_swallowtail` × 93。
- **游弋监视 × 地图设施数=2**：0/4。最终类别 `{"geometry_infeasible": 4}`；保存的主要原因：`orbit_phase_approach_unavailable` × 1977；`same_direction_parallel_phase_entries_do_not_fit` × 879；`closed_orbit_cannot_clear_exact_restrictions_and_alert_policy` × 240。
- **过境 × 合并后任务组数=3**：0/1。最终类别 `{"geometry_infeasible": 1}`；保存的主要原因：`no_valid_parallel_chord_block` × 216。
- **侦察 × 合并后任务组数=2**：0/4。最终类别 `{"kinematic_infeasible": 1, "geometry_infeasible": 3}`；保存的主要原因：`sector_area` × 720；`form_up_leg_blocked` × 50；`reference_leg_invalid` × 16。
- **游弋监视 × 合并后任务组数=3**：0/1。最终类别 `{"geometry_infeasible": 1}`；保存的主要原因：`same_direction_parallel_phase_entries_do_not_fit` × 288；`closed_orbit_cannot_clear_exact_restrictions_and_alert_policy` × 72。
- **游弋监视 × 任务组规模=2–3**：0/3。最终类别 `{"geometry_infeasible": 3}`；保存的主要原因：`same_direction_parallel_phase_entries_do_not_fit` × 384；`closed_orbit_cannot_clear_exact_restrictions_and_alert_policy` × 192；`whole episode actual-delay constant-speed estimate below 6m` × 1。

逐骨架记录、每次拒绝原文、来源路径和 SHA256 见 [diagnostics.json](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/audit_s2_sampling_bias_20261014_ec86137_verified/diagnostics.json>)。

## 4. 保留轨迹中的意图与逼近方式

| 意图 | 同向条数/该意图总数 | 同向比例 | 多向条数/该意图总数 | 多向比例 |
|---|---|---|---|---|
| 过境 | 6/16 | 37.50% | 10/16 | 62.50% |
| 侦察 | 4/8 | 50.00% | 4/8 | 50.00% |
| 游弋监视 | 0/6 | 0.00% | 6/6 | 100.00% |
| 佯动 | 8/17 | 47.06% | 9/17 | 52.94% |
| 突防 | 6/17 | 35.29% | 11/17 | 64.71% |

同一意图两种方式的骨架成功率差（绝对百分点）：

| 意图 | 同向成功率 | 多向成功率 | 绝对差（百分点） |
|---|---|---|---|
| 过境 | 60.00% | 71.43% | 11.43 |
| 侦察 | 40.00% | 28.57% | 11.43 |
| 游弋监视 | 0.00% | 42.86% | 42.86 |
| 佯动 | 80.00% | 57.14% | 22.86 |
| 突防 | 60.00% | 71.43% | 11.43 |

侦察包含两种方法，不能用合并后的侦察比例掩盖方法内部缺口。下表按含该角色的骨架去重，成功要求整个骨架成功：

| 角色/方法 | 逼近方式 | 成功/登记骨架 |
|---|---|---|
| area_search | same_direction | 1/3 |
| area_search | multi_direction | 2/6 |
| close_observation | same_direction | 2/3 |
| close_observation | multi_direction | 0/3 |
| feint | same_direction | 6/7 |
| feint | multi_direction | 6/11 |
| intrusion | same_direction | 3/5 |
| intrusion | multi_direction | 5/7 |
| monitoring | same_direction | 0/6 |
| monitoring | multi_direction | 4/8 |
| transit | same_direction | 3/5 |
| transit | multi_direction | 5/7 |

方法级零成功组合的保存原因（计数口径同第 3 节）：

- `close_observation × multi_direction`：`sector_area` × 360；`offset_lane_swallowtail` × 46；`all-warning-exterior_collection_unavailable` × 13
- `monitoring × same_direction`：`orbit_phase_approach_unavailable` × 1977；`same_direction_parallel_phase_entries_do_not_fit` × 1249；`closed_orbit_cannot_clear_exact_restrictions_and_alert_policy` × 411

## 5. 按 family 留出的快速捷径检查

固定浅层决策树：`max_depth=2, min_samples_leaf=3, random_state=0`；不调参、不看测试折拟合。每次留出一个完整 family，共 6 折。两项分别单独训练。
时长指模拟时间轴 `duration_s`，不使用受机器负载影响的墙钟时间。组合特征仅为逼近方式、合并后任务组数与地图设施数。准确率按全部留出预测汇总；同时报告宏平均召回率和按 family 平均准确率。
样本量 64，类别计数 `{"transit": 16, "reconnaissance": 8, "feint": 17, "penetration": 17, "monitoring": 6}`。五类均匀随机参考为 20%，类别不均衡时它不是最强的无特征基线；因此额外报告仅用训练折多数类的基线。

| 特征 | 留出准确率 | 宏平均召回率 | family 平均准确率 | 训练折多数类基线 | 五类随机参考 |
|---|---|---|---|---|---|
| duration_only | 17.19% | 17.48% | 16.28% | 20.31% | 20.00% |
| approach_group_facility_only | 31.25% | 24.12% | 31.31% | 20.31% | 20.00% |

### duration_only：逐折

| 留出 family | 训练数 | 测试数 | 准确率 | 多数类基线 |
|---|---|---|---|---|
| family_s12_4d13d93f9171c446 | 54 | 10 | 20.00% | 20.00% |
| family_s12_5024cb2ccea653ae | 56 | 8 | 12.50% | 25.00% |
| family_s12_8412c1cdb40e54b1 | 56 | 8 | 0.00% | 25.00% |
| family_s12_8e012bf033eb6821 | 56 | 8 | 25.00% | 0.00% |
| family_s12_aa4c66be8e85d64d | 50 | 14 | 21.43% | 28.57% |
| family_s12_f2adfbfae12fbbad | 48 | 16 | 18.75% | 18.75% |

混淆矩阵：行是真实类别，列是预测类别。

| 真实\预测 | 过境 | 侦察 | 游弋监视 | 佯动 | 突防 |
|---|---|---|---|---|---|
| 过境 | 3 | 1 | 0 | 10 | 2 |
| 侦察 | 2 | 0 | 2 | 4 | 0 |
| 游弋监视 | 0 | 0 | 2 | 0 | 4 |
| 佯动 | 6 | 2 | 0 | 5 | 4 |
| 突防 | 5 | 1 | 2 | 8 | 1 |

### approach_group_facility_only：逐折

| 留出 family | 训练数 | 测试数 | 准确率 | 多数类基线 |
|---|---|---|---|---|
| family_s12_4d13d93f9171c446 | 54 | 10 | 20.00% | 20.00% |
| family_s12_5024cb2ccea653ae | 56 | 8 | 50.00% | 25.00% |
| family_s12_8412c1cdb40e54b1 | 56 | 8 | 50.00% | 25.00% |
| family_s12_8e012bf033eb6821 | 56 | 8 | 0.00% | 0.00% |
| family_s12_aa4c66be8e85d64d | 50 | 14 | 42.86% | 28.57% |
| family_s12_f2adfbfae12fbbad | 48 | 16 | 25.00% | 18.75% |

混淆矩阵：行是真实类别，列是预测类别。

| 真实\预测 | 过境 | 侦察 | 游弋监视 | 佯动 | 突防 |
|---|---|---|---|---|---|
| 过境 | 8 | 0 | 0 | 4 | 4 |
| 侦察 | 2 | 0 | 0 | 4 | 2 |
| 游弋监视 | 2 | 0 | 0 | 2 | 2 |
| 佯动 | 8 | 0 | 0 | 3 | 6 |
| 突防 | 4 | 0 | 0 | 4 | 9 |

以上只作诊断，不设通过门槛。六个 family 的结果不能证明更广泛地图分布上的泛化能力；单一特征具有预测力也不等于已证明因果捷径。
运行环境提示：现有 SciPy 声明支持 NumPy <2.3，而项目环境为 NumPy 2.5.3，导入时产生兼容性警告。本次未更改项目依赖；树模型完成全部拟合和预测，并逐折用独立节点遍历核对预测一致。该检查不能替代依赖兼容性认证。

## 6. 主对照与交叉否定基线

| 项目 | 修订前 | 修订后 |
|---|---|---|
| 主对照视图条数 | 10 | 未运行 |
| 交叉否定实际执行项 | 232 | 未运行 |
| 交叉否定 not_run | 728 | 未运行 |

本次仅新增离线审计脚本、报告和统计证据。未修改共享规划代码或 `labels.measure`，未重跑固定回归、全量请求或交叉否定，未更新任何既有基准。

复核完成：三个互斥矩阵各自合计 60 个登记骨架、31 个成功骨架；两项分类器各有 64 个唯一的留出预测，6 折测试数合计 64，准确率由预测清单独立重算一致。全部报告证据链接存在；原始来源文件 SHA256 与审计前一致。

[来源文件哈希与验证记录](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/audit_s2_sampling_bias_20261014_ec86137_verified/provenance.json>)。
