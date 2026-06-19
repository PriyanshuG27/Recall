# ERROR_HANDLING — Recall

| Field | Value |
|-------|-------|
| Version | 0.1.0 |
| Date | 2026-06-19 |
| Status | Draft |

---

## Error Categories

| Category | Examples | Handling Strategy |
|----------|---------|-------------------|
| Cascade exhaustion | All 5 AI tiers fail | Dead letter queue + bookmark fallback |
| Webhook duplicate | Telegram retries same update_id | Idempotency via processed_updates (silent discard) |
| Rate limit breach | User sends > 20 req/min | 429 response; Telegram retries naturally |
| DB write failure | Neon connection error, partition missing | Exception logged; task stays in Redis queue for retry |
| Scheduler job failure | APScheduler job throws | Logged; next scheduled run retries |
| WebSocket disconnect | Client navigates away | Connection cleaned up; no error; re-established on next page load |

---

## Webhook Idempotency

Telegram may deliver the same update multiple times (network retry, webhook timeout). Recall deduplicates at the entry point.

```
POST /webhook received with update_id = "12345678"
    |
    v
INSERT INTO processed_updates (update_id)
ON CONFLICT (update_id) DO NOTHING
    |
    |--- rows_affected = 0 (duplicate) -> return 200 immediately, no processing
    |
    |--- rows_affected = 1 (new) -> proceed to rate limit + enqueue
```

- Primary key on `update_id` makes the check atomic — no locks needed.
- 200 is always returned to Telegram (even for duplicates) to stop retry loops.
- Cleanup job removes rows older than 30 days (processed_updates_cleanup job).

---

## AI Cascade Exhaustion Flow

```
Task dequeued from Redis
    |
    v
Try Tier 0 (Modal)
    FAIL -> Try Tier 1 (Groq)
    FAIL -> Try Tier 2 (Gemini)
    FAIL -> Tier 3: Bookmark Fallback (Or Tier 4 if LOCAL_MODE=true)
        |
        v
INSERT INTO items (source_type, source_url, title)  -- minimal fields only
INSERT INTO dead_letter_queue (user_id, task_payload, error_message)
        |
        v
Send Telegram message to user:
    "Could not process [voice note / PDF / link / image].
     Saved as bookmark. We'll retry later."
```

Dead letter entries are visible to admin. Setting `retried = TRUE` and re-enqueueing the `task_payload` triggers a fresh cascade attempt.

---

## Dead Letter Queue Schema

```sql
CREATE TABLE dead_letter_queue (
    id            SERIAL PRIMARY KEY,
    user_id       INT REFERENCES users(id) ON DELETE CASCADE,
    task_payload  JSONB NOT NULL,
    error_message TEXT,
    failed_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    retried       BOOLEAN DEFAULT FALSE
);
```

**task_payload structure**:
```json
{
  "chat_id": "123456789",
  "content_type": "voice",
  "file_id": "BQACAgIA...",
  "update_id": "12345678",
  "attempted_tiers": [0, 1, 2, 3],
  "last_error": "Modal timeout after 30s"
}
```

---

## User-Facing Error Messages

| Scenario | Message |
|---------|---------|
| Cascade exhaustion (voice) | "Could not process your voice note. Saved as bookmark. We'll retry later." |
| Cascade exhaustion (PDF) | "Could not process your PDF. Saved as bookmark. We'll retry later." |
| Cascade exhaustion (URL) | "Could not process that link. Saved as bookmark. We'll retry later." |
| Cascade exhaustion (image) | "Could not process your image. Saved as bookmark. We'll retry later." |
| Rate limit (user-facing) | No message to user — Telegram retries transparently |
| Reminder send failure | No message to user — status set to 'failed', admin visibility only |

---

## Admin Retry Procedure

1. Query dead_letter_queue WHERE retried = FALSE.
2. Inspect task_payload and error_message.
3. If root cause resolved (e.g. Modal back online): re-enqueue task_payload to Redis.
4. UPDATE dead_letter_queue SET retried = TRUE WHERE id = <id>.

No automated retry is implemented — prevents infinite retry loops on persistent failures (e.g. corrupted file, unsupported format).

---

## Scheduler Error Handling

| Job | On Failure |
|-----|-----------|
| reminders_dispatcher | Exception logged; reminder stays `pending`; retried next minute |
| louvain_clustering | Exception logged; hubs not updated; retried next day |
| partition_creator | Exception logged + alert; operator must manually create partition |
| drive_nudge_sender | Exception logged; `drive_nudge_sent` not set; retried next day |
| processed_updates_cleanup | Exception logged; table grows but no functional impact |

APScheduler's `misfire_grace_time` is set to 60 s for all jobs. Jobs that miss their window due to Render sleep are skipped (not run late), except reminders_dispatcher which runs every minute anyway.
