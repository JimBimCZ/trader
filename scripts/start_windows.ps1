# Start Trader. Idempotent: safe to run repeatedly.
#
#   .\scripts\start_windows.ps1            build if needed, start, open browser
#   .\scripts\start_windows.ps1 -Build     force a rebuild
#   .\scripts\start_windows.ps1 -NoOpen    do not open a browser
param([switch]$Build, [switch]$NoOpen)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$url = "http://localhost:8000"

if (-not (Test-Path ".env")) {
    Write-Host "No .env found. Copying .env.example - add your OPENROUTER_API_KEY to it."
    Copy-Item ".env.example" ".env"
}

New-Item -ItemType Directory -Force -Path "db" | Out-Null

Write-Host "Starting Trader..."
if ($Build) { docker compose up -d --build } else { docker compose up -d }

Write-Host -NoNewline "Waiting for the app to become healthy"
foreach ($i in 1..60) {
    try {
        Invoke-WebRequest -Uri "$url/api/health" -UseBasicParsing -TimeoutSec 2 | Out-Null
        Write-Host " ready."
        Write-Host "Trader is running at $url"
        if (-not $NoOpen) { Start-Process $url }
        exit 0
    } catch {
        Write-Host -NoNewline "."
        Start-Sleep -Seconds 1
    }
}

Write-Host ""
Write-Error "The app did not become healthy in time. Recent logs:"
docker compose logs --tail 40 trader
exit 1
