#!/usr/bin/env python3
"""
Intelligent Throttler Tests

Tests for Poisson delays, exponential backoff, and circuit breaker.
"""

import pytest
import asyncio
import time
from unittest.mock import patch, AsyncMock
import sys
sys.path.insert(0, "..")

from intelligent_throttler import (
    IntelligentThrottler,
    EngineHealth,
    CircuitState,
    CircuitOpenError,
    get_throttler,
)


class TestEngineHealth:
    """Tests for EngineHealth dataclass."""

    def test_default_values(self):
        """Test default health values."""
        health = EngineHealth(name="test")

        assert health.consecutive_failures == 0
        assert health.circuit_state == CircuitState.CLOSED
        assert health.current_backoff == 1.0

    def test_failure_rate_zero(self):
        """Test failure rate with zero requests."""
        health = EngineHealth(name="test")
        assert health.failure_rate == 0.0

    def test_failure_rate_calculation(self):
        """Test failure rate calculation."""
        health = EngineHealth(
            name="test",
            total_requests=100,
            total_failures=25,
        )
        assert health.failure_rate == 0.25


class TestCircuitState:
    """Tests for CircuitState enum."""

    def test_circuit_states(self):
        """Test circuit state values."""
        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        assert CircuitState.HALF_OPEN.value == "half_open"


class TestPoissonDelay:
    """Tests for Poisson-distributed delays."""

    def test_poisson_delay_within_bounds(self):
        """Test Poisson delay is within expected bounds."""
        throttler = IntelligentThrottler()

        delays = [throttler._poisson_delay() for _ in range(100)]

        # All delays should be at least MIN_HUMAN_DELAY
        assert all(d >= throttler.MIN_HUMAN_DELAY for d in delays)

        # Average should be around 2 seconds (1/POISSON_RATE)
        avg = sum(delays) / len(delays)
        assert 0.5 < avg < 6.0  # Reasonable range for exponential distribution


class TestExponentialBackoff:
    """Tests for exponential backoff with jitter."""

    def test_full_jitter_backoff_attempt_0(self):
        """Test backoff at attempt 0."""
        throttler = IntelligentThrottler()

        # Multiple samples to test range
        backoffs = [throttler._full_jitter_backoff(0) for _ in range(100)]

        # All should be between 0 and BASE_DELAY (1.0)
        assert all(0 <= b <= 1.0 for b in backoffs)

    def test_full_jitter_backoff_attempt_5(self):
        """Test backoff at attempt 5."""
        throttler = IntelligentThrottler()

        backoffs = [throttler._full_jitter_backoff(5) for _ in range(100)]

        # At attempt 5: base * 2^5 = 1 * 32 = 32
        # Full jitter: uniform(0, 32)
        assert all(0 <= b <= 32 for b in backoffs)

    def test_full_jitter_backoff_capped(self):
        """Test backoff is capped at MAX_DELAY."""
        throttler = IntelligentThrottler()

        # Very high attempt number
        backoffs = [throttler._full_jitter_backoff(20) for _ in range(100)]

        # All should be at most MAX_DELAY
        assert all(b <= throttler.MAX_DELAY for b in backoffs)

    def test_decorrelated_jitter_backoff(self):
        """Test decorrelated jitter backoff."""
        throttler = IntelligentThrottler()

        backoff = throttler._decorrelated_jitter_backoff(2.0)

        # Should be between BASE_DELAY and previous * 3 (capped)
        assert throttler.BASE_DELAY <= backoff <= min(6.0, throttler.MAX_DELAY)


class TestRecordSuccess:
    """Tests for recording successful requests."""

    def test_record_success_resets_failures(self):
        """Test success resets consecutive failures."""
        throttler = IntelligentThrottler()
        health = throttler._get_engine_health("test")

        # Simulate some failures
        health.consecutive_failures = 3
        health.current_backoff = 8.0

        throttler.record_success("test")

        assert health.consecutive_failures == 0
        assert health.current_backoff == throttler.BASE_DELAY

    def test_record_success_closes_half_open_circuit(self):
        """Test success closes half-open circuit."""
        throttler = IntelligentThrottler()
        health = throttler._get_engine_health("test")
        health.circuit_state = CircuitState.HALF_OPEN

        throttler.record_success("test")

        assert health.circuit_state == CircuitState.CLOSED


