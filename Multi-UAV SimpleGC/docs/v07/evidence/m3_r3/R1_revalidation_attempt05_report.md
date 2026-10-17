# R1 attempt05：G-2a 重验 PASS

原 attempt04 FAIL 和之前 BLOCKED 记录保持不变。

本次 R1_REVALIDATED_PASS：原 209 项完整回归执行，205 PASS、4 BASELINE_KNOWN_FAILURE，新增回归 0。新增门禁测试 15/15 PASS。

七个 r2 探针全部与历史 A 逐位一致；七个 r3 探针全部与历史 B2 逐位一致。输入哈希、曲线和限速、物理限制、有序航点、M1 驻留、低速及偏差复现检查均通过。

probe_05 的绝对跟踪偏差两版仍超过 0.5 m，r2 最大值 1.7849249178526083 m、r3 最大值 1.7853429850690588 m。接近/驻留阶段最大值分别增加约 0.566/1.336 mm；原始诊断仍记录 FAIL，按人工 G-2a 不参与硬门禁。不得据此称绝对精度已经合格。

运行中源码与旧证据哈希保持不变，r2 冻结配置未变。墙钟 810.968 s。未使用本轮额外 2 次 harness 修复额度。

证据：R1_revalidated_gate_attempt05.json；R1_revalidation/attempt05/；外部 SwarmData/fast_dynamics/m3/m3_r3_r1_revalidate05。现可按已授权规则进入 R2。
