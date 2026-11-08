param(
    [Parameter(Mandatory=$true)][ValidateSet('smoke','queries','skeleton','quick','full','rerun')][string]$Stage,
    [Parameter(Mandatory=$true)][string]$Name,
    [string]$ContractKey='',
    [int]$Workers=24,
    [int]$LimitSeconds=0,
    [string]$KeysPath='',
    [string]$CompareTo=''
)
$ErrorActionPreference='Stop'
$repo='F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-v08'
$root='F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-06_V8-18_feint\run'
$out=Join-Path $root ('out/' + $Name)
$diag=Join-Path $root ('diagnostics/' + $Name)
if ((Test-Path -LiteralPath $out) -or (Test-Path -LiteralPath $diag)) { throw 'Output already exists' }
New-Item -ItemType Directory -Path $diag | Out-Null
$env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'; $env:NUMEXPR_NUM_THREADS='1'
$argv=@('run','-n','llm','--no-capture-output','python','-B','tools/v08/run_feint_v18.py',
    '--stage',$Stage,'--devset',(Join-Path $repo 'docs/v08/V8-03/devset_v08.json'),
    '--data-root','F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData',
    '--cache',(Join-Path $root 'cache'),'--out',$out,'--workers',"$Workers")
if ($Stage -eq 'smoke') { $argv+=@('--smoke-level','skeleton') }
if ($ContractKey) { $argv+=@('--contract-keys',$ContractKey) }
if ($Stage -eq 'rerun') {
    if (-not $KeysPath -or -not $CompareTo -or $Workers -ne 1) { throw 'rerun requires keys, compare-to, and workers=1' }
    $argv+=@('--keys',$KeysPath,'--compare-to',$CompareTo)
}
$argvText=($argv | ForEach-Object { '"' + $_.Replace('"','\"') + '"' }) -join ' '
$start=[DateTime]::UtcNow
$proc=Start-Process -FilePath 'C:\Users\shy\anaconda3\Scripts\conda.exe' -ArgumentList $argvText -WorkingDirectory (Join-Path $repo 'Multi-UAV SimpleGC') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $diag 'stdout.log') -RedirectStandardError (Join-Path $diag 'stderr.log')
$status=@{stage=$Stage;name=$Name;key=$ContractKey;workers=$Workers;limit_s=$LimitSeconds;start_utc=$start.ToString('o');root_pid=$proc.Id;command=$argv;out=$out;timeout=$false;p0=$false}
$status | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $diag 'watchdog.json') -Encoding utf8
Write-Output "Started $Stage $ContractKey PID=$($proc.Id) at $($status.start_utc)"
$stopped=$false
$checkedResults=[Collections.Generic.HashSet[string]]::new()
while (-not $proc.WaitForExit(5000)) {
    $elapsed=([DateTime]::UtcNow-$start).TotalSeconds
    $p0=@()
    if ($Stage -in @('quick','full')) {
        $resultFiles=@(Get-ChildItem -Path (Join-Path $out 'contracts/*/result.json'),(Join-Path $out 'diversity/contracts/*/result.json') -File -ErrorAction SilentlyContinue)
        foreach ($resultFile in $resultFiles) {
            if ($checkedResults.Contains($resultFile.FullName)) { continue }
            try {
                $r=Get-Content -LiteralPath $resultFile.FullName -Raw -Encoding utf8 | ConvertFrom-Json
                if ($r.success -and $r.retained_p0_ok -eq $false) { $p0+=$resultFile.Directory.Name }
                [void]$checkedResults.Add($resultFile.FullName)
            } catch { }
        }
    }
    if ($Stage -eq 'rerun') {
        $mismatch=@(Select-String -LiteralPath (Join-Path $diag 'stdout.log') -Pattern 'bytes_equal=False|file_sets_equal=False' -ErrorAction SilentlyContinue)
        if ($mismatch.Count -gt 0) {
            $p0+='serial_byte_mismatch'
            $status.p0_details=@($mismatch | ForEach-Object {$_.Line})
        }
    }
    if (($LimitSeconds -gt 0 -and $elapsed -gt $LimitSeconds) -or $p0.Count -gt 0) {
        $status.timeout=($LimitSeconds -gt 0 -and $elapsed -gt $LimitSeconds)
        $status.p0=($p0.Count -gt 0)
        $status.p0_contracts=$p0
        $processes=@(Get-CimInstance Win32_Process)
        $tree=[Collections.Generic.List[int]]::new()
        $tree.Add($proc.Id)
        for ($i=0;$i -lt $tree.Count;$i++) {
            foreach ($child in $processes) {
                if ($child.ParentProcessId -eq $tree[$i] -and -not $tree.Contains([int]$child.ProcessId)) { $tree.Add([int]$child.ProcessId) }
            }
        }
        # 只终止本脚本创建的根进程及可验证的子进程，先子后父；保留所有输出。
        for ($i=$tree.Count-1;$i -ge 0;$i--) { Stop-Process -Id $tree[$i] -Force -ErrorAction SilentlyContinue }
        $stopped=$true
        break
    }
}
if (-not $stopped) { $proc.WaitForExit(); $status.exit_code=$proc.ExitCode }
else { $status.exit_code=if($status.p0){4}else{2} }
if ($status.exit_code -eq 4) { $status.p0=$true }
$status.wall_s=([DateTime]::UtcNow-$start).TotalSeconds
$status.end_utc=[DateTime]::UtcNow.ToString('o')
$status | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $diag 'watchdog.json') -Encoding utf8
$status | ConvertTo-Json -Depth 4 -Compress
Get-Content -LiteralPath (Join-Path $diag 'stdout.log') -Tail 12
Get-Content -LiteralPath (Join-Path $diag 'stderr.log') -Tail 8
exit $status.exit_code
