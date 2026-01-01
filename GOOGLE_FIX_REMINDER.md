# Google Engine Fix Reminder

> **Updated**: 2025-12-30 | **Parent**: [SearXNG CLAUDE.md](./CLAUDE.md) | **Root**: [Project CLAUDE.md](../CLAUDE.md)

| Field | Value |
|-------|-------|
| Created | 2025-12-28 |
| Review Date | 2026-01-28 (1 month from now) |
| Issue | [#5286](https://github.com/searxng/searxng/issues/5286) |

## Current Status

Google engine disabled due to upstream SearXNG bug #5286:
- Google changed their response format/HTML structure
- SearXNG's parser broken since October 7, 2025
- No fix merged as of December 28, 2025

## Workaround in Place

Using alternative engines:
- **Brave** (weight 1.5) - Returns 20 results, very reliable
- **Bing** (weight 1.2) - Returns 10 results, consistent
- **Startpage** (weight 1.1) - Google proxy, 6-7 results
- **DuckDuckGo** (weight 1.0) - May have rate limits

## Files Modified

1. `searxng/settings.yml` - `disabled: true` for google, google_news, google_scholar
2. `memOS/server/agentic/searcher.py` - Removed Google from ENGINE_GROUPS

## How to Re-enable

When upstream fix is merged:

1. **Test Google engine directly**:
   ```bash
   curl "http://localhost:8888/search?q=test&engines=google&format=json" | jq '.results | length'
   ```
   Should return > 0 results.

2. **Update settings.yml**:
   ```yaml
   - name: google
     disabled: false  # Was: true

   - name: google news
     disabled: false  # Was: true

   - name: google scholar
     disabled: false  # Was: true
   ```

3. **Update ENGINE_GROUPS in searcher.py**:
   Add `google` back to general, technical, fanuc, robotics groups.

4. **Pull latest SearXNG image**:
   ```bash
   cd /home/sparkone/sdd/Recovery_Bot/searxng
   docker compose pull
   docker compose up -d
   ```

5. **Test full pipeline**:
   ```bash
   ./test_search.sh "FANUC robot alarm SRVO-063"
   ```

## Monitoring

Check issue status:
- https://github.com/searxng/searxng/issues/5286
- Watch for PRs that reference this issue
- Subscribe to issue notifications

## Related Documentation

| Document | Purpose |
|----------|---------|
| [SearXNG CLAUDE.md](./CLAUDE.md) | Main SearXNG documentation |
| [ENGINE_FIX_PLAN.md](./ENGINE_FIX_PLAN.md) | Full implementation plan for engine fixes |
| [Project CLAUDE.md](../CLAUDE.md) | Root project documentation |

## External Resources

| Resource | URL |
|----------|-----|
| SearXNG Engine Docs | https://docs.searxng.org/dev/engines/online/google.html |
| Upstream Bug | https://github.com/searxng/searxng/issues/5286 |
| Alternative (Brave API) | Consider for guaranteed reliability |

**Note**: Mullvad Leta was shut down Nov 27, 2025 and is no longer available as a workaround.
