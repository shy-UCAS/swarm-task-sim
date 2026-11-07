# V8-18 三意图字节门禁（第 2 部分 phase=2、第 4 部分 phase=4）。用法：pwsh -File run_gates.ps1 <phase>
# 监视 run_separation_v15.py --mode production-quick（与 full_v14c）；过境 run_transit_v16.py --stage quick（与 full_transit_r2）；
# 突入 run_intrusion_v17.py --stage quick（与 V8-17 full_r1）。三者 24 进程、同环境、同输入；合同排除清单 []。
param([Parameter(Mandatory = $true)][int]$Phase)
$R = 'F:\CASIA\Drone Swarm Situational Awareness Algorithm'
$RUN = "$R\_handoff\2026-11-06_V8-18_feint\run"
$DOC = "$R\Simulation-v08\docs\v08\V8-18"
Set-Location "$R\Simulation-v08\Multi-UAV SimpleGC"
$env:OMP_NUM_THREADS = '1'; $env:OPENBLAS_NUM_THREADS = '1'; $env:MKL_NUM_THREADS = '1'; $env:NUMEXPR_NUM_THREADS = '1'
$conda = 'C:\Users\shy\anaconda3\Scripts\conda.exe'
$devset = "$R\Simulation-v08\docs\v08\V8-03\devset_v08.json"
$data = "$R\SwarmData"
$cache = "$RUN\cache"
$bases = @{ monitoring = "$R\_handoff\2026-11-04_V8-14_skeleton\out\full_v14c";
            transit = "$R\_handoff\2026-11-05_V8-16_transit\run\out\full_transit_r2";
            intrusion = "$R\_handoff\2026-11-06_V8-17_intrusion\run\out\full\full_r1" }
$out = "$RUN\out\gates_$Phase"
"start $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') commit=$(git rev-parse HEAD) dirty=$((git status --porcelain | Measure-Object -Line).Lines)"
git status --porcelain
& $conda run -n llm --no-capture-output python -B tools/v08/run_separation_v15.py --mode production-quick --workers 24 --baseline $bases.monitoring --devset $devset --data-root $data --cache $cache --out "$out\monitoring"
"monitoring exit=$LASTEXITCODE $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
& $conda run -n llm --no-capture-output python -B "$DOC\gate_compare.py" monitoring $Phase $bases.monitoring "$out\monitoring\run" "$DOC\part$Phase\gate_monitoring.json"
"monitoring gate exit=$LASTEXITCODE"
& $conda run -n llm --no-capture-output python -B tools/v08/run_transit_v16.py --stage quick --workers 24 --devset $devset --data-root $data --cache $cache --out "$out\transit"
"transit exit=$LASTEXITCODE $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
& $conda run -n llm --no-capture-output python -B "$DOC\gate_compare.py" transit $Phase $bases.transit "$out\transit" "$DOC\part$Phase\gate_transit.json"
"transit gate exit=$LASTEXITCODE"
& $conda run -n llm --no-capture-output python -B tools/v08/run_intrusion_v17.py --stage quick --workers 24 --devset $devset --data-root $data --cache $cache --out "$out\intrusion"
"intrusion exit=$LASTEXITCODE $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
& $conda run -n llm --no-capture-output python -B "$DOC\gate_compare.py" intrusion $Phase $bases.intrusion "$out\intrusion" "$DOC\part$Phase\gate_intrusion.json"
"intrusion gate exit=$LASTEXITCODE end $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
