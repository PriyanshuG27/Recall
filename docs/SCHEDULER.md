# SCHEDULER — Recall

| Field | Value |
|-------|-------|
| Version | 0.1.0 |
| Date | 2026-06-19 |
| Status | Draft |
| Scheduler | APScheduler 3.x (AsyncIOScheduler, in-process with FastAPI) |

---

## Overview

APScheduler runs inside the FastAPI process on Render. No separate worker needed. Five jobs cover reminders, clustering, partition maintenance, Drive nudges, and idempotency table cleanup.

---

## Job 1 — reminders_dispatcher

| Property | Value |
|----------|-------|
| Trigger | Interval, every 1 minute |
| Cron equivalent | `* * * * *` |
| Purpose | Deliver due reminders to users via Telegram bot API |

**Algorithm**:
```
SELECT * FROM reminders
WHERE remind_at <= NOW()
  AND status = 'pending'
LIMIT 50;

For each reminder:
    -> Call Telegram sendMessage API (chat_id from users table)
    -> On success: UPDATE reminders SET status='sent'
    -> On failure: UPDATE reminders SET status='failed'
```

**Failure behaviour**: Failed reminders stay in table with `status='failed'`. No automatic retry — prevents double-send. Admin can reset to `pending` for manual retry.

**Why it exists**: Render free tier has no cron jobs; APScheduler provides scheduling without extra infrastructure.

---

## Job 2 — louvain_clustering

| Property | Value |
|----------|-------|
| Trigger | Daily cron, 02:00 UTC |
| Cron expression | `0 2 * * *` |
| Purpose | Cluster each user's item embeddings into semantic hubs using Louvain community detection |

**Algorithm**:
```
For each user with >= 10 new items since last clustering run:
    -> Fetch all item embeddings for user
    -> Build k-NN graph (cosine similarity > 0.75)
    -> Run Louvain community detection
    -> For each community:
        -> Compute centroid (mean embedding)
        -> Generate label via LLM: "What theme connects these items?"
    -> DELETE existing semantic_hubs for user
    -> INSERT new hubs (label, centroid, member_ids)
    -> Broadcast via WS /ws/{token}: {type: "hubs_updated", hubs: [...]}
```

**Failure behaviour**: Exception is logged; next day's run retries. No partial writes — DELETE+INSERT is transactional.

**Why it exists**: Clustering is expensive; daily batch at off-peak hours avoids interfering with user requests.

---

## Job 3 — partition_creator

| Property | Value |
|----------|-------|
| Trigger | Monthly cron, 25th at 00:00 UTC |
| Cron expression | `0 0 25 * *` |
| Purpose | Pre-create the next month's `items` partition before it is needed |

**Algorithm**:
```
Calculate next_month = current month + 2 (creates partition one month ahead)
Compute partition bounds: FROM 'YYYY-MM-01' TO 'YYYY-[MM+1]-01'
Execute:
    CREATE TABLE IF NOT EXISTS items_yYYYYmMM
    PARTITION OF items
    FOR VALUES FROM ('<start>') TO ('<end>');
```

**Failure behaviour**: `CREATE TABLE IF NOT EXISTS` is idempotent; safe to retry. Alert logged if job fails — a missing partition causes item INSERTs to fail at month boundary.

**Why it exists**: PostgreSQL range partitioning requires the partition to exist before rows can be inserted. Pre-creation on the 25th gives a 6-day buffer.

---

## Job 4 — drive_nudge_sender

| Property | Value |
|----------|-------|
| Trigger | Daily cron, 10:00 UTC |
| Cron expression | `0 10 * * *` |
| Purpose | Encourage engaged users to connect Google Drive for backup |

**Algorithm**:
```
SELECT id, telegram_chat_id FROM users
WHERE streak_count >= 3
  AND drive_nudge_sent = FALSE
  AND google_refresh_token IS NULL;

For each user:
    -> Send Telegram message with Drive connect link
    -> UPDATE users SET drive_nudge_sent = TRUE
```

**Failure behaviour**: If Telegram API call fails, `drive_nudge_sent` is NOT set to TRUE — user will be retried tomorrow.

**Why it exists**: Drive sync is a high-value feature for retained users. Nudge is sent exactly once (gated by `drive_nudge_sent`) to avoid spam.

---

## Job 5 — processed_updates_cleanup

| Property | Value |
|----------|-------|
| Trigger | Weekly cron, Sunday 03:00 UTC |
| Cron expression | `0 3 * * 0` |
| Purpose | Prune `processed_updates` table to prevent unbounded growth |

**Algorithm**:
```
DELETE FROM processed_updates
WHERE processed_at < NOW() - INTERVAL '30 days';
```

**Failure behaviour**: Safe to retry; no side effects. Telegram update IDs older than 30 days will not be retried by Telegram.

**Why it exists**: `processed_updates` accumulates one row per Telegram update. Without cleanup, the table grows ~1000 rows/day for active users.

---

## Scheduler Summary Table

| Job | Trigger | Frequency | Failure Impact |
|-----|---------|-----------|----------------|
| reminders_dispatcher | Every 1 min | High | Delayed delivery; no data loss |
| louvain_clustering | Daily 02:00 UTC | Low | Stale hubs; retried next day |
| partition_creator | 25th 00:00 UTC | Monthly | INSERT failures at month boundary if missed |
| drive_nudge_sender | Daily 10:00 UTC | Low | Nudge delayed; retried tomorrow |
| processed_updates_cleanup | Weekly Sun 03:00 UTC | Low | Table grows; no functional impact |
