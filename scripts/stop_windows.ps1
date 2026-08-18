# Stop Trader. The database in .\db is left in place.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

docker compose down
Write-Host "Trader stopped. Your portfolio in .\db is preserved."
