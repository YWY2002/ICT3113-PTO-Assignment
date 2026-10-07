<#
.SYNOPSIS
  Runs one open-loop JMeter load test against a freshly started triage service.

.DESCRIPTION
  1. docker compose down -v, then up with MODEL / OLLAMA_API (empty database).
  2. Waits until the service answers, sends one warm-up ticket (request id
     "warmup", excluded from analysis) so model loading is not measured.
  3. Runs loadtest/triage.jmx in CLI mode with the requested arrival schedules.
  4. Saves into results/<model>/<test>/run<N>/:
       results.jtl     JMeter samples (with req_id, row, term columns)
       service.jsonl   the service log for this run
       jmeter.log, ollama_ps.txt, run.properties, metadata.json

.EXAMPLE
  # Mixed load (R2 + R3): 198 tickets/h plus 800 searches/h for 60 min
  .\loadtest\run_test.ps1 -Model tev1:4b -Api systemone -Test mixed -Run 1 -PostPerHour 198 -SearchPerHour 800

.EXAMPLE
  # Surge (R1): 334 tickets/h for 60 min
  .\loadtest\run_test.ps1 -Model tev1:4b -Api systemone -Test surge -Run 1 -PostPerHour 334

.EXAMPLE
  # Stress test: step the arrival rate up every 15 min
  .\loadtest\run_test.ps1 -Model tev1:4b -Api systemone -Test stress -Run 1 -PostSchedule "rate(334/hour) random_arrivals(15 min) rate(334/hour) rate(400/hour) random_arrivals(15 min) rate(400/hour) rate(450/hour) random_arrivals(15 min) rate(450/hour) rate(500/hour) random_arrivals(15 min) rate(500/hour)"
#>
param(
    [Parameter(Mandatory = $true)][string]$Model,
    [Parameter(Mandatory = $true)][ValidateSet('chat', 'systemone')][string]$Api,
    [Parameter(Mandatory = $true)][string]$Test,
    [Parameter(Mandatory = $true)][int]$Run,
    [double]$PostPerHour = 198,
    [double]$SearchPerHour = 0,
    [int]$DurationMin = 60,
    # Full Open Model schedule for POST /tickets; overrides PostPerHour and DurationMin.
    [string]$PostSchedule = '',
    [string]$JMeter = 'jmeter.bat',
    [string]$BaseUrl = 'http://localhost:8000',
    [int]$ReadyTimeoutMin = 60
)

$ErrorActionPreference = 'Stop'
$inv = [System.Globalization.CultureInfo]::InvariantCulture
$root = Split-Path $PSScriptRoot -Parent
$modelDir = $Model -replace '[^A-Za-z0-9._-]', '-'
$outDir = Join-Path $root "results\$modelDir\$Test\run$Run"

if (-not (Test-Path (Join-Path $PSScriptRoot 'tickets.tsv'))) {
    throw "loadtest\tickets.tsv not found. Run: python loadtest\prepare_data.py"
}
if (Test-Path $outDir) {
    throw "$outDir already exists. Use another -Run number, or delete it if that run was invalid."
}
New-Item -ItemType Directory -Force $outDir | Out-Null

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

# 1. Fresh service with an empty database
Write-Host "== Restarting service: MODEL=$Model OLLAMA_API=$Api"
Push-Location $root
try {
    docker compose down -v
    $env:MODEL = $Model
    $env:OLLAMA_API = $Api
    docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }
} finally {
    Pop-Location
}
$serviceStart = Get-Date

# 2. Wait for readiness (the first start of a model includes the download)
Write-Host "== Waiting for the service (pulls the model if needed)..."
$deadline = (Get-Date).AddMinutes($ReadyTimeoutMin)
while ($true) {
    try {
        Invoke-RestMethod -Uri "$BaseUrl/stats" -TimeoutSec 5 | Out-Null
        break
    } catch {
        if ((Get-Date) -gt $deadline) { throw "Service not ready after $ReadyTimeoutMin min. Check: docker compose logs triage" }
        Start-Sleep -Seconds 5
    }
}

Write-Host "== Warm-up request"
try {
    $body = '{"narrative": "Warm-up request. My bank charged me an overdraft fee twice for the same transaction."}'
    $w = Invoke-RestMethod -Method Post -Uri "$BaseUrl/tickets" -ContentType 'application/json' `
        -Body $body -Headers @{ 'X-Request-ID' = 'warmup' } -TimeoutSec 900
    Write-Host "   warm-up category: $($w.category)"
} catch {
    Write-Warning "Warm-up failed: $($_.Exception.Message). Continuing so the failure is recorded in the run."
}
try { ollama ps | Out-File -Encoding utf8 (Join-Path $outDir 'ollama_ps.txt') } catch { }

# 3. JMeter, CLI mode
$props = Join-Path $outDir 'run.properties'
@(
    "post_schedule=$PostSchedule"
    "search_schedule=$searchSchedule"
    "sample_variables=req_id,row,term"
    "jmeter.save.saveservice.output_format=csv"
    "jmeter.save.saveservice.print_field_names=true"
) | Set-Content -Encoding ASCII $props

$jtl = Join-Path $outDir 'results.jtl'
$testStart = Get-Date
Write-Host "== JMeter: $Test run $Run"
Write-Host "   tickets: $PostSchedule"
Write-Host "   search:  $searchSchedule"
& $JMeter -n -t (Join-Path $PSScriptRoot 'triage.jmx') -q $props -l $jtl -j (Join-Path $outDir 'jmeter.log')
$jmeterExit = $LASTEXITCODE
$testEnd = Get-Date

# 4. Collect the service log and metadata
$log = Get-ChildItem (Join-Path $root 'logs') -Filter '*.jsonl' |
    Where-Object { $_.LastWriteTime -ge $serviceStart } |
    Sort-Object LastWriteTime | Select-Object -Last 1
$digest = $null
if ($log) {
    Copy-Item $log.FullName (Join-Path $outDir 'service.jsonl')
    $digest = (Get-Content $log.FullName -TotalCount 1 | ConvertFrom-Json).model_digest
} else {
    Write-Warning "No service log found in logs\ for this run."
}

$commit = (git -C $root rev-parse HEAD)
$dirty = [bool](git -C $root status --porcelain -- app docker-compose.yml Dockerfile requirements.txt loadtest)
$ollamaVersion = try { (ollama --version) -join ' ' } catch { $null }

[ordered]@{
    model            = $Model
    model_digest     = $digest
    ollama_api       = $Api
    test             = $Test
    run              = $Run
    post_schedule    = $PostSchedule
    search_schedule  = $searchSchedule
    service_started  = $serviceStart.ToUniversalTime().ToString('o')
    test_started     = $testStart.ToUniversalTime().ToString('o')
    test_ended       = $testEnd.ToUniversalTime().ToString('o')
    git_commit       = $commit
    git_dirty        = $dirty
    ollama_version   = $ollamaVersion
    service_log      = if ($log) { $log.Name } else { $null }
    jmeter_exit_code = $jmeterExit
} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $outDir 'metadata.json')

Write-Host "== Done: $outDir"
if ($dirty) { Write-Warning "Service or load-test files have uncommitted changes; commit them so this run is reproducible." }
