#!/usr/bin/env python3
"""
Semantic Cache for SearXNG Search Results

Three-layer caching architecture:
- L1: Exact hash (Redis) - O(1) lookup for identical queries
- L2: Semantic (Qdrant) - Embedding similarity @ 0.88 threshold
- L3: Fresh search - Store results in L1 + L2

This significantly reduces search latency for similar queries
and reduces load on upstream search engines.
"""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Optional imports - graceful degradation if not available
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("redis not available - L1 cache disabled")

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance, VectorParams, PointStruct,
        Filter, FieldCondition, MatchValue
    )
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    logger.warning("qdrant-client not available - L2 cache disabled")

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


@dataclass
class CacheConfig:
    """Configuration for semantic cache."""
    # Redis (L1)
    redis_url: str = "redis://localhost:6379/1"
    l1_ttl_seconds: int = 3600  # 1 hour for exact matches

    # Qdrant (L2)
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    collection_name: str = "search_cache"
    embedding_dim: int = 768  # nomic-embed-text dimension
    similarity_threshold: float = 0.80  # Semantic match threshold (0.75-0.85 optimal)
    l2_ttl_seconds: int = 86400  # 24 hours for semantic matches

    # Embedding
    ollama_url: str = "http://localhost:11434"
    embedding_model: str = "nomic-embed-text"

    # General
    max_cached_results: int = 20  # Store top N results


@dataclass
class CacheEntry:
    """A cached search result."""
    query: str
    query_hash: str
    results: List[Dict[str, Any]]
    engines: List[str]
    timestamp: float
    ttl_seconds: int
    hit_count: int = 0

    @property
    def is_expired(self) -> bool:
        return time.time() > self.timestamp + self.ttl_seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "query_hash": self.query_hash,
            "results": self.results,
            "engines": self.engines,
            "timestamp": self.timestamp,
            "ttl_seconds": self.ttl_seconds,
            "hit_count": self.hit_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CacheEntry":
        return cls(
            query=data["query"],
            query_hash=data["query_hash"],
            results=data["results"],
            engines=data["engines"],
            timestamp=data["timestamp"],
            ttl_seconds=data["ttl_seconds"],
            hit_count=data.get("hit_count", 0),
        )


@dataclass
class CacheStats:
    """Cache performance statistics."""
    l1_hits: int = 0
    l2_hits: int = 0
    misses: int = 0
    stores: int = 0
    errors: int = 0
    avg_l1_latency_ms: float = 0.0
    avg_l2_latency_ms: float = 0.0

    @property
    def total_requests(self) -> int:
        return self.l1_hits + self.l2_hits + self.misses

    @property
    def hit_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return (self.l1_hits + self.l2_hits) / self.total_requests

    def to_dict(self) -> Dict[str, Any]:
        return {
            "l1_hits": self.l1_hits,
            "l2_hits": self.l2_hits,
            "misses": self.misses,
            "stores": self.stores,
            "errors": self.errors,
            "hit_rate": f"{self.hit_rate:.1%}",
            "avg_l1_latency_ms": f"{self.avg_l1_latency_ms:.1f}",
            "avg_l2_latency_ms": f"{self.avg_l2_latency_ms:.1f}",
        }


