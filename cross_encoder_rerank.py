#!/usr/bin/env python3
"""
Cross-Encoder Reranking for Search Results

Uses neural cross-encoders to rerank search results for higher relevance.
Cross-encoders provide more accurate relevance scores than bi-encoders
by considering query-document interaction directly.

Features:
- GPU-accelerated inference when available
- Multiple model options (speed vs quality tradeoff)
- Batch processing for efficiency
- Hybrid scoring (cross-encoder + original rank)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import CrossEncoder
    import torch
    CROSS_ENCODER_AVAILABLE = True

    # Check for GPU
    GPU_AVAILABLE = torch.cuda.is_available()
    DEVICE = "cuda" if GPU_AVAILABLE else "cpu"
except ImportError:
    CROSS_ENCODER_AVAILABLE = False
    GPU_AVAILABLE = False
    DEVICE = "cpu"
    CrossEncoder = None
    logger.warning("sentence-transformers not available - cross-encoder reranking disabled")


# Available cross-encoder models (speed vs quality)
AVAILABLE_MODELS = {
    # Fast models (< 100ms for 20 results)
    "fast": "cross-encoder/ms-marco-MiniLM-L-2-v2",      # 5M params, very fast
    "balanced": "cross-encoder/ms-marco-MiniLM-L-6-v2",  # 22M params, good balance

    # Quality models (100-500ms for 20 results)
    "quality": "cross-encoder/ms-marco-MiniLM-L-12-v2",  # 33M params, high quality
    "best": "cross-encoder/ms-marco-TinyBERT-L-2-v2",    # Alternative fast model

    # Domain-specific
    "scientific": "cross-encoder/stsb-distilroberta-base",  # For academic content
}


@dataclass
class RerankerConfig:
    """Configuration for cross-encoder reranking."""
    model_name: str = "balanced"  # Key from AVAILABLE_MODELS or full HF model name
    batch_size: int = 16          # Batch size for inference
    max_length: int = 512         # Max input length (query + doc)
    top_k: int = 20               # Number of results to rerank
    score_weight: float = 0.7     # Weight for cross-encoder score vs original
    device: str = DEVICE          # "cuda" or "cpu"
    cache_model: bool = True      # Keep model in memory


@dataclass
class RerankStats:
    """Statistics for reranking operations."""
    total_reranks: int = 0
    total_results_processed: int = 0
    avg_latency_ms: float = 0.0
    model_load_time_ms: float = 0.0
    gpu_used: bool = GPU_AVAILABLE

    def record_rerank(self, num_results: int, latency_ms: float):
        self.total_reranks += 1
        self.total_results_processed += num_results
        n = self.total_reranks
        self.avg_latency_ms = (self.avg_latency_ms * (n - 1) + latency_ms) / n


@dataclass
class RerankResult:
    """A reranked search result."""
    original_result: Dict[str, Any]
    cross_encoder_score: float
    original_rank: int
    final_score: float

    def to_dict(self) -> Dict[str, Any]:
        result = self.original_result.copy()
        result["rerank_scores"] = {
            "cross_encoder": self.cross_encoder_score,
            "original_rank": self.original_rank,
            "final": self.final_score
        }
        return result


class CrossEncoderReranker:
    """
    Neural cross-encoder for reranking search results.

    Uses MS MARCO trained models to score query-document relevance,
    providing more accurate ranking than lexical or bi-encoder methods.
    """

    def __init__(self, config: Optional[RerankerConfig] = None):
        self.config = config or RerankerConfig()
        self._model: Optional[CrossEncoder] = None
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._stats = RerankStats()
        self._lock = asyncio.Lock()

        if not CROSS_ENCODER_AVAILABLE:
            logger.warning("CrossEncoderReranker initialized without sentence-transformers")

    def _get_model_path(self) -> str:
        """Resolve model name to HuggingFace model path."""
        if self.config.model_name in AVAILABLE_MODELS:
            return AVAILABLE_MODELS[self.config.model_name]
        return self.config.model_name

    def _load_model(self) -> Optional[CrossEncoder]:
        """Load the cross-encoder model (blocking)."""
        if not CROSS_ENCODER_AVAILABLE:
            return None

        start = time.time()
        model_path = self._get_model_path()

        try:
            model = CrossEncoder(
                model_path,
                max_length=self.config.max_length,
                device=self.config.device
            )
            self._stats.model_load_time_ms = (time.time() - start) * 1000
            logger.info(
                f"Loaded cross-encoder {model_path} on {self.config.device} "
                f"in {self._stats.model_load_time_ms:.0f}ms"
            )
            return model
        except Exception as e:
            logger.error(f"Failed to load cross-encoder: {e}")
            return None

    async def _get_model(self) -> Optional[CrossEncoder]:
        """Get or load the cross-encoder model."""
        async with self._lock:
            if self._model is None:
                loop = asyncio.get_event_loop()
                self._model = await loop.run_in_executor(
                    self._executor,
                    self._load_model
                )
            return self._model

    def _compute_scores(
        self,
        model: CrossEncoder,
        query: str,
        documents: List[str]
    ) -> List[float]:
        """Compute cross-encoder scores for query-document pairs (blocking)."""
        pairs = [(query, doc) for doc in documents]
        scores = model.predict(
            pairs,
            batch_size=self.config.batch_size,
            show_progress_bar=False
        )
        return scores.tolist()

    async def rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        content_key: str = "content",
        top_k: Optional[int] = None
    ) -> List[RerankResult]:
        """
        Rerank search results using cross-encoder scoring.

        Args:
            query: The search query
            results: List of search result dicts
            content_key: Key to extract document content from results
            top_k: Number of top results to return (default: config.top_k)

        Returns:
            List of RerankResult objects sorted by final score
        """
        if not CROSS_ENCODER_AVAILABLE:
            logger.warning("Cross-encoder not available, returning original order")
            return [
                RerankResult(
                    original_result=r,
                    cross_encoder_score=0.0,
                    original_rank=i,
                    final_score=1.0 - (i * 0.01)
                )
                for i, r in enumerate(results)
            ]

        start_time = time.time()
        top_k = top_k or self.config.top_k

        # Limit to top_k for efficiency
        results_to_rerank = results[:top_k]

        # Extract document content
        documents = []
        for r in results_to_rerank:
            # Try different keys for content
            content = r.get(content_key, "")
            if not content:
                content = r.get("content", r.get("title", r.get("snippet", "")))
            # Combine title + content for better matching
            title = r.get("title", "")
            if title and title not in content:
                content = f"{title}. {content}"
            documents.append(content)

        # Get model and compute scores
        model = await self._get_model()
        if model is None:
            logger.warning("Model not available, returning original order")
            return [
                RerankResult(
                    original_result=r,
                    cross_encoder_score=0.0,
                    original_rank=i,
                    final_score=1.0 - (i * 0.01)
                )
                for i, r in enumerate(results_to_rerank)
            ]

        # Compute scores in thread pool
        loop = asyncio.get_event_loop()
        scores = await loop.run_in_executor(
            self._executor,
            self._compute_scores,
            model,
            query,
            documents
        )

        # Normalize scores to 0-1 range using sigmoid-like scaling
        min_score = min(scores) if scores else 0
        max_score = max(scores) if scores else 1
        score_range = max_score - min_score if max_score != min_score else 1

        normalized_scores = [
            (s - min_score) / score_range
            for s in scores
        ]

        # Create reranked results with hybrid scoring
        reranked = []
        for i, (result, ce_score, norm_score) in enumerate(
            zip(results_to_rerank, scores, normalized_scores)
        ):
            # Original rank bonus (1.0 for first, decreasing)
            rank_score = 1.0 - (i * 0.05)  # 0.05 penalty per position

            # Hybrid score: weighted combination
            final_score = (
                self.config.score_weight * norm_score +
                (1 - self.config.score_weight) * rank_score
            )

            reranked.append(RerankResult(
                original_result=result,
                cross_encoder_score=ce_score,
                original_rank=i,
                final_score=final_score
            ))

        # Sort by final score (descending)
        reranked.sort(key=lambda x: x.final_score, reverse=True)

        # Update stats
        latency = (time.time() - start_time) * 1000
        self._stats.record_rerank(len(results_to_rerank), latency)

        logger.debug(
            f"Reranked {len(results_to_rerank)} results in {latency:.0f}ms "
            f"(model: {self.config.model_name})"
        )

        return reranked

    async def rerank_to_dicts(
        self,
        query: str,
        results: List[Dict[str, Any]],
        content_key: str = "content",
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Rerank and return as list of dicts (convenient wrapper).

        Returns:
            List of result dicts with rerank_scores added
        """
        reranked = await self.rerank(query, results, content_key, top_k)
        return [r.to_dict() for r in reranked]

    def get_stats(self) -> Dict[str, Any]:
        """Get reranking statistics."""
        return {
            "total_reranks": self._stats.total_reranks,
            "total_results_processed": self._stats.total_results_processed,
            "avg_latency_ms": round(self._stats.avg_latency_ms, 2),
            "model_load_time_ms": round(self._stats.model_load_time_ms, 2),
            "gpu_used": self._stats.gpu_used,
            "model": self._get_model_path(),
            "device": self.config.device
        }

    def clear_model(self):
        """Clear the cached model to free memory."""
        self._model = None
        if CROSS_ENCODER_AVAILABLE:
            import torch
            torch.cuda.empty_cache()
        logger.info("Cross-encoder model cleared from memory")


