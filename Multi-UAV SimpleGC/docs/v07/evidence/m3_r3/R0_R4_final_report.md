# M3-r3 R0–R4 最终交付（候选，未正式冻结）

按人工修订 G-1～G-5、G-2a、G-5a 及路径签名澄清执行，全部阶段完成。当前停止位置为 R4 PASS 后的最终人工验收；未正式冻结、未合并稳定分支、未打 First Edition 标签、未量产。

| 阶段 | 最终状态 | 核心证据 |
|---|---|---|
| R0 | R0_REVALIDATED_PASS | [R0 重验门禁](R0_revalidated_gate.json)：282 条身份及数据保留，按原 tiers 适用性规则复算 |
| R1 | R1_REVALIDATED_PASS | [attempt05](R1_revalidated_gate_attempt05.json)：209 执行，205 PASS、4 历史故障；七探针 r2 与归档、r3 与 D0b B2 逐位一致 |
| R2 | PASS | [报告](R2_report.md)、[门禁](R2_gate.json)：282/282 完整可比较，原 tiers().hard 通过 |
| R3 | PASS | [G-5a 报告](R3_G5a_report.md)、[门禁](R3_gate.json)：P2 范围合规、492 执行/474 PASS/18 历史故障，默认 r2 七探针逐位一致 |
| R4 | PASS | [报告](R4_report.md)、[门禁](R4_gate.json)：原 30/30、新增 8/8 严格配对，76/76 episode 完成；492 项零新增回归及额外 39/39 harness 测试通过 |

上述测试集合在不同阶段复跑，不将重复执行次数加总宣称独立测试数量。历史 FAIL/BLOCKED 报告和 attempt04 原件保留，最终修订状态不改写历史。

## 282 条任务与 N/A

truth/observation 两个通道均使用原 aggregate_pairs 的 motion_reference_known。任务执行与观测成功均 282/282，可评价运动一致率各 226/226。

| flight_pattern | 原任务数 | truth 可评价/状态 | observation 可评价/状态 |
|---|---:|---|---|
| equal_strip_lawnmower | 42 | 42 / PASS | 42 / PASS |
| equal_strip_rectangular_spiral | 56 | 0 / N/A | 0 / N/A |
| line_abreast | 94 | 94 / PASS | 94 / PASS |
| staggered_same_loop | 90 | 90 / PASS | 90 / PASS |

56 条矩形螺旋没有删除；N/A 不替代任务执行成功，也未把 0/0 填成 0% 或 100%。未启动新的 SITL，未使用禁止的 M2-02B 或重复 internal holdout。

## R4 完整对照与限制

原 30 个骨架、两种 mode，共 480 个 member-episode：

| 指标 | r2 | r3 |
|---|---:|---:|
| 低速事件总数 | 11586 | 900 |
| 低速事件/km（总事件/总实际里程） | 3.718714 | 0.286874 |
| 运动窗低速时间占比 | 8.5745% | 7.1601% |
| 通用 M1 驻留阳性 | 324/480 | 306/480 |
| 佯动通用 M1 驻留阳性 | 104/104 | 82/104 |
| 抵近观察专用驻留保留 | 68/68 | 68/68 |
| 监视重访、撤离事件保留 | 各 100/100 | 各 100/100 |

58/60 条原集合 episode 参考几何相同；另两条为同一侦察骨架的两种 mode 改选候选几何。相同参考子集（460 member-episode）低速事件 11158→848，事件/km 3.671295→0.279120，低速时间占比 8.5034%→7.2042%。全组变化不能全部单独归因于 r3。

新增 8/8 骨架最终配对成功，但 `family_s15_f2adfbfae12fbbad_ext_006_regular` 前两候选因单机超时而未退出警戒区，第三候选成功。原预算和 M1 判据未修改，失败过程完整保留。新增集合无完整 r2 历史仿真，不构造 A/B 分母。

76 条 episode 的独立标签/几何审计通过，无原禁区判据违规、无 P0ContractError；最小机间距 2.044225225697 m，发生于 `family_s15_c713f51898e81011_ext_000_regular_synchronous`。运行源码/配置指纹及输入校验不变。R4 墙钟 4459.890 秒，未超 21600 秒，未完成 0。

低速事件大幅减少，但低速时间仍存在，佯动 82/104 仍满足通用 M1 空间驻留。不能宣称所有意图捷径消失，也不能将通用驻留直接解释为悬停。

## 仍需人工接受或后续处理

- probe_05 既有绝对跟踪偏差约 1.785 m：r2 1.784924917853 m，r3 1.785342985069 m，均超过 0.5 m；按 G-2a 保留为已知限制，未隐藏或改判为绝对精度合格。
- R2 总时长相对误差中位数 1.5705%→1.7605%，有 113 条任务变差；观察时长和转弯速度等对照及各项最差前 10 条见 R2 报告。不能宣称所有校准指标改善。
- [18 项历史测试债务](legacy_test_debt.md)未修复；pair_mismatch、balanced_minimum_pairs、independent_group_audit 三项缺字段夹具必须在正式冻结前另行修复并验证 P0 断言确实执行。
- 路径规范化只替换 `<TMP>` 和 `<ROOT>`，其余签名严格比较，单独提交 `fdbc273`，不消耗修复额度。R4 没有 harness 实现修复，剩余额度 1 次。
- 报告生成第一次 Conda 多行参数调用在 Python 执行前被启动器拒绝，改从外部文件运行；不涉及阶段门禁或实验重跑。详情与脚本哈希见 R4 analysis_summary / external_evidence_index。

建议最终人工审阅上述限制，并先完成三项冻结前必修测试债务，再单独决定正式冻结、稳定分支合并与标签。本任务不执行这些操作。

## 证据与版本

- 分支：`fe/m3-r3-p2-candidate`。
- P2 合并：`8ed1036a45e0cf05241ab01c8115bc27773c91fc`；R4 运行代码：`9ad8dd0`。
- r2 配置 SHA256：`94822513045c434dc2f713070728f1f99d18bcbea3933f8f092b85c5e4d78193`。
- r3 候选配置 SHA256：`0fe3efff6f97ed88c665374d0280aef571b92399ac3711184f13e5c6a3de3b30`。
- [流水线最终状态](pipeline_state.json)、[R4 逐角色与同参考子集统计](R4/m3_r3_r4_attempt01/analysis_summary.json)、[外部证据哈希索引](R4/m3_r3_r4_attempt01/external_evidence_index.json)。
- R4 外部原始数据：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\fast_dynamics\m3\m3_r3_r4_attempt01`（含 registration、76 episode、完整测试日志、38 worker 结果、逐成员 M1/低速对照与报告生成脚本）。
- R3 外部数据：同级 `m3_r3_r3_attempt03`；R2：`m3_r3_r2_attempt01`；R1：`m3_r3_r1_revalidate05`。各阶段门禁列出完整路径。
