param(
    [Parameter(Mandatory=$true)][ValidateSet('monitoring','transit','intrusion','feint')][string]$Intent,
    [Parameter(Mandatory=$true)][ValidateSet(2,4)][int]$Phase,
    [string]$Round='r1'
)
$ErrorActionPreference='Stop'
$repo='F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-v08'
$root='F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-08_V8-19_close_observation\run'
$conda='C:\Users\shy\anaconda3\Scripts\conda.exe'
$data='F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData'
$devset=Join-Path $repo 'docs/v08/V8-03/devset_v08.json'
$out=Join-Path $root ("out/gates_${Phase}_${Round}/$Intent")
$diag=Join-Path $root ("diagnostics/gates_${Phase}_${Round}/$Intent")
if ((Test-Path -LiteralPath $out) -or (Test-Path -LiteralPath $diag)) { throw 'Gate output already exists' }
$jobs=@{
 monitoring=@{tool='tools/v08/run_separation_v15.py'; mode=@('--mode','production-quick'); baseline='F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-04_V8-14_skeleton\out\full_v14c'; suffix='run'}
 transit=@{tool='tools/v08/run_transit_v16.py'; mode=@('--stage','quick'); baseline='F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-05_V8-16_transit\run\out\full_transit_r2'; suffix=''}
 intrusion=@{tool='tools/v08/run_intrusion_v17.py'; mode=@('--stage','quick'); baseline='F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-06_V8-17_intrusion\run\out\full\full_r1'; suffix=''}
 feint=@{tool='tools/v08/run_feint_v18.py'; mode=@('--stage','quick'); baseline='F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-06_V8-18_feint\run\out\full_lazy_r1'; suffix=''}
}
$job=$jobs[$Intent]
if (-not (Test-Path -LiteralPath (Join-Path $job.baseline 'records.json'))) { throw 'Required baseline missing' }
New-Item -ItemType Directory -Path $diag | Out-Null
$env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'; $env:NUMEXPR_NUM_THREADS='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$code=Join-Path $repo 'Multi-UAV SimpleGC'
$sourceHashes=@{}
foreach ($sub in @('v08','tools/v08')) {
    foreach ($file in Get-ChildItem -LiteralPath (Join-Path $code $sub) -Filter '*.py' -Recurse -File) {
        $sourceHashes[[IO.Path]::GetRelativePath($code,$file.FullName)]=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$argv=@('run','-n','llm','--no-capture-output','python','-B',$job.tool)+$job.mode+@('--workers','24','--devset',$devset,'--data-root',$data,'--cache',(Join-Path $root 'cache'),'--out',$out)
if ($Intent -eq 'monitoring') { $argv+=@('--baseline',$job.baseline) }
$commandText=($argv | ForEach-Object {'"'+$_.Replace('"','\"')+'"'}) -join ' '
$started=[DateTime]::UtcNow
$head=(& git -C $repo rev-parse HEAD)
$dirty=@(& git -C $repo diff --name-only HEAD -- 'Multi-UAV SimpleGC')
$proc=Start-Process -FilePath $conda -ArgumentList $commandText -WorkingDirectory $code -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $diag 'stdout.log') -RedirectStandardError (Join-Path $diag 'stderr.log')
Write-Output "Started phase=$Phase intent=$Intent workers=24 PID=$($proc.Id) at $($started.ToString('o'))"
while (-not $proc.HasExited) { Start-Sleep -Seconds 5; $proc.Refresh() }
$proc.WaitForExit()
$ended=[DateTime]::UtcNow
$nativeCode=$proc.ExitCode
[ordered]@{intent=$Intent;phase=$Phase;round=$Round;workers=24;head=$head;modified_source_paths=$dirty;source_sha256=$sourceHashes;command=$argv;start_utc=$started.ToString('o');end_utc=$ended.ToString('o');wall_s=($ended-$started).TotalSeconds;exit_code=$nativeCode;out=$out;baseline=$job.baseline;exclusions=@()} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $diag 'watchdog.json') -Encoding utf8
Get-Content -LiteralPath (Join-Path $diag 'stdout.log') -Tail 12
Get-Content -LiteralPath (Join-Path $diag 'stderr.log') -Tail 4
Write-Output "Ended phase=$Phase intent=$Intent native_exit=$nativeCode wall_s=$(($ended-$started).TotalSeconds)"
if ($nativeCode -ne 0) { exit $nativeCode }
$repeat=if ($job.suffix) {Join-Path $out $job.suffix} else {$out}
Set-Location -LiteralPath $code
& $conda run -n llm --no-capture-output python -B (Join-Path $repo 'docs/v08/V8-19/gate_compare.py') $Intent $Phase $job.baseline $repeat (Join-Path $diag 'comparison.json')
exit $LASTEXITCODE
