# Recall Architectural Roadmap

This document outlines the priority development phases, guidelines, and restrictions for stabilizing and scaling **Recall**.

> [!NOTE]
> **Hearth & Thought Compatibility Game**: Hearth is v1. The kintsugi visual compatibility decay and 5-question thought-compatibility game (`bridges.py`) have been deferred post-launch; a fresh design should be implemented when revisited, rather than reviving the legacy code.

---

## Roadmap Overview

```text
Phase 1
Core Completion
│
├── Branching Integration
├── AI Cascade Migration
├── Cleanup
├── Refactor
└── Stable Architecture
        │
        ▼
Phase 1.5
Immediate Security Fixes & Baselines
│
├── Telegram Webhook Verification
├── Secret Masking in Logs
├── Upload MIME/Type Validation
├── File Size Limits
├── Hashing Sensitive Cache Keys
├── Removing Prompt/Content Leaks from Logs
└── Minimal Eval Harness (Prerequisite Gate)
        │
        ▼
Phase 2
Intelligence Upgrade (Knowledge Quality)
│
├── 1. Eval Harness Validation Checkpoint
├── 2. Reranker Integration
├── 3. Parent-Child Retrieval
├── 4. Metadata Filtering
├── 5. Entity & Relationship Extraction
├── 6. Deduplication & Entity Resolution
├── 7. Semantic / Hierarchical Chunking
├── 8. BM25 tuning, Vector Fusion (RRF), Query Rewriting
└── 9. Instructor / Structured Output Enforcement
        │
        ▼
Phase 3
Production Hardening
│
├── Security (PII masking, audit logging, rate limiting)
├── Logging (Structlog integration)
├── Analytics (PostgreSQL telemetry)
├── Performance Tuning (latency & DB indexes)
├── Testing (E2E & automated suites)
├── Monitoring (APM & metrics)
├── Health Checks
├── Deployment
└── Backups
        │
        ▼
Phase 3.5
Database Migration Stabilization
│
└── Dbmate Integration
        │
        ▼
Release Candidate
│
└── Dogfooding & Bug Fixes
        │
        ▼
Production Launch
        │
        ▼
Phase 4
Knowledge Evolution
│
├── GraphRAG Concepts
├── Memory Layers
├── DSPy
├── Evaluation Pipeline Maturation (CI-integrated Ragas/DSPy)
└── Knowledge Health
        │
        ▼
Phase 5
Infrastructure Scaling
│
├── Qdrant (if needed)
├── Neo4j (if needed)
├── OpenTelemetry
├── Distributed Workers
└── Other scale-driven changes
```

## Strategy & Rationale
We perform **intelligence and quality upgrades first (Phase 2) before production hardening (Phase 3)** because production hardening is easier, cleaner, and more stable when the core intelligence layer is already in place.
* **Avoid Analytics Rework**: Introducing a reranker, semantic chunking, or custom search scoring first means we only instrument analytics once for the actual production pipeline.
* **Avoid Logging Rework**: Implementing structured logging across ingestion pipelines is cleaner when we don't have to rewrite the ingestion and parsing pipeline right after.
* **Avoid Security Rework**: Introducing structured extraction and parsing logic before hardening ensures the PII masking and security boundaries are designed around the final data shape.

However, to protect the project during development, we introduce **Phase 1.5 (Immediate Security Fixes & Baselines)**. These are low-effort, high-impact safety fixes that reduce developer-side risk without introducing heavy production infrastructure.

> [!WARNING]
> **Sequencing Risk**: Doing all of Phase 2 (the largest development phase) before Phase 3 security items (rate limiting, audit logging, PII masking) means the system runs without those protections for the full duration of Phase 2. Phase 1.5 must be treated as sufficient coverage for that entire window. If Phase 2 scope grows, specific Phase 3 items (such as rate limiting and PII masking) must be pulled forward rather than delaying them further.

---

## Phase 1 — Core Completion ✅
Finish what already exists to establish a stable architecture.
* **Branching**: Branching logic fully integrated into the backend core services.
* **AI Cascade**: Legacy paths, duplicate executions, duplicate planners, and dead code removed. All queries routed through the unified cascade router.
* **Cleanup & Refactor**: Eliminate duplicate services (such as the Cognitive Bridges router `bridges.py`, its React page `Bridges.jsx`, and associated database tables `cognitive_bridges` and `bridge_invites`), old prompts, unused models, duplicate websocket code, and old retry logic.
* **Database Schema Consolidation**: Sync and consolidate dynamic DDL statements in `backend/db/connection.py::open_pool()` with static definitions in `schema.sql` to prevent schema drift.
* **Stable Architecture**: Achieve architectural consistency across all modules.

