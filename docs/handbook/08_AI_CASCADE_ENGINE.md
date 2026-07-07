# Chapter 8: AI Cascade Orchestration Engine

## 1. Introduction
The AI Cascade Orchestration Engine is the heart of Recall's intelligence. It manages the execution of complex prompt pipelines across multiple AI providers, handling model selection, JSON repair, circuit breaking, and fallback logic. 
**CRITICAL RULE:** The architecture of the AI Cascade is FINAL. It must be treated as a black box and must never be redesigned or fundamentally altered. Future improvements must adhere strictly to its established modular components.

## 2. Current Recall implementation
The V9 modular cascade resides in `backend/services/ai_cascade/`. It utilizes a multi-step orchestration process:
1.  **AI Planner:** Maps tasks to active capabilities and selects optimal models.
2.  **Execution Engine:** Enforces an `asyncio.Semaphore(3)` concurrency cap, executes the plan, and utilizes a `RetryEngine` for exponential backoff.
3.  **Security Layer:** Strips prompt injections and truncates length.
4.  **Validators:** Uses regex heuristics to strip Markdown ticks and repair JSON before Pydantic validation.
5.  **Event Bus:** Publishes asynchronous events.
6.  **Persistence:** Writes execution metadata to `ai_decision_logs`.

## 3. Problems
*   **Bypassed Architecture:** The majority of non-summary AI tasks (Quiz, RAG, Insight, OCR URL cleanup) bypass the modular Execution Engine entirely. They execute directly inside `facade.py` using legacy HTTP calls, bypassing circuit breakers, retries, caches, and cost telemetry.
*   **Swallowed Exceptions:** Provider adapters (Groq, Gemini) catch exceptions internally and return `None`. This disables the `RetryEngine`'s specialized backoff logic (e.g., sleeping for 5 seconds on HTTP 429 Rate Limits).
*   **Duplicate Caches:** Summaries use an isolated, in-memory cache manager instead of the shared Upstash Redis cache manager, causing cache misses across worker processes.
*   **Dead Code:** Several classes (`AIStateMachine`, `QualityValidator`) and duplicate prompt loaders (Jinja vs. Txt) clutter the module.

## 4. Design Goals
*   **Unified Pipeline Execution:** 100% of LLM executions must route through the `ExecutionEngine`.
*   **Robust Fallbacks:** Provider errors must bubble up correctly to trigger exponential backoffs and circuit breakers.
*   **Absolute Auditability:** Every execution must write to the `ai_decision_logs` table.
*   **Stateless Operations:** Rely on Redis for circuit breakers and caching, entirely eliminating process-isolated memory caches.

## 5. Architecture
The AI Cascade consists of strictly defined sequential boundaries:
1.  **Facade (`facade.py`):** The public entry point. It creates an `AITask` and passes it to the adapter.
2.  **Planner (`planner.py`):** Matches the `AITask` against `pipelines.yaml` and active capabilities to produce an `ExecutionPlan`.
3.  **Pipeline (`pipelines/`):** A pipeline class (e.g., `SummaryPipeline`) injects variables into a Jinja2 prompt template.
4.  **Engine (`engine.py`):** Executes the prompt against the provider network, enforcing semaphores and executing the `RetryEngine`.
5.  **Validator (`validators/`):** Repairs and validates the response against strict Pydantic schemas.
6.  **Composer (`composer.py`):** Transforms internal results into clean API DTOs.

## 6. Data Flow
1.  Worker calls `AICascade.summarise()`.
2.  Facade constructs an `AITask(type="summary")`.
3.  Planner builds a plan targeting Groq (`llama-3.3-70b-versatile`).
4.  `SummaryPipeline` renders `summary_v1.jinja`.
5.  `SecurityLayer` sanitizes the prompt.
6.  `ExecutionEngine` attempts execution. If Groq returns 429, the provider adapter raises `RateLimitExceededError`.
7.  `RetryEngine` sleeps 5 seconds and retries.
8.  Groq succeeds. The raw markdown JSON is cleaned by `BaseValidator` and parsed into `SummaryResult`.
9.  `PersistenceManager` writes the decision tree to `ai_decision_logs`.
10. The result is composed and returned to the worker.

## 7. Diagrams

```mermaid
flowchart TD
    A[Facade / Worker] --> B[AITask]
    B --> C[AI Planner]
    C --> D[Execution Plan]
    D --> E[Pipeline / Jinja Builder]
    E --> F[Security Layer]
    F --> G[Execution Engine]
    
    G --> H{Retry Engine}
    H -- 429 Error --> H
    H -- Success --> I[Provider (Groq/Gemini/Modal)]
    
    I --> J[JSON Validator & Repair]
    J --> K[Persistence (ai_decision_logs)]
    K --> L[Event Bus & Cost Log]
    L --> M[Response Composer]
```

