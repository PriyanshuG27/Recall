-- migrate:up
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
    near_miss_lower_bound NUMERIC(4, 3) DEFAULT 0.710,
    last_atrium_moment_at TIMESTAMP WITH TIME ZONE,
    self_description     TEXT,
    mind_type            VARCHAR(50),
    mind_type_summary    TEXT,
    mind_type_trajectory JSONB DEFAULT '[]'::jsonb,
    node_milestones      JSONB DEFAULT '{"unlocked": []}'::jsonb,
    last_confession_at   TIMESTAMP WITH TIME ZONE,
    last_forward_hook_at TIMESTAMP WITH TIME ZONE,
    last_prediction_at   TIMESTAMP WITH TIME ZONE,
    first_name           VARCHAR(100),
    username             VARCHAR(100),
    pulse_score          NUMERIC DEFAULT 0,
    initial_onboarding_completed BOOLEAN DEFAULT FALSE,
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

CREATE TABLE IF NOT EXISTS items_default PARTITION OF items DEFAULT;

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

-- Functional GIN index for full-text search over the summary column
-- Default configuration is 'english' for stemming/tokenization; multilingual stemming is deferred post-v1.
CREATE INDEX IF NOT EXISTS idx_items_summary_fts_gin
    ON items USING gin (to_tsvector('english', COALESCE(summary, '')));

-- GIN index for fast PostgreSQL native array overlap tags filtering
CREATE INDEX IF NOT EXISTS idx_items_tags_gin
    ON items USING gin (tags);

-- B-Tree index for filtering by source type per user
CREATE INDEX IF NOT EXISTS idx_items_source_type
    ON items (user_id, source_type);

-- B-Tree index for filtering by creation date per user
CREATE INDEX IF NOT EXISTS idx_items_created_at
    ON items (user_id, created_at);

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
    chunk_version INT DEFAULT 1,
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


