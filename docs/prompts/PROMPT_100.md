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

* @quality-assurance
* @acceptance-testing
* @production-verification

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
✅ @quality-assurance loaded
✅ @acceptance-testing loaded
✅ @production-verification loaded
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

## PROMPT 100 — Final Acceptance: 0 → 100% Gate

**Skills:** `quality-assurance`, `acceptance-testing`, `production-verification`

```
Execute the final end-to-end acceptance review verifying Recall is 100% complete, fully tested, hardened, and ready for production operations.

Final Acceptance Gate Checks:
1. Test Suite Pass (100% Green):
   - Pytest Backend Test Suite: 339 passed (0 failed).
   - Vitest Frontend Test Suite: 83 passed (0 failed).
   - Bridges test modules cleanly skipped for Branching POC.
2. Security Hardening Pass:
   - 0 HIGH findings in Bandit SAST.
   - 0 CRITICAL/HIGH findings in pip-audit and npm audit.
   - 0 plaintext secrets in repo.
   - Fernet encryption verified for sensitive fields (`gAAAAA...`).
3. Performance Verification:
   - Vector search median < 10 ms (HNSW cosine index).
   - Text search median < 5 ms (GIN trigram index).
   - Telegram Webhook ACK latency < 50 ms.
   - 3D Observatory Canvas renders at 60 FPS target.
4. Product Readiness:
   - 3D Observatory Mind Map & Archive Cylinder fully operational.
   - Interactive RAG Citations trigger Map camera pan/zoom (k=1.35) and gold flare ring.
   - Telegram Bot & TWA integration validated (with location timezone auto-detection & `/match` game).
   - Production Smoke Test (`smoke_test.py`) passes cleanly.

Output: Record final acceptance sign-off in `docs/FINAL_ACCEPTANCE_REPORT.md`.

Gate Check:
[ ] 339 pytest tests passing
[ ] 83 vitest tests passing
[ ] All performance targets met
[ ] Final sign-off recorded in docs/FINAL_ACCEPTANCE_REPORT.md — RECALL IS 100% COMPLETE!
```
