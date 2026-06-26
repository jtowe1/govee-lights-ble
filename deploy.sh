#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "Pulling latest changes..."
git pull

echo "Stopping and removing existing container..."
docker compose down

echo "Building image..."
docker compose build --no-cache

echo "Starting container..."
docker compose up -d

echo "Done. Logs:"
docker compose logs -f
