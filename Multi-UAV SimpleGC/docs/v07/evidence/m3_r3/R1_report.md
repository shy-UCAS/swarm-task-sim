# M3-r3：R0 修订通过、R1 回归失败停止

## 当前阶段

| 阶段 | 门禁 | 实际执行情况 |
|---|---|---|
| R0 | PASS / R0_REVALIDATED_PASS | 完整重新核验 282 项身份、历史输入哈希、原始配对及汇总；按授权采用 N/A |
| R1 | FAIL | 完整登记回归 209 项：205 通过、2 失败、2 报错；七探针的 14 次重放未启动 |
| R2 | BLOCKED | R1_NOT_PASS，未执行历史 SITL 对照的候选 fastsim 运行 |
| R3 | BLOCKED | R1_NOT_PASS，未合并 P2、未创建候选冻结记录 |
| R4 | BLOCKED | R1_NOT_PASS，未执行固定 38 骨架试点 |

R0 修订提交：`81c4bf27010cca3dc1792149b06b77b94eae51dc`。R1 运行登记的 code_commit 是这个父提交，未提交实现的精确内容由外部 `registration.json.source_sha256` 绑定；收尾提交用于保存同一实现及失败证据，不代表验收通过。

## R0 适用性和完整性

原 56 条矩形螺旋任务全部保留在 282 项全集中。原始任务与 SITL/r2 身份匹配，原配对指标和冻结汇总精确再现。原 8196 项文件重新核验，补齐后续输入后共绑定 8608 项文件。原 R0 BLOCKED 报告、门禁、计划、日志保持原样。

| 模式 | 全部任务 | truth 可评价 / 状态 | observation 可评价 / 状态 |
|---|---:|---|---|
| equal_strip_lawnmower | 42 | 42 / PASS，42/42 | 42 / PASS，42/42 |
| equal_strip_rectangular_spiral | 56 | 0 / N/A，比例 null | 0 / N/A，比例 null |
| line_abreast | 94 | 94 / PASS，94/94 | 94 / PASS，94/94 |
| staggered_same_loop | 90 | 90 / PASS，90/90 | 90 / PASS，90/90 |

成功和观测成功仍为 282/282；总体运动一致率按原参考可评价分母为 226/226。N/A 不等于任务成功，不填零或百分之百。新增 N/A 修订测试 6 项、原核验器测试 4 项，共 10/10 通过。

固定验收计划：`R0_validation_plan_amended.json`。
SHA256：`50deb2ed20694508b9ecbe15fe234d56247f20db1bb6e35a1bd032746833a8e6`。
登记了 D0b 七探针、R2 历史 70 项功能子集及 282 全集、R4 30+8 去重后 38 骨架。R2 28800 秒、R4 21600 秒预算及全部数值误差非退化门槛保持原样。

## R1 实现与验证范围

在独立候选分支新增 `continuous_route_v3` 策略和 `m3_r3_candidate_v1.json`。普通转角沿用 D0b B2 的固定切距公式；其余 Bezier、曲率/jerk/响应时域限速、175° 显式停车、物理积分和航点见证算法不变。默认 ReferenceConfig 和 task_v07.execute 仍选 r2；候选调用需显式指定 r3。产物写入、读取校验及诊断记录实际参考版本，防止将 r3 冒充 r2。

候选配置 SHA256：`0fe3efff6f97ed88c665374d0280aef571b92399ac3711184f13e5c6a3de3b30`。
r2 冻结配置 SHA256：`94822513045c434dc2f713070728f1f99d18bcbea3933f8f092b85c5e4d78193`，未改。

新增 9 项 R1 测试通过：默认/显式 r2 几何一致、配置仅改策略、未知版本拒绝、D0b B2 数值一致、曲线顶点公式、相邻曲线/短航段顺序、两段驻留版本传递、真实驻留保持、产物身份回读及混合版本拒绝。

首轮预检发现新增版本元数据变量 `policy` 与质量策略变量重名，修正为 `reference_policy` 后，重新运行全部 209 项登记回归。首轮日志保留，不以其中通过结果替代本轮验证。正式 R1 完整回归耗时约 71.08 秒，源码/测试/配置哈希在运行中不变。

**未验证项**：由于完整回归 FAIL，七探针 r2/r3 相对历史 A/B2 的 14 次逐位轨迹重放均未启动，也未启动 R2 校准。因此不能声称 r2 历史轨迹已逐位验证、r3 七探针已复现，或 r3 已满足全部校准/数据质量门槛。

## 四项剩余失败及基线归因

均位于 `tests/test_v07_s2_revision_continuous.py`：

1. `test_115_percent_filter_then_seeded_order`：预期排除 115.1 成本候选，当前实现仍保留。
2. `test_each_group_has_its_own_115_percent_bound`：预期索引 `[2]`，实际 `[3, 2]`。
3. `test_five_calibration_round_limit_and_zero_flights_for_empty_pool`：旧测试 patch 的 `scripts.run_v07_s2_episode_batch.calibrate_episode` 属性已不存在。
4. `test_variable_observation_dwell_preserves_eighty_percent_criterion`：旧测试读取的 `conditions.minimum_dwell` 字段不存在。

在固定 FE 集成工作树、提交 `81f804a969192790d89100528e3f802bc06446b1`，只读运行该模块，12 项中同样 2 FAIL + 2 ERROR。使用 PYTHONSAFEPATH/PYTHONPATH 显式加载基线模块，工作命令仍位于候选目录，使用 `python -B -m unittest -v`，未修改基线文件。关联旧测试、candidate_search、episode_batch、labels、criteria、conditions audit 的候选/基线文件 SHA256 相同。归因记录见 `R1/baseline_attribution.json`。

已登记门禁要求全部回归通过；不能因为失败在基线已有，就在看到结果后删测试、改断言、放宽门槛或宣布例外。因此 R1 FAIL 并停止。后续需单独审定这四项历史测试与现行合同的关系；本轮未更改这些测试、相关生产算法或 M1 判据。

## 证据路径

仓库内均在 `docs/v07/evidence/m3_r3/`：

- `R0_gate_amendment.md` / `.json`：修订授权与原证据哈希。
- `R0_revalidated_gate.json`、`R0_validation_plan_amended.json`：重验结果与固定计划。
- `R0_amendment_tests.txt`：10 项模块命令测试。
- `R1/gate.json` 与 `R1_gate.json`：程序化 FAIL 门禁；`pipeline_state.json` 已停止在 R1。
- `R1/baseline_attribution.json`、`R1/closing_verification.json`：失败归因和最终证据哈希。

外部原始证据：

- R0：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\fast_dynamics\m3\m3_r3_r0_revalidate01`。
- R1：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\fast_dynamics\m3\m3_r3_r1_attempt01`，含 registration、完整 unit_tests、初轮预检、基线归因日志及 summary。

没有启动新 SITL、没有运行任何 holdout、没有合并 P2 或稳定分支、没有正式冻结/标签/量产，也没有推送。当前候选仅供审阅，不建议正式冻结。
