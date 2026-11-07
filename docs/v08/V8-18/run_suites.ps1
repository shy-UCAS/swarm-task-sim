# V8-18 回归套件：把 V8-17 run_suites.sh / run_v17_tests.sh 清单中的 Python 命令在 PowerShell 7 逐条执行（指令 1.3）。
# 每套写出命令、cwd、提交、环境与完整 unittest -v 输出。用法：pwsh -File run_suites.ps1 <日志文件> [-V17Artifacts]
param([Parameter(Mandatory = $true)][string]$Log, [switch]$V17Artifacts)
$ErrorActionPreference = 'Continue'
$R = 'F:\CASIA\Drone Swarm Situational Awareness Algorithm'
Set-Location "$R\Simulation-v08\Multi-UAV SimpleGC"
$env:OMP_NUM_THREADS = '1'; $env:OPENBLAS_NUM_THREADS = '1'; $env:MKL_NUM_THREADS = '1'; $env:NUMEXPR_NUM_THREADS = '1'
$conda = 'C:\Users\shy\anaconda3\Scripts\conda.exe'
$Log = [IO.Path]::GetFullPath($Log)
"# V8-18 回归套件（V8-17 清单，PowerShell 7 逐条执行） $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')" | Set-Content $Log -Encoding utf8
"# cwd=$(Get-Location)" | Add-Content $Log
"# commit=$(git rev-parse HEAD) dirty=$((git status --porcelain | Measure-Object -Line).Lines)" | Add-Content $Log
"# threads OMP=$env:OMP_NUM_THREADS OPENBLAS=$env:OPENBLAS_NUM_THREADS MKL=$env:MKL_NUM_THREADS NUMEXPR=$env:NUMEXPR_NUM_THREADS" | Add-Content $Log
function Run([string]$dir, [string]$pat, [hashtable]$envs = @{}) {
    $prefix = ($envs.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value) " }) -join ''
    "" | Add-Content $Log
    "## $prefix$conda run -n llm --no-capture-output python -B -m unittest discover -s $dir -p `"$pat`" -v" | Add-Content $Log
    $saved = @{}
    foreach ($k in $envs.Keys) { $saved[$k] = [Environment]::GetEnvironmentVariable($k); [Environment]::SetEnvironmentVariable($k, $envs[$k]) }
    $out = & $conda run -n llm --no-capture-output python -B -m unittest discover -s $dir -p $pat -v 2>&1
    $code = $LASTEXITCODE
    foreach ($k in $envs.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k]) }
    $out | ForEach-Object { "$_" } | Where-Object { $_ -notmatch 'UserWarning: A NumPy version|^  from scipy|^  import numpy' } | Add-Content $Log
    "exit=$code" | Add-Content $Log
}
Run tests/v08/V8-15 'test_preset_numeric_*.py'
Run tests/v08/V8-15 'test_preset_local_formation.py'
Run tests/v08/V8-15 'test_preset_local_injection.py'
Run tests/v08/V8-15 'test_preset_local_stress.py'
Run tests/v08/V8-15 'test_preset_local_defaults.py'
Run tests/v08/V8-15 'test_extra_*.py'
Run tests/v08/V8-16 'test_preset_numeric_v16.py'
Run tests/v08/V8-16 'test_preset_local_geometry_v16.py'
Run tests/v08/V8-16 'test_preset_local_revisit_v16.py'
Run tests/v08/V8-16 'test_extra_*.py'
Run tests/v08/V8-11 'test_*.py'
Run tests/v08/V8-12 'test_*.py'
Run tests/v08/V8-13 'test_preset_numeric_*.py'
Run tests/v08/V8-13 'test_extra_*.py'
Run tests/v08/V8-14 'test_preset_numeric_*.py'
Run tests/v08/V8-14 'test_extra_*.py'
Run tests/v08/V8-14 'test_preset_local_geometry.py'
Run tests/v08/V8-12 'test_*.py' @{ V8_12_DATA_ROOT = "$R\SwarmData" }
$v17 = @{ V8_17_DATA_ROOT = "$R\SwarmData"; V8_17_TEST_CACHE = "$R\_handoff\2026-11-06_V8-17_intrusion\run\cache";
          V8_17_DEVSET = "$R\Simulation-v08\docs\v08\V8-03\devset_v08.json";
          V8_17_MONITOR_BASELINE = "$R\_handoff\2026-11-04_V8-14_skeleton\out\full_v14c";
          V8_17_TRANSIT_BASELINE = "$R\_handoff\2026-11-05_V8-16_transit\run\out\full_transit_r2" }
Run tests/v08/V8-17 'test_preset_numeric_v17.py' $v17
Run tests/v08/V8-17 'test_preset_local_geometry_v17.py' $v17
Run tests/v08/V8-17 'test_extra_local_v17.py' $v17
"" | Add-Content $Log
"# end $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')" | Add-Content $Log
