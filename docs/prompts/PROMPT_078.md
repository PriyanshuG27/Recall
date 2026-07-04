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
* @testing-patterns
* @webapp-testing

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
✅ @testing-patterns loaded
✅ @webapp-testing loaded
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

## PROMPT 078 — Integration Test: Full Item Save Flow

**Skills:** `python-testing-patterns`, `testing-patterns`, `webapp-testing`

```
Create an end-to-end integration test suite validating the full item save lifecycle from Telegram webhook reception through passive context ingestion, multi-tier AI cascade, database persistence, and WebSocket real-time notification.

Create `backend/tests/integration/test_full_save_flow.py`:

```python
import pytest
import asyncio
from fastapi.testclient import TestClient
from backend.main import app

def test_full_instagram_reels_save_flow(client, mock_cobalt_and_ai):
    """Scenario 1: Instagram Reels Ingestion & Passive Context Enrichment."""
    payload = {
        "update_id": 888123,
        "message": {
            "message_id": 456,
            "from": {"id": 1001, "first_name": "IngestTester"},
            "chat": {"id": 1001},
            "text": "https://www.instagram.com/reel/C8x9yZ123/"
        }
    }
    
    # 1. Trigger POST /webhook
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    
    # 2. Assert webhook returns ACK in < 50ms
    assert response.json().get("status") == "ok"
    
    # 3. Assert DB item written with passive_context metadata
    # 4. Assert raw_text is Fernet encrypted (starts with 'gAAAAA')
    # 5. Assert WebSocket new_node broadcast sent to subscriber
```

Scenario 2 — AI Cascade Fallback & DLQ Writing:
  1. Post HTTP POST to `/webhook` with a complex scanned PDF document.
  2. Mock Modal GPU and secondary AI providers to raise TimeoutError / 500 Internal Error.
  3. Verify fallback bookmark item is created with title and empty raw_text.
  4. Assert entry written to `dead_letter_queue` table BEFORE fallback bookmark item save succeeds.

Rules:
- Require isolated Neon dev/test database branch. Refuse execution if `DATABASE_URL` contains "production" or "main".
- Pytest teardown fixture cleans up all created test items, processed updates, and DLQ rows after test completion.

Gate Check:
[ ] Multi-format ingestion test passes end-to-end with passive_context captured
[ ] Fernet encryption verified on raw_text column
[ ] DLQ entry timing confirmed before fallback bookmark creation
[ ] Test suite completes in < 60 seconds with full DB cleanup
```
