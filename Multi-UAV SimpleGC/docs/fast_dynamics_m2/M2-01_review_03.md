# M2-01 最终放行回执：PASS

日期：2026-10-12。最终修订：`attempt_03_id_guard`。用户授权 Codex 直接完成最后修复与收尾。

**结论：PASS。M2-01 证据迁移、清理、输出根和 ID 前置校验已完成，可以由用户启动 M2-02。当前业务变更尚未提交；没有开始 family 划分、M2 飞行功能或 M3。**

前两轮 [回执一](M2-01_review.md)、[回执二](M2-01_review_02.md)保持原样。本回执取代未放行状态，保留此前问题与被审版本。

## 1. 最后修复及验证

新增 `validate_run_id`，匹配公共产物既有 `[A-Za-z0-9_-]{1,100}` 规则，并执行必要的 Windows 文件名检查。run CLI 在输出分支选择、任务读取、目录创建和模拟之前无条件调用它；没有放宽 `write_episode` 或 dataset 的 ID 规则。通用命名前缀仍允许 benchmark 的 `.json` 文件名。

新增配对反例覆盖 11 类不合法 ID × 自动/显式两种输出模式：路径片段、点号 ID、空值、超长、设备名、盘符、分隔符、空格、非 ASCII 及 `.`/`..`。逐项断言参数拒绝、任务读取 0、模拟调用 0、临时根内无任何新增文件/目录；合法显式 ID 实际通过完整公共链，294 帧、语义成功、4 条描述。

最终针对性测试 **66/66 通过，0 失败、0 错误、0 skip**：内核 15、执行 10、产物 14、路径策略 27。包含真实默认/显式完整链、三个真实 junction 用例，以及原失败留痕、重复 attempt、worker 一致性和产物防伪测试。

首次辅助 runner 缺少 Windows spawn 所需的 `__main__` 保护，结果为 65 通过、1 worker 用例错误；日志、脚本、结果和解释均保留。仅修正外部 runner，以新日志复跑得到最终 66/66，不将该辅助脚本错误记为动力学回归。

## 2. 保留已通过的结论

上一轮独立复审已经确认：356 项归档全部匹配、338 项清理符合批准范围、18 项保留身份正确、7 条归档样本可独立加载/审计，以及真实 verify 的 7 个子 attempt 根身份和完成标记一致。本轮没有重新迁移、恢复删除项或改写这些证据。

原完整离线运行是 431 项总数、430 通过、1 卷相关 skip；被跳过用例另在 C: 环境独立补跑通过。本轮未重跑该全清单或完整 verify，最终 66 项仅验证本次局部改动与受影响链，不混写旧结果或虚构新的 433 项全量通过。

## 3. 最终身份

| 对象 | 身份 |
| --- | --- |
| 分支 / HEAD | `codex/fast-dynamics` / `57cca914f2e8b414e8820a1f08f6fd900f912d36`，未变 |
| 最终跟踪 diff | 1634145 字节；SHA256 `49945d06b9de5a9759ee51e8d136fa737a18f82c3ac6a17b907926b096c48539` |
| 最终报告 SHA256 | `1a5f40ec2a980c91c0dc60d82a62e5b46d82c374506dc69fca3dcbd0f17c9b38` |
| 最终摘要 SHA256 | `7f4383d08b3f6cd4031b13e422d812fa14a0298b7c6dd21bafd0c257002677f3` |

diff 为 Git 根 `git diff --binary --no-ext-diff --no-color HEAD --` 的 stdout 原始字节。新增未跟踪代码、测试、报告、回执和指令不在该 diff 中；分别绑定于本轮外部最终索引。

本轮证据目录：

```text
F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/m2/M2-01/attempt_03_id_guard/
  before/                         修复前原样副本
  before_manifest.json            11 文件原身份
  targeted_tests.log/json          首次 runner 错误，保留
  targeted_tests_pass2.log/json    最终66项通过
  first_run_note.md               runner错误原因
  source_snapshot_final.json      最终可执行改动身份
  final_validation.json           当前文件/链接/差异及历史证据身份核验
  tracked_diff_final.patch        最终差异原字节
```

本次是 Codex 按用户授权直接修改后验证，没有声称另一个审阅者独立实现了修复。没有修改冻结 Simulation、其他会话工作树、旧 SITL 数据或未来盲测资料，没有提交、amend、push 或启动后续阶段。

## 4. M2-02 放行范围

下一阶段按 [M2-02 任务计划](M2-02_instruction.md)执行：核对来源和使用记录；在读取候选运行结果前预登记重复关联规则，按 family/泄漏分量冻结校准与盲测划分；从开发来源登记 12 个真实任务和状态负例方案，实测字段均为 NOT_RUN/null。

用户启动 M2-02 后，可按显式白名单保存本回执批准的 M2-01 代码、测试、迁移索引、182 项跟踪删除、必要文档和报告。Git 历史不改写，原始证据仍在仓库外。新阶段完成后状态 `AWAITING_REVIEW` 并停止，不自动实现 M2-03 或运行 M3。
