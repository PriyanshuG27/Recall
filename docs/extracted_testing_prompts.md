# Extracted Testing Prompts

## PROMPT 066 — Backend Test Suite: Full Coverage

**Skills:** `python-testing-patterns` · `testing-patterns` · `unit-testing-test-generate`

```
Write the complete pytest test suite for all critical paths identified in TESTING.md.

Test files to create:
- tests/test_idempotency.py    → all 4 cases from TESTING.md §1
- tests/test_cascade.py        → all 4 cases from TESTING.md §2 (plus LOCAL_MODE cases)
- tests/test_rate_limiter.py   → all 5 cases from TESTING.md §3
- tests/test_sm2.py            → all 5 cases from TESTING.md §4
- tests/test_auth_twa.py       → all 4 cases from TESTING.md §5 TWA section
- tests/test_auth_jwt.py       → all 5 cases from TESTING.md §5 JWT section
- tests/test_auth_oauth.py     → all 3 cases from TESTING.md §5 OAuth section
- tests/test_partitioning.py   → all 5 cases from TESTING.md §6

Test configuration rules (MANDATORY):
- All AI calls: mocked via pytest-mock (no real API calls ever)
- All Telegram API calls: mocked
- Redis: use fakeredis library
- Database: use pytest-postgresql or psycopg in-memory test DB
- Time: use freezegun for time-dependent tests (rate limiter, auth_date expiry, SM-2 dates)

Coverage requirements:
- src/services/encryption.py: 100% coverage
- src/services/sm2.py: 100% coverage
- src/routes/auth.py: >= 90% coverage
- src/services/rate_limiter.py: >= 90% coverage

Rules:
- Tests must run in < 30 s total (fast feedback).
- No test may make network calls (add pytest-httpretty or respx to block).
- Test names must describe the scenario: test_duplicate_update_id_returns_200_without_processing.
- Every security-critical function must have a test for the attack path (not just happy path).

Gate Check:
[ ] pytest runs all tests in < 30 s
[ ] Zero network calls made during test run (verified with respx)
[ ] test_sm2.py: all 5 cases pass with exact numeric values from TESTING.md
[ ] test_auth_twa.py: tampered hash returns 401
[ ] Coverage report shows encryption.py at 100%
```

---

---

## PROMPT 028 — Frontend Test Suite: Vitest

**Skills:** `javascript-testing-patterns` · `react-best-practices`

```
Write Vitest tests for frontend critical components.

Test files:
- src/canvas/__tests__/GraphCanvas.test.jsx
  → Renders without crash (smoke test)
  → Calls onNodeClick when node is clicked
  → requestAnimationFrame loop starts on mount, stops on unmount

- src/components/__tests__/NodePanel.test.jsx
  → Renders node title and summary
  → Escape key fires onClose
  → Renders correct @phosphor-icons icon per source_type
  → Does not render when node prop is null

- src/hooks/__tests__/useGraphSocket.test.js
  → Connects to WebSocket on mount
  → Appends new_node event to nodes state
  → Reconnects after disconnect (3 s delay)
  → Closes WebSocket on unmount

- src/pages/__tests__/Dashboard.test.jsx
  → Search input debounces 300 ms before firing API call
  → Non-matching nodes get opacity 0.1 after search

Rules:
- Use @testing-library/react for component tests.
- Mock WebSocket with jest-websocket-mock.
- Mock axios with vi.mock('axios').
- No real network calls — all API responses must be mocked.

Gate Check:
[ ] All Vitest tests pass
[ ] NodePanel tests confirm no emoji icons used for source types
[ ] useGraphSocket reconnect test passes with fake timers
[ ] Dashboard search debounce test verifies 300 ms delay
```

---

---

## PROMPT 074 — Load Testing with k6

**Skills:** `k6-load-testing`

```
Create backend/tests/load/k6_webhook.js — load test for the webhook endpoint.

Scenario:
- 50 virtual users (simulating 50 DAU sending content concurrently)
- Test duration: 60 seconds
- Each VU: POST /webhook every 3 s with a text message payload

Checks:
- Response time p95 < 200 ms
- HTTP status == 200 for all requests
- Zero 5xx responses

Threshold config:
  thresholds: {
    http_req_duration: ['p(95)<200'],
    http_req_failed: ['rate<0.01'],
  }

Also create k6_search.js:
- 20 VUs, 30 s duration
- POST /api/search every 2 s with random query
- p95 < 500 ms (vector + trigram search combined)

Rules:
- Load tests must target a staging environment, not production (comment clearly in script).
- k6 script must NOT hardcode any real credentials — use k6 environment variables.
- Webhook load test must NOT use a real bot token — use a mock payload.
- Results must be captured: k6 run --out json=results.json k6_webhook.js

Gate Check:
[ ] k6 run k6_webhook.js completes with p95 < 200 ms under 50 VU load
[ ] k6 run k6_search.js completes with p95 < 500 ms
[ ] Zero 5xx responses in both tests
[ ] Thresholds pass (k6 exits with code 0)
```

