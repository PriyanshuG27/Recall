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

* @python-testing-patterns
* @async-python-patterns
* @redis-best-practices

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
✅ @python-testing-patterns loaded
✅ @async-python-patterns loaded
✅ @redis-best-practices loaded
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

## PROMPT 082 — Rate Limit Testing: Redis Pipeline Atomicity

**Skills:** `python-testing-patterns`, `async-python-patterns`, `redis-best-practices`

```
Verify sliding window rate limiter atomicity, multi-tenant isolation, and race-condition prevention under concurrent request bursts.

Create `backend/tests/test_rate_limiter_concurrency.py`:
```python
import pytest
import asyncio
from backend.services.rate_limiter import check_rate_limit, RateLimitExceeded

@pytest.mark.asyncio
async def test_concurrent_burst_rate_limiting():
    chat_id = 999111
    # 20 concurrent requests
    tasks = [check_rate_limit(chat_id) for _ in range(20)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    assert all(r is True for r in results)

@pytest.mark.asyncio
async def test_rate_limit_overflow_exactly_5_rejected():
    chat_id = 999222
    # 25 concurrent requests
    tasks = [check_rate_limit(chat_id) for _ in range(25)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    successes = [r for r in results if r is True]
    rejections = [r for r in results if isinstance(r, RateLimitExceeded)]
    
    assert len(successes) == 20
    assert len(rejections) == 5
```

Scenario 3 — Multi-User Isolation.
Scenario 4 — Sliding Window Expiry.

Rules:
- Upstash Redis REST pipeline commands (`INCR`, `EXPIRE`, `ZADD`, `ZREMRANGEBYSCORE`) must execute atomically.
- Use `freezegun` for time manipulation in unit tests.

Gate Check:
[ ] Exactly 20 requests allowed per user per 60s window under concurrency
[ ] Multi-tenant quota isolation confirmed
[ ] Atomic Redis pipeline prevents race conditions during concurrent spikes
```
