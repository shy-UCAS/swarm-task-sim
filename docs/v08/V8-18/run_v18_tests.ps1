# V8-18 新测试：预置三文件逐个运行（缺环境变量的 skip 在报告写"未执行"）+ 自加测试。用法：pwsh -File run_v18_tests.ps1 <日志> [-Scene] [-Artifacts]
# -Scene 设 V8_18_DEVSET/DATA_ROOT/CACHE 运行场景门禁；-Artifacts 需先设 V8_18_ACCEPTANCE。
param([Parameter(Mandatory = $true)][string]$Log, [switch]$Scene, [switch]$Artifacts)
$R = 'F:\CASIA\Drone Swarm Situational Awareness Algorithm'
Set-Location "$R\Simulation-v08\Multi-UAV SimpleGC"
$env:OMP_NUM_THREADS = '1'; $env:OPENBLAS_NUM_THREADS = '1'; $env:MKL_NUM_THREADS = '1'; $env:NUMEXPR_NUM_THREADS = '1'
$conda = 'C:\Users\shy\anaconda3\Scripts\conda.exe'
$Log = [IO.Path]::GetFullPath($Log)
"# V8-18 新测试 $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')" | Set-Content $Log -Encoding utf8
"# commit=$(git rev-parse HEAD) dirty=$((git status --porcelain | Measure-Object -Line).Lines) V8_18_ACCEPTANCE=$env:V8_18_ACCEPTANCE" | Add-Content $Log
if ($Scene) { $env:V8_18_DEVSET = "$R\Simulation-v08\docs\v08\V8-03\devset_v08.json"; $env:V8_18_DATA_ROOT = "$R\SwarmData"; $env:V8_18_CACHE = "$R\_handoff\2026-11-06_V8-18_feint\run\cache" }
else { Remove-Item Env:V8_18_DEVSET -ErrorAction SilentlyContinue }
function Run([string]$pat) {
    "" | Add-Content $Log
    "## $conda run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-18 -p `"$pat`" -v" | Add-Content $Log
    "sha256 $((Get-FileHash "tests/v08/V8-18/$pat").Hash.ToLower())" | Add-Content $Log
    $out = & $conda run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-18 -p $pat -v 2>&1
    $code = $LASTEXITCODE
    $out | ForEach-Object { "$_" } | Where-Object { $_ -notmatch 'UserWarning: A NumPy version|^  from scipy|^  import numpy' } | Add-Content $Log
    "exit=$code" | Add-Content $Log
}
Run 'test_preset_numeric_v18.py'
Run 'test_preset_local_geometry_v18.py'
if ($Artifacts) { Run 'test_preset_local_artifacts_v18.py' }
Run 'test_extra_local_v18.py'
"" | Add-Content $Log
"# end $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')" | Add-Content $Log
