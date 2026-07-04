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

* @devops
* @deployment-rollback
* @site-reliability

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
✅ @devops loaded
✅ @deployment-rollback loaded
✅ @site-reliability loaded
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

## PROMPT 095 — Rollback Procedure

**Skills:** `devops`, `deployment-rollback`, `site-reliability`

```
Create documented rollback procedures and automated rollback scripts for database schema and application code deployments.

Rollback Playbook (`docs/ROLLBACK_PROCEDURE.md`):
1. Application Code Rollback:
   - Render Backend: Trigger 1-click rollback to previous successful build deployment ID in Render Dashboard.
   - Vercel Frontend: Promote previous deployment commit to Instant Production in Vercel Dashboard.
2. Database Schema Rollback (`backend/db/rollback_schema.sql`):
   - Maintain reverse DDL migration scripts for each database schema change.
   - Ensure rollbacks preserve existing user data rows.
3. Emergency Traffic Cutoff / Maintenance Mode:
   - Toggle `MAINTENANCE_MODE=true` in Render environment settings to return HTTP 503 Maintenance Mode instantly during critical fixes.

Rules:
- Database rollback scripts must be dry-run tested on a Neon dev branch prior to execution on production.

Gate Check:
[ ] Application code rollback procedure documented and verified
[ ] Reverse DDL rollback scripts present for database schema updates
[ ] Maintenance mode toggle returns 503 Maintenance overlay
```
