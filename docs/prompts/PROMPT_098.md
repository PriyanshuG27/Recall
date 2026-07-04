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

* @readme-documentation
* @open-source
* @technical-writing

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
✅ @readme-documentation loaded
✅ @open-source loaded
✅ @technical-writing loaded
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

## PROMPT 098 — README.md for GitHub

**Skills:** `readme-documentation`, `open-source`, `technical-writing`

```
Create a comprehensive, visually compelling `README.md` for the GitHub repository.

Create `README.md` at project root:
```markdown
# ✦ Recall — AI Knowledge Management & Observatory

> Forward anything to Telegram. Find everything with natural language.

![Recall Observatory 3D Starry Sky](fastapi_flow.png)

## Overview & Key Capabilities

Recall is an AI-powered personal second brain built around a 3D Observatory visual environment.

- **✦ 3D Observatory Environment**: Starry Sky mind map (`NebulaCanvas.jsx`) rendered with Three.js / React Three Fiber at 60 FPS, alongside a 3D Glass Archive Cylinder (`ArchiveCylinder.jsx`).
- **✦ Interactive RAG Citations**: Clicking citation badges (`[1]`, `[2]`) in AI assistant answers automatically switches to Map (`/map`), smoothly pans and zooms camera transform to center cited node at scale $k = 1.35$, selects node, highlights connection lines, and animates a 3-second gold flare ring.
- **✦ Multi-Tier Ingestion**: Ingests text, voice audio (Whisper), PDFs (PyPDF/OCR), images (Pillow contrast/sharpen + Tesseract OCR), YouTube/Instagram videos via Cobalt API & OpenGraph HTML scraping fallback.
- **✦ Multi-Tier AI Cascade**: Groq Llama 3 70B -> Gemini 1.5 Pro -> Modal GPU fallback with dynamic Markdown templates (Variants A-F), brand spelling repair ('TestSprite'), and dead-letter queue recovery.
- **✦ Passive Context & Onboarding**: Passive context tracking (`compute_passive_context`), location-based timezone auto-detection, and Day 1-5 onboarding state machine.
- **✦ Active Recall & Spaced Repetition**: SuperMemo SM-2 algorithm quiz generator and drill flashcards (`/drill`).
- **✦ Telegram Friend Fast-Track (`/match`)**: 5-question thought-compatibility game generating referral links and computing tag synergy scores.

## Architecture

```
Telegram Bot / Chrome Extension / SPA
       │
       ▼
 FastAPI Backend (Port 8000)
       │
 ┌─────┴──────────────────┐
 ▼                        ▼
Upstash Redis Queue   Neon PostgreSQL (pgvector + pg_trgm)
 │                        │
 ▼                        ▼
Worker Ingestion      HNSW Cosine Vector Search (<10ms)
 │
 ▼
AI Cascade (Groq ➔ Gemini ➔ Modal GPU)
```

## Quick Start

```bash
# Backend Setup
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000

# Frontend Setup
cd frontend
npm install
npm run dev
```

## Testing & Verification

```bash
# Run backend pytest suite (339 tests)
python -m pytest

# Run frontend Vitest suite (83 tests)
cd frontend && npm run test
```
```

Rules:
- Include absolute path clickable file links to repository documentation files.

Gate Check:
[ ] README.md contains complete setup instructions, architecture diagram, and feature descriptions
[ ] All commands in README tested and verified functional
[ ] Markdown renders cleanly on GitHub
```
