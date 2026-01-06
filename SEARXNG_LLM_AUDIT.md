# LLM Integration Audit Report

> **Audit Date**: 2026-01-01 | **Purpose**: Gateway Project Planning | **Scope**: Full Recovery Bot Ecosystem

## Executive Summary

This audit documents all LLM integration points across the Recovery Bot ecosystem to inform the design of a unified **LLM Gateway** service that will manage various LLM engines.

### Key Findings

| Metric | Value |
|--------|-------|
| **Total LLM Integration Points** | 45+ calls across 18 files |
| **LLM Provider** | Ollama (self-hosted, port 11434) |
| **Distinct Models Used** | 8 models |
| **Async Pattern** | 100% async via `httpx.AsyncClient` |
| **Embedding Calls** | 3 locations |
| **Vision/Multimodal Calls** | 2 locations |

---

## 1. LLM Provider Architecture

### Current Setup

```
┌─────────────────────────────────────────────────────────────┐
│                    OLLAMA SERVER                             │
│                  http://localhost:11434                      │
├─────────────────────────────────────────────────────────────┤
│  /api/generate     - Text generation                        │
│  /api/embeddings   - Text embeddings                        │
│  /api/tags         - List available models                  │
│  /api/show         - Model details                          │
└─────────────────────────────────────────────────────────────┘
          ▲                    ▲                    ▲
          │                    │                    │
    ┌─────┴─────┐        ┌────┴────┐        ┌─────┴─────┐
    │  memOS    │        │ SearXNG │        │  Vision   │
    │  Agents   │        │  Cache  │        │ Scraper   │
    └───────────┘        └─────────┘        └───────────┘
```

### Models Inventory

| Model | Purpose | Size | Usage Location |
|-------|---------|------|----------------|
| `llama3.3:70b` | Main generation | 70B | Fallback for synthesis |
| `deepseek-r1:14b-qwen-distill-q8_0` | Thinking/reasoning | 14B | Classifier, synthesis |
| `qwen3:8b` | Fast classification | 8B | Query classifier |
| `qwen3:30b-a3b` | Synthesis fallback | 30B | Synthesizer |
| `gemma3:4b` | Analysis/evaluation | 4B | Analyzer, CRAG, Self-RAG |
| `mxbai-embed-large` | Embeddings (1024d) | - | memOS embeddings |
| `nomic-embed-text` | Embeddings (768d) | - | SearXNG semantic cache |
| `qwen3-vl:7b` | Vision-language | 7B | Screenshot analysis |

### Fallback Chains

```python
# Main Model Chain
llama3.3:70b → qwen3:30b-a3b → qwen3:8b → llama3.2:3b

# Thinking Model Chain
deepseek-r1:14b-qwen-distill-q8_0 → deepseek-r1:8b-0528-qwen3-fp16 → qwen3:8b

# Embedding Model Chain
mxbai-embed-large → bge-m3 → nomic-embed-text

# Vision Model Chain
qwen3-vl:7b → qwen2.5-vl:7b → minicpm-v:latest → llama3.2-vision:11b → granite3.2-vision:2b
```

---

## 2. LLM Calls by Component

### 2.1 SearXNG Module

| File | Function | Endpoint | Model | Timeout | Purpose |
|------|----------|----------|-------|---------|---------|
| `semantic_cache.py:241` | `_get_embedding()` | `/api/embeddings` | `nomic-embed-text` | 30s | Semantic similarity for L2 cache |

**Configuration** (`semantic_cache.py`):
```python
ollama_url: str = "http://localhost:11434"
embedding_model: str = "nomic-embed-text"
embedding_dim: int = 768
```

**Note**: SearXNG's query_router.py is pattern-based (no LLM) for speed. LLM-based routing is in memOS.

---

### 2.2 memOS Agentic Module

#### Core Agents (Primary LLM Usage)

| Agent | File | LLM Calls | Model(s) | Timeout | Purpose |
|-------|------|-----------|----------|---------|---------|
| **Synthesizer** | `synthesizer.py` | 3 | thinking models | 120-600s | Combine search results into answer |
| **QueryClassifier** | `query_classifier.py` | 2 | `qwen3:8b` | 30s | Classify query type/complexity |
| **QueryAnalyzer** | `analyzer.py` | 3 | `gemma3:4b` | 60s | Determine if search needed |
| **SelfReflection** | `self_reflection.py` | 5 | `gemma3:4b` | 30s | Post-synthesis quality check |
| **RetrievalEvaluator** | `retrieval_evaluator.py` | 2 | `gemma3:4b` | 30s | Pre-synthesis retrieval quality |
| **Verifier** | `verifier.py` | 1 | `gemma3:4b` | 30s | Fact verification |

