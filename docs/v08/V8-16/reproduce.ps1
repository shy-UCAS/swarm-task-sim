# V8-16 复现脚本（PowerShell 7）。路径全部从同目录 manifest.json 的 reproduce 段读取；先打印并校验，缺前提返回 3 且不运行。
#   pwsh -File reproduce.ps1 -Scope tests                          # 预置 + 自加 + 旧套件；不启动任何批次
#   pwsh -File reproduce.ps1 -Scope quick       -Out <不存在的新根>  # 监视 20 字节门禁 + 过境只骨架 200 + 过境快批 20
#   pwsh -File reproduce.ps1 -Scope acceptance  -Out <不存在的新根>  # 过境全量 200 + 多样性 100，再 5 键单进程复跑
#   pwsh -File reproduce.ps1 -Scope diagnostics -Out <不存在的新根>  # 198 时长、两低速诊断、重访三方对照
param(
    [Parameter(Mandatory = $true)][ValidateSet('tests', 'quick', 'acceptance', 'diagnostics')][string]$Scope,
    [string]$Out
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$manifestPath = Join-Path $here 'manifest.json'
if (-not (Test-Path $manifestPath)) { [Console]::Error.WriteLine("缺少 $manifestPath：未运行"); exit 3 }
$m = (Get-Content $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json).reproduce
foreach ($k in 'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS') { Set-Item -Path "env:$k" -Value '1' }
$m.PSObject.Properties | ForEach-Object { Write-Host ("{0,-18} = {1}" -f $_.Name, $_.Value) }
foreach ($p in $m.project_dir, $m.conda_exe, $m.data_root, $m.cache, $m.monitor_baseline, $m.devset, $m.worker_selection, $m.speed_cases) {
    if (-not (Test-Path $p)) { [Console]::Error.WriteLine("前提路径不存在：$p（未运行）"); exit 3 }
}
$conda = $m.conda_exe
function Py([string[]]$a) { & $conda run -n $m.conda_env --no-capture-output python -B @a; return $LASTEXITCODE }
Push-Location $m.project_dir
try {
    if ($Scope -eq 'tests') {
        $env:V8_15_WORKER_SELECTION = $m.worker_selection
        $env:V8_16_DATA_ROOT = $m.data_root; $env:V8_16_TEST_CACHE = $m.cache; $env:V8_16_DEVSET = $m.devset
        $suites = @(@('tests/v08/V8-16', 'test_preset_numeric_v16.py'), @('tests/v08/V8-16', 'test_preset_local_geometry_v16.py'),
            @('tests/v08/V8-16', 'test_preset_local_revisit_v16.py'), @('tests/v08/V8-16', 'test_extra_*.py'),
            @('tests/v08/V8-15', 'test_preset_*.py'), @('tests/v08/V8-11', 'test_*.py'),
            @('tests/v08/V8-13', 'test_preset_numeric_*.py'), @('tests/v08/V8-13', 'test_extra_*.py'),
            @('tests/v08/V8-14', 'test_preset_numeric_*.py'), @('tests/v08/V8-14', 'test_extra_*.py'),
            @('tests/v08/V8-14', 'test_preset_local_geometry.py'))
        $fail = 0
        foreach ($s in $suites) {
            Write-Host "## unittest discover -s $($s[0]) -p $($s[1])"
            if ((Py @('-m', 'unittest', 'discover', '-s', $s[0], '-p', $s[1], '-v')) -ne 0) { $fail++ }
        }
        Write-Host "失败套件数：$fail（V8-12 未列入：已知 frechet 历史失败，见 REPORT 第 1、9 节；artifacts 预置需批次输出，见 -Scope quick）"
        exit ([int]($fail -ne 0))
    }
    if (-not $Out) { [Console]::Error.WriteLine("-Scope $Scope 需要 -Out <不存在的新根>（未运行）"); exit 3 }
    if (Test-Path $Out) { [Console]::Error.WriteLine("输出根已存在：$Out（未运行，不覆盖）"); exit 3 }
    New-Item -ItemType Directory $Out | Out-Null
    $base = @('--devset', $m.devset, '--data-root', $m.data_root, '--cache', $m.cache)
    if ($Scope -eq 'quick') {
        $c1 = Py (@('tools/v08/run_separation_v15.py', '--mode', 'production-quick', '--baseline', $m.monitor_baseline, '--out', "$Out/monitor_regression", '--workers', '24') + $base)
        $c2 = Py (@('tools/v08/run_transit_v16.py', '--stage', 'skeleton', '--out', "$Out/skeleton_transit") + $base)
        if ($c2 -ne 0) { Write-Host "骨架检查点未通过或未完成（$c2），不启动快批"; exit $c2 }
        $c3 = Py (@('tools/v08/run_transit_v16.py', '--stage', 'quick', '--out', "$Out/quick_transit") + $base)
        Write-Host "退出码：监视门禁 $c1，骨架 $c2，快批 $c3"
        exit ([int](($c1 -ne 0) -or ($c3 -ne 0)))
    }
    if ($Scope -eq 'acceptance') {
        $c1 = Py (@('tools/v08/run_transit_v16.py', '--stage', 'full', '--out', "$Out/full_transit") + $base)
        $c2 = Py (@('tools/v08/run_transit_v16.py', '--stage', 'rerun', '--out', "$Out/rerun_transit", '--workers', '1', '--keys', "$Out/full_transit/rerun_keys.json", '--compare-to', "$Out/full_transit") + $base)
        Write-Host "退出码：全量 $c1，复跑 $c2"
        exit ([int](($c1 -ne 0) -or ($c2 -ne 0)))
    }
    $c1 = Py (@('tools/v08/analyze_transit_v16.py', '--mode', 'monitor-durations', '--baseline', $m.monitor_baseline, '--out', "$Out/monitor_durations") + $base)
    $c2 = Py (@('tools/v08/diagnose_low_speed_v16.py', '--baseline', $m.monitor_baseline, '--speed-cases', $m.speed_cases, '--out', "$Out/low_speed") + $base)
    $c3 = Py @('tools/v08/revisit_equivalence_v16.py', '--mode', 'quick20', '--baseline', $m.monitor_baseline, '--devset', $m.devset, '--data-root', $m.data_root, '--cache', $m.cache, '--keys', $m.manifest, '--out', "$Out/revisit_quick20")
    $c4 = Py @('tools/v08/revisit_equivalence_v16.py', '--mode', 'v811', '--data-root', $m.data_root, '--out', "$Out/revisit_v811")
    Write-Host "退出码：时长 $c1，低速 $c2，重访快批 $c3，重访 V8-11 $c4"
    exit ([int](($c1 -ne 0) -or ($c2 -ne 0) -or ($c3 -ne 0) -or ($c4 -ne 0)))
}
finally { Pop-Location }
