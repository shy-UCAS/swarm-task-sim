# 项目交接

本仓库用 ArduCopter SITL 生成多无人机轨迹、双通道标签及描述；v0.5 已完成并冻结，v0.6 三意图与 pilot 已完成，正式生产 r1 在 296/900 个任务后规则停止、未收尾，保留为证据；用户已决定修复台账持久化后另建 r2 批次 `v06_production900r2_seed2026100812`（标签 `v0.6-production-r2`）从头运行，r2 准备中。新会话先读根目录 `README.md`，其中保存当前进度和新旧仓库边界。本文件状态核对日期为 2026-10-10。

- `Multi-UAV SimpleGC/`：当前多机工程；`swarm_sim/` 源码，`tests/` 测试，`scripts/` 执行与复核，`docs/` 规则/报告，`verification/` 实跑台账，`tmp_v05/` 离线证据，`generation_profiles/` 配置。
- `SimpleGC/`：原始单机工程；`.claude/progress/`：仓库级进度快照。

## 环境与常用命令

Windows 只用 PowerShell 7；首次运行检查 `$PSVersionTable.PSVersion` 主版本 ≥ 7。已验证路径：`C:/Users/shy/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe`。

Python 前先读 `Multi-UAV SimpleGC/.conda-env`（当前 `llm`），遵循项目 `AGENTS.md`；在该项目目录运行：

```powershell
& 'C:/Users/shy/anaconda3/Scripts/conda.exe' run -n llm --no-capture-output python -m unittest discover -s tests -p test_publication_runtime.py
& 'C:/Users/shy/anaconda3/Scripts/conda.exe' run -n llm --no-capture-output python main.py --help
```

Git 在当前 `Simulation-dev` 仓库根执行：`git status --short`、`git diff --check`；Python 通常在 `Multi-UAV SimpleGC` 中执行。原 `Simulation` 仅作冻结归档，不从其旧 main 开发或推送。发布 PR #1 与并行开发 PR #2 已合并；本次文档核对 HEAD 为 `main=037ed7e`（生产停止报告），生产运行提交为 `762a303`／`v0.6-pilot`，pilot30 运行提交为 `0dffcd8`／`v0.6-pauseA3`，不能混同。尚未打 `v0.6-production` 标签。后续以 `git log -1`、标签指向与工作区状态为准；提交/推送按当前用户授权执行。当前离线 CI 清单见 `.github/workflows/unit-tests.yml`，历史通过数不等于当前 HEAD 已重新验收。当前没有自动接续的仿真任务。

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
5. r1 批次不得清除 `stopped_reason`、直接 `--resume`、补飞、覆盖 prepare 或强行 finalize。用户已决定：修复持久化（`save_atomic` 共享冲突退避重试、worker 改读 `assignment.json`、只读 `progress.json`）后，以同 profile、同主种子 `2026100812` prepare r2，任务清单须与 r1 逐条一致；prepare 后停下，由用户启动。任务记录见 [r2 起始指令](Multi-UAV%20SimpleGC/docs/v06_r2_kickoff.md)。运行期间查看进度只读 `progress.json`，不打开 `control.json`；生产运行期间不在本仓库开发，新功能在 worktree `Simulation-dev-wip`（`wip/episode-player`）中进行。旧计划、旧命令和历史启动授权不自动转化为新的运行授权。
