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

* @k6-load-testing
* @performance-profiling
* @async-python-patterns

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
✅ @k6-load-testing loaded
✅ @performance-profiling loaded
✅ @async-python-patterns loaded
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

## PROMPT 077 — Load Testing with k6

**Skills:** `k6-load-testing`, `performance-profiling`, `async-python-patterns`

```
Create and execute k6 load testing scripts to measure Telegram webhook ACK latency and hybrid vector search performance under heavy simulated user load.

Create `backend/tests/load/k6_webhook.js`:
```javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  stages: [
    { duration: '15s', target: 50 },
    { duration: '30s', target: 50 },
    { duration: '15s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<50'],
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const url = `${__ENV.API_URL}/webhook`;
  const payload = JSON.stringify({
    update_id: Math.floor(Math.random() * 1000000),
    message: {
      message_id: 123,
      from: { id: 99999, first_name: 'TestUser' },
      chat: { id: 99999 },
      text: 'https://instagram.com/reel/C123456',
    },
  });

  const params = { headers: { 'Content-Type': 'application/json' } };
  const res = http.post(url, payload, params);

  check(res, {
    'status is 200': (r) => r.status === 200,
    'ACK under 50ms': (r) => r.timings.duration < 50,
  });
}
```

Also create `backend/tests/load/k6_search.js`:
- 30 VUs, 45 seconds duration.
- POST `/api/search` with `{"query": "machine learning architecture"}`.
- Target: 95th percentile response time (p95) < 300 ms.

Rules:
- Load scripts must target isolated dev/staging environments — NEVER production.
- Use k6 environment variables for API base URLs and auth cookies.
- Output results to JSON artifacts (`k6_webhook_results.json`, `k6_search_results.json`).

Gate Check:
[ ] k6_webhook.js completes 50 VU load test with p95 ACK latency < 50 ms
[ ] k6_search.js completes 30 VU load test with p95 search latency < 300 ms
[ ] 0% HTTP 5xx server error rate across all load scenarios
[ ] k6 threshold assertion verification exits with status code 0
```
