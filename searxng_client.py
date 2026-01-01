"""
SearXNG Client for Recovery Bot Agentic Search

This client provides async access to the self-hosted SearXNG metasearch engine.
It replaces the rate-limited DuckDuckGo API calls with unlimited local searches.

Features:
- Intelligent throttling with human-like request timing
- Exponential backoff with jitter on failures
- Circuit breaker pattern for failing engines
- Tor proxy integration for anonymity

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

# Import intelligent throttler
try:
    from intelligent_throttler import get_throttler, CircuitOpenError
    THROTTLER_AVAILABLE = True
except ImportError:
    THROTTLER_AVAILABLE = False
    CircuitOpenError = Exception  # Fallback

# Import result fusion
try:
    from result_fusion import get_fusion_engine, FusedResult
    FUSION_AVAILABLE = True
except ImportError:
    FUSION_AVAILABLE = False
    FusedResult = dict  # Fallback

# Import query router
try:
    from query_router import get_router, QueryType
    ROUTER_AVAILABLE = True
except ImportError:
    ROUTER_AVAILABLE = False
    QueryType = None

# Import semantic cache
try:
    from semantic_cache import get_cache, SemanticCache
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False
    SemanticCache = None

# Import local docs search (Meilisearch)
try:
    from local_docs import get_local_docs, LocalDocsSearch
    LOCAL_DOCS_AVAILABLE = True
except ImportError:
    LOCAL_DOCS_AVAILABLE = False
    LocalDocsSearch = None

# Import TLS fingerprint rotation
try:
    from tls_rotation import get_tls_rotator, TLSRotator, TLSConfig, is_tls_available
    TLS_ROTATION_AVAILABLE = is_tls_available()
except ImportError:
    TLS_ROTATION_AVAILABLE = False
    TLSRotator = None
    TLSConfig = None

# Import cross-encoder reranking
try:
    from cross_encoder_rerank import get_reranker, CrossEncoderReranker, RerankerConfig, is_reranker_available
    RERANKER_AVAILABLE = is_reranker_available()
except ImportError:
    RERANKER_AVAILABLE = False
    CrossEncoderReranker = None
    RerankerConfig = None

# Import search metrics
try:
    from search_metrics import get_metrics, SearchMetrics
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    SearchMetrics = None

# Import feedback loop
try:
    from feedback_loop import get_feedback_loop, FeedbackLoop, SearchFeedback, FeedbackSignal
    FEEDBACK_AVAILABLE = True
except ImportError:
    FEEDBACK_AVAILABLE = False
    FeedbackLoop = None

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
        default_engines: Optional[List[str]] = None,
        enable_throttling: bool = True,
        enable_cache: bool = True,
        enable_local_docs: bool = True,
        enable_tls_rotation: bool = False,  # Disabled by default (use for external requests)
        enable_reranking: bool = True,
        enable_metrics: bool = True,
        enable_feedback: bool = True
    ):
        """
        Initialize SearXNG client.

        Args:
            base_url: SearXNG server URL
            timeout: Request timeout in seconds
            default_engines: Default engines to use (None = all enabled)
            enable_throttling: Enable intelligent request throttling
            enable_cache: Enable semantic caching (L1 Redis + L2 Qdrant)
            enable_local_docs: Enable local document search (Meilisearch)
            enable_tls_rotation: Enable TLS fingerprint rotation (for external requests)
            enable_reranking: Enable cross-encoder reranking
            enable_metrics: Enable search quality metrics
            enable_feedback: Enable feedback loop for learning
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # NOTE: Google disabled (upstream bug #5286), DuckDuckGo/Startpage hitting CAPTCHA
        # Prioritize Brave/Bing/Mojeek which are consistently working
        self.default_engines = default_engines or ["brave", "bing", "mojeek", "reddit", "wikipedia"]
        self._client: Optional[httpx.AsyncClient] = None
        self._throttler = get_throttler() if enable_throttling and THROTTLER_AVAILABLE else None
        self._cache = get_cache() if enable_cache and CACHE_AVAILABLE else None
        self._cache_initialized = False
        self._local_docs = get_local_docs() if enable_local_docs and LOCAL_DOCS_AVAILABLE else None
        self._local_docs_initialized = False
        self._tls_rotator = get_tls_rotator() if enable_tls_rotation and TLS_ROTATION_AVAILABLE else None
        self._reranker = get_reranker() if enable_reranking and RERANKER_AVAILABLE else None
        self._metrics = get_metrics() if enable_metrics and METRICS_AVAILABLE else None
        self._feedback = get_feedback_loop() if enable_feedback and FEEDBACK_AVAILABLE else None
        self._feedback_initialized = False
        self._stats = {
            "total_searches": 0,
            "total_results": 0,
            "errors": 0,
            "avg_response_time_ms": 0.0,
            "throttle_delays_ms": 0.0,
            "cache_hits": 0,
            "cache_misses": 0,
            "local_docs_results": 0,
            "reranked_searches": 0
        }

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True
            )
        return self._client

    async def _init_cache(self):
        """Initialize cache if not already done."""
        if self._cache and not self._cache_initialized:
            await self._cache.initialize()
            self._cache_initialized = True

    async def _init_local_docs(self):
        """Initialize local docs search if not already done."""
        if self._local_docs and not self._local_docs_initialized:
            await self._local_docs.initialize()
            self._local_docs_initialized = True

    async def _init_feedback(self):
        """Initialize feedback loop if not already done."""
        if self._feedback and not self._feedback_initialized:
            await self._feedback.initialize()
            self._feedback_initialized = True

    async def cached_search(
        self,
        query: str,
        engines: Optional[List[str]] = None,
        use_cache: bool = True,
        **kwargs
    ) -> SearchResponse:
        """
        Search with semantic caching.

        Checks L1 (exact hash) then L2 (semantic) cache before hitting engines.

        Args:
            query: Search query string
            engines: List of engines to use
            use_cache: Whether to use cache (default True)
            **kwargs: Additional args passed to search()

        Returns:
            SearchResponse (may be from cache)
        """
        engines_list = engines or self.default_engines

        # Try cache first
        if use_cache and self._cache:
            await self._init_cache()
            entry, level = await self._cache.get(query, engines_list)
            if entry:
                self._stats["cache_hits"] += 1
                logger.debug(f"Cache {level} hit for: {query[:30]}...")
                # Convert cached results to SearchResponse
                results = [
                    SearchResult(
                        title=r.get("title", ""),
                        url=r.get("url", ""),
                        content=r.get("content", ""),
                        engine=r.get("engine", "cache"),
                        score=r.get("score", 0.0),
                        metadata={"cache_level": level, "cache_hit_count": entry.hit_count}
                    )
                    for r in entry.results
                ]
                return SearchResponse(
                    query=query,
                    results=results,
                    number_of_results=len(results),
                    search_time=0.001  # Cached, nearly instant
                )

        # Cache miss - perform actual search
        self._stats["cache_misses"] += 1
        response = await self.search(query, engines=engines_list, **kwargs)

        # Store in cache
        if use_cache and self._cache and response.results:
            await self._cache.store(
                query=query,
                results=[r.to_dict() for r in response.results],
                engines=engines_list
            )

        return response

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

        # Determine primary engine for throttling
        engine_name = (engines[0] if engines else
                       self.default_engines[0] if self.default_engines else "default")

        try:
            # Apply intelligent throttling (human-like delays)
            throttle_delay = 0.0
            if self._throttler:
                try:
                    throttle_delay = await self._throttler.wait_before_request(engine_name)
                    self._stats["throttle_delays_ms"] += throttle_delay * 1000
                except CircuitOpenError as e:
                    logger.warning(f"Circuit open for {engine_name}: {e}")
                    # Try with different engines if circuit is open
                    if engines and len(engines) > 1:
                        params["engines"] = ",".join(engines[1:])
                    else:
                        raise

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

            # Record success for throttler
            if self._throttler:
                self._throttler.record_success(engine_name)

            # Update stats
            self._stats["total_searches"] += 1
            self._stats["total_results"] += len(results)
            n = self._stats["total_searches"]
            self._stats["avg_response_time_ms"] = (
                (self._stats["avg_response_time_ms"] * (n - 1) + elapsed_ms) / n
            )

            logger.debug(
                f"SearXNG search '{query[:50]}...': {len(results)} results in {elapsed_ms:.0f}ms "
                f"(throttle: {throttle_delay*1000:.0f}ms)"
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
            # Record failure for throttler with error type
            if self._throttler:
                error_type = "rate_limit" if e.response.status_code == 429 else "http_error"
                self._throttler.record_failure(engine_name, error_type)
            raise
        except Exception as e:
            logger.error(f"SearXNG search failed: {e}")
            self._stats["errors"] += 1
            if self._throttler:
                self._throttler.record_failure(engine_name, "unknown")
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
        # NOTE: Google disabled (upstream bug #5286), DuckDuckGo/Startpage hitting CAPTCHA
        primary_engines = primary_engines or ["brave", "bing"]
        fallback_engines = fallback_engines or ["reddit", "wikipedia", "arxiv"]

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

    async def search_with_rrf(
        self,
        query: str,
        engines: Optional[List[str]] = None,
        fusion_method: str = "rrf",
        top_k: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search with Reciprocal Rank Fusion for better result merging.

        RRF provides superior ranking when combining results from multiple
        search engines, as shown by Cormack et al. research.

        Args:
            query: Search query
            engines: Engines to use (default: all working engines)
            fusion_method: "rrf", "weighted", "borda", or "hybrid"
            top_k: Number of top results to return

        Returns:
            List of fused result dicts with RRF scores
        """
        if not FUSION_AVAILABLE:
            logger.warning("Result fusion not available, falling back to regular search")
            response = await self.search(query, engines=engines, max_results=top_k)
            return [r.to_dict() for r in response.results]

        # Use all working engines for best fusion
        engines = engines or ["brave", "bing", "mojeek", "reddit", "wikipedia"]

        # Get results from SearXNG (already aggregated)
        response = await self.search(query, engines=engines, max_results=100)

        # Apply RRF fusion
        fusion = get_fusion_engine()
        fused_results = fusion.fuse_from_searxng(
            [r.to_dict() for r in response.results],
            method=fusion_method,
            top_k=top_k
        )

        logger.info(
            f"RRF fusion: {len(response.results)} raw -> {len(fused_results)} fused results"
        )

        return [r.to_dict() for r in fused_results]

    async def search_academic(
        self,
        query: str,
        top_k: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search academic sources with RRF fusion.

        Uses: arxiv, semantic_scholar, openalex, pubmed, crossref
        """
        academic_engines = ["arxiv", "semantic_scholar", "openalex", "pubmed", "crossref"]
        return await self.search_with_rrf(
            query,
            engines=academic_engines,
            fusion_method="rrf",
            top_k=top_k
        )

    async def search_technical(
        self,
        query: str,
        top_k: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search technical sources with RRF fusion.

        Uses: stackoverflow, github, brave, bing, reddit
        """
        technical_engines = ["stackoverflow", "github", "brave", "bing", "reddit"]
        return await self.search_with_rrf(
            query,
            engines=technical_engines,
            fusion_method="rrf",
            top_k=top_k
        )

    async def smart_search(
        self,
        query: str,
        use_rrf: bool = True,
        top_k: int = 20
    ) -> Dict[str, Any]:
        """
        Intelligent search with automatic engine selection and RRF fusion.

        Uses pattern-based query routing to select optimal engines,
        then applies RRF fusion for best result ranking.

        Args:
            query: Search query
            use_rrf: Whether to apply RRF fusion
            top_k: Number of results to return

        Returns:
            Dict with results, routing info, and metadata
        """
        # Route query to optimal engines
        if ROUTER_AVAILABLE:
            router = get_router()
            decision = router.route(query)
            engines = decision.engines
            query_type = decision.query_type.value
            routing_confidence = decision.confidence
            routing_reasoning = decision.reasoning
        else:
            engines = self.default_engines
            query_type = "general"
            routing_confidence = 0.5
            routing_reasoning = "Query router not available"

        logger.info(
            f"Smart search: '{query[:50]}...' routed to {query_type} "
            f"(confidence: {routing_confidence:.2f})"
        )

        # Execute search with selected engines
        if use_rrf and FUSION_AVAILABLE:
            results = await self.search_with_rrf(
                query,
                engines=engines,
                fusion_method="rrf",
                top_k=top_k
            )
        else:
            response = await self.search(query, engines=engines, max_results=top_k)
            results = [r.to_dict() for r in response.results]

        return {
            "query": query,
            "query_type": query_type,
            "routing_confidence": routing_confidence,
            "routing_reasoning": routing_reasoning,
            "engines_used": engines,
            "result_count": len(results),
            "results": results,
            "fusion_applied": use_rrf and FUSION_AVAILABLE
        }

    async def search_with_local_docs(
        self,
        query: str,
        engines: Optional[List[str]] = None,
        local_docs_limit: int = 5,
        web_results_limit: int = 15,
        use_rrf: bool = True
    ) -> Dict[str, Any]:
        """
        Search combining web results with local FANUC documentation.

        Prioritizes local docs for industrial/technical queries while
        also including web results for broader context.

        Args:
            query: Search query
            engines: Web engines to use
            local_docs_limit: Max results from local docs
            web_results_limit: Max results from web search
            use_rrf: Whether to apply RRF fusion to web results

        Returns:
            Dict with local_docs, web_results, and combined results
        """
        results = {
            "query": query,
            "local_docs": [],
            "web_results": [],
            "combined": [],
            "local_docs_available": LOCAL_DOCS_AVAILABLE and self._local_docs is not None
        }

        # Search local documents
        if self._local_docs:
            try:
                await self._init_local_docs()
                local_results = await self._local_docs.search(query, limit=local_docs_limit)
                results["local_docs"] = [r.to_searxng_format() for r in local_results]
                self._stats["local_docs_results"] += len(local_results)
                logger.info(f"Local docs: {len(local_results)} results for '{query[:30]}...'")
            except Exception as e:
                logger.warning(f"Local docs search failed: {e}")

        # Search web via SearXNG
        try:
            if use_rrf and FUSION_AVAILABLE:
                web_results = await self.search_with_rrf(
                    query,
                    engines=engines,
                    top_k=web_results_limit
                )
            else:
                response = await self.search(query, engines=engines, max_results=web_results_limit)
                web_results = [r.to_dict() for r in response.results]

            results["web_results"] = web_results
        except Exception as e:
            logger.warning(f"Web search failed: {e}")

        # Combine results: local docs first (higher priority), then web
        combined = []

        # Add local docs with boosted scores
        for doc in results["local_docs"]:
            doc_copy = doc.copy()
            doc_copy["score"] = doc.get("score", 1.0) + 0.5  # Boost local docs
            doc_copy["source_type"] = "local_docs"
            combined.append(doc_copy)

        # Add web results
        for web in results["web_results"]:
            web_copy = web.copy()
            web_copy["source_type"] = "web"
            combined.append(web_copy)

        # Sort by score (local docs should be at top due to boost)
        combined.sort(key=lambda x: x.get("score", 0), reverse=True)
        results["combined"] = combined

        return results

    async def search_full_pipeline(
        self,
        query: str,
        engines: Optional[List[str]] = None,
        include_local_docs: bool = True,
        apply_reranking: bool = True,
        record_metrics: bool = True,
        top_k: int = 20
    ) -> Dict[str, Any]:
        """
        Full pipeline search with all features integrated.

        Pipeline:
        1. Query routing → Select optimal engines
        2. Cache check → L1 (exact) → L2 (semantic) → Fresh search
        3. Local docs → Search Meilisearch for FANUC docs
        4. Result fusion → RRF combine web + local
        5. Reranking → Cross-encoder neural rerank
        6. Metrics → Track quality metrics
        7. Feedback → Record for learning

        Args:
            query: Search query
            engines: Override engines (default: auto-routed)
            include_local_docs: Include local FANUC docs
            apply_reranking: Apply cross-encoder reranking
            record_metrics: Track search metrics
            top_k: Number of results to return

        Returns:
            Dict with pipeline results and metadata
        """
        import time
        start_time = time.time()

        result = {
            "query": query,
            "pipeline": {
                "routing": None,
                "cache": None,
                "local_docs": None,
                "fusion": None,
                "reranking": None,
                "metrics": None
            },
            "results": [],
            "metadata": {
                "total_time_ms": 0,
                "engines_used": [],
                "result_count": 0
            }
        }

        # 1. Query Routing
        if ROUTER_AVAILABLE:
            router = get_router()
            decision = router.route(query)
            engines = engines or decision.engines
            result["pipeline"]["routing"] = {
                "query_type": decision.query_type.value,
                "confidence": decision.confidence,
                "engines": engines
            }
        else:
            engines = engines or self.default_engines
            result["pipeline"]["routing"] = {"engines": engines, "auto": False}

        result["metadata"]["engines_used"] = engines

        # 2. Cache Check
        web_results = []
        cache_hit = False
        if self._cache:
            await self._init_cache()
            entry, level = await self._cache.get(query, engines)
            if entry:
                cache_hit = True
                web_results = entry.results
                result["pipeline"]["cache"] = {"hit": True, "level": level}
                self._stats["cache_hits"] += 1

        if not cache_hit:
            result["pipeline"]["cache"] = {"hit": False}
            self._stats["cache_misses"] += 1

            # Fresh search via SearXNG
            try:
                if FUSION_AVAILABLE:
                    web_results = await self.search_with_rrf(
                        query, engines=engines, top_k=top_k * 2
                    )
                    result["pipeline"]["fusion"] = {"method": "rrf", "input_count": len(web_results)}
                else:
                    response = await self.search(query, engines=engines, max_results=top_k * 2)
                    web_results = [r.to_dict() for r in response.results]
            except Exception as e:
                logger.warning(f"Web search failed: {e}")
                web_results = []

            # Store in cache
            if self._cache and web_results:
                await self._cache.store(query, web_results, engines)

        # 3. Local Docs Search
        local_results = []
        if include_local_docs and self._local_docs:
            try:
                await self._init_local_docs()
                local_search = await self._local_docs.search(query, limit=5)
                local_results = [r.to_searxng_format() for r in local_search]
                result["pipeline"]["local_docs"] = {"count": len(local_results)}
                self._stats["local_docs_results"] += len(local_results)
            except Exception as e:
                logger.warning(f"Local docs search failed: {e}")
                result["pipeline"]["local_docs"] = {"error": str(e)}

        # 4. Combine Results (local docs boosted)
        combined = []
        for doc in local_results:
            doc_copy = doc.copy()
            doc_copy["score"] = doc.get("score", 1.0) + 0.5
            doc_copy["source_type"] = "local_docs"
            combined.append(doc_copy)

        for web in web_results:
            web_copy = web.copy() if isinstance(web, dict) else web
            web_copy["source_type"] = "web"
            combined.append(web_copy)

        # 5. Cross-Encoder Reranking
        if apply_reranking and self._reranker and combined:
            try:
                reranked = await self._reranker.rerank_to_dicts(
                    query, combined, content_key="content", top_k=top_k
                )
                combined = reranked
                result["pipeline"]["reranking"] = {
                    "applied": True,
                    "input_count": len(combined),
                    "output_count": len(reranked)
                }
                self._stats["reranked_searches"] += 1
            except Exception as e:
                logger.warning(f"Reranking failed: {e}")
                result["pipeline"]["reranking"] = {"applied": False, "error": str(e)}
        else:
            result["pipeline"]["reranking"] = {"applied": False, "reason": "disabled or unavailable"}

        # Sort by score
        combined.sort(key=lambda x: x.get("score", 0) if isinstance(x, dict) else 0, reverse=True)
        result["results"] = combined[:top_k]

        # 6. Track Metrics
        if record_metrics and self._metrics:
            try:
                self._metrics.record_search(
                    results=result["results"],
                    response_time=(time.time() - start_time),
                    engines_queried=engines
                )
                result["pipeline"]["metrics"] = {"recorded": True}
            except Exception as e:
                logger.debug(f"Metrics recording failed: {e}")
                result["pipeline"]["metrics"] = {"recorded": False, "error": str(e)}

        # 7. Record for Feedback (impressions)
        if self._feedback and result["results"]:
            try:
                await self._init_feedback()
                query_type = result["pipeline"]["routing"].get("query_type", "general")
                await self._feedback.record_impression(
                    query=query,
                    query_type=query_type,
                    results=result["results"]
                )
            except Exception as e:
                logger.debug(f"Feedback recording failed: {e}")

        # Final metadata
        result["metadata"]["total_time_ms"] = (time.time() - start_time) * 1000
        result["metadata"]["result_count"] = len(result["results"])

        return result

    async def record_click(
        self,
        query: str,
        query_type: str,
        engine: str,
        url: str,
        position: int
    ):
        """Record a user click for feedback learning."""
        if self._feedback:
            await self._init_feedback()
            await self._feedback.record_feedback(SearchFeedback(
                query=query,
                query_type=query_type,
                engine=engine,
                url=url,
                position=position,
                signal=FeedbackSignal.CLICK
            ))

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
        stats = self._stats.copy()
        stats["features"] = {
            "throttler": THROTTLER_AVAILABLE,
            "fusion": FUSION_AVAILABLE,
            "router": ROUTER_AVAILABLE,
            "cache": CACHE_AVAILABLE,
            "local_docs": LOCAL_DOCS_AVAILABLE,
            "tls_rotation": TLS_ROTATION_AVAILABLE,
            "reranker": RERANKER_AVAILABLE,
            "metrics": METRICS_AVAILABLE,
            "feedback": FEEDBACK_AVAILABLE
        }
        if self._throttler:
            stats["throttler"] = self._throttler.get_all_status()
        if self._cache:
            stats["cache"] = self._cache.get_stats()
        if self._local_docs:
            stats["local_docs"] = self._local_docs.get_stats()
        if self._tls_rotator:
            stats["tls_rotation"] = self._tls_rotator.get_stats()
        if self._reranker:
            stats["reranker"] = self._reranker.get_stats()
        if self._feedback:
            stats["feedback"] = self._feedback.get_performance_summary()
        return stats

    def get_engine_health(self, engine: str = "default") -> Dict[str, Any]:
        """Get health status for a specific engine."""
        if self._throttler:
            return self._throttler.get_engine_status(engine)
        return {"status": "throttling_disabled"}

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
    # NOTE: Google disabled (upstream bug #5286)
    response = await client.search(
        "Python programming language",
        engines=["brave", "bing", "duckduckgo"]
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
