#!/usr/bin/env python3
"""
Semantic Cache Tests

Tests for the three-layer caching architecture (Redis + Qdrant + embeddings).
Uses mocks to avoid requiring external services.
"""

import pytest
import asyncio
import time
import json
from unittest.mock import AsyncMock, MagicMock, patch
import sys
sys.path.insert(0, "..")

from semantic_cache import (
    SemanticCache,
    CacheConfig,
    CacheEntry,
    CacheStats,
    get_cache,
)


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_is_expired_false(self):
        """Test non-expired entry."""
        entry = CacheEntry(
            query="test",
            query_hash="abc123",
            results=[],
            engines=["brave"],
            timestamp=time.time(),
            ttl_seconds=3600,
        )
        assert entry.is_expired is False

    def test_is_expired_true(self):
        """Test expired entry."""
        entry = CacheEntry(
            query="test",
            query_hash="abc123",
            results=[],
            engines=["brave"],
            timestamp=time.time() - 7200,  # 2 hours ago
            ttl_seconds=3600,  # 1 hour TTL
        )
        assert entry.is_expired is True

    def test_to_dict(self):
        """Test serialization to dict."""
        entry = CacheEntry(
            query="test query",
            query_hash="abc123",
            results=[{"url": "https://example.com"}],
            engines=["brave", "bing"],
            timestamp=1000.0,
            ttl_seconds=3600,
            hit_count=5,
        )

        d = entry.to_dict()

        assert d["query"] == "test query"
        assert d["query_hash"] == "abc123"
        assert len(d["results"]) == 1
        assert d["engines"] == ["brave", "bing"]
        assert d["hit_count"] == 5

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "query": "test",
            "query_hash": "abc123",
            "results": [{"url": "https://example.com"}],
            "engines": ["brave"],
            "timestamp": 1000.0,
            "ttl_seconds": 3600,
            "hit_count": 3,
        }

        entry = CacheEntry.from_dict(data)

        assert entry.query == "test"
        assert entry.hit_count == 3


class TestCacheStats:
    """Tests for CacheStats dataclass."""

    def test_total_requests(self):
        """Test total_requests calculation."""
        stats = CacheStats(l1_hits=10, l2_hits=5, misses=15)
        assert stats.total_requests == 30

    def test_hit_rate_zero_requests(self):
        """Test hit_rate with zero requests."""
        stats = CacheStats()
        assert stats.hit_rate == 0.0

    def test_hit_rate_calculation(self):
        """Test hit_rate calculation."""
        stats = CacheStats(l1_hits=50, l2_hits=25, misses=25)
        # (50 + 25) / 100 = 0.75
        assert stats.hit_rate == 0.75

    def test_to_dict(self):
        """Test stats serialization."""
        stats = CacheStats(
            l1_hits=10,
            l2_hits=5,
            misses=5,
            stores=20,
            errors=1,
            avg_l1_latency_ms=1.5,
            avg_l2_latency_ms=15.0,
        )

        d = stats.to_dict()

        assert d["l1_hits"] == 10
        assert d["hit_rate"] == "75.0%"
        assert d["avg_l1_latency_ms"] == "1.5"


class TestCacheConfig:
    """Tests for CacheConfig defaults."""

    def test_default_values(self):
        """Test default configuration values."""
        config = CacheConfig()

        assert config.redis_url == "redis://localhost:6379/1"
        assert config.l1_ttl_seconds == 3600
        assert config.qdrant_port == 6333
        assert config.embedding_dim == 768
        assert config.similarity_threshold == 0.80
        assert config.max_cached_results == 20

    def test_custom_values(self):
        """Test custom configuration values."""
        config = CacheConfig(
            similarity_threshold=0.90,
            l1_ttl_seconds=7200,
        )

        assert config.similarity_threshold == 0.90
        assert config.l1_ttl_seconds == 7200


class TestQueryHashing:
    """Tests for query hash generation."""

    def test_hash_consistency(self):
        """Test same query produces same hash."""
        cache = SemanticCache()
        hash1 = cache._hash_query("test query")
        hash2 = cache._hash_query("test query")
        assert hash1 == hash2

    def test_hash_case_insensitive(self):
        """Test hash is case-insensitive."""
        cache = SemanticCache()
        hash1 = cache._hash_query("Test Query")
        hash2 = cache._hash_query("test query")
        assert hash1 == hash2

    def test_hash_trims_whitespace(self):
        """Test hash trims whitespace."""
        cache = SemanticCache()
        hash1 = cache._hash_query("  test query  ")
        hash2 = cache._hash_query("test query")
        assert hash1 == hash2

    def test_hash_includes_engines(self):
        """Test hash includes engines when provided."""
        cache = SemanticCache()
        hash1 = cache._hash_query("test", engines=["brave", "bing"])
        hash2 = cache._hash_query("test", engines=["bing", "brave"])  # Different order
        # Engines are sorted, so hash should be same
        assert hash1 == hash2

        hash3 = cache._hash_query("test", engines=["brave"])
        assert hash1 != hash3  # Different engines = different hash


