$ErrorActionPreference='Stop'
$repo='F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-v08'
$diag='F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-08_V8-19_close_observation\run\diagnostics'
if (Test-Path -LiteralPath (Join-Path $diag 'snapshot_final.json')) { throw 'Final snapshot must be new' }
$env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'; $env:NUMEXPR_NUM_THREADS='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$argv=@('run','-n','llm','--no-capture-output','python','-B',(Join-Path $repo 'docs/v08/V8-19/snapshot.py'),(Join-Path $diag 'snapshot_final.json'))
$watch=[Diagnostics.Stopwatch]::StartNew()
& 'C:\Users\shy\anaconda3\Scripts\conda.exe' @argv *> (Join-Path $diag 'snapshot_final.log')
$nativeExit=$LASTEXITCODE
$watch.Stop()
[ordered]@{argv=$argv;wall_s=$watch.Elapsed.TotalSeconds;exit_code=$nativeExit;checked_utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $diag 'snapshot_final_watch.json') -Encoding utf8NoBOM
Get-Content -LiteralPath (Join-Path $diag 'snapshot_final.log') -Tail 4
exit $nativeExit
