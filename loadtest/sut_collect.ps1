<#
.SYNOPSIS
  SYSTEM UNDER TEST machine, step 2 of 2: collect one run's evidence.

.DESCRIPTION
  Run after JMeter has finished on the load generator. Stops the CPU sampler,
  copies this run's service log to service.jsonl, and writes metadata.json
  (model digest, git commit, Ollama version, timings).

  -LoadgenDir: the run folder copied from the load-generator machine
  (results.jtl, jmeter.log, run.properties, loadgen.json). Its files are copied
  into this run's folder. It can also be added later by copying by hand.

.EXAMPLE
  .\loadtest\sut_collect.ps1 -Model tev1:4b -Test mixed -Run 1 -LoadgenDir D:\from-friend\run1
#>
param(
    [Parameter(Mandatory = $true)][string]$Model,
    [Parameter(Mandatory = $true)][string]$Test,
    [Parameter(Mandatory = $true)][int]$Run,
    [string]$LoadgenDir = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$modelDir = $Model -replace '[^A-Za-z0-9._-]', '-'
$outDir = Join-Path $root "results\$modelDir\$Test\run$Run"
$startFile = Join-Path $outDir 'sut_start.json'
if (-not (Test-Path $startFile)) { throw "$startFile not found. Was sut_prepare.ps1 run for this model/test/run?" }
$start = Get-Content $startFile -Raw | ConvertFrom-Json

# Stop CPU sampling
if ($start.cpu_sampler_pid) {
    Stop-Process -Id $start.cpu_sampler_pid -ErrorAction SilentlyContinue
}

# Service log: the file this service start created
$serviceStart = [datetime]::Parse($start.service_started).ToLocalTime()
$log = Get-ChildItem (Join-Path $root 'logs') -Filter '*.jsonl' |
    Where-Object { $_.LastWriteTime -ge $serviceStart } |
    Sort-Object LastWriteTime | Select-Object -Last 1
$digest = $null
$requests = 0
if ($log) {
    Copy-Item $log.FullName (Join-Path $outDir 'service.jsonl')
    $digest = (Get-Content $log.FullName -TotalCount 1 | ConvertFrom-Json).model_digest
    $requests = (Get-Content $log.FullName | Select-Object -Skip 1 | Measure-Object -Line).Lines
} else {
    Write-Warning "No service log found in logs\ since $serviceStart."
}

# Load generator's files
if ($LoadgenDir -ne '') {
    if (-not (Test-Path $LoadgenDir)) { throw "$LoadgenDir not found." }
    Copy-Item (Join-Path $LoadgenDir '*') $outDir -Force
}
$jtl = Join-Path $outDir 'results.jtl'
$samples = if (Test-Path $jtl) { (Get-Content $jtl | Measure-Object -Line).Lines - 1 } else { $null }

[ordered]@{
    model                  = $Model
    model_digest           = $digest
    ollama_api             = $start.ollama_api
    test                   = $Test
    run                    = $Run
    service_started        = $start.service_started
    sut_ready              = $start.sut_ready
    collected              = (Get-Date).ToUniversalTime().ToString('o')
    sut_hostname           = $start.sut_hostname
    git_commit             = $start.git_commit
    git_dirty              = $start.git_dirty
    ollama_version         = $start.ollama_version
    service_log            = if ($log) { $log.Name } else { $null }
    service_log_requests   = $requests
    jtl_samples            = $samples
} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $outDir 'metadata.json')

Write-Host "== Collected: $outDir"
Write-Host "   service log requests (incl. warm-up): $requests"
if ($null -ne $samples) {
    Write-Host "   JMeter samples: $samples"
} else {
    Write-Warning "results.jtl not in $outDir yet. Copy the load generator's run folder here, or rerun with -LoadgenDir."
}