class TestSemanticCacheL1:
    """Tests for L1 (Redis) cache operations."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        mock = AsyncMock()
        mock.ping = AsyncMock()
        mock.get = AsyncMock(return_value=None)
        mock.setex = AsyncMock()
        mock.delete = AsyncMock()
        mock.keys = AsyncMock(return_value=[])
        return mock

    @pytest.mark.asyncio
    async def test_l1_hit(self, mock_redis):
        """Test L1 cache hit."""
        cache = SemanticCache()
        cache._redis = mock_redis
        cache._initialized = True

        entry_data = {
            "query": "test",
            "query_hash": "abc123",
            "results": [{"url": "https://example.com"}],
            "engines": ["brave"],
            "timestamp": time.time(),
            "ttl_seconds": 3600,
            "hit_count": 0,
        }
        mock_redis.get.return_value = json.dumps(entry_data)

        entry, level = await cache.get("test")

        assert level == "l1"
        assert entry is not None
        assert entry.query == "test"
        cache.stats.l1_hits == 1

    @pytest.mark.asyncio
    async def test_l1_miss(self, mock_redis):
        """Test L1 cache miss."""
        cache = SemanticCache()
        cache._redis = mock_redis
        cache._initialized = True
        mock_redis.get.return_value = None

        entry, level = await cache.get("test")

        assert level == "miss"
        assert entry is None

    @pytest.mark.asyncio
    async def test_l1_expired_entry_skipped(self, mock_redis):
        """Test expired L1 entries are skipped."""
        cache = SemanticCache()
        cache._redis = mock_redis
        cache._initialized = True

        # Entry expired 2 hours ago
        entry_data = {
            "query": "test",
            "query_hash": "abc123",
            "results": [],
            "engines": ["brave"],
            "timestamp": time.time() - 7200,
            "ttl_seconds": 3600,
            "hit_count": 0,
        }
        mock_redis.get.return_value = json.dumps(entry_data)

        entry, level = await cache.get("test")

        assert level == "miss"


class TestSemanticCacheStore:
    """Tests for cache store operations."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        mock = AsyncMock()
        mock.setex = AsyncMock()
        return mock

    @pytest.mark.asyncio
    async def test_store_l1(self, mock_redis):
        """Test storing in L1 cache."""
        cache = SemanticCache()
        cache._redis = mock_redis
        cache._initialized = True

        results = [{"url": "https://example.com", "title": "Example"}]

        success = await cache.store(
            query="test query",
            results=results,
            engines=["brave"],
        )

        assert success is True
        mock_redis.setex.assert_called_once()
        assert cache.stats.stores == 1

    @pytest.mark.asyncio
    async def test_store_limits_results(self):
        """Test store limits results to max_cached_results."""
        config = CacheConfig(max_cached_results=5)
        cache = SemanticCache(config)
        cache._initialized = True
        cache._redis = AsyncMock()
        cache._redis.setex = AsyncMock()

        # Try to store 10 results
        results = [{"url": f"https://example{i}.com"} for i in range(10)]

        await cache.store("test", results, ["brave"])

        # Check the call to see how many results were stored
        call_args = cache._redis.setex.call_args
        stored_data = json.loads(call_args[0][2])
        assert len(stored_data["results"]) == 5


class TestSemanticCacheInvalidate:
    """Tests for cache invalidation."""

    @pytest.mark.asyncio
    async def test_invalidate_l1(self):
        """Test invalidating L1 cache entry."""
        cache = SemanticCache()
        cache._initialized = True
        cache._redis = AsyncMock()
        cache._redis.delete = AsyncMock()

        success = await cache.invalidate("test query")

        assert success is True
        cache._redis.delete.assert_called_once()


class TestSemanticCacheClear:
    """Tests for cache clearing."""

    @pytest.mark.asyncio
    async def test_clear_l1(self):
        """Test clearing L1 cache."""
        cache = SemanticCache()
        cache._initialized = True
        cache._redis = AsyncMock()
        cache._redis.keys = AsyncMock(return_value=["search:abc", "search:def"])
        cache._redis.delete = AsyncMock()

        await cache.clear()

        cache._redis.keys.assert_called_with("search:*")
        cache._redis.delete.assert_called()


class TestSemanticCacheGetStats:
    """Tests for statistics retrieval."""

    def test_get_stats(self):
        """Test getting cache statistics."""
        cache = SemanticCache()
        cache.stats.l1_hits = 100
        cache.stats.l2_hits = 50
        cache.stats.misses = 50

        stats = cache.get_stats()

        assert stats["l1_hits"] == 100
        assert stats["l2_hits"] == 50
        assert stats["hit_rate"] == "75.0%"


class TestSemanticCacheInitialize:
    """Tests for cache initialization."""

    @pytest.mark.asyncio
    async def test_initialize_already_initialized(self):
        """Test initialize returns True if already initialized."""
        cache = SemanticCache()
        cache._initialized = True

        result = await cache.initialize()

        assert result is True

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing cache connections."""
        cache = SemanticCache()
        cache._initialized = True
        cache._redis = AsyncMock()
        cache._http_client = AsyncMock()

        await cache.close()

        assert cache._initialized is False
        cache._redis.close.assert_called_once()
        cache._http_client.aclose.assert_called_once()


class TestSingleton:
    """Tests for singleton pattern."""

    def test_singleton_returns_same_instance(self):
        """Test get_cache returns singleton."""
        import semantic_cache

        # Reset singleton
        semantic_cache._cache = None

        cache1 = get_cache()
        cache2 = get_cache()

        assert cache1 is cache2

        # Cleanup
        semantic_cache._cache = None
