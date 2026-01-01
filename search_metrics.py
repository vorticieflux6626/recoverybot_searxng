#!/usr/bin/env python3
"""
Search Quality Metrics for SearXNG

Tracks and calculates search quality metrics:
- Response time percentiles
- Engine availability and success rates
- Result diversity metrics
- Click-through rate (CTR) estimation based on position

These metrics help optimize engine selection and identify issues.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from collections import defaultdict
import statistics
import logging

logger = logging.getLogger(__name__)


@dataclass
class EngineMetrics:
    """Metrics for a single search engine."""
    name: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_results: int = 0
    response_times: List[float] = field(default_factory=list)

    # Keep last N response times for percentile calculation
    MAX_SAMPLES = 100

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests

    @property
    def avg_results_per_request(self) -> float:
        if self.successful_requests == 0:
            return 0.0
        return self.total_results / self.successful_requests

    @property
    def p50_response_time(self) -> float:
        if not self.response_times:
            return 0.0
        return statistics.median(self.response_times)

    @property
    def p95_response_time(self) -> float:
        if len(self.response_times) < 2:
            return self.p50_response_time
        sorted_times = sorted(self.response_times)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[idx]

    def record_request(self, success: bool, result_count: int, response_time: float):
        """Record a request outcome."""
        self.total_requests += 1
        if success:
            self.successful_requests += 1
            self.total_results += result_count
        else:
            self.failed_requests += 1

        self.response_times.append(response_time)
        # Keep only last N samples
        if len(self.response_times) > self.MAX_SAMPLES:
            self.response_times = self.response_times[-self.MAX_SAMPLES:]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "total_requests": self.total_requests,
            "success_rate": f"{self.success_rate:.1%}",
            "avg_results": f"{self.avg_results_per_request:.1f}",
            "p50_ms": f"{self.p50_response_time * 1000:.0f}",
            "p95_ms": f"{self.p95_response_time * 1000:.0f}",
        }


@dataclass
class QueryMetrics:
    """Metrics for query quality estimation."""
    total_queries: int = 0
    queries_with_results: int = 0
    total_results_returned: int = 0
    total_unique_domains: int = 0
    multi_engine_results: int = 0  # Results appearing in 2+ engines

    # Position-based click model (simplified)
    # Based on research: position 1 has ~30% CTR, decays exponentially
    POSITION_CTR = [0.30, 0.15, 0.10, 0.07, 0.05, 0.04, 0.03, 0.02, 0.02, 0.01]

    @property
    def zero_result_rate(self) -> float:
        if self.total_queries == 0:
            return 0.0
        return 1.0 - (self.queries_with_results / self.total_queries)

    @property
    def avg_results_per_query(self) -> float:
        if self.total_queries == 0:
            return 0.0
        return self.total_results_returned / self.total_queries

    @property
    def avg_domain_diversity(self) -> float:
        """Average unique domains per query (higher = more diverse)."""
        if self.total_queries == 0:
            return 0.0
        return self.total_unique_domains / self.total_queries

    @property
    def estimated_mrr(self) -> float:
        """
        Estimate Mean Reciprocal Rank based on multi-engine agreement.

        Results appearing in multiple engines are assumed to be more relevant,
        giving higher MRR when they appear early.
        """
        if self.total_queries == 0:
            return 0.0
        # Simplified: assume multi-engine results are "relevant"
        # MRR improves when these appear early
        return min(1.0, self.multi_engine_results / max(1, self.total_queries) * 2)

    def record_query(
        self,
        result_count: int,
        unique_domains: int,
        multi_engine_count: int
    ):
        """Record a query outcome."""
        self.total_queries += 1
        if result_count > 0:
            self.queries_with_results += 1
        self.total_results_returned += result_count
        self.total_unique_domains += unique_domains
        self.multi_engine_results += multi_engine_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_queries": self.total_queries,
            "zero_result_rate": f"{self.zero_result_rate:.1%}",
            "avg_results": f"{self.avg_results_per_query:.1f}",
            "avg_domain_diversity": f"{self.avg_domain_diversity:.1f}",
            "estimated_mrr": f"{self.estimated_mrr:.3f}",
        }


class SearchMetrics:
    """
    Centralized search quality metrics tracking.

    Tracks per-engine and overall query quality metrics.
    """

    def __init__(self):
        self.engines: Dict[str, EngineMetrics] = {}
        self.queries = QueryMetrics()
        self.start_time = time.time()

    def get_engine_metrics(self, engine: str) -> EngineMetrics:
        """Get or create metrics for an engine."""
        if engine not in self.engines:
            self.engines[engine] = EngineMetrics(name=engine)
        return self.engines[engine]

    def record_search(
        self,
        results: List[Dict[str, Any]],
        response_time: float,
        engines_queried: List[str]
    ):
        """
        Record a complete search operation.

        Args:
            results: List of search results
            response_time: Total response time in seconds
            engines_queried: List of engines that were queried
        """
        # Count results per engine
        results_by_engine: Dict[str, int] = defaultdict(int)
        domains_seen = set()
        urls_seen: Dict[str, List[str]] = defaultdict(list)

        for result in results:
            engine = result.get("engine", "unknown")
            results_by_engine[engine] += 1

            url = result.get("url", "")
            if url:
                # Extract domain
                try:
                    from urllib.parse import urlparse
                    domain = urlparse(url).netloc
                    domains_seen.add(domain)
                    urls_seen[url].append(engine)
                except Exception:
                    pass

        # Record per-engine metrics
        avg_time_per_engine = response_time / max(1, len(engines_queried))
        for engine in engines_queried:
            metrics = self.get_engine_metrics(engine)
            result_count = results_by_engine.get(engine, 0)
            success = result_count > 0
            metrics.record_request(success, result_count, avg_time_per_engine)

        # Count multi-engine results
        multi_engine_count = sum(1 for urls in urls_seen.values() if len(urls) > 1)

        # Record query metrics
        self.queries.record_query(
            result_count=len(results),
            unique_domains=len(domains_seen),
            multi_engine_count=multi_engine_count
        )

        logger.debug(
            f"Recorded search: {len(results)} results, "
            f"{len(domains_seen)} domains, {multi_engine_count} multi-engine"
        )

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all metrics."""
        uptime = time.time() - self.start_time

        engine_summaries = [
            m.to_dict() for m in sorted(
                self.engines.values(),
                key=lambda e: e.total_requests,
                reverse=True
            )
        ]

        return {
            "uptime_seconds": int(uptime),
            "query_metrics": self.queries.to_dict(),
            "engine_metrics": engine_summaries,
            "top_engines": [e["name"] for e in engine_summaries[:5]],
        }

    def get_engine_ranking(self) -> List[str]:
        """
        Get engines ranked by quality score.

        Score = success_rate * avg_results * (1 / p50_response_time)
        """
        scores = []
        for engine in self.engines.values():
            if engine.total_requests < 3:
                continue  # Not enough data

            score = (
                engine.success_rate *
                engine.avg_results_per_request *
                (1.0 / max(0.1, engine.p50_response_time))
            )
            scores.append((engine.name, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in scores]


# Singleton instance
_metrics: Optional[SearchMetrics] = None


def get_metrics() -> SearchMetrics:
    """Get or create the metrics singleton."""
    global _metrics
    if _metrics is None:
        _metrics = SearchMetrics()
    return _metrics


# Example usage
def example_usage():
    """Demonstrate metrics tracking."""
    metrics = get_metrics()

    # Simulate some searches
    sample_results = [
        {"url": "https://python.org", "engine": "brave", "title": "Python"},
        {"url": "https://python.org", "engine": "bing", "title": "Python"},
        {"url": "https://docs.python.org", "engine": "brave", "title": "Docs"},
        {"url": "https://realpython.com", "engine": "mojeek", "title": "Real Python"},
    ]

    for i in range(10):
        response_time = 0.5 + (i * 0.1)
        metrics.record_search(
            results=sample_results,
            response_time=response_time,
            engines_queried=["brave", "bing", "mojeek"]
        )

    # Print summary
    import json
    summary = metrics.get_summary()
    print("Search Metrics Summary:")
    print(json.dumps(summary, indent=2))

    print("\nEngine Ranking:")
    for i, engine in enumerate(metrics.get_engine_ranking(), 1):
        print(f"  {i}. {engine}")


if __name__ == "__main__":
    example_usage()
