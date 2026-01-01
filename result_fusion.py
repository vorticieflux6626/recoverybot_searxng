#!/usr/bin/env python3
"""
Result Fusion Algorithms for SearXNG

Implements advanced result merging strategies:
- Reciprocal Rank Fusion (RRF): Best for combining ranked lists
- Weighted Score Fusion: Uses engine confidence/weights
- Borda Count: Democratic voting across engines

Reference:
- Cormack et al. "Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods"
- OpenSearch RRF: https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class FusedResult:
    """A search result with fusion metadata."""
    url: str
    title: str
    content: str
    engines: List[str]

    # Fusion scores
    rrf_score: float = 0.0
    weighted_score: float = 0.0
    borda_score: float = 0.0
    final_score: float = 0.0

    # Original data
    original_scores: Dict[str, float] = field(default_factory=dict)
    original_ranks: Dict[str, int] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def engine_count(self) -> int:
        """Number of engines that returned this result."""
        return len(self.engines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "engines": self.engines,
            "engine_count": self.engine_count,
            "rrf_score": round(self.rrf_score, 4),
            "weighted_score": round(self.weighted_score, 4),
            "final_score": round(self.final_score, 4),
            "metadata": self.metadata
        }


class ResultFusion:
    """
    Fuses search results from multiple engines using various algorithms.

    The primary algorithm is RRF (Reciprocal Rank Fusion), which has been
    shown to outperform individual ranking methods and Condorcet voting.
    """

    # RRF constant (k=60 is standard, provides good balance)
    RRF_K = 60

    # Engine weights (higher = more trusted)
    DEFAULT_WEIGHTS = {
        "brave": 1.5,
        "bing": 1.2,
        "mojeek": 1.1,
        "reddit": 1.2,
        "wikipedia": 1.0,
        "arxiv": 1.3,
        "semantic_scholar": 1.2,
        "openalex": 1.2,
        "stackoverflow": 1.1,
        "github": 1.0,
        "pubmed": 1.2,
        "crossref": 1.0,
    }

    def __init__(
        self,
        rrf_k: int = 60,
        engine_weights: Optional[Dict[str, float]] = None,
        url_normalizer: Optional[Callable[[str], str]] = None
    ):
        """
        Initialize the result fusion engine.

        Args:
            rrf_k: RRF constant (default 60, higher = less aggressive ranking)
            engine_weights: Custom engine weight overrides
            url_normalizer: Function to normalize URLs for deduplication
        """
        self.rrf_k = rrf_k
        self.engine_weights = {**self.DEFAULT_WEIGHTS, **(engine_weights or {})}
        self.url_normalizer = url_normalizer or self._default_url_normalizer

    @staticmethod
    def _default_url_normalizer(url: str) -> str:
        """Normalize URL for deduplication."""
        # Remove trailing slashes, www prefix, and protocol
        url = url.lower().rstrip("/")
        for prefix in ["https://www.", "http://www.", "https://", "http://"]:
            if url.startswith(prefix):
                url = url[len(prefix):]
                break
        return url

    def fuse(
        self,
        results_by_engine: Dict[str, List[Dict[str, Any]]],
        method: str = "rrf",
        top_k: Optional[int] = None
    ) -> List[FusedResult]:
        """
        Fuse results from multiple engines.

        Args:
            results_by_engine: Dict mapping engine name to list of results
            method: Fusion method ("rrf", "weighted", "borda", "hybrid")
            top_k: Return only top K results (None = all)

        Returns:
            List of FusedResult objects sorted by score
        """
        # Group results by normalized URL
        url_groups: Dict[str, FusedResult] = {}

        for engine, results in results_by_engine.items():
            for rank, result in enumerate(results, start=1):
                url = result.get("url", "")
                if not url:
                    continue

                norm_url = self.url_normalizer(url)

                if norm_url not in url_groups:
                    url_groups[norm_url] = FusedResult(
                        url=url,
                        title=result.get("title", ""),
                        content=result.get("content", ""),
                        engines=[],
                        metadata={}
                    )

                fused = url_groups[norm_url]
                fused.engines.append(engine)
                fused.original_ranks[engine] = rank
                fused.original_scores[engine] = result.get("score", 0.0)

                # Keep best title/content
                if len(result.get("title", "")) > len(fused.title):
                    fused.title = result["title"]
                if len(result.get("content", "")) > len(fused.content):
                    fused.content = result["content"]

        # Apply fusion algorithms
        fused_results = list(url_groups.values())

        for fused in fused_results:
            fused.rrf_score = self._calculate_rrf(fused)
            fused.weighted_score = self._calculate_weighted(fused)
            fused.borda_score = self._calculate_borda(fused, len(results_by_engine))

        # Calculate final score based on method
        if method == "rrf":
            for f in fused_results:
                f.final_score = f.rrf_score
        elif method == "weighted":
            for f in fused_results:
                f.final_score = f.weighted_score
        elif method == "borda":
            for f in fused_results:
                f.final_score = f.borda_score
        elif method == "hybrid":
            # Combine RRF and weighted scores
            for f in fused_results:
                f.final_score = 0.6 * f.rrf_score + 0.4 * f.weighted_score
        else:
            raise ValueError(f"Unknown fusion method: {method}")

        # Sort by final score
        fused_results.sort(key=lambda x: x.final_score, reverse=True)

        if top_k:
            fused_results = fused_results[:top_k]

        logger.debug(
            f"Fused {sum(len(r) for r in results_by_engine.values())} results "
            f"from {len(results_by_engine)} engines into {len(fused_results)} unique results"
        )

        return fused_results

    def _calculate_rrf(self, result: FusedResult) -> float:
        """
        Calculate Reciprocal Rank Fusion score.

        RRF(d) = Σ 1/(k + rank(d))

        This formula gives more weight to higher-ranked results while
        preventing any single engine from dominating the final ranking.
        """
        score = 0.0
        for engine, rank in result.original_ranks.items():
            weight = self.engine_weights.get(engine, 1.0)
            score += weight / (self.rrf_k + rank)
        return score

    def _calculate_weighted(self, result: FusedResult) -> float:
        """
        Calculate weighted score based on engine weights and original scores.
        """
        if not result.original_scores:
            return 0.0

        total_weight = 0.0
        weighted_sum = 0.0

        for engine, score in result.original_scores.items():
            weight = self.engine_weights.get(engine, 1.0)
            weighted_sum += weight * score
            total_weight += weight

        # Add bonus for appearing in multiple engines
        engine_bonus = 0.1 * (len(result.engines) - 1)

        return (weighted_sum / total_weight if total_weight > 0 else 0.0) + engine_bonus

    def _calculate_borda(self, result: FusedResult, num_engines: int) -> float:
        """
        Calculate Borda count score.

        Each engine "votes" for results, with higher ranks getting more points.
        Points = (max_rank - rank + 1) for each engine
        """
        max_rank = 100  # Assume max 100 results per engine
        score = 0.0

        for engine, rank in result.original_ranks.items():
            weight = self.engine_weights.get(engine, 1.0)
            score += weight * (max_rank - rank + 1)

        # Normalize by number of engines
        return score / (num_engines * max_rank) if num_engines > 0 else 0.0

    def fuse_from_searxng(
        self,
        results: List[Dict[str, Any]],
        method: str = "rrf",
        top_k: Optional[int] = None
    ) -> List[FusedResult]:
        """
        Convenience method to fuse SearXNG results directly.

        SearXNG returns results with 'engine' field, this groups them
        and applies fusion.

        Args:
            results: List of SearXNG result dicts
            method: Fusion method
            top_k: Return only top K results

        Returns:
            List of FusedResult objects
        """
        # Group by engine
        by_engine: Dict[str, List[Dict]] = defaultdict(list)
        for result in results:
            engine = result.get("engine", "unknown")
            by_engine[engine].append(result)

        return self.fuse(dict(by_engine), method=method, top_k=top_k)


# Singleton instance
_fusion: Optional[ResultFusion] = None


def get_fusion_engine(
    rrf_k: int = 60,
    engine_weights: Optional[Dict[str, float]] = None
) -> ResultFusion:
    """Get or create the fusion engine singleton."""
    global _fusion
    if _fusion is None:
        _fusion = ResultFusion(rrf_k=rrf_k, engine_weights=engine_weights)
    return _fusion


# Example usage
def example_usage():
    """Demonstrate result fusion."""
    # Simulated results from different engines
    brave_results = [
        {"url": "https://python.org", "title": "Python.org", "content": "Official Python site", "score": 0.95},
        {"url": "https://docs.python.org", "title": "Python Docs", "content": "Documentation", "score": 0.90},
        {"url": "https://realpython.com", "title": "Real Python", "content": "Tutorials", "score": 0.85},
    ]

    bing_results = [
        {"url": "https://python.org", "title": "Welcome to Python.org", "content": "The official home", "score": 0.92},
        {"url": "https://www.w3schools.com/python", "title": "Python Tutorial", "content": "Learn Python", "score": 0.88},
        {"url": "https://docs.python.org", "title": "Python 3 Documentation", "content": "Docs", "score": 0.84},
    ]

    mojeek_results = [
        {"url": "https://realpython.com", "title": "Real Python Tutorials", "content": "Learn Python programming", "score": 0.80},
        {"url": "https://python.org", "title": "Python", "content": "Programming language", "score": 0.78},
    ]

    fusion = get_fusion_engine()

    # Fuse results using RRF
    fused = fusion.fuse(
        {
            "brave": brave_results,
            "bing": bing_results,
            "mojeek": mojeek_results
        },
        method="rrf",
        top_k=5
    )

    print("RRF Fusion Results:")
    print("-" * 60)
    for i, result in enumerate(fused, 1):
        print(f"{i}. {result.title}")
        print(f"   URL: {result.url}")
        print(f"   Engines: {', '.join(result.engines)} ({result.engine_count})")
        print(f"   RRF Score: {result.rrf_score:.4f}")
        print(f"   Ranks: {result.original_ranks}")
        print()


if __name__ == "__main__":
    example_usage()
