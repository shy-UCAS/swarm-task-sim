# v0.8 佯动单段：运行说明（V8-18 起）

> 适用分支：`review/v08/V8-18-feint`。命令都在 `Multi-UAV SimpleGC` 目录、PowerShell 7、conda `llm` 环境下运行。
> 先设线程变量：`$env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'; $env:NUMEXPR_NUM_THREADS='1'`。
> 真实路径见同目录 [manifest.json](manifest.json)（`run_root`、`data_root`、`baselines`、`test_env`）。
> 当前按 2026-11-08 按需判空裁定执行：取消全格预建和成本外推；三键单进程快速骨架单键超过 15 分钟、正式 200 骨架整批墙钟超过 60 分钟均停下留证。

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
$fullOut = Join-Path $runRoot 'out/full_lazy_r1'
$rerunOut = Join-Path $runRoot 'out/rerun_lazy_r1'
$acceptance = Join-Path $runRoot 'diagnostics/<新acceptance索引>.json'
# 预置测试（逐文件；缺环境变量的 skip 不算通过）
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-18 -p test_preset_numeric_v18.py -v
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-18 -p test_preset_local_geometry_v18.py -v
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-18 -p test_extra_local_v18.py -v
# SceneGate 本轮依成本裁定不运行，以原24进程三路门禁替代；谓词未变，本轮不重跑turn-gate。
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


## 5. 本次运行与证据索引

按检查点逐项运行并已完成，生产源码固定8e22f06；各路径位于manifest的run_root下，均未覆盖旧目录：

| 步骤 | 输出 | 结果 |
|---|---|---|
| 共享变更后第二轮三意图门禁 | out/gates_lazy_r1 | 各20/20，排除[] |
| 1进程三键骨架 | out/smoke_lazy_r1_o01_d0、_o02_d0、_o11_d1 | 全成功，单键均<38秒 |
| 两边缘集合诊断 | out/queries_lazy_r1_o17_d1、_o17_d4 | 各10 probe；走9989/10167格 |
| 24进程200骨架 | out/skeleton_lazy_r1 | 200/200，墙钟2031.349秒<3600 |
| 24进程20快批 | out/quick_lazy_r1 | 20/20，无止损 |
| 24进程全量与多样性 | out/full_lazy_r1、其下diversity | 200/200＋100/100，检查点无触发 |
| 1进程固定5键复跑 | out/rerun_lazy_r1 | 5/5，105文件bytes全同 |
| 独立磁盘复核 | diagnostics/quick_disk_validation_r1.json、full_disk_validation_r1.json | 主/多样性全部，P0[] |
| 原ArtifactPreset | diagnostics/test_preset_local_artifacts_lazy_r1.log | 3/3通过 |
| 四意图/成员观测 | diagnostics/four_intent_lazy_r1、observables_paired_lazy_r1 | 200键/969成员，\(L=0\)字段问题在REPORT明示 |
| 最终冻结快照 | diagnostics/snapshot_end_lazy_r1.json、snapshot_compare_end_lazy_r1.json | all_frozen_ok=true |

骨架和全链路实际使用[run_bounded.ps1](run_bounded.ps1)，三意图使用[run_gates_lazy.ps1](run_gates_lazy.ps1)。守护每5秒看退出/P0/预算，只停止本次进程树；900秒用于三键快速骨架，正式200只骨架用整批3600秒；full原7200秒合作预算不变。目录名必须改成新值才能再次运行，不能覆盖本轮证据。各阶段具体argv、开始结束UTC/墙钟/退出码均在diagnostics对应目录watchdog.json内。

