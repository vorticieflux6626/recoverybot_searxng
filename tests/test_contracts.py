#!/usr/bin/env python3
"""
SearXNG Contract Tests

Validates that SearXNG API responses conform to expected format.
Run with: pytest tests/test_contracts.py -v
"""

import pytest
import httpx
import asyncio
from typing import Dict, Any, List

SEARXNG_URL = "http://localhost:8888"


@pytest.fixture
def searxng_client():
    """Create HTTP client for SearXNG"""
    return httpx.Client(timeout=30.0)


class TestSearXNGContracts:
    """Contract tests for SearXNG JSON API"""

    def test_health_endpoint(self, searxng_client):
        """Verify SearXNG is responding"""
        response = searxng_client.get(f"{SEARXNG_URL}/healthz")
        assert response.status_code == 200

    def test_search_returns_json(self, searxng_client):
        """Verify search returns valid JSON"""
        response = searxng_client.get(
            f"{SEARXNG_URL}/search",
            params={"q": "test", "format": "json"}
        )
        assert response.status_code == 200
        assert response.headers.get("content-type", "").startswith("application/json")
        data = response.json()
        assert isinstance(data, dict)

    def test_search_response_structure(self, searxng_client):
        """Verify search response has required fields"""
        response = searxng_client.get(
            f"{SEARXNG_URL}/search",
            params={"q": "python", "format": "json"}
        )
        data = response.json()

        # Required top-level fields
        assert "results" in data, "Response missing 'results' field"
        assert "query" in data, "Response missing 'query' field"
        assert isinstance(data["results"], list), "'results' must be a list"

    def test_result_item_structure(self, searxng_client):
        """Verify each result item has required fields"""
        response = searxng_client.get(
            f"{SEARXNG_URL}/search",
            params={"q": "python tutorial", "format": "json", "engines": "brave,bing"}
        )
        data = response.json()

        if len(data["results"]) > 0:
            result = data["results"][0]

            # Required fields per result
            assert "title" in result, "Result missing 'title'"
            assert "url" in result, "Result missing 'url'"
            assert "engine" in result, "Result missing 'engine'"

            # Type validation
            assert isinstance(result["title"], str), "'title' must be string"
            assert isinstance(result["url"], str), "'url' must be string"
            assert result["url"].startswith(("http://", "https://")), "'url' must be valid URL"

    def test_engine_parameter(self, searxng_client):
        """Verify engine filtering works"""
        response = searxng_client.get(
            f"{SEARXNG_URL}/search",
            params={"q": "test", "format": "json", "engines": "wikipedia"}
        )
        data = response.json()

        # All results should be from Wikipedia
        for result in data["results"]:
            assert result.get("engine") == "wikipedia", f"Expected wikipedia, got {result.get('engine')}"

    def test_categories_parameter(self, searxng_client):
        """Verify category filtering works"""
        response = searxng_client.get(
            f"{SEARXNG_URL}/search",
            params={"q": "machine learning", "format": "json", "categories": "science"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["results"], list)

    def test_empty_query_handling(self, searxng_client):
        """Verify empty query is handled gracefully"""
        response = searxng_client.get(
            f"{SEARXNG_URL}/search",
            params={"q": "", "format": "json"}
        )
        # Should return 200 with empty results, not error
        assert response.status_code in [200, 400]

    def test_special_characters_in_query(self, searxng_client):
        """Verify special characters are handled"""
        response = searxng_client.get(
            f"{SEARXNG_URL}/search",
            params={"q": "C++ programming", "format": "json"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data

    def test_pagination_parameter(self, searxng_client):
        """Verify pagination works"""
        response = searxng_client.get(
            f"{SEARXNG_URL}/search",
            params={"q": "python", "format": "json", "pageno": 2}
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data


class TestSearXNGEngineGroups:
    """Test that configured engine groups return results"""

    @pytest.mark.parametrize("engines,query", [
        ("brave,bing", "test query"),
        ("wikipedia", "python programming"),
        ("arxiv", "machine learning"),
        ("stackoverflow", "python async"),
        ("reddit", "programming tips"),
    ])
    def test_engine_group_returns_results(self, searxng_client, engines: str, query: str):
        """Verify each engine group returns results"""
        response = searxng_client.get(
            f"{SEARXNG_URL}/search",
            params={"q": query, "format": "json", "engines": engines}
        )
        assert response.status_code == 200
        data = response.json()
        # Note: Some engines may return 0 results for certain queries
        assert "results" in data


class TestSearXNGResponseFormat:
    """Test response format compliance for memOS integration"""

    def test_content_field_exists(self, searxng_client):
        """Verify results have content/snippet field"""
        response = searxng_client.get(
            f"{SEARXNG_URL}/search",
            params={"q": "python tutorial", "format": "json", "engines": "brave"}
        )
        data = response.json()

        for result in data.get("results", [])[:5]:
            # SearXNG uses 'content' for snippets
            assert "content" in result or "snippet" in result, \
                "Result missing content/snippet field"

    def test_score_field_when_available(self, searxng_client):
        """Check if score field is present (optional)"""
        response = searxng_client.get(
            f"{SEARXNG_URL}/search",
            params={"q": "python", "format": "json"}
        )
        data = response.json()

        # Score is optional but if present should be numeric
        for result in data.get("results", []):
            if "score" in result:
                assert isinstance(result["score"], (int, float)), \
                    "'score' must be numeric"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
