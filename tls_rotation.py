#!/usr/bin/env python3
"""
TLS Fingerprint Rotation for Anti-Detection

Uses curl_cffi to impersonate real browser TLS fingerprints,
preventing bot detection by search engines and websites.

Features:
- Random browser impersonation (Chrome, Firefox, Safari, Edge)
- Weighted selection favoring common browsers
- Async HTTP client with browser-like TLS
- Automatic rotation per request or per session
"""

import asyncio
import random
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)

try:
    from curl_cffi.requests import AsyncSession
    from curl_cffi import CurlError
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False
    AsyncSession = None
    CurlError = Exception
    logger.warning("curl_cffi not available - TLS rotation disabled")


class BrowserImpersonation(Enum):
    """Available browser impersonations in curl_cffi (tested and working)."""
    # Chrome versions (most common)
    CHROME_120 = "chrome120"
    CHROME_119 = "chrome119"
    CHROME_116 = "chrome116"
    CHROME_110 = "chrome110"
    CHROME_104 = "chrome104"
    CHROME_101 = "chrome101"
    CHROME_99 = "chrome99"

    # Safari versions (working)
    SAFARI_17_0 = "safari17_0"
    SAFARI_15_5 = "safari15_5"
    SAFARI_15_3 = "safari15_3"

    # Edge versions (working)
    EDGE_101 = "edge101"
    EDGE_99 = "edge99"


# Weighted browser selection (Chrome most common, then Safari, Edge)
# Firefox not supported in curl_cffi 0.14
BROWSER_WEIGHTS: Dict[BrowserImpersonation, float] = {
    # Chrome (65% market share) - primary target
    BrowserImpersonation.CHROME_120: 25.0,
    BrowserImpersonation.CHROME_119: 18.0,
    BrowserImpersonation.CHROME_116: 12.0,
    BrowserImpersonation.CHROME_110: 8.0,
    BrowserImpersonation.CHROME_104: 5.0,
    BrowserImpersonation.CHROME_101: 3.0,
    BrowserImpersonation.CHROME_99: 2.0,

    # Safari (20% market share - mostly mobile)
    BrowserImpersonation.SAFARI_17_0: 12.0,
    BrowserImpersonation.SAFARI_15_5: 6.0,
    BrowserImpersonation.SAFARI_15_3: 4.0,

    # Edge (5% market share)
    BrowserImpersonation.EDGE_101: 3.0,
    BrowserImpersonation.EDGE_99: 2.0,
}


@dataclass
class TLSConfig:
    """Configuration for TLS rotation."""
    rotate_per_request: bool = False  # Rotate on every request
    rotate_per_session: bool = True   # Rotate per session creation
    session_ttl_seconds: int = 300    # Session lifetime before rotation
    timeout: float = 30.0             # Request timeout
    verify: bool = True               # Verify SSL certificates
    proxy: Optional[str] = None       # Optional SOCKS5/HTTP proxy

    # Browser family preferences (adjust weights)
    prefer_chrome: bool = True        # Higher Chrome weight
    prefer_modern: bool = True        # Prefer newer versions


@dataclass
class TLSStats:
    """Statistics for TLS rotation."""
    requests: int = 0
    successful: int = 0
    failed: int = 0
    rotations: int = 0
    browsers_used: Dict[str, int] = field(default_factory=dict)

    def record_request(self, browser: str, success: bool):
        self.requests += 1
        if success:
            self.successful += 1
        else:
            self.failed += 1
        self.browsers_used[browser] = self.browsers_used.get(browser, 0) + 1


