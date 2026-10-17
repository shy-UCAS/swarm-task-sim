# R3 G-5a 重验通过

结果 PASS。保留原 R3 attempt01/02 BLOCKED、原 R3_report.md 与库存清单，不改写历史。

完整候选 492 项：474 PASS、18 BASELINE_KNOWN_FAILURE、零新增失败、零签名变化、零意外跳过；已知故障意外通过 0 项。全部 36 项新增工具测试 PASS。
默认 r2 七探针使用不传 reference_version 的实际执行，time_us/p/v/a/agent_ids/execution_status 与历史归档逐位一致。

P2 合并提交：8ed1036a45e0cf05241ab01c8115bc27773c91fc。生产改动仅 construction.py::ingress_issues，函数外 AST 不变，整个文件与已批准 fa7518b 一致。
墙钟 364.046 s；输入、运行期源码、r2/r3 配置哈希保持不变。

候选冻结记录仅为 CANDIDATE_ONLY，尚未正式冻结或打标签。
签名路径规范化按用户补充单独提交 fdbc273；不计入修复额度，剩余仍 1 次。
G5a_gate_amendment.json 保存 18 项签名与原始消息；legacy_test_debt.md 完整保留原四项原文，并标出三项冻结前必修夹具债务。

外部原始数据：F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\fast_dynamics\m3\m3_r3_r3_attempt03
程序化门禁与差分：F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-fe-m3r3\Multi-UAV SimpleGC\docs\v07\evidence\m3_r3\R3\m3_r3_r3_attempt03

下一阶段 R4：原30严格配对硬门禁；新增8逐项测量；全部审计、禁区、保留 episode 间距≥2m、无P0、源码不变按原合同执行。
