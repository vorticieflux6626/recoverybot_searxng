# SearXNG Improvement Plan

> **Created**: 2025-12-31 | **Based on**: 4-agent deep research | **Status**: Active

## Executive Summary

Research from 4 expert agents covering: engine optimization, anti-detection strategies, alternative search APIs, and agentic search architecture patterns. This plan prioritizes improvements by impact and implementation complexity.

---

## Research Findings Summary

### Agent 1: SearXNG Engine Optimization
- **Google bug #5286**: Still open (Oct 2025), no official fix
- **Mullvad Leta**: Shut down Nov 27, 2025 - no longer a workaround
- **DuckDuckGo/Startpage**: CAPTCHA issues confirmed, use lower weights
- **Recommended engines**: Brave (1.5x), Mojeek (1.1x), Yep (1.0x)

### Agent 2: Anti-Detection Strategies
- **Tor integration**: Docker-based with socks5://tor:9050
- **Proxy rotation**: Native SearXNG round-robin support
- **TLS fingerprinting**: curl_cffi for browser impersonation
- **Residential proxies**: Bright Data, Oxylabs options

### Agent 3: Alternative Search APIs
- **Brave Search API**: 2K free/month, best Google alternative
- **OpenAlex**: 100% FREE, 100K/day, academic focus
- **Tavily**: 1K free/month, AI-optimized for RAG
- **Meilisearch/Typesense**: Local document search

### Agent 4: Agentic Architecture
- **RRF (Reciprocal Rank Fusion)**: Better result merging
- **Circuit breaker pattern**: Graceful degradation
- **Semantic caching**: 60-80% speedup for similar queries
- **Query routing**: Pattern + LLM classification

---

## Prioritized Improvement Plan

### Phase 1: Immediate (This Week) - Engine Reliability

| Task | Effort | Impact | Status |
|------|--------|--------|--------|
| Add Mojeek engine | Low | High | ✅ Done (10 results) |
| Add Yep engine | Low | High | ❌ Blocked (HTTP 403) |
| Fix duplicate entries in settings.yml | Low | Medium | ✅ Done |
| Add Tor container to docker-compose | Medium | High | ✅ Done (30s timeout, Reddit blocks Tor) |
| Lower DuckDuckGo/Startpage weights | Low | Medium | ✅ Done |

**Configuration for Mojeek and Yep:**
```yaml
# Add to settings.yml engines section
- name: mojeek
  engine: mojeek
  shortcut: mj
  weight: 1.1
  disabled: false
  timeout: 8.0

- name: yep
  engine: yep
  shortcut: yep
  weight: 1.0
  disabled: false
  timeout: 5.0
  search_type: web
```

**Tor Container Addition:**
```yaml
# Add to docker-compose.yml
tor:
  container_name: searxng-tor
  image: osminogin/tor-simple:latest
  restart: unless-stopped
  networks:
    - searxng
  healthcheck:
    test: ["CMD-SHELL", "nc -z localhost 9050 || exit 1"]
    interval: 60s
    timeout: 15s
    retries: 3
    start_period: 30s
```

---

### Phase 2: Short-Term (1-2 Weeks) - Fallback & APIs

| Task | Effort | Impact | Status |
|------|--------|--------|--------|
| Register for Brave Search API | Low | High | ⏭️ Skipped (using Tor) |
| Register for Tavily API (1K free) | Low | High | ⏭️ Skipped (using Tor) |
| Add OpenAlex as custom engine | Medium | High | ✅ Done (json_engine) |
| Implement circuit breaker in memOS | Medium | High | ✅ Done (intelligent_throttler.py) |
| Add RRF to result fusion | Medium | High | ✅ Done (result_fusion.py) |
| **Intelligent Request Throttling** | Medium | High | ✅ Done |

**Throttling Implementation (2025-12-31):**
- Human-like Poisson-distributed delays
- Exponential backoff with full jitter (AWS pattern)
- Per-engine circuit breaker
- Tor SOCKS5 proxy integration

**Brave Search API Integration (memOS):**
```python
# Add to memOS/server/agentic/brave_search.py
import httpx

class BraveSearcher:
    """Direct Brave Search API for fallback."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.search.brave.com/res/v1/web/search"

    async def search(self, query: str, count: int = 20):
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.base_url,
                params={"q": query, "count": count},
                headers={"X-Subscription-Token": self.api_key}
            )
            return response.json()["web"]["results"]
```

---

### Phase 3: Medium-Term (2-4 Weeks) - Caching & Quality

| Task | Effort | Impact | Status |
|------|--------|--------|--------|
| Implement semantic cache layer | High | Very High | ✅ Done (semantic_cache.py + Qdrant) |
| Add search quality metrics (MRR, NDCG) | Medium | Medium | ✅ Done (search_metrics.py) |
| Implement query router (pattern + LLM) | Medium | High | ✅ Done (query_router.py) |
| Add feedback loop for preset learning | Medium | Medium | Pending |

