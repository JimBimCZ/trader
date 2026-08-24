# Stop Trader. The Postgres volume is left in place.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

docker compose down
Write-Host "Trader stopped. Your portfolio is preserved in the trader-pgdata volume."
Write-Host "To wipe it and start over: docker compose down -v"