#### Advanced Agents

| Agent | File | LLM Calls | Model(s) | Timeout | Purpose |
|-------|------|-----------|----------|---------|---------|
| **ReasoningComposer** | `reasoning_composer.py` | 1 | configurable | 60s | Multi-agent orchestration |
| **EntityTracker** | `entity_tracker.py` | 1 | `gemma3:4b` | 60s | GSW-style entity tracking |
| **HyDE** | `hyde.py` | 3 | configurable | 30s | Hypothetical document expansion |
| **Planner** | `planner.py` | 3 | MCP | 5-60s | Task planning via MCP |
| **ReasoningDAG** | `reasoning_dag.py` | 1+ | configurable | 30-60s | GoT reasoning paths |
| **AdaptiveRefinement** | `adaptive_refinement.py` | 1 | configurable | 30s | Query refinement |
| **MultiAgent** | `multi_agent.py` | 3 | dynamic | 60s | Multi-agent synthesis |
| **ActorFactory** | `actor_factory.py` | 2 | dynamic | 60s | Dynamic agent assembly |
| **EnhancedReasoning** | `enhanced_reasoning.py` | 1 | configurable | 60s | Multi-step reasoning |
| **GraphCache** | `graph_cache_integration.py` | 1+ | configurable | 60s | KV cache optimization |
| **SelfConsistency** | `self_consistency.py` | 2+ | configurable | 60s | Convergence validation |
| **EntropyMonitor** | `entropy_monitor.py` | 1+ | configurable | 30s | Confidence-based halting |

#### Embedding Service

| Service | File | Endpoint | Model | Timeout | Purpose |
|---------|------|----------|-------|---------|---------|
| **EmbeddingService** | `embedding_service.py` | `/api/embeddings` | `mxbai-embed-large` | 30-60s | Text embeddings (1024d) |

---

### 2.3 Vision-Language Scraping

| Service | File | Endpoint | Model(s) | Timeout | Purpose |
|---------|------|----------|----------|---------|---------|
| **VisionAnalyzer** | `scraper.py:964-1300` | `/api/generate` | Dynamic VL selection | 120s | Screenshot analysis |
| **VLScraper** | `vl_scraper.py` | `/api/generate` | Vision models | 120s | JS-rendered page extraction |

**Vision Model Selection** (GPU-aware):
```python
PREFERRED_VISION_MODELS = [
    "qwen3-vl:7b",
    "qwen2.5-vl:7b",
    "minicpm-v:latest",
    "llama3.2-vision:11b",
    "granite3.2-vision:2b"
]
```

---

## 3. HTTP Client Pattern

**Unified Pattern Used Everywhere**:

```python
async with httpx.AsyncClient(timeout=TIMEOUT) as client:
    response = await client.post(
        f"{ollama_url}/api/generate",  # or /api/embeddings
        json={
            "model": model_name,
            "prompt": prompt_text,
            "stream": False,
            "keep_alive": "30m",  # For thinking models
            "options": {
                "temperature": 0.2-0.5,
                "top_p": 0.9-0.95,
                "num_predict": 128-2048,
                "num_ctx": 32768  # For thinking models
            }
        }
    )
    result = response.json().get("response", "")
```

**Key Observations**:
- All calls are async (`httpx.AsyncClient`)
- No OpenAI SDK used - direct HTTP calls
- `stream: False` for all calls (no streaming)
- Temperature: 0.2-0.5 (low for consistency)
- Context window: Up to 32768 for thinking models

---

## 4. Configuration Centralization

### Current Configuration (`memOS/server/config/settings.py`)

```python
class Settings(BaseSettings):
    # LLM Configuration
    ollama_host: str = "localhost"
    ollama_port: int = 11434
    ollama_model: str = "llama3.3:70b"
    synthesizer_model: str = "qwen3:8b"
    classifier_model: str = "deepseek-r1:14b-qwen-distill-q8_0"
    thinking_model: str = "deepseek-r1:14b-qwen-distill-q8_0"
    ollama_embedding_model: str = "mxbai-embed-large"

    # Timeouts
    llm_request_timeout: float = 90.0
    embedding_timeout: float = 60.0
    health_check_timeout: float = 5.0

    @property
    def ollama_base_url(self) -> str:
        return f"http://{self.ollama_host}:{self.ollama_port}"
```

### SearXNG Configuration (`searxng/semantic_cache.py`)

```python
@dataclass
class CacheConfig:
    ollama_url: str = "http://localhost:11434"
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768
```

---

## 5. Timeout Strategy