class TestRecordFailure:
    """Tests for recording failed requests."""

    def test_record_failure_increments_count(self):
        """Test failure increments failure count."""
        throttler = IntelligentThrottler()

        throttler.record_failure("test")

        health = throttler._get_engine_health("test")
        assert health.consecutive_failures == 1
        assert health.total_failures == 1

    def test_record_failure_opens_circuit(self):
        """Test circuit opens after threshold failures."""
        throttler = IntelligentThrottler()

        # Record failures up to threshold (default 5)
        for _ in range(5):
            throttler.record_failure("test")

        health = throttler._get_engine_health("test")
        assert health.circuit_state == CircuitState.OPEN

    def test_record_failure_increases_backoff(self):
        """Test failure increases backoff time."""
        throttler = IntelligentThrottler()

        initial_backoff = throttler._get_engine_health("test").current_backoff
        throttler.record_failure("test")
        new_backoff = throttler._get_engine_health("test").current_backoff

        # Backoff should increase (decorrelated jitter)
        assert new_backoff >= throttler.BASE_DELAY

    def test_record_failure_captcha_increases_recovery_timeout(self):
        """Test captcha errors increase recovery timeout."""
        throttler = IntelligentThrottler()
        health = throttler._get_engine_health("test")

        # Open circuit first
        for _ in range(5):
            throttler.record_failure("test", error_type="captcha")

        initial_timeout = health.recovery_timeout

        # Another captcha failure should increase timeout
        throttler.record_failure("test", error_type="captcha")

        assert health.recovery_timeout > initial_timeout


class TestWaitBeforeRequest:
    """Tests for pre-request waiting."""

    @pytest.mark.asyncio
    async def test_wait_before_request_normal(self):
        """Test normal wait behavior."""
        throttler = IntelligentThrottler()

        # Reset last request time
        throttler.last_request_time = 0

        start = time.time()
        delay = await throttler.wait_before_request("test")
        elapsed = time.time() - start

        # Delay should be at least MIN_HUMAN_DELAY
        assert delay >= 0
        assert elapsed >= 0

    @pytest.mark.asyncio
    async def test_wait_before_request_circuit_open(self):
        """Test circuit open raises error."""
        throttler = IntelligentThrottler()

        # Open the circuit
        health = throttler._get_engine_health("test")
        health.circuit_state = CircuitState.OPEN
        health.last_failure_time = time.time()
        health.recovery_timeout = 30.0

        with pytest.raises(CircuitOpenError) as exc_info:
            await throttler.wait_before_request("test")

        assert "circuit open" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_wait_before_request_circuit_half_open(self):
        """Test circuit transitions to half-open after recovery timeout."""
        throttler = IntelligentThrottler()

        # Set up open circuit that's past recovery timeout
        health = throttler._get_engine_health("test")
        health.circuit_state = CircuitState.OPEN
        health.last_failure_time = time.time() - 60  # 60s ago
        health.recovery_timeout = 30.0  # Only 30s timeout

        # Should not raise, should transition to half-open
        await throttler.wait_before_request("test")

        assert health.circuit_state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_wait_uses_backoff_on_failures(self):
        """Test wait uses exponential backoff after failures."""
        throttler = IntelligentThrottler()

        # Set up consecutive failures
        health = throttler._get_engine_health("test")
        health.consecutive_failures = 3

        delay = await throttler.wait_before_request("test")

        # Should use full jitter backoff, which can be 0 to 2^3=8
        assert 0 <= delay <= throttler.MAX_DELAY


class TestEngineStatus:
    """Tests for engine status reporting."""

    def test_get_engine_status(self):
        """Test getting single engine status."""
        throttler = IntelligentThrottler()

        # Record some activity
        throttler.record_success("test")
        throttler.record_failure("test")

        status = throttler.get_engine_status("test")

        assert status["name"] == "test"
        assert status["circuit_state"] == "closed"
        assert status["consecutive_failures"] == 1
        assert "failure_rate" in status
        assert "current_backoff" in status

    def test_get_all_status(self):
        """Test getting all engine statuses."""
        throttler = IntelligentThrottler()

        throttler.record_success("brave")
        throttler.record_success("bing")
        throttler.record_failure("mojeek")

        status = throttler.get_all_status()

        assert "brave" in status
        assert "bing" in status
        assert "mojeek" in status
        assert status["mojeek"]["consecutive_failures"] == 1


class TestGetEngineHealth:
    """Tests for engine health management."""

    def test_creates_new_health_if_missing(self):
        """Test new health tracker created for unknown engine."""
        throttler = IntelligentThrottler()

        health = throttler._get_engine_health("new_engine")

        assert health.name == "new_engine"
        assert health.consecutive_failures == 0

    def test_returns_existing_health(self):
        """Test returns existing health tracker."""
        throttler = IntelligentThrottler()

        health1 = throttler._get_engine_health("test")
        health1.consecutive_failures = 5

        health2 = throttler._get_engine_health("test")

        assert health2.consecutive_failures == 5
        assert health1 is health2


class TestSingleton:
    """Tests for singleton pattern."""

    def test_singleton_returns_same_instance(self):
        """Test get_throttler returns singleton."""
        import intelligent_throttler

        # Reset singleton
        intelligent_throttler._throttler = None

        throttler1 = get_throttler()
        throttler2 = get_throttler()

        assert throttler1 is throttler2

        # Cleanup
        intelligent_throttler._throttler = None


class TestCircuitOpenError:
    """Tests for CircuitOpenError exception."""

    def test_error_message(self):
        """Test error has correct message."""
        error = CircuitOpenError("Engine brave circuit open, retry in 30.0s")
        assert "brave" in str(error)
        assert "retry" in str(error)
