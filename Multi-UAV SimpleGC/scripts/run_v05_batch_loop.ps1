#requires -Version 7.0
# Invoke next only. Never retry, repair, clear a stop, or finalize the dataset.
# Exit codes: 0 = all 240 complete; 1 = controller stop/command failure;
# 2 = unreadable/ambiguous state or unexpected progress.
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$controlPath = Join-Path $projectRoot 'verification/v05_batch_20261002/control.json'
$logPath = Join-Path $projectRoot 'tmp_v05/batch_execution_20261002/batch_loop.log'
$condaPath = 'C:/Users/shy/anaconda3/Scripts/conda.exe'

function Write-LoopLog([string]$Message) {
    $line = '[{0}] {1}' -f [DateTimeOffset]::UtcNow.ToString('o'), $Message
    $line | Tee-Object -FilePath $logPath -Append | Out-Host
}

function Read-Control {
    $state = Get-Content -LiteralPath $controlPath -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
    foreach ($field in @('records', 'aggregate', 'active_attempt', 'stopped_reason', 'completed')) {
        if (-not $state.ContainsKey($field)) { throw "Control is missing $field; do not start another attempt" }
    }
    if ($state.completed -isnot [bool] -or -not $state.aggregate.ContainsKey('logical_completed')) {
        throw 'Control completion state is ambiguous; do not start another attempt'
    }
    return $state
}

function Write-Progress($State, [string]$Reason) {
    Write-LoopLog ('completed={0}/240 attempts={1}/264 reason={2}' -f
        $State.aggregate.logical_completed, $State.records.Count, $Reason)
}

New-Item -ItemType Directory -Path (Split-Path -Parent $logPath) -Force | Out-Null
Push-Location -LiteralPath $projectRoot
try {
    Write-LoopLog "Starting next-only loop; append log: $logPath"
    $state = Read-Control
    while ($true) {
        if ($state.stopped_reason) {
            Write-Progress $state ([string]$state.stopped_reason)
            exit 1
        }
        if ($null -ne $state.active_attempt) {
            Write-Progress $state 'Unresolved active_attempt; no next call made'
            exit 2
        }
        if ($state.completed) {
            if ($state.aggregate.logical_completed -ne 240) {
                throw 'completed=true disagrees with logical_completed=240'
            }
            Write-Progress $state 'All 240 complete; no finalize call made'
            exit 0
        }
        if ($state.aggregate.logical_completed -ge 240 -or $state.records.Count -ge 264) {
            throw 'Completion or attempt limit reached without a completed controller state'
        }
        $environmentName = (Get-Content -LiteralPath (Join-Path $projectRoot '.conda-env') -Raw -Encoding utf8).Trim()
        if (-not $environmentName) { throw 'Project .conda-env is empty' }
        $beforeAttempts = $state.records.Count
        $beforeCompleted = $state.aggregate.logical_completed
        Write-Progress $state 'Calling controller next once'
        $global:LASTEXITCODE = 0
        & $condaPath run -n $environmentName --no-capture-output python 'scripts/run_v05_batch.py' next 2>&1 |
            Tee-Object -FilePath $logPath -Append | Out-Host
        $commandExit = $LASTEXITCODE
        $state = Read-Control
        if ($commandExit -ne 0 -or $state.stopped_reason) {
            $reason = if ($state.stopped_reason) { [string]$state.stopped_reason } else { 'Controller returned nonzero without a stop reason' }
            Write-Progress $state ("exit=$commandExit; $reason; no retry")
            exit 1
        }
        if ($null -ne $state.active_attempt) {
            Write-Progress $state 'Controller returned with unresolved active_attempt; no retry'
            exit 2
        }
        if ($state.records.Count -ne ($beforeAttempts + 1) -or
                $state.aggregate.logical_completed -ne ($beforeCompleted + 1)) {
            Write-Progress $state 'Unexpected attempt/completion count change; no retry'
            exit 2
        }
        Write-Progress $state 'Controller next completed'
    }
}
catch {
    Write-LoopLog ('Loop stopped: {0}; no retry' -f $_.Exception.Message)
    if ($null -ne $state) { Write-Progress $state 'Last readable control state' }
    exit 2
}
finally {
    Pop-Location
}
