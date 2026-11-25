<#
.SYNOPSIS
  LOAD GENERATOR machine: run one open-loop JMeter test against the system
  under test over the network, including over the internet from a different
  network.

.DESCRIPTION
  Needs only this loadtest folder (triage.jmx, tickets.tsv, search_terms.txt;
  with -S, speedtest_tickets.tsv from assignment2/speedtest/make_speedtest.py)
  and the JMeter binary release; no Docker or Ollama.

  -SutUrl is how this machine reaches the service, for example
    http://100.101.102.103:8000     Tailscale address of the SUT (recommended)
    http://203.0.113.7:8000         SUT's public IP with router port forwarding
    https://example.tunnel.host     a tunnel URL (check it allows 650 s requests)
  The connection must not cut off requests shorter than 650 s (JMeter's
  response timeout). Cloudflare Tunnel stops at about 100 s, so it is not
  suitable for overload and stress runs.

  Start it only after sut_prepare.ps1 on the system under test prints READY.
  Before JMeter starts it measures the network: HTTP round-trip time of 20
  GET /stats requests (works through tunnels) and ICMP ping (often blocked
  across the internet). Writes results/<model>/<test>/run<N>/ next to this
  folder: results.jtl, jmeter.log, run.properties, loadgen.json.
  Send that folder back to the system-under-test machine for sut_collect.ps1.

  On macOS/Linux, run the same test with:
    jmeter -n -t triage.jmx -q run.properties -l results.jtl -j jmeter.log
  where run.properties holds the protocol/host/port, schedule and
  sample_variables / save-service lines written below.

.EXAMPLE
  # Mixed load (R2 + R3)
  .\loadgen_run.ps1 -SutUrl http://100.101.102.103:8000 -Model tev1:4b -Test mixed -Run 1 -PostPerHour 198 -SearchPerHour 800

.EXAMPLE
  # Surge (R1)
  .\loadgen_run.ps1 -SutUrl http://100.101.102.103:8000 -Model tev1:4b -Test surge -Run 1 -PostPerHour 334

.EXAMPLE
  # Stress test: step the arrival rate up every 15 min
  .\loadgen_run.ps1 -SutUrl http://100.101.102.103:8000 -Model tev1:4b -Test stress -Run 1 -PostSchedule "rate(334/hour) random_arrivals(15 min) rate(334/hour) rate(400/hour) random_arrivals(15 min) rate(400/hour) rate(450/hour) random_arrivals(15 min) rate(450/hour) rate(500/hour) random_arrivals(15 min) rate(500/hour)"

.EXAMPLE
  # A2 speed test. Pass -S from measure_s.py; the script derives everything:
  #   rate = 3600 / (2*S) tickets/h, run length = max(5, S) min,
  #   HTTP timeout = max(10*S, 300) s, OMTG pause = timeout + 60 s.
  .\loadgen_run.ps1 -SutUrl http://100.101.102.103:8000 -Model clef-flash:9b -Test a2-speed -Run 1 -S 9
#>
param(
    [Parameter(Mandatory = $true)][string]$SutUrl,
    [Parameter(Mandatory = $true)][string]$Model,
    [Parameter(Mandatory = $true)][string]$Test,
    [Parameter(Mandatory = $true)][int]$Run,
    # A2: pass -S (seconds, from measure_s.py). Overrides PostPerHour, DurationMin,
    # and the JMeter HTTP response timeout, per brief Step 4.
    [double]$S = 0,
    [double]$PostPerHour = 198,
    [double]$SearchPerHour = 0,
    [int]$DurationMin = 60,
    # Full Open Model schedule for POST /tickets; overrides PostPerHour and DurationMin.
    [string]$PostSchedule = '',
    [int]$RttSamples = 20,
    [string]$JMeter = 'jmeter.bat'
)

$ErrorActionPreference = 'Stop'
$inv = [System.Globalization.CultureInfo]::InvariantCulture
$modelDir = $Model -replace '[^A-Za-z0-9._-]', '-'
$outDir = Join-Path (Split-Path $PSScriptRoot -Parent) "results\$modelDir\$Test\run$Run"

$uri = [Uri]$SutUrl.TrimEnd('/')
if ($uri.Scheme -notin @('http', 'https') -or $uri.AbsolutePath -ne '/') {
    throw "-SutUrl must be like http://<host>:<port> or https://<host>, with no path. Got: $SutUrl"
}
$base = "$($uri.Scheme)://$($uri.Authority)"

