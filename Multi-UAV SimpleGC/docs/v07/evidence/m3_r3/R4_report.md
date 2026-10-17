# R4 固定试点报告（G-4 / G-5a）

状态：**PASS**。原 30/30、新增 P2 8/8 均严格配对，76/76 episode 完成并保留，未完成为 0。
总墙钟 4459.890 s（上限 21600 s），8 workers。未启动 SITL、未读取封存 holdout。

## 门禁与测试

- 492 项执行：474 PASS，18 BASELINE_KNOWN_FAILURE，0 新增回归，0 签名变化；额外 harness 测试 39/39 PASS。
- 历史 r2 原 30 个骨架基线干跑通过；新增 8 个无历史完整 r2 episode，按 G-4 单列测量。
- 76 条独立标签/几何审计通过，无原判据禁入区违规，无 P0ContractError。最小机间距 2.044225225697 m：`family_s15_c713f51898e81011_ext_000_regular_synchronous`（阈值 2 m）。
- 运行源码/配置指纹不变，锁定输入最终复核通过，r2 配置未修改。

## 原集合完整 r2/r3 对照

两组均为 480 个 member-episode（含同步/递次）。沿用原 QC，低速阈值 1 m/s，无最短事件时长。

| 指标 | r2 | r3 |
|---|---:|---:|
| 低速事件 | 11586 | 900 |
| 低速事件/km（总事件/总里程） | 3.718714 | 0.286874 |
| 运动窗低速时间占比 | 8.5745% | 7.1601% |
| 成员运动窗总时长/s | 616537.3 | 607677.2 |
| 通用 M1 驻留阳性 | 324/480 | 306/480 |

低速事件减少不等于低速时间等比例减少，更不表示所有意图捷径已消除。通用 M1 空间驻留不直接解释为悬停。

## 任务语义与几何

| 指标 | r2 | r3 |
|---|---:|---:|
| 抵近观察专用 observation_dwell | 68/68 | 68/68 |
| 监视撤离事件 known | 100/100 | 100/100 |
| 监视有作业折返成员 | 96 | 96 |

环绕监视不以折返作为统一要求；所有角色仍按原 M1 判据验收。58/60 条原集合 episode 的参考几何哈希相同，2 条来自同一骨架的两种 mode 改选了几何候选。因此全组统计是集成版对照，不能全部单独归因于 r3。相同参考子集和逐成员对照另存。

## 新增 P2 八骨架

| 骨架 | 最终配对 | 候选轮数 | 首次失败环节/原因 |
|---|---|---:|---|
| family_s15_1c267d4d7000043d_ext_001_regular | PASS | 1 | 无 |
| family_s15_5024cb2ccea653ae_ext_001_regular | PASS | 1 | 无 |
| family_s15_5024cb2ccea653ae_ext_006_regular | PASS | 1 | 无 |
| family_s15_7b73a7fc210d4c8f_ext_001_regular | PASS | 1 | 无 |
| family_s15_8e012bf033eb6821_ext_001_regular | PASS | 1 | 无 |
| family_s15_aa4c66be8e85d64d_ext_006_regular | PASS | 1 | 无 |
| family_s15_ef1ed9ff0b0e7013_ext_001_regular | PASS | 1 | 无 |
| family_s15_f2adfbfae12fbbad_ext_006_regular | PASS | 3 | rehearsal_failure: [{'group_id': 'task_group_01', 'agent_id': 'uav_03', 'conditions': ['ended_outside_warning']}, {'group_id': 'task_group_01', 'agent_id': 'uav_04', 'conditions': ['ended_outside_warning']}, {'group_id': 'task_group_01', 'agent_id': 'uav_05', 'conditions': ['ended_outside_warning']}, {'group_id': 'task_group_01', 'agent_id': 'uav_06', 'conditions': ['ended_outside_warning']}] |

新增集合共 134 个 member-episode；低速事件 480，事件/km 0.678351，低速时间占比 22.5386%。没有完整 r2 历史对照。

`family_s15_f2adfbfae12fbbad_ext_006_regular` 前两候选到达原单机预算，部分成员 ended_outside_warning 未满足；第三候选成功。全部失败记录保留，没有增加预算、修改 M1 判据。

## 审计链与停止边界

- 签名澄清单独提交 fdbc273，仅规范化临时随机目录及检出根路径；文件名、errno、异常类型、其余消息严格比较。覆盖测试通过，不消耗修复额度。
- R4 未修复 harness 实现，剩余额度 1 次；未修改既有测试断言或生产代码以通过门禁。
- 报告汇总首次调用被 Conda 多行参数限制拒绝（Python 未执行）；改从外部报告文件运行。没有重跑实验或修改门禁。
- 18 项历史测试债务见 legacy_test_debt.md，其中 3 项缺字段夹具为正式冻结前必修，本轮未修。
- 原 R1 FAIL、attempt04 FAIL、R3 BLOCKED 记录保留。
- R0–R4 通过授权后门禁，停止于人工冻结之前；未合并稳定分支、打标签或量产。

外部证据：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\fast_dynamics\m3\m3_r3_r4_attempt01`。运行代码提交：`9ad8dd0c8f5bb31b5b708d1a1892fa2b71c4b101`。外部报告脚本、逐成员对照和原始结果哈希见 external_evidence_index.json。
