# V8-21 运行登记

工作树：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-v08`，分支 `review/v08/V8-21-detour`（基线 `4418668`）。
代码工作目录：`Multi-UAV SimpleGC`。解释器：`C:\Users\shy\anaconda3\envs\llm\python.exe -B`（项目 `.conda-env` = llm）。
四个线程变量 `OMP_NUM_THREADS/OPENBLAS_NUM_THREADS/MKL_NUM_THREADS/NUMEXPR_NUM_THREADS` = 1，`PYTHONDONTWRITEBYTECODE=1`。
正式批次 24 进程（`runtime_defaults.DEFAULT_WORKERS`），复跑 1 进程。PowerShell 7.6.9。

- 开发集：`Simulation-v08\docs\v08\V8-03\devset_v08.json`
- 只读数据根：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData`
- 运行根（合同外）：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-10_V8-21_detour\run\`
- 缓存：运行根 `cache\`，由 V8-22 运行缓存原样复制（只加速，不进入合同）；迂回新几何的原始距离场由 `--stage prewarm` 单族单进程写入。
- pytest：llm 环境没有 pytest，沿用 V8-22 的做法，以 `PYTHONPATH=<V8-22 run\test_runtime>`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` 调用，不在 llm 安装任何包。
- 资源监控：本目录 `monitor_resources.ps1`（V8-20 原样），输出 `run\system_monitor\<名>`，写 `stop.request` 停止。

## 命令（每步全新输出目录）

```text
python -B ../docs/v08/V8-21/part1_snapshot.py r2
python -B ../docs/v08/V8-21/run_old_intent_gate.py 2 r1          # 第一道门禁：六意图 × 20
python -B -m unittest discover -s tests/v08/V8-21 -p test_preset_numeric_v21.py -v
python -B -m unittest discover -s tests/v08/V8-21 -p test_preset_local_v21.py -v
python -B -m unittest discover -s tests/v08/V8-21 -p test_preset_ruling_v21.py -v
python -B -m unittest discover -s tests/v08/V8-21 -p test_extra_v21.py -v
python -B tools/v08/run_detour_v21.py --stage prewarm  --devset <devset> --data-root <data> --cache <cache> --out <run>/prewarm/r1 --workers 24
python -B tools/v08/run_detour_v21.py --stage smoke    --devset <devset> --data-root <data> --cache <cache> --out <run>/smoke/r1 --workers 1
python -B ../docs/v08/V8-21/run_old_intent_gate.py 4 r1          # 第二道门禁
python -B tools/v08/run_detour_v21.py --stage skeleton --prewarm-from <run>/prewarm/r1/prewarm.json ... --out <run>/skeleton/r1 --workers 24
python -B tools/v08/run_detour_v21.py --stage quick    --prewarm-from ... --out <run>/quick/r1 --workers 24
python -B tools/v08/run_detour_v21.py --stage full     --prewarm-from ... --out <run>/full/r1 --workers 24
python -B tools/v08/run_detour_v21.py --stage rerun    --keys <run>/full/r1/rerun_keys.json --compare-to <run>/full/r1 ... --out <run>/rerun/r1 --workers 1
python -B ../docs/v08/V8-21/part7_analysis.py <run>/full/r1 <run>/pairing/r1
python -B tools/v08/analyze_detour_sweep_v21.py --repo . --devset <devset> --data-root <data> --candidate-config configs/v08/criteria_detour_candidate.json --run monitoring=... (七个主批) --out <run>/sweep/r1 --workers 24
set V8_21_ACCEPTANCE=docs/v08/V8-21/acceptance.json ; python -B -m unittest discover -s tests/v08/V8-21 -p test_preset_artifacts_v21.py -v
```

实际执行的完整 argv、起止时间与结果以 REPORT 及运行根各阶段目录为准。


## 只骨架修复运行补记

固定基点b70d1b9，按11-11最新六条修复裁定。外置工具、完整命令/日志及R0–R2证据在run/repair_r1；R1完整预演preflight_r1，正式只骨架将用run/skeleton/r2。额外PYTHONUTF8=1仅统一日志编码，四线程变量/24或1worker及所有业务配置不变。