-- 17. JOURNEY PAIRS TABLE (Hearth feature)
-- Stores active Hearth partnerships between two users.
-- user_a_id < user_b_id enforced by CHECK to prevent duplicate pairs.
CREATE TABLE IF NOT EXISTS journey_pairs (
  id          SERIAL PRIMARY KEY,
  user_a_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  user_b_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  shared_days INTEGER NOT NULL DEFAULT 0,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  status      VARCHAR(20) NOT NULL DEFAULT 'active',
  CHECK (user_a_id < user_b_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_journey_pairs_users
  ON journey_pairs(user_a_id, user_b_id);
CREATE INDEX IF NOT EXISTS idx_journey_pairs_a ON journey_pairs(user_a_id);
CREATE INDEX IF NOT EXISTS idx_journey_pairs_b ON journey_pairs(user_b_id);

-- 18. JOURNEY INVITES TABLE (Hearth feature)
-- Invite codes generated by one user, shared via link or Telegram.
-- Codes expire after 7 days. Status: pending | accepted | expired.
CREATE TABLE IF NOT EXISTS journey_invites (
  id          SERIAL PRIMARY KEY,
  inviter_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  invite_code VARCHAR(16) NOT NULL UNIQUE,
  status      VARCHAR(20) NOT NULL DEFAULT 'pending',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at  TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '7 days'
);
CREATE INDEX IF NOT EXISTS idx_journey_invites_code
  ON journey_invites(invite_code);
CREATE INDEX IF NOT EXISTS idx_journey_invites_inviter
  ON journey_invites(inviter_id, status);

-- 19. TELEMETRY COST LOGS TABLE
CREATE TABLE IF NOT EXISTS telemetry_cost_logs (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE SET NULL,
    request_id VARCHAR(100),
    provider VARCHAR(50) NOT NULL,
    model VARCHAR(100) NOT NULL,
    task VARCHAR(50) NOT NULL,
    prompt_tokens INT DEFAULT 0,
    completion_tokens INT DEFAULT 0,
    total_tokens INT DEFAULT 0,
    audio_duration_seconds NUMERIC(8, 2) DEFAULT 0.0,
    cost_usd NUMERIC(12, 8) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_telemetry_cost_logs_user_id ON telemetry_cost_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_cost_logs_created_at ON telemetry_cost_logs(created_at);

-- 20. AI DECISION LOGS TABLE
CREATE TABLE IF NOT EXISTS ai_decision_logs (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE SET NULL,
    request_id VARCHAR(100) NOT NULL,
    execution_id VARCHAR(100) NOT NULL,
    task VARCHAR(50) NOT NULL,
    pipeline VARCHAR(100) NOT NULL,
    provider_used VARCHAR(50),
    model_used VARCHAR(100),
    success BOOLEAN NOT NULL,
    attempts JSONB NOT NULL,       -- Detailed array of attempt metadata
    final_output JSONB,           -- Sanitized final validation payload
    error_message TEXT,           -- Complete error trace if all candidates failed
    cache_hit BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_decision_logs_user_id ON ai_decision_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_decision_logs_created_at ON ai_decision_logs(created_at);

-- 21. ACTIVE HUBS TABLE (Thematic visual hubs computed daily)
CREATE TABLE IF NOT EXISTS active_hubs (
    id             SERIAL PRIMARY KEY,
    user_id        INT REFERENCES users(id) ON DELETE CASCADE,
    tag            VARCHAR(100) NOT NULL,
    last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_active_hubs_user ON active_hubs(user_id);


-- 22. INSIGHT CANDIDATES TABLE
CREATE TABLE IF NOT EXISTS insight_candidates (
    id                 SERIAL PRIMARY KEY,
    user_id            INT REFERENCES users(id) ON DELETE CASCADE,
    item_id_a          INT NOT NULL,
    item_id_b          INT NOT NULL,
    similarity_score   FLOAT NOT NULL,
    bucket             VARCHAR(20) NOT NULL,
    status             VARCHAR(20) DEFAULT 'pending',
    insight_text       TEXT,
    expires_at         TIMESTAMP,
    cluster_pair_hash  VARCHAR(32),
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_candidates_user_status ON insight_candidates(user_id, status);


-- 23. ENTITY & RELATIONSHIP EXTRACTION SCHEMAS
ALTER TABLE items ADD COLUMN IF NOT EXISTS extraction_status VARCHAR(20) DEFAULT 'pending';
ALTER TABLE items ADD COLUMN IF NOT EXISTS extractor_version INT DEFAULT 1;

CREATE TABLE IF NOT EXISTS entities (
    id              SERIAL PRIMARY KEY,
    user_id         INT REFERENCES users(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    normalized_name VARCHAR(255) NOT NULL,
    type            VARCHAR(100) NOT NULL,      -- Person, Org, Project, Tech, Concept, Place
    description     TEXT,
    embedding       VECTOR(384),                -- Stable name + type embedding
    degree          INT DEFAULT 0,              -- Precomputed node degree centrality
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, normalized_name, type)
);

CREATE TABLE IF NOT EXISTS entity_mentions (
    id           SERIAL PRIMARY KEY,
    user_id      INT REFERENCES users(id) ON DELETE CASCADE,
    entity_id    INT REFERENCES entities(id) ON DELETE CASCADE,
    item_id      INT,
    excerpt      TEXT,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, entity_id, item_id)
);

CREATE TABLE IF NOT EXISTS relationships (
    id             SERIAL PRIMARY KEY,
    user_id        INT REFERENCES users(id) ON DELETE CASCADE,
    source_type    VARCHAR(50) NOT NULL,      -- 'entity' or 'item'
    source_id      INT NOT NULL,
    target_type    VARCHAR(50) NOT NULL,      -- 'entity' or 'item'
    target_id      INT NOT NULL,
    predicate      VARCHAR(100) NOT NULL,     -- 'works_on', 'uses', 'part_of', 'related_to'
    description    TEXT,
    weight         FLOAT DEFAULT 1.0,
    confidence     FLOAT DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1), -- Model extraction confidence
    item_id        INT, -- Provenance
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, source_type, source_id, target_type, target_id, predicate)
);

CREATE INDEX IF NOT EXISTS idx_entities_user ON entities (user_id);
CREATE INDEX IF NOT EXISTS idx_entities_user_emb ON entities USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_entity_mentions_item ON entity_mentions (item_id);

ALTER TABLE item_chunks ADD COLUMN IF NOT EXISTS chunk_version INT DEFAULT 1;
CREATE INDEX IF NOT EXISTS idx_item_chunks_version ON item_chunks (chunk_version);


-- 15. AUDIT LOGS TABLE
CREATE TABLE IF NOT EXISTS audit_logs (
    id          SERIAL PRIMARY KEY,
    user_id     INT REFERENCES users(id) ON DELETE CASCADE,
    action      VARCHAR(50) NOT NULL,
    details     JSONB NOT NULL,
    request_id  VARCHAR(50),
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user ON audit_logs (user_id);


-- 16. ENGAGEMENT EVENTS TABLE
CREATE TABLE IF NOT EXISTS engagement_events (
    id           SERIAL PRIMARY KEY,
    user_id      INT REFERENCES users(id) ON DELETE CASCADE,
    event_type   VARCHAR(50) NOT NULL,
    details      JSONB DEFAULT '{}'::jsonb,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_engagement_events_user_type ON engagement_events(user_id, event_type);


-- 17. AI COST LOGS TABLE
CREATE TABLE IF NOT EXISTS ai_cost_logs (
    id           SERIAL PRIMARY KEY,
    user_id      INT REFERENCES users(id) ON DELETE CASCADE,
    request_id   VARCHAR(50),
    provider     VARCHAR(50) NOT NULL,
    model_name   VARCHAR(100) NOT NULL,
    operation    VARCHAR(50) NOT NULL,
    input_tokens INT DEFAULT 0,
    output_tokens INT DEFAULT 0,
    cost_usd     NUMERIC(10, 6) DEFAULT 0.000000,
    success      BOOLEAN DEFAULT TRUE,
    retry_count  INT DEFAULT 0,
    cache_hit    BOOLEAN DEFAULT FALSE,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ai_cost_logs_user_request ON ai_cost_logs(user_id, request_id);

-- migrate:down
DROP TABLE IF EXISTS ai_cost_logs CASCADE;
DROP TABLE IF EXISTS engagement_events CASCADE;
DROP TABLE IF EXISTS audit_logs CASCADE;
DROP TABLE IF EXISTS relationships CASCADE;
DROP TABLE IF EXISTS entity_mentions CASCADE;
DROP TABLE IF EXISTS entities CASCADE;
DROP TABLE IF EXISTS insight_candidates CASCADE;
DROP TABLE IF EXISTS active_hubs CASCADE;
DROP TABLE IF EXISTS ai_decision_logs CASCADE;
DROP TABLE IF EXISTS telemetry_cost_logs CASCADE;
DROP TABLE IF EXISTS journey_invites CASCADE;
DROP TABLE IF EXISTS journey_pairs CASCADE;
DROP TABLE IF EXISTS tag_portraits CASCADE;
DROP TABLE IF EXISTS static_domain_centroids CASCADE;
DROP TABLE IF EXISTS quiz_answers CASCADE;
DROP FUNCTION IF EXISTS cascade_delete_item_chunks() CASCADE;
DROP TABLE IF EXISTS item_chunks CASCADE;
DROP TABLE IF EXISTS processed_updates CASCADE;
DROP TABLE IF EXISTS semantic_hubs CASCADE;
DROP TABLE IF EXISTS reminders CASCADE;
DROP TABLE IF EXISTS quizzes CASCADE;
DROP TABLE IF EXISTS items CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP EXTENSION IF EXISTS pg_trgm CASCADE;
DROP EXTENSION IF EXISTS vector CASCADE;