class TLSRotator:
    """
    Manages TLS fingerprint rotation for anti-detection.

    Uses curl_cffi to impersonate real browser TLS fingerprints,
    making requests appear to come from genuine browsers rather
    than Python scripts.
    """

    def __init__(self, config: Optional[TLSConfig] = None):
        self.config = config or TLSConfig()
        self._session: Optional[AsyncSession] = None
        self._current_browser: Optional[BrowserImpersonation] = None
        self._session_created_at: float = 0.0
        self._stats = TLSStats()
        self._lock = asyncio.Lock()

        if not CURL_CFFI_AVAILABLE:
            logger.warning("TLSRotator initialized without curl_cffi - using fallback")

    def _select_browser(self) -> BrowserImpersonation:
        """Select a random browser based on weighted distribution."""
        browsers = list(BROWSER_WEIGHTS.keys())
        weights = list(BROWSER_WEIGHTS.values())

        # Adjust weights based on config
        if self.config.prefer_modern:
            # Boost newer versions
            modern = ["120", "119", "117", "17_0"]
            weights = [
                w * 1.5 if any(m in b.value for m in modern) else w
                for w, b in zip(weights, browsers)
            ]

        selected = random.choices(browsers, weights=weights, k=1)[0]
        return selected

    async def _get_session(self) -> AsyncSession:
        """Get or create an async session with browser impersonation."""
        import time

        async with self._lock:
            now = time.time()
            session_expired = (
                now - self._session_created_at > self.config.session_ttl_seconds
            )

            # Create new session if needed
            if self._session is None or session_expired or self.config.rotate_per_request:
                if self._session:
                    try:
                        await self._session.close()
                    except Exception:
                        pass

                # Select browser
                browser = self._select_browser()
                self._current_browser = browser
                self._stats.rotations += 1

                logger.debug(f"TLS rotation: using {browser.value}")

                # Create session with browser impersonation
                self._session = AsyncSession(
                    impersonate=browser.value,
                    timeout=self.config.timeout,
                    verify=self.config.verify,
                    proxies={"all": self.config.proxy} if self.config.proxy else None
                )
                self._session_created_at = now

            return self._session

    async def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> Tuple[int, str, Dict[str, str]]:
        """
        Perform GET request with browser TLS impersonation.

        Args:
            url: Request URL
            params: Query parameters
            headers: Additional headers
            **kwargs: Additional arguments for curl_cffi

        Returns:
            Tuple of (status_code, text, response_headers)
        """
        if not CURL_CFFI_AVAILABLE:
            raise RuntimeError("curl_cffi not available")

        session = await self._get_session()
        browser = self._current_browser.value if self._current_browser else "unknown"

        try:
            response = await session.get(
                url,
                params=params,
                headers=headers,
                **kwargs
            )

            self._stats.record_request(browser, True)

            return (
                response.status_code,
                response.text,
                dict(response.headers)
            )

        except CurlError as e:
            self._stats.record_request(browser, False)
            logger.error(f"TLS request failed: {e}")
            raise
        except Exception as e:
            self._stats.record_request(browser, False)
            raise

    async def get_json(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Perform GET request and parse JSON response.

        Returns:
            Parsed JSON response
        """
        if not CURL_CFFI_AVAILABLE:
            raise RuntimeError("curl_cffi not available")

        session = await self._get_session()
        browser = self._current_browser.value if self._current_browser else "unknown"

        try:
            response = await session.get(
                url,
                params=params,
                headers=headers,
                **kwargs
            )

            self._stats.record_request(browser, True)
            return response.json()

        except CurlError as e:
            self._stats.record_request(browser, False)
            logger.error(f"TLS request failed: {e}")
            raise
        except Exception as e:
            self._stats.record_request(browser, False)
            raise

    @property
    def current_browser(self) -> Optional[str]:
        """Get current browser impersonation."""
        return self._current_browser.value if self._current_browser else None

    def get_stats(self) -> Dict[str, Any]:
        """Get rotation statistics."""
        return {
            "requests": self._stats.requests,
            "successful": self._stats.successful,
            "failed": self._stats.failed,
            "rotations": self._stats.rotations,
            "browsers_used": self._stats.browsers_used,
            "current_browser": self.current_browser,
            "success_rate": (
                self._stats.successful / self._stats.requests
                if self._stats.requests > 0 else 0.0
            )
        }

    async def close(self):
        """Close the session."""
        if self._session:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None


# Singleton instance
_tls_rotator: Optional[TLSRotator] = None


def get_tls_rotator(config: Optional[TLSConfig] = None) -> TLSRotator:
    """Get or create the TLS rotator singleton."""
    global _tls_rotator
    if _tls_rotator is None:
        _tls_rotator = TLSRotator(config)
    return _tls_rotator


def is_tls_available() -> bool:
    """Check if TLS rotation is available."""
    return CURL_CFFI_AVAILABLE


async def example_usage():
    """Demonstrate TLS rotation."""
    if not CURL_CFFI_AVAILABLE:
        print("curl_cffi not available - install with: pip install curl-cffi")
        return

    rotator = get_tls_rotator(TLSConfig(
        rotate_per_request=True,  # Rotate on every request
        timeout=30.0
    ))

    print("=== TLS Fingerprint Rotation Demo ===\n")

    # Make several requests with rotation
    urls = [
        "https://httpbin.org/headers",
        "https://httpbin.org/user-agent",
        "https://httpbin.org/ip",
    ]

    for url in urls:
        try:
            status, text, headers = await rotator.get(url)
            print(f"Browser: {rotator.current_browser}")
            print(f"URL: {url}")
            print(f"Status: {status}")
            print(f"Response: {text[:200]}...")
            print("-" * 50)
        except Exception as e:
            print(f"Error: {e}")

    # Print stats
    print("\n=== Stats ===")
    stats = rotator.get_stats()
    print(f"Total requests: {stats['requests']}")
    print(f"Rotations: {stats['rotations']}")
    print(f"Browsers used: {stats['browsers_used']}")
    print(f"Success rate: {stats['success_rate']:.1%}")

    await rotator.close()


if __name__ == "__main__":
    asyncio.run(example_usage())
