#!/usr/bin/env python3
"""
Feedback Loop for Preset Learning

Tracks search effectiveness and learns optimal engine/preset configurations:
- Records which engines return useful results for query types
- Tracks user engagement signals (clicks, result quality)
- Adjusts engine weights based on historical performance
- Provides recommendations for query routing

This enables the system to improve over time based on actual usage patterns.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
from enum import Enum

logger = logging.getLogger(__name__)

# Optional Redis import
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class FeedbackSignal(Enum):
    """Types of feedback signals."""
    CLICK = "click"           # User clicked a result
    DWELL = "dwell"           # User spent time on result
    REFORMULATE = "reform"    # User reformulated query
    NO_CLICK = "no_click"     # User didn't click any result
    HELPFUL = "helpful"       # Explicit helpful rating
    NOT_HELPFUL = "not_help"  # Explicit not helpful rating


@dataclass
class SearchFeedback:
    """Feedback for a single search result."""
    query: str
    query_type: str  # From QueryRouter (industrial, academic, etc.)
    engine: str
    url: str
    position: int
    signal: FeedbackSignal
    timestamp: float = field(default_factory=time.time)
    session_id: Optional[str] = None
    dwell_time_ms: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "query_type": self.query_type,
            "engine": self.engine,
            "url": self.url,
            "position": self.position,
            "signal": self.signal.value,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "dwell_time_ms": self.dwell_time_ms,
        }


@dataclass
class EnginePerformance:
    """Aggregated performance metrics for an engine."""
    engine: str
    query_type: str
    total_impressions: int = 0
    clicks: int = 0
    dwells: int = 0
    helpful_ratings: int = 0
    not_helpful_ratings: int = 0
    total_dwell_time_ms: int = 0
    avg_click_position: float = 0.0
    last_updated: float = field(default_factory=time.time)

    @property
    def ctr(self) -> float:
        """Click-through rate."""
        if self.total_impressions == 0:
            return 0.0
        return self.clicks / self.total_impressions

    @property
    def engagement_score(self) -> float:
        """
        Composite engagement score (0-1).

        Weights:
        - CTR: 40%
        - Dwell rate: 25%
        - Helpful rate: 25%
        - Position bonus: 10%
        """
        ctr_score = min(self.ctr * 5, 1.0)  # Normalize CTR (20% = 1.0)

        dwell_rate = self.dwells / max(1, self.clicks)
        dwell_score = min(dwell_rate, 1.0)

        helpful_total = self.helpful_ratings + self.not_helpful_ratings
        helpful_rate = self.helpful_ratings / max(1, helpful_total)

        # Higher positions (1, 2, 3) are better
        position_score = 1.0 / max(1, self.avg_click_position) if self.clicks > 0 else 0.5

        return (
            0.40 * ctr_score +
            0.25 * dwell_score +
            0.25 * helpful_rate +
            0.10 * position_score
        )

    @property
    def recommended_weight(self) -> float:
        """
        Calculate recommended engine weight based on performance.

        Returns weight multiplier (0.5 to 2.0).
        """
        score = self.engagement_score

        # Map score to weight: 0.0 -> 0.5, 0.5 -> 1.0, 1.0 -> 2.0
        if score < 0.5:
            return 0.5 + score
        else:
            return 1.0 + (score - 0.5) * 2

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine": self.engine,
            "query_type": self.query_type,
            "total_impressions": self.total_impressions,
            "clicks": self.clicks,
            "ctr": f"{self.ctr:.1%}",
            "engagement_score": f"{self.engagement_score:.3f}",
            "recommended_weight": f"{self.recommended_weight:.2f}",
            "last_updated": datetime.fromtimestamp(self.last_updated).isoformat(),
        }


@dataclass
class FeedbackConfig:
    """Configuration for feedback loop."""
    redis_url: str = "redis://localhost:6379/2"  # Separate DB from cache
    retention_days: int = 30  # How long to keep feedback data
    min_samples: int = 10  # Minimum samples before adjusting weights
    learning_rate: float = 0.1  # How fast to adjust weights


class FeedbackLoop:
    """
    Learns optimal engine configurations from user feedback.

    Tracks:
    - Click-through rates by engine and query type
    - Dwell time (engagement depth)
    - Explicit user ratings
    - Query reformulation patterns
    """

    def __init__(self, config: Optional[FeedbackConfig] = None):
        self.config = config or FeedbackConfig()
        self._redis: Optional[redis.Redis] = None
        self._initialized = False

        # In-memory cache of performance data
        self._performance: Dict[Tuple[str, str], EnginePerformance] = {}

        # Current weight adjustments
        self._weight_adjustments: Dict[Tuple[str, str], float] = {}

    async def initialize(self) -> bool:
        """Initialize feedback storage."""
        if self._initialized:
            return True

        if REDIS_AVAILABLE:
            try:
                self._redis = redis.from_url(
                    self.config.redis_url,
                    encoding="utf-8",
                    decode_responses=True
                )
                await self._redis.ping()
                logger.info("Feedback loop storage (Redis) connected")

                # Load existing performance data
                await self._load_performance()
                self._initialized = True
                return True
            except Exception as e:
                logger.error(f"Feedback storage failed: {e}")
                self._redis = None

        # Fall back to in-memory only
        self._initialized = True
        return True

    async def _load_performance(self):
        """Load performance data from Redis."""
        if not self._redis:
            return

        try:
            keys = await self._redis.keys("perf:*")
            for key in keys:
                data = await self._redis.hgetall(key)
                if data:
                    engine = data.get("engine", "unknown")
                    query_type = data.get("query_type", "general")
                    perf = EnginePerformance(
                        engine=engine,
                        query_type=query_type,
                        total_impressions=int(data.get("impressions", 0)),
                        clicks=int(data.get("clicks", 0)),
                        dwells=int(data.get("dwells", 0)),
                        helpful_ratings=int(data.get("helpful", 0)),
                        not_helpful_ratings=int(data.get("not_helpful", 0)),
                        total_dwell_time_ms=int(data.get("dwell_time", 0)),
                        avg_click_position=float(data.get("avg_position", 0)),
                        last_updated=float(data.get("updated", time.time()))
                    )
                    self._performance[(engine, query_type)] = perf

            logger.info(f"Loaded {len(self._performance)} performance records")
        except Exception as e:
            logger.error(f"Failed to load performance data: {e}")

    async def record_impression(
        self,
        query: str,
        query_type: str,
        results: List[Dict[str, Any]]
    ):
        """
        Record that results were shown to user.

        Args:
            query: The search query
            query_type: Classification from QueryRouter
            results: List of search results shown
        """
        if not self._initialized:
            await self.initialize()

        for position, result in enumerate(results, start=1):
            engine = result.get("engine", "unknown")
            key = (engine, query_type)

            if key not in self._performance:
                self._performance[key] = EnginePerformance(
                    engine=engine,
                    query_type=query_type
                )

            self._performance[key].total_impressions += 1

    async def record_feedback(self, feedback: SearchFeedback):
        """
        Record user feedback signal.

        Args:
            feedback: SearchFeedback object with signal details
        """
        if not self._initialized:
            await self.initialize()

        key = (feedback.engine, feedback.query_type)

        if key not in self._performance:
            self._performance[key] = EnginePerformance(
                engine=feedback.engine,
                query_type=feedback.query_type
            )

        perf = self._performance[key]
        perf.last_updated = time.time()

        # Update metrics based on signal
        if feedback.signal == FeedbackSignal.CLICK:
            perf.clicks += 1
            # Update rolling average position
            perf.avg_click_position = (
                (perf.avg_click_position * (perf.clicks - 1) + feedback.position)
                / perf.clicks
            )
        elif feedback.signal == FeedbackSignal.DWELL:
            perf.dwells += 1
            if feedback.dwell_time_ms:
                perf.total_dwell_time_ms += feedback.dwell_time_ms
        elif feedback.signal == FeedbackSignal.HELPFUL:
            perf.helpful_ratings += 1
        elif feedback.signal == FeedbackSignal.NOT_HELPFUL:
            perf.not_helpful_ratings += 1

        # Persist to Redis
        if self._redis:
            try:
                await self._redis.hset(
                    f"perf:{feedback.engine}:{feedback.query_type}",
                    mapping={
                        "engine": feedback.engine,
                        "query_type": feedback.query_type,
                        "impressions": perf.total_impressions,
                        "clicks": perf.clicks,
                        "dwells": perf.dwells,
                        "helpful": perf.helpful_ratings,
                        "not_helpful": perf.not_helpful_ratings,
                        "dwell_time": perf.total_dwell_time_ms,
                        "avg_position": perf.avg_click_position,
                        "updated": perf.last_updated,
                    }
                )

                # Also store raw feedback for analysis
                await self._redis.lpush(
                    f"feedback:{feedback.query_type}",
                    json.dumps(feedback.to_dict())
                )
                # Trim to last 1000 entries per query type
                await self._redis.ltrim(f"feedback:{feedback.query_type}", 0, 999)
            except Exception as e:
                logger.error(f"Failed to persist feedback: {e}")

    def get_weight_adjustment(
        self,
        engine: str,
        query_type: str
    ) -> float:
        """
        Get recommended weight adjustment for an engine/query type combo.

        Returns multiplier (0.5 to 2.0).
        """
        key = (engine, query_type)
        perf = self._performance.get(key)

        if not perf or perf.total_impressions < self.config.min_samples:
            return 1.0  # No adjustment until enough data

        return perf.recommended_weight

    def get_ranked_engines(
        self,
        query_type: str,
        available_engines: List[str]
    ) -> List[Tuple[str, float]]:
        """
        Get engines ranked by learned performance for a query type.

        Returns list of (engine, weight) tuples sorted by weight descending.
        """
        rankings = []

        for engine in available_engines:
            weight = self.get_weight_adjustment(engine, query_type)
            rankings.append((engine, weight))

        rankings.sort(key=lambda x: x[1], reverse=True)
        return rankings

    def get_performance_summary(
        self,
        query_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get performance summary for all or specific query type."""
        results = []

        for (engine, qtype), perf in self._performance.items():
            if query_type is None or qtype == query_type:
                results.append(perf.to_dict())

        # Sort by engagement score
        results.sort(key=lambda x: float(x["engagement_score"]), reverse=True)
        return results

    async def close(self):
        """Close storage connections."""
        if self._redis:
            await self._redis.close()


