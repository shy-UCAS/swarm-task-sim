$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required' }
Set-Location -LiteralPath (Resolve-Path -LiteralPath "$PSScriptRoot/../..").Path
$initial = Get-Content -Raw -Encoding utf8 'verification/v05_batch_20261002/control.json' | ConvertFrom-Json
if ($initial.records.Count -ne 1 -or $initial.stopped_reason -or $initial.active_attempt) {
    throw 'Expected recovered B001 and no active or stopped attempt'
}
for ($batchNumber = 2; $batchNumber -le 240; $batchNumber++) {
    $batchLog = 'tmp_v05/batch_execution_20261002/B{0:D3}.log' -f $batchNumber
    if (Test-Path -LiteralPath $batchLog) { throw "Refusing to overwrite $batchLog" }
    & 'C:/Users/shy/anaconda3/Scripts/conda.exe' run -n llm --no-capture-output python 'scripts/run_v05_batch.py' next *> $batchLog
    $batchExit = $LASTEXITCODE
    $batchControl = Get-Content -Raw -Encoding utf8 'verification/v05_batch_20261002/control.json' | ConvertFrom-Json
    [ordered]@{
        batch = ('B{0:D3}' -f $batchNumber)
        exit = $batchExit
        aggregate = $batchControl.aggregate
        rolling = $batchControl.rolling
        stopped_reason = $batchControl.stopped_reason
        completed = $batchControl.completed
    } | ConvertTo-Json -Depth 8 -Compress
    if ($batchExit -ne 0 -or $batchControl.stopped_reason) { exit 1 }
    if ($batchControl.records.Count -ne $batchNumber) { throw 'Unexpected record count' }
}
