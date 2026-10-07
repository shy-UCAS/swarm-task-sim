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

Git 在当前 `Simulation-dev` 仓库根执行：`git status --short`、`git diff --check`；Python 通常在 `Multi-UAV SimpleGC` 中执行。原 `Simulation` 仅作冻结归档，不从其旧 main 开发或推送。发布 PR #1 已合并，目录迁移完成；提交/推送按当前用户授权执行。141 项发布检查见 `.github/workflows/unit-tests.yml`，完整历史集成测试需要另行取得归档。当前没有自动接续的仿真任务。

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
3. v0.5 已完成 260 次运行和收尾；Git 发布、迁移均完成。后续工作依据新的用户指令，不自动启动仿真、批量生成或改写旧证据。
