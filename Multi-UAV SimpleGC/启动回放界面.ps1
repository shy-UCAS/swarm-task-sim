# Run with PowerShell 7. Uses only this project's configured Conda environment.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$ReplayEnvName = (Get-Content -LiteralPath (Join-Path $PSScriptRoot '.conda-env') -Raw).Trim()
if ([string]::IsNullOrWhiteSpace($ReplayEnvName)) { throw '项目 .conda-env 为空。' }
& conda run -n $ReplayEnvName --no-capture-output python (Join-Path $PSScriptRoot 'replay.py') @args
exit $LASTEXITCODE