---

---

## PROMPT 075 — Integration Test: Full Item Save Flow

**Skills:** `python-testing-patterns` · `testing-patterns` · `webapp-testing`

```
Write an end-to-end integration test covering the complete item save pipeline.

Test file: backend/tests/integration/test_full_save_flow.py

Use a real (Neon test branch) or local PostgreSQL for this test.
Mock ONLY: Telegram API, Modal GPU, Groq API, Gemini API.

Scenario 1 — URL save:
  1. POST /webhook with a text message containing a URL
  2. Assert: processed_updates row created
  3. Assert: items row created with correct source_type='url'
  4. Assert: items.raw_text starts with 'gAAAA' (Fernet prefix)
  5. Assert: WS event received (new_node)
  6. Assert: Telegram mock called with ACK message

Scenario 2 — Voice note save (cascade Tier 0 → Tier 1 fallback):
  1. POST /webhook with voice file_id
  2. Mock Modal to fail (500)
  3. Mock Groq to succeed with transcript
  4. Assert: items row created with source_type='voice' and embedding
  5. Assert: dead_letter_queue has 0 rows (cascade succeeded before fallback)
  6. Assert: quiz row created for the item

Scenario 3 — Full cascade exhaustion:
  1. POST /webhook with PDF
  2. Mock ALL tiers to fail
  3. Assert: dead_letter_queue row created
  4. Assert: items row created with source_type='pdf', raw_text=NULL
  5. Assert: Telegram mock called with "Saved as bookmark" message

Rules:
- Integration tests in a separate tests/integration/ directory.
- Require DATABASE_URL env var pointing to a test DB (refuse if it contains "prod").
- Clean up all created rows after each test (use pytest fixtures with teardown).
- Entire integration test suite must complete in < 60 s.

Gate Check:
[ ] All 3 scenarios pass
[ ] Database is clean after each test (no leaked rows)
[ ] Tests refuse to run if DATABASE_URL contains "prod"
[ ] Suite completes in < 60 s
[ ] CI workflow runs integration tests on a Neon CI branch
```

---

---

## PROMPT 021 — Security Penetration Tests: IDOR + Injection

**Skills:** `idor-testing` · `sql-injection-testing` · `web-security-testing`

```
Write a security-focused test suite covering IDOR and injection scenarios.

File: backend/tests/security/test_idor.py

IDOR Tests:
  T1: User B tries GET /api/items → only sees own items (not User A's)
  T2: User B tries DELETE /api/items/{user_A_item_id} → 404
  T3: User B tries POST /api/quizzes/{user_A_quiz_id}/answer → 404
  T4: User B tries DELETE /api/reminders/{user_A_reminder_id} → 404
  T5: User B tries GET /api/graph → only sees own nodes (0 of User A's)
  T6: User B tries POST /api/drive/sync → only syncs own data

SQL Injection Tests (file: test_sql_injection.py):
  T1: POST /api/search with query="'; DROP TABLE items;--" → 200, no error, no items deleted
  T2: GET /api/items?tag="' OR '1'='1" → 200, only user's items returned
  T3: POST /webhook with text containing SQL keywords → processed safely, no injection
  T4: /auth/telegram with tampered id param containing SQL → 401, no DB error

XSS Tests (file: test_xss.py):
  T1: Item saved with title="<script>alert(1)</script>" → title returned as-is in JSON (not executed)
  T2: Search query with XSS payload → returned in JSON, not reflected as HTML
  (XSS note: since backend is JSON API + React frontend auto-escapes, XSS is largely mitigated at framework level)

Rules:
- These tests run against a test DB — never production.
- SQL injection tests verify BOTH no data change AND no 500 error.
- IDOR tests must create two real users (User A, User B) with real tokens.
- All tests must pass — any failure is a BLOCKING security issue.

Gate Check:
[ ] All IDOR tests (T1-T6) pass — no cross-user data access
[ ] SQL injection T1: items table count unchanged after injection attempt
[ ] SQL injection T2: parameterised query prevents injection
[ ] All tests run against test DB only
[ ] CI: security test suite runs on every PR
```

---

---

## PROMPT 026 — Performance Profiling: Vector Search Benchmarks

