#!/bin/bash
# Install TLS rotation cron job for SearXNG
# Runs rotate-tls.sh every 6 hours to prevent engine blocking

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROTATE_SCRIPT="${SCRIPT_DIR}/rotate-tls.sh"
CRON_SCHEDULE="0 */6 * * *"

echo "Installing SearXNG TLS rotation cron job..."

# Make rotate script executable
chmod +x "$ROTATE_SCRIPT"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "rotate-tls.sh"; then
    echo "Cron job already exists. Updating..."
    # Remove old entry
    crontab -l 2>/dev/null | grep -v "rotate-tls.sh" | crontab -
fi

# Add new cron job
(crontab -l 2>/dev/null; echo "${CRON_SCHEDULE} ${ROTATE_SCRIPT} # SearXNG TLS rotation") | crontab -

# Verify installation
if crontab -l 2>/dev/null | grep -q "rotate-tls.sh"; then
    echo "Cron job installed successfully!"
    echo ""
    echo "Schedule: Every 6 hours (${CRON_SCHEDULE})"
    echo "Script: ${ROTATE_SCRIPT}"
    echo "Logs: ${SCRIPT_DIR}/logs/tls-rotation.log"
    echo ""
    echo "To view cron jobs: crontab -l"
    echo "To remove: crontab -l | grep -v 'rotate-tls.sh' | crontab -"
else
    echo "ERROR: Failed to install cron job"
    exit 1
fi
