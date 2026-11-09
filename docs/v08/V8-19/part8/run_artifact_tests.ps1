$ErrorActionPreference='Stop'
$repo='F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-v08'
$diag='F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-08_V8-19_close_observation\run\diagnostics'
if (Test-Path -LiteralPath (Join-Path $diag 'artifact_tests_r1.log')) { throw 'Test log must be new' }
$env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'; $env:NUMEXPR_NUM_THREADS='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:V8_19_ACCEPTANCE=Join-Path $repo 'docs/v08/V8-19/acceptance.json'
Set-Location -LiteralPath (Join-Path $repo 'Multi-UAV SimpleGC')
$argv=@('run','-n','llm','--no-capture-output','python','-B','-m','unittest','discover','-s','tests/v08/V8-19','-p','test_preset_local_artifacts_v19.py','-v')
$started=[DateTime]::UtcNow
$watch=[Diagnostics.Stopwatch]::StartNew()
& 'C:\Users\shy\anaconda3\Scripts\conda.exe' @argv *> (Join-Path $diag 'artifact_tests_r1.log')
$nativeExit=$LASTEXITCODE
$watch.Stop()
[ordered]@{argv=$argv;acceptance=$env:V8_19_ACCEPTANCE;started_utc=$started.ToString('o');ended_utc=[DateTime]::UtcNow.ToString('o');wall_s=$watch.Elapsed.TotalSeconds;exit_code=$nativeExit} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $diag 'artifact_tests_r1_watch.json') -Encoding utf8NoBOM
Get-Content -LiteralPath (Join-Path $diag 'artifact_tests_r1.log') -Tail 12
exit $nativeExit
