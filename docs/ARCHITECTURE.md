> **Audience**: System Architects, Maintainers, Core Developers  
> **Estimated Reading Time**: 12 min

# Architecture

Recall is a multi-tier personal knowledge OS & 3D Observatory. This document details component responsibilities, ingestion request lifecycles, hybrid search retrieval, and queue architecture.

---

## 1. System Overview & Component Layering

```mermaid
flowchart TB
    subgraph Clients["Ingestion & Client Layer"]
        TG["Telegram Bot App
(@<YourBotUsername>)"]
        WEB["React SPA
(Vite 6 / Port 5173)"]
        EXT["Chrome Web Clipper
(Extension Popup)"]
        SHARE["Mobile Share Target
(/api/share-target)"]
    end

    subgraph API["FastAPI Application Layer (backend/main.py)"]
        AUTH["Auth Router
        (backend/routes/auth.py)"]
        ITEMS["API Router
        (backend/routes/api.py)"]
        HOOK["Webhook Handler
        (backend/routes/webhook.py)"]
        WS["WebSocket Router
        (backend/routes/websocket.py)"]
    end

    subgraph Workers["Background Queue & Processing"]
        REDIS["Upstash Redis Queue
        (recall:tasks)"]
        WORKER["Async Worker Loop
        (backend/worker.py
        Semaphore: 3)"]
        SCHED["APScheduler Engine
        (backend/scheduler/scheduler.py
        22 Cron Jobs)"]
    end

    subgraph Storage["Data & Pipeline Layer"]
        DB[(Neon PostgreSQL 16
        pgvector + pg_trgm)]
        DLQ[(Dead Letter Queue
        dead_letter_queue table)]
        AI_CASCADE["AI Cascade Engine
        (Groq / Gemini / OpenRouter)"]
        AI_SVC["Azure AI Service VM
        (FastEmbed / Reranker / spaCy)"]
    end

    TG --> HOOK
    WEB --> AUTH
    WEB --> ITEMS
    WEB <--> WS
    EXT --> ITEMS
    SHARE --> ITEMS

    HOOK -- "< 50ms ACK" --> REDIS
    REDIS --> WORKER
    WORKER --> AI_CASCADE
    WORKER --> AI_SVC
    WORKER --> DB
    WORKER -- "On Failure" --> DLQ
    SCHED --> DB
    SCHED --> REDIS
```

---

## 2. Request Sequence Diagrams

### Ingestion Sequence: Telegram → Queue → Worker → AI → DB → WebSocket

```mermaid
sequenceDiagram
    autonumber
    participant User as User (Telegram)
    participant Hook as Webhook Router (webhook.py)
    participant Redis as Upstash Redis (recall:tasks)
    participant Worker as Async Worker (worker.py)
    participant Nvidia as NVIDIA NIM (Primary OCR)
    participant Gemini as Gemini API (OCR Fallback / Summarization)
    participant AzureVM as Azure AI Service (Embeddings)
    participant DB as Neon PostgreSQL (items)
    participant WS as WebSocket Router (websocket.py)
    participant SPA as React SPA (App.jsx)

    User->>Hook: Send voice note / text / link
    Hook->>Redis: Push task JSON to recall:tasks
    Hook-->>User: Return HTTP 200 ACK (< 50 ms)
    
    Worker->>Redis: brpoplpush recall:tasks recall:processing
    Worker->>Nvidia: Extract OCR Text (Image/PDF)
    Nvidia-->>Worker: OCR Text (or low confidence failover)
    opt Low Confidence / Empty OCR
        Worker->>Gemini: OCR Fallback (Gemini 2.5 Flash)
        Gemini-->>Worker: Extracted text
    end
    Worker->>Gemini: Summarize & Extract Tags
    Gemini-->>Worker: Summary + Tags
    Worker->>AzureVM: Generate 384-dim Embedding
    AzureVM-->>Worker: Vector (384)
    Worker->>DB: Fernet encrypt raw_text & INSERT item
    Worker->>Redis: Publish event to ws:connections:user:{id}
    Redis->>WS: Push new_node event
    WS-->>SPA: Stream WebSocket event -> new node & trigger toast
```

---

### Hybrid Search & RAG Retrieval Sequence

```mermaid
sequenceDiagram
    autonumber
    participant SPA as React SPA (ChatDrawer.jsx)
    participant API as API Router (api.py)
    participant Search as Search Service (search_service.py)
    participant DB as Neon PostgreSQL
    participant AI as AI Cascade (ai_cascade.py)

    SPA->>API: POST /api/search {query: "quantum computing"}
    API->>Search: Execute hybrid retrieval
    
    par Vector Search Path (HNSW Cosine)
        Search->>DB: Query VECTOR(384) embedding <=> query_vec (< 10ms)
    and Trigram Search Path (GIN Trigram)
        Search->>DB: Query summary gin_trgm_ops similarity (< 5ms)
    end
    
    DB-->>Search: Return vector & text matches
    Search->>Search: Compute Reciprocal Rank Fusion (RRF) scores
    Search->>AI: Generate RAG response with source citations [1], [2]
    AI-->>SPA: Return structured markdown answer + source citations
```

---

## 3. Worker Queue & Concurrency Design

* **Task Queue**: Upstash Redis REST list key `recall:tasks`.
* **Atomic Processing**: Worker uses `brpoplpush("recall:tasks", "recall:processing")` guaranteeing zero task loss on worker crash.
* **Concurrency Semaphore**: `worker_semaphore = asyncio.Semaphore(3)` caps concurrent AI tasks.
* **Dead Letter Queue**: Exceptions write failure payloads to `dead_letter_queue` table ([dlq.py](../backend/services/dlq.py)). Startup lifespan re-enqueues unretried tasks failed < 24h ago.
* **Background Scheduler**: 22 background cron jobs running in APScheduler with `misfire_grace_time=60`.
* **Single-Process Deployment**: In production (Koyeb free tier), the FastAPI web server, background queue worker loop, and APScheduler are consolidated inside a single service container (using `RUN_WORKER_INLINE=true`) to run at low RAM footprint (~150-300 MB) without sacrificing asynchronous task execution.


---

← [Index](INDEX.md) | [Database](DATABASE.md) →

## Related Documentation

[README](../README.md) · [Index](INDEX.md) · **Architecture** · [Database](DATABASE.md) · [API](API.md) · [Features](FEATURES.md)  
[Development](DEVELOPMENT.md) · [Deployment](DEPLOYMENT.md) · [Security](SECURITY.md) · [Testing](TESTING.md) · [Contributing](CONTRIBUTING.md) · [Diagrams](DIAGRAMS.md) · [ADRs](adr/README.md)
