-- ==============================================================================
-- RECALL DATABASE SCHEMA (schema.sql)
-- Neon PostgreSQL 16 + pgvector + pg_trgm
-- ==============================================================================

-- 1. EXTENSIONS
-- pgvector for approximate nearest-neighbor vector search
CREATE EXTENSION IF NOT EXISTS vector;
-- pg_trgm for fuzzy text search on plaintext summaries
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 2. USERS TABLE
CREATE TABLE IF NOT EXISTS users (
    id                   SERIAL PRIMARY KEY,
    telegram_chat_id     VARCHAR(50) UNIQUE NOT NULL,
    google_refresh_token TEXT,              -- Fernet AES-128 encrypted
    timezone_offset      INT DEFAULT 0,     -- UTC offset in minutes
    streak_count         INT DEFAULT 0,
    last_activity_date   DATE,
    drive_nudge_sent     BOOLEAN DEFAULT FALSE,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. ITEMS TABLE (Partitioned by Range on created_at)
CREATE TABLE IF NOT EXISTS items (
    id           SERIAL,
    user_id      INT REFERENCES users(id) ON DELETE CASCADE,
    source_type  VARCHAR(20) NOT NULL,      -- url / voice / pdf / image / text
    source_url   TEXT,
    raw_text     TEXT,                      -- Fernet AES-128 encrypted at rest
    summary      TEXT,                      -- Plaintext (required for GIN trigram index)
    title        VARCHAR(500),              -- Plaintext
    embedding    VECTOR(384),               -- MiniLM-L6-v2 output
    tags         TEXT[],                    -- Postgres native array
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

-- 4. PARTITIONS
-- Pre-create partitions for June and July 2026
CREATE TABLE IF NOT EXISTS items_y2026m06 PARTITION OF items
    FOR VALUES FROM ('2026-06-01 00:00:00') TO ('2026-07-01 00:00:00');

CREATE TABLE IF NOT EXISTS items_y2026m07 PARTITION OF items
    FOR VALUES FROM ('2026-07-01 00:00:00') TO ('2026-08-01 00:00:00');

-- 5. QUIZZES TABLE
CREATE TABLE IF NOT EXISTS quizzes (
    id             SERIAL PRIMARY KEY,
    user_id        INT REFERENCES users(id) ON DELETE CASCADE,
    item_id        INT NOT NULL,              -- References items(id), not FK due to partitioning composite PK
    question       TEXT NOT NULL,
    options        JSONB NOT NULL,            -- Array of 4 options: ["opt1", "opt2", "opt3", "opt4"]
    correct_index  INT NOT NULL,              -- 0-based index of correct option
    explanation    TEXT,
    ease_factor    FLOAT DEFAULT 2.5,         -- SM-2 ease factor
    interval_days  INT DEFAULT 1,             -- SM-2 interval
    next_review    DATE DEFAULT CURRENT_DATE, -- Scheduled review date
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. REMINDERS TABLE
CREATE TABLE IF NOT EXISTS reminders (
    id           SERIAL PRIMARY KEY,
    user_id      INT REFERENCES users(id) ON DELETE CASCADE,
    item_id      INT,                       -- Optional link to a saved item
    message      TEXT NOT NULL,
    remind_at    TIMESTAMP NOT NULL,
    status       VARCHAR(20) DEFAULT 'pending', -- pending / sent / failed
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. SEMANTIC HUBS TABLE
CREATE TABLE IF NOT EXISTS semantic_hubs (
    id           SERIAL PRIMARY KEY,
    user_id      INT REFERENCES users(id) ON DELETE CASCADE,
    label        VARCHAR(200) NOT NULL,     -- LLM-generated community name
    centroid     VECTOR(384),               -- Mean embedding of members
    member_ids   INT[],                     -- Array of member item.ids
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 8. PROCESSED UPDATES (Telegram webhook idempotency)
CREATE TABLE IF NOT EXISTS processed_updates (
    update_id    VARCHAR(50) PRIMARY KEY,   -- Telegram update_id as string
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 9. DEAD LETTER QUEUE (Task execution failover)
CREATE TABLE IF NOT EXISTS dead_letter_queue (
    id            SERIAL PRIMARY KEY,
    user_id       INT REFERENCES users(id) ON DELETE CASCADE,
    task_payload  JSONB NOT NULL,            -- Full task context
    error_message TEXT,
    failed_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    retried       BOOLEAN DEFAULT FALSE
);

-- 10. INDICES
-- B-Tree index for fast user items fetching (list + graph APIs)
CREATE INDEX IF NOT EXISTS idx_items_user
    ON items(user_id);

-- HNSW index for sub-10 ms cosine similarity vector search
CREATE INDEX IF NOT EXISTS idx_items_embedding
    ON items USING hnsw (embedding vector_cosine_ops)
    WITH (m=16, ef_construction=64);

-- GIN trigram index for sub-5 ms fuzzy text search on summary column ONLY (not raw_text)
CREATE INDEX IF NOT EXISTS idx_items_text_gin
    ON items USING gin (summary gin_trgm_ops);

-- B-Tree index for reminders dispatcher polling
CREATE INDEX IF NOT EXISTS idx_reminders_time_status
    ON reminders(remind_at, status);
