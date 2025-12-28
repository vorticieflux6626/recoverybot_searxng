#!/bin/bash
# Stop SearXNG service

cd "$(dirname "$0")"

echo "Stopping SearXNG..."
docker compose down

echo "SearXNG stopped"
