#!/bin/bash
# Start SearXNG service

cd "$(dirname "$0")"

echo "Starting SearXNG..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker is not running"
    exit 1
fi

# Start containers
docker compose up -d

# Wait for startup
echo "Waiting for SearXNG to start..."
sleep 5

# Check health
if curl -s "http://localhost:8888/search?q=test&format=json" > /dev/null 2>&1; then
    echo "SearXNG is running at http://localhost:8888"
    echo "JSON API: curl 'http://localhost:8888/search?q=test&format=json'"
else
    echo "Warning: SearXNG may not be fully ready yet"
    echo "Check logs with: docker compose logs searxng"
fi
