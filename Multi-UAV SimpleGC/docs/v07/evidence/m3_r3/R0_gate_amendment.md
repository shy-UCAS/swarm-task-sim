# R0 门禁修订与完整重新验收

用户明确批准沿用原 M3 `tiers()` 的 N/A 适用性规则。原阻断来自新增全模式门禁与原适用性规则不一致，不是校准数据错误。原 `R0/gate.json`、`R0_report.md`、`R0_validation_plan.json` 与外部 audit01 均保留原样。

对 truth、observation 分别计算原 `aggregate_pairs().motion_reference_known`：原参考 total 为 0 时 applicable=false、passed_check=null、status=N/A；否则保持 all_task_rate >= 0.95。总体仍 >=0.98，成功和观测成功仍 >=0.995。保留全部 282 项和相同参考身份；缺失原本可评价的 r3 结果不能变为 N/A。所有数值误差非退化门槛及 1e-9 浮点容差不变。

本次重新读取并核验原 8196 项文件哈希、282 项任务身份、参考/候选输入绑定、冻结配置和历史结果；重新调用原 paired_metrics、aggregate_pairs、tiers。后续输入登记扩展为 8608 项文件，锁定 D0b 七探针、R2 原 70 项功能子集及 282 全集、R4 去重后 38 个骨架。原始代码、判据和数据没有改写。

| 模式 | 任务数 | truth 可评价/状态 | observation 可评价/状态 |
|---|---:|---|---|
| equal_strip_lawnmower | 42 | 42 / PASS (42/42) | 42 / PASS (42/42) |
| equal_strip_rectangular_spiral | 56 | 0 / N/A | 0 / N/A |
| line_abreast | 94 | 94 / PASS (94/94) | 94 / PASS (94/94) |
| staggered_same_loop | 90 | 90 / PASS (90/90) | 90 / PASS (90/90) |

完整门禁：`R0_revalidated_gate.json`，status=PASS、result=R0_REVALIDATED_PASS。修订计划：`R0_validation_plan_amended.json`；其 SHA256 已绑定到新门禁和 pipeline_state。旧状态快照另存 `pipeline_state_R0_blocked.json`。

新增 6 项 N/A、FAIL、分母和非退化测试，保留旧 4 项测试，共 10 项。外部重验证据在 `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\fast_dynamics\m3\m3_r3_r0_revalidate01`。不启动 SITL、不运行 holdout、不推送或正式冻结。
