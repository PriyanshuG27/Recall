# PROMPTS — Phase 10 & Phase 11 Ultimate Master Playbook (Recall 100% Production State)
> Production-grade, copy-pasteable implementation prompts for **Phase 10: Automated Testing Suite** and **Phase 11: Deployment, Security & Observability** (Prompts 075 → 100).
> Every prompt provides complete technical specifications, exact file paths, full code snippets, test assertions, SQL queries, and gate checks incorporating all Recall Evolution features.

---

## GLOBAL RULES (Mandatory Context for Every Single Prompt)

```
ARCHITECTURE & STACK CONSTRAINTS
- Fixed Stack: FastAPI (backend) · React 18 + Vite (frontend with Three.js / React Three Fiber 3D Observatory) · Neon PostgreSQL (pgvector + pg_trgm) · Upstash Redis REST · Modal GPU · Render · Vercel.
- Database Queries: 100% parameterised statements (%s or $1) — zero raw SQL string interpolation into queries.
- Webhook ACK Target: Return HTTP 200 to Telegram in < 50 ms for BOTH text messages and inline callback query button clicks. All heavy work dispatched asynchronously to background queue.
- Concurrency Cap: asyncio.Semaphore(3) caps concurrent AI cascade tasks. Never raise this limit without explicit benchmark justification.

SECURITY RULES — NON-NEGOTIABLE
- Zero Credential Exposure: TELEGRAM_BOT_TOKEN, FERNET_KEY, JWT_SECRET, COBALT_API_URL keys must NEVER appear in logs, client responses, or frontend source code.
- Encryption at Rest: raw_text and google_refresh_token MUST be Fernet-encrypted (prefixed with gAAAAA...) before writing to PostgreSQL. No exceptions.
- Auth Verification: Every /api/* endpoint must validate either Telegram TWA initData HMAC or the recall_session JWT cookie before processing.
- HMAC Comparison: Must use hmac.compare_digest() for constant-time comparison — never == secret evaluation.
- Multi-Tenant Isolation: Every database query touching items, quizzes, reminders, hubs, pulse metrics, or predictions MUST include WHERE user_id = <verified_user_id>.
- Cookie Hardening: httpOnly=True, Secure=True, SameSite=Lax on all session cookies.
- OAuth Scope: Google OAuth scope restricted exclusively to drive.file — never broader scopes.

PERFORMANCE TARGETS
- Vector Search Latency: < 10 ms (HNSW cosine index: m=16, ef_construction=64).
- Text Search Latency: < 5 ms (GIN trigram on summary column ONLY — never on encrypted raw_text).
- 3D Observatory Canvas Target: 60 FPS at 500 nodes (monitored via PerfContext and useFPSMonitor hook).
- Webhook Response Time: < 50 ms.

ALL 24+ SCHEDULER & ENGAGEMENT CRON ENGINES (scheduler.py)
- Reminders Dispatcher: Checks due reminders and dispatches Telegram notifications (`reminders_dispatcher`).
- Insight Scanner: Cross-item tension/recurring question synthesis between items saved weeks apart (`scan_insight_candidates_for_user`).
- Louvain Clustering: Nightly Louvain community detection on co-occurrence graph updating `semantic_hubs` (`louvain_clustering`).
- Nightly Mind Type Classifier: Computes cognitive mind style (Synthesis, Technical, Analytical, Creative) based on cluster ratios (`run_nightly_mind_type_for_user`).
- Weekly Profile Trajectory Generator: Generates weekly psychological cognitive trajectory profile (`weekly_profile_text_generator`).
- Monthly Prediction Engine: Predicts upcoming interest shifts based on node growth (`monthly_prediction_generator`).
- Monthly Discrepancy Scanner: Compares self-description vs actual saved items (`monthly_discrepancy_scanner`).
- Monthly Forward Hook: Generates forward-looking synthesis prompts (`monthly_forward_hook`).
- Partition Creator: Monthly automated PostgreSQL table partitioning (`partition_creator`).
- Drive Nudge Sender: Drive backup nudge for un-synced active users (`drive_nudge_sender`).
- Idempotency Cleanup: Retains processed updates for 7 days (`processed_updates_cleanup`).
- Daily Digest Sender: Delivers daily digest at user's local 8 AM (`daily_digest_sender`).
- Weekly Drive Sync: Automatic weekly Google Drive sync (`weekly_drive_sync`).
- Offpeak Quiz Generator: Generates SM-2 active recall quizzes during off-peak hours (`offpeak_quiz_generator`).
- Onboarding Sequence Dispatcher: Manages Day 0-2 onboarding state machine (`onboarding_sequence_dispatcher`).
- Mid-Graph Re-Engagement Dispatcher: Nudges silent users (5-30 nodes after 5 days) (`mid_graph_re_engagement_dispatcher`).
- Spaced Repetition Nudge Dispatcher: Nudges users with due SM-2 reviews (`spaced_repetition_nudge_dispatcher`).
- Weekly Mind Map Dispatcher: Generates and sends weekly mind map visual render to Telegram chat (`weekly_mind_map_dispatcher`).
- Monthly Memory Rhythm Scanner: Analyzes monthly memory accumulation rhythm (`monthly_memory_rhythm_scanner`).
- Near-Miss Calibration: Calibrates near-miss quiz options (`near_miss_calibration`).
- Save Rhythm Scanner: Detects saving habit spikes and lulls (`save_rhythm_scanner`).
- Recall Moment Dispatcher: Spontaneous "Recall Moment" memory surfacing (`recall_moment_dispatcher`).
- Tag Portraits Generator: Generates tag portraits and conceptual cluster briefs (`tag_portraits_generator`).
- Daily Pulse Updater: Computes daily pulse score, streak updates, and mind portrait radar metrics (`daily_pulse_updater`).

FRONTEND & TELEGRAM RECALL EVOLUTION FEATURES (MANDATORY IN ALL PROMPTS)
- Interactive RAG Citations: Clicking citation badges ([1], [2]) in ChatDrawer.jsx automatically switches to Map (/map), smoothly pans and zooms camera transform to center cited node at scale k = 1.35, selects the node, highlights connecting edge lines, and animates a 3-second gold flare ring.
- Passive Context Ingestion: Worker helper `compute_passive_context(user_id, source_type, conn)` computes local time_of_day, day_of_week, prior_cluster_activity_24h, session_gap_hours, and input_method, injecting metadata into DB and INSIGHT_SYSTEM_PROMPT.
- Day 1-5 Onboarding State Machine & Re-Engagement: Manages `onboarding_day` and `onboarding_last_sent`. Day 0 (2h post-save: inline preference buttons "was this for you?"), Day 1 (Next morning 8 AM: "Still thinking about X?"), Day 2 (New-node fishing prompt). Includes 5-day silent user re-engagement cron scanner and developer `/reset_onboarding` command.
- Location-Based Timezone Auto-Detection: Telegram reply keyboard requests location (`request_location=True`), approximates timezone offset from longitude (`round(lon / 15.0 * 2) / 2`), updates `users.timezone_offset`, removes keyboard (`remove_keyboard=True`), and outputs confirmation.
- Telegram Friend Fast-Track (`/match`): `/match` command generates referral link (`https://t.me/RecallBot?start=match_{user_id}`), runs 5-question thought-compatibility game, calculates tag synergy score, and creates bridge in `cognitive_bridges`.
- Floating PWA Install Banner: Dark glassmorphic banner (`PWAInstallBanner.jsx`) with gold 'R' monogram logo, install trigger, and session dismissal.
- Bridges Feature Status: Bridges room is hidden in Sidebar navigation while Branching POC is in development; all bridge test modules carry explicit skip markers (`pytestmark = pytest.mark.skip` / `describe.skip`).
```

---

# PHASE 10: AUTOMATED TESTING SUITE
---

## PROMPT 075 — Backend Test Suite: Full Coverage

**Skills:** `python-testing-patterns` · `testing-patterns` · `unit-testing-test-generate`

```
Write and maintain the complete Pytest backend test suite covering all critical paths, multi-tier AI cascade fallbacks, passive context ingestion, onboarding state machine, Telegram location auto-detection, OKF knowledge synthesis, Pulse analytics, all 24+ background scheduler jobs, and Telegram webhook handlers.

