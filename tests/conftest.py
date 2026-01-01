"""
Pytest configuration for SearXNG contract tests
"""

import pytest
import httpx


def pytest_configure(config):
    """Configure pytest markers"""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )


@pytest.fixture(scope="session")
def searxng_available():
    """Check if SearXNG is running before tests"""
    try:
        response = httpx.get("http://localhost:8888/healthz", timeout=5.0)
        return response.status_code == 200
    except Exception:
        return False


@pytest.fixture(autouse=True)
def skip_if_searxng_unavailable(request, searxng_available):
    """Skip tests if SearXNG is not running"""
    if not searxng_available:
        pytest.skip("SearXNG is not running on localhost:8888")