```powershell
# 从 Multi-UAV SimpleGC 目录运行。下列仅为对应阶段的命令格式，按检查点逐条执行。
$bounded = '../docs/v08/V8-18/run_bounded.ps1'
& $bounded -Stage smoke -Name '<新smoke目录>' -ContractKey o01_d0 -Workers 1 -LimitSeconds 900
& $bounded -Stage queries -Name '<新查询目录>' -ContractKey o17_d1 -Workers 1
& $bounded -Stage skeleton -Name '<新骨架目录>' -Workers 24 -LimitSeconds 3600
& $bounded -Stage quick -Name '<新快批目录>' -Workers 24
& $bounded -Stage full -Name '<新全量目录>' -Workers 24
& $bounded -Stage rerun -Name '<新复跑目录>' -Workers 1 -KeysPath (Join-Path $fullOut 'rerun_keys.json') -CompareTo $fullOut
# 每次 --out 必须是新文件，非零/P0/未完成即停止后续步骤。
& $condaExe run -n llm --no-capture-output python -B ../docs/v08/V8-18/validate_feint_disk.py --root (Join-Path $runRoot 'out/quick_lazy_r1') --stage quick --out (Join-Path $runRoot 'diagnostics/<新快批复核>.json')
& $condaExe run -n llm --no-capture-output python -B ../docs/v08/V8-18/validate_feint_disk.py --root $fullOut --stage full --include-diversity --out (Join-Path $runRoot 'diagnostics/<新全量复核>.json')
# 只改验收索引的第二轮路径，原预置文件/断言不动。
& $condaExe run -n llm --no-capture-output python -B ../docs/v08/V8-18/make_acceptance.py $acceptance --quick (Join-Path $runRoot 'out/quick_lazy_r1') --full $fullOut --rerun $rerunOut --phase4-root (Join-Path $runRoot 'out/gates_lazy_r1')
$env:V8_18_ACCEPTANCE = $acceptance
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-18 -p test_preset_local_artifacts_v18.py -v
```

`validate_feint_disk.py`返回4为保留P0、3为资料不完整或字段扫描不过、0为该次磁盘复核通过。该工具不替代原Artifact三项测试。27通过、SceneGate1项未执行/已裁定替代，详见REPORT；不将语法检查算作测试。

## 6. 只读分析与最终快照

下列是本轮使用的输入路径。输出使用新目录；同名目录不允许覆盖。四意图分析不运行生成器：

```powershell
$base = 'F:\CASIA\Drone Swarm Situational Awareness Algorithm'
$handoff = Join-Path $base '_handoff'
$analyzeArgs = @(
  '--out', (Join-Path $runRoot 'diagnostics/<新四意图目录>'),
  '--monitor-skeleton', (Join-Path $handoff '2026-11-04_V8-14_skeleton/out/skeleton_v14b/records.json'),
  '--transit-skeleton', (Join-Path $handoff '2026-11-05_V8-16_transit/run/out/skeleton_transit_r3/records.json'),
  '--intrusion-skeleton', (Join-Path $handoff '2026-11-06_V8-17_intrusion/run/out/skeleton/skeleton_r1/records.json'),
  '--feint-skeleton', (Join-Path $runRoot 'out/skeleton_lazy_r1/records.json'),
  '--monitor-full', (Join-Path $handoff '2026-11-04_V8-14_skeleton/out/full_v14c/records.json'),
  '--transit-full', (Join-Path $handoff '2026-11-05_V8-16_transit/run/out/full_transit_r2/records.json'),
  '--intrusion-full', (Join-Path $handoff '2026-11-06_V8-17_intrusion/run/out/full/full_r1/records.json'),
  '--feint-full', $fullOut
)
& $condaExe run -n llm --no-capture-output python -B tools/v08/analyze_feint_v18.py @analyzeArgs
& $condaExe run -n llm --no-capture-output python -B ../docs/v08/V8-18/snapshot.py (Join-Path $runRoot 'diagnostics/<新末快照>.json') --baseline
& $condaExe run -n llm --no-capture-output python -B ../docs/v08/V8-18/snapshot_compare.py ../docs/v08/V8-18/snapshot_part1.json (Join-Path $runRoot 'diagnostics/<新末快照>.json') (Join-Path $runRoot 'diagnostics/<新快照对照>.json')
```

[collect_lazy_evidence.py](collect_lazy_evidence.py)补充骨架完整折线精确protected距离与排列统计；[validation_metrics.py](validation_metrics.py)从原独立复核JSON的非None数字取min，纠正PowerShell摘要聚合；[export_feint_observables.py](export_feint_observables.py)写两张失败表和同成员观测配对。这三个单次诊断脚本含本轮固定路径；再次导出时先另设全新输出路径，不可直接覆盖。\(L=0\)独立配对的None和原合同raw字段区别见REPORT，未改生产合同。

最终155缓存与源文件保留检查见[preserve_final.ps1](preserve_final.ps1)及part8；初次比较时间戳须用PowerShell7的`ConvertFrom-Json -DateKind String`，避免ISO字符串自动转DateTime造成假差异。最终回执`run/diagnostics/delivery_end_lazy_r1.json`在最后一次提交/推送后写入完整本地与远端SHA及唯一owner未提交项。只推指定review分支。
