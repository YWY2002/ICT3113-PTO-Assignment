<#
.SYNOPSIS
  LOAD GENERATOR machine: run one open-loop JMeter test against the system
  under test over the network.

.DESCRIPTION
  Needs only this loadtest folder (triage.jmx, tickets.tsv, search_terms.txt)
  and the JMeter binary release; no Docker or Ollama.

  Start it only after sut_prepare.ps1 on the system under test prints READY.
  Writes results/<model>/<test>/run<N>/ next to this folder:
    results.jtl, jmeter.log, run.properties, loadgen.json (schedules, times,
    network round-trip time to the system under test).
  Send that folder back to the system-under-test machine for sut_collect.ps1.

  On macOS/Linux, run the same test with:
    jmeter -n -t triage.jmx -q run.properties -Jhost=<SUT IP> -l results.jtl -j jmeter.log
  where run.properties holds post_schedule, search_schedule and the
  sample_variables / save-service lines written below.

.EXAMPLE
  # Mixed load (R2 + R3)
  .\loadgen_run.ps1 -SutHost 192.168.1.50 -Model tev1:4b -Test mixed -Run 1 -PostPerHour 198 -SearchPerHour 800

.EXAMPLE
  # Surge (R1)
  .\loadgen_run.ps1 -SutHost 192.168.1.50 -Model tev1:4b -Test surge -Run 1 -PostPerHour 334

.EXAMPLE
  # Stress test: step the arrival rate up every 15 min
  .\loadgen_run.ps1 -SutHost 192.168.1.50 -Model tev1:4b -Test stress -Run 1 -PostSchedule "rate(334/hour) random_arrivals(15 min) rate(334/hour) rate(400/hour) random_arrivals(15 min) rate(400/hour) rate(450/hour) random_arrivals(15 min) rate(450/hour) rate(500/hour) random_arrivals(15 min) rate(500/hour)"
#>
param(
    [Parameter(Mandatory = $true)][string]$SutHost,
    [Parameter(Mandatory = $true)][string]$Model,
    [Parameter(Mandatory = $true)][string]$Test,
    [Parameter(Mandatory = $true)][int]$Run,
    [double]$PostPerHour = 198,
    [double]$SearchPerHour = 0,
    [int]$DurationMin = 60,
    # Full Open Model schedule for POST /tickets; overrides PostPerHour and DurationMin.
    [string]$PostSchedule = '',
    [int]$Port = 8000,
    [string]$JMeter = 'jmeter.bat'
)

$ErrorActionPreference = 'Stop'
$inv = [System.Globalization.CultureInfo]::InvariantCulture
$modelDir = $Model -replace '[^A-Za-z0-9._-]', '-'
$outDir = Join-Path (Split-Path $PSScriptRoot -Parent) "results\$modelDir\$Test\run$Run"

if (-not (Test-Path (Join-Path $PSScriptRoot 'tickets.tsv'))) {
    throw "tickets.tsv not found next to this script. Run prepare_data.py on the system-under-test machine and copy it here."
}
if (Test-Path $outDir) {
    throw "$outDir already exists. Use another -Run number, or delete it if that run was invalid."
}

# The system under test must be up and reachable before the clock starts
try {
    Invoke-RestMethod -Uri "http://${SutHost}:$Port/stats" -TimeoutSec 10 | Out-Null
} catch {
    throw "Cannot reach http://${SutHost}:$Port/stats. Is sut_prepare.ps1 READY, and is port $Port allowed through the firewall?"
}
New-Item -ItemType Directory -Force $outDir | Out-Null

# Network round-trip time, for the test-environment description
$rtt = $null
try {
    $pings = Test-Connection -ComputerName $SutHost -Count 20 -ErrorAction Stop
    # Windows PowerShell 5.1 reports ResponseTime; PowerShell 7 reports Latency.
    $times = $pings | ForEach-Object { if ($null -ne $_.ResponseTime) { $_.ResponseTime } else { $_.Latency } }
    $rtt = [ordered]@{
        count  = $times.Count
        min_ms = ($times | Measure-Object -Minimum).Minimum
        avg_ms = [math]::Round(($times | Measure-Object -Average).Average, 2)
        max_ms = ($times | Measure-Object -Maximum).Maximum
    }
    Write-Host "== Ping to ${SutHost}: avg $($rtt.avg_ms) ms (min $($rtt.min_ms), max $($rtt.max_ms))"
} catch {
    Write-Warning "Ping failed (ICMP may be blocked): $($_.Exception.Message)"
}

# Schedules
if ($PostSchedule -eq '') {
    $r = $PostPerHour.ToString($inv)
    $PostSchedule = "rate($r/hour) random_arrivals($DurationMin min) rate($r/hour)"
}
if ($SearchPerHour -gt 0) {
    $s = $SearchPerHour.ToString($inv)
    $searchSchedule = "rate($s/hour) random_arrivals($DurationMin min) rate($s/hour)"
} else {
    $searchSchedule = 'rate(0/hour) random_arrivals(1 min)'
}

$props = Join-Path $outDir 'run.properties'
@(
    "host=$SutHost"
    "port=$Port"
    "post_schedule=$PostSchedule"
    "search_schedule=$searchSchedule"
    "sample_variables=req_id,row,term"
    "jmeter.save.saveservice.output_format=csv"
    "jmeter.save.saveservice.print_field_names=true"
) | Set-Content -Encoding ASCII $props

$jtl = Join-Path $outDir 'results.jtl'
$testStart = Get-Date
Write-Host "== JMeter: $Model $Test run $Run -> http://${SutHost}:$Port"
Write-Host "   tickets: $PostSchedule"
Write-Host "   search:  $searchSchedule"
& $JMeter -n -t (Join-Path $PSScriptRoot 'triage.jmx') -q $props -l $jtl -j (Join-Path $outDir 'jmeter.log')
$jmeterExit = $LASTEXITCODE
$testEnd = Get-Date

$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
[ordered]@{
    model            = $Model
    test             = $Test
    run              = $Run
    sut_host         = $SutHost
    post_schedule    = $PostSchedule
    search_schedule  = $searchSchedule
    test_started     = $testStart.ToUniversalTime().ToString('o')
    test_ended       = $testEnd.ToUniversalTime().ToString('o')
    jmeter_exit_code = $jmeterExit
    loadgen_hostname = $env:COMPUTERNAME
    loadgen_cpu      = $cpu.Name
    loadgen_cores    = $cpu.NumberOfCores
    loadgen_ram_gb   = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
    network_rtt      = $rtt
} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $outDir 'loadgen.json')

Write-Host "== Done: $outDir"
Write-Host "   Send this folder to the system-under-test machine for sut_collect.ps1 -LoadgenDir."
