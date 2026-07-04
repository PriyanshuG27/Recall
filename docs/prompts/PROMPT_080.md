# 🚨 GLOBAL EXECUTION PROTOCOL (MANDATORY)

This protocol overrides every other instruction in this prompt.

---

# Phase 0 — Repository Loading (BLOCKING)

Before **any** reasoning, planning, implementation, refactoring, testing, tool usage, architecture decisions, or code generation:

## Step 1 — Load Repository Context

Read **completely**:

* `AGENTS.md`
* Every document under `/docs`
* Every document referenced by `AGENTS.md`
* Every dependency listed in **Required Dependencies**

Do **not** skip documents because they appear unrelated.

If **any** required file cannot be found or read:

* STOP immediately.
* Report the missing file(s).
* Do **not** continue.
* Wait for further instructions.

---

# Phase 1 — Dependency Loading (BLOCKING)

## Required Dependencies

Read the following dependencies completely before continuing:

* @performance-profiling
* @postgres-best-practices
* @web-performance-optimization

Read every dependency **from beginning to end**.

Do **not**:

* skim
* summarize without reading
* rely on memory
* assume previous prompts already loaded them

Every architectural, implementation, security, performance, testing, and design decision must comply with these dependencies.

---

# Phase 2 — Verification (REQUIRED)

Before writing **any** code, output exactly:

```text
### Repository Verification

✅ AGENTS.md loaded
✅ Repository documentation loaded
✅ @performance-profiling loaded
✅ @postgres-best-practices loaded
✅ @web-performance-optimization loaded
```

Only mark a dependency as loaded if it was actually located, opened, and completely read.

---

# Phase 3 — Compliance Summary (REQUIRED)

For **every** dependency and repository document:

Provide:

* 3–5 important implementation rules
* the relevant section/reference
* how those rules affect this implementation

Do **not** continue if this cannot be done.

---

# Phase 4 — Implementation Plan (REQUIRED)

Before generating code provide:

* Architecture overview
* Files to modify/create
* Backend changes
* Frontend changes
* Database changes
* API changes
* Scheduler changes (if any)
* Security considerations
* Performance considerations
* Testing strategy

---

# GLOBAL REPOSITORY RULES

These rules apply regardless of the prompt.

## Architecture

* Fixed stack:

  * FastAPI
  * React + Vite
  * Neon PostgreSQL + pgvector + pg_trgm
  * Upstash Redis
  * Modal GPU
  * Render
  * Vercel

* Do not introduce new libraries without explicit justification.

* Prefer stdlib and already-approved packages.

---

## Database

* Parameterized SQL only.
* Never build SQL via string interpolation.
* Every user query must be scoped to the authenticated user.
* Use transactions where required.
* Respect existing indexes.

---

## Security

* Never expose:

  * TELEGRAM_BOT_TOKEN
  * JWT_SECRET
  * FERNET_KEY

* Never log:

  * plaintext
  * tokens
  * secrets
  * encrypted values

* Encrypt before DB write where required.

* Secret comparisons must always use:

```python
hmac.compare_digest(...)
```

Never use `==`.

---

## Authentication

Every `/api/*` endpoint must authenticate using the project's existing authentication middleware.

Never duplicate authentication logic.

---

## Performance

Maintain repository targets including:

* Webhook ACK <50 ms
* Canvas 60 FPS @ 500 nodes
* Vector search <10 ms
* Text search <5 ms

Heavy work must remain asynchronous.

---

## Error Handling

* Specific exception handling only.
* No broad silent failures.
* Never expose stack traces.
* Preserve repository retry behavior.
* Scheduler jobs must configure the required `misfire_grace_time`.

---

## Testing

Every new function requires corresponding unit tests.

Backend:

* pytest

Frontend:

* Vitest

Mock:

* AI services
* Telegram
* Redis
* Google APIs
* Chrome APIs
* External services

### IMPORTANT

Create or update tests.

**Do NOT execute them.**

---

## Coding Rules

* Reuse existing project abstractions.
* Avoid duplicate logic.
* Keep implementations modular.
* Follow repository conventions.
* Prefer composition over duplication.

---

# Failure Policy

If any dependency, AGENTS.md, or required documentation cannot be loaded:

* STOP.
* Do not generate code.
* Do not guess.
* Report what is missing.
* Wait for further instructions.

Implementation before completing all loading and verification phases is considered invalid.

---

# TASK

## PROMPT 080 — Performance Profiling: Vector Search Benchmarks

**Skills:** `performance-profiling`, `postgres-best-practices`, `web-performance-optimization`

```
Benchmark database search performance and 3D Observatory visual rendering to verify all target metrics.

Test 1 — Vector Search Latency Target (< 10 ms):
  Seed database with 1,000 items containing 1536-dimensional vector embeddings.
  Execute 100 benchmark vector similarity queries using `EXPLAIN ANALYZE SELECT id, 1 - (embedding <=> %s) AS score FROM items ORDER BY embedding <=> %s LIMIT 10;`.
  Assert: Median execution time < 10 ms.
  Assert: EXPLAIN ANALYZE confirms usage of `idx_items_embedding` HNSW cosine index (`m=16, ef_construction=64`).

Test 2 — GIN Trigram Text Search Latency Target (< 5 ms):
  Execute 100 benchmark text search queries using `EXPLAIN ANALYZE SELECT id FROM items WHERE summary % %s ORDER BY similarity(summary, %s) DESC LIMIT 20;`.
  Assert: Median execution time < 5 ms.
  Assert: EXPLAIN ANALYZE confirms usage of `idx_items_text_gin` GIN trigram index on summary column ONLY.

Test 3 — 3D Observatory Canvas Frame Rate (60 FPS Target):
  Using `PerfContext.jsx` and `useFPSMonitor.js` in frontend benchmarks, simulate 500 active knowledge nodes in `NebulaCanvas.jsx` and `ArchiveCylinder.jsx` with active flowing edge particles and orbiting review particles.
  Assert: Average frame render duration <= 16.67 ms (60 FPS target).

Rules:
- Save benchmark report to `docs/PERFORMANCE_BENCHMARKS.md`.
- Never run benchmark seeding against production databases.

Gate Check:
[ ] Vector search median latency < 10 ms verified with HNSW index scan
[ ] GIN trigram text search median latency < 5 ms verified
[ ] 3D Canvas 500-node simulation maintains 60 FPS target
[ ] Performance report written to docs/PERFORMANCE_BENCHMARKS.md
```
