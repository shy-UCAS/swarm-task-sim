# v0.8 佯动单段：运行说明（V8-18 起）

> 适用分支：`review/v08/V8-18-feint`。命令都在 `Multi-UAV SimpleGC` 目录、PowerShell 7、conda `llm` 环境下运行。
> 先设线程变量：`$env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'; $env:NUMEXPR_NUM_THREADS='1'`。
> 真实路径见同目录 [manifest.json](manifest.json)（`run_root`、`data_root`、`baselines`、`test_env`）。

## 1. 进程数

- 默认进程数仍为 **`DEFAULT_WORKERS = 24`**（`v08/runner/runtime_defaults.py`；V8-15 选定，V8-16/17/18 未改）。新入口 `tools/v08/run_feint_v18.py --workers` 缺省读同一常量。
- **单进程复跑固定 1**（`--stage rerun`），不随默认值变化。
- `--stage smoke --smoke-level chain` 只运行四个键，进程数取 min(workers, 4)；它不是新默认，不能替代固定 20 键快批。
- 同时运行大内存程序时，可按 V8-16 的建议改用 `--workers 16`；本项验收按 24 进程运行。

## 2. 入口与阶段

```powershell
$condaExe = 'C:\Users\shy\anaconda3\Scripts\conda.exe'
$devset   = 'F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-v08\docs\v08\V8-03\devset_v08.json'
$dataRoot = 'F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData'
$runRoot  = 'F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-06_V8-18_feint\run'
$cache    = Join-Path $runRoot 'cache'
# 预置测试（逐文件；缺环境变量的 skip 不算通过）
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-18 -p test_preset_numeric_v18.py -v
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-18 -p test_preset_local_geometry_v18.py -v
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-18 -p test_extra_local_v18.py -v
# 场景门禁预置测试（需 V8_18_DEVSET / V8_18_DATA_ROOT / V8_18_CACHE）
$env:V8_18_DEVSET = $devset; $env:V8_18_DATA_ROOT = $dataRoot; $env:V8_18_CACHE = $cache
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-18 -p test_preset_local_geometry_v18.py -v
# 三路对照门禁（裁定 1、3(b)；退出码 5 = exact / screened / 剪枝+screened 不一致）
& $condaExe run -n llm --no-capture-output python -B tools/v08/run_feint_v18.py --stage turn-gate --devset $devset --data-root $dataRoot --cache $cache --out (Join-Path $runRoot 'diagnostics\<新目录>') --workers 24
# 成本检查点（裁定 3(c)；前 5 族预建、按机数外推 40 族；> 45 分钟退出码 2）
& $condaExe run -n llm --no-capture-output python -B tools/v08/run_feint_v18.py --stage cost-check --devset $devset --data-root $dataRoot --cache $cache --out (Join-Path $runRoot 'diagnostics\<新目录>') --workers 24
# 集合诊断与单骨架 smoke（o17_d1/d4 与三个原型键）
& $condaExe run -n llm --no-capture-output python -B tools/v08/run_feint_v18.py --stage queries --devset $devset --data-root $dataRoot --cache $cache --out (Join-Path $runRoot 'diagnostics\<新目录>')
& $condaExe run -n llm --no-capture-output python -B tools/v08/run_feint_v18.py --stage smoke --smoke-level skeleton --devset $devset --data-root $dataRoot --cache $cache --out (Join-Path $runRoot 'out\smoke\<新目录>')
& $condaExe run -n llm --no-capture-output python -B tools/v08/run_feint_v18.py --stage smoke --smoke-level chain --devset $devset --data-root $dataRoot --cache $cache --out (Join-Path $runRoot 'out\smoke\<新目录>')
# 200 合同只骨架
& $condaExe run -n llm --no-capture-output python -B tools/v08/run_feint_v18.py --stage skeleton --devset $devset --data-root $dataRoot --cache $cache --out (Join-Path $runRoot 'out\skeleton\<新目录>') --workers 24
# 20 合同快批
& $condaExe run -n llm --no-capture-output python -B tools/v08/run_feint_v18.py --stage quick --devset $devset --data-root $dataRoot --cache $cache --out (Join-Path $runRoot 'out\quick\<新目录>') --workers 24
# 全量 200 + 多样性 100（7200 s 合作退出预算，仅防卡死）
& $condaExe run -n llm --no-capture-output python -B tools/v08/run_feint_v18.py --stage full --devset $devset --data-root $dataRoot --cache $cache --out $fullOut --workers 24
# 预登记 5 键单进程复跑（固定 1 进程，逐字节比较，排除清单 []）
& $condaExe run -n llm --no-capture-output python -B tools/v08/run_feint_v18.py --stage rerun --devset $devset --data-root $dataRoot --cache $cache --out $rerunOut --keys (Join-Path $fullOut 'rerun_keys.json') --compare-to $fullOut
```

这些命令**按检查点逐条执行**，不要写成失败后仍继续跑全量的无条件脚本。

退出码：0 完成且未触发；1 参数或路径错误；2 止损/成本检查点触发；3 未完成；4 三项 P0（保留违规、复跑不一致）；5 三路对照不一致。

## 3. 三意图字节门禁

`pwsh -File docs/v08/V8-18/run_gates.ps1 <phase>` 依次运行：监视 `run_separation_v15.py --mode production-quick`、过境 `run_transit_v16.py --stage quick`、突入 `run_intrusion_v17.py --stage quick`（均 24 进程），再由 `gate_compare.py` 分别与 `full_v14c`、`full_transit_r2`、V8-17 `full_r1` 逐合同比较递归文件集合与 bytes（排除清单 `[]`），结果写入 `part<phase>/gate_<intent>.json`。

## 4. 缓存

- 佯动可行格文件：`<cache>\feint_v18\<场景缓存键>\<目标>_<查询身份>.json`。身份版本 `v18-feint-cells-1`（掉头认证 `v18-feint-turn-1`），包含 intent、ctx 缓存身份、目标与全部设施几何、base 与 crossing 完整有序身份、按槽位序的偏移 `float.hex`、间距、L、l*、全部网格/界值、认证模式 `screened` 与剪枝开关。不复用 intrusion/transit 的结果。
- 预建（`prewarm_all(intent="feint")`）按族一个进程、按完整查询身份去重、原子落盘；已有文件先核对身份再使用，不覆盖。派发阶段 worker 只读，缺文件时在进程内计算、不写回，records 的 `chord_cache` 记 `cache_hits` / `cache_misses_computed`（合同目录外）。
