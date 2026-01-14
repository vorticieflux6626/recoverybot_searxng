#!/usr/bin/env python3
"""
Result Fusion Tests

Tests for RRF, weighted, and Borda count fusion algorithms.
"""

import pytest
import sys
sys.path.insert(0, "..")

from result_fusion import (
    ResultFusion,
    FusedResult,
    get_fusion_engine,
)


class TestFusedResult:
    """Tests for FusedResult dataclass."""

    def test_engine_count(self):
        """Test engine_count property."""
        result = FusedResult(
            url="https://example.com",
            title="Test",
            content="Test content",
            engines=["brave", "bing", "mojeek"],
        )
        assert result.engine_count == 3

    def test_to_dict(self):
        """Test serialization to dict."""
        result = FusedResult(
            url="https://example.com",
            title="Test",
            content="Test content",
            engines=["brave"],
            rrf_score=0.0123,
            weighted_score=0.456,
            final_score=0.789,
            metadata={"key": "value"},
        )

        d = result.to_dict()

        assert d["url"] == "https://example.com"
        assert d["engines"] == ["brave"]
        assert d["rrf_score"] == 0.0123
        assert d["metadata"]["key"] == "value"


class TestURLNormalization:
    """Tests for URL normalization."""

    def test_removes_trailing_slash(self):
        """Test trailing slash removal."""
        fusion = ResultFusion()
        assert fusion._default_url_normalizer("https://example.com/") == "example.com"

    def test_removes_www(self):
        """Test www prefix removal."""
        fusion = ResultFusion()
        assert fusion._default_url_normalizer("https://www.example.com") == "example.com"

    def test_removes_protocol(self):
        """Test protocol removal."""
        fusion = ResultFusion()
        assert fusion._default_url_normalizer("http://example.com") == "example.com"
        assert fusion._default_url_normalizer("https://example.com") == "example.com"

    def test_lowercase(self):
        """Test URL lowercasing."""
        fusion = ResultFusion()
        assert fusion._default_url_normalizer("HTTPS://EXAMPLE.COM") == "example.com"

    def test_custom_normalizer(self):
        """Test custom URL normalizer."""
        custom = lambda url: url.upper()
        fusion = ResultFusion(url_normalizer=custom)
        assert fusion.url_normalizer("test") == "TEST"


class TestRRFFusion:
    """Tests for Reciprocal Rank Fusion algorithm."""

    def test_rrf_basic(self):
        """Test basic RRF calculation."""
        fusion = ResultFusion(rrf_k=60, engine_weights={"test_engine": 1.0})

        results = {
            "test_engine": [
                {"url": "https://example.com", "title": "Example", "content": "Test"},
            ],
        }

        fused = fusion.fuse(results, method="rrf")

        assert len(fused) == 1
        # RRF score for rank 1 with k=60, weight 1.0: 1/(60+1) = 0.0164
        assert fused[0].rrf_score == pytest.approx(1 / 61, rel=0.01)

    def test_rrf_multiple_engines(self):
        """Test RRF with multiple engines returning same URL."""
        fusion = ResultFusion(rrf_k=60, engine_weights={"brave": 1.0, "bing": 1.0})

        results = {
            "brave": [
                {"url": "https://example.com", "title": "Example", "content": "Test"},
            ],
            "bing": [
                {"url": "https://example.com", "title": "Example 2", "content": "Test 2"},
            ],
        }

        fused = fusion.fuse(results, method="rrf")

        assert len(fused) == 1
        # RRF score: 1/(60+1) + 1/(60+1) = 2/61 (both rank 1)
        assert fused[0].rrf_score == pytest.approx(2 / 61, rel=0.01)
        assert len(fused[0].engines) == 2

    def test_rrf_rank_ordering(self):
        """Test that higher-ranked results get higher RRF scores."""
        fusion = ResultFusion(rrf_k=60)

        results = {
            "brave": [
                {"url": "https://first.com", "title": "First", "content": ""},
                {"url": "https://second.com", "title": "Second", "content": ""},
                {"url": "https://third.com", "title": "Third", "content": ""},
            ],
        }

        fused = fusion.fuse(results, method="rrf")

        assert len(fused) == 3
        # Results should be ordered by RRF score (higher rank = higher score)
        assert fused[0].rrf_score > fused[1].rrf_score > fused[2].rrf_score

    def test_rrf_with_engine_weights(self):
        """Test RRF respects engine weights."""
        fusion = ResultFusion(
            rrf_k=60,
            engine_weights={"trusted": 2.0, "untrusted": 0.5},
        )

        results = {
            "trusted": [
                {"url": "https://trusted.com", "title": "Trusted", "content": ""},
            ],
            "untrusted": [
                {"url": "https://untrusted.com", "title": "Untrusted", "content": ""},
            ],
        }

        fused = fusion.fuse(results, method="rrf")

        # Both rank 1, but trusted has 2x weight
        trusted_result = next(r for r in fused if "trusted.com" in r.url)
        untrusted_result = next(r for r in fused if "untrusted.com" in r.url)

        assert trusted_result.rrf_score > untrusted_result.rrf_score


