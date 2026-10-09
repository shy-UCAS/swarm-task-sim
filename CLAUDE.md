# 项目交接

本仓库用 ArduCopter SITL 生成多无人机轨迹、双通道标签及描述；v0.5 已完成并冻结，用于算法链路开发。新会话先读根目录 `README.md`，其中保存当前进度和新旧仓库边界。

- `Multi-UAV SimpleGC/`：当前多机工程；`swarm_sim/` 源码，`tests/` 测试，`scripts/` 执行与复核，`docs/` 规则/报告，`verification/` 实跑台账，`tmp_v05/` 离线证据，`generation_profiles/` 配置。
- `SimpleGC/`：原始单机工程；`.claude/progress/`：仓库级进度快照。

## 环境与常用命令

Windows 只用 PowerShell 7；首次运行检查 `$PSVersionTable.PSVersion` 主版本 ≥ 7。已验证路径：`C:/Users/shy/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe`。

Python 前先读 `Multi-UAV SimpleGC/.conda-env`（当前 `llm`），遵循项目 `AGENTS.md`；在该项目目录运行：

```powershell
& 'C:/Users/shy/anaconda3/Scripts/conda.exe' run -n llm --no-capture-output python -m unittest discover -s tests -p test_publication_runtime.py
& 'C:/Users/shy/anaconda3/Scripts/conda.exe' run -n llm --no-capture-output python main.py --help
```

Git 在当前 `Simulation-dev` 仓库根执行：`git status --short`、`git diff --check`；Python 通常在 `Multi-UAV SimpleGC` 中执行。原 `Simulation` 仅作冻结归档，不从其旧 main 开发或推送。发布 PR #1 与并行开发 PR #2 已合并；本次核对时 main 已推进到 v0.6 的 `v0.6-pilot` 标签（30 任务 pilot 与阈值冻结），当前基线以 `git log -1`、`git describe --tags` 为准，不要沿用旧基线号 `9812645`；提交/推送按当前用户授权执行。当前离线 CI 清单见 `.github/workflows/unit-tests.yml`，包含发布逻辑检查、并行测试与 v0.6 三意图测试；141 项是迁移时的历史计数，完整历史集成测试需要另行取得归档。当前没有自动接续的仿真任务。

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
2. 再读 `Multi-UAV SimpleGC/docs/v0.5_final_report.md`，以及本次任务涉及的有效规则、源码和证据；历史规则文件的“剩余步骤”不代表当前进度。
3. v0.5 已完成 260 次运行并冻结；Git 发布、迁移及 v0.6 并行开发合并均完成。v0.6 已完成 20 任务（20/20、合格 20/20、语义一致 19/20）与 30 任务（30/30、合格 29/30、语义一致 29/30）两次两路试跑，含一次真实人工暂停续跑，均已收尾，数据在仓库外 SwarmData，pilot 不用于训练；快速通过六项阈值已冻结，事实层 `null` 槽位问题已修复并通过离线验收。`Multi-UAV SimpleGC/docs/v06_formal_plan.md` 的 pilot 阶段已执行完毕，正式生产（300 family／900 任务）已完成批次准备但**未启动仿真**；新会话先恢复已完成进展，后续按新的用户指令执行，不自动启动仿真、批量生成或改写旧证据。