**Skills:** `performance-profiling` · `postgres-best-practices` · `k6-load-testing`

```
Benchmark and verify all performance targets from PERFORMANCE.md.

Test 1 — Vector search < 10 ms:
  Insert 1000 items with real 384-dim embeddings (use MiniLM locally).
  Run EXPLAIN ANALYZE on vector search query 100 times.
  Assert: median execution time < 10 ms.
  Assert: EXPLAIN shows "Index Scan using idx_items_embedding".

Test 2 — GIN trigram search < 5 ms:
  Same dataset.
  Run EXPLAIN ANALYZE on GIN search 100 times.
  Assert: median < 5 ms.
  Assert: EXPLAIN shows "Bitmap Index Scan on idx_items_text_gin".

Test 3 — Webhook ACK < 50 ms:
  Use k6 with single VU, measure time from request to 200 response.
  Mock all DB and Redis calls to be < 2 ms.
  Assert: p95 < 50 ms.

Test 4 — Graph API < 200 ms:
  200 items with pre-computed hubs.
  GET /api/graph timed 50 times.
  Assert: p95 < 200 ms.

Test 5 — Canvas 60 FPS:
  Use Vitest + fake requestAnimationFrame.
  Simulate 500 nodes, 60 ticks.
  Assert: each tick completes in < 16.67 ms (1000/60).

Create: backend/tests/performance/test_benchmarks.py and frontend/src/canvas/__tests__/benchmark.test.js

Rules:
- Benchmarks run with EXPLAIN ANALYZE — never on production.
- Vector search benchmark must use real HNSW index (not mock).
- Canvas benchmark: disable all async (no WS, no API calls) — pure render loop timing.
- Results saved to docs/PERFORMANCE_BENCHMARKS.md with date and results.

Gate Check:
[ ] Vector search: median < 10 ms confirmed with real HNSW index
[ ] GIN search: median < 5 ms confirmed
[ ] Webhook ACK: p95 < 50 ms in k6 test
[ ] Canvas: 500 nodes render at >= 60 FPS in benchmark
[ ] Results documented in PERFORMANCE_BENCHMARKS.md
```

---

---

## PROMPT 023 — End-to-End Test: Auth Flows

**Skills:** `webapp-testing` · `testing-patterns`

```
Write E2E tests for all three authentication flows.

Test framework: Playwright (add to frontend/ or run separately as e2e/ directory).

Setup: Launch FastAPI dev server + Vite dev server before tests.
Use a test Telegram bot token (not production).

Test 1 — Telegram Login Widget (website flow):
  1. Navigate to /login
  2. Mock Telegram Login Widget callback (since real Telegram auth requires human interaction)
     Directly call GET /auth/telegram?id=...&hash=...&auth_date=... with valid params
  3. Assert: redirect to /dashboard
  4. Assert: recall_session cookie is set (httpOnly — check via API response)
  5. Assert: GET /api/items returns 200

Test 2 — TWA flow (simulated):
  1. Direct POST to /api/items with valid TWA initData in Authorization header
  2. Assert: 200 (authenticated)
  3. Tamper with hash
  4. Assert: 401

Test 3 — Expired JWT:
  1. Set a JWT cookie with exp = 1 minute ago
  2. GET /api/items
  3. Assert: 401 response
  4. Assert: cookie is cleared in response

Test 4 — Logout:
  1. Login (valid JWT)
  2. POST /auth/logout
  3. GET /api/items
  4. Assert: 401

Rules:
- Playwright tests in e2e/ directory — separate from Vitest unit tests.
- Real HTTP calls to local dev server — no mocking in E2E tests.
- Test Telegram Login Widget hash must be computed correctly (real HMAC with test bot token).
- E2E tests must not touch production DB.

Gate Check:
[ ] Test 1: Login Widget flow creates valid session
[ ] Test 2: Tampered TWA hash returns 401
[ ] Test 3: Expired JWT returns 401 and clears cookie
[ ] Test 4: Logout prevents further API access
[ ] All 4 tests pass in CI with test bot token
```

---

---

## PROMPT 056 — Rate Limit Testing: Redis Pipeline Atomicity

**Skills:** `python-testing-patterns` · `async-python-patterns`

