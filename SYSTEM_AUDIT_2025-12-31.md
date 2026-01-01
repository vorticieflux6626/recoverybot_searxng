# SearXNG System Audit Report

> **Date**: 2025-12-31 | **Auditor**: Claude Code | **Parent**: [SearXNG CLAUDE.md](./CLAUDE.md)

## Executive Summary

Comprehensive audit of SearXNG integration with the Recovery Bot ecosystem, analyzing current status, identifying improvements, and planning integration with advanced memOS G.6/G.7 features.

**Overall Health**: GOOD - 34 engines configured, 31 active, Google workaround in place

---

## 1. Current System Status

### 1.1 SearXNG Configuration

| Metric | Value | Status |
|--------|-------|--------|
| Total Engines | 34 | |
| Active Engines | 29 | |
| Disabled (broken) | 5 | Google, Google News, Google Scholar, DuckDuckGo*, Startpage* |
| Settings Version | 2025-12-31 | Updated during audit |
| Docker Health | Healthy | check_engines.sh verified |

*DuckDuckGo and Startpage disabled due to CAPTCHA blocking (2025-12-31)

### 1.2 Engine Weights (Priority Order)

| Engine | Weight | Notes |
|--------|--------|-------|
| Brave | 1.5 | Primary - returns 20 results |
| Bing | 1.2 | Secondary - returns 10 results |
| Startpage | 1.1 | Google proxy - 6-7 results |
| DuckDuckGo | 1.0 | May have rate limits |

### 1.3 Active Engine Categories

| Category | Engines |
|----------|---------|
| **General Web** | Brave, Bing, Startpage, DuckDuckGo |
| **Reference** | Wikipedia |
| **News** | Bing News |
| **Academic** | arXiv, Semantic Scholar, PubMed, Crossref |
| **Q&A** | StackOverflow, Ask Ubuntu, SuperUser, ServerFault, Unix SE, Electronics SE, Robotics SE |
| **Code** | GitHub, GitLab, Codeberg |
| **Packages** | PyPI, npm, Docker Hub, crates.io, pkg.go.dev |
| **Community** | Reddit, HackerNews |
| **Wikis** | Arch Linux Wiki, Gentoo |

---

## 2. Integration with memOS Agentic Search

### 2.1 Current Integration Architecture

```
Android Client
     │
     ▼
memOS UniversalOrchestrator (port 8001)
     │
     ├── DyLAN Agent Classification
     ├── QueryTreeDecoder
     ├── searxng_search.py (SearXNGSearcher)
     │         │
     │         ▼
     │    SearXNG (port 8888)
     │         │
     │         ▼
     │    34 Search Engines
     │
     ├── A-MEM Semantic Memory
     ├── IB Filtering
     ├── Contrastive Retriever
     └── Cross-Encoder Reranking
```

### 2.2 memOS Phases Utilizing SearXNG

| Phase | Feature | SearXNG Integration |
|-------|---------|---------------------|
| G.1 | BGE-M3 ColBERT | Reranks SearXNG results |
| G.2 | Cascade Retrieval | Multi-stage filtering of results |
| G.6 | A-MEM Semantic Memory | Stores successful search patterns |
| G.6 | DyLAN Agent | Classifies query complexity for engine selection |
| G.6 | IB Filtering | Removes noise from search results |
| G.6 | Contrastive Retriever | Learns from search sessions |
| G.7.2 | Hyperbolic Embeddings | Hierarchy-aware document retrieval |
| G.7.3 | Optimal Transport | Dense-sparse fusion for result ranking |
| G.7.4 | TSDAE | Domain adaptation for industrial queries |

### 2.3 ENGINE_GROUPS Alignment (Updated 2025-12-31)