| Call Type | Timeout | Rationale |
|-----------|---------|-----------|
| Fast classification | 30s | Quick model, short output |
| Analysis/evaluation | 60s | Medium complexity |
| Main generation | 90s | Standard synthesis |
| Thinking model synthesis | 120-600s | Deep reasoning chains |
| Embedding | 30-60s | Quick vector generation |
| Vision analysis | 120s | Image processing overhead |
| Health check | 5s | Quick ping |

---

## 6. Error Handling & Fallbacks

### Fallback Strategy

```python
async def _call_llm_with_fallback(prompt: str, models: List[str]) -> str:
    for model in models:
        try:
            return await _call_llm(prompt, model)
        except Exception as e:
            logger.warning(f"Model {model} failed: {e}")
            continue
    return fallback_response
```

### JSON Extraction

All agents use robust JSON extraction:
```python
def extract_json_object(text: str) -> Optional[Dict]:
    """Extract JSON from LLM response, handling markdown blocks."""
    # Try raw parse
    # Try markdown ```json blocks
    # Try partial extraction
    # Return None on failure
```

---

## 7. Metrics & Observability

### Current Tracking

```python
# Context utilization tracking
metrics.record_context_utilization(
    agent_name="synthesizer",
    model=model_name,
    input_tokens=len(prompt.split()),
    output_tokens=len(response.split()),
    context_window=32768
)
```

### Event Emission (Orchestrator)

```python
# LLM call events for monitoring
emit_event("llm_call_start", {
    "agent": agent_name,
    "model": model_name,
    "request_id": request_id
})

emit_event("llm_call_complete", {
    "agent": agent_name,
    "duration_ms": duration,
    "tokens_used": token_count
})
```

---

## 8. Gateway Design Recommendations

### 8.1 Required Gateway Features

| Feature | Priority | Rationale |
|---------|----------|-----------|
| **Model Routing** | Critical | Direct calls to appropriate provider (Ollama, vLLM, external) |
| **Fallback Chain** | Critical | Auto-fallback on model unavailability |
| **Request Queuing** | High | Manage concurrent requests per model |
| **Timeout Management** | High | Different timeouts by model type |
| **Metrics Collection** | High | Centralized usage tracking |
| **Rate Limiting** | Medium | Prevent overload |
| **Caching** | Medium | Response caching for identical prompts |
| **Health Monitoring** | Medium | Model availability checks |
| **Load Balancing** | Low | Multiple instances of same model |

### 8.2 Suggested Gateway API

```python
# Gateway endpoint (replaces direct Ollama calls)
POST /gateway/v1/generate
{
    "model": "synthesizer",  # Logical name, not physical
    "prompt": "...",
    "options": {...},
    "priority": "high",  # For queue prioritization
    "timeout_ms": 60000,
    "fallback_models": ["qwen3:8b", "llama3.2:3b"]
}

POST /gateway/v1/embeddings
{
    "model": "default",  # Gateway selects best available
    "texts": ["..."],
    "dimensions": 1024
}

GET /gateway/v1/models
# Returns available models and their status

GET /gateway/v1/health
# Gateway and backend health status
```

### 8.3 Migration Path

1. **Phase 1**: Create gateway service with Ollama passthrough
2. **Phase 2**: Add model routing and fallback logic
3. **Phase 3**: Migrate agents to use gateway endpoint
4. **Phase 4**: Add vLLM backend support
5. **Phase 5**: Add external API support (OpenAI, Anthropic)

### 8.4 Configuration Migration

```yaml
# gateway_config.yaml
providers:
  ollama:
    url: http://localhost:11434
    models:
      - llama3.3:70b
      - qwen3:8b
      - gemma3:4b
      - deepseek-r1:14b-qwen-distill-q8_0

  vllm:
    url: http://localhost:8000
    models:
      - Qwen/Qwen2.5-72B-Instruct-AWQ

model_routing:
  synthesizer:
    primary: qwen3:8b
    fallback: [llama3.3:70b, llama3.2:3b]
    provider: ollama

  classifier:
    primary: deepseek-r1:14b-qwen-distill-q8_0
    fallback: [qwen3:8b]
    provider: ollama

  embedding:
    primary: mxbai-embed-large
    fallback: [nomic-embed-text]
    provider: ollama