# Singleton instance
_reranker: Optional[CrossEncoderReranker] = None


def get_reranker(config: Optional[RerankerConfig] = None) -> CrossEncoderReranker:
    """Get or create the cross-encoder reranker singleton."""
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoderReranker(config)
    return _reranker


def is_reranker_available() -> bool:
    """Check if cross-encoder reranking is available."""
    return CROSS_ENCODER_AVAILABLE


async def example_usage():
    """Demonstrate cross-encoder reranking."""
    if not CROSS_ENCODER_AVAILABLE:
        print("sentence-transformers not available - install with:")
        print("  pip install sentence-transformers")
        return

    print("=== Cross-Encoder Reranking Demo ===\n")

    # Sample search results
    query = "How to fix FANUC servo alarm SRVO-063"
    results = [
        {"title": "FANUC Error Code List", "content": "Complete list of FANUC robot error codes and their meanings."},
        {"title": "SRVO-063 Robot Servo Alarm", "content": "SRVO-063 indicates a general servo communication error. Check encoder cables and amplifier connections."},
        {"title": "Industrial Robot Maintenance", "content": "General maintenance procedures for industrial robots including lubrication and inspection."},
        {"title": "Troubleshooting FANUC Alarms", "content": "Step-by-step guide to diagnose and resolve common FANUC robot alarms including servo errors."},
        {"title": "PLC Programming Guide", "content": "How to program PLCs for industrial automation applications."},
    ]

    reranker = get_reranker(RerankerConfig(
        model_name="fast",  # Use fast model for demo
        device="cpu"
    ))

    print(f"Query: {query}\n")
    print("Original order:")
    for i, r in enumerate(results, 1):
        print(f"  {i}. {r['title']}")

    print("\nReranking...")
    reranked = await reranker.rerank(query, results)

    print("\nReranked order:")
    for i, rr in enumerate(reranked, 1):
        print(
            f"  {i}. {rr.original_result['title']} "
            f"(score: {rr.cross_encoder_score:.3f}, was #{rr.original_rank + 1})"
        )

    print(f"\nStats: {reranker.get_stats()}")

    reranker.clear_model()


if __name__ == "__main__":
    asyncio.run(example_usage())
