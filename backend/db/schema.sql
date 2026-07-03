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
    google_last_sync     TIMESTAMP,         -- Timestamp of last Google Drive sync
    timezone_offset      INT DEFAULT 0,     -- UTC offset in minutes
    streak_count         INT DEFAULT 0,
    last_activity_date   DATE,
    digest_enabled       BOOLEAN DEFAULT TRUE,
    drive_nudge_sent     BOOLEAN DEFAULT FALSE,
    onboarding_day       INT DEFAULT 0,     -- Day 1-5 onboarding sequence tracking
    onboarding_last_sent TIMESTAMP DEFAULT NULL,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Ensure the columns exist if the users/items tables already exist
ALTER TABLE users ADD COLUMN IF NOT EXISTS google_last_sync TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS digest_enabled BOOLEAN DEFAULT TRUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_day INT DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_last_sent TIMESTAMP DEFAULT NULL;
ALTER TABLE items ADD COLUMN IF NOT EXISTS context_note TEXT;
ALTER TABLE items ADD COLUMN IF NOT EXISTS passive_context JSONB;
ALTER TABLE items ADD COLUMN IF NOT EXISTS save_time_bucket VARCHAR(20);
ALTER TABLE items ADD COLUMN IF NOT EXISTS category VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS near_miss_lower_bound NUMERIC(4, 3) DEFAULT 0.710;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_recall_moment_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS self_description TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS mind_type VARCHAR(50);
ALTER TABLE users ADD COLUMN IF NOT EXISTS mind_type_summary TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS mind_type_trajectory JSONB DEFAULT '[]'::jsonb;
ALTER TABLE users ADD COLUMN IF NOT EXISTS node_milestones JSONB DEFAULT '{"unlocked": []}'::jsonb;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_confession_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_forward_hook_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_prediction_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(100);



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
    content_hash VARCHAR(16),               -- SHA256 first 16 chars for exact text deduplication
    context_note TEXT,                      -- User-provided context note
    context_prompt TEXT,                    -- AI-generated custom context prompt question
    passive_context JSONB,                  -- Captured ingest event metadata
    category     VARCHAR(100),              -- AI-classified topic category
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
    last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    streak_days   INT DEFAULT 0,
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

-- B-Tree index for deduplication checks
CREATE INDEX IF NOT EXISTS idx_items_content_hash
    ON items(user_id, content_hash);

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


-- 11. ITEM CHUNKS TABLE (PDF Chunking & Multi-Chunk Embedding)
CREATE TABLE IF NOT EXISTS item_chunks (
    id          SERIAL PRIMARY KEY,
    item_id     INT NOT NULL,              -- References items(id), not FK due to partitioning composite PK
    user_id     INT REFERENCES users(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    chunk_text  TEXT NOT NULL,             -- Plaintext (excerpt for search, max 500 chars)
    embedding   VECTOR(384),               -- MiniLM-L6-v2 output
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chunks_item 
    ON item_chunks(item_id);

CREATE INDEX IF NOT EXISTS idx_chunks_embedding 
    ON item_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m=16, ef_construction=64);

-- Trigger to cascade deletes from items to item_chunks (needed since we cannot use a simple FK due to partitioning composite PK)
CREATE OR REPLACE FUNCTION cascade_delete_item_chunks()
RETURNS TRIGGER AS $$
BEGIN
    DELETE FROM item_chunks WHERE item_id = OLD.id;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trigger_cascade_delete_item_chunks
BEFORE DELETE ON items
FOR EACH ROW
EXECUTE FUNCTION cascade_delete_item_chunks();


-- 12. QUIZ ANSWERS TABLE
CREATE TABLE IF NOT EXISTS quiz_answers (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    quiz_id INT REFERENCES quizzes(id) ON DELETE CASCADE,
    quality INT NOT NULL,
    answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 13. STATIC DOMAIN CENTROIDS TABLE
CREATE TABLE IF NOT EXISTS static_domain_centroids (
    id SERIAL PRIMARY KEY,
    domain_name VARCHAR(100) UNIQUE NOT NULL,
    embedding vector(384) NOT NULL
);


-- 14. COGNITIVE BRIDGES TABLE
CREATE TABLE IF NOT EXISTS cognitive_bridges (
    id                  SERIAL PRIMARY KEY,
    user_id_1           INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    user_id_2           INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    compatibility_score NUMERIC(5, 2) DEFAULT 0.0,
    synergy_description TEXT,
    last_ceremony_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id_1, user_id_2),
    CHECK (user_id_1 < user_id_2)
);

CREATE INDEX IF NOT EXISTS idx_bridges_users ON cognitive_bridges(user_id_1, user_id_2);


-- 15. BRIDGE INVITES TABLE
CREATE TABLE IF NOT EXISTS bridge_invites (
    id         SERIAL PRIMARY KEY,
    inviter_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code       VARCHAR(50) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 16. TAG PORTRAITS TABLE
CREATE TABLE IF NOT EXISTS tag_portraits (
    id           SERIAL PRIMARY KEY,
    user_id      INT REFERENCES users(id) ON DELETE CASCADE,
    tag          VARCHAR(100) NOT NULL,
    description  TEXT NOT NULL,
    icon         VARCHAR(100) NOT NULL,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, tag)
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS pulse_score NUMERIC DEFAULT 0;

