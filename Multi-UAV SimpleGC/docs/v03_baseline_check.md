# v0.3 开发基线核对

- 核对日期：2026-09-30。
- 开发前提交：`0ea70a2ae08cf76d2b34322fa47e466659a20bdf`，分支 `main`，工作区干净。
- 范围：仅 `Multi-UAV SimpleGC` 及仓库入口说明；原始 `SimpleGC` 保持原状。
- 项目环境：`.conda-env` 指定 `llm`；PowerShell 7.6.5、Python 3.12.3、pymavlink 2.4.50。
- 开工前实际执行 `conda run -n llm --no-capture-output python -m unittest discover -s tests -q`：63 项通过。
- 三类 v1 任务编译结果与版本库中的 `scenarios/task_*_3uav.json` 一致；这些场景作为兼容性参照，不重写为 v2。
- 之前 v0.2.2 的三机真实飞行记录仍是历史证据，不算作本次 v0.3 实跑。
- 现有规模和执行限制保留：1～6 机、最多 100 个阶段、AUTO 全机阶段屏障、速度倍数 1、本机独立 SITL。
- 数值质量策略保持 `quality_policies/default_v022.json`；新标签与资格规则另外版本化。
- 不安装新依赖，不自动提交或推送，不覆盖旧运行与旧分析。

## 开工时确认的接线问题

1. `runner` 和旧验证器直接读取 TaskSpec v1 的 `task`，必须增加版本分派。
2. 原有主分析窗口不包括完整起飞和降落，全程资源检查需要独立生命周期窗口。
3. SIM 非有限数据需要保留异常断点，避免成为真值主判据后跨异常插值。
4. v1/v2 语义协议与数值质量策略是独立维度，数据集必须分别校验。
