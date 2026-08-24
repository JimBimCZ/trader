#!/usr/bin/env bash
# Stop Trader. The Postgres volume is left in place.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

docker compose down
echo "Trader stopped. Your portfolio is preserved in the trader-pgdata volume."
echo "To wipe it and start over: docker compose down -v"
