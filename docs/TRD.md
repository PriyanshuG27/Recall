# TRD — Recall

| Field | Value |
|-------|-------|
| Version | 0.1.0 |
| Date | 2026-06-19 |
| Status | Draft |

---

## Full Stack

| Layer | Technology | Tier / Plan | Rationale |
|-------|-----------|-------------|-----------|
| Backend API | FastAPI (Python) | Render free | Async-native, webhook-friendly, easy APScheduler integration |
| Frontend | React + Vite | Vercel free | Fast builds, edge CDN, zero config for SPA |
| Database | PostgreSQL + pgvector + pg_trgm | Neon free (0.5 GB) | Single DB for relational + vector + full-text; no separate vector DB |
| Task Queue | Upstash Redis (REST) | Free (10K cmd/day) | Serverless Redis; no persistent connection needed; atomic ZADD for rate limiting |
| AI Tier 0 | Modal serverless GPU | Pay-per-second | Whisper large-v3 + Llama 3.3 70B + MiniLM — highest quality, no monthly fee when idle |
| AI Tier 1 | Groq Cloud API | Free tier | Whisper-Turbo + Qwen3-32b (60 RPM) + Llama 4 Scout (long context) |
| AI Tier 2 | Gemini 3.1 Flash-Lite | Free (30 RPM / 1500 RPD) | Large context window; fallback for summarisation |
| AI Tier 3 | Ollama (local) | Optional | Developer/self-host escape hatch; active when LOCAL_MODE=true |
| AI Tier 4 | Bookmark fallback | — | Guarantees zero data loss; item saved without AI enrichment |
| Scheduler | APScheduler (in-process) | — | No extra infra; runs inside FastAPI on Render |
| Keepalive | Uptime Robot | Free (5-min ping) | Prevents Render free-tier cold starts |

---

## System Architecture

```
                        ┌─────────────────────────────┐
                        │        USER SURFACES         │
                        │  Telegram Bot  │  Web (TWA)  │
                        └────────┬───────────────┬─────┘
                                 │               │
                    Telegram API │               │ HTTPS / WS
                                 ▼               ▼
                        ┌────────────────────────────────┐
                        │     FastAPI Backend (Render)    │
                        │                                 │
                        │  POST /webhook                  │
                        │  GET  /health                   │
                        │  GET  /auth/telegram            │
                        │  GET  /auth/google[/callback]   │
                        │  WS   /ws/{token}               │
                        │  GET  /api/items                │
                        │  POST /api/search               │
                        │  GET  /api/graph                │
                        │  GET  /api/quizzes/due          │
                        │  POST /api/quizzes/{id}/answer  │
                        │  POST /api/reminders            │
                        │  GET  /api/hubs                 │
                        │                                 │
                        │  [APScheduler in-process]       │
                        └──────────┬──────────────────────┘
                    ┌──────────────┼──────────────────┐
                    ▼              ▼                   ▼
            ┌──────────────┐ ┌──────────┐   ┌──────────────────┐
            │   Neon DB    │ │ Upstash  │   │  AI Cascade      │
            │  PostgreSQL  │ │  Redis   │   │  T0: Modal GPU   │
            │  + pgvector  │ │  Queue   │   │  T1: Groq        │
            │  + pg_trgm   │ │  + Rate  │   │  T2: Gemini      │
            └──────────────┘ │  Limiter │   │  T3: Bookmark    │
                             └──────────┘   │  T4: Ollama (dev)│
                                            └──────────────────┘
```

---

## Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Single-process scheduler | APScheduler in FastAPI | Eliminates separate Celery worker on free tier; acceptable for 5 jobs |
| Partitioned items table | Monthly RANGE partitions | Prevents full-table scans; partition pruning on date filters |
| HNSW over IVFFlat | pgvector HNSW | Faster query (no probe tuning), better accuracy at small-to-mid scale |
| Redis via REST (Upstash) | Not persistent TCP | Render free tier has no persistent outbound TCP guarantee; REST is stateless |
| Fernet for raw_text | AES-128 symmetric | Simple, auditable, single-key rotation path; server must see plaintext for embeddings anyway |
| In-process WebSocket | FastAPI native WS | No separate WS server; acceptable at free-tier concurrency |
| Webhook idempotency via PK | processed_updates table | ON CONFLICT DO NOTHING is atomic and cheap; no Redis needed for dedup |
| Monthly partitions pre-created | partition_creator job | Postgres requires partition to exist before INSERT; pre-creation on 25th gives buffer |

---

## Data Flow

```
User sends message to Telegram
    -> Telegram delivers to POST /webhook
    -> Idempotency check (processed_updates)
    -> Rate limit check (Redis sliding window)
    -> Task pushed to Upstash Redis queue
    -> Webhook returns 200 in < 50 ms

Worker dequeues task:
    -> Detect content type (voice / URL / PDF / image / text)
    -> AI Cascade (T0 -> T3/T4)
        -> Transcription / extraction
        -> Summarisation
        -> Embedding (MiniLM 384-dim)
        -> Quiz generation
    -> INSERT into items (with Fernet-encrypted raw_text)
    -> INSERT into quizzes
    -> Broadcast graph update via WebSocket
    -> Reply to user via Telegram bot API
```

---

## Scaling Assumptions

| Constraint | Limit | Mitigation |
|------------|-------|------------|
| Neon free tier | 0.5 GB storage | Monthly partitioning; pruning old partitions manually |
| Upstash free tier | 10K commands/day | Rate limiter caps at 20 req/user/min; typical user: ~50 cmd/day |
| Render free tier | 512 MB RAM, sleeps after 15 min inactivity | Uptime Robot 5-min ping; asyncio.Semaphore(3) caps memory |
| Modal cold start | 2-5 s for GPU container | Groq Tier 1 handles burst while Modal warms |
| Groq free tier | Unknown RPM cap | Gemini Tier 2 absorbs overflow |
| pgvector HNSW | Sub-10 ms at 1M vectors | m=16, ef_construction=64; acceptable for single-user scale |