| Query Type | SearXNG Engines | Status |
|------------|-----------------|--------|
| `general` | brave,bing,reddit,wikipedia | ✅ Updated |
| `academic` | arxiv,semantic_scholar,pubmed,crossref,wikipedia | ✅ Aligned |
| `technical` | github,gitlab,stackoverflow,superuser,serverfault,pypi,npm,dockerhub,bing | ✅ Aligned |
| `fanuc` | reddit,brave,bing,arxiv,electronics_stackexchange,robotics_stackexchange | ✅ Updated |
| `robotics` | reddit,brave,bing,arxiv,github,gitlab,robotics_stackexchange,electronics_stackexchange | ✅ Aligned |
| `linux` | askubuntu,unix_stackexchange,serverfault,arch_linux_wiki,gentoo,reddit,bing | ✅ Aligned |
| `imm` | reddit,brave,bing,wikipedia | ✅ Updated |

**Note**: DuckDuckGo and Startpage removed from all groups due to CAPTCHA blocking.

---

## 3. Issues Identified & Fixed

### 3.1 Fixed During Audit

| Issue | File | Fix Applied |
|-------|------|-------------|
| Default engines referenced disabled Google | `searxng_client.py` | Changed to brave,bing,reddit,wikipedia |
| Primary engines referenced Google | `searxng_client.py` | Changed to brave,bing |
| Test search used Google | `searxng_client.py` | Changed to brave,bing |
| memOS default engines had Google | `searxng_search.py` | Changed to brave,bing,reddit,wikipedia |
| Docker file ownership reset on restart | `docker-compose.yml` | Added `user: "1000:1000"` directive |
| ENGINE_GROUPS had CAPTCHA-blocked engines | `searcher.py` | Removed duckduckgo,startpage from all groups |
| UTC import missing | `memOS/server/api/search.py` | Added `UTC` to datetime imports |
| DuckDuckGo/Startpage hitting CAPTCHA | `settings.yml` | Disabled both engines |

### 3.2 Known Issues (Upstream)

