"""
SearXNG Client for Recovery Bot Agentic Search

This client provides async access to the self-hosted SearXNG metasearch engine.
It replaces the rate-limited DuckDuckGo API calls with unlimited local searches.

Usage:
    from searxng_client import SearXNGClient, get_searxng_client

    client = get_searxng_client()
    results = await client.search("addiction recovery services")
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum

import httpx

logger = logging.getLogger(__name__)


class SearchCategory(Enum):
    """Search categories supported by SearXNG"""
    GENERAL = "general"
    IMAGES = "images"
    NEWS = "news"
    MAP = "map"
    SCIENCE = "science"
    IT = "it"
    FILES = "files"
    MUSIC = "music"
    VIDEOS = "videos"


class TimeRange(Enum):
    """Time range filters for search results"""
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


@dataclass
class SearchResult:
    """Individual search result from SearXNG"""
    title: str
    url: str
    content: str  # Snippet/description
    engine: str
    score: float = 0.0
    category: str = "general"
    thumbnail: Optional[str] = None
    publishedDate: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "content": self.content,
            "engine": self.engine,
            "score": self.score,
            "category": self.category,
            "thumbnail": self.thumbnail,
            "publishedDate": self.publishedDate,
            "metadata": self.metadata
        }


@dataclass
class SearchResponse:
    """Complete search response from SearXNG"""
    query: str
    results: List[SearchResult]
    suggestions: List[str] = field(default_factory=list)
    corrections: List[str] = field(default_factory=list)
    infoboxes: List[Dict] = field(default_factory=list)
    number_of_results: int = 0
    search_time: float = 0.0


class SearXNGClient:
    """
    Async client for SearXNG metasearch engine.

    Features:
    - Multiple search engine aggregation (Google, Bing, DuckDuckGo, Brave, etc.)
    - No rate limiting (self-hosted)
    - Caching allowed (no API restrictions)
    - JSON API access
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8888",
        timeout: float = 30.0,
        default_engines: Optional[List[str]] = None
    ):
        """
        Initialize SearXNG client.

        Args:
            base_url: SearXNG server URL
            timeout: Request timeout in seconds
            default_engines: Default engines to use (None = all enabled)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.default_engines = default_engines or ["google", "bing", "duckduckgo", "brave"]
        self._client: Optional[httpx.AsyncClient] = None
        self._stats = {
            "total_searches": 0,
            "total_results": 0,
            "errors": 0,
            "avg_response_time_ms": 0.0
        }

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True
            )
        return self._client

    async def search(
        self,
        query: str,
        engines: Optional[List[str]] = None,
        categories: Optional[List[SearchCategory]] = None,
        language: str = "en-US",
        time_range: Optional[TimeRange] = None,
        page: int = 1,
        safesearch: int = 0,
        max_results: int = 20
    ) -> SearchResponse:
        """
        Perform a search query.

        Args:
            query: Search query string
            engines: List of engines to use (google, bing, duckduckgo, brave, etc.)
            categories: List of search categories
            language: Language code (en-US, en-GB, etc.)
            time_range: Time filter (day, week, month, year)
            page: Page number (1-indexed)
            safesearch: Safe search level (0=off, 1=moderate, 2=strict)
            max_results: Maximum results to return

        Returns:
            SearchResponse with results and metadata
        """
        import time
        start_time = time.time()

        client = await self._get_client()

        params = {
            "q": query,
            "format": "json",
            "language": language,
            "pageno": page,
            "safesearch": safesearch
        }

        if engines:
            params["engines"] = ",".join(engines)
        elif self.default_engines:
            params["engines"] = ",".join(self.default_engines)

        if categories:
            params["categories"] = ",".join(c.value for c in categories)

        if time_range:
            params["time_range"] = time_range.value

        try:
            response = await client.get(
                f"{self.base_url}/search",
                params=params
            )
            response.raise_for_status()

            data = response.json()
            elapsed_ms = (time.time() - start_time) * 1000

            results = []
            for item in data.get("results", [])[:max_results]:
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    content=item.get("content", ""),
                    engine=item.get("engine", "unknown"),
                    score=item.get("score", 0.0),
                    category=item.get("category", "general"),
                    thumbnail=item.get("thumbnail"),
                    publishedDate=item.get("publishedDate"),
                    metadata={
                        k: v for k, v in item.items()
                        if k not in ["title", "url", "content", "engine", "score", "category", "thumbnail", "publishedDate"]
                    }
                ))

            # Update stats
            self._stats["total_searches"] += 1
            self._stats["total_results"] += len(results)
            n = self._stats["total_searches"]
            self._stats["avg_response_time_ms"] = (
                (self._stats["avg_response_time_ms"] * (n - 1) + elapsed_ms) / n
            )

            logger.debug(
                f"SearXNG search '{query[:50]}...': {len(results)} results in {elapsed_ms:.0f}ms"
            )

            return SearchResponse(
                query=query,
                results=results,
                suggestions=data.get("suggestions", []),
                corrections=data.get("corrections", []),
                infoboxes=data.get("infoboxes", []),
                number_of_results=data.get("number_of_results", len(results)),
                search_time=elapsed_ms / 1000.0
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"SearXNG HTTP error: {e.response.status_code}")
            self._stats["errors"] += 1
            raise
        except Exception as e:
            logger.error(f"SearXNG search failed: {e}")
            self._stats["errors"] += 1
            raise

    async def search_multi_query(
        self,
        queries: List[str],
        engines: Optional[List[str]] = None,
        max_per_query: int = 10
    ) -> List[SearchResult]:
        """
        Execute multiple queries and combine results.

        Args:
            queries: List of query strings
            engines: Engines to use
            max_per_query: Max results per query

        Returns:
            Combined list of SearchResult objects (deduplicated by URL)
        """
        tasks = [
            self.search(q, engines=engines, max_results=max_per_query)
            for q in queries
        ]

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        all_results = []
        seen_urls = set()

        for response in responses:
            if isinstance(response, Exception):
                logger.warning(f"Query failed: {response}")
                continue

            for result in response.results:
                if result.url not in seen_urls:
                    seen_urls.add(result.url)
                    all_results.append(result)

        return all_results

    async def search_with_fallback(
        self,
        query: str,
        primary_engines: Optional[List[str]] = None,
        fallback_engines: Optional[List[str]] = None,
        min_results: int = 5
    ) -> SearchResponse:
        """
        Search with fallback to additional engines if results are insufficient.

        Args:
            query: Search query
            primary_engines: Primary engines to try first
            fallback_engines: Engines to try if primary returns too few results
            min_results: Minimum results before trying fallback

        Returns:
            SearchResponse with combined results
        """
        primary_engines = primary_engines or ["google", "bing"]
        fallback_engines = fallback_engines or ["duckduckgo", "brave", "wikipedia"]

        response = await self.search(query, engines=primary_engines)

        if len(response.results) < min_results:
            logger.info(
                f"Primary search returned {len(response.results)} results, "
                f"trying fallback engines"
            )
            fallback_response = await self.search(query, engines=fallback_engines)

            # Combine results, deduplicating by URL
            seen_urls = {r.url for r in response.results}
            for result in fallback_response.results:
                if result.url not in seen_urls:
                    response.results.append(result)
                    seen_urls.add(result.url)

        return response

    async def health_check(self) -> Dict[str, Any]:
        """
        Check if SearXNG is responding.

        Returns:
            Dict with health status and stats
        """
        try:
            response = await self.search("test", max_results=1)
            return {
                "status": "healthy",
                "results_returned": len(response.results),
                "search_time_ms": response.search_time * 1000,
                "stats": self._stats
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "stats": self._stats
            }

    @property
    def stats(self) -> Dict[str, Any]:
        """Get client statistics"""
        return self._stats.copy()

    async def close(self):
        """Close the HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton instance
