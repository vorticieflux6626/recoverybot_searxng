#!/bin/bash
# Test SearXNG search

QUERY="${1:-test query}"
FORMAT="${2:-json}"

echo "=== SearXNG Search Test ==="
echo "Query: $QUERY"
echo ""

# URL encode the query
ENCODED_QUERY=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$QUERY'))")

# Perform search
echo "Searching..."
RESULT=$(curl -s "http://localhost:8888/search?q=$ENCODED_QUERY&format=$FORMAT&engines=google,bing,duckduckgo")

if [ "$FORMAT" = "json" ]; then
    # Parse JSON result
    RESULT_COUNT=$(echo "$RESULT" | jq '.results | length')
    echo ""
    echo "Found $RESULT_COUNT results"
    echo ""
    echo "Top 5 results:"
    echo "$RESULT" | jq -r '.results[:5][] | "[\(.engine)] \(.title)\n  URL: \(.url)\n  \(.content[:100])...\n"'

    echo "Engines used:"
    echo "$RESULT" | jq -r '.results[].engine' | sort | uniq -c | sort -rn
else
    echo "$RESULT"
fi
