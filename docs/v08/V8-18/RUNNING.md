# v0.8 佯动单段：运行说明（V8-18 起）

> 适用分支：`review/v08/V8-18-feint`。命令都在 `Multi-UAV SimpleGC` 目录、PowerShell 7、conda `llm` 环境下运行。
> 先设线程变量：`$env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'; $env:NUMEXPR_NUM_THREADS='1'`。
> 真实路径见同目录 [manifest.json](manifest.json)（`run_root`、`data_root`、`baselines`、`test_env`）。
> 当前按 2026-11-08 按需判空裁定执行：取消全格预建和成本外推；单合同骨架超过 15 分钟、200 骨架墙钟超过 60 分钟均停下留证。

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
# 按需判空自加测试（真实 1/2 进程对照需全新证据目录）
$env:V8_18_LAZY_TEST_OUT = Join-Path $runRoot 'diagnostics\<新的测试目录>'
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-18 -p test_extra_lazy_v18.py -v
# 单进程：骨架 smoke 默认 o01_d0/o02_d0/o11_d1；诊断默认 o17_d1/d4。
# 可用 --contract-keys o01_d0 单键运行，以分别监视 15 分钟上限。
& $condaExe run -n llm --no-capture-output python -B tools/v08/run_feint_v18.py --stage smoke --smoke-level skeleton --devset $devset --data-root $dataRoot --cache $cache --out (Join-Path $runRoot 'out\smoke\<新目录>') --workers 1
& $condaExe run -n llm --no-capture-output python -B tools/v08/run_feint_v18.py --stage queries --devset $devset --data-root $dataRoot --cache $cache --out (Join-Path $runRoot 'diagnostics\<新目录>') --workers 1
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

- 旧 `<cache>\feint_v18` 的 29 族完成证据原样保留（实际共 155 个查询文件），生产不再读写。
- `prewarm_all(intent="feint")` 只预热既有距离场并登记人数，不调用格存在性检查。廉价入口表缓存与单车道缓存继续使用。
- 每个 probe 的 shape 排列取首个非空格；确定性存在性结果只在当前合同内存中复用。缓存冷热不改变 RNG 消耗、谓词或合同字节。`cache_hits/cache_misses_computed` 现在表示该内存 memo 的命中/首次判定，只进合同目录外。
- 逐 probe 的完整走格下标、计时与认证计数写入目录外 `telemetry`；合同内仅保存确定性候选数、走格数和非空位置。
