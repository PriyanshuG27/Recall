# Architectural Weaknesses (01_PROBLEMS)

**Purpose:** This document identifies every known architectural weakness, technical debt, and risk in the current Recall implementation. It strictly identifies problems without proposing solutions, serving as the justification for future architectural decisions.

---

## 1. Architecture

### 1.1. Fragmented AI Processing (Bypass)
*   **Description:** Multiple AI tasks (Quiz, Insight, RAG) completely bypass the modular `ExecutionEngine`.
*   **Current implementation:** `facade.py` executes legacy HTTP calls directly for certain endpoints rather than routing through `planner.py` and `engine.py`.
*   **Root cause:** Phased rollout of the V9 Cascade left legacy endpoints unconverted.
*   **Impact:** Bypasses circuit breakers, retries, concurrency caps, and cost telemetry.
*   **Frequency:** Every time a Quiz, Insight, or direct RAG query is triggered.
*   **Risk:** High - Can exhaust API limits and bankrupt accounts unmonitored.
*   **Affected modules:** `backend/services/ai_cascade/facade.py`
*   **Estimated engineering cost:** High (Refactoring multiple pipelines)
*   **Estimated user impact:** High (Silent failures when rate limits hit)
*   **Priority:** Critical

### 1.2. Duplicate Instantiation of AICascade
*   **Description:** The core orchestration class is instantiated repetitively.
*   **Current implementation:** Instantiated locally inside individual FastAPI routes and the worker loop.
*   **Root cause:** Lack of dependency injection / global singleton pattern in Fast-API routers.
*   **Impact:** Bloats memory footprint and prevents unified state (like shared caches).
*   **Frequency:** On every API request hitting an AI route.
*   **Risk:** Medium - Contributes to OOM crashes on constrained PaaS limits.
*   **Affected modules:** `backend/routes/api.py`, `backend/worker.py`
*   **Estimated engineering cost:** Low (Dependency injection refactor)
*   **Estimated user impact:** Low (Slight latency/memory overhead)
*   **Priority:** Medium

---

## 2. Security

### 2.1. Unauthenticated Webhooks
*   **Description:** Telegram webhook endpoint does not strictly verify the cryptographic source of the payload.
*   **Current implementation:** `/webhook/telegram` accepts POST payloads without verifying `X-Telegram-Bot-Api-Secret-Token`.
*   **Root cause:** Oversight during rapid prototyping.
*   **Impact:** Attackers can forge webhooks to inject arbitrary data into user accounts or trigger expensive LLM processing.
*   **Frequency:** Always vulnerable.
*   **Risk:** Critical - Complete ingestion spoofing.
*   **Affected modules:** `backend/routes/webhook.py`
*   **Estimated engineering cost:** Low (Middleware addition)
*   **Estimated user impact:** None (Transparent to legitimate users)
*   **Priority:** Critical

### 2.2. Overlapping & Bypassed Prompt Filters
*   **Description:** Safety logic is fragmented and often entirely bypassed.
*   **Current implementation:** `safety.py` uses regex for masking; `security/filter.py` checks length. Legacy AI pipelines bypass both.
*   **Root cause:** Lack of a unified security interceptor boundary.
*   **Impact:** High probability of PII leakage or prompt injection success on bypassed routes.
*   **Frequency:** Depends on user input targeting legacy pipelines.
*   **Risk:** High - Privacy and security violation.
*   **Affected modules:** `backend/services/ai_cascade/security/`
*   **Estimated engineering cost:** Medium
*   **Estimated user impact:** High (Privacy risk)
*   **Priority:** High

---

## 3. Performance

### 3.1. Duplicate WebSocket Endpoints
*   **Description:** Two separate WebSocket routes handle connection mapping.
*   **Current implementation:** `/ws/{token}` and `/api/ws` exist simultaneously.
*   **Root cause:** Incomplete migration to a unified API structure.
*   **Impact:** Causes duplicate broadcasting logic and disconnected authentication schemes.
*   **Frequency:** Every client connection.
*   **Risk:** Low - Primarily technical debt.
*   **Affected modules:** `backend/routes/websocket.py`
*   **Estimated engineering cost:** Medium (Requires frontend alignment)
*   **Estimated user impact:** Low
*   **Priority:** Low

