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
* @unit-testing-test-generate

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
✅ @unit-testing-test-generate loaded
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

## PROMPT 075 — Backend Test Suite: Full Coverage

**Skills:** `python-testing-patterns`, `testing-patterns`, `unit-testing-test-generate`

```
Write and maintain the complete Pytest backend test suite covering all critical paths, multi-tier AI cascade fallbacks, passive context ingestion, onboarding state machine, Telegram location auto-detection, OKF knowledge synthesis, Pulse analytics, all 24+ background scheduler jobs, and Telegram webhook handlers.

Create / update the following test modules under `backend/tests/`:

1. `tests/test_ai_cascade.py` & `tests/test_ai_cascade_extra.py`:
   - `test_ai_cascade_tier_fallback()`: Test Groq Llama 3 70B -> Gemini 1.5 Pro -> Modal GPU fallback flow.
   - `test_variant_templates()`: Test markdown outputs for Academic (Variant A with LaTeX equations), Business (Variant B), Tech Docs (Variant C with code blocks), Legal (Variant D), Creative (Variant E), Social Video (Variant F).
   - `test_brand_spelling_repair()`: Verifies phonetic correction of misheard software brands in transcripts (e.g. repairing 'Digma' to 'TestSprite').
   - `test_passive_context_injection()`: Verifies `compute_passive_context()` metadata is injected into `INSIGHT_SYSTEM_PROMPT` when no context_note is present.
   - `test_dlq_timing_before_bookmark_save()`: Confirms dead_letter_queue row is inserted BEFORE fallback bookmark item save succeeds.

2. `tests/test_phase_1_backfills.py` & `tests/test_batch_onboarding.py`:
   - `test_compute_passive_context()`: Verifies local time mapping, day of week string, 24h count, and session gap hours.
   - `test_onboarding_sequence_state_machine()`: Verifies Day 0 (2h post-save), Day 1 (8 AM morning nudge), Day 2 context note checks, and mid-graph silent user re-engagement scanner (5-30 nodes after 5 days).
   - `test_reset_onboarding_command()`: Tests `/reset_onboarding` clearing saves and resetting onboarding state.
   - `test_location_auto_detect_timezone()`: Tests location coordinate reception, longitude calculation (`round(lon / 15.0 * 2) / 2`), DB timezone offset update, and `remove_keyboard=True` response payload.

3. `tests/test_scheduler.py`, `tests/test_scheduler_extra.py` & `tests/test_engagement_crons.py`:
   - Validates all 24+ cron jobs in `scheduler.py`: `reminders_dispatcher`, `scan_insight_candidates_for_user`, `louvain_clustering`, `run_nightly_mind_type_for_user`, `weekly_profile_text_generator`, `monthly_prediction_generator`, `monthly_discrepancy_scanner`, `monthly_forward_hook`, `partition_creator`, `drive_nudge_sender`, `processed_updates_cleanup`, `daily_digest_sender`, `weekly_drive_sync`, `offpeak_quiz_generator`, `onboarding_sequence_dispatcher`, `mid_graph_re_engagement_dispatcher`, `spaced_repetition_nudge_dispatcher`, `weekly_mind_map_dispatcher`, `monthly_memory_rhythm_scanner`, `near_miss_calibration`, `save_rhythm_scanner`, `recall_moment_dispatcher`, `tag_portraits_generator`, `daily_pulse_updater`.
   - Asserts `misfire_grace_time=60` set on all job registrations.

4. `tests/test_auth.py`, `tests/test_auth_extra.py` & `tests/test_twa_auth.py`:
   - `test_twa_hmac_valid()` & `test_twa_hmac_tampered()`: Validates `hmac.compare_digest()` rejecting tampered `hash` or expired `auth_date`.
   - `test_jwt_cookie_security()`: Verifies `recall_session` cookie set with `httpOnly=True`, `Secure=True`, `SameSite='Lax'`.

5. `tests/test_telegram_buttons.py` & `tests/test_commands.py`:
   - `test_webhook_ack_under_50ms()`: Asserts POST `/webhook` returns HTTP 200 in < 50 ms for BOTH `message` and `callback_query` (inline keyboard buttons like `onboarding_opt:<choice>`).
   - `test_bot_commands()`: Validates `/start`, `/match` (5-question compatibility game), `/drill`, `/search`, `/stats`, `/help`, `/remind`, `/reset_onboarding`.

6. `tests/test_url_ingester.py`, `tests/test_youtube_ingester.py`, `tests/test_instagram_ingester.py`, `tests/test_image_ingester.py`, `tests/test_pdf_chunks.py`, `tests/test_voice_ingester.py`:
   - Ingestion Pipeline: `yt-dlp` video audio extraction, Cobalt API integration (`COBALT_API_URL`), Instagram HTML OpenGraph scraping fallback when unauthenticated requests fail, PyPDF / pdfplumber chunking, Tesseract OCR with Pillow preprocessing (contrast 2.0, sharpen, adaptive binarization), Whisper audio transcription via Groq / Modal.

7. `tests/test_okf.py`, `tests/test_pulse_and_portraits.py` & `tests/test_streak.py`:
   - OKF Service: Optimal Knowledge Formats, structured synthesis, cheat-sheets, executive briefs.
   - Mind Portrait & Pulse Service: Cognitive mind style calculation (Synthesis, Technical, Analytical, Creative), mood trends, linkage ratios, daily streak calculation with freeze/recovery logic.

8. `tests/test_bridges.py`:
   - Top-level skip: `pytestmark = pytest.mark.skip(reason="Bridges hidden for branching POC")`.

Execution Rules:
- 100% offline — zero external HTTP requests (mock Groq, Gemini, Modal, Telegram Bot API, Upstash Redis, and external scrapers).
- Target execution time: full suite run in under 45 seconds total.

Gate Check:
[ ] 339 pytest tests pass with zero network calls
[ ] All 24+ scheduler jobs and engagement crons verified
[ ] Passive context calculation and onboarding state machine tests verified
[ ] Location auto-detection test verifies timezone offset calculation and keyboard dismissal
[ ] Telegram inline callback query ACK verified (< 50 ms)
[ ] AI cascade test confirms DLQ entry written before fallback bookmark creation
[ ] Bridges tests skipped cleanly with explicit POC reason
```
