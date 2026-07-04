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

* @python-pro
* @testing-patterns
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
✅ @python-pro loaded
✅ @testing-patterns loaded
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

## PROMPT 086 — Smoke Test Script (Production Verification)

**Skills:** `python-pro`, `testing-patterns`, `production-verification`

```
Create and execute `backend/scripts/smoke_test.py` to perform post-deployment verification against live production environments.

Create `backend/scripts/smoke_test.py`:
```python
import argparse
import requests
import websocket
import sys

def run_smoke_test(api_url, token):
    headers = {"Cookie": f"recall_session={token}"}
    
    # T1: Health check
    r = requests.get(f"{api_url}/health", timeout=5)
    assert r.status_code == 200 and r.json().get("status") == "ok", "T1 Health Check Failed"
    print("[✓] T1: Health Check Passed")
    
    # T2: Profile
    r = requests.get(f"{api_url}/api/me", headers=headers, timeout=5)
    assert r.status_code == 200, "T2 Profile Failed"
    print("[✓] T2: Profile Endpoint Passed")
    
    # T3: Hybrid Search
    r = requests.post(f"{api_url}/api/search", json={"query": "test"}, headers=headers, timeout=5)
    assert r.status_code == 200, "T3 Search Failed"
    print("[✓] T3: Search API Passed")

    print("ALL SMOKE TESTS PASSED!")
    sys.exit(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()
    run_smoke_test(args.api_url, args.token)
```

Rules:
- Smoke test must NOT use production bot token — use a test JWT generated with FERNET_KEY.
- Exit code 0 on success, 1 on failure.

Gate Check:
[ ] All 7 production smoke test scenarios pass cleanly
[ ] Webhook ACK response verified < 50 ms
[ ] WebSocket handshake completes within 2 seconds
[ ] Exit code 0 returned on success
```
