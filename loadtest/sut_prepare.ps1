<#
.SYNOPSIS
  SYSTEM UNDER TEST machine, step 1 of 2: start a fresh service for one run.

.DESCRIPTION
  1. docker compose down -v, then up with MODEL / OLLAMA_API (empty database).
  2. Waits until the service answers and sends three fixed warm-up tickets
     (request ids "warmup-1", "warmup-2", "warmup-3", excluded from analysis)
     so model loading is not measured. For the cascade, the three narratives
     span categories the primary and escalation model are likely to disagree
     on, so both models load before the measured run starts.
  3. Records `ollama ps` and starts sampling CPU utilisation every 5 s
     (total, Ollama processes, Docker's WSL VM) into cpu.csv.
  4. Writes sut_start.json into results/<model>/<test>/run<N>/.

  Then tell the load-generator machine to start loadgen_run.ps1. When JMeter
  has finished, run sut_collect.ps1 with the same -Model, -Test and -Run.

.EXAMPLE
  .\loadtest\sut_prepare.ps1 -Model tev1:4b -Api systemone -Test mixed -Run 1

.EXAMPLE
  # Cascade (Setting A: risky = Money transfer, Debt collection)
  .\loadtest\sut_prepare.ps1 -Model cascade-A -Api cascade -Test a2-accuracy -Run 1

.EXAMPLE
  # Cascade (Setting B: risky = Money transfer, Debt collection, Credit reporting)
  .\loadtest\sut_prepare.ps1 -Model cascade-B -Api cascade -Test a2-accuracy -Run 1
#>
param(
    [Parameter(Mandatory = $true)][string]$Model,
    [Parameter(Mandatory = $true)][ValidateSet('chat', 'systemone', 'cascade')][string]$Api,
    [Parameter(Mandatory = $true)][string]$Test,
    [Parameter(Mandatory = $true)][int]$Run,
    [string]$BaseUrl = 'http://localhost:8000',
    [int]$ReadyTimeoutMin = 60
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$modelDir = $Model -replace '[^A-Za-z0-9._-]', '-'
$outDir = Join-Path $root "results\$modelDir\$Test\run$Run"

# Cascade settings. Looked up from -Model when -Api is cascade. The small and
# large models are Assignment 1 candidates; the risky-set choice comes from
# tev1's confusion matrix on the odd (tuning) golden rows.
$cascadeConfigs = @{
    'cascade-A' = @{
        Small   = 'tev1:4b'
        SmallApi = 'systemone'
        Large   = 'clef-flash:9b'
        LargeApi = 'systemone'
        Risky   = 'Money transfer or service,Debt collection'
    }
    'cascade-B' = @{
        Small   = 'tev1:4b'
        SmallApi = 'systemone'
        Large   = 'clef-flash:9b'
        LargeApi = 'systemone'
        Risky   = 'Money transfer or service,Debt collection,Credit reporting'
    }
}

if ($Api -eq 'cascade' -and -not $cascadeConfigs.ContainsKey($Model)) {
    throw "Unknown cascade model '$Model'. Known: $($cascadeConfigs.Keys -join ', ')"
}

if (Test-Path $outDir) {
    throw "$outDir already exists. Use another -Run number, or delete it if that run was invalid."
}
New-Item -ItemType Directory -Force $outDir | Out-Null

# 1. Fresh service with an empty database
Write-Host "== Restarting service: MODEL=$Model OLLAMA_API=$Api"
Push-Location $root
try {
    docker compose down -v
    $env:MODEL = $Model
    $env:OLLAMA_API = $Api
    if ($Api -eq 'cascade') {
        $cfg = $cascadeConfigs[$Model]
        $env:CASCADE_SMALL = $cfg.Small
        $env:CASCADE_SMALL_API = $cfg.SmallApi
        $env:CASCADE_LARGE = $cfg.Large
        $env:CASCADE_LARGE_API = $cfg.LargeApi
        $env:CASCADE_RISKY = $cfg.Risky
        Write-Host "   CASCADE_SMALL=$($cfg.Small) ($($cfg.SmallApi))"
        Write-Host "   CASCADE_LARGE=$($cfg.Large) ($($cfg.LargeApi))"
        Write-Host "   CASCADE_RISKY=$($cfg.Risky)"
    } else {
        Remove-Item Env:\CASCADE_SMALL -ErrorAction SilentlyContinue
        Remove-Item Env:\CASCADE_SMALL_API -ErrorAction SilentlyContinue
        Remove-Item Env:\CASCADE_LARGE -ErrorAction SilentlyContinue
        Remove-Item Env:\CASCADE_LARGE_API -ErrorAction SilentlyContinue
        Remove-Item Env:\CASCADE_RISKY -ErrorAction SilentlyContinue
    }
    docker compose up -d --build
    if ($LASTEXITCODE -ne 0) {
        Remove-Item -Recurse -Force $outDir -ErrorAction SilentlyContinue
        throw "docker compose up failed"
    }
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

Write-Host "== Warm-up: 3 fixed tickets"
# Three fixed narratives, one from each of the three categories the cascade
# is most likely to disagree on (overdraft/bank, credit report/debt,
# mortgage). Sent one at a time with request ids warmup-1..3 so they are
# easy to exclude from analysis. If the service is a cascade, these are
# enough to load both the primary and the escalation model into ollama ps
# before the measured run starts.
$warmups = @(
    'My bank charged me an overdraft fee twice for the same transaction.',
    'A collector keeps calling me about a debt I already paid off two years ago.',
    'My mortgage servicer put my escrow into shortage and raised my monthly payment without notice.'
)
for ($i = 0; $i -lt $warmups.Count; $i++) {
    $rid = "warmup-$($i + 1)"
    $body = (@{ narrative = $warmups[$i] } | ConvertTo-Json -Compress)
    try {
        $w = Invoke-RestMethod -Method Post -Uri "$BaseUrl/tickets" -ContentType 'application/json' `
            -Body $body -Headers @{ 'X-Request-ID' = $rid } -TimeoutSec 900
        Write-Host "   $rid category: $($w.category)"
    } catch {
        Write-Warning "$rid failed: $($_.Exception.Message). Continuing so the failure is recorded in the run."
    }
}
try {
    $psOut = ollama ps
    $psOut | Out-File -Encoding utf8 (Join-Path $outDir 'ollama_ps.txt')
    if ($Api -eq 'cascade') {
        # Brief: "run ollama ps in the container and confirm both models are
        # listed. Do not start the run until they are."
        $joined = ($psOut -join "`n")
        $cfg = $cascadeConfigs[$Model]
        if ($joined -notmatch [regex]::Escape($cfg.Small)) {
            Write-Warning "Small model '$($cfg.Small)' not in ollama ps. The small-model warm-up may not have triggered."
        }
        if ($joined -notmatch [regex]::Escape($cfg.Large)) {
            Write-Warning "Large model '$($cfg.Large)' not in ollama ps. No warm-up escalated, so the large model is not pre-loaded. Pick a warm-up narrative your rule will escalate, or re-run."
        }
    }
} catch { }

# 3. CPU sampling until sut_collect.ps1 stops it
$cpuCsv = Join-Path $outDir 'cpu.csv'
$counters = @(
    '\Processor(_Total)\% Processor Time',
    '\Process(ollama*)\% Processor Time',
    '\Process(vmmem*)\% Processor Time'
)
$typeperf = Start-Process -FilePath 'typeperf.exe' -PassThru -WindowStyle Hidden `
    -ArgumentList (($counters | ForEach-Object { '"' + $_ + '"' }) + @('-si', '5', '-f', 'CSV', '-o', ('"' + $cpuCsv + '"'), '-y'))

# 4. Start record
$commit = (git -C $root rev-parse HEAD)
$dirty = [bool](git -C $root status --porcelain -- app docker-compose.yml Dockerfile requirements.txt loadtest)
$ollamaVersion = try { (ollama --version) -join ' ' } catch { $null }
[ordered]@{
    model           = $Model
    ollama_api      = $Api
    test            = $Test
    run             = $Run
    service_started = $serviceStart.ToUniversalTime().ToString('o')
    sut_ready       = (Get-Date).ToUniversalTime().ToString('o')
    sut_hostname    = $env:COMPUTERNAME
    git_commit      = $commit
    git_dirty       = $dirty
    ollama_version  = $ollamaVersion
    cpu_sampler_pid = $typeperf.Id
} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $outDir 'sut_start.json')

if ($dirty) { Write-Warning "Service or load-test files have uncommitted changes; commit them so this run is reproducible." }
$ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.PrefixOrigin -ne 'WellKnown' } |
    Select-Object -ExpandProperty IPAddress) -join ', '
Write-Host ""
Write-Host "== READY. Load generator can now start, targeting this machine: $ip (port 8000)"
Write-Host "   Afterwards run: .\loadtest\sut_collect.ps1 -Model $Model -Test $Test -Run $Run -LoadgenDir <folder copied from the load generator>"
