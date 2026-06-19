# APP_FLOW — Recall

| Field | Value |
|-------|-------|
| Version | 0.1.0 |
| Date | 2026-06-19 |
| Status | Draft |

---

## Entry Points

Recall has two entry surfaces. Both converge on the same backend and data store.

```
┌───────────────────────┐     ┌──────────────────────────┐
│   Telegram Bot        │     │   Web Dashboard / TWA    │
│   (primary surface)   │     │   (secondary surface)    │
└──────────┬────────────┘     └─────────────┬────────────┘
           │                                │
           └─────────────┬──────────────────┘
                         ▼
                  FastAPI Backend
```

---

## First-Touch Onboarding

```
User finds @RecallBot on Telegram
    -> Sends /start
    -> Bot creates users row (telegram_chat_id = chat.id)
    -> Bot replies: welcome message + supported commands list
    -> User sends first item (any type)
```

No sign-up form. No email. Identity = Telegram chat_id.

---

## Content Ingestion Flows

### URL

```
User sends URL
    -> webhook received
    -> BeautifulSoup scrape -> clean text
    -> AI Cascade: embedding + summary
    -> INSERT items (source_type='url')
    -> Bot replies: title + 2-sentence summary + tags
```

### Voice Note / Audio

```
User sends voice note (or audio file)
    -> yt-dlp downloads audio stream
    -> AI Cascade Tier 0: Modal Whisper large-v3 transcription
       (fallback: Groq Whisper -> Gemini STT)
    -> Transcribed text -> Llama 3 summary + quiz generation
    -> Embedding via MiniLM-L6-v2
    -> INSERT items (source_type='voice') + INSERT quizzes
    -> Bot replies: transcript excerpt + summary
```

### YouTube / Instagram URL

```
User sends YouTube or Instagram URL
    -> yt-dlp downloads audio track
       (Instagram: ZenRows -> ScrapingBee -> ScraperAPI -> yt-dlp -> bookmark fallback. Ingestion engine must handle cookie rotation and user-agent spoofing robustly from Day 1.)
    -> Whisper transcription (same cascade as voice)
    -> Summary + embedding
    -> INSERT items (source_type='url', source_url set)
    -> Bot replies: video title + summary
```

### PDF

```
User sends PDF file
    -> PyMuPDF extracts text (page by page)
    -> Text chunked (max 512 tokens/chunk)
    -> Each chunk embedded via MiniLM
    -> Llama 3 produces full document summary
    -> INSERT items (source_type='pdf', one row per document)
    -> Bot replies: document title + summary + page count
```

### Image

```
User sends image
    -> Tesseract OCR -> extracted text
    -> MiniLM embedding on OCR text
    -> Llama 3 summary if text > 50 chars; else caption only
    -> INSERT items (source_type='image')
    -> Bot replies: extracted text preview + summary
```

### Plain Text

```
User sends text message (not a URL)
    -> Direct to MiniLM embedding
    -> Llama 3 summary (if > 100 chars)
    -> INSERT items (source_type='text')
    -> Bot replies: confirmation + generated tags
```

---

## Search Flow

```
User sends /search <query>
    -> Backend: MiniLM embeds query -> 384-dim vector
    -> pgvector HNSW cosine search (top-10 candidates)
    -> GIN trigram filter on summary (rerank by text relevance)
    -> Merge results (RRF or score sum)
    -> Return top-5 items
    -> Bot replies: numbered list with title, summary snippet, source_type icon
```

Web dashboard search:
```
User types in search bar (debounce 300 ms)
    -> POST /api/search
    -> Same vector + keyword hybrid pipeline
    -> Results rendered as card list; clicking node highlights it in mind map
```

---

## Mind Map Flow

```
Web dashboard loads
    -> GET /api/graph
    -> Returns nodes (items) + edges (cosine similarity > threshold)
    -> Canvas renders force-directed graph (constellation aesthetic)
    -> WS /ws/{token} open
        -> New item saved -> WS pushes {type: "new_node", node: {...}}
        -> Canvas animates: node pulse + gravitational ripple
        -> Louvain clustering update -> hub nodes re-rendered

Node types:
    orbital  — standard item node
    hub      — Louvain centroid (semantic_hubs)
    pulse    — recently added (< 5 min)

Interactions:
    Click node    -> side panel: title, summary, source link, tags
    Click hub     -> highlight all member nodes
    Scroll/pinch  -> zoom canvas
    Drag          -> pan canvas
```

---

## Daily Use Loop

```
Morning:
    APScheduler fires quiz reminders
    -> Bot sends /quiz_due notification
    -> User answers inline keyboard options
    -> SM-2 interval updated

Throughout day:
    User forwards content (any type)
    -> Background processing
    -> Bot acknowledges within seconds

Evening:
    User views mind map on web dashboard
    -> New nodes visible
    -> Hubs updated if >= 10 new items since last clustering
```
