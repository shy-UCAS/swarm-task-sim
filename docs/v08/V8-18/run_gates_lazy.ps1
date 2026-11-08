$ErrorActionPreference = 'Stop'
$repo = 'F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-v08'
$root = 'F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-06_V8-18_feint\run'
$conda = 'C:\Users\shy\anaconda3\Scripts\conda.exe'
$devset = Join-Path $repo 'docs/v08/V8-03/devset_v08.json'
$data = 'F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData'
$cache = Join-Path $root 'cache'
$out = Join-Path $root 'out/gates_lazy_r1'
$evidence = Join-Path $root 'diagnostics/gates_lazy_r1'
if ((Test-Path -LiteralPath $out) -or (Test-Path -LiteralPath $evidence)) { throw 'Gate output already exists' }
New-Item -ItemType Directory -Path $evidence | Out-Null
Set-Location -LiteralPath (Join-Path $repo 'Multi-UAV SimpleGC')
$env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'; $env:NUMEXPR_NUM_THREADS='1'
$jobs = @(
    @{ intent='monitoring'; tool='tools/v08/run_separation_v15.py'; mode=@('--mode','production-quick'); baseline='F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-04_V8-14_skeleton\out\full_v14c'; suffix='run' },
    @{ intent='transit'; tool='tools/v08/run_transit_v16.py'; mode=@('--stage','quick'); baseline='F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-05_V8-16_transit\run\out\full_transit_r2'; suffix='' },
    @{ intent='intrusion'; tool='tools/v08/run_intrusion_v17.py'; mode=@('--stage','quick'); baseline='F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-06_V8-17_intrusion\run\out\full\full_r1'; suffix='' }
)
foreach ($job in $jobs) {
    $intent = $job.intent
    $target = Join-Path $out $intent
    $argv = @('run','-n','llm','--no-capture-output','python','-B',$job.tool) + $job.mode + @('--workers','24','--devset',$devset,'--data-root',$data,'--cache',$cache,'--out',$target)
    if ($intent -eq 'monitoring') { $argv += @('--baseline',$job.baseline) }
    Write-Output "Starting $intent gate at $([DateTime]::UtcNow.ToString('o'))"
    & $conda @argv 2>&1 | Tee-Object -FilePath (Join-Path $evidence ($intent + '.log'))
    $runCode = $LASTEXITCODE
    Write-Output "$intent run exit=$runCode"
    if ($runCode -ne 0) { exit $runCode }
    $repeat = if ($job.suffix) { Join-Path $target $job.suffix } else { $target }
    & $conda run -n llm --no-capture-output python -B (Join-Path $repo 'docs/v08/V8-18/gate_compare.py') $intent 4 $job.baseline $repeat (Join-Path $evidence ('gate_' + $intent + '.json'))
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
Write-Output "All gates passed at $([DateTime]::UtcNow.ToString('o'))"
