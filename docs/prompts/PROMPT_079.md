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

* @idor-testing
* @sql-injection-testing
* @web-security-testing

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
✅ @idor-testing loaded
✅ @sql-injection-testing loaded
✅ @web-security-testing loaded
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

## PROMPT 079 — Security Penetration Tests: IDOR + Injection

**Skills:** `idor-testing`, `sql-injection-testing`, `web-security-testing`

```
Create a dedicated security penetration testing suite targeting Broken Object Level Authorization (IDOR), SQL injection, XSS escaping, and Telegram HMAC tampering.

Create `backend/tests/security/test_security_pen.py`:

```python
import pytest
import hmac
import hashlib

def test_idor_cross_user_isolation(client, token_user_A, token_user_B, user_A_item_id):
    """User B must get 404 attempting to access or delete User A's item."""
    # GET item
    res = client.get(f"/api/items/{user_A_item_id}", cookies={"recall_session": token_user_B})
    assert res.status_code == 404
    
    # DELETE item
    res = client.delete(f"/api/items/{user_A_item_id}", cookies={"recall_session": token_user_B})
    assert res.status_code == 404

def test_sql_injection_search_endpoint(client, token_user_A):
    """SQL injection payloads must fail safely without DB execution or 500 errors."""
    payload = {"query": "' OR 1=1; DROP TABLE items; --"}
    res = client.post("/api/search", json=payload, cookies={"recall_session": token_user_A})
    assert res.status_code == 200
    assert isinstance(res.json().get("results"), list)

def test_twa_hmac_tampered_hash_rejection(client):
    """TWA auth middleware must reject tampered hash payloads."""
    tampered_headers = {"Authorization": "twa-init-data query_id=123&user={}&hash=invalid_hash"}
    res = client.get("/api/items", headers=tampered_headers)
    assert res.status_code == 401
```

IDOR Isolation Tests:
  1. User B (with valid JWT B) attempts GET `/api/items/{user_A_item_id}` → returns 404 Not Found.
  2. User B attempts DELETE `/api/items/{user_A_item_id}` → returns 404 Not Found.
  3. User B attempts POST `/api/quizzes/{user_A_quiz_id}/answer` → returns 404 Not Found.
  4. User B attempts DELETE `/api/reminders/{user_A_reminder_id}` → returns 404 Not Found.
  5. User B attempts GET `/api/graph` → returns ONLY User B's nodes, zero nodes belonging to User A.
  6. User B attempts GET `/api/pulse` → returns ONLY User B's mind portrait metrics.

Rules:
- ALL database queries MUST use parameterised query binding (`psycopg` %s or `$1`).
- HMAC comparison MUST use `hmac.compare_digest()` for constant-time evaluation.

Gate Check:
[ ] All IDOR tests return 404/empty sets — zero cross-tenant data leakage
[ ] SQL injection attacks fail harmlessly with 0 schema modifications
[ ] Tampered Telegram initData rejected with 401
[ ] Constant-time HMAC comparison confirmed
```
