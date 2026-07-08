# Recall Architectural Roadmap

This document outlines the priority development phases, guidelines, and restrictions for stabilizing and scaling **Recall**.

---

## Final Priority Order
1. **Branching Integration** (Completed)
2. **AI Cascade Migration** (Completed)
3. **Code Cleanup** (Completed)
4. **Security Hardening** (Next Priority)
5. **Logging (Structlog)**
6. **Product & Cost Analytics**
7. **Production Testing**
8. **Production Deployment**
9. **Observe Real Usage**
10. **Instructor Integration**
11. **Unstructured Parser Integration**
12. **Mixedbread Reranker Integration**
13. **Metadata Filtering**
14. **Parent-Child Retrieval**
15. **Context Compression**
16. **Graph Extraction**
17. **Memory Layer**
18. **GraphRAG Evolution**
19. **Infrastructure Upgrades** (Only if metrics demand them)

---

## Phase 1 — Finish the Current Product (Highest Priority)

Do not adopt external libraries yet. Focus on finishing the core features that users will interact with.

### 1. Integrate the Branching PoC
*   **Status:** Completed.
*   **Description:** Branching logic is fully integrated into the backend core services.

### 2. Replace the Old AI Cascade
*   **Status:** Completed.
*   **Description:** Removed legacy paths, duplicate executions, duplicate planners, and dead code. All AI queries now pass through the unified cascade router.

### 3. Code Cleanup
*   **Status:** Completed.
*   **Description:** Removed duplicate services, old prompts, unused models, duplicate websocket code, and old retry logics.

---

## Phase 2 — Production Hardening

Focus on making Recall safe, observable, and reliable.

### 1. Security
*   **Webhook Verification:** Validate Telegram HMAC.
*   **Cache Key Safety:** Clean and secure Redis key lookups.
*   **Unified AI Security Layer:** Check and filter prompts.
*   **Sensitive Document Detection:** Detect PII and redact it.
*   **PII Masking & Prompt Injection Protection:** Sanitize inputs before passing to LLMs.

### 2. Logging
*   **Framework:** Implement `structlog`.
*   **Unified Context:** Every request, database query, AI execution, and queue job should carry:
    *   `request_id`
    *   `user_id`
    *   `task_id`
    *   `worker_id`

### 3. Analytics
*   **Storage:** PostgreSQL (no separate analytics DB).
*   **Tracks:**
    *   Product analytics
    *   AI analytics
    *   Cost analytics

### 4. Tests
*   Verify AI, retrieval, queue worker, security, auth, and webhook paths.

---

## Phase 3 — Ship

*   Deploy to production.
*   Freeze architectural changes and documentation during deployment.

---

## Phase 4 — Observe

*   Monitor performance metrics from real usage:
    *   Logs and exception rates.
    *   API and database query latencies.
    *   AI token costs.
    *   Queue depths and worker throughput.
    *   Search latency and accuracy failures.

---

## Phase 5 — First Major Upgrade

Begin adopting target architectural improvements in order of cost-to-benefit ratio:

1.  **Instructor:** Structured outputs.
2.  **Unstructured:** Better PDF, HTML, and DOCX parsing.
3.  **Mixedbread Reranker:** Improve retrieval quality without changing storage.
4.  **Metadata Filtering:** Narrow search space cheaply.
5.  **Parent-Child Retrieval:** Fetch better context chunks.
6.  **Context Compression:** Minimize token count.
7.  **Graph Extraction:** Extract entities, relations, and communities.
8.  **Memory:** Working, semantic, and episodic layers.

---

## Phase 6 — Version 2

Evolve the system to make it smarter:
*   GraphRAG-style retrieval.
*   Graph traversal optimizations.
*   Memory consolidation.
*   Semantic hub generation.

---

## Phase 7 — Version 3

Scale the infrastructure *only* if metrics justify it:
*   DSPy
*   Neo4j / Qdrant / Distributed workers
*   OpenTelemetry

---

## Excluded Frameworks & Tools (DO NOT USE)
Do not spend time adopting:
*   Qdrant / Neo4j / Memgraph / FalkorDB (keep standard PGvector + trigrams)
*   Mem0 / Haystack / LangChain / LlamaIndex / CrewAI / AutoGen / Semantic Kernel
*   ClickHouse / Kafka / Kubernetes
