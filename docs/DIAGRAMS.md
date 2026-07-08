> **Audience**: System Architects, Developers, Reviewers  
> **Estimated Reading Time**: 7 min

# Diagrams

This document serves as the visual reference repository containing all **10 verified Mermaid diagrams** for **Recall**.

---

## 1. System Architecture Diagram
*(Explains overall multi-tier client, API router, worker queue, database, and AI cascade interaction)*

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
        AI["AI Cascade Engine
(Groq / Gemini / Modal)"]
    end

    TG --> HOOK
    WEB --> AUTH
    WEB --> ITEMS
    WEB <--> WS
    EXT --> ITEMS
    SHARE --> ITEMS

    HOOK -- "< 50ms ACK" --> REDIS
    REDIS --> WORKER
    WORKER --> AI
    WORKER --> DB
    WORKER -- "On Failure" --> DLQ
    SCHED --> DB
    SCHED --> REDIS
```

---

## 2. Content Ingestion Pipeline Diagram
```mermaid
flowchart TD
    A["Raw Content Input
(Text / Voice / Image / PDF / URL)"] --> B{"Source Type?"}
    
    B -- "Voice / Audio" --> C1["Voice Ingester
(voice_ingester.py)"]
    C1 --> C2["Groq Whisper Turbo
(Fallback: Modal / Gemini)"]
    C2 --> C3["Phonetic Sanitizer
(sanitize_transcript)"]
    
    B -- "Image / Document" --> D1["OCR Worker
(ocr_worker.py)"]
    D1 --> D2["OpenCV + PaddleOCR
(Threshold >= 60%)"]
    D2 -- "< 10 words" --> D3["Gemini Vision Fallback"]
    
    B -- "PDF Document" --> E1["PDF Ingester
(pdf_ingester.py)"]
    E1 --> E2["PyMuPDF Chunking
(300-word chunks)"]
    E2 --> E3["Store Chunks in
item_chunks table"]

    B -- "Web URL / Media" --> F1["URL Ingester
(url_ingester.py)"]
    F1 --> F2["Cobalt API / ScraperAPI
Extract OpenGraph & Text"]

    C3 --> G["AI Cascade Engine
(ai_cascade.py)"]
    D2 --> G
    D3 --> G
    E3 --> G
    F2 --> G

    G --> H1["Modal GPU Endpoint"]
    H1 -- "Failover" --> H2["Groq 3-Tier Rotation
(Qwen 27B / GPT-OSS 120B / 20B)"]
    H2 -- "Failover" --> H3["Gemini 3.1 Flash-Lite"]
    H3 -- "On Failure" --> H4["Bookmark Fallback / DLQ"]

    H1 --> I["Generate Summary & Tags"]
    H2 --> I
    H3 --> I

    I --> J["Generate 384-dim Vector
(BAAI/bge-small-en-v1.5)"]
    J --> K["Fernet Encrypt raw_text"]
    K --> L["Save to items table
(Partitioned by Range)"]
```

---

## 3. Database Entity-Relationship Diagram
```mermaid
erDiagram
    users ||--o{ items : "owns"
    users ||--o{ quizzes : "owns"
    users ||--o{ reminders : "owns"
    users ||--o{ semantic_hubs : "owns"
    users ||--o{ dead_letter_queue : "owns"
    items ||--o{ item_chunks : "partitioned cascade delete"
    quizzes ||--o{ quiz_answers : "tracks"

    users {
        int id PK
        string telegram_chat_id UK
        string google_refresh_token "Fernet Encrypted"
        int streak_count
        numeric pulse_score
    }

    items {
        int id PK
        int user_id FK
        string source_type
        string raw_text "Fernet Encrypted"
        string summary "GIN Trigram Indexed"
        vector_384 embedding "HNSW Cosine Indexed"
        timestamp created_at PK
    }
```


---

← [Testing](TESTING.md) | [ADRs](adr/README.md) →

## Related Documentation

[README](../README.md) · [Index](INDEX.md) · [Architecture](ARCHITECTURE.md) · [Database](DATABASE.md) · [API](API.md) · [Features](FEATURES.md)  
[Development](DEVELOPMENT.md) · [Deployment](DEPLOYMENT.md) · [Security](SECURITY.md) · [Testing](TESTING.md) · [Contributing](CONTRIBUTING.md) · **Diagrams** · [ADRs](adr/README.md)