Create / update the following test modules under `backend/tests/`:

1. `tests/test_ai_cascade.py` & `tests/test_ai_cascade_extra.py`:
   - `test_ai_cascade_tier_fallback()`: Test Groq Llama 3 70B -> Gemini 1.5 Pro -> Modal GPU fallback flow.
   - `test_variant_templates()`: Test markdown outputs for Academic (Variant A with LaTeX \(x^2\)), Business (Variant B), Tech Docs (Variant C with ```python code), Legal (Variant D), Creative (Variant E), Social Video (Variant F).
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

---

## PROMPT 076 — Frontend Test Suite: Vitest

**Skills:** `javascript-testing-patterns` · `react-best-practices`

```
Write and maintain the complete Vitest component, hook, and page test suite for the Recall Observatory frontend application.

Target Test Files (frontend/src/tests/):
1. `App.test.jsx` & `Sidebar.test.jsx`:
   - Navigation rail rendering: Archive, Map, Drill, Settings, Profile.
   - Verifies active room highlighting, monogram badge, liquid amber droplet effect, and sound toggle.
   - Asserts `Bridges` item is hidden from sidebar rail during Branching POC (`hidden: true`).

2. `ChatDrawer.test.jsx`:
   - Interactive RAG Citations: Tests AI Assistant response rendering numbered citation badges (`[1]`, `[2]`).
   - Citation Click Handling: Asserts clicking citation badge `[1]` switches room to `/map`, pans/zooms camera transform to center cited node at scale $k = 1.35$, selects node, highlights connection lines, and triggers a 3-second gold flare ring.

3. `PWAInstallBanner.test.jsx`:
   - Floating PWA Banner: Dark glassmorphic banner rendering with gold 'R' monogram logo, install button trigger, and close button dismissal.

4. `Archive.test.jsx` & `ArchiveCard.test.jsx`:
   - 3D Glass Cylinder Archive View (`ArchiveCylinder.jsx`, `ArchiveCard.jsx`): Cylinder rotation, card selection, tag pill filtering, modal inspection.

5. `Map.test.jsx`, `MapCanvas.test.jsx`, `GraphControls.test.jsx`, `NodeHoverCard.test.jsx`:
   - 3D Constellation Sky Mind Map (`NebulaCanvas.jsx`, `Graph3DScene.jsx`, `GraphNode3D.jsx`, `GraphEdge3D.jsx`): R3F / Three.js canvas fallback, color-coded glowing star nodes per source_type (Blue: Link, Purple: Voice, Emerald: Image, Crimson: PDF, Amber: Text), 60 FPS flowing edge light particles, orbiting micro-particles around hot/review nodes at radius $1.7\times - 2.2\times$, physics tracking (`useMouseVelocity`, `useScrollVelocity`).

6. `SearchOverlay.test.jsx` & `KeyboardShortcuts.test.jsx`:
   - Command+K / Ctrl+K Global Terminal Finder: Live 300ms debounced search, tag grouping, hotkey listener mounting/unmounting.

7. `AudioEngine.test.jsx`:
   - Web Audio API Synth System: Synthesizer initialization, retro sci-fi sound triggers (click, transition, drill success, modal open/close), mute state persistence.

8. `Drill.test.jsx`, `DrillProgress.test.jsx`, `DrillSummary.test.jsx`:
   - Active Recall Spaced Repetition UI: Flashcard stack navigation, SuperMemo SM-2 answer button scoring (Again, Hard, Good, Easy), progress bar, summary metrics.

9. `Profile.test.jsx`, `StreakBadge.test.jsx`, `StreakPanel.test.jsx`, `QuizStatsPanel.test.jsx`:
   - Profile & Pulse UI: Mind portrait radar chart, cognitive mind type badge, streak counter, quiz performance statistics.

10. `CustomCursor.test.jsx`, `GlitchText.test.jsx`, `RoomTransition.test.jsx`, `SplashScreen.jsx`:
    - Cyber-Noir UI Micro-Animations: Custom magnetic cursor, boot sequence splash screen, glitch text rendering, sound-synced room transitions.

11. `ExtensionPopup.test.jsx`, `ExtensionOptions.test.jsx`, `ExtensionServiceWorker.test.js`:
    - Chrome Extension Manifest v3: Popup web clipper, options sync, JWT token sync.

12. `Bridges.test.jsx`:
    - Top-level skip: `describe.skip('Bridges Page Component', () => { ... })`.

Execution Rules:
- Environment: `@testing-library/react` with `jsdom`.
- Mocks: Mock Web Audio API (`AudioContext`, `OscillatorNode`, `GainNode`) and HTMLCanvasElement / WebGLContext for Three.js.
- Mock fetch / axios for all API interactions.

Gate Check:
[ ] 83 Vitest tests pass with zero warnings
[ ] ChatDrawer citation badge click verified transitioning to Map and triggering camera pan + gold flare ring
[ ] PWAInstallBanner renders floating glassmorphic card with install/close handlers
[ ] Command+K SearchOverlay opens on hotkey and debounces inputs correctly
[ ] Three.js canvas fallback renders gracefully in test DOM environment
[ ] Chrome extension popup and background worker tests pass
[ ] Bridges component tests skipped cleanly
```

---

## PROMPT 077 — Load Testing with k6

**Skills:** `k6-load-testing`

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

---

## PROMPT 078 — Integration Test: Full Item Save Flow

**Skills:** `python-testing-patterns` · `testing-patterns` · `webapp-testing`

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

---

## PROMPT 079 — Security Penetration Tests: IDOR + Injection

**Skills:** `idor-testing` · `sql-injection-testing` · `web-security-testing`

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

---

## PROMPT 080 — Performance Profiling: Vector Search Benchmarks

**Skills:** `performance-profiling` · `postgres-best-practices` · `web-performance-optimization`

```
Benchmark database search performance and 3D Observatory visual rendering to verify all target metrics.

Test 1 — Vector Search Latency Target (< 10 ms):
  Seed database with 1,000 items containing 1536-dimensional vector embeddings.
  Execute 100 benchmark vector similarity queries using `EXPLAIN ANALYZE SELECT id, 1 - (embedding <=> %s) AS score FROM items ORDER BY embedding <=> %s LIMIT 10;`.
  Assert: Median execution time < 10 ms.
  Assert: EXPLAIN ANALYZE confirms usage of `idx_items_embedding` HNSW cosine index (`m=16, ef_construction=64`).

Test 2 — GIN Trigram Text Search Latency Target (< 5 ms):
  Execute 100 benchmark text search queries using `EXPLAIN ANALYZE SELECT id FROM items WHERE summary % %s ORDER BY similarity(summary, %s) DESC LIMIT 20;`.
  Assert: Median execution time < 5 ms.
  Assert: EXPLAIN ANALYZE confirms usage of `idx_items_text_gin` GIN trigram index on summary column ONLY.

Test 3 — 3D Observatory Canvas Frame Rate (60 FPS Target):
  Using `PerfContext.jsx` and `useFPSMonitor.js` in frontend benchmarks, simulate 500 active knowledge nodes in `NebulaCanvas.jsx` and `ArchiveCylinder.jsx` with active flowing edge particles and orbiting review particles.
  Assert: Average frame render duration <= 16.67 ms (60 FPS target).

Rules:
- Save benchmark report to `docs/PERFORMANCE_BENCHMARKS.md`.
- Never run benchmark seeding against production databases.

Gate Check:
[ ] Vector search median latency < 10 ms verified with HNSW index scan
[ ] GIN trigram text search median latency < 5 ms verified
[ ] 3D Canvas 500-node simulation maintains 60 FPS target
[ ] Performance report written to docs/PERFORMANCE_BENCHMARKS.md
```

---

## PROMPT 081 — End-to-End Test: Auth Flows

**Skills:** `webapp-testing` · `testing-patterns`

```
Create automated Playwright E2E tests validating user authentication, session persistence, and logout workflows across desktop and mobile viewports.

Create `e2e/auth_flows.spec.js`:
```javascript
import { test, expect } from '@playwright/test';

test.describe('Authentication & Session Persistence', () => {
  test('TWA automatic auth transitions to 3D Observatory', async ({ page }) => {
    // Navigate with simulated initData hash
    await page.goto('/#tgWebAppStartParam=test_session');
    await expect(page.locator('.sidebar-rail')).toBeVisible();
    await expect(page).toHaveURL(/.*archive/);
  });

  test('Expired JWT redirects to login and clears cookie', async ({ page, context }) => {
    await context.addCookies([{
      name: 'recall_session',
      value: 'expired_token',
      domain: 'localhost',
      path: '/',
      expires: Date.now() / 1000 - 3600
    }]);

    await page.goto('/map');
    await expect(page).toHaveURL(/.*login/);
  });
});
```

Test Scenarios:
1. Telegram TWA Automatic Authentication.
2. Telegram Widget Login (Desktop Web).
3. Expired Session Handling.
4. User Logout.

Rules:
- Playwright tests run against isolated dev server instances.
- Must test both desktop viewport and mobile Telegram TWA viewport sizes.

Gate Check:
[ ] TWA HMAC auth flow succeeds automatically
[ ] Expired session triggers clean redirect and cookie deletion
[ ] Logout revokes session cookie and clears local state
[ ] All Playwright auth scenarios pass on Chromium and Mobile Safari viewports
```

---

## PROMPT 082 — Rate Limit Testing: Redis Pipeline Atomicity

**Skills:** `python-testing-patterns` · `async-python-patterns`

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

---

## PROMPT 083 — Image OCR Quality + Preprocessing

**Skills:** `python-pro` · `image-processing`

```
Enhance image ingestion quality using Pillow image preprocessing prior to Tesseract OCR and Gemini visual captioning fallbacks.

Pipeline (`backend/services/ocr_service.py`):
```python
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
import io

def preprocess_and_ocr_image(image_bytes: bytes) -> dict:
    image = Image.open(io.BytesIO(image_bytes))
    
    # 1. Convert to grayscale & enhance contrast
    image = image.convert('L')
    image = ImageEnhance.Contrast(image).enhance(2.0)
    image = image.filter(ImageFilter.SHARPEN)
    
    # 2. Resize if width < 800px
    if image.width < 800:
        ratio = 1200.0 / image.width
        image = image.resize((1200, int(image.height * ratio)), Image.Resampling.LANCZOS)
        
    # 3. Adaptive binarization
    image = image.point(lambda p: 0 if p < 128 else 255, '1')
    
    # 4. Tesseract OCR with confidence filtering (>60%)
    data = pytesseract.image_to_data(image, lang='eng+hin+fra+deu', output_type=pytesseract.Output.DICT)
    high_conf_words = [data['text'][i] for i in range(len(data['text'])) if int(data['conf'][i]) >= 60 and data['text'][i].strip()]
    
    # 5. Fallback trigger check
    if len(high_conf_words) < 10:
        return {"ocr_text": None, "trigger_gemini_fallback": True}
        
    return {"ocr_text": " ".join(high_conf_words), "trigger_gemini_fallback": False}
```

Rules:
- All image manipulations MUST execute in memory via `io.BytesIO` (zero temporary file writes to disk).
- Enforce a strict 30-second processing timeout per image.

Gate Check:
[ ] Preprocessed images produce higher OCR text extraction accuracy
[ ] Low-confidence images (< 10 words) cleanly trigger Gemini visual fallback
[ ] Embedded QR codes extracted and routed as URL ingestion items
[ ] In-memory processing verified (no temp files left on disk)
```

---

## PROMPT 084 — Security Scanning: SAST + Dependency Audit

**Skills:** `security-scanning-security-sast` · `security-scanning-security-hardening` · `security`

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

---

## PROMPT 085 — Performance Testing: Frontend Bundle Optimisation

**Skills:** `web-performance-optimization` · `react-component-performance`

```
Optimize React Vite frontend production bundle for rapid initial load, smooth 3D Observatory rendering, and optimal memory management.

Configure `frontend/vite.config.js`:
```javascript
export default defineConfig({
  plugins: [react()],
  build: {
    target: 'esnext',
    minify: 'esbuild',
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/react') || id.includes('node_modules/react-dom')) {
            return 'vendor-react';
          }
          if (id.includes('node_modules/three') || id.includes('node_modules/@react-three')) {
            return 'vendor-three';
          }
          if (id.includes('node_modules/lucide-react') || id.includes('node_modules/canvas-confetti')) {
            return 'vendor-utils';
          }
        },
      },
    },
  },
});
```

Optimization Tasks:
1. Dynamic Code Splitting & Dynamic Imports (`Map.jsx`, `Archive.jsx`, `Drill.jsx`, `Settings.jsx`, `Profile.jsx`).
2. Suspense Skeletons (`SplashScreen.jsx`).
3. Target Metrics: Main entry bundle < 200 KB gzipped.

Rules:
- Suspense fallbacks must display retro cybernetic skeletons/loading screens, avoiding blank flashes.
- CSS styling must remain in Vanilla CSS (`index.css`, `theme.css`).

Gate Check:
[ ] Gzipped main entry bundle size < 200 KB
[ ] Three.js dynamic chunk loaded only when navigating to Observatory 3D view
[ ] Production Lighthouse performance score >= 90
[ ] Smooth Suspense fallback loading experience
```

---

## PROMPT 086 — Smoke Test Script (Production Verification)

**Skills:** `python-pro` · `testing-patterns`

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

---

# PHASE 11: DEPLOYMENT, SECURITY & OBSERVABILITY
---

## PROMPT 087 — Security Audit Pass

**Skills:** `security-hardening` · `security`

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

---

## PROMPT 088 — Pre-Deployment Checklist Execution

**Skills:** `deployment-checklist` · `devops`

```
Execute pre-deployment validation to confirm environment configuration, database migrations, CORS policies, and external service credentials.

Checklist Verification:
1. Environment Variable Audit (20 mandatory variables in `backend/.env.local` / production settings):
   - `DATABASE_URL` (Neon production cluster)
   - `UPSTASH_REDIS_REST_URL` & `UPSTASH_REDIS_REST_TOKEN`
   - `TELEGRAM_BOT_TOKEN`
   - `FERNET_KEY` (32-byte base64 string)
   - `JWT_SECRET` (64-character hex string)
   - `COBALT_API_URL`
   - `WEBSITE_URL` (Production Vercel domain)
2. Database Schema & Migration Verification:
   - Execute `python -m backend.db.verify` to confirm all 8 tables, `vector` and `pg_trgm` extensions, HNSW cosine indices, and monthly item partitions exist.
3. CORS Policy Lockdown:
   - Ensure `allow_origins` in `main.py` is restricted explicitly to `[settings.WEBSITE_URL]` (no wildcard `*`).
4. Build Pre-compilation:
   - Verify frontend compiles with 0 errors (`npm run build`).

Rules:
- Production deployment MUST fail fast on application startup if any required environment variable is absent or malformed.

Gate Check:
[ ] All 20 environment variables validated
[ ] Database schema and HNSW indices verified via `verify.py`
[ ] CORS whitelist confirmed restricted to production domain
[ ] Frontend build compiles with zero errors
```

---

## PROMPT 089 — GitHub Actions CI Pipeline

**Skills:** `ci-cd-github-actions` · `devops`

```
Create `.github/workflows/ci.yml` to automate testing, security scanning, and build validation on every push and pull request.

Create `.github/workflows/ci.yml`:
```yaml
name: Recall Continuous Integration

on:
  push:
    branches: [ main, dev ]
  pull_request:
    branches: [ main ]

jobs:
  backend-quality-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python 3.11
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install -r backend/requirements.txt pytest pytest-cov bandit
      - name: Run Pytest Suite (339 tests)
        run: pytest -v --cov=backend
      - name: Run Bandit SAST Scan
        run: bandit -r backend/ -ll

  frontend-quality-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Node.js 20
        uses: actions/setup-node@v3
        with:
          node-version: '20'
      - name: Install frontend dependencies
        run: cd frontend && npm ci
      - name: Run Vitest Suite (83 tests)
        run: cd frontend && npm run test
      - name: Production Build Check
        run: cd frontend && npm run build
```

Rules:
- Pull requests CANNOT be merged unless all jobs in the CI pipeline pass with status 0.
- All test runs in CI must execute completely offline using mock fixtures.

Gate Check:
[ ] `.github/workflows/ci.yml` created and validated
[ ] Automated Pytest and Vitest execution in CI
[ ] Bandit SAST scan integrated into CI workflow
[ ] Build step verifies bundle compilation
```

---

## PROMPT 090 — Production Go-Live Sequence

**Skills:** `deployment-production` · `devops`

```
Execute the production go-live sequence deploying the FastAPI backend to Render and the React SPA frontend to Vercel.

Deployment Sequence:
1. Render Backend Deployment:
   - Deploy FastAPI application from `main:app`.
   - Set environment variables in Render Dashboard matching `ENV_CONFIG.md`.
   - Configure health check path: `GET /health`.
   - Set start command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT --workers 4`.
2. Vercel Frontend Deployment:
   - Connect GitHub repository to Vercel.
   - Set build command: `npm run build`.
   - Set output directory: `dist`.
   - Set environment variable: `VITE_API_URL=https://recall-api.onrender.com`.
3. Post-Deployment Verification:
   - Execute `smoke_test.py` against live production URLs.
   - Verify HTTPS SSL certificates active on both frontend and backend domains.

Rules:
- Zero downtime deployment strategy — Render & Vercel handle rolling updates.
- Verify CORS allowed origins match Vercel production domain immediately after deploy.

Gate Check:
[ ] Backend active on Render with `/health` returning 200 OK
[ ] Frontend active on Vercel with 3D Observatory loading smoothly
[ ] SSL certificates valid on all domains
[ ] Production smoke test script completes successfully
```

---

## PROMPT 091 — Telegram TWA Registration

**Skills:** `telegram-bot-api` · `twa-integration`

```
Register and configure the Telegram Web App (TWA) interface via Telegram BotFather.

Registration Steps:
1. BotFather Command Configuration:
   - Open conversation with `@BotFather`.
   - Execute `/newapp` or `/setappurl`.
   - Select targeted bot (`@RecallBrainBot`).
   - Set Web App URL: `https://recall.vercel.app` (or production frontend URL).
   - Set Web App short name: `recall`.
2. Menu Button Binding:
   - Execute `/setmenubutton` in BotFather.
   - Select bot and set menu button to launch Web App directly (`https://recall.vercel.app`).
   - Button text: `"Open Recall"`.
3. TWA Viewport & Theme Integration:
   - Verify `window.Telegram.WebApp.ready()` and `window.Telegram.WebApp.expand()` execute on boot in `App.jsx`.
   - Sync background theme colors with Telegram viewport parameters (`header_color`, `bg_color`).

Rules:
- TWA HMAC verification MUST validate all initData requests entering `/api/*`.

Gate Check:
[ ] Bot menu button opens Recall TWA inside Telegram client
[ ] Viewport expands automatically to full screen on open
[ ] TWA initData HMAC authentication verified against bot token
```

---

## PROMPT 092 — Monitoring & Observability Setup

**Skills:** `monitoring-logging` · `devops`

```
Establish application monitoring, error reporting, and operational health checks across backend services.

Implementation Steps:
1. Health Check Endpoint (`GET /health`):
   - Returns JSON: `{"status": "ok", "timestamp": "ISO_UTC", "version": "0.1.0"}`.
   - Responds in < 5 ms (no database or external network overhead).
2. Sentry Error Tracking Integration:
   - Initialize Sentry SDK in `main.py` and `App.jsx`.
   - Configure environment tag (`production` / `staging`).
   - Mask sensitive fields (`raw_text`, `auth_date`, `hash`, `token`, `authorization`).
3. Render / Upstash Metric Alerts:
   - Configure alert triggers for CPU usage > 85%, memory > 80%, or HTTP 5xx rate > 1%.

Rules:
- Health check endpoint must remain public and unauthenticated for uptime monitoring tools.
- Never capture raw decrypted user notes in error reports or stack traces.

Gate Check:
[ ] GET /health returns 200 OK in < 5 ms
[ ] Sentry error reporting initialized with sensitive field masking
[ ] Operational uptime monitor configured against backend /health
```

---

## PROMPT 093 — Monitoring: Structured Logging + Alerts

**Skills:** `monitoring-logging` · `python-pro`

```
Implement structured JSON logging and request tracing across FastAPI endpoints and background worker tasks.

Implementation Details:
1. Structured JSON Logger (`backend/config.py` / logger setup):
   - Configure `python-json-logger` to format logs as single-line JSON.
   - Include standard fields: `timestamp`, `level`, `logger_name`, `request_id`, `user_id`, `path`, `status_code`, `latency_ms`.
2. Request ID Middleware (`backend/middleware/request_tracing.py`):
   - Generate unique `X-Request-ID` UUID for every incoming HTTP request.
   - Attach `request_id` to logger context and response headers.
3. Background Worker Context Tracing:
   - Pass `request_id` into background ingestion tasks in `worker.py`.
   - Log task lifecycle events: `task_enqueued`, `ingestion_started`, `ai_cascade_tier_changed`, `task_completed`, `task_failed`.

Rules:
- Strictly prohibit logging `raw_text`, `summary` contents, or encryption keys.

Gate Check:
[ ] All application logs formatted as single-line JSON
[ ] Request ID header `X-Request-ID` present on all API responses
[ ] Worker ingestion lifecycle events logged with request context
[ ] Zero sensitive user note data present in log outputs
```

---

## PROMPT 094 — Database Backup Strategy

**Skills:** `neon-postgres` · `database-backup`

```
Configure automated database backup, point-in-time recovery (PITR), and disaster recovery routines for Neon PostgreSQL.

Implementation Details:
1. Neon Automated Point-in-Time Recovery (PITR):
   - Enable Neon daily automatic WAL snapshots with 7-day retention window.
2. Automated Logical Backups (`scripts/db_backup.py`):
   - Create daily `pg_dump` script executing schema + data export (excluding non-essential temp logs).
   - Compress dump using gzip (`recall_backup_YYYYMMDD.sql.gz`).
   - Upload encrypted backup to isolated cloud storage bucket.
3. Disaster Recovery Verification Script (`scripts/verify_backup_restore.py`):
   - Download latest backup dump.
   - Restore into temporary Neon test branch.
   - Verify table counts, HNSW indices, and row counts match live dataset.

Rules:
- Backup dumps must be encrypted at rest before storing in secondary cloud storage.

Gate Check:
[ ] Neon automated PITR enabled and confirmed active
[ ] Daily logical backup script `db_backup.py` executes cleanly
[ ] Backup restoration test restores schema and data into isolated branch without errors
```

---

## PROMPT 095 — Rollback Procedure

**Skills:** `devops` · `deployment-rollback`

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

---

## PROMPT 096 — OpenTelemetry Tracing (Optional Enhancement)

**Skills:** `opentelemetry` · `observability`

```
Instrument FastAPI application and background workers with OpenTelemetry distributed tracing.

Implementation Details:
1. FastAPI Instrumentation:
   - Install `opentelemetry-instrumentation-fastapi`.
   - Instrument FastAPI `app` in `main.py`.
2. Distributed Trace Propagation:
   - Inject `traceparent` headers into background queue tasks (`worker.py`).
   - Create custom spans around AI Cascade model calls (`Groq`, `Gemini`, `Modal GPU`).
3. OTLP Exporter Setup:
   - Configure OpenTelemetry Collector / Jaeger / Honeycomb OTLP gRPC exporter.
   - Respect `OTEL_SDK_DISABLED=true` flag in local dev to prevent unwanted telemetry egress.

Rules:
- Tracing MUST NOT introduce more than 2 ms of overhead per HTTP request.

Gate Check:
[ ] Distributed trace spans generated for HTTP requests and background AI tasks
[ ] AI cascade tier execution duration visible in trace timeline
[ ] Local dev environment bypasses exporter when OTEL_SDK_DISABLED=true
```

---

## PROMPT 097 — Final Documentation Pass

**Skills:** `technical-documentation` · `api-documentation`

```
Perform a final documentation synchronization across all project specs, architecture diagrams, API schemas, and verification guides.

Documentation Audit:
1. `docs/BACKEND_SCHEMA.md`: Ensure all database tables, columns, vector dimensions (1536), and indices match production schema exactly.
2. `docs/AI_CASCADE.md`: Update AI model tier hierarchy (Groq Llama 3 70B → Gemini 1.5 Pro → Modal GPU fallback) and brand spelling normalization logic.
3. `docs/UI_UX_BRIEF.md`: Document Three.js / R3F 3D Observatory Starry Sky Mind Map, Archive Glass Cylinder View, AudioEngine synth system, and Command+K Global Finder.
4. `docs/MANUAL_VERIFICATION.md` & `docs/MANUAL_VERIFICATION_RECALL_EVOLUTION.md`: Update manual UI verification steps reflecting Interactive RAG Citations (Map camera transform scale k=1.35 + gold flare ring), Telegram `/match` 5-question game, location timezone auto-detection, PWA install banner, and 3D visual controls.

Rules:
- All documentation files must use GitHub-flavored markdown with clean file link syntax.

Gate Check:
[ ] All docs in `docs/` reflect the 100% completed state of Recall
[ ] OpenAPI spec (`docs/openapi.json`) matches live FastAPI endpoint schemas
[ ] UI/UX brief updated with 3D Observatory R3F specifications
```

---

## PROMPT 098 — README.md for GitHub

**Skills:** `readme-documentation` · `open-source`

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

---

## PROMPT 099 — Partition Manager CLI Script

**Skills:** `python-pro` · `postgres-best-practices`

```
Create `backend/scripts/partition_manager.py` — an automated CLI utility for managing PostgreSQL range partitions on the `items` table.

Create `backend/scripts/partition_manager.py`:
```python
import argparse
import asyncio
from datetime import datetime
from dateutil.relativedelta import relativedelta
from backend.db.connection import get_db

async def create_partitions(months: int, dry_run: bool):
    now = datetime.utcnow()
    async with get_db() as conn:
        async with conn.cursor() as cur:
            for i in range(months):
                target = now + relativedelta(months=i)
                year_str = target.strftime("%Y")
                month_str = target.strftime("%m")
                start_date = f"{year_str}-{month_str}-01"
                
                next_month = target + relativedelta(months=1)
                end_date = f"{next_month.strftime('%Y')}-{next_month.strftime('%m')}-01"
                
                table_name = f"items_y{year_str}m{month_str}"
                ddl = f"CREATE TABLE IF NOT EXISTS {table_name} PARTITION OF items FOR VALUES FROM ('{start_date}') TO ('{end_date}');"
                
                print(f"[+] DDL: {ddl}")
                if not dry_run:
                    await cur.execute(ddl)
                    print(f"[✓] Created partition {table_name}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PostgreSQL Partition Manager CLI")
    parser.add_argument("--action", choices=["create", "list", "detach"], required=True)
    parser.add_argument("--months", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    if args.action == "create":
        asyncio.run(create_partitions(args.months, args.dry_run))
```

Rules:
- CLI script must require confirmation prompt before executing DDL alterations unless `--yes` flag is passed.
- All DDL queries must use parameterised/validated identifiers preventing SQL injection.

Gate Check:
[ ] `--action create` creates correct monthly partition tables and indices
[ ] `--action list` outputs current partition status and row counts
[ ] Dry-run mode (`--dry-run`) displays SQL statements without executing
```

---

## PROMPT 100 — Final Acceptance: 0 → 100% Gate

**Skills:** `quality-assurance` · `acceptance-testing`

```
Execute the final end-to-end acceptance review verifying Recall is 100% complete, fully tested, hardened, and ready for production operations.

Final Acceptance Gate Checks:
1. Test Suite Pass (100% Green):
   - Pytest Backend Test Suite: 339 passed (0 failed).
   - Vitest Frontend Test Suite: 83 passed (0 failed).
   - Bridges test modules cleanly skipped for Branching POC.
2. Security Hardening Pass:
   - 0 HIGH findings in Bandit SAST.
   - 0 CRITICAL/HIGH findings in pip-audit and npm audit.
   - 0 plaintext secrets in repo.
   - Fernet encryption verified for sensitive fields (`gAAAAA...`).
3. Performance Verification:
   - Vector search median < 10 ms (HNSW cosine index).
   - Text search median < 5 ms (GIN trigram index).
   - Telegram Webhook ACK latency < 50 ms.
   - 3D Observatory Canvas renders at 60 FPS target.
4. Product Readiness:
   - 3D Observatory Mind Map & Archive Cylinder fully operational.
   - Interactive RAG Citations trigger Map camera pan/zoom (k=1.35) and gold flare ring.
   - Telegram Bot & TWA integration validated (with location timezone auto-detection & `/match` game).
   - Production Smoke Test (`smoke_test.py`) passes cleanly.

Output: Record final acceptance sign-off in `docs/FINAL_ACCEPTANCE_REPORT.md`.

Gate Check:
[ ] 339 pytest tests passing
[ ] 83 vitest tests passing
[ ] All performance targets met
[ ] Final sign-off recorded in docs/FINAL_ACCEPTANCE_REPORT.md — RECALL IS 100% COMPLETE!
```
