param(
    [Parameter(Mandatory=$true)][string]$OutDir,
    [Parameter(Mandatory=$true)][string]$RunRoot,
    [ValidateRange(1,30)][int]$IntervalSeconds=2
)
$ErrorActionPreference='Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required' }
if (Test-Path -LiteralPath $OutDir) { throw 'Monitor output must be new' }
New-Item -ItemType Directory -Path $OutDir | Out-Null
$utf8=[Text.UTF8Encoding]::new($false)
$stream=[IO.FileStream]::new((Join-Path $OutDir 'metrics.jsonl'),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::ReadWrite,4096,[IO.FileOptions]::WriteThrough)
$writer=[IO.StreamWriter]::new($stream,$utf8,4096,$true)
$writer.AutoFlush=$true
$timer=[Diagnostics.Stopwatch]::StartNew()
$sequence=0
function Write-DurableJson([object]$Value) {
    $writer.WriteLine(($Value | ConvertTo-Json -Depth 8 -Compress))
    $writer.Flush()
    $stream.Flush($true)
}
function Read-SystemEvents([datetime]$After) {
    $rows=@()
    foreach ($spec in @(
        @{LogName='System';ProviderName='Microsoft-Windows-Resource-Exhaustion-Detector';StartTime=$After},
        @{LogName='System';Id=@(41,6008,1074,1001);StartTime=$After}
    )) {
        try {
            $events=Get-WinEvent -FilterHashtable $spec -MaxEvents 30 -ErrorAction Stop
            $rows+=@($events | ForEach-Object { [ordered]@{time_utc=$_.TimeCreated.ToUniversalTime().ToString('o');id=$_.Id;provider=$_.ProviderName;level=$_.LevelDisplayName;record_id=$_.RecordId;message=$_.Message} })
        } catch {
            $rows+=@([ordered]@{query=$spec;query_status=$_.Exception.GetType().Name})
        }
    }
    return $rows
}
try {
    # Only this lightweight monitor is raised; worker priorities are not changed.
    [Diagnostics.Process]::GetCurrentProcess().PriorityClass=[Diagnostics.ProcessPriorityClass]::AboveNormal
    $os=Get-CimInstance Win32_OperatingSystem
    $computer=Get-CimInstance Win32_ComputerSystem
    $meta=[ordered]@{
        schema='v8-20-resource-monitor-1';pid=$PID;start_utc=[datetime]::UtcNow.ToString('o');interval_seconds=$IntervalSeconds
        boot_utc=$os.LastBootUpTime.ToUniversalTime().ToString('o');physical_bytes=[uint64]$computer.TotalPhysicalMemory
        logical_processors=$computer.NumberOfLogicalProcessors;ps_version=$PSVersionTable.PSVersion.ToString()
        pagefiles=@(Get-CimInstance Win32_PageFileUsage | Select-Object Name,AllocatedBaseSize,CurrentUsage,PeakUsage)
        run_root=$RunRoot;flush='FileOptions.WriteThrough + StreamWriter.Flush + FileStream.Flush(true)'
        passive=$true;worker_count_changed=$false
    }
    [IO.File]::WriteAllText((Join-Path $OutDir 'metadata.json'),($meta | ConvertTo-Json -Depth 6)+"`n",$utf8)
    [IO.File]::WriteAllText((Join-Path $OutDir 'system_events_at_start.json'),((Read-SystemEvents ([datetime]::Now.AddHours(-12))) | ConvertTo-Json -Depth 8)+"`n",$utf8)
    while (-not (Test-Path -LiteralPath (Join-Path $OutDir 'stop.request'))) {
        $sampleStart=$timer.Elapsed.TotalSeconds
        $row=[ordered]@{sequence=$sequence;utc=[datetime]::UtcNow.ToString('o');elapsed_s=$sampleStart;errors=@()}
        try {
            $m=Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
            $row.memory=[ordered]@{
                available_bytes=[uint64]$m.AvailableBytes;committed_bytes=[uint64]$m.CommittedBytes;commit_limit_bytes=[uint64]$m.CommitLimit
                commit_percent=$m.PercentCommittedBytesInUse;page_reads_per_s=$m.PageReadsPersec;pages_input_per_s=$m.PagesInputPersec
                pages_output_per_s=$m.PagesOutputPersec;page_faults_per_s=$m.PageFaultsPersec;pool_nonpaged_bytes=[uint64]$m.PoolNonpagedBytes
            }
        } catch { $row.errors+=('memory:'+ $_.Exception.GetType().Name) }
        try {
            $cpu=Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter "Name='_Total'"
            $sys=Get-CimInstance Win32_PerfFormattedData_PerfOS_System
            $row.cpu=[ordered]@{busy_percent=$cpu.PercentProcessorTime;privileged_percent=$cpu.PercentPrivilegedTime;processor_queue=$sys.ProcessorQueueLength;context_switches_per_s=$sys.ContextSwitchesPersec;uptime_s=$sys.SystemUpTime}
        } catch { $row.errors+=('cpu:'+ $_.Exception.GetType().Name) }
        try {
            $row.disks=@(Get-CimInstance Win32_PerfFormattedData_PerfDisk_PhysicalDisk | ForEach-Object {
                [ordered]@{name=$_.Name;queue=$_.CurrentDiskQueueLength;busy_percent=$_.PercentDiskTime;bytes_per_s=$_.DiskBytesPersec;transfers_per_s=$_.DiskTransfersPersec;avg_read_seconds=$_.AvgDisksecPerRead;avg_write_seconds=$_.AvgDisksecPerWrite}
            })
        } catch { $row.errors+=('disk:'+ $_.Exception.GetType().Name) }
        try {
            $all=@(Get-Process -ErrorAction SilentlyContinue)
            $row.python=@($all | Where-Object { $_.ProcessName -match '^(python|pythonw|conda)$' } | ForEach-Object {
                try { [ordered]@{pid=$_.Id;name=$_.ProcessName;working_set_bytes=$_.WorkingSet64;private_bytes=$_.PrivateMemorySize64;peak_working_set_bytes=$_.PeakWorkingSet64;paged_bytes=$_.PagedMemorySize64;cpu_total_s=$_.TotalProcessorTime.TotalSeconds;threads=$_.Threads.Count;handles=$_.HandleCount;start_utc=$_.StartTime.ToUniversalTime().ToString('o')} }
                catch { [ordered]@{pid=$_.Id;name=$_.ProcessName;status='exited_or_inaccessible'} }
            })
            $row.top_private=@($all | Sort-Object PrivateMemorySize64 -Descending | Select-Object -First 8 | ForEach-Object {
                [ordered]@{pid=$_.Id;name=$_.ProcessName;private_bytes=$_.PrivateMemorySize64;working_set_bytes=$_.WorkingSet64}
            })
        } catch { $row.errors+=('process:'+ $_.Exception.GetType().Name) }
        $jobFile=Join-Path $RunRoot 'system_monitor/current_job.json'
        if (Test-Path -LiteralPath $jobFile) {
            try { $row.job=Get-Content -LiteralPath $jobFile -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable }
            catch { $row.errors+=('job:'+ $_.Exception.GetType().Name) }
        }
        $row.sample_cost_s=$timer.Elapsed.TotalSeconds-$sampleStart
        Write-DurableJson $row
        $sequence++
        $remaining=[math]::Max(0,[int](1000*($IntervalSeconds-($timer.Elapsed.TotalSeconds-$sampleStart))))
        if ($remaining -gt 0) { Start-Sleep -Milliseconds $remaining }
    }
    Write-DurableJson ([ordered]@{event='stopped';utc=[datetime]::UtcNow.ToString('o');samples=$sequence})
    [IO.File]::WriteAllText((Join-Path $OutDir 'system_events_at_end.json'),((Read-SystemEvents ([datetime]::Now.AddHours(-12))) | ConvertTo-Json -Depth 8)+"`n",$utf8)
} catch {
    try { Write-DurableJson ([ordered]@{event='monitor_error';utc=[datetime]::UtcNow.ToString('o');error_type=$_.Exception.GetType().Name;message=$_.Exception.Message}) } catch {}
    throw
} finally {
    $writer.Dispose()
    $stream.Dispose()
}
