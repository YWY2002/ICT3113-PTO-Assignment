<#
.SYNOPSIS
  SYSTEM UNDER TEST machine, step 1 of 2: start a fresh service for one run.

.DESCRIPTION
  1. docker compose down -v, then up with MODEL / OLLAMA_API (empty database).
  2. Waits until the service answers and sends one warm-up ticket (request id
     "warmup", excluded from analysis) so model loading is not measured.
  3. Records `ollama ps` and starts sampling CPU utilisation every 5 s
     (total, Ollama processes, Docker's WSL VM) into cpu.csv.
  4. Writes sut_start.json into results/<model>/<test>/run<N>/.

  Then tell the load-generator machine to start loadgen_run.ps1. When JMeter
  has finished, run sut_collect.ps1 with the same -Model, -Test and -Run.

.EXAMPLE
  .\loadtest\sut_prepare.ps1 -Model tev1:4b -Api systemone -Test mixed -Run 1
#>
param(
    [Parameter(Mandatory = $true)][string]$Model,
    [Parameter(Mandatory = $true)][ValidateSet('chat', 'systemone')][string]$Api,
    [Parameter(Mandatory = $true)][string]$Test,
    [Parameter(Mandatory = $true)][int]$Run,
    [string]$BaseUrl = 'http://localhost:8000',
    [int]$ReadyTimeoutMin = 60
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$modelDir = $Model -replace '[^A-Za-z0-9._-]', '-'
$outDir = Join-Path $root "results\$modelDir\$Test\run$Run"

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
