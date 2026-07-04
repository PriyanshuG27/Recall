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

* @security-scanning-security-sast
* @security-scanning-security-hardening
* @security

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
✅ @security-scanning-security-sast loaded
✅ @security-scanning-security-hardening loaded
✅ @security loaded
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

## PROMPT 084 — Security Scanning: SAST + Dependency Audit

**Skills:** `security-scanning-security-sast`, `security-scanning-security-hardening`, `security`

```
Run automated static application security testing (SAST), secret detection, and dependency vulnerability scans across backend and frontend codebases.

Execution Battery:
1. Backend SAST (Bandit):
   ```powershell
   bandit -r backend/ -ll -f json -o security_reports/bandit_report.json
   ```
   Must report 0 HIGH severity vulnerabilities.

2. Backend Dependency Audit (pip-audit):
   ```powershell
   pip-audit --require-hashes -r backend/requirements.txt -o security_reports/pip_audit.json
   ```
   Must report 0 CRITICAL or HIGH vulnerability CVEs.

3. Frontend Dependency Audit (npm audit):
   ```powershell
   cd frontend; npm audit --json > ../security_reports/npm_audit.json
   ```
   Must report 0 CRITICAL or HIGH vulnerabilities.

4. Secret Leak Detection:
   Scan codebase for unencrypted Fernet keys, JWT secrets, Telegram bot tokens, or AWS credentials:
   ```powershell
   grep -rE "(gAAAAA[A-Za-z0-9+/]{60,}|TELEGRAM_BOT_TOKEN\s*=\s*['\"][0-9]+:[A-Za-z0-9_-]{35})" backend/ frontend/
   ```
   Must return 0 secret leaks.

Output: Generate `docs/SECURITY_SCAN_REPORT.md` recording scan dates, tool versions, and vulnerability counts.

Rules:
- Any HIGH or CRITICAL security finding is a BLOCKER.
- Any path traversal risk (`open(user_input)` without path validation) must be remediated.

Gate Check:
[ ] 0 HIGH findings in Bandit SAST report
[ ] 0 CRITICAL/HIGH CVEs in pip-audit and npm audit
[ ] 0 plain-text secrets in repository history or code
[ ] Security scan report written to docs/SECURITY_SCAN_REPORT.md
```