```
Verify the atomicity and correctness of the Redis sliding window rate limiter under concurrency.

Test file: backend/tests/test_rate_limiter_concurrency.py

Scenario 1 — Concurrent requests at limit boundary:
  Simulate 20 concurrent requests from the same chat_id using asyncio.gather.
  Assert: ALL 20 succeed (no race condition incorrectly rejects requests under limit).

Scenario 2 — Concurrent requests over limit:
  Simulate 25 concurrent requests.
  Assert: exactly 20 succeed, exactly 5 are rejected.
  Assert: no request is double-counted (race condition check).

Scenario 3 — Window expiry under load:
  Send 20 requests. Wait 61 s (mock time). Send 20 more.
  Assert: all 40 requests succeed (two separate windows).

Scenario 4 — Different users are independent:
  50 requests from chat_id_A and 50 requests from chat_id_B.
  Assert: exactly 20 from A succeed, exactly 20 from B succeed.
  Assert: A and B do not share quota.

Implementation note:
  The Upstash REST pipeline is atomic (single HTTP POST) — verify this prevents the race condition.
  Use fakeredis.aioredis for synchronous tests; for concurrency tests, use asyncio.gather with real Upstash dev instance.

Rules:
- Concurrency tests must actually run async operations concurrently (asyncio.gather).
- Never use time.sleep() for window expiry — use freezegun to advance time.
- Tests must pass consistently (not flaky) — run each 10 times in CI.

Gate Check:
[ ] Scenario 1: all 20 concurrent succeed
[ ] Scenario 2: exactly 5 rejected (no race condition accepting more/fewer)
[ ] Scenario 3: window reset allows new requests
[ ] Scenario 4: user isolation confirmed
[ ] Tests are not flaky (run 10 times: all pass)
```

---

---

---

## PROMPT 045 — Image OCR Quality + Preprocessing

**Skills:** `python-pro`

```
Improve image ingestion (PROMPT 022) with pre-processing for better OCR quality.

Image preprocessing pipeline (before Tesseract):
  Use Pillow for all preprocessing:
  1. Convert to grayscale: image.convert('L')
  2. Increase contrast: ImageEnhance.Contrast(image).enhance(2.0)
  3. Sharpen: ImageFilter.SHARPEN
  4. Resize if < 800px wide: image.resize to 1200px width (maintains aspect ratio)
  5. Binarise (black/white): image.point(lambda p: 0 if p < 128 else 255, '1')

Language detection:
  Run Tesseract with lang='eng+hin+fra+deu' (multi-language support for common languages)
  Detect dominant language from Tesseract output (pytesseract.image_to_data returns language info)

Confidence filtering:
  pytesseract.image_to_data returns per-word confidence scores.
  Filter out words with confidence < 60% before returning OCR text.
  If fewer than 10 high-confidence words remain: treat as low-quality → use Gemini captioning.

QR code / barcode detection:
  If image appears to be a QR code (pyzbar library): decode QR → save as URL item.
  Bot reply: "QR code detected → URL: {decoded_url}\nSaved ✓"

Rules:
- Preprocessing must happen in memory (no additional temp files).
- Tesseract timeout: 30 s per image — kill process if exceeded.
- Confidence threshold: 60% is not configurable — hardcoded.
- pyzbar: optional dependency (skip QR if not installed, log warning).

Gate Check:
[ ] Skewed/low-contrast image produces better OCR with preprocessing
[ ] Low confidence OCR (<10 words) falls back to Gemini captioning
[ ] QR code image → decoded URL saved as url item
[ ] Tesseract kills process after 30 s timeout
[ ] Unit test: test_image_ocr.py with mocked PIL and Tesseract
```

---

---

## PROMPT 083 — Security Scanning: SAST + Dependency Audit

**Skills:** `security-scanning-security-sast` · `security-scanning-security-hardening` · `security`

```
Run automated static analysis and produce a security scan report.

Backend SAST (bandit):
  bandit -r backend/ -ll -f json -o security_reports/bandit_report.json
  Review all HIGH and MEDIUM findings.
  Fix ALL HIGH severity issues before deployment.
  Document any accepted MEDIUM risks in security_reports/ACCEPTED_RISKS.md.

Dependency vulnerability scan:
  pip-audit --require-hashes -r backend/requirements.txt -o security_reports/pip_audit.json
  npm audit --json > security_reports/npm_audit.json
  Fix ALL critical and high severity dependency vulnerabilities.

Secrets scan:
  Use trufflescan or simple grep:
  grep -rE "(AAAB[A-Za-z0-9+/]{32,}|ghp_[A-Za-z0-9]{36}|gAAAAA[A-Za-z0-9+/]{60,})" backend/ frontend/
  Any match is a BLOCKER.

Hardening checklist:
  [ ] TLS: no HTTP allowed in any URL construction (grep for "http://" in backend/ — only localhost allowed)
  [ ] No subprocess.shell=True in any code
  [ ] No eval() or exec() calls
  [ ] No pickle.loads() on untrusted data
  [ ] All file operations: validate path is within expected directory (prevent path traversal)

Output: Create docs/SECURITY_SCAN_REPORT.md with:
  - Bandit summary (HIGH/MEDIUM/LOW counts)
  - pip-audit summary
  - npm audit summary
  - Any accepted risks with justification

Rules:
- BLOCKER issues must all be fixed before this prompt is marked complete.
- Accepted risks must have documented rationale — not just "we'll fix later".
- Security scan runs in CI (from PROMPT 086) — must pass cleanly.
- Report must be dated and versioned.

Gate Check:
[ ] bandit: 0 HIGH findings
[ ] pip-audit: 0 CRITICAL or HIGH vulnerability findings
[ ] npm audit: 0 CRITICAL or HIGH findings
[ ] Secrets scan: 0 matches
[ ] docs/SECURITY_SCAN_REPORT.md written with all counts
```

