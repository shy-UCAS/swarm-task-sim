# v0.5 M0 基线核对

日期：2026-10-02。状态：`IMPLEMENTED_AND_TESTED`（仅 M0 离线核对；尚未运行 v0.5 SITL）。唯一执行依据为[修订版 r1 计划](swarm-task-sim_v0.5_最小双意图数据集实施计划_修订版r1.md)，并沿用 v0.4 计划第 0 节的证据与进程规则。

## 结论

| 核对项 | 结果 |
| --- | --- |
| Git 起点 | `main`，`c204d1d013cdc668aa1979c66687d58c6a551da6`；相对 v0.4 计划所列原始基线 `e13564b700934b481ad37cba053db9daabf9e4fa`，已有审查、WP-S、WP-G、WP-E、V1、V06 六次提交 |
| 原有测试 | `llm` 环境 Python 3.12.3，430/430 通过；[完整日志](../tmp_v05/m0/baseline_tests.log)，SHA256 `9955431613614b35e6a73bb1abef1c9ba36992c7f5a9443f09cab689b0829794` |
| v0.4 兼容基线 | 6 个 v3 示例任务与 10 个 V06 任务的规范化哈希、33 个 V06 生成 JSON 的文件哈希已冻结在[兼容基线](../tmp_v05/m0/v04_compatibility_baseline.json)；用于 H02/R06 对照 |
| 受保护产物 | 原 V06 前快照 10,336/10,336 文件重新计算 SHA256，变化 0；新建的[v0.5 保护基线](../tmp_v05/m0/protected_baseline.json)覆盖 11,307 个文件、约 4.29 GiB，包含 V06 新产物、原始 `SimpleGC/`、固件及参数模板；[首次重新核对](../tmp_v05/m0/protected_recheck.json)为 11,307/11,307 一致 |
| 工作区 | 开始时仅修订版计划文件未跟踪；`tmp_v05/` 是本轮新建证据目录。未修改旧运行、数据集、生成物或验证记录 |

## 任务种子依赖核实

结论是**有条件成立**。[生成器](../swarm_sim/generation_v2.py)在 profile 未给 `template_id` 时，用完整模板的哈希生成默认 ID；任务种子又包含该 ID。因此只改 `execution.terminal_hold_s` 也会改变任务种子。用 V06 第 0 场景的真实场景种子演示，默认 ID 下任务种子从 `4835539782409883372` 变为 `1904240717079467866`。V06 profile 显式固定 `template_id`，同样修改下任务种子均为 `330863698933941023`，与已有 `mission_list.json` 对上。场景种子独立于模板。完整输入和计算链见[JSON](../tmp_v05/m0/seed_dependency_review.json)与[说明](../tmp_v05/m0/seed_dependency_review.md)。R06 须验证新 `seed_scheme` 在执行参数变化时保持巡逻任务抽样不变，同时保证 V06 缺省路径逐文件哈希不变。

## 保护边界

v0.4 计划原文将 `audit_v04/` 视为未纳入版本管理的审查证据；当前 HEAD 已包含该目录的顶层审查资料，这是前一轮按用户要求提交后的仓库现状。本轮不再修改或提交其中内容，保护基线覆盖其全部 1,270 个文件。源码、测试和脚本属于 v0.5 将修改的范围，不纳入文件冻结；其行为由 430 项既有测试与上述兼容哈希守护。

M0 只包含旧测试、源码与历史证据核查、文件哈希；不能将其写作 v0.5 飞行验证。后续运行前后由[scripts/verify_v05_protected.py](../scripts/verify_v05_protected.py)复核快照，发现缺失或变化立即停止。下一步依计划进入 WP-H 离线实现与 H01–H03 验收。
