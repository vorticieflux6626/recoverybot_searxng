#!/bin/bash
#
# SearXNG Engine Health Check Script
# Checks which engines are returning results and identifies issues
#
# Usage:
#   ./check_engines.sh              # Full health check
#   ./check_engines.sh quick        # Quick status only
#   ./check_engines.sh test "query" # Test specific query
#

set -e

SEARXNG_URL="${SEARXNG_URL:-http://localhost:8888}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== SearXNG Engine Health Check ===${NC}"
echo -e "URL: ${SEARXNG_URL}"
echo ""

# Quick status check
quick_status() {
    echo -e "${YELLOW}Container Status:${NC}"
    docker compose ps 2>/dev/null || echo "Not running via docker compose"
    echo ""

    echo -e "${YELLOW}Service Health:${NC}"
    if curl -s --max-time 5 "${SEARXNG_URL}/healthz" > /dev/null 2>&1; then
        echo -e "  SearXNG: ${GREEN}UP${NC}"
    else
        echo -e "  SearXNG: ${RED}DOWN${NC}"
    fi

    if docker exec searxng-redis valkey-cli ping 2>/dev/null | grep -q PONG; then
        echo -e "  Redis:   ${GREEN}UP${NC}"
    else
        echo -e "  Redis:   ${RED}DOWN${NC}"
    fi
}

# Test engines with a query
test_engines() {
    local query="${1:-test}"
    echo -e "${YELLOW}Testing with query: '${query}'${NC}"
    echo ""

    # Get results and parse
    local result=$(curl -s "${SEARXNG_URL}/search?q=${query}&format=json" 2>/dev/null)

    if [ -z "$result" ]; then
        echo -e "${RED}Error: No response from SearXNG${NC}"
        return 1
    fi

    # Count results per engine
    echo -e "${YELLOW}Results by Engine:${NC}"
    echo "$result" | jq -r '.results[].engine' 2>/dev/null | sort | uniq -c | sort -rn | while read count engine; do
        if [ "$count" -ge 10 ]; then
            echo -e "  ${GREEN}$count${NC} - $engine"
        elif [ "$count" -ge 5 ]; then
            echo -e "  ${YELLOW}$count${NC} - $engine"
        else
            echo -e "  ${RED}$count${NC} - $engine"
        fi
    done

    # Total results
    local total=$(echo "$result" | jq '.results | length' 2>/dev/null)
    echo ""
    echo -e "Total Results: ${GREEN}${total}${NC}"

    # Check for unresponsive engines
    local unresponsive=$(echo "$result" | jq -r '.unresponsive_engines[]?' 2>/dev/null)
    if [ -n "$unresponsive" ]; then
        echo ""
        echo -e "${RED}Unresponsive Engines:${NC}"
        echo "$unresponsive" | while read engine; do
            echo -e "  ${RED}✗${NC} $engine"
        done
    fi
}

# Full health check
full_check() {
    quick_status
    echo ""

    # Test general query
    test_engines "test"
    echo ""

    # Test FANUC query (industrial/robotics)
    echo -e "${BLUE}--- FANUC/Industrial Query ---${NC}"
    test_engines "FANUC+robot+alarm"
    echo ""

    # Test technical query
    echo -e "${BLUE}--- Technical Query ---${NC}"
    test_engines "python+async+tutorial"
    echo ""

    # Check specific engine groups
    echo -e "${BLUE}--- Engine Group Tests ---${NC}"

    echo -e "\n${YELLOW}Stack Exchange:${NC}"
    curl -s "${SEARXNG_URL}/search?q=linux+permissions&format=json&engines=stackoverflow,askubuntu,superuser" 2>/dev/null | \
        jq -r '{count: (.results | length), engines: ([.results[].engine] | unique)}' 2>/dev/null

    echo -e "\n${YELLOW}Code Repositories:${NC}"
    curl -s "${SEARXNG_URL}/search?q=robotics+ROS&format=json&engines=github,gitlab" 2>/dev/null | \
        jq -r '{count: (.results | length), engines: ([.results[].engine] | unique)}' 2>/dev/null

    echo -e "\n${YELLOW}Academic:${NC}"
    curl -s "${SEARXNG_URL}/search?q=machine+learning&format=json&engines=arxiv,semantic_scholar" 2>/dev/null | \
        jq -r '{count: (.results | length), engines: ([.results[].engine] | unique)}' 2>/dev/null

    # Redis stats
    echo ""
    echo -e "${BLUE}--- Redis Statistics ---${NC}"
    docker exec searxng-redis valkey-cli INFO stats 2>/dev/null | grep -E "(keyspace|used_memory|connected)" || echo "Unable to get Redis stats"
}

# Main
case "${1:-full}" in
    quick)
        quick_status
        ;;
    test)
        test_engines "${2:-test}"
        ;;
    full|*)
        full_check
        ;;
esac

echo ""
echo -e "${BLUE}Health check complete.${NC}"