# Singleton instance
_feedback: Optional[FeedbackLoop] = None


def get_feedback_loop(config: Optional[FeedbackConfig] = None) -> FeedbackLoop:
    """Get or create the feedback loop singleton."""
    global _feedback
    if _feedback is None:
        _feedback = FeedbackLoop(config)
    return _feedback


async def example_usage():
    """Demonstrate feedback loop usage."""
    loop = get_feedback_loop()
    await loop.initialize()

    # Simulate search results shown
    results = [
        {"url": "https://fanuc.com", "engine": "brave"},
        {"url": "https://docs.fanuc.com", "engine": "bing"},
        {"url": "https://reddit.com/r/fanuc", "engine": "reddit"},
    ]

    await loop.record_impression(
        query="FANUC SRVO-063",
        query_type="industrial",
        results=results
    )

    # Simulate user clicking result
    await loop.record_feedback(SearchFeedback(
        query="FANUC SRVO-063",
        query_type="industrial",
        engine="brave",
        url="https://fanuc.com",
        position=1,
        signal=FeedbackSignal.CLICK,
    ))

    # Simulate dwell time
    await loop.record_feedback(SearchFeedback(
        query="FANUC SRVO-063",
        query_type="industrial",
        engine="brave",
        url="https://fanuc.com",
        position=1,
        signal=FeedbackSignal.DWELL,
        dwell_time_ms=45000,  # 45 seconds
    ))

    # Get recommendations
    print("Performance Summary:")
    for perf in loop.get_performance_summary("industrial"):
        print(f"  {perf}")

    print("\nRanked Engines for 'industrial':")
    rankings = loop.get_ranked_engines("industrial", ["brave", "bing", "reddit"])
    for engine, weight in rankings:
        print(f"  {engine}: {weight:.2f}x")

    await loop.close()


if __name__ == "__main__":
    asyncio.run(example_usage())
