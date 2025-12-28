#!/bin/bash
# Check SearXNG service status

cd "$(dirname "$0")"

echo "=== SearXNG Status ==="
echo ""

# Check container status
echo "Containers:"
docker compose ps
echo ""

# Check if service is responding
echo "Health Check:"
if curl -s "http://localhost:8888/search?q=test&format=json" > /dev/null 2>&1; then
    RESULT_COUNT=$(curl -s "http://localhost:8888/search?q=test&format=json" | jq '.results | length')
    echo "  Status: HEALTHY"
    echo "  Test query returned $RESULT_COUNT results"
else
    echo "  Status: NOT RESPONDING"
fi
echo ""

# Show resource usage
echo "Resource Usage:"
docker stats --no-stream searxng searxng-redis 2>/dev/null || echo "  Containers not running"
