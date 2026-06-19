# TESTING — Recall

| Field | Value |
|-------|-------|
| Version | 0.1.0 |
| Date | 2026-06-19 |
| Status | Draft |

---

## Testing Philosophy

- No test is worth writing if it does not protect a real failure mode.
- Focus: idempotency, cascade failover, auth correctness, SM-2 math, partition boundaries.
- Framework: pytest (backend), Vitest (frontend).
- All tests must run with no external API calls (mock AI tiers, mock Telegram API).

---

## 1. Webhook Idempotency

**What to verify**: The same Telegram update_id, delivered twice, produces exactly one items row.

**Test cases**:

| Test | Setup | Expected |
|------|-------|----------|
| First delivery | Fresh DB; POST /webhook with update_id="111" | items row created; processed_updates row created |
| Duplicate delivery | Same update_id="111" | No new items row; 200 returned; processed_updates unchanged |
| Different update_id | update_id="112" | Second items row created independently |
| Concurrent duplicates | Two simultaneous requests with update_id="113" | Exactly one items row due to PK constraint |

**Method**: Use pytest with an in-memory test DB (SQLite or Neon branch). Mock Telegram sendMessage.

---

## 2. AI Cascade Failover

**What to verify**: When each tier fails, the next tier is attempted; Tier 4 always succeeds.

**Test cases**:

| Test | Mocked Failure | Expected |
|------|---------------|----------|
| Tier 0 fails | Modal returns 500 | Tier 1 (Groq) is called |
| Tiers 0-1 fail | Modal + Groq return 500 | Tier 2 (Gemini) is called |
| Tiers 0-2 fail | All three fail | Tier 3 bookmark saved |
| All cascade tiers fail | All return 500 | dead_letter_queue row inserted; user notified |
| COMPUTE_PROVIDER=groq | Override set | Tier 1 called directly; Tier 0 skipped |

**Method**: Dependency-inject AI client wrappers; mock each to raise specific exceptions.

---

## 3. Rate Limiter

**What to verify**: 20 requests within 60 s succeed; the 21st within the window returns 429.

**Test cases**:

| Test | Setup | Expected |
|------|-------|----------|
| Under limit | 20 requests in 60 s | All 200 |
| At limit | 20th request | 200 |
| Over limit | 21st request in same window | 429 + Retry-After header present |
| Window expiry | 21st request after 61 s | 200 (window has reset) |
| Different users | 20 req from user A + 20 req from user B | All 200 (per-user isolation) |

**Method**: Mock Redis; use fakeredis or Upstash local emulator. Manipulate time via freezegun.

---

## 4. SM-2 Algorithm

**What to verify**: Correct answer updates ease_factor and interval_days per SM-2 spec.

SM-2 reference:
- Quality 0-2 (wrong): interval = 1; ease_factor -= 0.8 (min 1.3)
- Quality 3 (correct, hard): interval unchanged; ease_factor unchanged
- Quality 4 (correct, ok): interval = interval * ease_factor (rounded)
- Quality 5 (correct, easy): interval = interval * ease_factor (rounded); ease_factor += 0.1

**Test cases**:

| Test | Input | Expected ease_factor | Expected interval_days |
|------|-------|---------------------|----------------------|
| Wrong answer (q=1) | ef=2.5, interval=1 | 1.7 | 1 |
| Correct easy (q=5) | ef=2.5, interval=1 | 2.6 | 3 |
| Correct ok (q=4) | ef=2.5, interval=3 | 2.5 | 8 |
| Wrong after streak | ef=2.5, interval=8 | 1.7 | 1 |
| ease_factor floor | ef=1.3, q=1 | 1.3 (clamped) | 1 |

**Method**: Unit test the SM-2 function in isolation; no DB needed.

---

## 5. Auth Flows

### TWA HMAC Verification

| Test | Setup | Expected |
|------|-------|----------|
| Valid initData | Correct HMAC, auth_date within 1h | 200, user context attached |
| Invalid hash | Tampered initData | 401 |
| Expired auth_date | auth_date 2 hours ago | 401 |
| Missing hash field | initData without hash key | 401 |

### Login Widget JWT

| Test | Setup | Expected |
|------|-------|----------|
| Valid Telegram hash | Correct SHA256 hash | JWT issued; httpOnly cookie set |
| Invalid hash | Tampered params | 401 |
| auth_date > 1 day old | Stale widget callback | 401 |
| JWT on protected route | Valid cookie | 200 |
| Expired JWT | exp in past | 401, cookie cleared |

### Google OAuth CSRF Protection

| Test | Setup | Expected |
|------|-------|----------|
| Valid state JWT | Correct state token | Callback proceeds |
| Tampered state | Modified state JWT | 401 |
| Expired state | state.exp > 10 min ago | 401 |

---

## 6. DB Partitioning

**What to verify**: Items are routed to correct partitions; queries prune non-relevant partitions.

**Test cases**:

| Test | Setup | Expected |
|------|-------|----------|
| Insert June item | created_at = '2026-06-15' | Row in items_y2026m06 |
| Insert July item | created_at = '2026-07-15' | Row in items_y2026m07 |
| Cross-partition query | SELECT all items | UNION across both partitions |
| Pruned query | WHERE created_at BETWEEN '2026-06-01' AND '2026-07-01' | EXPLAIN shows only items_y2026m06 |
| Missing partition | Insert with created_at = '2026-09-01' (no partition exists) | PostgreSQL error — verify partition_creator prevents this |

**Method**: Integration test against Neon test branch or local PostgreSQL 16 with partitions.

---

## Test Coverage Priorities

| Area | Priority | Reason |
|------|----------|--------|
| Webhook idempotency | Critical | Duplicate processing corrupts user data |
| Cascade failover | Critical | Service availability depends on it |
| SM-2 algorithm | High | Incorrect math breaks spaced repetition |
| Rate limiter | High | Free-tier quota protection |
| Auth HMAC/JWT | High | Security boundary |
| Partitioning | Medium | Data correctness at month boundaries |
| Canvas rendering | Low | Visual; manual QA sufficient |
