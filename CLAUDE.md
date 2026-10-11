# 项目交接

本仓库用 ArduCopter SITL 生成多无人机轨迹、双通道标签及描述；v0.5 已冻结，v0.6 三意图与 pilot 已完成。r1 在 296/900 后持久化停止；r2 在 465/900 后因外部负载触发滚动异常停止；两批均未收尾、不可续跑，仅保留证据。停止规则已修订：滚动异常为可人工续跑的规则暂停，确认违规及基础设施类停止不变。下一步先做并行扩展与仿真倍率对照测试（`v06_accel_test_plan.md`，尚未纳入仓库），确定配置后准备 r3 从头运行 900 个任务；本轮不准备/运行新批次。先读根 `README.md` 与 [规则修订记录](Multi-UAV%20SimpleGC/docs/v06_rule_pause_kickoff.md)。本文件状态更新于 2026-10-11。

- `Multi-UAV SimpleGC/`：当前多机工程；`swarm_sim/` 源码，`tests/` 测试，`scripts/` 执行与复核，`docs/` 规则/报告，`verification/` 实跑台账，`tmp_v05/` 离线证据，`generation_profiles/` 配置。
- `SimpleGC/`：原始单机工程；`.claude/progress/`：仓库级进度快照。

## 环境与常用命令

Windows 只用 PowerShell 7；首次运行检查 `$PSVersionTable.PSVersion` 主版本 ≥ 7。已验证路径：`C:/Users/shy/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe`。

Python 前先读 `Multi-UAV SimpleGC/.conda-env`（当前 `llm`），遵循项目 `AGENTS.md`；在该项目目录运行：

```powershell
& 'C:/Users/shy/anaconda3/Scripts/conda.exe' run -n llm --no-capture-output python -m unittest discover -s tests -p test_publication_runtime.py
& 'C:/Users/shy/anaconda3/Scripts/conda.exe' run -n llm --no-capture-output python main.py --help
```

Git 在当前 `Simulation-dev` 仓库根执行：`git status --short`、`git diff --check`；Python 通常在 `Multi-UAV SimpleGC` 中执行。原 `Simulation` 仅作冻结归档，不从其旧 main 开发或推送。发布 PR #1 与并行开发 PR #2 已合并；规则修订起始 HEAD 为 `main=8fbe1d7`，r2 运行提交为 `8d366b4`／`v0.6-production-r2`，r1 运行提交为 `762a303`／`v0.6-pilot`，pilot30 运行提交为 `0dffcd8`／`v0.6-pauseA3`，不能混同。尚未打 `v0.6-production` 标签。后续以 `git log -1`、标签指向与工作区状态为准；提交/推送按当前用户授权执行。当前离线 CI 清单见 `.github/workflows/unit-tests.yml`，历史通过数不等于当前 HEAD 已重新验收。当前没有自动接续的仿真任务。

## 铁律与报告

- 不修改或删除旧证据、原运行、已有分析/判定和受保护文件；新版本分析另存目录并绑定来源。历史停止记录和旧哈希保留；旧阶段的接续授权不等于当前授权，不修改冻结台账来启动新实验。
- 未经用户指令不改阈值、门禁和已有判定；失败如实保留，不能重跑洗掉失败；停止时写停止报告并更新进度快照。
- 报告按“结论 → 异常 → 证据位置”；数字带分母。代码摘录必须从源码原样复制并标注行号；正文公式用 `\(...\)`。

## 决策原则
- 优先级：P0 研究正确性（模型输入、标签与描述事实、数据划分泄漏、任务语义、数据完整与可复现）> P1 完成当前里程碑 > P2 诊断记录 > P3 形式完备与未来扩展（不做）。
- 遇到异常，先回答"它具体会让哪项研究结果出错"。能回答才停止；答不出就记录并继续；无法判断时只做一轮影响定位，不顺手修复。
- 规则误报时的处理顺序：判断是否必要 → 删除 → 简化 → 降级为诊断 → 最后才加例外。
- 不新增当前里程碑非必需的模块、字段、版本或检查；想到的改进写入待办，不实现。
- 停止报告必须写明：此问题会导致哪一项研究结果错误。

## 新会话恢复顺序

1. 先读根目录 `README.md` 并核对 Git 状态；本机 `.claude/progress/` 的最新快照可辅助恢复，但新克隆不保证存在。
2. 再读 [生产停止报告](Multi-UAV%20SimpleGC/docs/v0.6_production_stop_01.md) 和 [pilot 报告的暂停 B 复核结论](Multi-UAV%20SimpleGC/docs/v0.6_pilot_report.md)，以及本次任务涉及的规则、源码和证据；涉及 v0.5 时读其冻结最终报告。历史规则文件的“剩余步骤”不代表当前进度。
3. v0.5 已完成 260 次运行并冻结。v0.6 pilot20（质量 20/20、语义一致 19/20）与 pilot30（质量 29/30、语义一致 29/30）均已收尾，不用于训练。快速通过六项阈值冻结；事实层 `observer_facts_v06b`／`pattern_detector_v06b` 修复已在 `a345f27` 提交，12/12 离线验收通过；最后终点悬停 2 秒，固件版本等待恢复 10 秒。
4. 正式生产 `v06_production900_seed2026100812` 已执行两段并发生一次人工暂停续跑；目前 296/900 个不同任务有终态记录（completed 288、failed 8），质量合格 287/296、语义一致 289/296。2026-10-10 05:22:08（America/Los_Angeles）台账替换 `control.json.tmp -> control.json` 的 `WinError 5` 导致规则停止；`completed=false`、`finalized=false`，无正式导出数据集或描述层。逐尝试证据位于仓库外 `SwarmData/parallel_batch/v06_production900_seed2026100812/`。
5. r2 使用 `8d366b4`／`v0.6-production-r2`，465/900 次尝试中质量合格 446/465、语义一致 453/465。外部负载突发导致 4 次时钟失败与 1 次断连，触发旧规则不可恢复停止；见 [r2 停止报告](Multi-UAV%20SimpleGC/docs/v0.6_production_r2_stop_01.md)。r1/r2 不得清除 `stopped_reason`、直接 `--resume`、补飞、覆盖 prepare 或强行 finalize。
6. 新代码滚动异常改为规则暂停：停止派发、排空登记、`paused=true` 且停止原因为空，事件分 manual/rule，记录原因、触发尝试、排空完成及累计次数；人工检查后显式续跑，预算与窗口不清零。续跑后只有新异常且窗口达阈值才再次暂停。确认违规、持久化/派发基础设施失败、合并错误和 family 泄漏仍不可恢复。
7. 生产期间机器独占使用，不运行播放器、本地大模型、文档解析服务或训练。进度只读 `progress.json`；控制器退出后才读台账。资源采样写在批次外，记录整机指标及内存/CPU 前五进程。生产期间不在本仓库开发；`Simulation-dev-wip` 属另一会话，本轮不碰。旧计划和历史授权不自动转化为新运行授权。
