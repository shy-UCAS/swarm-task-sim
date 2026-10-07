# v0.6 离线预检查归档

本目录原样保存已完成的截断扰动诊断、DR130 金标准生成脚本及结果摘要。归档时没有重新执行脚本；运行基线为 `fe7ac4da8bb41498bcb1ba97ac20df76b71ab7c0`。这些脚本只读取冻结代码和历史数据、写入外部结果目录，不启动仿真；审计钩子禁止子进程及结果目录以外的写入，并禁止修改隔离基线副本。

| 文件 | 字节数 | 原文件 SHA256（复制后逐项相同） |
|---|---:|---|
| `diagnose.py` | 12,093 | `066165ea633c1b9760695f059395869fcf1071c124768a9e3ce9bc4a44b39fc1` |
| `freeze_golden.py` | 5,171 | `10b3d8c50e4459b90d8bdc0cdbc57e5ed82eca1cee9be16e29c64724f87bad75` |
| `truncation_diagnostic.json` | 20,767 | `156ab5113d4598fe0ce64c4d492fc6d2f8b8c193b46eeb42cfb8aba0f04ba7b7` |
| `golden_summary.json` | 887 | `8296fb454c53f9988b846b98c2628342450bcac2a9913ba82814b3b7bd403347` |

四个原样文件合计 **38,918 字节**，单个及合计均小于 5 MB。完整冻结夹具已保存于 [`tests/fixtures/intent_registry_DR130_golden.json`](../../tests/fixtures/intent_registry_DR130_golden.json)（146,787 字节），未重复复制。详细结论见[预检查报告](../../docs/v0.6_intent_registry_prechecks.md)。

## 结果分母

- 截断诊断：PP01、PP02、PP05、PP14 共 **4 次运行**；原始成功判定、条件、事实和描述均与历史结果一致，原始描述 **16 条**。两种截断共 **7/7 个适用案例通过**（PP05 不要求返航，无返航前截断），检查截断描述 **28 条**。观测不足项为“未知”，不是“否”；详见 JSON 中的双通道三值结果。这不是全量 260 次运行标签和 1,008 条描述的等价性验收。
- 金标准：同一主种子 `2026100205` 重生成 **130 个 family、260 个任务**，完整 DR130 清单与归档一致；实际使用的 PP20 **20/20**、B240 **240/240** 条目均一致，全部任务与规划文件逐字节一致。夹具 SHA256 为 `b4e3a4dd6ac90c8a43a1b98d2ad71f5d30403b3f0c118129eea63c4ae63ee53a`。

## 复现前提与本机路径

这些是当次核验脚本，原样保留了路径假设，不能直接对任意 checkout 或精简发布数据运行。`diagnose.py` 要求显式设置 `SIM_DATA_ROOT`，从其 `r2_fe7ac4d/baseline/Multi-UAV SimpleGC/` 导入代码，并将当前目录切换到该隔离副本；副本必须事先从上述基线提交完整提取并核验。`freeze_golden.py` 导入同目录的 `diagnose.py`，继承相同路径和写入保护，且需要完整归档。

归档根硬编码为 `F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation/Multi-UAV SimpleGC`；脚本还声明了本机 `Simulation-dev` 路径。冻结台账、分析选择清单中的绝对运行路径和分析路径必须可读，且 manifest 哈希仍匹配；仅设置新的 `SIM_DATA_ROOT` 不会重定位这些输入。脚本依赖归档中的原始遥测、最终分析、260 个 episode、事实和描述，并使用隔离基线内的质量策略及生成 profile。换机器时需单独安排路径映射与绑定验证，不能通过改写冻结归档来迁就脚本。

当次外部结果根为 `C:/Users/shy/.codex/visualizations/2026/10/07/01a116da-bdd0-7400-a803-7c3858904e9f/intent_registry_data`。脚本会写入其 `r2_fe7ac4d/` 下的摘要、逐案例结果与生成文件；复现应另选全新外部数据根并准备基线副本，避免覆盖当次证据。使用项目指定 Conda `llm` 环境及 `python -B`；本目录不是 pilot 的启动入口。

归档前已人工检查脚本和摘要，并检索常见凭据字段／令牌模式，未发现凭据。保留的本机用户名、绝对目录、运行 ID 与哈希均用于来源追溯。
