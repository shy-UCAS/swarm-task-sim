param([ValidateSet('r1','r2')][string]$Round='r1')
$ErrorActionPreference='Stop'
$base='F:\CASIA\Drone Swarm Situational Awareness Algorithm'
$root=Join-Path $base '_handoff/2026-11-08_V8-19_close_observation/run'
$code=Join-Path $base 'Simulation-v08/Multi-UAV SimpleGC'
$argv=@('run','-n','llm','--no-capture-output','python','-B','tools/v08/analyze_close_observation_v19.py',
    '--monitoring',(Join-Path $base '_handoff/2026-11-04_V8-14_skeleton/out/full_v14c'),
    '--transit',(Join-Path $base '_handoff/2026-11-05_V8-16_transit/run/out/full_transit_r2'),
    '--intrusion',(Join-Path $base '_handoff/2026-11-06_V8-17_intrusion/run/out/full/full_r1'),
    '--feint',(Join-Path $base '_handoff/2026-11-06_V8-18_feint/run/out/full_lazy_r1'),
    '--close-observation',(Join-Path $root 'out/full_r1'),
    '--out',(Join-Path $root "diagnostics/analysis_$Round"))
if (Test-Path -LiteralPath (Join-Path $root "diagnostics/analysis_$Round")) { throw 'Analysis output must be new' }
$env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'; $env:NUMEXPR_NUM_THREADS='1'
$env:PYTHONDONTWRITEBYTECODE='1'
Set-Location -LiteralPath $code
$watch=[Diagnostics.Stopwatch]::StartNew()
& 'C:\Users\shy\anaconda3\Scripts\conda.exe' @argv *> (Join-Path $root "diagnostics/analysis_$Round.log")
$nativeExit=$LASTEXITCODE
$watch.Stop()
[ordered]@{argv=$argv;exit_code=$nativeExit;wall_s=$watch.Elapsed.TotalSeconds;checked_utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $root "diagnostics/analysis_${Round}_watch.json") -Encoding utf8NoBOM
Get-Content -LiteralPath (Join-Path $root "diagnostics/analysis_$Round.log") -Tail 6
exit $nativeExit