---

## Phase 1.5 — Immediate Security Fixes & Baselines 🛡️
Critical safety fixes to protect the development environment, prevent leaks immediately, and establish baseline quality metrics.
* **Telegram Webhook Secret Validation**: Verify incoming webhooks using Telegram HMAC validation.
* **Secret Masking in Logs**: Mask sensitive environment variables (e.g., tokens, keys) in all console outputs and logs.
* **Upload MIME/Type Validation**: Restrict file uploads to allowed formats.
* **File Size Limits**: Enforce maximum limits on payload sizes for uploads.
* **Hashing Sensitive Cache Keys**: Ensure cached items do not expose raw tokens or personal identifiers in Redis keys.
* **Removing Prompt/Content Leaks**: Ensure raw user content or detailed prompts do not leak into general logs.
* **Minimal Eval Harness**: A small fixed test set (20-50 real queries + expected/acceptable results) to measure retrieval quality before Phase 2 changes begin. This is a prerequisite gate, not optional. No Phase 2 sub-phase (reranker, chunking, hybrid scoring) may be considered "done" without before/after eval numbers against this harness.

---

## Phase 2 — Intelligence Upgrade (Knowledge Quality) 🧠
Add improvements that dramatically increase Recall's quality **without changing the product or introducing new user-visible features**.

*Rationale for Priority Order*: Reranker and parent-child retrieval give the largest quality delta per unit of engineering effort; BM25/query rewriting give the smallest.

### 1. Eval Harness Validation Checkpoint
* Establish baseline metrics on the Minimal Eval Harness. No Phase 2 sub-phase (reranker, chunking, hybrid scoring) may be considered "done" without before/after eval numbers against this harness.

### 2. Reranker Integration
* **Reranker**: Integrate a high-quality reranking model (Mixedbread or BGE) to improve precision before adding database complexities.

### 3. Parent-Child Retrieval
* **Parent-Child Retrieval**: Store small chunks for search but retrieve parent chunks for context, ensuring LLMs receive coherent passages.

### 4. Metadata Filtering
* **Metadata Filtering**: Enable precise, database-level metadata filters to narrow search space cheaply.

### 5. Entity & Relationship Extraction
* **Entity & Relationship Extraction**: Extract key nodes and edges to build clean, localized semantic links.
* *Note on Louvain Clustering*: Louvain today is purely similarity-threshold based on item embeddings; "Entity & Relationship Extraction" and "Hub Detection" are net-new builds.

### 6. Deduplication & Entity Resolution
* **Deduplication / Entity Resolution**: Implement near-duplicate note detection and merge same-entity-different-name records. This is higher leverage for personal-knowledge-graph quality than lexical search tuning, and must happen before/alongside entity extraction, not after.
* *Clarification*: Exact SHA256 deduplication exists in the core, so this task is strictly for near-duplicate/semantic dedup and cross-item entity resolution.

### 7. Semantic / Hierarchical Chunking
* **Semantic Chunking**: Chunk documents based on semantic shifts rather than token count.
* **Hierarchical / Adaptive Chunking**: Dynamically adjust chunk sizes based on document layout.

### 8. BM25 tuning, Vector Fusion (RRF), Query Rewriting
* **BM25 Tuning**: Enhance lexical search scoring.
* **Vector Fusion**: Optimize reciprocal rank fusion (RRF) parameters.
* **Query Rewriting**: Standardize and expand search queries before execution.

### 9. Instructor / Structured Output Enforcement
* **Instructor**: Integrate Instructor/Outlines for structured outputs.
* **Better JSON Enforcement**: Ensure robust, parseable JSON schema enforcement.
* *Note*: Treated as cheap infrastructure hygiene, not high-impact.
* > [!WARNING]
  > **Strategic Contradiction**: Structured output enforcement (Instructor/Outlines) is listed here in Phase 2, but the AI Cascade is frozen/finalized in Phase 1 (no structural changes). This must be resolved before scheduling.

