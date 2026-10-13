<!-- activate-conda-env:begin -->

> **2026-10-13 当前状态：A 已获用户放行，B 修复与 282 条默认基线通过；调参因覆盖格计数门禁停止。** 统一 10 Hz 事实采样；原 patrol_0070_v00 从 600 s 超时恢复到 260.022496 s 完成，不改路线或超时。M2 的 16 条重飞通过，轨迹、事件、labels 全部保持原字节；新基线 282/282 合格，双通道判定全部一致，SITL 已知模式 226/226 一致。调参 config_005（执行响应 0.25→0.15 s）使 reconnaissance_0024_v00 的单机覆盖格 456→457、重复格 47→48，按现行硬门禁停止；不是 P0。完整离线 540/540、DR130 260/260、v0.5 四例通过。未冻结参数、未运行内部留出或高速检查；M2-02B 两组继续封存，不启动 SITL、不推送。详见[修复与调参停止报告](docs/fast_dynamics_m3_calibration_report.md)；本补注优先于下方历史状态。
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

## Current local development handoff (2026-10-12)

Latest follow-up: coverage geometry acceleration is verified (20 prior runs,
120 JSON files byte-identical; 12 positive reruns, 144 evidence files identical).
512 offline tests, DR130 260 cases and four v0.5 examples passed. Four-agent
lawnmower takes 47.549 s, so the 30 s target is not met; no other optimization.
M3 stopped at source mapping: the frozen M2-02B calibration inputs use the new
2026101203 source, and none of 213 tasks matches r2 family/scene/task identity.
Do not substitute same-name r2 tasks, change the split, or launch SITL. No M3
baseline or parameter calibration has run. Read
docs/fast_dynamics_coverage_performance_report.md before further work.
This follow-up supersedes the older M2-only stop description below.

Latest status: M2 implementation and the planned_phases P0 repair are complete.
The fixed 12 positive + 4 physical-state negative tasks passed the full chain;
502 offline tests, DR130 260 cases and all four v0.5 examples passed.
Read docs/fast_dynamics_m2/M2_runtime_resume_report.md for provenance, coverage,
timings and limitations. Preserve the previous P0 report and external evidence.
The user authorized this completion to be committed locally, without pushing.
M2 is stopped after completion; do not enter M3 or rerun historical batches.

Read `../README.md`, `../CLAUDE.md`, `docs/fast_dynamics_engine_kickoff.md`, then
`docs/fast_dynamics_engine_implementation_plan.md` before new engine work.
SITL v0.6.1 remains available. The local fast dynamics M0/M1 implementation now
includes the adapter memo/contract, deterministic numerical core, and a minimal
two-vehicle rapid-passage task through analysis/export/audit/descriptions/loading.
Final local M0/M1 verification passed (367 legacy plus 39 new tests); read `docs/fast_dynamics_engine_m01_report.md`
for actual results and remaining items. The next package is M2 full mission coverage;
M2-M5, calibration, production qualification, and full-production throughput validation are not complete.
The new entry point is `scripts/run_fast_dynamics.py`; always choose a new output
directory. `requirements.txt` declares `numpy==2.5.3` in addition to pymavlink.
Preserve existing local documentation changes and record actual progress in the handoff.
T1/T4 share 42 tasks from 14 families; merge source identities before splitting data.

The M2 completion has explicit authorization for a local commit only; no push, PR or tag.
Do not start SITL, resume historical batches, run T6, prepare r3, or rewrite old data.
Use PowerShell 7 and the project Conda environment. `Simulation` is a frozen archive;
the active project is `Simulation-dev/Multi-UAV SimpleGC`.
