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

* @security-hardening
* @security-audit
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
✅ @security-hardening loaded
✅ @security-audit loaded
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

## PROMPT 087 — Security Audit Pass

**Skills:** `security-hardening`, `security-audit`, `web-security-testing`

```
Perform a complete security hardening pass across application APIs, database connections, and authentication routines.

Hardening Checklist:
1. Strict HTTPS & Security Headers (FastAPI middleware):
   - `Strict-Transport-Security: max-age=31536000; includeSubDomains`
   - `X-Content-Type-Options: nosniff`
   - `X-Frame-Options: DENY`
   - `Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' wss: https:;`
2. Database TLS & Encryption Verification:
   - `DATABASE_URL` must mandate `?sslmode=require`.
   - `raw_text` and `google_refresh_token` Fernet encryption verified prior to PostgreSQL write operations.
3. HMAC & Cookie Hardening:
   - Telegram TWA HMAC verification enforces strict hash check via `hmac.compare_digest()`.
   - JWT session cookies enforce `httpOnly=True`, `Secure=True`, `SameSite='Lax'`.
4. Sensitive Data Logging Exclusion:
   - Verify `settings.__repr__()` returns `<Settings: [REDACTED]>`.
   - Ensure `TELEGRAM_BOT_TOKEN`, `FERNET_KEY`, `JWT_SECRET` never appear in application logs or Sentry payloads.

Rules:
- All HTTP routes without explicit public status (`/health`, `/webhook`, `/auth/telegram`) MUST require authenticated user sessions.

Gate Check:
[ ] Security headers present on all FastAPI responses
[ ] Database connections enforce TLS sslmode=require
[ ] Fernet key encryption verified on sensitive database columns
[ ] Zero secrets present in server logs
```
