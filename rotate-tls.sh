#!/bin/bash
# TLS Fingerprint Rotation for SearXNG
# Restarts the container to get a new TLS fingerprint, preventing engine blocking.
# Run via cron every 6 hours: 0 */6 * * * /path/to/rotate-tls.sh
#
# This helps avoid detection by search engines that track TLS fingerprints.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/logs/tls-rotation.log"

# Ensure log directory exists
mkdir -p "${SCRIPT_DIR}/logs"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

log "Starting TLS rotation..."

cd "$SCRIPT_DIR"

# Check if container is running
if ! docker compose ps --status running | grep -q searxng; then
    log "SearXNG not running, skipping rotation"
    exit 0
fi

# Restart the container
if docker compose restart searxng >> "$LOG_FILE" 2>&1; then
    log "SearXNG container restarted successfully"

    # Wait for health check
    sleep 10

    # Verify it's working
    if curl -s "http://localhost:8888/search?q=test&format=json" | grep -q '"results"'; then
        log "Health check passed - TLS rotation complete"
    else
        log "WARNING: Health check failed after restart"
    fi
else
    log "ERROR: Failed to restart SearXNG container"
    exit 1
fi
