# 项目交接

本仓库用 ArduCopter SITL 生成多无人机轨迹、双通道标签及描述；v0.5 用于算法链路开发。

- `Multi-UAV SimpleGC/`：当前多机工程；`swarm_sim/` 源码，`tests/` 测试，`scripts/` 执行与复核，`docs/` 规则/报告，`verification/` 实跑台账，`tmp_v05/` 离线证据，`generation_profiles/` 配置。
- `SimpleGC/`：原始单机工程；`.claude/progress/`：仓库级进度快照。

## 环境与常用命令

Windows 只用 PowerShell 7；首次运行检查 `$PSVersionTable.PSVersion` 主版本 ≥ 7。已验证路径：`C:/Users/shy/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe`。

Python 前先读 `Multi-UAV SimpleGC/.conda-env`（当前 `llm`），遵循项目 `AGENTS.md`；在该项目目录运行：

```powershell
& 'C:/Users/shy/anaconda3/Scripts/conda.exe' run -n llm --no-capture-output python -m unittest discover -s tests
& 'C:/Users/shy/anaconda3/Scripts/conda.exe' run -n llm --no-capture-output python main.py --help
```

Git 一律在 `F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation` 仓库根执行（子目录可能触发 dubious ownership）：`git status --short`、`git diff --check`。提交/推送按用户本轮授权；当前将全部改动本地提交，不推送，再执行 B002–B240。SITL 命令须先核对当前规则、预算和台账；停止后的恢复必须依据用户授权并保留说明。

## 铁律与报告

- 不修改或删除旧证据、原运行、已有分析/判定和受保护文件；新版本分析另存目录并绑定来源。历史停止记录和旧哈希保留；用户已授权本轮在原批量台账写入简短修复/恢复说明后接续，不另建恢复机制。
- 未经用户指令不改阈值、门禁和已有判定；失败如实保留，不能重跑洗掉失败；停止时写停止报告并更新进度快照。
- 报告按“结论 → 异常 → 证据位置”；数字带分母。代码摘录必须从源码原样复制并标注行号；正文公式用 `\(...\)`。

## 决策原则
- 优先级：P0 研究正确性（模型输入、标签与描述事实、数据划分泄漏、任务语义、数据完整与可复现）> P1 完成当前里程碑 > P2 诊断记录 > P3 形式完备与未来扩展（不做）。
- 遇到异常，先回答"它具体会让哪项研究结果出错"。能回答才停止；答不出就记录并继续；无法判断时只做一轮影响定位，不顺手修复。
- 规则误报时的处理顺序：判断是否必要 → 删除 → 简化 → 降级为诊断 → 最后才加例外。
- 不新增当前里程碑非必需的模块、字段、版本或检查；想到的改进写入待办，不实现。
- 停止报告必须写明：此问题会导致哪一项研究结果错误。

## 新会话恢复顺序

1. 先读 `.claude/progress/` 中最新进度快照，并核对当前代码和证据。
2. 再读 `Multi-UAV SimpleGC/docs/v0.5_当前有效规则.md`。
3. 最后按最新用户指令执行任务。暂停 1 已确认，返航描述核对通过；用户已授权最简修复 B001 分析目录问题，用原数据补做 v2/v3 离线分析，不重飞，原 STOP 与初报保留。本地提交后继续 B002–B240，完成全量验收与最终报告后停在暂停 2；实际状态、预算与门禁见当前规则。
