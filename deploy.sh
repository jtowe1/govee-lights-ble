#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

CONTAINER=motion-controller
IMAGE=motion-controller

echo "Pulling latest changes..."
git pull

echo "Stopping and removing existing container..."
docker stop "$CONTAINER" 2>/dev/null || true
docker rm "$CONTAINER" 2>/dev/null || true

echo "Building image..."
docker build --no-cache -t "$IMAGE" .

echo "Starting container..."
docker run -d \
  --name "$CONTAINER" \
  --restart unless-stopped \
  --network host \
  --privileged \
  -v /var/run/dbus:/var/run/dbus \
  -e WEBHOOK_PORT=8124 \
  "$IMAGE"

echo "Done. Logs:"
docker logs -f "$CONTAINER"
