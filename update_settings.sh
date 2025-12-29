#!/bin/bash
# Update SearXNG settings with academic engines
# Run with: sudo ./update_settings.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETTINGS_DIR="$SCRIPT_DIR/searxng"
NEW_SETTINGS="/tmp/searxng_settings_new.yml"

echo "Updating SearXNG settings..."

# Check if new settings exist
if [ ! -f "$NEW_SETTINGS" ]; then
    echo "Error: $NEW_SETTINGS not found"
    exit 1
fi

# Backup current settings
if [ -f "$SETTINGS_DIR/settings.yml" ]; then
    cp "$SETTINGS_DIR/settings.yml" "$SETTINGS_DIR/settings.yml.backup"
    echo "Backed up current settings to settings.yml.backup"
fi

# Copy new settings
cp "$NEW_SETTINGS" "$SETTINGS_DIR/settings.yml"
chown 1000:1000 "$SETTINGS_DIR/settings.yml"
chmod 644 "$SETTINGS_DIR/settings.yml"

echo "Settings updated successfully!"
echo ""
echo "New academic engines added:"
echo "  - semantic scholar (ss)"
echo "  - pubmed (pm)"
echo "  - base (ba)"
echo "  - crossref (cr)"
echo ""
echo "New technical engines added:"
echo "  - dockerhub (dh)"
echo "  - npm"
echo "  - pypi (pip)"
echo ""
echo "Restart SearXNG to apply changes:"
echo "  cd $SCRIPT_DIR && docker compose restart"
