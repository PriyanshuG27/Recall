> **Audience**: Backend Engineers, Frontend Developers, Integrators  
> **Estimated Reading Time**: 12 min

# API

Recall exposes API endpoints across 5 FastAPI routers (`api.py`, `auth.py`, `webhook.py`, `websocket.py`, `main.py`).

---

## 1. Authentication Router (`backend/routes/auth.py`)

### `GET /auth/telegram`
* **Purpose**: Telegram Web Widget login verification.
* **Authentication**: Query parameters signed with bot token.
* **Implementation Files**: `routes/auth.py`, `services/user_service.py`.
* **Related Tables**: `users`.
* **Related Pages**: `/login`.

**Request**: `GET /auth/telegram?id=123456&first_name=Alex&hash=abc123...`  
**Success Response**: `HTTP 307 Temporary Redirect` -> `/archive` (Sets `recall_session` & `jwt` httpOnly cookies).  
**Common Errors**: `401 Unauthorized` (Invalid signature).

---

## 2. Items & Media Router (`backend/routes/api.py`)

### `POST /api/items`
* **Purpose**: Create a new knowledge item directly.
* **Authentication**: JWT Cookie / Session (`get_current_user`).
* **Implementation Files**: `routes/api.py`, `services/ai_cascade.py`.
* **Related Tables**: `items`.
* **Related Pages**: `/archive`, `/map`.

**Request Example**:
```json
{
  "text": "Deep learning research paper on transformers",
  "source_type": "text"
}
```

**Response Example (HTTP 201 Created)**:
```json
{
  "id": 183,
  "summary": "Deep learning research paper on transformers",
  "source_type": "text",
  "tags": ["ai", "research"],
  "created_at": "2026-07-04T17:50:00Z"
}
```

**Common Errors**:
* `401 Unauthorized`: Session missing or expired.
* `422 Unprocessable Entity`: Missing required `text` field.

---

### `POST /api/search`
* **Purpose**: Execute hybrid vector + trigram search with conversational RAG Q&A.
* **Authentication**: JWT Cookie / Session.
* **Implementation Files**: `services/search_service.py`, `services/ai_cascade.py`.
* **Related Tables**: `items`, `item_chunks`.
* **Related Components**: `ChatDrawer.jsx`, `SearchOverlay.jsx`.

**Request Example**:
```json
{
  "query": "explain vector index parameters",
  "limit": 5
}
```

**Response Example (HTTP 200 OK)**:
```json
{
  "answer": "HNSW vector indexes use m=16 and ef_construction=64 for sub-10ms cosine search [1].",
  "sources": [
    {
      "id": 42,
      "summary": "Database Schema Notes",
      "citation_index": 1
    }
  ]
}
```

---

## 3. Spaced Repetition SM-2 Router (`backend/routes/api.py`)

### `GET /api/quizzes/due`
* **Purpose**: Fetch flashcards due for active recall review.
* **Authentication**: JWT Cookie / Session.
* **Implementation Files**: `services/sm2.py`, `routes/api.py`.
* **Related Tables**: `quizzes`, `items`.
* **Related Pages**: `/drill` (`Drill.jsx`, `TransmissionCard.jsx`).

**Response Example (HTTP 200 OK)**:
```json
[
  {
    "id": 12,
    "question": "What is the vector dimension in Recall?",
    "options": ["1536", "384", "768"],
    "answer": "384",
    "ease_factor": 2.5,
    "interval_days": 1
  }
]
```

---

### `POST /api/quizzes/{id}/answer`
* **Purpose**: Submit review rating (0=Again, 3=Shaky, 5=Locked) to update SM-2 interval.
* **Authentication**: JWT Cookie / Session.

**Request Example**:
```json
{
  "quality": 5
}
```

**Response Example (HTTP 200 OK)**:
```json
{
  "id": 12,
  "ease_factor": 2.6,
  "interval_days": 6,
  "next_review": "2026-07-10"
}
```
---

## 4. System & Webhook Endpoints

### `POST /webhook`
* **Purpose**: Telegram bot webhook listener.
* **Authentication**: Signed Telegram header.
* **Response**: `{"status": "ok"}` (Returned in **< 50 ms**).


---

← [Database](DATABASE.md) | [Features](FEATURES.md) →

## Related Documentation

[README](../README.md) · [Index](INDEX.md) · [Architecture](ARCHITECTURE.md) · [Database](DATABASE.md) · **API** · [Features](FEATURES.md)  
[Development](DEVELOPMENT.md) · [Deployment](DEPLOYMENT.md) · [Security](SECURITY.md) · [Testing](TESTING.md) · [Contributing](CONTRIBUTING.md) · [Diagrams](DIAGRAMS.md) · [ADRs](adr/README.md)
