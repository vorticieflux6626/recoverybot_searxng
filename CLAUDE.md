# SearXNG Self-Hosted Search Server

## Overview

SearXNG is a self-hosted metasearch engine that aggregates results from multiple search providers (Google, Bing, DuckDuckGo, Brave, etc.) without rate limiting or API costs. It serves as the search backend for the Recovery Bot agentic search system.

## Project Location

- **Directory**: `/home/sparkone/sdd/Recovery_Bot/searxng/`
- **Part of**: Recovery Bot monorepo (`recoverybot_server`)
- **Related**: memOS agentic search (`/home/sparkone/sdd/Recovery_Bot/memOS/server/agentic/`)

## Architecture

```
technobot.sparkonelabs.com:8443
├── /                  → Open-WebUI (port 8080)
├── /ollama/           → Ollama API (port 11434)
├── /memOS/            → memOS Quest/Memory API (port 8001)
└── /search/           → SearXNG JSON API (port 8888)  ← THIS SERVICE
```

## Directory Structure

```
/home/sparkone/sdd/Recovery_Bot/searxng/
├── CLAUDE.md              # This file
├── docker-compose.yml     # Docker services (SearXNG + Redis)
├── .env                   # Environment variables (SECRET_KEY)
├── searxng/
│   ├── settings.yml       # SearXNG configuration
│   └── limiter.toml       # Rate limiter config (optional)
├── searxng_client.py      # Python client for memOS integration
├── start.sh               # Start the service
├── stop.sh                # Stop the service
├── status.sh              # Check service status
├── logs.sh                # View logs
└── test_search.sh         # Test search functionality
```

## Quick Commands

```bash
# Start SearXNG
cd /home/sparkone/sdd/Recovery_Bot/searxng
./start.sh

# Stop SearXNG
./stop.sh

# Check status
./status.sh

# View logs
./logs.sh

# Test search
./test_search.sh "addiction recovery kentucky"

# Manual Docker commands
docker compose up -d        # Start in background
docker compose down         # Stop
docker compose logs -f      # Follow logs
docker compose restart      # Restart
```

## API Usage

### Basic JSON Search

```bash
# Local (direct)
curl "http://localhost:8888/search?q=test&format=json" | jq

# Via nginx proxy
curl "https://technobot.sparkonelabs.com:8443/search/search?q=test&format=json" | jq
```

### Search Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `q` | Query string | `q=addiction+recovery` |
| `format` | Output format | `format=json` |
| `engines` | Specific engines | `engines=google,bing` |
| `categories` | Search categories | `categories=general,news` |
| `language` | Language code | `language=en-US` |
| `time_range` | Time filter | `time_range=month` |
| `pageno` | Page number | `pageno=2` |
| `safesearch` | Safe search level | `safesearch=0` |

### Example Queries

```bash
# Multi-engine search
curl "http://localhost:8888/search?q=homeless+shelters+kentucky&format=json&engines=google,bing,duckduckgo"

# News search
curl "http://localhost:8888/search?q=mental+health+services&format=json&categories=news&time_range=week"

# Location-based search
curl "http://localhost:8888/search?q=food+pantry&format=json&categories=general,map"
```

## Python Client Usage

```python
from searxng_client import SearXNGClient

async def search_example():
    client = SearXNGClient()

    # General search
    results = await client.search("addiction recovery services")

    # Recovery-specific search
    shelters = await client.search_recovery_services("homeless")

    await client.close()
```

## memOS Integration

The SearXNG client is integrated into the agentic search pipeline:

- **File**: `/home/sparkone/sdd/Recovery_Bot/memOS/server/agentic/searxng_search.py`
- **Replaces**: DuckDuckGo direct API calls (which were rate-limited)
- **Benefits**: No rate limits, caching allowed, multiple engines

## Configuration

### Enabled Search Engines

| Engine | Shortcut | Status |
|--------|----------|--------|
| Google | g | Enabled |
| Bing | b | Enabled |
| DuckDuckGo | ddg | Enabled |
| Brave | br | Enabled |
| Wikipedia | wp | Enabled |
| Google News | gn | Enabled |
| Bing News | bn | Enabled |
| OpenStreetMap | osm | Enabled |

### Disabled Engines

- Yahoo (slow, redundant)
- Qwant (unreliable)

## Ports

| Service | Internal Port | External Access |
|---------|---------------|-----------------|
| SearXNG | 8888 | via nginx `/search/` |
| Redis | 6379 | internal only |

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker compose logs searxng

# Fix permissions
sudo chown -R 1000:1000 ./searxng
```

### No JSON Output

```bash
# Verify format is enabled
grep -A 5 "formats:" ./searxng/settings.yml
```

### Empty Results

```bash
# Check which engines are working
curl "http://localhost:8888/search?q=test&format=json" | jq '.results[] | .engine' | sort | uniq -c
```

### Rate Limited by Upstream

Rotate user agents or add proxy configuration in `settings.yml`.

## Maintenance

### Update SearXNG

```bash
docker compose pull
docker compose up -d
```

### Clear Redis Cache

```bash
docker compose exec redis redis-cli FLUSHALL
```

### Backup Configuration

```bash
cp -r searxng/ searxng-backup-$(date +%Y%m%d)/
```

## Security

- SearXNG binds to `127.0.0.1:8888` (local only)
- External access requires nginx proxy with SSL
- No authentication by default (internal use only)
- Add nginx basic auth if exposing publicly

## Related Documentation

- [SearXNG Official Docs](https://docs.searxng.org/)
- [SearXNG GitHub](https://github.com/searxng/searxng)
- [Docker Hub](https://hub.docker.com/r/searxng/searxng)
- [Recovery Bot CLAUDE.md](../CLAUDE.md)
- [memOS CLAUDE.md](../memOS/CLAUDE.md)

## Version History

| Date | Change |
|------|--------|
| 2025-12-28 | Initial deployment for Recovery Bot |
