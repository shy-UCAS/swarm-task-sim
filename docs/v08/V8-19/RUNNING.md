# V8-19 当前失败检查点复现

当前代码停在第2部分；不得据此文档启动骨架/快批/全量。完整生成CLI、两轮门禁和生产链尚未完成。

在`Multi-UAV SimpleGC`目录、PowerShell7、项目Conda llm环境中设置四个线程变量均为1，运行：

```powershell
$env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'; $env:NUMEXPR_NUM_THREADS='1'
$condaExe='C:\Users\shy\anaconda3\Scripts\conda.exe'
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-19 -p test_preset_numeric_v19.py -v
$env:PYTHONPATH=Join-Path (Get-Location).Path 'tests/v08/V8-19'
& $condaExe run -n llm --no-capture-output python -B -m unittest test_preset_local_geometry_v19.InterfacePreset.test_exact_control_indices_and_elimination test_preset_local_geometry_v19.InterfacePreset.test_outer_appends_after_merge_and_legacy_empty -v
& $condaExe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-19 -p test_extra_dwell_reference_v19.py -v
```

本轮结果依次8通过、2通过、自加3通过1失败。数值诊断脚本为`../docs/v08/V8-19/diagnose_part2_failure.py`，需要显式传一个全新输出JSON路径，拒绝覆盖原证据。原始stderr保留已有NumPy/SciPy版本提示，未安装升级依赖。

后续完成时仍须补充原Artifact验收索引和5键复跑命令；当前尚无合格输出可供它们验收，不能把缺环境变量的skip记通过。