### Migration & Re-indexing Note
* **Chunking/Embedding Changes**: Any change to chunking or embedding strategy requires a documented re-indexing plan (dual-write, background re-embed job, or versioned chunk schema) before rollout — do not let old and new chunk formats silently coexist unflagged.

---

## Phase 3 — Production Hardening 🔒
Focus on making Recall safe, observable, and reliable based on the finalized intelligence pipeline.

### 1. Security
* **PII Masking**: Prevent sending sensitive data to external AI models.
* **Audit Logging**: Maintain access and alteration logs for security auditing.
* **Rate Limiting**: Enforce request rate limits to prevent denial-of-service.

### 2. Logging & Analytics
* **Structured Logging**: Implement `structlog` with unified request/user/task context.
* **PostgreSQL Analytics**: Product, AI, and cost analytics tracked inside PostgreSQL.

### 3. Observability & Performance
* **Sentry**: Crash and error reporting.
* **Monitoring & Alerts**: API/Database query latency, queue depth monitoring.
* **Performance Tuning**: Measure and record current baseline latency before setting hard targets (e.g., vector search < 10ms, text search < 5ms). If no baseline exists yet, mark these targets as provisional until measured.

### 4. Deploy & Backups
* **Deployment Automation**: Configs for Vercel, Render, Modal.
* **Backup & Rollback Procedures**: Automated database backups and zero-downtime rollback scripts.

---

## Phase 3.5 — Database Migration Stabilization 🗄️
Stabilize database deployment workflows by transitioning from dynamic schema checking to structured migrations.
* **Dbmate Integration**: Adopt `dbmate` for language-agnostic, raw SQL schema migrations.
* **Migration Directory**: Migrate all existing table definitions to a structured `db/migrations/` folder.
* **CI Integration**: Enforce migration schema checks on pull requests.

---

## Release Candidate 🧪
Deploy internally and validate correctness.
* **Dogfooding**: Use the application internally under real workloads.
* **Bug Fixes**: Resolve edge cases uncovered during active use.
* **Disaster Recovery**: Automated verification of both database backup generation and full-schema restore validation on a clean instance.

---

## Production Launch 🚀
Ship Recall to production users.

---

## Phase 4 — Knowledge Evolution 🧬
Evolve the system to support advanced memory and traversal capabilities.
* **Typed Memory**: Segment memory into working, episodic, and semantic layers.
* **Memory Consolidation**: Implement background consolidation of old memories.
* **Better Graph Traversal & GraphRAG**: Local and global query answering over the knowledge graph.
* **Evaluation Pipeline Maturation (CI-integrated Ragas/DSPy)**: Maturation of the evaluation pipelines to support automated continuous integration testing for retrieval and generation quality.
* **Knowledge Health Scoring**: Periodically check for broken links and outdated information.

---

## Phase 5 — Scale & Infrastructure ⚙️
Only after users and metrics justify it:
* **Vector & Graph DBs**: Transition to standalone Qdrant or Neo4j.
* **Orchestration**: Implement LangGraph or advanced worker setups.
* **Observability**: OpenTelemetry instrumentation.
* **Analytics**: Move analytics to ClickHouse.
* **Infrastructure**: Migrate to Kubernetes or distributed queues if needed.
* > [!WARNING]
  > **Scale Triggers & Bottlenecks**: Louvain clustering runs in \(O(N^2)\) time relative to the number of nodes. Before migrating to Neo4j/ClickHouse, this CPU bottleneck on the single scheduler process will trigger long locks; Louvain must be offloaded to background worker queues before \(N > 5000\).

---

## Excluded Frameworks & Tools (DO NOT USE)
Do not spend time adopting:
* **Qdrant / Neo4j / Memgraph / FalkorDB** (until Phase 5; keep standard PGvector + trigrams)
* **Mem0 / Haystack / LangChain / LlamaIndex / CrewAI / AutoGen / Semantic Kernel**
* **ClickHouse / Kafka / Kubernetes** (until Phase 5)

---

## Roadmap Freeze

This roadmap is frozen as of Version 1.

Changes to the roadmap should only occur if:
- Implementation reveals a critical architectural flaw.
- Production metrics justify a different direction.
- A new product requirement fundamentally changes Recall.

Do not modify the roadmap simply to adopt new technologies or trends.