**Query Router Features (2025-01-01):**
- 8 query types: academic, technical, code, troubleshooting, industrial, medical, news, general
- Pattern-based classification (no LLM required)
- Automatic engine group selection
- Confidence scoring for routing decisions

**Semantic Cache Architecture (Implemented 2026-01-01):**
```
L1: Exact Hash (Redis)     → O(1) lookup, ~0.5ms latency
L2: Semantic (Qdrant)      → nomic-embed-text (768-dim) @ 0.80 threshold, ~34ms
L3: Fresh Search           → Store in L1 + L2, 1-2s latency
```

**Cache Configuration:**
- `semantic_cache.py` - Three-layer cache implementation
- `docker-compose.yml` - Added Qdrant container (port 6333)
- Embedding model: nomic-embed-text via Ollama
- L1 TTL: 1 hour, L2 TTL: 24 hours

---

### Phase 4: Long-Term (1-3 Months) - Advanced Features

| Task | Effort | Impact | Status |
|------|--------|--------|--------|
| Deploy Meilisearch for local FANUC docs | High | High | Pending |
| TLS fingerprint randomization (curl_cffi) | High | Medium | Pending |
| Residential proxy integration | Medium | Medium | Pending |
| Google Programmable Search for industrial sites | Medium | Medium | Pending |
| Cross-encoder reranking for search results | High | Medium | Pending |

---

## Engine Status Quick Reference

| Engine | Status | Weight | Notes |
|--------|--------|--------|-------|
| **Brave** | ✅ Working | 1.5 | Primary engine |
| **Bing** | ✅ Working | 1.2 | Secondary |
| **Mojeek** | ✅ Working | 1.1 | Independent index, 10 results |
| **Yep** | ❌ Blocked | 1.0 | HTTP 403 bot protection |
| **Reddit** | ✅ Working | 1.2 | Great for troubleshooting |
| **Wikipedia** | ✅ Working | 1.0 | Reference |
| DuckDuckGo | ⚠️ CAPTCHA | 0.7 | Disabled |
| Startpage | ⚠️ CAPTCHA | 0.8 | Disabled |
| Google | ❌ Broken | - | Bug #5286 |
| Qwant | ❌ Broken | - | CAPTCHA |

---

## Alternative API Quick Reference

| API | Free Tier | Best For | Priority |
|-----|-----------|----------|----------|
| **Brave Search** | 2K/month | General web | High |
| **OpenAlex** | Unlimited | Academic | High |
| **Tavily** | 1K/month | AI/RAG | High |
| **Semantic Scholar** | Unlimited | Research | Already integrated |
| **Serper** | 2.5K signup | Google SERP | Medium |
| **Exa AI** | $10 credit | Semantic | Medium |
| **Meilisearch** | Self-hosted | Local docs | Medium |

---

## Architecture Documents Created

1. **`SYSTEM_AUDIT_2025-12-31.md`** - Comprehensive audit findings
2. **`memOS/server/agentic/METASEARCH_INTEGRATION_ARCHITECTURE.md`** - Architecture patterns
3. **`tests/test_contracts.py`** - 16 contract tests

---

## Monitoring Checklist

### Weekly
- [ ] Run `./check_engines.sh` to verify engine health
- [ ] Check `logs/tls-rotation.log` for rotation status
- [ ] Monitor GitHub issue #5286 for Google fix

### Monthly
- [ ] Review search quality metrics
- [ ] Check API usage (Brave, Tavily)
- [ ] Update engine weights based on reliability

---

## Related Files

| File | Purpose |
|------|---------|
| `settings.yml` | Engine configuration |
| `docker-compose.yml` | Container setup (includes Tor) |
| `intelligent_throttler.py` | Poisson delays + circuit breaker |
| `result_fusion.py` | RRF/weighted/Borda fusion |
| `query_router.py` | 8-type query classification |
| `search_metrics.py` | Quality metrics tracking |
| `searxng_client.py` | Async Python client |
| `check_engines.sh` | Health monitoring |

## Known Limitations

### Tor Proxy
- **Reddit blocks Tor exit nodes** - Reddit returns "too many requests" when accessed via Tor
- **Increased latency** - ~1.6s avg vs ~1s without Tor (60% slower)
- **Configuration**: `extra_proxy_timeout: 30` required (default 6s too short)
- **Workaround**: Disable Tor for Reddit-heavy queries via engine selection

---

## Sources

### SearXNG
- [GitHub Issue #5286](https://github.com/searxng/searxng/issues/5286) - Google engine bug
- [SearXNG Documentation](https://docs.searxng.org/)
- [Tor Integration Discussion](https://github.com/searxng/searxng/discussions/1665)

### Search APIs
- [Brave Search API](https://brave.com/search/api/)
- [OpenAlex API](https://docs.openalex.org/)
- [Tavily API](https://docs.tavily.com/)

### Architecture
- [Perplexity AI Architecture](https://www.perplexity.ai/api-platform/resources/)
- [OpenSearch RRF](https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/)
- [GPTCache](https://github.com/zilliztech/GPTCache)

---

*Plan generated by Claude Opus 4.5 based on 4-agent deep research*
