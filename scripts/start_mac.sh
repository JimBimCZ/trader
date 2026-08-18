#!/usr/bin/env bash
# Start Trader. Idempotent: safe to run repeatedly.
#
#   ./scripts/start_mac.sh            build if needed, start, open the browser
#   ./scripts/start_mac.sh --build    force a rebuild
#   ./scripts/start_mac.sh --no-open  do not open a browser
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

URL="http://localhost:8000"
BUILD_FLAG=""
OPEN_BROWSER=1

for arg in "$@"; do
  case "$arg" in
    --build) BUILD_FLAG="--build" ;;
    --no-open) OPEN_BROWSER=0 ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

if [ ! -f .env ]; then
  echo "No .env found. Copying .env.example — add your OPENROUTER_API_KEY to it."
  cp .env.example .env
fi

mkdir -p db

echo "Starting Trader…"
docker compose up -d $BUILD_FLAG

printf "Waiting for the app to become healthy"
for _ in $(seq 1 60); do
  if curl -fsS "$URL/api/health" >/dev/null 2>&1; then
    echo " ready."
    echo "Trader is running at $URL"
    [ "$OPEN_BROWSER" -eq 1 ] && command -v open >/dev/null && open "$URL"
    exit 0
  fi
  printf "."
  sleep 1
done

echo
echo "The app did not become healthy in time. Recent logs:" >&2
docker compose logs --tail 40 trader >&2
exit 1
