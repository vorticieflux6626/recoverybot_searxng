#!/bin/bash
# View SearXNG logs

cd "$(dirname "$0")"

# Default to following logs
FOLLOW="${1:--f}"

if [ "$FOLLOW" = "-f" ]; then
    echo "Following SearXNG logs (Ctrl+C to stop)..."
    docker compose logs -f --tail=100 searxng
else
    echo "Last 100 log lines:"
    docker compose logs --tail=100 searxng
fi
