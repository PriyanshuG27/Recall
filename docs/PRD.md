# PRD — Recall

| Field | Value |
|-------|-------|
| Version | 0.1.0 |
| Date | 2026-06-19 |
| Status | Draft |
| Owner | Recall Core Team |

---

## Executive Summary

Recall is a Telegram-first AI knowledge management bot with a companion web dashboard. Users forward any content—links, voice notes, PDFs, images, YouTube/Instagram videos—and Recall automatically transcribes, summarises, embeds, and maps everything into a searchable constellation-style mind map. The system runs entirely on free-tier infrastructure.

---

## Problem Statement

Knowledge workers and students encounter valuable content throughout the day but lack friction-free capture. Existing tools (Notion, Readwise, Obsidian) require deliberate switching and manual tagging. Content saved without structure is effectively lost. The gap: **zero-friction capture + automatic organisation + active recall**.

---

## Target Users

| Persona | Description | Primary Pain |
|---------|-------------|--------------|
| Student | Captures lecture notes, research papers, YouTube explainers | No time to organise; forgets 90% within a week |
| Knowledge Worker | Saves articles, podcasts, voice memos between meetings | Disparate apps, no connections surfaced |
| Content Creator | Tracks Instagram/YouTube inspiration, voice braindumps | Cannot find saved ideas when needed |
| Developer (early adopter) | Heavy Telegram user; comfortable with bots | Wants powerful capture without leaving Telegram |

---

## Product Goals

### User Goals
- Capture any content in under 3 seconds.
- Find any saved item in seconds using natural language.
- Rediscover forgotten knowledge through daily quizzes and visual clustering.

### Portfolio / Builder Goals
- Demonstrate end-to-end AI system design (ingestion, embedding, retrieval, spaced repetition).
- Ship a production system on $0 infrastructure budget.
- Showcase WebSocket + Canvas constellation UI as a portfolio centrepiece.

---

## Success Metrics

| Metric | Target | Measurement Method |
|--------|--------|--------------------|
| Capture latency (p95) | < 50 ms webhook ACK | Render request logs |
| AI processing time (p95) | < 15 s per item | APScheduler + task timestamps |
| Semantic search relevance | Top-3 correct hit >= 80% | Manual eval set (50 queries) |
| Webhook reliability | >= 99.5% idempotent processing | processed_updates collision rate |
| DAU retention (D7) | >= 40% | DB query on last_activity_date |
| Quiz completion rate | >= 60% of due quizzes answered | quizzes.next_review vs answered count |
| Cold start avoidance | 0 Render cold starts per day | Uptime Robot alert history |

---

## Feature Inventory

### MVP (Phases 1-4)

| Feature | Description |
|---------|-------------|
| Telegram webhook ingestion | Receive text, URL, voice, PDF, image via bot |
| AI cascade processing | Whisper -> Llama 3 -> summary + embedding, 5-tier fallback |
| PostgreSQL storage | Encrypted raw_text, partitioned items table |
| Semantic search | pgvector HNSW + GIN trigram hybrid search |
| Mind map (Canvas) | Force-directed constellation, 60 FPS |
| Telegram-only auth | chat_id identity + TWA HMAC verification |

### Post-MVP (Phases 5-8)

| Feature | Phase | Description |
|---------|-------|-------------|
| Web dashboard | 5 | React/Vite with Telegram Login Widget JWT auth |
| WebSocket graph updates | 5 | Real-time node additions without refresh |
| Spaced repetition | 6 | SM-2 quiz generation and scheduling |
| Daily streak + nudges | 6 | Streak counter + Drive connect nudge |
| Google Drive sync | 7 | Export items to user's Drive (drive.file scope) |
| Chrome extension | 8 | One-click capture from browser |
| Louvain clustering (hubs) | 6 | Daily graph clustering -> semantic_hubs |

---

## Non-Goals

- **E2EE** — Server processes plaintext during embedding; no end-to-end encryption claim.
- **Team / collaborative workspaces** — Single-user knowledge graph only (v1).
- **Native mobile app** — Telegram TWA covers mobile surface; no separate iOS/Android app.
- **Custom domain storage** — Items stored in Recall DB only; Drive sync is export, not primary store.
- **Real-time collaborative editing** — No multiplayer features.
- **Billing / monetisation** — Free-tier infrastructure only; no payment integration in scope.