# A2 speed runs (-S) send the fixed speed-test list, the same tickets in the same order every run.
$ticketsFile = if ($S -gt 0) { 'speedtest_tickets.tsv' } else { 'tickets.tsv' }
if (-not (Test-Path (Join-Path $PSScriptRoot $ticketsFile))) {
    throw "$ticketsFile not found next to this script. Build it on the system-under-test machine (tickets.tsv: prepare_data.py; speedtest_tickets.tsv: assignment2/speedtest/make_speedtest.py) and copy it here."
}
if (Test-Path $outDir) {
    throw "$outDir already exists. Use another -Run number, or delete it if that run was invalid."
}

# The system under test must be up and reachable before the clock starts
try {
    Invoke-RestMethod -Uri "$base/stats" -TimeoutSec 15 | Out-Null
} catch {
    throw "Cannot reach $base/stats. Is sut_prepare.ps1 READY, is the tunnel / port forward up, and is port $($uri.Port) allowed through the SUT's firewall?"
}
New-Item -ItemType Directory -Force $outDir | Out-Null

function Get-Summary($values) {
    $v = @($values | Sort-Object)
    if ($v.Count -eq 0) { return $null }
    # Nearest-rank percentiles, the same method as the result analysis
    $rank = { param($p) $v[[math]::Max(0, [math]::Ceiling($p / 100 * $v.Count) - 1)] }
    [ordered]@{
        count  = $v.Count
        min_ms = [math]::Round($v[0], 1)
        p50_ms = [math]::Round((& $rank 50), 1)
        p95_ms = [math]::Round((& $rank 95), 1)
        max_ms = [math]::Round($v[-1], 1)
        mean_ms = [math]::Round(($v | Measure-Object -Average).Average, 1)
    }
}

# Network round-trip time, for the test-environment description and prediction B4.
# HTTP RTT: GET /stats is a near-instant query on the SUT, so its elapsed time is
# almost entirely network (plus TLS for https). It works through tunnels.
Write-Host "== Measuring network round-trip time to $base ..."
$httpTimes = @()
for ($i = 0; $i -lt $RttSamples; $i++) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        Invoke-WebRequest -Uri "$base/stats" -UseBasicParsing -TimeoutSec 15 -Headers @{ 'X-Request-ID' = "rtt-$i" } | Out-Null
        $sw.Stop()
        $httpTimes += $sw.Elapsed.TotalMilliseconds
    } catch {
        Write-Warning "RTT probe $i failed: $($_.Exception.Message)"
    }
    Start-Sleep -Milliseconds 250
}
$httpRtt = Get-Summary $httpTimes
if ($httpRtt) {
    Write-Host "   HTTP GET /stats: p50 $($httpRtt.p50_ms) ms, p95 $($httpRtt.p95_ms) ms, max $($httpRtt.max_ms) ms"
}

$icmpRtt = $null
try {
    $pings = Test-Connection -ComputerName $uri.Host -Count $RttSamples -ErrorAction Stop
    # Windows PowerShell 5.1 reports ResponseTime; PowerShell 7 reports Latency.
    $icmpRtt = Get-Summary ($pings | ForEach-Object { if ($null -ne $_.ResponseTime) { $_.ResponseTime } else { $_.Latency } })
    Write-Host "   ICMP ping: p50 $($icmpRtt.p50_ms) ms, p95 $($icmpRtt.p95_ms) ms"
} catch {
    Write-Host "   ICMP ping not available (often blocked across the internet); using HTTP RTT only."
}