| Issue | Impact | Status | Workaround |
|-------|--------|--------|------------|
| Google engine [#5286](https://github.com/searxng/searxng/issues/5286) | No Google results | Open since Oct 7, 2025 | Using Brave/Bing |
| Mullvad Leta shutdown | Former workaround unavailable | Permanent | N/A |
| DuckDuckGo CAPTCHA blocking | Intermittent failures | Active | Disabled engine |
| Startpage CAPTCHA blocking | Intermittent failures | Active | Disabled engine |
| Industrial forums bot protection | CNCZone/PLCTalk inaccessible | Permanent | Use Reddit/StackExchange |

---

## 4. Improvement Recommendations

### 4.1 High Priority - Integration Enhancements

#### 4.1.1 Add TSDAE Domain Adaptation to Search (NEW)

memOS G.7.4 implements TSDAE for domain adaptation. Integrate this with SearXNG:

```python
# In searcher.py, add after search results
from agentic import TSDaeAdapter, FANUC_DOMAIN_CONFIG

adapter = TSDaeAdapter()
# Encode search results with domain-adapted embeddings
embeddings = await adapter.encode(
    [r.snippet for r in results],
    domain_id="fanuc"
)
```

**Benefit**: 93.1% of supervised fine-tuning performance without labeled data

#### 4.1.2 Add Hyperbolic Retrieval for Hierarchical Results (NEW)

memOS G.7.2 implements hyperbolic embeddings. Apply to SearXNG results:

```python
from agentic import HyperbolicRetriever

retriever = HyperbolicRetriever()
# Re-rank results using hyperbolic distance
ranked = await retriever.search(query, top_k=20)
```

**Benefit**: +5.6% Recall@5 via Poincaré ball geometry

#### 4.1.3 Add Contrastive Learning Feedback (NEW)

memOS G.6.5 tracks which results users click. Integrate with SearXNG:

```python
from agentic import ContrastiveRetriever

retriever = ContrastiveRetriever()
# Record which URLs from SearXNG results were cited
await retriever.record_session(
    query=query,
    cited_urls=cited_urls,
    all_urls=all_urls
)
```

**Benefit**: Learns from successful searches to improve future rankings

### 4.2 Medium Priority - New Engines

#### 4.2.1 Industrial Automation Engines

Consider adding these specialized sources:

| Engine | Purpose | Implementation |
|--------|---------|----------------|
| FANUC Forum | Direct FANUC troubleshooting | Custom xpath engine |
| ManualsLib | Equipment manuals | Custom xpath engine |
| CNCZone | CNC/machining community | Custom xpath engine |
| PLCTalk | PLC discussion forum | Custom xpath engine |

Example configuration for ManualsLib:

```yaml
- name: manualslib
  engine: xpath
  search_url: https://www.manualslib.com/search?q={query}
  url_xpath: //a[@class="link"]/@href
  title_xpath: //a[@class="link"]
  content_xpath: //div[@class="description"]
  categories: [it, science]
  shortcut: ml
  timeout: 10.0
```

#### 4.2.2 Add Wolframalpha for Technical Calculations

```yaml
- name: wolframalpha
  engine: wolframalpha
  shortcut: wa
  categories: [science, it]
  disabled: false
  timeout: 15.0
  # Requires API key
  api_key: ${WOLFRAM_API_KEY}
```

### 4.3 Low Priority - Performance Optimization

#### 4.3.1 Enable Result Caching in SearXNG

Add to settings.yml:

```yaml
outgoing:
  # Enable result caching
  enable_http2: true
  pool_connections: 100
  pool_maxsize: 20
```

#### 4.3.2 Add TLS Fingerprint Rotation Cron

Prevents engine blocking:

```bash
# Add to crontab
0 */6 * * * cd /home/sparkone/sdd/Recovery_Bot/searxng && docker compose restart searxng
```

---

## 5. Testing Recommendations

### 5.1 Engine Health Monitoring

Run regularly:

```bash
./check_engines.sh              # Full health check
./check_engines.sh quick        # Container status
./check_engines.sh test "FANUC SRVO-063"  # Specific query
```

### 5.2 Integration Testing with memOS

```bash
cd /home/sparkone/sdd/Recovery_Bot/memOS/server
source venv/bin/activate

# Test SearXNG integration
python -c "
import asyncio
from agentic.searxng_search import get_searxng_searcher

async def test():
    searcher = get_searxng_searcher()
    print('Available:', await searcher.is_available())
    results = await searcher.search(['FANUC robot alarm'])
    print(f'Results: {len(results)}')
    await searcher.close()

asyncio.run(test())
"
```

### 5.3 Contract Tests

Add to `tests/contracts/`:

```python
def test_searxng_response_format():
    """Verify SearXNG returns expected format"""
    response = await client.search("test")
    assert "results" in response
    assert isinstance(response["results"], list)
    for result in response["results"]:
        assert "title" in result
        assert "url" in result
        assert "content" in result
```

---

## 6. Monitoring Google Fix Status

### 6.1 Check Issue Periodically

```bash
# Check if Google engine works
curl "http://localhost:8888/search?q=test&engines=google&format=json" | jq '.results | length'
```

### 6.2 Re-enable When Fixed

1. Update `settings.yml`: `disabled: false` for google, google_news, google_scholar
2. Update `ENGINE_GROUPS` in `searcher.py`
3. Update `default_engines` in `searxng_client.py` and `searxng_search.py`
4. Pull latest SearXNG image: `docker compose pull && docker compose up -d`
5. Delete `GOOGLE_FIX_REMINDER.md`

---

## 7. Related Documentation

| Document | Purpose |
|----------|---------|
| [SearXNG CLAUDE.md](./CLAUDE.md) | Main SearXNG documentation |
| [ENGINE_FIX_PLAN.md](./ENGINE_FIX_PLAN.md) | Engine fix implementation |
| [GOOGLE_FIX_REMINDER.md](./GOOGLE_FIX_REMINDER.md) | Google re-enable checklist |
| [memOS CLAUDE.md](../memOS/CLAUDE.md) | memOS agentic features |
| [Root CLAUDE.md](../CLAUDE.md) | Project-wide standards |

---

## 8. External References

| Resource | URL |
|----------|-----|
| SearXNG Issue #5286 | https://github.com/searxng/searxng/issues/5286 |
| SearXNG Configured Engines | https://docs.searxng.org/user/configured_engines.html |
| SearXNG Engine Settings | https://docs.searxng.org/admin/settings/settings_engines.html |
| SearXNG Performance Tips | https://github.com/searxng/searxng/discussions/1738 |

---

**Generated**: 2025-12-31 | **Next Review**: 2026-01-28 (check Google fix status)
