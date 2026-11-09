param(
    [Parameter(Mandatory=$true)][ValidateSet('smoke','prewarm','skeleton','quick','full','rerun')][string]$Stage,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-z0-9_]+$')][string]$Round,
    [int]$Workers=24,
    [string]$ContractKeys,
    [string]$PrewarmFrom,
    [string]$Keys,
    [string]$CompareTo
)
$ErrorActionPreference='Stop'
$repo='F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-v08'
$root='F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-08_V8-19_close_observation\run'
$code=Join-Path $repo 'Multi-UAV SimpleGC'
$conda='C:\Users\shy\anaconda3\Scripts\conda.exe'
$out=Join-Path $root ("out/${Stage}_${Round}")
$diag=Join-Path $root ("diagnostics/${Stage}_${Round}")
if ((Test-Path -LiteralPath $out) -or (Test-Path -LiteralPath $diag)) { throw 'Stage output already exists' }
if ($Stage -eq 'skeleton' -and -not $PrewarmFrom) { throw 'Formal skeleton dispatch requires a separately completed prewarm document' }
if (($Stage -eq 'quick' -or $Stage -eq 'full') -and -not $PrewarmFrom) { throw 'Production batch requires the separately accepted prewarm document' }
New-Item -ItemType Directory -Path $diag | Out-Null
$env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'; $env:NUMEXPR_NUM_THREADS='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$argv=@('run','-n','llm','--no-capture-output','python','-B','tools/v08/run_close_observation_v19.py','--stage',$Stage,
    '--workers',[string]$Workers,'--devset',(Join-Path $repo 'docs/v08/V8-03/devset_v08.json'),
    '--data-root','F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData','--cache',(Join-Path $root 'cache'),'--out',$out)
if ($ContractKeys) { $argv+=@('--contract-keys',$ContractKeys) }
if ($PrewarmFrom) { $argv+=@('--prewarm-from',$PrewarmFrom) }
if ($Keys) { $argv+=@('--keys',$Keys) }
if ($CompareTo) { $argv+=@('--compare-to',$CompareTo) }
$sourceHashes=@{}
foreach ($sub in @('v08','tools/v08')) {
    foreach ($file in Get-ChildItem -LiteralPath (Join-Path $code $sub) -Filter '*.py' -Recurse -File) {
        $sourceHashes[[IO.Path]::GetRelativePath($code,$file.FullName)]=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$head=(& git -C $repo rev-parse HEAD)
$dirty=@(& git -C $repo diff --name-only HEAD -- 'Multi-UAV SimpleGC')
$limit=if ($Stage -eq 'prewarm') {2700.0} elseif ($Stage -eq 'skeleton') {1800.0} else {$null}
$commandText=($argv | ForEach-Object {'"'+$_.Replace('"','\"')+'"'}) -join ' '
$started=[DateTime]::UtcNow
$proc=Start-Process -FilePath $conda -ArgumentList $commandText -WorkingDirectory $code -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $diag 'stdout.log') -RedirectStandardError (Join-Path $diag 'stderr.log')
Write-Output "Started stage=$Stage round=$Round PID=$($proc.Id) at $($started.ToString('o'))"
$limited=$false
while (-not $proc.WaitForExit(1000)) {
    $elapsed=([DateTime]::UtcNow-$started).TotalSeconds
    if ($null -ne $limit -and $elapsed -gt $limit) {
        $limited=$true
        $all=@(Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId)
        $ids=[System.Collections.Generic.List[int]]::new()
        $ids.Add([int]$proc.Id)
        do {
            $added=$false
            foreach ($p in $all) {
                if ($ids.Contains([int]$p.ParentProcessId) -and -not $ids.Contains([int]$p.ProcessId)) {
                    $ids.Add([int]$p.ProcessId); $added=$true
                }
            }
        } while ($added)
        for ($i=$ids.Count-1; $i -ge 0; $i--) { Stop-Process -Id $ids[$i] -Force -ErrorAction SilentlyContinue }
        break
    }
}
if (-not $limited) { $proc.WaitForExit(); $proc.Refresh() }
$ended=[DateTime]::UtcNow
$exitCode=if ($limited) {2} else {$proc.ExitCode}
$watch=[ordered]@{stage=$Stage;round=$Round;head=$head;modified_source_paths=$dirty;source_sha256=$sourceHashes;
    argv=$argv;pid=$proc.Id;started_utc=$started.ToString('o');ended_utc=$ended.ToString('o');wall_s=($ended-$started).TotalSeconds;
    workers_requested=$Workers;workers_effective=if ($Stage -in @('smoke','rerun')) {1} else {$Workers};
    limit_s=$limit;limited=$limited;exit_code=$exitCode;out=$out}
$watch | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $diag 'watchdog.json') -Encoding utf8NoBOM
Get-Content -LiteralPath (Join-Path $diag 'stdout.log') -Tail 8
if ($exitCode -ne 0) { Get-Content -LiteralPath (Join-Path $diag 'stderr.log') -Tail 16 }
Write-Output "Ended stage=$Stage exit=$exitCode wall_s=$($watch.wall_s) limited=$limited"
exit $exitCode