---

## 4. AI

### 4.1. Swallowed Provider Exceptions
*   **Description:** External API errors (e.g., 429 Rate Limits) are caught internally by adapters and hidden from the retry engine.
*   **Current implementation:** `except Exception: return None` inside provider adapters.
*   **Root cause:** Overly aggressive defensive programming against crashes.
*   **Impact:** The `RetryEngine` never triggers exponential backoffs, and circuit breakers never trip.
*   **Frequency:** Whenever an external provider fails.
*   **Risk:** High - Causes silent data loss on ingestion spikes.
*   **Affected modules:** Provider adapters (`groq.py`, `gemini.py`)
*   **Estimated engineering cost:** Low (Remove try/except blocks)
*   **Estimated user impact:** High (Missing summaries/answers)
*   **Priority:** Critical

---

## 5. Retrieval

### 5.1. PDF Layout Flattening
*   **Description:** Complex documents lose structure during parsing.
*   **Current implementation:** Naive text extraction destroys tables and heading hierarchies before chunking.
*   **Root cause:** Reliance on basic PDF string extractors rather than layout-aware parsers.
*   **Impact:** RAG retrieves fragmented, context-free chunks (e.g., half a table row).
*   **Frequency:** Every PDF/DOCX ingestion.
*   **Risk:** Medium - Severely degrades RAG answer quality.
*   **Affected modules:** Ingestion pipeline / chunking logic.
*   **Estimated engineering cost:** High (Integration of Unstructured library)
*   **Estimated user impact:** High (Poor search precision)
*   **Priority:** High

---

## 6. Memory

### 6.1. Ad-hoc Memory Heuristics
*   **Description:** No typed memory differentiation (working vs. episodic vs. semantic).
*   **Current implementation:** Relies entirely on semantic vector proximity during search; no explicit facts are durably stored.
*   **Root cause:** GraphRAG layer was never fully realized.
*   **Impact:** The AI forgets user preferences or contradicts past instructions.
*   **Frequency:** Constant across long-term usage.
*   **Risk:** Medium - Limits product ceiling.
*   **Affected modules:** `backend/services/ai_cascade/`
*   **Estimated engineering cost:** High (New schema and pipeline)
*   **Estimated user impact:** High (Limits "Second Brain" utility)
*   **Priority:** Medium

---

## 7. Graph

### 7.1. Unstructured Graph Edges
*   **Description:** Semantic hubs group items, but distinct entity relationships (edges) are not mapped.
*   **Current implementation:** Centroid-based clustering without typed relations (e.g., "Company X" -> "acquired" -> "Project Y").
*   **Root cause:** V1 focused on vector search rather than structured knowledge graphs.
*   **Impact:** Cannot answer complex relational queries (e.g., "Who are all the leads on Project Apollo?").
*   **Frequency:** Limits advanced querying.
*   **Risk:** Medium
*   **Affected modules:** Database schema, extraction pipeline.
*   **Estimated engineering cost:** High
*   **Estimated user impact:** Medium
*   **Priority:** Medium

---

## 8. Logging

### 8.1. Lack of Structured Logging & Trace IDs
*   **Description:** System is virtually impossible to debug across async boundaries.
*   **Current implementation:** Uses standard Python `print` and `logging` without JSON structure or `request_id` correlation.
*   **Root cause:** Observability was deferred during MVP.
*   **Impact:** Cannot trace a failed worker task back to the specific webhook payload that triggered it.
*   **Frequency:** Affects every debugging session.
*   **Risk:** High - Severe operational blindness.
*   **Affected modules:** Entire backend.
*   **Estimated engineering cost:** Medium (structlog integration)
*   **Estimated user impact:** Low (Internal ops issue)
*   **Priority:** High

---

## 9. Analytics

### 9.1. Global Telemetry Leak (Tenant Violation)
*   **Description:** The `/metrics` API endpoint returns global system token usage to any authenticated user.
*   **Current implementation:** Endpoint does not partition data by `user_id` or enforce an admin role check.
*   **Root cause:** Missing authorization filter on internal metrics route.
*   **Impact:** Any user can see the aggregate operational scale/costs of the entire platform.
*   **Frequency:** Always vulnerable.
*   **Risk:** High - Data/Scale leakage.
*   **Affected modules:** `backend/routes/api.py` (/metrics)
*   **Estimated engineering cost:** Low
*   **Estimated user impact:** None
*   **Priority:** Critical