class TestWeightedFusion:
    """Tests for weighted score fusion algorithm."""

    def test_weighted_basic(self):
        """Test basic weighted score calculation."""
        fusion = ResultFusion()

        results = {
            "brave": [
                {"url": "https://example.com", "title": "Example", "content": "", "score": 0.8},
            ],
        }

        fused = fusion.fuse(results, method="weighted")

        assert len(fused) == 1
        assert fused[0].weighted_score == pytest.approx(0.8, rel=0.1)

    def test_weighted_multiple_engines(self):
        """Test weighted with multiple engines."""
        fusion = ResultFusion(engine_weights={"brave": 1.5, "bing": 1.0})

        results = {
            "brave": [
                {"url": "https://example.com", "title": "Example", "content": "", "score": 0.8},
            ],
            "bing": [
                {"url": "https://example.com", "title": "Example", "content": "", "score": 0.6},
            ],
        }

        fused = fusion.fuse(results, method="weighted")

        # weighted = (1.5 * 0.8 + 1.0 * 0.6) / (1.5 + 1.0) + 0.1 (engine bonus)
        # = (1.2 + 0.6) / 2.5 + 0.1 = 0.72 + 0.1 = 0.82
        assert fused[0].weighted_score > 0.7

    def test_weighted_engine_bonus(self):
        """Test that appearing in multiple engines adds bonus."""
        fusion = ResultFusion(engine_weights={"a": 1.0, "b": 1.0, "c": 1.0})

        # Same score from different numbers of engines
        results_one = {
            "a": [{"url": "https://example.com", "title": "T", "content": "", "score": 0.5}],
        }
        results_three = {
            "a": [{"url": "https://example.com", "title": "T", "content": "", "score": 0.5}],
            "b": [{"url": "https://example.com", "title": "T", "content": "", "score": 0.5}],
            "c": [{"url": "https://example.com", "title": "T", "content": "", "score": 0.5}],
        }

        fused_one = fusion.fuse(results_one, method="weighted")
        fused_three = fusion.fuse(results_three, method="weighted")

        # More engines = higher score due to bonus
        assert fused_three[0].weighted_score > fused_one[0].weighted_score


class TestBordaFusion:
    """Tests for Borda count fusion algorithm."""

    def test_borda_basic(self):
        """Test basic Borda count calculation."""
        fusion = ResultFusion()

        results = {
            "brave": [
                {"url": "https://example.com", "title": "Example", "content": ""},
            ],
        }

        fused = fusion.fuse(results, method="borda")

        assert len(fused) == 1
        assert fused[0].borda_score > 0

    def test_borda_rank_ordering(self):
        """Test Borda prefers higher-ranked results."""
        fusion = ResultFusion()

        results = {
            "brave": [
                {"url": "https://first.com", "title": "First", "content": ""},
                {"url": "https://second.com", "title": "Second", "content": ""},
            ],
        }

        fused = fusion.fuse(results, method="borda")

        # Higher rank = more Borda points
        assert fused[0].borda_score > fused[1].borda_score


