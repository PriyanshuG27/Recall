# Phase 2 Completion Report — Recall

This document details the completed implementation of **Phase 2 (Ingestion Pipeline & AI Cascade)** for the Recall AI-powered Second Brain.

Phase 2 builds the ingestion engines, queue handlers, fallback AI processing (AI Cascade), vector embedding integration, content deduplication, and administrator dead-letter tools.

---

## 1. Prompt Mapping & Completion Status
The following table maps the requirements from the Phase 2 prompt roadmap to their Pydantic/FastAPI prompt numbers, code locations, and completion status.

| SS # | Playbook Prompt | Feature / Component | Code Files | Status |
| :--- | :--- | :--- | :--- | :--- |
| **017** | **PROMPT 020** | Text Ingestion + Task Worker Loop | `backend/worker.py` | **Completed** |
| **018** | **PROMPT 030** | Voice Note Ingestion | `backend/services/voice_ingester.py` | **Completed** |
| **019** | **PROMPT 046** | URL Ingestion: Scraping + Save | `backend/services/url_ingester.py` | **Completed** |
| **020** | **PROMPT 043 / 045** | Image Ingestion + OCR Preprocessing | `backend/services/image_ingester.py` | **Completed** |
| **021** | **PROMPT 031 / 034** | PDF Ingestion & Chunking | `backend/services/pdf_ingester.py` | **Completed** |
| **022** | **PROMPT 035** | YouTube URL Pipeline | `backend/services/youtube_ingester.py` | **Completed** |
| **023** | **PROMPT 022** | Modal Whisper Endpoint (Tier 0 STT) | `backend/modal_apps/` | *Deferred to Prod* (Local/APIs active) |
| **024** | **PROMPT 029** | AI Cascade Service | `backend/services/ai_cascade.py` | **Completed** |
| **025** | **PROMPT 048** | Content Deduplication | `backend/worker.py`, `backend/services/voice_ingester.py`, `backend/services/image_ingester.py`, `backend/services/pdf_ingester.py` | **Completed** |
| **026** | **PROMPT 053** | Embedding Pipeline Integration | `backend/services/ai_cascade.py` (MiniLM v2) | **Completed** |
| **027** | **PROMPT 049 / 052** | Redis Queue Monitoring + DLQ Retries | `backend/services/dlq.py`, `backend/routes/api.py` | **Completed** |

---

## 2. Ingestion Pipeline Details

### A. Background Task Loop & Text Ingestion (017)
* **Pipelined Tasks**: Implemented an async loop in `backend/worker.py` pulling tasks from the Upstash Redis list (`recall:tasks`) using `brpop`.
* **FastAPI Lifespan Startup**: Task worker starts on server lifespan startup.
* **Concurrency Protection**: Access to the AI processing tier is strictly managed via `asyncio.Semaphore(3)`, preventing resource starvation.
* **Text Save**: Saves plaintext text forwards after Fernet encrypting the content under `items.raw_text`.

### B. Voice Note & Audio Ingestion (018)
* **Downloads & Audio Extract**: Calls `bot.getFile` to download voice notes and audio files from Telegram directly to local ephemeral storage in `backend/tmp/`. Dynamically determines the file extension (e.g., `.ogg`, `.mp3`, `.m4a`, `.wav`, `.aac`, `.flac`) from Telegram's file path.
* **Cascade transcription**: Audio is transcribed via `AICascade` (sending the correct dynamic MIME type payload to Groq or Gemini transcription API) and summarized. Supports native voice notes, direct audio attachments, and generic files with audio MIME types.
* **Cleanup**: Guarantees file deletion from disk in `finally` blocks to prevent disk leaks.

### C. URL Ingestion & Scraping (019)
* **Scraper**: Plain web URLs are scraped using `httpx` + `BeautifulSoup` to extract the title and readable body.
* **Google Drive Ingestion**: Detects public vs private Drive links. For private links, if the user has authenticated and connected their Google Account, it exchanges the Fernet-encrypted refresh token for an access token to download files using the Google Drive API.
* **Routing**: PDF, audio, and doc formats within Google Drive are automatically routed to the correct sub-parsers.

### D. Image Ingestion + Preprocessing (020)
* **Contrast & Quality Enhancer**: Integrates Pillow-based binarization, contrast stretching, and resizing filters to maximize Tesseract OCR readability.
* **Caption Fallback**: If Tesseract fails to extract readable text, the image is sent to Gemini (Tier 2) to auto-generate a descriptive caption as the item summary.

### E. PDF Ingestion & Chunk-level Embedding (021)
* **PyMuPDF Extraction**: Extracts text content page by page.
* **Chunking**: Chunks documents into ~400 token sentences and generates per-chunk vector representations stored in the `item_chunks` table, enabling granular semantic retrieval.

### F. YouTube URL Pipeline (022)
* **Audio Fetch**: Utilizes `yt-dlp` format filters to fetch the audio track from YouTube links (videos & shorts up to 30 minutes) and routes it to the STT transcription pipeline.

---

## 3. AI Cascade Service & Embeddings (024, 026)
* **Tiered Resilience**:
  * **Tier 0**: Local Ollama (when `LOCAL_MODE` is active) / Modal.
  * **Tier 1 (Groq API)**: 
    * **STT**: Whisper Turbo (falls back to Whisper Large-v3).
    * **LLM**: Primary model is **Qwen 3.6 27B** (`qwen/qwen3.6-27b`). If that fails, it cascades down to **GPT-OSS 120B** (`openai/gpt-oss-120b`) and then **GPT-OSS 20B** (`openai/gpt-oss-20b`) on Groq before moving to the next provider tier. Each Groq LLM call is protected by a responsive **15-second timeout** to prevent webhook hanging.
  * **Tier 2**: Gemini 3.1 Flash-Lite API.
  * **Tier 3**: Graceful fallbacks saving item as bookmark without summarization.
* **Embeddings**: Text summaries are mapped into 384-dimensional dense vectors using the MiniLM-L6-v2 model and saved to the database.
* **Hugging Face Hub Auth**: Authenticates local Hugging Face requests using the `HF_TOKEN` environment variable to ensure rate-limit-free downloads and clean logs.

---

## 4. Content Deduplication (025)
* **URL Matches**: Identifies exact duplicate URL saves per user.
* **Content Hashes (Text, Voice, Image, PDF)**: Generates unique SHA-256 hashes of content (plain text, voice note bytes, image bytes, and PDF file bytes) to prevent redundant database entries, save GPU/API credits, and return consistent Telegram feedback.

---

## 5. DLQ Retries & Health Metrics (027)
* **Reliability**: Tasks failing all AI tiers are captured in `dead_letter_queue`.
* **API Endpoints**:
  * `GET /api/admin/queue`: Monitors Redis queue length, active semaphore slots, and DLQ counts.
  * `POST /api/admin/dlq/{id}/retry`: Re-enqueues failed tasks back into the task queue and marks them as retried.
* **Security**: Both endpoints are protected by `X-Internal-Key` validation.

---

## 6. Testing Metrics & Verification
* **Pytest Coverage**: **172 unit and integration tests** passing with zero failures.
* Tests cover: URL/Text deduplication, voice/image/PDF content hash deduplication, DLQ retry enqueuing, and the full AI Cascade fallback tiers.

```text
backend\tests\test_voice_ingester.py ...                                 [ 88%]
backend\tests\test_webhook_idempotency.py ............                   [ 95%]
backend\tests\test_worker.py .....                                       [ 98%]
backend\tests\test_youtube_ingester.py ...                               [100%]

====================== 172 passed, 31 warnings in 24.77s ======================
```
