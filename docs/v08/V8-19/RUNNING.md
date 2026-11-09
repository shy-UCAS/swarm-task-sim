# V8-19 运行与复核

工作树为 `Simulation-v08`，仅使用审查分支 `review/v08/V8-19-close-observation`。历史检查点和修正见 REPORT；以下命令不得覆盖已有输出，每阶段检查通过后才进入下一阶段。完整产物9.3在两轮门禁、快批、全量和5键复跑齐全后执行；缺环境变量而跳过不算通过。

在 PowerShell 7 中设置环境：

```powershell
Set-Location -LiteralPath 'F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-v08\Multi-UAV SimpleGC'
$PSVersionTable.PSVersion
Get-Content -LiteralPath '.conda-env' # llm
$condaExe = 'C:\Users\shy\anaconda3\Scripts\conda.exe'
$env:OMP_NUM_THREADS = '1'
$env:OPENBLAS_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:NUMEXPR_NUM_THREADS = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$runRoot = 'F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-08_V8-19_close_observation\run'
$runner = '..\docs\v08\V8-19\run_stage.ps1'
```

快速测试各命令独立执行，检查退出码：

```powershell
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-19 -p test_preset_numeric_v19.py -v
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-19 -p test_preset_local_geometry_v19.py -v
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-19 -p test_extra_dwell_reference_v19.py -v
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-19 -p test_extra_selected_curve_v19.py -v
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-19 -p test_extra_chain_v19.py -v
```

27文件134项旧测试的命令、日志和所用脚本见 `part4_complete/part4_old_tests_r2/` 与 `part4_complete/run_old_tests_r2.py`。真实链路失败注入测试见 `part4_complete/part4_injection_r1.log`，原始测试运行目录位于 diagnostics；注入产物不进入固定20/200/100名单。复跑该测试须将 `V8_19_DATA_ROOT/V8_19_DEVSET/V8_19_CACHE/V8_19_CHAIN_TEST_OUT` 分别设为数据根、开发集、缓存根和全新诊断目录，否则测试明确跳过，不算通过。

四个旧意图门禁分别运行，合同比较原始文件bytes，排除清单[]。以下是第二轮命令，第一轮相同但 `-Phase 2`；原轮次已存在时改新轮次并保存全部比较证据：

```powershell
& '..\docs\v08\V8-19\run_old_intent_gate.ps1' -Intent monitoring -Phase 4 -Round owner_r1
& '..\docs\v08\V8-19\run_old_intent_gate.ps1' -Intent transit -Phase 4 -Round owner_r1
& '..\docs\v08\V8-19\run_old_intent_gate.ps1' -Intent intrusion -Phase 4 -Round owner_r1
& '..\docs\v08\V8-19\run_old_intent_gate.ps1' -Intent feint -Phase 4 -Round owner_r1
```

以下每条都是单独的检查点，不是一段允许忽略失败的批处理。每次24进程运行前后告知用户。`owner_r1`是新的示例轮次；预建和正式骨架分开计时，包装器分别在2700秒和1800秒止损，骨架限额不含预建。四键 smoke 默认1进程，另测最大实际编组/宽度键 o17_d1。

```powershell
& $runner -Stage smoke -Round owner_r1 -Workers 1
& $runner -Stage smoke -Round owner_max_r1 -Workers 1 -ContractKeys 'o17_d1'
& $runner -Stage prewarm -Round owner_r1 -Workers 24
$prewarm = Join-Path $runRoot 'out/prewarm_owner_r1/prewarm.json'
& $runner -Stage skeleton -Round owner_r1 -Workers 24 -PrewarmFrom $prewarm
& $runner -Stage quick -Round owner_r1 -Workers 24 -PrewarmFrom $prewarm
& $runner -Stage full -Round owner_r1 -Workers 24 -PrewarmFrom $prewarm
& $runner -Stage rerun -Round owner_r1 -Workers 1 -Keys (Join-Path $runRoot 'out/full_owner_r1/rerun_keys.json') -CompareTo (Join-Path $runRoot 'out/full_owner_r1')
```

包装器底层调用薄CLI `tools/v08/run_close_observation_v19.py`，参数 `--stage/--workers/--devset/--data-root/--cache/--out` 及 `--prewarm-from/--contract-keys/--keys/--compare-to` 全部写入 diagnostics/watchdog。预建只认证过境式弦集合，不构造全格驻留集合。`--prewarm-from`复用同一新意图生产缓存的已完成预建文档；四个旧意图仍沿其原路径。每个阶段自动写合同外 `disk_verification.json`，完整复算已保留轨迹和新增事件。

退出码：0完成且检查点未触发，1参数/路径错误，2止损，3未完成，4 P0。非零即停依赖后续，保存并推送失败版本。P0不得自行修复重跑。

结果齐全后独立产物预置：

```powershell
$env:V8_19_ACCEPTANCE = (Resolve-Path '..\docs\v08\V8-19\acceptance.json').Path
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-19 -p test_preset_local_artifacts_v19.py -v
```

仅推送审查分支，并核对远端SHA；不合并dev、不推main、不强制推送。两份 owner_rerun.json 保留未跟踪，不提交或删除。原始轨迹/缓存留本地run，Git保存报告、脚本、汇总和散列索引。
