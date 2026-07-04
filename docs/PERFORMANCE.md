# PERFORMANCE — Recall

| Field | Value |
|-------|-------|
| Version | 0.1.0 |
| Date | 2026-06-19 |
| Status | Draft |

---

## Performance Targets

| Operation | Target | Actual Mechanism |
|-----------|--------|-----------------|
| Webhook ACK | < 50 ms | Async enqueue only; no blocking AI call |
| Vector search (top-10) | < 10 ms | HNSW index, cosine ops |
| Text search (trigram) | < 5 ms | GIN index, pg_trgm |
| AI processing (p95) | < 15 s | Modal GPU; Groq fallback |
| Mind map render | 60 FPS | HTML5 Canvas, requestAnimationFrame |
| Graph API response | < 200 ms | Pre-computed hubs; no live clustering |

---

## Vector Search — HNSW Index

```sql
CREATE INDEX idx_items_embedding
    ON items USING hnsw (embedding vector_cosine_ops)
    WITH (m=16, ef_construction=64);
```

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Algorithm | HNSW | No probe tuning; better recall than IVFFlat at small-to-mid scale |
| Distance | cosine | MiniLM-L6-v2 embeddings are unit-normalised; cosine = dot product |
| m | 16 | Number of connections per node; 16 is balanced (accuracy vs memory) |
| ef_construction | 64 | Build-time beam width; 64 gives good recall without slow build |
| ef_search | default (40) | Runtime beam; can be increased per-query for higher recall at cost |
| Scale | < 1M vectors/user | Sub-10 ms maintained up to this scale on Neon free tier |

**Query pattern**:
```sql
SELECT id, title, summary,
       embedding <=> $1 AS distance
FROM items
WHERE user_id = $2
ORDER BY distance
LIMIT 10;
```

---

## Full-Text Search — GIN Index

```sql
CREATE INDEX idx_items_text_gin
    ON items USING gin (summary gin_trgm_ops);
```

| Property | Detail |
|----------|--------|
| Type | GIN (Generalised Inverted Index) |
| Operator class | gin_trgm_ops — trigram decomposition |
| Supported queries | LIKE '%query%', ILIKE, similarity(), word_similarity() |
| Speed | Sub-5 ms for typical summary corpus |
| Why summary not raw_text | raw_text is Fernet-encrypted; GIN cannot index ciphertext |

**Hybrid search**: vector results + GIN results are merged using Reciprocal Rank Fusion (RRF) before returning top-5 to user.

---

## Monthly Partitioning

```
items (parent)
├── items_y2026m06  (2026-06-01 to 2026-07-01)
├── items_y2026m07  (2026-07-01 to 2026-08-01)
└── items_y2026m08  (2026-08-01 to 2026-09-01)  <-- pre-created on 25th
```

| Benefit | Detail |
|---------|--------|
| Partition pruning | Query with date range only scans relevant child table |
| Maintenance | DROP old partition without locking parent |
| Index isolation | HNSW index per partition; smaller, faster builds |
| Insert routing | Postgres routes INSERT to correct partition by created_at automatically |

---

## Redis Task Queue

```
Webhook -> LPUSH task_queue <payload>
Worker  -> BRPOP task_queue (blocking pop)
```

| Property | Detail |
|----------|--------|
| Queue type | Redis List (LPUSH / BRPOP) |
| Webhook latency contribution | ~2 ms for LPUSH via Upstash REST |
| Worker poll | Async task worker loop in FastAPI startup |
| Backpressure | asyncio.Semaphore(3) — max 3 concurrent AI tasks |

---

## Concurrency Semaphore

```python
# Conceptual — no implementation code
semaphore = asyncio.Semaphore(3)

async with semaphore:
    result = await run_ai_cascade(task)
```

| Property | Detail |
|----------|--------|
| Limit | 3 concurrent AI tasks per Render instance |
| Rationale | Render free tier: 512 MB RAM; each AI HTTP call ~80 MB overhead |
| Effect on queue | Tasks queue in Redis if semaphore full; no dropped requests |
| Overflow behaviour | Task waits in Redis; Telegram user receives response within ~15 s |