_searxng_client: Optional[SearXNGClient] = None


def get_searxng_client(
    base_url: str = "http://localhost:8888",
    **kwargs
) -> SearXNGClient:
    """
    Get or create the SearXNG client singleton.

    Args:
        base_url: SearXNG server URL
        **kwargs: Additional arguments for SearXNGClient

    Returns:
        SearXNGClient instance
    """
    global _searxng_client
    if _searxng_client is None:
        _searxng_client = SearXNGClient(base_url=base_url, **kwargs)
    return _searxng_client


# CLI for testing
async def main():
    """Test the SearXNG client"""
    import json

    client = get_searxng_client()

    print("Testing SearXNG client...")
    print("-" * 50)

    # Health check
    health = await client.health_check()
    print(f"Health: {health['status']}")

    # Test search
    print("\nSearching for 'Python programming'...")
    response = await client.search(
        "Python programming language",
        engines=["google", "bing", "duckduckgo"]
    )

    print(f"Found {len(response.results)} results in {response.search_time:.2f}s")
    print("\nTop 5 results:")
    for i, result in enumerate(response.results[:5], 1):
        print(f"\n{i}. [{result.engine}] {result.title}")
        print(f"   URL: {result.url}")
        print(f"   {result.content[:100]}...")

    # Stats
    print("\n" + "-" * 50)
    print("Client stats:", json.dumps(client.stats, indent=2))

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
