# v0.8 突入单段：运行说明（V8-17 起）

> 适用分支：`review/v08/V8-17-intrusion`。命令都在 `Multi-UAV SimpleGC` 目录、PowerShell 7、conda `llm` 环境下运行。
> 先设线程变量：`$env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'; $env:NUMEXPR_NUM_THREADS='1'`。
> 真实路径见同目录 [manifest.json](manifest.json)（`run_root`、`data_root`、`baselines`、`test_env`）。

## 1. 进程数

- 默认进程数仍为 **`DEFAULT_WORKERS = 24`**（`v08/runner/runtime_defaults.py`；V8-15 选定，V8-16/V8-17 未改）。新入口 `tools/v08/run_intrusion_v17.py --workers` 缺省读同一常量。
- **单进程复跑固定 1**（`--stage rerun`），不随默认值变化。
- `--stage smoke --smoke-level chain` 只运行 U C.3 四个键，进程数取 min(workers, 4)。它不是新默认，也不能替代固定 20 键快批。
- 同时运行大内存程序时，可以按 V8-16 的建议改用 `--workers 16`；本项验收按 24 进程运行。

## 2. 入口与阶段

```powershell
$condaExe = 'C:\Users\shy\anaconda3\Scripts\conda.exe'
$devset   = 'F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-v08\docs\v08\V8-03\devset_v08.json'
$dataRoot = 'F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData'
$runRoot  = 'F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-06_V8-17_intrusion\run'
$cache    = Join-Path $runRoot 'cache'
# 预置测试（逐文件；缺环境变量的 skip 不算通过）
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-17 -p 'test_preset_numeric_v17.py' -v
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-17 -p 'test_preset_local_geometry_v17.py' -v
# 组合一致性门禁（指令 5.1；45 组 + 横排/梯形自加覆盖；退出码 5 = 组合与直算不一致）
& $condaExe run -n llm --no-capture-output python -B tools/v08/run_intrusion_v17.py --stage chord-gate --devset $devset --data-root $dataRoot --cache $cache --out (Join-Path $runRoot 'diagnostics\<新目录>') --workers 24
# 证书/边缘例/四键单格查询
& $condaExe run -n llm --no-capture-output python -B tools/v08/run_intrusion_v17.py --stage queries --devset $devset --data-root $dataRoot --cache $cache --out (Join-Path $runRoot 'diagnostics\<新目录>')
# U C.3 四键 smoke（骨架或全链路）
& $condaExe run -n llm --no-capture-output python -B tools/v08/run_intrusion_v17.py --stage smoke --smoke-level skeleton --devset $devset --data-root $dataRoot --cache $cache --out (Join-Path $runRoot 'out\smoke\<新目录>')
& $condaExe run -n llm --no-capture-output python -B tools/v08/run_intrusion_v17.py --stage smoke --smoke-level chain --devset $devset --data-root $dataRoot --cache $cache --out (Join-Path $runRoot 'out\smoke\<新目录>')
# 200 合同只骨架（按族预建 → 24 进程派发）
& $condaExe run -n llm --no-capture-output python -B tools/v08/run_intrusion_v17.py --stage skeleton --devset $devset --data-root $dataRoot --cache $cache --out (Join-Path $runRoot 'out\skeleton\<新目录>') --workers 24
# 20 合同快批（select_quick 既有名单）
& $condaExe run -n llm --no-capture-output python -B tools/v08/run_intrusion_v17.py --stage quick --devset $devset --data-root $dataRoot --cache $cache --out (Join-Path $runRoot 'out\quick\<新目录>') --workers 24
# 全量 200 + 多样性 100（7200 s 合作退出预算，仅防卡死）
& $condaExe run -n llm --no-capture-output python -B tools/v08/run_intrusion_v17.py --stage full --devset $devset --data-root $dataRoot --cache $cache --out $fullOut --workers 24
# 预登记 5 键单进程复跑（固定 1 进程，逐字节比较，排除清单 []）
& $condaExe run -n llm --no-capture-output python -B tools/v08/run_intrusion_v17.py --stage rerun --devset $devset --data-root $dataRoot --cache $cache --out $rerunOut --keys (Join-Path $fullOut 'rerun_keys.json') --compare-to $fullOut
```

这些命令**按检查点逐条执行**，不要写成失败后仍继续跑全量的无条件脚本。

退出码：
- 0：完成且未触发；
- 2：止损检查点触发；
- 3：未完成；
- 4：保留 P0 违规，或复跑/门禁字节不一致；
- 1：参数或路径错误；
- 5：组合加速对照不一致（加速正确性前提，不冒充保留数据 P0）。

## 3. 两意图字节门禁

`bash docs/v08/V8-17/run_gates.sh <phase>` 依次运行两项：
- 监视：`run_separation_v15.py --mode production-quick`；
- 过境：`run_transit_v16.py --stage quick`。

两者都是 24 进程。之后 `gate_compare.py` 与 `full_v14c`、`full_transit_r2` 逐合同比较递归文件集合与 bytes（排除清单 `[]`），结果写入 `part<phase>/gate_<intent>.json`。四条门禁记录汇总在 [regression_gates.json](regression_gates.json)，作为预置测试 `V8_17_REGRESSION_MANIFEST` 的输入。

## 4. 缓存

- 突入弦集合在派发前按族预建，路径为 `<cache>\intrusion_v17\<场景缓存键>\<目标>_<查询身份>.json`。
- 身份版本为 `v17-intrusion-chords-1`，包含 intent、完整约束身份、槽位偏移 float.hex、σ 网格和全部常数。不复用 `transit_v16` 的弦集合。
- 预建先读已有文件；只在文件缺失时计算并写入，已有文件不覆盖。派发阶段的 worker 只读，缺文件时在进程内计算、不写回，summary 的 `chord_cache` 记 `cache_hits` / `cache_misses_computed`。
- 运行前圆形证书成立的合同（例如 o34_d3）不发起 probe，也不预建。