class SemanticCache:
    """
    Three-layer semantic cache for search results.

    L1 (Redis): Exact query hash match - fastest, O(1)
    L2 (Qdrant): Semantic similarity match - fast, uses embeddings
    L3: Fresh search from engines - slowest, but always fresh
    """

    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()
        self.stats = CacheStats()
        self._redis: Optional[redis.Redis] = None
        self._qdrant: Optional[QdrantClient] = None
        self._http_client: Optional[httpx.AsyncClient] = None
        self._initialized = False
        self._l1_latencies: List[float] = []
        self._l2_latencies: List[float] = []

    async def initialize(self) -> bool:
        """Initialize cache connections."""
        if self._initialized:
            return True

        success = True

        # Initialize Redis (L1)
        if REDIS_AVAILABLE:
            try:
                self._redis = redis.from_url(
                    self.config.redis_url,
                    encoding="utf-8",
                    decode_responses=True
                )
                await self._redis.ping()
                logger.info("L1 cache (Redis) connected")
            except Exception as e:
                logger.error(f"L1 cache (Redis) failed: {e}")
                self._redis = None
                success = False

        # Initialize Qdrant (L2)
        if QDRANT_AVAILABLE:
            try:
                self._qdrant = QdrantClient(
                    host=self.config.qdrant_host,
                    port=self.config.qdrant_port,
                )
                # Create collection if not exists
                collections = self._qdrant.get_collections().collections
                if not any(c.name == self.config.collection_name for c in collections):
                    self._qdrant.create_collection(
                        collection_name=self.config.collection_name,
                        vectors_config=VectorParams(
                            size=self.config.embedding_dim,
                            distance=Distance.COSINE
                        )
                    )
                    logger.info(f"Created Qdrant collection: {self.config.collection_name}")
                logger.info("L2 cache (Qdrant) connected")
            except Exception as e:
                logger.error(f"L2 cache (Qdrant) failed: {e}")
                self._qdrant = None
                success = False

        # Initialize HTTP client for embeddings
        if HTTPX_AVAILABLE:
            self._http_client = httpx.AsyncClient(timeout=30.0)

        self._initialized = True
        return success

    async def close(self):
        """Close cache connections."""
        if self._redis:
            await self._redis.close()
        if self._http_client:
            await self._http_client.aclose()
        self._initialized = False

    def _hash_query(self, query: str, engines: Optional[List[str]] = None) -> str:
        """Generate hash for exact match lookup."""
        key = query.lower().strip()
        if engines:
            key += "|" + ",".join(sorted(engines))
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    async def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding for text using Ollama."""
        if not self._http_client:
            return None

        try:
            response = await self._http_client.post(
                f"{self.config.ollama_url}/api/embeddings",
                json={
                    "model": self.config.embedding_model,
                    "prompt": text
                }
            )
            if response.status_code == 200:
                return response.json().get("embedding")
        except Exception as e:
            logger.debug(f"Embedding failed: {e}")

        return None

    async def get(
        self,
        query: str,
        engines: Optional[List[str]] = None
    ) -> Tuple[Optional[CacheEntry], str]:
        """
        Look up query in cache.

        Returns:
            Tuple of (CacheEntry or None, cache_level: "l1", "l2", or "miss")
        """
        if not self._initialized:
            await self.initialize()

        query_hash = self._hash_query(query, engines)

        # L1: Exact hash match in Redis
        if self._redis:
            start = time.time()
            try:
                cached = await self._redis.get(f"search:{query_hash}")
                latency = (time.time() - start) * 1000
                self._l1_latencies.append(latency)
                if len(self._l1_latencies) > 100:
                    self._l1_latencies = self._l1_latencies[-100:]
                self.stats.avg_l1_latency_ms = sum(self._l1_latencies) / len(self._l1_latencies)

                if cached:
                    entry = CacheEntry.from_dict(json.loads(cached))
                    if not entry.is_expired:
                        entry.hit_count += 1
                        self.stats.l1_hits += 1
                        logger.debug(f"L1 hit for: {query[:30]}...")
                        return entry, "l1"
            except Exception as e:
                logger.error(f"L1 lookup failed: {e}")
                self.stats.errors += 1

        # L2: Semantic similarity in Qdrant
        if self._qdrant:
            start = time.time()
            try:
                embedding = await self._get_embedding(query)
                if embedding:
                    # Qdrant v1.16+ uses query_points instead of search
                    search_result = self._qdrant.query_points(
                        collection_name=self.config.collection_name,
                        query=embedding,
                        limit=1,
                        score_threshold=self.config.similarity_threshold
                    )
                    results = search_result.points if search_result else []

                    latency = (time.time() - start) * 1000
                    self._l2_latencies.append(latency)
                    if len(self._l2_latencies) > 100:
                        self._l2_latencies = self._l2_latencies[-100:]
                    self.stats.avg_l2_latency_ms = sum(self._l2_latencies) / len(self._l2_latencies)

                    if results:
                        payload = results[0].payload
                        entry = CacheEntry.from_dict(payload)
                        if not entry.is_expired:
                            entry.hit_count += 1
                            self.stats.l2_hits += 1
                            logger.debug(
                                f"L2 hit (score={results[0].score:.3f}) for: {query[:30]}..."
                            )
                            return entry, "l2"
            except Exception as e:
                logger.error(f"L2 lookup failed: {e}")
                self.stats.errors += 1

        self.stats.misses += 1
        return None, "miss"

    async def store(
        self,
        query: str,
        results: List[Dict[str, Any]],
        engines: List[str],
        ttl_seconds: Optional[int] = None
    ) -> bool:
        """
        Store search results in cache.

        Stores in both L1 (Redis) and L2 (Qdrant) for redundancy.
        """
        if not self._initialized:
            await self.initialize()

        query_hash = self._hash_query(query, engines)
        ttl = ttl_seconds or self.config.l1_ttl_seconds

        entry = CacheEntry(
            query=query,
            query_hash=query_hash,
            results=results[:self.config.max_cached_results],
            engines=engines,
            timestamp=time.time(),
            ttl_seconds=ttl,
        )

        success = True

        # Store in L1 (Redis)
        if self._redis:
            try:
                await self._redis.setex(
                    f"search:{query_hash}",
                    ttl,
                    json.dumps(entry.to_dict())
                )
                logger.debug(f"L1 stored: {query[:30]}...")
            except Exception as e:
                logger.error(f"L1 store failed: {e}")
                success = False

        # Store in L2 (Qdrant)
        if self._qdrant:
            try:
                embedding = await self._get_embedding(query)
                if embedding:
                    self._qdrant.upsert(
                        collection_name=self.config.collection_name,
                        points=[
                            PointStruct(
                                id=hash(query_hash) % (2**63),  # Convert to int64
                                vector=embedding,
                                payload=entry.to_dict()
                            )
                        ]
                    )
                    logger.debug(f"L2 stored: {query[:30]}...")
            except Exception as e:
                logger.error(f"L2 store failed: {e}")
                success = False

        if success:
            self.stats.stores += 1

        return success

    async def invalidate(self, query: str, engines: Optional[List[str]] = None) -> bool:
        """Invalidate cache entry for a query."""
        query_hash = self._hash_query(query, engines)

        success = True

        if self._redis:
            try:
                await self._redis.delete(f"search:{query_hash}")
            except Exception as e:
                logger.error(f"L1 invalidate failed: {e}")
                success = False

        # Note: Qdrant deletion would require storing query_hash in payload
        # For now, expired entries are ignored on lookup

        return success

    async def clear(self) -> bool:
        """Clear all cache entries."""
        success = True

        if self._redis:
            try:
                keys = await self._redis.keys("search:*")
                if keys:
                    await self._redis.delete(*keys)
                logger.info(f"L1 cleared: {len(keys)} entries")
            except Exception as e:
                logger.error(f"L1 clear failed: {e}")
                success = False

        if self._qdrant:
            try:
                self._qdrant.delete_collection(self.config.collection_name)
                self._qdrant.create_collection(
                    collection_name=self.config.collection_name,
                    vectors_config=VectorParams(
                        size=self.config.embedding_dim,
                        distance=Distance.COSINE
                    )
                )
                logger.info("L2 cleared and recreated")
            except Exception as e:
                logger.error(f"L2 clear failed: {e}")
                success = False

        return success

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return self.stats.to_dict()


# Singleton instance
_cache: Optional[SemanticCache] = None


def get_cache(config: Optional[CacheConfig] = None) -> SemanticCache:
    """Get or create the cache singleton."""
    global _cache
    if _cache is None:
        _cache = SemanticCache(config)
    return _cache


async def example_usage():
    """Demonstrate semantic cache usage."""
    cache = get_cache()
    await cache.initialize()

    # Simulate storing search results
    results = [
        {"url": "https://fanuc.com", "title": "FANUC Servo Guide", "engine": "brave"},
        {"url": "https://docs.fanuc.com", "title": "FANUC Docs", "engine": "bing"},
    ]

    await cache.store(
        query="FANUC SRVO-063 servo alarm",
        results=results,
        engines=["brave", "bing"]
    )

    # Look up exact match
    entry, level = await cache.get("FANUC SRVO-063 servo alarm", ["brave", "bing"])
    print(f"Exact match: level={level}, results={len(entry.results) if entry else 0}")

    # Look up similar query (semantic match)
    entry, level = await cache.get("FANUC servo alarm SRVO-063", ["brave", "bing"])
    print(f"Similar query: level={level}, results={len(entry.results) if entry else 0}")

    # Print stats
    print(f"Stats: {cache.get_stats()}")

    await cache.close()


if __name__ == "__main__":
    asyncio.run(example_usage())
