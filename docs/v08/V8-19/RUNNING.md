# V8-19 当前检查点复现

当前源码的两项获准修正提交为`bb7a6ce9d7a523549454ae92cb19bab4a5afa5f1`。修正后的选点6项、独立16项、相关旧测试134项全部通过；随后真实几何审计首键因新LP白名单误将`max_residual`字典当标量而停止。未应用修复，未重跑失败审计。完整CLI和第4–8部分验收尚未完成。

使用PowerShell7，读取项目`.conda-env`（llm），四线程变量设1。不安装或升级包。

```powershell
Set-Location -LiteralPath 'F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-v08\Multi-UAV SimpleGC'
$PSVersionTable.PSVersion
Get-Content -LiteralPath '.conda-env'
$condaExe = 'C:\Users\shy\anaconda3\Scripts\conda.exe'
$env:OMP_NUM_THREADS = '1'
$env:OPENBLAS_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:NUMEXPR_NUM_THREADS = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
```

以下检查本轮为8/8、3/3、5/5、6/6通过。每条独立执行并检查退出码。

```powershell
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-19 -p test_preset_numeric_v19.py -v
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-19 -p test_preset_local_geometry_v19.py -v
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-19 -p test_extra_dwell_reference_v19.py -v
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-19 -p test_extra_selected_curve_v19.py -v
```

本轮27文件134项旧回归的全部命令、环境和日志在`part3_lp_checkpoint/run_old_tests_r2.py`及`part3_lp_checkpoint/part3_old_tests_r2/`。旧SceneGate沿用已接受替代，其他实际执行项无跳过；脚本输出目录须为全新路径，不得覆盖本轮原始目录。

当前LP问题可以只调用纯投影函数复现，不必重新构造几何。下条预期抛`ValueError`，不是通过测试；它不会写文件或运行优化/仿真。

```powershell
& $condaExe run -n llm --no-capture-output python -B -c 'from v08.motion.intents.close_observation import project, LP; project({"max_residual":{"slope":0.0,"curvature_per_m":0.0,"corridor_m":0.0}},LP,"plan.proposal.lp")'
```

`part3_lp_checkpoint/PROPOSED_LP_RESIDUAL_SCHEMA.patch`仅为未应用的修正与回归测试建议。完整真实几何审计脚本和首轮失败在`part3_lp_checkpoint/audit_geometry_cache.py`、`part3_geometry_rng_r1/`，后续恢复须使用新轮次输出目录。缓存冷/热/1对2进程及最大查询试测未运行；身份枚举178项仅为诊断，不是预建。

产物预置9.3按用户澄清留待相应结果齐全后完整执行。当前acceptance.json尚不存在，历史setUpClass跳过不算通过。后续指定形式如下，当前不可执行：

```powershell
$env:V8_19_ACCEPTANCE = (Resolve-Path '..\docs\v08\V8-19\acceptance.json').Path
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-19 -p test_preset_local_artifacts_v19.py -v
```

新意图200骨架、20快批、200+100全量和5键复跑均未启动；完整CLI尚未实现。第二轮四意图门禁须在全部共享修改完成后运行，第一轮80/80不覆盖之后代码。24进程运行前后通知用户；当前没有运行中的24进程任务。运行根为`F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-08_V8-19_close_observation\run`；每轮新目录，合同比较排除[]。预建超过2700秒停止，正式200骨架派发超过1800秒停止。
