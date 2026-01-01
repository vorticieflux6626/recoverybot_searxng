# SearXNG Self-Hosted Search Server

> **Updated**: 2025-12-31 | **Parent**: [Root CLAUDE.md](../CLAUDE.md) | **Repository**: `recoverybot_searxng`

## Quick Reference

| Action | Command | Notes |
|--------|---------|-------|
| Start Service | `./start.sh` | Starts SearXNG + Redis |
| Stop Service | `./stop.sh` | Stops containers |
| Check Status | `./status.sh` | Health check |
| View Logs | `./logs.sh` | Container logs |
| Test Search | `./test_search.sh "query"` | Test query |
| Check Engines | `./check_engines.sh` | Full engine health |
| Update Settings | `./update_settings.sh` | Backup & update config |

## Critical Rules

1. **NEVER** push from wrong directory - verify with `pwd && git remote -v` first
2. **NEVER** expose port 8888 directly - always use nginx proxy with SSL
3. **ALWAYS** use `format=json` parameter for API responses
4. **ALWAYS** check engine status before debugging empty results - Google is currently DISABLED (bug #5286)

## SSOT Responsibilities

SearXNG is the authoritative source for:

| Data Domain | Description |
|-------------|-------------|
| **Search Engine Configuration** | Engine list, weights, timeouts, categories |
| **Engine Availability Status** | Current health and rate-limit status of each engine |
| **Search Caching** | Redis-backed result caching with TTL |
| **Engine Groups** | Pre-defined groups (academic, technical, general) |

## Dependencies

| Service | Required | Purpose |
|---------|----------|---------|
| Docker | Yes | Container runtime |
| Redis (Valkey) | Yes | Result caching, rate limiting |
| nginx | No | SSL termination, external proxy |
| memOS | No | Consumer of search results |

## Testing

```bash
# Start the service first
./start.sh

# Quick status check
./status.sh

# Test a specific query
./test_search.sh "FANUC SRVO-063 alarm"

# Comprehensive engine health check
./check_engines.sh

# Test specific engine groups
./check_engines.sh test "robotics topic"

# Manual API test
curl "http://localhost:8888/search?q=test&format=json" | jq '.results | length'
```

**Test Scripts:**
- `status.sh` - Container health and port checks
- `test_search.sh` - Single query test with output
- `check_engines.sh` - Full engine availability audit

## Overview

SearXNG is a self-hosted metasearch engine that aggregates results from multiple search providers (Google, Bing, DuckDuckGo, Brave, etc.) without rate limiting or API costs. It serves as the search backend for the Recovery Bot agentic search system.

## Project Location

- **Directory**: `/home/sparkone/sdd/Recovery_Bot/searxng/`
- **Repository**: `recoverybot_searxng`
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
├── CLAUDE.md              # This file - AI assistant guidance
├── ENGINE_FIX_PLAN.md     # Implementation plan for engine fixes
├── GOOGLE_FIX_REMINDER.md # Reminder to re-enable Google when fixed
├── docker-compose.yml     # Docker services (SearXNG + Redis) with health checks
├── nginx.conf             # Reference nginx configuration for proxy
├── .env                   # Environment variables (SEARXNG_SECRET)
├── searxng/
│   └── settings.yml       # SearXNG engine configuration (36 engines, 3 disabled)
├── searxng_client.py      # Python async client for memOS integration
├── start.sh               # Start the service
├── stop.sh                # Stop the service
├── status.sh              # Check service status and health
├── logs.sh                # View container logs
├── test_search.sh         # Test search with specific query
├── check_engines.sh       # Full engine health check script
└── update_settings.sh     # Update settings with backup
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
# Multi-engine search (Google disabled - using Brave/Bing/DuckDuckGo)
curl "http://localhost:8888/search?q=homeless+shelters+kentucky&format=json&engines=brave,bing,duckduckgo"

# News search
curl "http://localhost:8888/search?q=mental+health+services&format=json&categories=news&time_range=week"

# Location-based search
curl "http://localhost:8888/search?q=food+pantry&format=json&categories=general,map"

# Academic search
curl "http://localhost:8888/search?q=machine+learning&format=json&engines=arxiv,semantic_scholar,pubmed"

# Technical search
curl "http://localhost:8888/search?q=python+async+tutorial&format=json&engines=stackoverflow,github,pypi"
```

## Python Client Usage

```python
from searxng_client import SearXNGClient, get_searxng_client

async def search_example():
    client = get_searxng_client()  # Singleton pattern

    # General search
    response = await client.search(
        "addiction recovery services",
        engines=["brave", "bing", "duckduckgo"]
    )

    for result in response.results:
        print(f"[{result.engine}] {result.title}")
        print(f"  URL: {result.url}")
        print(f"  {result.content[:100]}...")

    # Check client stats
    print(f"Stats: {client.stats}")

    # Health check
    health = await client.health_check()
    print(f"Health: {health['status']}")

    await client.close()
```

## memOS Integration

The SearXNG client is integrated into the agentic search pipeline:

- **File**: `/home/sparkone/sdd/Recovery_Bot/memOS/server/agentic/searxng_search.py`
- **Replaces**: DuckDuckGo direct API calls (which were rate-limited)
- **Benefits**: No rate limits, caching allowed, multiple engines

```python
from agentic.searxng_search import SearXNGSearcher, get_searxng_searcher

# Use singleton searcher
searcher = get_searxng_searcher()

# Search with multiple queries (parallel execution)
results = await searcher.search(["query 1", "query 2"])

# Search with specific engine group
results = await searcher.search_with_engines(
    ["FANUC SRVO-063 alarm"],
    engines=["reddit", "brave", "bing", "arxiv"]
)
```

## Configuration

### Engine Status (Updated 2025-12-29)

| Engine | Shortcut | Weight | Status | Notes |
|--------|----------|--------|--------|-------|
| **General Web** |||||
| Google | g | - | **DISABLED** | Upstream bug [#5286](https://github.com/searxng/searxng/issues/5286) |
| Brave | br | 1.5 | **Working Well** | Primary engine, returns 20 results |
| Bing | b | 1.2 | Working | Returns 10 results |
| Startpage | sp | 1.1 | **Working Well** | Google proxy, 6-7 results |
| DuckDuckGo | ddg | 1.0 | Working | May have rate limits |
| **Reference** |||||
| Wikipedia | wp | - | Working | General knowledge, 3s timeout |
| **News** |||||
| Google News | gn | - | **DISABLED** | Depends on broken Google |
| Bing News | bn | - | Working | News category |
| **Maps** |||||
| OpenStreetMap | osm | - | Working | Map category |
| **Academic/Science** |||||
| arXiv | arx | - | Working | 12s timeout, science category |
| Google Scholar | gs | - | **DISABLED** | Depends on broken Google |
| Semantic Scholar | ss | - | Working | Science category |
| PubMed | pm | - | Working | Medical literature, 15s timeout |
| Crossref | cr | - | Working | DOI lookup, 30s timeout |
| **Q&A - Stack Exchange** |||||
| StackOverflow | st | - | Working | IT/Q&A category |
| Ask Ubuntu | ubuntu | - | Working | IT/Q&A category |
| Super User | su | - | Working | IT/Q&A category |
| Server Fault | sf | - | Working | IT/Q&A category |
| Unix StackExchange | unix | - | Working | IT/Q&A category |
| Electronics SE | ee | - | Working | IT/Q&A/Science category |
| Robotics SE | rob | - | Working | IT/Q&A/Science category |
| **Code Repositories** |||||
| GitHub | gh | - | Working | Limited for niche topics, 10s timeout |
| GitLab | gl | - | Working | gitlab.com, 10s timeout |
| Codeberg | cb | - | Working | gitea engine, 10s timeout |
| **Package Managers** |||||
| Docker Hub | dock | - | Working | Container images |
| npm | npmpkg | - | Working | Node packages |
| PyPI | pip | - | Working | Python packages |
| crates.io | crates | - | Working | Rust packages |
| pkg.go.dev | pgo | - | Working | Go packages |
| **Community/Forums** |||||
| Reddit | re | - | **Working Well** | Returns 25 results, great for troubleshooting |
| HackerNews | hn | - | Working | Limited for non-tech topics |
| **Documentation Wikis** |||||
| Arch Linux Wiki | al | - | Working | archlinux engine |
| Gentoo Wiki | ge | - | Working | mediawiki engine |

### Known Issues

1. **Google Engine (BROKEN)**: SearXNG upstream bug [#5286](https://github.com/searxng/searxng/issues/5286) - Google changed their response format. No fix yet. Workaround: Use Brave/Bing instead.

2. **DuckDuckGo/Startpage (CAPTCHA)**: As of 2025-12-31, both engines are hitting CAPTCHAs and returning 0 results. Removed from default ENGINE_GROUPS temporarily. Monitor and re-enable when cleared.

3. **Rate Limiting**: Some engines may trigger CAPTCHAs or rate limits with heavy usage. Container restart may help temporarily: `docker compose restart searxng`

4. **Niche Topics**: HackerNews and GitHub return 0 results for industrial/robotics topics (FANUC, etc.) - they simply don't have much content on these topics.

### Current Working Engines (2025-12-31)

| Engine | Status | Results |
|--------|--------|---------|
| Brave | Working | 15-20 results |
| Bing | Working | 10 results |
| Reddit | Working | 25 results |
| Wikipedia | Working | 1-5 results |
| arXiv | Working | 10+ results |
| Stack Exchange (7) | Working | 10+ results |
| GitHub/GitLab | Working | Variable |
| DuckDuckGo | CAPTCHA | Temporarily disabled |
| Startpage | CAPTCHA | Temporarily disabled |
| Google | Broken | Disabled upstream bug |

### Engine Groups for memOS

The memOS searcher uses these engine groups (defined in `searcher.py`):

```yaml
fanuc: "reddit,brave,bing,startpage,arxiv,electronics_stackexchange,robotics_stackexchange"
robotics: "reddit,brave,bing,arxiv,github,robotics_stackexchange,electronics_stackexchange"
academic: "arxiv,semantic_scholar,pubmed,crossref"
technical: "github,gitlab,stackoverflow,superuser,pypi,npm,dockerhub,bing,startpage"
general: "brave,bing,duckduckgo,wikipedia,startpage"
linux: "askubuntu,unix_stackexchange,archlinux,serverfault,reddit,bing"
```

### Disabled Engines

- Google, Google News, Google Scholar (broken - upstream bug #5286)
- Yahoo (slow, redundant)
- Qwant (unreliable, often blocked)
- Mojeek (limited results)

## Ports

| Service | Internal Port | External Access |
|---------|---------------|-----------------|
| SearXNG | 8888 | via nginx `/search/` |
| Redis | 6379 | internal only |

## Docker Configuration

### Container Resources
- **SearXNG**: 256-512MB memory, 4 workers, 4 threads
- **Redis (Valkey)**: 256MB maxmemory, LRU eviction policy
- **Health Checks**: Both containers have health checks (30s interval)

### Docker Compose Commands
```bash
docker compose up -d          # Start detached
docker compose down           # Stop and remove
docker compose restart        # Restart containers
docker compose pull           # Pull latest images
docker compose logs -f        # Follow logs
docker compose ps             # Show container status
docker compose exec redis valkey-cli  # Redis CLI
```

## nginx Proxy Configuration

The `nginx.conf` file provides a reference for proxying SearXNG through nginx at `/search/`:

```nginx
location /search/ {
    proxy_pass http://127.0.0.1:8888/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # CORS headers for API access
    add_header Access-Control-Allow-Origin "*" always;
    add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;
    add_header Access-Control-Allow-Headers "Content-Type" always;

    # Timeouts
    proxy_connect_timeout 30s;
    proxy_send_timeout 30s;
    proxy_read_timeout 60s;
}
```

**External URL**: `https://technobot.sparkonelabs.com:8443/search/search?q=query&format=json`

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

### Engine Health Check

Run the comprehensive engine check script:
```bash
./check_engines.sh              # Full health check with multiple queries
./check_engines.sh quick        # Quick container status only
./check_engines.sh test "query" # Test specific query
```

### Test Specific Engines

```bash
# Test Stack Exchange
curl "http://localhost:8888/search?q=linux+permissions&engines=askubuntu,stackoverflow&format=json" | jq '.results | length'

# Test Academic
curl "http://localhost:8888/search?q=machine+learning&engines=arxiv,semantic_scholar&format=json" | jq '.results | length'

# Test Code Repositories
curl "http://localhost:8888/search?q=robotics+ROS&engines=github,gitlab&format=json" | jq '.results | length'
```

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

## memOS Integration (December 2025)

SearXNG is deeply integrated with memOS agentic search pipeline (Phases G.1-G.7):

### Integration Architecture

```
Android Client → memOS UniversalOrchestrator (8001)
                        │
                        ├── DyLAN Query Classification
                        ├── QueryTreeDecoder
                        ├── SearXNGSearcher → SearXNG (8888)
                        │                         │
                        │                         └── 31 Active Engines
                        ├── A-MEM Semantic Memory
                        ├── IB Noise Filtering
                        ├── Cross-Encoder Reranking (BGE-M3)
                        ├── Hyperbolic Embeddings (G.7.2)
                        ├── Optimal Transport Fusion (G.7.3)
                        └── TSDAE Domain Adaptation (G.7.4)
```

### memOS Features Leveraging SearXNG

| Feature | Phase | Description |
|---------|-------|-------------|
| DyLAN Agent | G.6.2 | Classifies query complexity to select ENGINE_GROUPS |
| A-MEM Memory | G.6.1 | Stores successful search patterns in SQLite |
| IB Filtering | G.6.4 | Removes noise from search results |
| Contrastive Learning | G.6.5 | Learns from cited URLs to improve rankings |
| Cascade Retrieval | G.2 | Multi-stage filtering with MRL dimensions |
| TSDAE Adaptation | G.7.4 | Domain-specific embeddings for industrial queries |

### ENGINE_GROUPS in memOS

The `searcher.py` defines query-type specific engine groups:

| Query Type | Engines |
|------------|---------|
| `general` | brave,bing,startpage,duckduckgo,wikipedia |
| `academic` | arxiv,semantic_scholar,pubmed,crossref,wikipedia |
| `technical` | github,gitlab,stackoverflow,superuser,serverfault,pypi,npm,dockerhub,bing |
| `fanuc` | reddit,brave,bing,startpage,arxiv,electronics_stackexchange,robotics_stackexchange |
| `robotics` | reddit,brave,bing,arxiv,github,gitlab,robotics_stackexchange,electronics_stackexchange |
| `linux` | askubuntu,unix_stackexchange,serverfault,arch_linux_wiki,gentoo,reddit,bing |
| `imm` | reddit,brave,bing,startpage,wikipedia |

### Integration Files

| File | Purpose |
|------|---------|
| `memOS/server/agentic/searxng_search.py` | SearXNGSearcher class with fallback to DuckDuckGo |
| `memOS/server/agentic/searcher.py` | ENGINE_GROUPS and query type detection |
| `searxng/searxng_client.py` | Low-level SearXNG API client |

### Latest Audit

See [SYSTEM_AUDIT_2025-12-31.md](./SYSTEM_AUDIT_2025-12-31.md) for comprehensive analysis.

## Version History

| Date | Change |
|------|--------|
| 2025-12-31 | Fixed Docker permissions with user: "1000:1000" directive |
| 2025-12-31 | Added industrial forum engines (disabled - bot protection) |
| 2025-12-31 | Documented DuckDuckGo/Startpage CAPTCHA issue and workaround |
| 2025-12-31 | Removed DDG/Startpage from ENGINE_GROUPS in memOS searcher.py |
| 2025-12-31 | Updated default_engines to brave,bing,reddit,wikipedia (CAPTCHA-free) |
| 2025-12-31 | Added memOS Integration section with G.6/G.7 feature documentation |
| 2025-12-31 | Fixed default_engines in searxng_client.py (removed disabled Google) |
| 2025-12-31 | Fixed default_engines in searxng_search.py (removed disabled Google) |
| 2025-12-31 | Created SYSTEM_AUDIT_2025-12-31.md comprehensive audit document |
| 2025-12-29 | Updated engine status table with weights and all 34 engines |
| 2025-12-29 | Added Docker configuration and nginx proxy sections |
| 2025-12-29 | Updated directory structure with all scripts |
| 2025-12-29 | Marked Google/Google News/Google Scholar as DISABLED |
| 2025-12-28 | Added Stack Exchange engines (7 sites) |
| 2025-12-28 | Added code repositories (GitHub, GitLab, Codeberg) |
| 2025-12-28 | Added package managers (PyPI, npm, Docker Hub, crates.io, pkg.go.dev) |
| 2025-12-28 | Added documentation wikis (Arch Linux, Gentoo) |
| 2025-12-28 | Added academic engines (Semantic Scholar, PubMed, Crossref) |
| 2025-12-28 | Added engine weights (Brave 1.5, Bing 1.2, Startpage 1.1) |
| 2025-12-28 | Implemented Docker health checks and Redis optimization |
| 2025-12-28 | Created check_engines.sh monitoring script |
| 2025-12-28 | Documented engine status - Google broken (upstream bug #5286) |
| 2025-12-28 | Initial deployment for Recovery Bot |