## 8. Interfaces
*   **Provider Interface:**
    ```python
    class BaseProvider(ABC):
        @abstractmethod
        async def chat_completion(self, messages: List[dict], **kwargs) -> str:
            # Must RAISE exceptions (ProviderError, RateLimitExceededError) on failure.
            pass
    ```

## 9. Database Changes
*   `ai_decision_logs` captures comprehensive execution details (attempts, fallback logic, metadata). Ensure the `raw_response` and `prompt` fields are omitted to prevent PII leakage.

## 10. Folder Structure
*   `backend/services/ai_cascade/` (DO NOT REDESIGN).
*   Must delete unused dead files: `state_machine.py`, `quality_validator.py`.
*   Must merge `prompt_manager.py` (Txt) into `pipelines/context_builder.py` (Jinja).

## 11. API Changes
*   No external REST API changes. The internal `AICascade` facade will be exported as a singleton to avoid repetitive instantiation overhead.

## 12. Migration Strategy
1.  **Wire the Pipelines:** Refactor `generate_quiz`, `generate_insight`, and `answer_question` in `facade.py` to route through the `LegacyAdapter` and `ExecutionEngine`, identical to the summary pipeline.
2.  **Fix Providers:** Modify `groq.py`, `gemini.py`, etc., to remove generic `except Exception: return None` blocks, allowing exceptions to surface.
3.  **Fix Caches:** Update the imports in `legacy/adapter.py` to utilize the Redis-backed cache manager.

## 13. Rollback Strategy
The `facade.py` legacy HTTP calls will remain commented out in the codebase for one deployment cycle. If the Execution Engine integration fails in production, the methods can be hot-swapped back to the bypass implementations.

## 14. Performance
*   **Concurrency:** The `asyncio.Semaphore(3)` is non-negotiable. It protects Recall from bankrupting the cloud account and destroying rate limits.
*   **Latency:** The pipeline orchestration overhead (planning, templating, validation) adds approximately `< 15ms` to the overall execution, which is negligible compared to LLM generation times.

## 15. Failure Modes
*   **Circuit Breaker Trip:** If a provider fails 3 consecutive times, it is tripped for 60 seconds. The engine will gracefully route down the fallback list in `pipelines.yaml`.
*   **Schema Mismatch:** If the LLM generates fundamentally broken JSON that the heuristic regex cannot repair, the execution fails safely and writes to `dead_letter_queue`.

## 16. Security Considerations
*   **Prompt Injection:** The `SecurityLayer` actively searches for XML breakouts (e.g., `</context>`).
*   **PII Masking:** Applies strictly prior to the prompt leaving the server.
*   **Metadata Scrubbing:** The `PersistenceManager` must explicitly delete API keys and raw inputs from the dictionary before writing to PostgreSQL logs.

## 17. Complexity Analysis
*   **Time Complexity:** O(R * (P + E)) where R is retries, P is provider latency, and E is execution overhead.
*   **Space Complexity:** O(T) where T is the prompt size, stored ephemerally during execution.

## 18. Tradeoffs
*   **Rigidity vs. Chaos:** The modular architecture requires defining strict schemas, templates, and pipelines for every new AI feature. This rigidity trades away ad-hoc developmental speed in favor of absolute production stability and observability.

## 19. Alternatives Considered
*   **Replacing the Cascade:** Strictly forbidden by project constraints.
*   **LangChain / LlamaIndex Orchestration:** Rejected. Recall's cascade provides specific JSON heuristic repairs, domain-specific persistence, and strict concurrency controls tailored to this product.

## 20. Final Recommendation
Lock down the AI Cascade. Wire the remaining orphaned tasks (Quiz, Insight, RAG) into the Execution Engine. Fix the provider exception swallowing to restore the Retry Engine's capabilities. Clean up the dead code.

## 21. Implementation Checklist
*   [ ] Wire `generate_quiz`, `generate_insight`, `answer_question` to the Execution Engine.
*   [ ] Refactor `GroqProvider` and others to raise exceptions instead of swallowing them.
*   [ ] Swap the in-memory cache in `legacy/adapter.py` for the Redis `cache_manager`.
*   [ ] Delete `state_machine.py`, `quality_validator.py`, and unused enum priorities.
*   [ ] Convert all remaining `.txt` prompts to `.jinja` and unify the loader.

## 22. Future Improvements
*   Implement the missing `TranscriptionPipeline` and `GraphPipeline` using the established pattern.
*   Upgrade the `BaseValidator` heuristic regexes as new LLM failure modes are discovered in production.

## 23. Version
9.1.0

## 24. Priority
P0 - Critical (The cascade is the core engine of the product).

## 25. Estimated Engineering Effort
14 Developer Days.
