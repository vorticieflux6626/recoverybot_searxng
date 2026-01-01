#!/usr/bin/env python3
"""
Intelligent Request Throttler for SearXNG

Implements human-like request timing using:
- Poisson process for inter-request delays
- Exponential backoff with full jitter on failures
- Circuit breaker pattern for failing engines
- Adaptive rate limiting based on response patterns

Reference: AWS Architecture Blog - Exponential Backoff and Jitter
https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
"""

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional
import math


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class EngineHealth:
    """Track health metrics for a search engine."""
    name: str
    consecutive_failures: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    circuit_state: CircuitState = CircuitState.CLOSED
    current_backoff: float = 1.0  # Starting backoff in seconds
    total_requests: int = 0
    total_failures: int = 0

    # Circuit breaker thresholds
    failure_threshold: int = 3
    recovery_timeout: float = 60.0  # Seconds before trying again

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate (0.0 to 1.0)."""
        if self.total_requests == 0:
            return 0.0
        return self.total_failures / self.total_requests


class IntelligentThrottler:
    """
    Implements intelligent request throttling with human-like timing.

    Features:
    - Poisson-distributed delays between requests (mimics human behavior)
    - Exponential backoff with full jitter on failures
    - Per-engine circuit breakers
    - Adaptive rate limiting based on response patterns
    """

    # Backoff configuration (AWS recommended values)
    BASE_DELAY = 1.0        # Base delay in seconds
    MAX_DELAY = 60.0        # Maximum backoff delay
    JITTER_FACTOR = 1.0     # Full jitter (0.0 = no jitter, 1.0 = full)

    # Human-like timing parameters
    MIN_HUMAN_DELAY = 0.5   # Minimum "reading time"
    MAX_HUMAN_DELAY = 3.0   # Maximum "reading time"
    POISSON_RATE = 0.5      # Average requests per second (human pace)

    def __init__(self):
        self.engine_health: Dict[str, EngineHealth] = {}
        self.last_request_time: float = 0.0
        self._lock = asyncio.Lock()

    def _get_engine_health(self, engine: str) -> EngineHealth:
        """Get or create health tracker for engine."""
        if engine not in self.engine_health:
            self.engine_health[engine] = EngineHealth(name=engine)
        return self.engine_health[engine]

    def _poisson_delay(self) -> float:
        """
        Generate Poisson-distributed inter-arrival time.

        Uses exponential distribution (continuous analog of Poisson process)
        to simulate natural human request patterns.
        """
        # Exponential distribution for inter-arrival times
        # Mean = 1/rate, so rate=0.5 means avg 2 seconds between requests
        delay = random.expovariate(self.POISSON_RATE)
        # Clamp to reasonable bounds
        return max(self.MIN_HUMAN_DELAY, min(delay, self.MAX_HUMAN_DELAY * 2))

    def _full_jitter_backoff(self, attempt: int) -> float:
        """
        Calculate exponential backoff with full jitter.

        Full jitter provides best performance in contention scenarios
        by spreading retries uniformly across the backoff window.

        Formula: sleep = random(0, min(cap, base * 2^attempt))
        """
        # Calculate exponential backoff
        exp_backoff = self.BASE_DELAY * (2 ** attempt)
        # Apply cap
        capped = min(exp_backoff, self.MAX_DELAY)
        # Apply full jitter (uniform random from 0 to capped)
        return random.uniform(0, capped)

    def _decorrelated_jitter_backoff(self, previous_delay: float) -> float:
        """
        Alternative: Decorrelated jitter backoff.

        Increases jitter range based on previous delay, providing
        good spread while maintaining correlation with failure severity.

        Formula: sleep = random(base, previous_delay * 3)
        """
        return random.uniform(self.BASE_DELAY, min(previous_delay * 3, self.MAX_DELAY))

    async def wait_before_request(self, engine: str = "default") -> float:
        """
        Wait appropriate time before making a request.

        Returns the actual delay applied (for logging/metrics).
        """
        async with self._lock:
            health = self._get_engine_health(engine)
            now = time.time()

            # Check circuit breaker
            if health.circuit_state == CircuitState.OPEN:
                time_since_failure = now - health.last_failure_time
                if time_since_failure < health.recovery_timeout:
                    # Still in cooldown
                    remaining = health.recovery_timeout - time_since_failure
                    raise CircuitOpenError(
                        f"Engine {engine} circuit open, retry in {remaining:.1f}s"
                    )
                # Try half-open
                health.circuit_state = CircuitState.HALF_OPEN

            # Calculate delay
            if health.consecutive_failures > 0:
                # Use exponential backoff with jitter
                delay = self._full_jitter_backoff(health.consecutive_failures)
            else:
                # Use human-like Poisson delay
                time_since_last = now - self.last_request_time
                if time_since_last < self.MIN_HUMAN_DELAY:
                    delay = self._poisson_delay()
                else:
                    # Already waited enough
                    delay = max(0, self.MIN_HUMAN_DELAY - time_since_last)

            self.last_request_time = now + delay
            health.total_requests += 1

        if delay > 0:
            await asyncio.sleep(delay)

        return delay

    def record_success(self, engine: str = "default"):
        """Record successful request - reset backoff."""
        health = self._get_engine_health(engine)
        health.consecutive_failures = 0
        health.current_backoff = self.BASE_DELAY
        health.last_success_time = time.time()

        if health.circuit_state == CircuitState.HALF_OPEN:
            health.circuit_state = CircuitState.CLOSED

    def record_failure(self, engine: str = "default",
                       error_type: str = "unknown") -> float:
        """
        Record failed request - increase backoff.

        Returns the new backoff delay for informational purposes.
        """
        health = self._get_engine_health(engine)
        health.consecutive_failures += 1
        health.total_failures += 1
        health.last_failure_time = time.time()

        # Update backoff using decorrelated jitter for next attempt
        health.current_backoff = self._decorrelated_jitter_backoff(
            health.current_backoff
        )

        # Check if circuit should open
        if health.consecutive_failures >= health.failure_threshold:
            health.circuit_state = CircuitState.OPEN
            # Increase recovery timeout based on error type
            if error_type in ("captcha", "access_denied"):
                health.recovery_timeout = min(
                    health.recovery_timeout * 2,
                    600.0  # Max 10 minutes
                )

        return health.current_backoff

    def get_engine_status(self, engine: str = "default") -> dict:
        """Get current status of an engine."""
        health = self._get_engine_health(engine)
        return {
            "name": health.name,
            "circuit_state": health.circuit_state.value,
            "consecutive_failures": health.consecutive_failures,
            "failure_rate": f"{health.failure_rate:.1%}",
            "current_backoff": f"{health.current_backoff:.1f}s",
            "recovery_timeout": f"{health.recovery_timeout:.0f}s",
        }

    def get_all_status(self) -> dict:
        """Get status of all tracked engines."""
        return {
            name: self.get_engine_status(name)
            for name in self.engine_health
        }


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


# Singleton instance for use across the application
_throttler: Optional[IntelligentThrottler] = None


def get_throttler() -> IntelligentThrottler:
    """Get singleton throttler instance."""
    global _throttler
    if _throttler is None:
        _throttler = IntelligentThrottler()
    return _throttler


# Example usage
async def example_usage():
    """Demonstrate throttler usage."""
    throttler = get_throttler()

    engines = ["brave", "bing", "mojeek", "reddit"]

    for i in range(10):
        engine = random.choice(engines)

        try:
            # Wait before request
            delay = await throttler.wait_before_request(engine)
            print(f"[{i+1}] Waited {delay:.2f}s before {engine} request")

            # Simulate request (random success/failure)
            if random.random() > 0.8:  # 20% failure rate
                throttler.record_failure(engine, "rate_limit")
                print(f"  -> Failed! Backoff: {throttler.get_engine_status(engine)}")
            else:
                throttler.record_success(engine)
                print(f"  -> Success")

        except CircuitOpenError as e:
            print(f"[{i+1}] {e}")

    print("\nFinal status:")
    for status in throttler.get_all_status().values():
        print(f"  {status}")


if __name__ == "__main__":
    asyncio.run(example_usage())