# Schedules. If -S is given, derive rate / run length / timeout / pause per A2 brief.
$a2 = $S -gt 0
$responseTimeoutMs = 650000
if ($a2) {
    if ($PostSchedule -ne '') {
        throw "-S and -PostSchedule are mutually exclusive. The A2 schedule is derived from -S."
    }
    $rateA2 = 3600.0 / (2.0 * $S)             # one ticket every 2S seconds
    $runMin = [int][math]::Max(5, [math]::Ceiling($S))
    $timeoutS = [int][math]::Max(300, [math]::Ceiling(10 * $S))
    $pauseMin = [int][math]::Ceiling($timeoutS / 60.0) + 1
    $responseTimeoutMs = $timeoutS * 1000
    $rateStr = $rateA2.ToString('F4', $inv)
    $PostSchedule = "rate($rateStr/hour) random_arrivals($runMin min) pause($pauseMin min)"
    Write-Host "== A2 mode: S=$S s"
    Write-Host "   rate         = $([math]::Round($rateA2, 1)) tickets/h (one every $([math]::Round(2.0 * $S, 1)) s)"
    Write-Host "   run length   = $runMin min"
    Write-Host "   HTTP timeout = $timeoutS s"
    Write-Host "   OMTG pause   = $pauseMin min (brief: timeout + >=1 min)"
} elseif ($PostSchedule -eq '') {
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
    "protocol=$($uri.Scheme)"
    "host=$($uri.Host)"
    "port=$($uri.Port)"
    "post_schedule=$PostSchedule"
    "search_schedule=$searchSchedule"
    "response_timeout_ms=$responseTimeoutMs"
    "tickets_file=$ticketsFile"
    "sample_variables=req_id,row,term"
    "jmeter.save.saveservice.output_format=csv"
    "jmeter.save.saveservice.print_field_names=true"
    # Write each sample to the .jtl as it completes. JMeter buffers by default,
    # and at a few samples per minute the file can look empty for many minutes.
    "jmeter.save.saveservice.autoflush=true"
) | Set-Content -Encoding ASCII $props

# A2 brief Step 4 "Each run": GET /stats before (and after) the JMeter run.
# The increase is the number of requests the service completed and stored.
$statsBefore = $null
try {
    $statsBefore = Invoke-RestMethod -Uri "$base/stats" -TimeoutSec 15
    Write-Host "== GET /stats before run: total = $($statsBefore.total)"
} catch {
    Write-Warning "GET /stats before run failed: $($_.Exception.Message)"
}

$jtl = Join-Path $outDir 'results.jtl'
$testStart = Get-Date
Write-Host "== JMeter: $Model $Test run $Run -> $base"
Write-Host "   tickets: $PostSchedule"
Write-Host "   search:  $searchSchedule"
& $JMeter -n -t (Join-Path $PSScriptRoot 'triage.jmx') -q $props -l $jtl -j (Join-Path $outDir 'jmeter.log')
$jmeterExit = $LASTEXITCODE
$testEnd = Get-Date

$statsAfter = $null
try {
    $statsAfter = Invoke-RestMethod -Uri "$base/stats" -TimeoutSec 15
    Write-Host "== GET /stats after run: total = $($statsAfter.total)"
    if ($statsBefore) {
        $delta = $statsAfter.total - $statsBefore.total
        Write-Host "   requests completed and stored during this run: $delta"
    }
} catch {
    Write-Warning "GET /stats after run failed: $($_.Exception.Message)"
}

$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$json = [ordered]@{
    model            = $Model
    test             = $Test
    run              = $Run
    sut_url          = $base
    post_schedule    = $PostSchedule
    search_schedule  = $searchSchedule
    response_timeout_ms = $responseTimeoutMs
    tickets_file     = $ticketsFile
    test_started     = $testStart.ToUniversalTime().ToString('o')
    test_ended       = $testEnd.ToUniversalTime().ToString('o')
    jmeter_exit_code = $jmeterExit
    stats_before     = $statsBefore
    stats_after      = $statsAfter
    loadgen_hostname = $env:COMPUTERNAME
    loadgen_cpu      = $cpu.Name
    loadgen_cores    = $cpu.NumberOfCores
    loadgen_ram_gb   = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
    network_http_rtt = $httpRtt
    network_icmp_rtt = $icmpRtt
}
if ($a2) {
    $json['a2_S_seconds']           = $S
    $json['a2_rate_tickets_per_h']  = [math]::Round(3600.0 / (2.0 * $S), 2)
    $json['a2_run_length_minutes']  = [int][math]::Max(5, [math]::Ceiling($S))
    $json['a2_http_timeout_s']      = [int][math]::Max(300, [math]::Ceiling(10 * $S))
    $json['a2_omtg_pause_minutes']  = [int][math]::Ceiling($json['a2_http_timeout_s'] / 60.0) + 1
}
$json | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 (Join-Path $outDir 'loadgen.json')

Write-Host "== Done: $outDir"
Write-Host "   Send this folder to the system-under-test machine for sut_collect.ps1 -LoadgenDir."