---

## Keepalive — Uptime Robot

```
Uptime Robot -> GET https://recall-api.onrender.com/health (every 5 min)
Backend      -> {"status": "ok", "timestamp": "..."}
```

| Property | Detail |
|----------|--------|
| Interval | 5 minutes |
| Render sleep threshold | 15 minutes of inactivity |
| Effect | Render never sleeps during active monitoring |
| /health cost | No DB query; no AI call; pure in-memory response |
| Cold start avoidance | 0 cold starts expected during Uptime Robot uptime |

---

## Cold Start Behaviour (if Uptime Robot fails)

```
Render cold start: ~3-5 s for FastAPI boot
Modal cold start: ~2-5 s for GPU container

User experience if both cold:
    -> Webhook received (Render cold start adds 3-5 s)
    -> Task enqueued
    -> AI processing (Modal cold start adds 2-5 s)
    -> Total user-visible delay: ~15-25 s (still within acceptable range)
    -> Telegram does not time out webhook within 30 s
```

---

## Connection Pooling (psycopg3)

To ensure high-throughput execution while respecting the connections limits of Neon serverless databases:
* **Pool Size**: Configured at `min_size=0, max_size=5` per instance.
* **Cold Start Timeout**: Set to `timeout=30.0` seconds to gracefully handle Neon serverless branch wakeups (which typically take 15-20 seconds).
* **Idle Reclaim**: Idle connections are closed after `max_idle=240.0` seconds (4 minutes) to avoid silent link drops by Neon's router (which terminates inactive sockets at 5 minutes).

---

## 3D Mind Map Canvas (WebGL) Performance Gating

To maintain the 60 FPS target on client devices during WebGL rendering of complex graphs, the frontend utilizes [useFPSMonitor.js](file:///d:/Recall/frontend/src/hooks/useFPSMonitor.js):
* **Fidelity Downgrades**: If frame rates drop below **45 FPS** (`lowPerf = true`), the rendering pipeline dynamically:
  * Disables antialiasing on the canvas: `gl={{ antialias: !lowPerf }}`.
  * Hides mouse-following lighting and cursor flashlight passes.
  * Reduces tag connection threads per node from 4 to 2.
  * Diminishes particle density on the orbiting background field from 2,000 to 400.

---

## Reciprocal Rank Fusion (RRF) & Caching

Recall combines semantic similarity and keyword relevance in a single database RRF compiler:
* **Hybrid Search Query**: Unifies `direct_vector` HNSW search, `chunk_vector` child lookup, and GIN trigram `text_search` in a CTE, sorting by `1 / (rank + 60)`.
* **Redis Graph Caching**: Mind map responses are serialized to `graph:{user_id}` and cached.
* **Cache Invalidation Policy**: Whenever a user modifies, adds, uploads, or deletes an item/note, the backend executes `await redis.delete(f"graph:{user_id}")` to force a cached refresh.

---

## Ingest Deduplication & Cascading Triggers

* **Deduplication (`idx_items_content_hash`)**: We compute SHA-256 hashes of incoming documents. A B-Tree index on `(user_id, content_hash)` prevents redundant model calculations by identifying duplicates instantly on ingestion.
* **Cascading Triggers**: Since partitioned tables require composite primary keys `(id, created_at)`, simple foreign keys `ON DELETE CASCADE` cannot bind to the child `item_chunks` table. Instead, a custom PL/pgSQL trigger `trigger_cascade_delete_item_chunks` executes chunk removal atomically whenever an item is deleted.

---

## Rate Limiting & Timeout Guards

* **Rate Limits**: Expensive API paths (such as `/api/pulse` or detailed profile calculations) are decorated with Upstash Redis rate-limiter dependencies to prevent API exhaustion.
* **Timeout Enforcement**: All external LLM and transcription requests specify strict timeouts (e.g. `timeout=15.0` or `10.0` seconds) inside `ai_cascade.py` to prevent thread hangs during service degradation.

