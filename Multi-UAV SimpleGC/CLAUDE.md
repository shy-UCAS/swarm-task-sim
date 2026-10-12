<!-- activate-conda-env:begin -->
## Project Python environment

Read `.conda-env` from this project root before running Python or installing packages.
The file contains this project's Conda environment name, not a global default.
Use `conda run -n <name> --no-capture-output python ...` and
`conda run -n <name> --no-capture-output python -m pip ...`.
Resolve the configuration before changing the command's working directory.
Never fall back to a skills installation directory or another project's environment.
If the file is missing, empty, or names an environment unavailable on this machine,
list local environments and ask the user to choose before environment-dependent work.
Do not silently switch to base or install into another interpreter.
<!-- activate-conda-env:end -->

## 当前本地开发入口（2026-10-12）

先读 [根 README](../README.md)、[根交接规则](../CLAUDE.md)、[快速引擎开发交接](docs/fast_dynamics_engine_kickoff.md)、[M0/M1 报告](docs/fast_dynamics_engine_m01_report.md)与[完整实现计划融合修订版 r2](docs/fast_dynamics_engine_implementation_plan.md)。快速引擎 M0/M1 已本地实现，适配备忘/契约、确定性内核和最小双机完整数据链已落地，M0/M1 最终本地验收已通过。下一包 M2 扩三意图四飞法，M2–M5 尚未完成；校准按同源 family 去重划分，保留共同时间、来源协议及未来模型替换边界。新入口为 `scripts/run_fast_dynamics.py`，使用全新输出目录及七组严格配置；`requirements.txt` 已声明 `numpy==2.5.3`。

仅本地开发、测试和记录，暂不提交/推送/打标签；不启动 SITL、不续跑旧批次、不运行 T6、不准备 r3、不改旧数据。保留已有未提交文档。使用 PowerShell 7 与项目 Conda 环境，在 `Simulation-dev` 开发，不修改冻结归档 `Simulation`。
