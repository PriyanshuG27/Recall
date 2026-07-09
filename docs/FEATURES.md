> **Audience**: Product Managers, Contributors, Reviewers  
> **Estimated Reading Time**: 6 min

# Features

Capabilities in **Recall** are classified across 5 status levels:

* ✅ **Production**: Fully implemented, tested, and actively reachable.
* ⚠ **Partial**: Implemented in code but requires external credentials.
* 🧪 **Active Development**: Functional implementation under active development or hidden from nav.
* ❌ **Legacy**: Path redirects maintained for backward compatibility.
* 💀 **Dead Code**: Unreferenced or unapplied files.

---

## Capabilities Specification Matrix

| Feature | Status | Implementation Files | Value & Description |
|---|---|---|---|
| **Telegram Ingestion** | ✅ Production | `routes/webhook.py`<br>`worker.py` | Ingest voice notes, screenshots, PDFs, URLs, text via Telegram (`@<YourBotUsername>`). |
| **Multi-Format Parsing** | ✅ Production | `services/*_ingester.py` | Media scrapers for URLs, YouTube/Instagram reels via Cobalt API, PyMuPDF PDF chunking, OpenCV OCR. |
| **Hybrid Search & RAG** | ✅ Production | `services/search_service.py` | Combined 384-dim `pgvector` HNSW cosine search (< 10ms) and `pg_trgm` GIN trigram search (< 5ms) via RRF. |
| **AI Cascade** | ✅ Production | `services/ai_cascade.py` | Multi-provider LLM failover. Summarization/RAG: Groq -> Gemini -> OpenRouter -> Bookmark Fallback. |
| **OCR Preprocessing** | ✅ Production | `services/ocr_service.py` | Image/PDF OCR utilizing NVIDIA NIM OCR as the primary engine, with Gemini 2.5 Flash as the fallback. |
| **3D Observatory** | ✅ Production | `pages/Map.jsx`<br>`canvas/MapCanvas.jsx` | Force-directed 2D/3D constellation mind map (`/map`) and glass archive cylinder (`/archive`). |
| **Interactive Citations** | ✅ Production | `components/ChatDrawer.jsx` | Clicking RAG citation badges (`[1]`, `[2]`) animates camera focus to center on cited item with aura flare. |
| **Spaced Repetition SM-2** | ✅ Production | `pages/Drill.jsx`<br>`services/sm2.py` | Active recall review room (`/drill`) updating SuperMemo-2 ease factors and review intervals. |
| **Obsidian OKF Sync** | ✅ Production | `services/okf_service.py` | Export (`GET /api/export/zip`) & Import (`POST /api/import/zip`) Markdown ZIP archives formatted as OKF. |
| **WebSocket Sync** | ✅ Production | `routes/websocket.py` | Upstash Redis pub/sub real-time event channel (`new_node`, `google_connected`). |
| **APScheduler Jobs** | ✅ Production | `scheduler/scheduler.py` | 22 background cron jobs with `misfire_grace_time=60` (reminders, Louvain clustering, daily digests). |
| **Fernet Encryption** | ✅ Production | `services/encryption.py` | Cryptographic encryption at rest for `items.raw_text` and `users.google_refresh_token`. |
| **Dead Letter Queue** | ✅ Production | `services/dlq.py` | Failover table (`dead_letter_queue`) logging failed task payloads with boot auto-retry. |
| **Google Drive Sync** | ✅ Production | `services/drive_sync.py` | One-click Google Docs backup (`POST /api/drive/sync`) with OAuth2 token refresh & Fernet encryption. |
| **PWA Share Target** | ✅ Production | `routes/api.py` | Web Share Target API handler (`POST /api/share-target`) for mobile native share sheet integration. |
| **Cognitive Bridges** | 💀 Dead Code | None (Superseded by Hearth) | Superseded by Hearth (v1). Compatibility/kintsugi visualization deferred post-launch. |
| **Branching POC (`/poc/branching`)** | 🧪 Active Development | `pages/BranchingPOC.jsx` | Isolated proof-of-concept for visual node branching on top of the mind graph. |
| **Nebula Route (`/nebula`)** | ❌ Legacy | `App.jsx:L29` | Hard redirects to `/map`. `Nebula.jsx` component is unrendered legacy code. |
| **Dashboard Route (`/dashboard`)** | ❌ Legacy | `App.jsx:L280` | Hard redirects to `/archive`. `Dashboard.jsx` component is unrendered legacy code. |
| **Unused Pages (`Feed`, `Reminders`)** | ❌ Legacy / Unused | `pages/` | Unreachable from router or navigation. Reminders integrated into Settings. |
| **YouTube Patch File** | 💀 Dead Code | `services/` | `youtube_ingester_diff.txt` unapplied git patch file. |


---

← [API](API.md) | [Development](DEVELOPMENT.md) →

## Related Documentation

[README](../README.md) · [Index](INDEX.md) · [Architecture](ARCHITECTURE.md) · [Database](DATABASE.md) · [API](API.md) · **Features**  
[Development](DEVELOPMENT.md) · [Deployment](DEPLOYMENT.md) · [Security](SECURITY.md) · [Testing](TESTING.md) · [Contributing](CONTRIBUTING.md) · [Diagrams](DIAGRAMS.md) · [ADRs](adr/README.md)
