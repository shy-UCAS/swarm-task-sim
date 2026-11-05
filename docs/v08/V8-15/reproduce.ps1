# V8-15 复现脚本（PowerShell 7）。不隐式执行 full / diversity。
#   pwsh -File reproduce.ps1 -Scope tests
#   pwsh -File reproduce.ps1 -Scope quick -Out "<不存在的新目录>"
# 路径全部从同目录 manifest.json 读取；先打印解析后的路径，缺前提时给出未运行原因并返回 3。
param(
    [Parameter(Mandatory = $true)][ValidateSet('tests', 'quick')][string]$Scope,
    [string]$Out
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$manifestPath = Join-Path $here 'manifest.json'
if (-not (Test-Path $manifestPath)) { [Console]::Error.WriteLine("缺少 $manifestPath：未运行"); exit 3 }
$m = Get-Content $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json
$proj = $m.project_dir
$conda = $m.conda_exe
foreach ($k in 'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS') {
    Set-Item -Path "env:$k" -Value '1'
}
Write-Host "project_dir      = $proj"
Write-Host "conda            = $conda (env $($m.conda_env))"
Write-Host "data_root        = $($m.data_root)"
Write-Host "cache            = $($m.cache)"
Write-Host "baseline         = $($m.baseline)"
Write-Host "devset           = $($m.devset)"
Write-Host "worker_selection = $($m.worker_selection)"
foreach ($p in $proj, $conda, $m.data_root, $m.cache, $m.baseline, $m.devset) {
    if (-not (Test-Path $p)) { [Console]::Error.WriteLine("前提路径不存在：$p（未运行）"); exit 3 }
}
Push-Location $proj
try {
    if ($Scope -eq 'tests') {
        $env:V8_15_WORKER_SELECTION = $m.worker_selection
        $suites = @(
            @('tests/v08/V8-15', 'test_preset_numeric_*.py'),
            @('tests/v08/V8-15', 'test_preset_local_formation.py'),
            @('tests/v08/V8-15', 'test_preset_local_injection.py'),
            @('tests/v08/V8-15', 'test_preset_local_stress.py'),
            @('tests/v08/V8-15', 'test_preset_local_defaults.py'),
            @('tests/v08/V8-11', 'test_*.py'),
            @('tests/v08/V8-13', 'test_preset_numeric_*.py'),
            @('tests/v08/V8-13', 'test_extra_*.py'),
            @('tests/v08/V8-14', 'test_preset_numeric_*.py'),
            @('tests/v08/V8-14', 'test_extra_*.py'),
            @('tests/v08/V8-14', 'test_preset_local_geometry.py')
        )
        $fail = 0
        foreach ($s in $suites) {
            Write-Host "## unittest discover -s $($s[0]) -p $($s[1])"
            & $conda run -n $m.conda_env --no-capture-output python -B -m unittest discover -s $s[0] -p $s[1] -v
            if ($LASTEXITCODE -ne 0) { $fail++ }
        }
        Write-Host "失败套件数：$fail（V8-12 未列入：其 2 项已知失败见 REPORT 第 2.4 节）"
        exit ([int]($fail -ne 0))
    }
    if (-not $Out) { [Console]::Error.WriteLine('-Scope quick 需要 -Out <不存在的新目录>（未运行）'); exit 3 }
    if (Test-Path $Out) { [Console]::Error.WriteLine("输出目录已存在：$Out（未运行，不覆盖）"); exit 3 }
    Write-Host "out              = $Out"
    & $conda run -n $m.conda_env --no-capture-output python -B tools/v08/run_separation_v15.py --mode production-quick `
        --baseline $m.baseline --devset $m.devset --data-root $m.data_root --cache $m.cache --out $Out
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
