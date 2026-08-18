#!/usr/bin/env bash
# Stop Trader. The database in ./db is left in place.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

docker compose down
echo "Trader stopped. Your portfolio in ./db is preserved."
