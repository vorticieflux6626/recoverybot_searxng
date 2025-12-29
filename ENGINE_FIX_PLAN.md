# SearXNG Engine Fix Plan

Based on research from 4 sub-agents with comprehensive web searches and documentation analysis.

## Executive Summary

**Google Engine Status**: BROKEN (upstream bug #5286, since Oct 7, 2025) - No fix timeline.
**Mullvad Leta**: SHUT DOWN (Nov 27, 2025) - Former workaround no longer available.
**Recommended Strategy**: Disable Google, prioritize Brave/Bing/Startpage, add Stack Exchange network.

---

## Phase 1: Immediate Fixes (Today)

### 1.1 Disable Google Engine

Google engine broken due to upstream SearXNG bug #5286. No fix available.

```yaml
# In searxng/settings.yml - change:
- name: google
  disabled: true  # Was: false
```

### 1.2 Add Startpage to ENGINE_GROUPS

Startpage is working but not in memOS engine groups:

```python
# In memOS/server/agentic/searcher.py - update:
ENGINE_GROUPS = {
    "general": "brave,bing,startpage,duckduckgo,wikipedia",
    "fanuc": "reddit,brave,bing,startpage,arxiv",
    "technical": "github,stackoverflow,pypi,npm,dockerhub,bing,startpage",
}
```

### 1.3 Add Engine Weights

Prioritize reliable engines with weights:

```yaml
engines:
  - name: brave
    weight: 1.5
    disabled: false
  - name: bing
    weight: 1.2
    disabled: false
  - name: startpage
    weight: 1.1
    disabled: false
```

---

## Phase 2: Add Stack Exchange Engines (This Week)

### 2.1 Q&A Engines for Technical Topics

Add these to `searxng/settings.yml`:

```yaml
# Stack Exchange Network
- name: askubuntu
  engine: stackexchange
  shortcut: ubuntu
  api_site: 'askubuntu'
  categories: [it, q&a]
  disabled: false

- name: superuser
  engine: stackexchange
  shortcut: su
  api_site: 'superuser'
  categories: [it, q&a]
  disabled: false

- name: serverfault
  engine: stackexchange
  shortcut: sf
  api_site: 'serverfault'
  categories: [it, q&a]
  disabled: false

- name: unix stackexchange
  engine: stackexchange
  shortcut: unix
  api_site: 'unix'
  categories: [it, q&a]
  disabled: false

- name: electronics stackexchange
  engine: stackexchange
  shortcut: ee
  api_site: 'electronics'
  categories: [it, q&a, science]
  disabled: false

- name: robotics stackexchange
  engine: stackexchange
  shortcut: rob
  api_site: 'robotics'
  categories: [it, q&a, science]
  disabled: false
```

### 2.2 Update memOS Engine Groups

```python
ENGINE_GROUPS = {
    "fanuc": "reddit,brave,bing,startpage,arxiv,electronics_stackexchange,robotics_stackexchange",
    "robotics": "reddit,brave,bing,arxiv,github,robotics_stackexchange,electronics_stackexchange",
    "technical": "github,stackoverflow,superuser,serverfault,unix_stackexchange,pypi,npm,bing",
    "linux": "askubuntu,unix_stackexchange,serverfault,reddit,bing",
    "qa": "stackoverflow,superuser,askubuntu,serverfault,unix_stackexchange,reddit",
}
```

---

## Phase 3: Add Code Repository Engines (Next Week)

### 3.1 GitLab

```yaml
- name: gitlab
  engine: gitlab
  base_url: https://gitlab.com
  shortcut: gl
  categories: [it, repos]
  disabled: false
  timeout: 10.0
```

### 3.2 Codeberg

```yaml
- name: codeberg
  engine: gitea
  base_url: https://codeberg.org
  shortcut: cb
  categories: [it, repos]
  disabled: false
  timeout: 10.0
```

### 3.3 Bitbucket

```yaml
- name: bitbucket
  engine: xpath
  paging: true
  search_url: https://bitbucket.org/repo/all/{pageno}?name={query}
  url_xpath: //article[@class="repo-summary"]//a[@class="repo-link"]/@href
  title_xpath: //article[@class="repo-summary"]//a[@class="repo-link"]
  content_xpath: //article[@class="repo-summary"]/p
  categories: [it, repos]
  timeout: 4.0
  shortcut: bb
  disabled: false
```

---

## Phase 4: Performance Optimization

### 4.1 Redis Configuration

Update `docker-compose.yml`:

```yaml
redis:
  command: >
    valkey-server
    --save 30 1
    --loglevel warning
    --maxmemory 256mb
    --maxmemory-policy allkeys-lru
    --tcp-keepalive 300
```

### 4.2 Per-Engine Timeouts

```yaml
engines:
  # Fast engines (2-4s)
  - name: wikipedia
    timeout: 3.0
  - name: duckduckgo
    timeout: 4.0

  # Standard engines (6-8s)
  - name: brave
    timeout: 6.0
  - name: bing
    timeout: 6.0

  # Academic/slow engines (10-15s)
  - name: arxiv
    timeout: 12.0
  - name: semantic_scholar
    timeout: 12.0
  - name: pubmed
    timeout: 15.0
```

### 4.3 TLS Fingerprint Rotation

Add scheduled restarts to avoid Google-style blocking:

```bash
# Add to crontab:
0 */6 * * * cd /home/sparkone/sdd/Recovery_Bot/searxng && docker compose restart searxng
```

---

## Phase 5: Monitoring & Health Checks

### 5.1 Docker Health Checks

Add to `docker-compose.yml`:

```yaml
searxng:
  healthcheck:
    test: ["CMD", "wget", "-q", "--spider", "http://localhost:8080/healthz"]
    interval: 30s
    timeout: 10s
    retries: 3

redis:
  healthcheck:
    test: ["CMD", "valkey-cli", "ping"]
    interval: 30s
    timeout: 5s
    retries: 3
```

### 5.2 Engine Status Script

Create `check_engines.sh`:

```bash
#!/bin/bash
echo "=== SearXNG Engine Status ==="
curl -s "http://localhost:8888/search?q=test&format=json" | \
  jq '.results[] | .engine' | sort | uniq -c | sort -rn
echo ""
echo "=== Unresponsive Engines ==="
curl -s "http://localhost:8888/search?q=test&format=json" | \
  jq '.unresponsive_engines'
```

---

## Engine Status Summary

| Engine | Status | Action | Priority |
|--------|--------|--------|----------|
| Google | BROKEN | Disable | P0 |
| Brave | Working Well | Keep enabled, add weight 1.5 | P0 |
| Bing | Working | Keep enabled, add weight 1.2 | P0 |
| Startpage | Working Well | Add to ENGINE_GROUPS | P0 |
| DuckDuckGo | Working (may rate limit) | Keep enabled | P1 |
| Reddit | Working Well | Keep enabled for troubleshooting | P1 |
| Stack Exchange | Not configured | Add 6 engines | P1 |
| GitLab/Codeberg | Not configured | Add for code search | P2 |
| arXiv/Semantic Scholar | Working | Keep enabled | P1 |
| HackerNews | Working (limited content) | Keep for tech news | P2 |
| GitHub | Working (limited for niche) | Keep enabled | P1 |

---

## Files to Modify

| File | Changes |
|------|---------|
| `searxng/settings.yml` | Disable Google, add weights, add Stack Exchange, add GitLab/Codeberg |
| `memOS/server/agentic/searcher.py` | Update ENGINE_GROUPS with new engines |
| `searxng/docker-compose.yml` | Add Redis optimization, health checks |
| `searxng/check_engines.sh` | NEW: Engine status monitoring script |

---

## Monitoring Google Fix

Watch for upstream fix:
- Issue: https://github.com/searxng/searxng/issues/5286
- Test: `curl "http://localhost:8888/search?q=test&engines=google&format=json"`
- When fixed: Re-enable Google and add back to ENGINE_GROUPS

---

## Implementation Checklist

### Phase 1 (Today)
- [ ] Disable Google engine in settings.yml
- [ ] Add engine weights (Brave 1.5, Bing 1.2, Startpage 1.1)
- [ ] Update ENGINE_GROUPS with Startpage
- [ ] Restart SearXNG: `docker compose restart`
- [ ] Test: `./test_search.sh "FANUC robot alarm"`

### Phase 2 (This Week)
- [ ] Add 6 Stack Exchange engines to settings.yml
- [ ] Update ENGINE_GROUPS with new Q&A engines
- [ ] Test: `curl "http://localhost:8888/search?q=linux+permissions&engines=askubuntu&format=json"`

### Phase 3 (Next Week)
- [ ] Add GitLab, Codeberg, Bitbucket engines
- [ ] Update ENGINE_GROUPS with code repositories
- [ ] Test: `curl "http://localhost:8888/search?q=robotics+ROS&engines=gitlab&format=json"`

### Phase 4 (Optimization)
- [ ] Update Redis configuration in docker-compose.yml
- [ ] Add per-engine timeouts to settings.yml
- [ ] Set up TLS fingerprint rotation cron job

### Phase 5 (Monitoring)
- [ ] Add Docker health checks
- [ ] Create check_engines.sh script
- [ ] Test health endpoints

---

## Research Sources

- SearXNG GitHub Issue #5286 (Google broken)
- SearXNG Documentation (docs.searxng.org)
- Mullvad Leta shutdown notice
- SearXNG configured engines list
- Reddit r/selfhosted discussions
- Brave Search API pricing

---

Generated: 2025-12-28