class TestHybridFusion:
    """Tests for hybrid fusion algorithm."""

    def test_hybrid_combines_scores(self):
        """Test hybrid combines RRF and weighted scores."""
        fusion = ResultFusion()

        results = {
            "brave": [
                {"url": "https://example.com", "title": "Example", "content": "", "score": 0.9},
            ],
        }

        fused = fusion.fuse(results, method="hybrid")

        # hybrid = 0.6 * rrf + 0.4 * weighted
        expected = 0.6 * fused[0].rrf_score + 0.4 * fused[0].weighted_score
        assert fused[0].final_score == pytest.approx(expected, rel=0.01)


class TestFusionEdgeCases:
    """Tests for edge cases in fusion."""

    def test_empty_results(self):
        """Test fusion with no results."""
        fusion = ResultFusion()
        fused = fusion.fuse({}, method="rrf")
        assert fused == []

    def test_missing_url(self):
        """Test results without URL are skipped."""
        fusion = ResultFusion()

        results = {
            "brave": [
                {"title": "No URL", "content": ""},  # Missing URL
                {"url": "https://example.com", "title": "Has URL", "content": ""},
            ],
        }

        fused = fusion.fuse(results, method="rrf")
        assert len(fused) == 1

    def test_top_k_limit(self):
        """Test top_k parameter limits results."""
        fusion = ResultFusion()

        results = {
            "brave": [{"url": f"https://example{i}.com", "title": f"T{i}", "content": ""} for i in range(10)],
        }

        fused = fusion.fuse(results, method="rrf", top_k=3)
        assert len(fused) == 3

    def test_unknown_method_raises(self):
        """Test unknown fusion method raises ValueError."""
        fusion = ResultFusion()

        results = {
            "brave": [{"url": "https://example.com", "title": "T", "content": ""}],
        }

        with pytest.raises(ValueError, match="Unknown fusion method"):
            fusion.fuse(results, method="nonexistent")

    def test_best_title_content_kept(self):
        """Test that longest title/content is kept when merging."""
        fusion = ResultFusion()

        results = {
            "brave": [
                {"url": "https://example.com", "title": "Short", "content": "A"},
            ],
            "bing": [
                {"url": "https://example.com", "title": "Much Longer Title", "content": "Longer content"},
            ],
        }

        fused = fusion.fuse(results, method="rrf")

        assert fused[0].title == "Much Longer Title"
        assert fused[0].content == "Longer content"


class TestFuseFromSearXNG:
    """Tests for SearXNG-specific fusion helper."""

    def test_fuse_from_searxng(self):
        """Test convenience method for SearXNG results."""
        fusion = ResultFusion()

        # SearXNG format: each result has 'engine' field
        results = [
            {"url": "https://a.com", "title": "A", "content": "", "engine": "brave"},
            {"url": "https://b.com", "title": "B", "content": "", "engine": "brave"},
            {"url": "https://a.com", "title": "A2", "content": "", "engine": "bing"},
        ]

        fused = fusion.fuse_from_searxng(results, method="rrf")

        assert len(fused) == 2
        # https://a.com should have 2 engines
        a_result = next(r for r in fused if "a.com" in r.url)
        assert len(a_result.engines) == 2


class TestSingleton:
    """Tests for singleton pattern."""

    def test_singleton_returns_same_instance(self):
        """Test get_fusion_engine returns singleton."""
        import result_fusion

        # Reset singleton
        result_fusion._fusion = None

        fusion1 = get_fusion_engine()
        fusion2 = get_fusion_engine()

        assert fusion1 is fusion2

        # Cleanup
        result_fusion._fusion = None
