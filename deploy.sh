#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# Support both Docker Compose v2 (docker compose) and v1 (docker-compose)
if docker compose version &>/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose &>/dev/null; then
  DC="docker-compose"
else
  echo "Error: neither 'docker compose' nor 'docker-compose' found" >&2
  exit 1
fi

echo "Pulling latest changes..."
git pull

echo "Stopping and removing existing container..."
$DC down

echo "Building image..."
$DC build --no-cache

echo "Starting container..."
$DC up -d

echo "Done. Logs:"
$DC logs -f