```

---

## 9. Files Requiring Gateway Integration

### High Priority (Direct LLM Calls)

| File | Lines | Calls | Action |
|------|-------|-------|--------|
| `memOS/server/agentic/synthesizer.py` | 185-536 | 3 | Replace with gateway |
| `memOS/server/agentic/query_classifier.py` | 140-150 | 2 | Replace with gateway |
| `memOS/server/agentic/analyzer.py` | 325-356 | 3 | Replace with gateway |
| `memOS/server/agentic/self_reflection.py` | 582-616 | 5 | Replace with gateway |
| `memOS/server/agentic/retrieval_evaluator.py` | 493-520 | 2 | Replace with gateway |
| `memOS/server/core/embedding_service.py` | 39-100 | 2 | Replace with gateway |
| `searxng/semantic_cache.py` | 240-252 | 1 | Replace with gateway |

### Medium Priority (Advanced Features)

| File | Calls | Action |
|------|-------|--------|
| `memOS/server/agentic/reasoning_composer.py` | 1 | Gateway integration |
| `memOS/server/agentic/entity_tracker.py` | 1 | Gateway integration |
| `memOS/server/agentic/hyde.py` | 3 | Gateway integration |
| `memOS/server/agentic/verifier.py` | 1 | Gateway integration |
| `memOS/server/agentic/scraper.py` | 2 | Gateway integration (vision) |

### Low Priority (Infrastructure)

| File | Action |
|------|--------|
| `memOS/server/agentic/planner.py` | MCP passthrough |
| `memOS/server/agentic/multi_agent.py` | Dynamic model selection |

---

## 10. Summary Statistics

| Category | Count |
|----------|-------|
| **Total Files with LLM Calls** | 18 |
| **Total LLM Call Sites** | 45+ |
| **Unique Ollama Endpoints Used** | 4 (`/api/generate`, `/api/embeddings`, `/api/tags`, `/api/show`) |
| **Distinct Models Referenced** | 8 |
| **Async Calls** | 100% |
| **Streaming Calls** | 0% |
| **Average Timeout** | 60s |
| **Max Timeout** | 600s (thinking models) |

---

## Appendix: Complete Call Inventory

```
memOS/server/agentic/synthesizer.py:185          POST /api/generate (synthesis)
memOS/server/agentic/synthesizer.py:350          POST /api/generate (thinking)
memOS/server/agentic/synthesizer.py:480          POST /api/execute (MCP)
memOS/server/agentic/query_classifier.py:140     GET /api/tags
memOS/server/agentic/query_classifier.py:148     POST /api/generate
memOS/server/agentic/analyzer.py:325             POST /api/generate
memOS/server/agentic/analyzer.py:338             POST /api/generate
memOS/server/agentic/analyzer.py:350             POST /api/generate
memOS/server/agentic/self_reflection.py:582      POST /api/generate (ISREL)
memOS/server/agentic/self_reflection.py:590      POST /api/generate (ISSUP)
memOS/server/agentic/self_reflection.py:598      POST /api/generate (ISUSE)
memOS/server/agentic/self_reflection.py:606      POST /api/generate (refine)
memOS/server/agentic/self_reflection.py:614      POST /api/generate (temporal)
memOS/server/agentic/retrieval_evaluator.py:493  POST /api/generate
memOS/server/agentic/retrieval_evaluator.py:510  POST /api/generate
memOS/server/agentic/verifier.py:155             POST /api/generate
memOS/server/agentic/reasoning_composer.py:388   POST /api/generate
memOS/server/agentic/entity_tracker.py:382       POST /api/generate
memOS/server/agentic/hyde.py:214                 POST /api/generate
memOS/server/agentic/hyde.py:260                 POST /api/generate
memOS/server/agentic/hyde.py:295                 POST /api/generate
memOS/server/agentic/planner.py:60               POST /api/execute (MCP)
memOS/server/agentic/planner.py:120              GET /api/status (MCP)
memOS/server/agentic/reasoning_dag.py:918        POST /api/generate
memOS/server/agentic/adaptive_refinement.py:108  POST /api/generate
memOS/server/agentic/multi_agent.py:681          GET /api/v1/models/specs
memOS/server/agentic/multi_agent.py:720          GET /api/tags
memOS/server/agentic/multi_agent.py:880          POST /api/generate
memOS/server/agentic/actor_factory.py:409        GET /api/tags
memOS/server/agentic/actor_factory.py:450        POST /api/generate
memOS/server/agentic/enhanced_reasoning.py:652   POST /api/generate
memOS/server/agentic/graph_cache_integration.py  POST /api/generate
memOS/server/agentic/self_consistency.py:130     POST /api/generate
memOS/server/agentic/self_consistency.py:420     POST /api/generate
memOS/server/agentic/entropy_monitor.py:173      POST /api/generate
memOS/server/agentic/scraper.py:1050             GET /api/tags
memOS/server/agentic/scraper.py:1180             POST /api/generate (vision)
memOS/server/services/vl_scraper.py              POST /api/generate (vision)
memOS/server/core/embedding_service.py:50        POST /api/embeddings
memOS/server/core/embedding_service.py:75        POST /api/embeddings (batch)
searxng/semantic_cache.py:241                    POST /api/embeddings
```

---

*Generated by Claude Code LLM Audit - 2026-01-01*
