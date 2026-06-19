# RATE_LIMITING — Recall

| Field | Value |
|-------|-------|
| Version | 0.1.0 |
| Date | 2026-06-19 |
| Status | Draft |

---

## Overview

A Redis sliding window rate limiter gates the Telegram webhook handler. It prevents a single user from saturating the AI cascade or Upstash command quota.

---

## Limits

| Dimension | Limit |
|-----------|-------|
| Requests per user per minute | 20 |
| Window type | Sliding (60-second rolling window) |
| Granularity | Per `telegram_chat_id` |
| Enforcement point | POST /webhook, before task enqueue |
| Response on breach | HTTP 429 + `Retry-After` header |

---

## Algorithm — Redis Sliding Window

Uses sorted set (ZSET) where each member is a unique request ID and score is the Unix timestamp in milliseconds.

```
key = "rate:{chat_id}"
now = current Unix timestamp (ms)
window_start = now - 60_000  (60 seconds ago)

MULTI / pipeline:
    ZREMRANGEBYSCORE key 0 window_start      # evict expired entries
    ZADD key now "{now}-{uuid4}"             # add current request
    ZCARD key                                 # count requests in window
    EXPIRE key 61                             # TTL slightly > window
EXEC

if count > 20:
    retry_after = 60 - (now - oldest_score_in_window) / 1000
    return HTTP 429, Retry-After: {retry_after}
```

All four commands execute atomically via Upstash REST pipeline. No race condition possible.

---

## Request Lifecycle Position

```
POST /webhook received
    |
    v
[1] Parse Telegram update JSON
    |
    v
[2] Idempotency check (processed_updates)
    |
    v
[3] RATE LIMIT CHECK  <-- here
    |     |
    |   FAIL -> return 429 (Telegram will retry after delay)
    |
    v
[4] Push task to Upstash Redis queue
    |
    v
[5] Return 200 OK to Telegram (< 50 ms)
```

Rate limiting happens BEFORE task enqueue to protect:
- Upstash command quota (10K/day free tier)
- AI cascade concurrency semaphore
- Neon DB write capacity

---

## Response Format

```
HTTP/1.1 429 Too Many Requests
Retry-After: 23
Content-Type: application/json

{
  "error": "rate_limit_exceeded",
  "message": "Too many requests. Please wait 23 seconds.",
  "retry_after": 23
}
```

Telegram interprets a non-200 response as a delivery failure and retries with exponential backoff. The 429 + Retry-After is informational for monitoring; Telegram's own retry logic handles re-delivery.

---

## Upstash Command Cost

| Operation | Commands | Per request |
|-----------|----------|-------------|
| ZREMRANGEBYSCORE | 1 | Always |
| ZADD | 1 | Always |
| ZCARD | 1 | Always |
| EXPIRE | 1 | Always |
| **Total** | **4** | per webhook call |

At 20 req/user/min maximum and assuming 10 active users: 20 * 10 * 4 = 800 commands/min = 1.15M/day. This exceeds the 10K/day free tier at high load, but realistic usage (1-5 saves/day per user) stays well within budget (~50 commands/user/day).

---

## Exemptions

| Request | Rate Limited? |
|---------|--------------|
| GET /health | No — Uptime Robot keepalive must never be blocked |
| GET /auth/* | No — OAuth flows are user-initiated, not bot-triggered |
| WebSocket /ws/* | No — persistent connection, not per-message |
| POST /webhook | **Yes** — per chat_id |