---

---

## PROMPT 094 — Performance Testing: Frontend Bundle Optimisation

**Skills:** `web-performance-optimization` · `react-component-performance`

```
Optimise the React frontend bundle for performance.

Analysis:
  npm run build -- --analyze (or use rollup-plugin-visualizer)
  Identify large chunks. Target: main bundle < 200 KB gzipped.

Optimisations:

1. Code splitting:
  Lazy-load Feed and Reminders pages:
    const Feed = React.lazy(() => import('./pages/Feed'))
    Wrap in <Suspense fallback={<FeedCardSkeleton />}>

2. D3 tree-shaking:
  Import only used D3 modules:
    import {forceSimulation, forceLink, forceManyBody, forceCenter} from 'd3-force'
  NOT: import * as d3 from 'd3'

3. @phosphor-icons: already tree-shaken by default — verify.

4. Image optimisation:
  The login page mini-canvas is pure code — no images to optimise.
  Any static images: use WebP format, max 100 KB.

5. CSS:
  Remove unused CSS custom properties (audit with devtools Coverage tab).
  Consolidate duplicate animation definitions.

Lighthouse audit targets:
  Performance: >= 90
  Accessibility: >= 95
  Best Practices: >= 95
  SEO: >= 90

Vite config optimisations:
  build.rollupOptions.output.manualChunks: split vendor (d3, react) from app code
  build.minify: 'esbuild' (default, fast)

Rules:
- Lazy-loaded routes must have matching skeleton (not blank screen) during load.
- No CSS framework added for optimisation — Vanilla CSS is already optimal.
- Lighthouse audit must be run on production build, not dev server.

Gate Check:
[ ] Main bundle < 200 KB gzipped (measure with npm run build + du)
[ ] Lighthouse Performance >= 90 on production build
[ ] Lighthouse Accessibility >= 95
[ ] Feed page is lazily loaded (Network tab shows chunk loaded on demand)
[ ] D3 imports are tree-shaken (no d3-array, d3-scale etc. if not used)
```

---

---

## PROMPT 042 — Smoke Test Script (Production Verification)

**Skills:** `python-pro` · `testing-patterns`

```
Create backend/scripts/smoke_test.py — a production smoke test run after every deploy.

Usage: python smoke_test.py --api-url https://recall-api.onrender.com --token {test_jwt}

Tests run in sequence:

T1 — Health check:
  GET /health → assert status == "ok"
  Assert response time < 200 ms

T2 — Authenticated request:
  GET /api/items with valid JWT cookie → assert 200

T3 — Search works:
  POST /api/search {"query": "test"} → assert 200, valid JSON structure

T4 — Graph loads:
  GET /api/graph → assert 200, nodes is a list

T5 — WebSocket connects:
  Connect to /ws/{jwt} → assert "connected" event within 2 s

T6 — Rate limiter active:
  POST /webhook 25 times quickly → assert at least one is rejected (200 but no task enqueued — check via T7)

T7 — DLQ accessible:
  GET /api/admin/queue with INTERNAL_API_KEY → assert queue_length is an integer

Output: JSON report with each test result and duration.
Exit code: 0 if all pass, 1 if any fail.

Rules:
- Smoke test must NOT use production bot token — use a test JWT generated with the FERNET_KEY.
- Smoke test must run against staging/production URL — not localhost.
- T6 does not require actual task processing — just verifies webhook returns 200.
- Output file: smoke_test_report_{timestamp}.json in /tmp (not committed).

Gate Check:
[ ] All 7 tests pass against production API
[ ] Script exits with code 0 on success, 1 on failure
[ ] T5: WebSocket connection within 2 s
[ ] Report JSON generated with per-test durations
[ ] Script works with --api-url parameter (not hardcoded URL)
```

---

---
