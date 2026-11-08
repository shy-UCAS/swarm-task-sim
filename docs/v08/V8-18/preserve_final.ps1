$ErrorActionPreference = 'Stop'
$v18base = 'F:\CASIA\Drone Swarm Situational Awareness Algorithm'
$v18repo = Join-Path $v18base 'Simulation-v08'
$v18handoff = Join-Path $v18base '_handoff/2026-11-06_V8-18_feint'
$v18doc = Join-Path $v18handoff 'resume_20261108/docs/v08/V8-18'
$v18dest = Join-Path $v18doc 'part8'
New-Item -ItemType Directory -Path $v18dest | Out-Null
$v18before = Get-Content -LiteralPath (Join-Path $v18repo 'docs/v08/V8-18/part5_lazy/preservation_before.json') -Raw | ConvertFrom-Json -DateKind String
$v18cache = Join-Path $v18handoff 'run/cache/feint_v18'
$v18files = @(Get-ChildItem -LiteralPath $v18cache -Recurse -File | Sort-Object FullName | ForEach-Object {
    @{path=[IO.Path]::GetRelativePath($v18cache, $_.FullName); bytes=$_.Length;
      sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant();
      mtime_utc=$_.LastWriteTimeUtc.ToString('o')}
})
$v18lookup = @{}
foreach ($v18file in $v18files) { $v18lookup[$v18file.path] = $v18file }
$v18differences = @()
foreach ($v18old in $v18before.files) {
    $v18new = $v18lookup[$v18old.path]
    if ($null -eq $v18new) { $v18differences += @{path=$v18old.path; reason='missing'}; continue }
    foreach ($v18key in @('bytes','sha256','mtime_utc')) {
        if ($v18old.$v18key -cne $v18new[$v18key]) { $v18differences += @{path=$v18old.path; field=$v18key; before=$v18old.$v18key; after=$v18new[$v18key]} }
}
}
$v18original = @{}
$v18sourceDifferences = @()
foreach ($v18property in $v18before.preserved_source.PSObject.Properties) {
    $v18hash = (Get-FileHash -LiteralPath (Join-Path $v18repo $v18property.Name) -Algorithm SHA256).Hash.ToLowerInvariant()
    $v18original[$v18property.Name] = $v18hash
    if ($v18hash -cne $v18property.Value) { $v18sourceDifferences += $v18property.Name }
}
$v18passed = ($v18files.Count -eq $v18before.files.Count -and $v18differences.Count -eq 0 -and $v18sourceDifferences.Count -eq 0)
@{all_equal=$v18passed; checked_utc=[DateTime]::UtcNow.ToString('o');
  files_before=$v18before.files.Count; files_after=$v18files.Count;
  family_directories=@(Get-ChildItem -LiteralPath $v18cache -Directory).Count;
  cache_differences=$v18differences; preserved_source_differences=$v18sourceDifferences;
  preserved_source=$v18original; files=$v18files;
  timestamp_comparison='ConvertFrom-Json -DateKind String; exact UTC o-format strings, no DateTime auto-conversion'
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $v18dest 'preservation_final.json') -Encoding utf8
foreach ($v18name in @('snapshot_end_lazy_r1.json','snapshot_compare_end_lazy_r1.json','snapshot_lazy_r1.log','snapshot_compare_lazy_r1.log')) {
    Copy-Item -LiteralPath (Join-Path $v18handoff ('run/diagnostics/' + $v18name)) -Destination (Join-Path $v18dest $v18name)
}
Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $v18doc 'preserve_final.ps1')
@{all_equal=$v18passed; cache_files=$v18files.Count; families=@(Get-ChildItem -LiteralPath $v18cache -Directory).Count; cache_diff=$v18differences.Count; source_diff=$v18sourceDifferences.Count} | ConvertTo-Json -Compress
if (-not $v18passed) { exit 3 }
