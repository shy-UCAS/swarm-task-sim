# V8-19 当前失败检查点的复现

当前停在第3部分快速检查。第2部分第一轮四意图门禁80/80通过；第3部分新增自加测试1项失败，相关旧回归2项error。源代码和失败断言均保留，`part3_checkpoint/PROPOSED_*.patch`只是审查建议，没有应用或测试。完整生成CLI、第4–8部分验收和acceptance.json尚未完成。

使用PowerShell7，代码目录为`F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-v08\Multi-UAV SimpleGC`。读取`.conda-env`，本项目为llm；不安装或升级包。

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

以下三份检查当前全部通过（8/3/5）。每条独立执行，检查退出码。

```powershell
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-19 -p test_preset_numeric_v19.py -v
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-19 -p test_preset_local_geometry_v19.py -v
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-19 -p test_extra_dwell_reference_v19.py -v
```

下条复现本次自加检查点的4通过、1失败；失败是整段经过圆心的解析夹具被错误预期为名义预筛全通过。预筛实际最大层3，只有`max_target_layer_one`条件为False。按规则暂停依赖批次，不能应用建议后自行重跑。

```powershell
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-19 -p test_extra_selected_curve_v19.py -v
```

旧回归两项error的原日志和所有27文件结果在`part3_checkpoint/part3_old_tests_r1/`及`part3_checkpoint/part3_old_tests_remainder_r1/`。错误来自旧桩没有`intent`属性；旧文件没有修改。完整命令、所需输入变量及真实日志见同目录的`run_related_tests_part3*.py`。这些脚本的证据输出路径要求不存在，不能覆盖本轮原始目录。

产物预置9.3按用户澄清留待相应结果齐全后运行。届时须生成真实`acceptance.json`，完整执行三项；此前setUpClass跳过不是通过。以下是指令指定形式，当前文件缺失，尚不能执行：

```powershell
$env:V8_19_ACCEPTANCE = (Resolve-Path '..\docs\v08\V8-19\acceptance.json').Path
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-19 -p test_preset_local_artifacts_v19.py -v
```

完整生成、200骨架、20快批、200+100全量及5键复跑均未启动；第2轮旧意图门禁须在最终共享代码完成后运行。运行根为`F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-08_V8-19_close_observation\run`，每次使用新输出目录，合同比较排除[]。24进程运行前后分别通知用户；当前没有待运行的24进程任务。