### 9.2. In-Memory Data Loss for Cost Analytics
*   **Description:** AI costs are tracked in memory and lost when the worker restarts.
*   **Current implementation:** `PromptAnalyticsManager` aggregates metrics locally.
*   **Root cause:** Avoidance of database writes for fast telemetry.
*   **Impact:** Cannot accurately track LLM billing or attribute costs historically.
*   **Frequency:** On every container redeploy/restart.
*   **Risk:** High - Financial blindness.
*   **Affected modules:** `backend/services/ai_cascade/telemetry/`
*   **Estimated engineering cost:** Medium
*   **Estimated user impact:** None
*   **Priority:** High

---

## 10. Developer Experience

### 10.1. Unwired Legacy Code
*   **Description:** Dead files and duplicated prompt formats clutter the core orchestration engine.
*   **Current implementation:** Both `.txt` and `.jinja` prompts exist. Files like `state_machine.py` remain unused.
*   **Root cause:** Incomplete cleanup after the V9 Cascade refactor.
*   **Impact:** High cognitive load for new developers onboarding to the cascade.
*   **Frequency:** Permanent state.
*   **Risk:** Low
*   **Affected modules:** `backend/services/ai_cascade/`
*   **Estimated engineering cost:** Low
*   **Estimated user impact:** None
*   **Priority:** Low

---

## 11. Deployment

### 11.1. Missing Active Heartbeat (Task Loss)
*   **Description:** If a worker crashes (e.g., OOM), the task it was processing is permanently lost.
*   **Current implementation:** `brpoplpush` moves tasks to `recall:processing`. There is no script to re-enqueue orphaned tasks from this list.
*   **Root cause:** Basic queueing without durability checks.
*   **Impact:** Silently dropped messages during traffic spikes or container rotation.
*   **Frequency:** Occasional (tied to PaaS reboots/crashes).
*   **Risk:** High - Data loss.
*   **Affected modules:** `backend/worker.py`
*   **Estimated engineering cost:** Medium
*   **Estimated user impact:** High (Notes sent to bot disappear)
*   **Priority:** High

---

## 12. Testing

### 12.1. Lack of Provider Mocking
*   **Description:** AI pipelines cannot be tested in CI without burning real API credits.
*   **Current implementation:** No robust mocking framework for Groq/Gemini adapters.
*   **Root cause:** Speed of MVP development.
*   **Impact:** Tests are flaky, slow, or nonexistent for core logic.
*   **Frequency:** Every CI run.
*   **Risk:** Medium
*   **Affected modules:** `tests/`
*   **Estimated engineering cost:** High
*   **Estimated user impact:** None
*   **Priority:** Medium

---

## 13. Scalability

### 13.1. Unbounded Database Connections
*   **Description:** PostgreSQL connections scale linearly with the number of worker instances.
*   **Current implementation:** Standard asyncpg pools per worker without a centralized multiplexer like PgBouncer.
*   **Root cause:** Simple direct connection string usage.
*   **Impact:** Connection limit exhaustion on Neon Postgres when scaling workers horizontally.
*   **Frequency:** High traffic spikes.
*   **Risk:** Medium
*   **Affected modules:** `backend/db/database.py`
*   **Estimated engineering cost:** Low (Rely on Neon pooling)
*   **Estimated user impact:** High (Site goes down if DB blocks)
*   **Priority:** Medium

---

## 14. Maintainability

### 14.1. Tight Coupling of Chunking Logic
*   **Description:** Chunking rules are tightly coupled to the PostgreSQL insertion logic.
*   **Current implementation:** `items` and `item_chunks` are processed in massive monolithic functions.
*   **Root cause:** Organic growth of the ingestion pipeline.
*   **Impact:** Difficult to swap chunking strategies (e.g., token-based vs. semantic-based) for A/B testing.
*   **Frequency:** Development time.
*   **Risk:** Low
*   **Affected modules:** `backend/services/ingestion/`
*   **Estimated engineering cost:** Medium
*   **Estimated user impact:** None
*   **Priority:** Low
