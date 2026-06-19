# BACKEND_SCHEMA — Recall

| Field | Value |
|-------|-------|
| Version | 0.1.0 |
| Date | 2026-06-19 |
| Status | Draft |
| DB Engine | PostgreSQL 16 + pgvector + pg_trgm |

---

## Extensions

```sql
CREATE EXTENSION IF NOT EXISTS vector;    -- pgvector: HNSW / cosine similarity
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- trigram GIN index for fuzzy text search
```

---

## Tables

### users

```sql
CREATE TABLE users (
    id                  SERIAL PRIMARY KEY,
    telegram_chat_id    VARCHAR(50) UNIQUE NOT NULL,
    google_refresh_token TEXT,
    timezone_offset     INT DEFAULT 0,
    streak_count        INT DEFAULT 0,
    last_activity_date  DATE,
    drive_nudge_sent    BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

| Column | Type | Purpose |
|--------|------|---------|
| id | SERIAL PK | Internal surrogate key; referenced by all child tables |
| telegram_chat_id | VARCHAR(50) UNIQUE | Primary user identity; Telegram chat.id; UNIQUE enforces one account per Telegram user |
| google_refresh_token | TEXT | Fernet AES-128 encrypted OAuth refresh token; NULL until user connects Drive |
| timezone_offset | INT | UTC offset in minutes; used by reminders_dispatcher for local-time delivery |
| streak_count | INT | Consecutive days with at least one save; incremented by daily activity check |
| last_activity_date | DATE | Date of most recent item insert; drives streak calculation |
| drive_nudge_sent | BOOLEAN | Gates drive_nudge_sender job; prevents repeat nudges |
| created_at | TIMESTAMP | Account creation timestamp |

---

### items (partitioned)

```sql
CREATE TABLE items (
    id          SERIAL,
    user_id     INT REFERENCES users(id) ON DELETE CASCADE,
    source_type VARCHAR(20) NOT NULL,
    source_url  TEXT,
    raw_text    TEXT,
    summary     TEXT,
    title       VARCHAR(500),
    embedding   VECTOR(384),
    tags        TEXT[],
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE TABLE items_y2026m06 PARTITION OF items
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');

CREATE TABLE items_y2026m07 PARTITION OF items
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
```

| Column | Type | Purpose |
|--------|------|---------|
| id | SERIAL | Item identifier; combined with created_at as composite PK (required for partitioned table) |
| user_id | INT FK | Owner; CASCADE DELETE removes items when user is deleted |
| source_type | VARCHAR(20) | Enum: url / voice / pdf / image / text; drives pipeline routing |
| source_url | TEXT | Original URL for url/voice/YouTube items; NULL for direct uploads |
| raw_text | TEXT | Full extracted/transcribed text; Fernet AES-128 encrypted at rest |
| summary | TEXT | Llama 3 generated summary; **plaintext** — required for GIN index |
| title | VARCHAR(500) | Extracted or generated title; plaintext |
| embedding | VECTOR(384) | MiniLM-L6-v2 output; 384 dimensions; used for HNSW cosine search |
| tags | TEXT[] | LLM-generated tags; Postgres native array; filterable with @> operator |
| created_at | TIMESTAMP | Partition key; determines which child table stores the row |

**Partitioning Strategy**:
- Strategy: RANGE on `created_at`, one partition per calendar month.
- Pre-created by `partition_creator` scheduler job on the 25th of each month.
- Partition pruning: queries with `WHERE created_at BETWEEN x AND y` never scan other months.
- Retention: old partitions can be DETACHed and DROPped without locking the parent table.

---

### quizzes

```sql
CREATE TABLE quizzes (
    id            SERIAL PRIMARY KEY,
    user_id       INT REFERENCES users(id) ON DELETE CASCADE,
    item_id       INT NOT NULL,
    question      TEXT NOT NULL,
    options       JSONB NOT NULL,
    correct_index INT NOT NULL,
    explanation   TEXT,
    ease_factor   FLOAT DEFAULT 2.5,
    interval_days INT DEFAULT 1,
    next_review   DATE DEFAULT CURRENT_DATE,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

| Column | Type | Purpose |
|--------|------|---------|
| item_id | INT | References the item this quiz tests; not FK (items has composite PK) |
| question | TEXT | LLM-generated question |
| options | JSONB | Array of 4 answer strings: `["opt1","opt2","opt3","opt4"]` |
| correct_index | INT | 0-based index of correct option in options array |
| explanation | TEXT | LLM explanation shown after answer |
| ease_factor | FLOAT | SM-2 ease factor; starts at 2.5; adjusted per answer quality |
| interval_days | INT | Days until next review; grows exponentially on correct answers |
| next_review | DATE | Scheduled review date; queried by GET /api/quizzes/due |

---

### reminders

```sql
CREATE TABLE reminders (
    id         SERIAL PRIMARY KEY,
    user_id    INT REFERENCES users(id) ON DELETE CASCADE,
    item_id    INT,
    message    TEXT NOT NULL,
    remind_at  TIMESTAMP NOT NULL,
    status     VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

| Column | Type | Purpose |
|--------|------|---------|
| item_id | INT | Optional link to a saved item; NULL for standalone reminders |
| message | TEXT | Reminder text sent via Telegram bot API |
| remind_at | TIMESTAMP | Target delivery time; indexed with status for dispatcher query |
| status | VARCHAR(20) | pending / sent / failed; updated by reminders_dispatcher |

---

### semantic_hubs

```sql
CREATE TABLE semantic_hubs (
    id         SERIAL PRIMARY KEY,
    user_id    INT REFERENCES users(id) ON DELETE CASCADE,
    label      VARCHAR(200) NOT NULL,
    centroid   VECTOR(384),
    member_ids INT[],
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

| Column | Type | Purpose |
|--------|------|---------|
| label | VARCHAR(200) | LLM-generated cluster label (e.g. "Machine Learning Research") |
| centroid | VECTOR(384) | Mean embedding of all member items; used for hub node position in mind map |
| member_ids | INT[] | item.id array for all cluster members; used to draw edges on graph |

---

### processed_updates

```sql
CREATE TABLE processed_updates (
    update_id    VARCHAR(50) PRIMARY KEY,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

| Column | Type | Purpose |
|--------|------|---------|
| update_id | VARCHAR(50) PK | Telegram update_id as string; PRIMARY KEY makes duplicate INSERT silently fail via ON CONFLICT DO NOTHING |
| processed_at | TIMESTAMP | Used by processed_updates_cleanup job (deletes rows older than 30 days) |

---

### dead_letter_queue

```sql
CREATE TABLE dead_letter_queue (
    id           SERIAL PRIMARY KEY,
    user_id      INT REFERENCES users(id) ON DELETE CASCADE,
    task_payload JSONB NOT NULL,
    error_message TEXT,
    failed_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    retried      BOOLEAN DEFAULT FALSE
);
```

| Column | Type | Purpose |
|--------|------|---------|
| task_payload | JSONB | Full task context (content_type, file_id, chat_id, etc.) for retry |
| error_message | TEXT | Last error from cascade Tier 4 exhaustion |
| retried | BOOLEAN | Admin sets TRUE to trigger manual re-enqueue |

---

## Indices

| Index Name | Table | Type | Columns | Rationale |
|------------|-------|------|---------|-----------|
| idx_items_user | items | B-Tree | user_id | Fast fetch of all items for a given user (list + graph API) |
| idx_items_embedding | items | HNSW | embedding (vector_cosine_ops) | Sub-10 ms approximate nearest-neighbour search; m=16, ef_construction=64 |
| idx_items_text_gin | items | GIN | summary (gin_trgm_ops) | Sub-5 ms trigram fuzzy text search; LIKE/ILIKE queries without sequential scan |
| idx_reminders_time_status | reminders | B-Tree | (remind_at, status) | reminders_dispatcher query: WHERE remind_at <= NOW() AND status='pending' |

```sql
CREATE INDEX idx_items_user
    ON items(user_id);

CREATE INDEX idx_items_embedding
    ON items USING hnsw (embedding vector_cosine_ops)
    WITH (m=16, ef_construction=64);

CREATE INDEX idx_items_text_gin
    ON items USING gin (summary gin_trgm_ops);

CREATE INDEX idx_reminders_time_status
    ON reminders(remind_at, status);
```

---

## Entity Relationship Overview

```
users (1)
  |-- (N) items            [user_id FK]
  |-- (N) quizzes          [user_id FK]
  |-- (N) reminders        [user_id FK]
  |-- (N) semantic_hubs    [user_id FK]
  |-- (N) dead_letter_queue[user_id FK]

processed_updates           [standalone, no FK]
```
