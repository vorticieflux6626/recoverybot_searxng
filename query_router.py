#!/usr/bin/env python3
"""
Query Router for Intelligent Engine Selection

Routes queries to the most appropriate search engines based on:
- Pattern matching (regex-based classification)
- Keyword detection
- Query structure analysis

This is a lightweight, fast router that doesn't require LLM inference.
For LLM-based routing, see memOS/server/agentic/query_classifier.py
"""

import re
from dataclasses import dataclass
from typing import List, Dict, Set, Tuple, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class QueryType(Enum):
    """Classification of query types."""
    ACADEMIC = "academic"
    TECHNICAL = "technical"
    CODE = "code"
    TROUBLESHOOTING = "troubleshooting"
    INDUSTRIAL = "industrial"
    MEDICAL = "medical"
    NEWS = "news"
    GENERAL = "general"


@dataclass
class RoutingDecision:
    """Result of query routing."""
    query_type: QueryType
    engines: List[str]
    confidence: float
    matched_patterns: List[str]
    reasoning: str


class QueryRouter:
    """
    Routes queries to optimal engine groups based on pattern matching.

    This is a fast, rule-based router suitable for high-throughput scenarios.
    Patterns are designed to catch common query types without LLM overhead.
    """

    # Engine groups by query type
    ENGINE_GROUPS = {
        QueryType.ACADEMIC: [
            "arxiv", "semantic_scholar", "openalex", "pubmed", "crossref"
        ],
        QueryType.TECHNICAL: [
            "stackoverflow", "github", "brave", "bing", "reddit"
        ],
        QueryType.CODE: [
            "github", "stackoverflow", "pypi", "npm", "dockerhub"
        ],
        QueryType.TROUBLESHOOTING: [
            "reddit", "stackoverflow", "brave", "bing", "superuser"
        ],
        QueryType.INDUSTRIAL: [
            "brave", "bing", "reddit", "arxiv", "stackoverflow"
        ],
        QueryType.MEDICAL: [
            "pubmed", "semantic_scholar", "wikipedia", "brave"
        ],
        QueryType.NEWS: [
            "bing_news", "brave", "reddit"
        ],
        QueryType.GENERAL: [
            "brave", "bing", "mojeek", "reddit", "wikipedia"
        ],
    }

    # Pattern definitions for each query type
    PATTERNS = {
        QueryType.ACADEMIC: [
            r"\b(research|study|paper|journal|publication|thesis|dissertation)\b",
            r"\b(doi|arxiv|pubmed|pmid|isbn)\b",
            r"\b(et al\.?|citation|bibliography|peer.?review)\b",
            r"\b(hypothesis|methodology|findings|abstract)\b",
            r"\b(literature review|meta.?analysis|systematic review)\b",
        ],
        QueryType.TECHNICAL: [
            r"\b(tutorial|documentation|how to|guide|example)\b",
            r"\b(api|sdk|library|framework|package)\b",
            r"\b(install|setup|configure|deploy)\b",
            r"\b(best practice|pattern|architecture)\b",
        ],
        QueryType.CODE: [
            r"\b(python|javascript|java|rust|go|c\+\+|typescript)\b",
            r"\b(function|class|method|variable|import)\b",
            r"\b(github|gitlab|npm|pypi|pip install)\b",
            r"\b(code|script|program|algorithm)\b",
            r"\b(syntax|compile|runtime|exception)\b",
        ],
        QueryType.TROUBLESHOOTING: [
            r"\b(error|exception|bug|issue|problem|fail)\b",
            r"\b(not working|doesn't work|won't|can't)\b",
            r"\b(fix|solve|resolve|debug|troubleshoot)\b",
            r"\b(help|stuck|confused|weird)\b",
            r"\b(warning|crash|freeze|hang)\b",
            r"(SRVO|MOTN|SYST|INTP|PROG|MANU|TOOL|HOST)-\d+",  # FANUC errors
            r"(fault|alarm|error)\s*(code|number|message)",
        ],
        QueryType.INDUSTRIAL: [
            r"\b(fanuc|siemens|rockwell|allen.?bradley|abb|kuka)\b",
            r"\b(plc|hmi|scada|dcs|cnc|robot)\b",
            r"\b(servo|motor|drive|encoder|sensor)\b",
            r"\b(ladder|function.?block|structured.?text)\b",
            r"\b(injection.?mold|extrusion|blow.?mold)\b",
            r"\b(automation|manufacturing|industrial)\b",
        ],
        QueryType.MEDICAL: [
            r"\b(symptom|diagnosis|treatment|medication|drug)\b",
            r"\b(disease|condition|syndrome|disorder)\b",
            r"\b(clinical|patient|hospital|doctor|physician)\b",
            r"\b(therapy|surgery|procedure|prognosis)\b",
        ],
        QueryType.NEWS: [
            r"\b(news|breaking|latest|today|yesterday)\b",
            r"\b(announced|reported|released|unveiled)\b",
            r"\b(20\d{2})\b",  # Year references
            r"\b(update|announcement|press.?release)\b",
        ],
    }

    # Keywords that boost confidence for each type
    BOOSTERS = {
        QueryType.ACADEMIC: {"research", "paper", "study", "journal", "doi"},
        QueryType.TECHNICAL: {"tutorial", "documentation", "api", "how to"},
        QueryType.CODE: {"python", "javascript", "github", "function", "class"},
        QueryType.TROUBLESHOOTING: {"error", "fix", "not working", "help"},
        QueryType.INDUSTRIAL: {"fanuc", "plc", "robot", "servo", "cnc"},
        QueryType.MEDICAL: {"symptom", "treatment", "diagnosis", "drug"},
        QueryType.NEWS: {"news", "today", "latest", "announced"},
    }

    def __init__(self, custom_patterns: Optional[Dict[QueryType, List[str]]] = None):
        """
        Initialize the query router.

        Args:
            custom_patterns: Additional patterns to merge with defaults
        """
        self.patterns = {**self.PATTERNS}
        if custom_patterns:
            for qtype, patterns in custom_patterns.items():
                if qtype in self.patterns:
                    self.patterns[qtype].extend(patterns)
                else:
                    self.patterns[qtype] = patterns

        # Compile patterns for efficiency
        self._compiled: Dict[QueryType, List[re.Pattern]] = {}
        for qtype, pattern_list in self.patterns.items():
            self._compiled[qtype] = [
                re.compile(p, re.IGNORECASE) for p in pattern_list
            ]

    def route(self, query: str) -> RoutingDecision:
        """
        Route a query to the most appropriate engine group.

        Args:
            query: The search query

        Returns:
            RoutingDecision with engines and confidence
        """
        query_lower = query.lower()
        scores: Dict[QueryType, Tuple[float, List[str]]] = {}

        # Score each query type based on pattern matches
        for qtype, patterns in self._compiled.items():
            matched = []
            for pattern in patterns:
                if pattern.search(query):
                    matched.append(pattern.pattern)

            if matched:
                # Base score from pattern matches
                score = len(matched) / len(patterns)

                # Boost for keyword matches
                boosters = self.BOOSTERS.get(qtype, set())
                boost_count = sum(1 for b in boosters if b in query_lower)
                score += 0.1 * boost_count

                scores[qtype] = (min(score, 1.0), matched)

        # Select best match
        if scores:
            best_type = max(scores.keys(), key=lambda t: scores[t][0])
            confidence, matched = scores[best_type]
        else:
            best_type = QueryType.GENERAL
            confidence = 0.5
            matched = []

        engines = self.ENGINE_GROUPS[best_type]

        # Generate reasoning
        if matched:
            reasoning = f"Matched {len(matched)} {best_type.value} patterns"
        else:
            reasoning = "No specific patterns matched, using general engines"

        logger.debug(
            f"Routed '{query[:50]}...' to {best_type.value} "
            f"(confidence: {confidence:.2f}, patterns: {len(matched)})"
        )

        return RoutingDecision(
            query_type=best_type,
            engines=engines,
            confidence=confidence,
            matched_patterns=matched,
            reasoning=reasoning
        )

    def route_multi(self, query: str, min_confidence: float = 0.3) -> List[RoutingDecision]:
        """
        Route to multiple engine groups if query matches multiple types.

        Useful for complex queries that span multiple domains.

        Args:
            query: The search query
            min_confidence: Minimum confidence to include a route

        Returns:
            List of RoutingDecision objects, sorted by confidence
        """
        query_lower = query.lower()
        decisions = []

        for qtype, patterns in self._compiled.items():
            matched = []
            for pattern in patterns:
                if pattern.search(query):
                    matched.append(pattern.pattern)

            if not matched:
                continue

            score = len(matched) / len(patterns)
            boosters = self.BOOSTERS.get(qtype, set())
            boost_count = sum(1 for b in boosters if b in query_lower)
            score += 0.1 * boost_count
            score = min(score, 1.0)

            if score >= min_confidence:
                decisions.append(RoutingDecision(
                    query_type=qtype,
                    engines=self.ENGINE_GROUPS[qtype],
                    confidence=score,
                    matched_patterns=matched,
                    reasoning=f"Matched {len(matched)} {qtype.value} patterns"
                ))

        # Sort by confidence
        decisions.sort(key=lambda d: d.confidence, reverse=True)

        # If no matches, add general
        if not decisions:
            decisions.append(RoutingDecision(
                query_type=QueryType.GENERAL,
                engines=self.ENGINE_GROUPS[QueryType.GENERAL],
                confidence=0.5,
                matched_patterns=[],
                reasoning="No specific patterns matched"
            ))

        return decisions

    def get_combined_engines(
        self,
        query: str,
        max_engines: int = 6
    ) -> Tuple[List[str], str]:
        """
        Get a combined list of engines from all matching routes.

        Args:
            query: The search query
            max_engines: Maximum engines to return

        Returns:
            Tuple of (engine list, reasoning string)
        """
        decisions = self.route_multi(query)

        # Combine engines from all matches, preserving order by confidence
        seen: Set[str] = set()
        engines: List[str] = []

        for decision in decisions:
            for engine in decision.engines:
                if engine not in seen and len(engines) < max_engines:
                    seen.add(engine)
                    engines.append(engine)

        types = [d.query_type.value for d in decisions[:3]]
        reasoning = f"Combined engines for: {', '.join(types)}"

        return engines, reasoning


# Singleton instance
_router: Optional[QueryRouter] = None


def get_router() -> QueryRouter:
    """Get or create the query router singleton."""
    global _router
    if _router is None:
        _router = QueryRouter()
    return _router


# Example usage
def example_usage():
    """Demonstrate query routing."""
    router = get_router()

    test_queries = [
        "machine learning research paper 2024",
        "python tutorial for beginners",
        "FANUC SRVO-063 servo alarm troubleshooting",
        "how to fix TypeError in React",
        "latest news about AI regulation",
        "symptoms of diabetes treatment options",
        "what is the capital of France",
        "PLC ladder logic programming Allen-Bradley",
    ]

    print("Query Routing Examples:")
    print("=" * 70)

    for query in test_queries:
        decision = router.route(query)
        print(f"\nQuery: {query}")
        print(f"  Type: {decision.query_type.value}")
        print(f"  Confidence: {decision.confidence:.2f}")
        print(f"  Engines: {', '.join(decision.engines[:4])}...")
        print(f"  Reasoning: {decision.reasoning}")


if __name__ == "__main__":
    example_usage()
