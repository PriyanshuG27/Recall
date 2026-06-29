# Recall Phase 2: Urgency, Verification, and Loop Pipeline Completion Report

This document outlines the successful implementation, testing, and delivery of all Phase 2 features in the Recall codebase.

---

## 1. Features Implemented

### Dynamic AI Mood-Angled Generation
* Rotates prompts dynamically using 8 distinct psychological angles: `curiosity`, `timing`, `future`, `friction`, `identity`, `connection`, `stakes`, `surprise`.
* Maintains a history of the last 4 used variants per user in Redis to prevent repeats.
* Uses an epsilon-greedy algorithm (70% exploitation of highest-scoring mood based on reply length, 30% exploration of other eligible moods).
* Updates the system prompt in `ai_cascade.py` and utilizes `contextvars.ContextVar` to propagate the chosen mood category to all ingesters without signature changes.

### Zero-Compute Drift Expiries & Ignore Checks
* Implements task-level ignore tracking. Three consecutive ignored prompts trigger a context prompt pause for the next 5 saves.
* Ingestion skips prompts and decrements the pause counter while active.
* Replying to a prompt resets consecutive ignores and adds the reply length score to the mood variant in Redis.
* Integrates drift expiry scheduling (`drift:{cand_id}`) into the existing Redis Sorted Set (`reminders:active`), keeping additional checks at 0 network/compute overhead.

### Nightly Scan & Mystery Cron Loops
* Evaluates cross-cluster similarity ($\ge 0.60$) for items saved $\ge 14$ days apart.
* Filters out hub duplicates and implements a 60-day MD5 pair novelty check.
* **Morning Mystery** (8:00 AM local time): Delivers morning stats, delivers the mystery clue, marks candidates as `delivered`, and sets a 12-hour expiry.
* **Evening Answer** (8:00 PM local time): Generates a tension connection insight using the LLM cascade, marks it as `confirmed`, and sends the resolution to the user.
* **Dispatcher Sweep**: Expired candidates are updated to `expired` status in the DB and cleared from Redis.

### Conversational Graph RAG Interface (Section 8.6)
* **Question Interception**: Real-time webhook interception of question messages (using `?` and starting word heuristics), routing them to RAG search without creating a new node or entering the debouncer queue.
* **pgvector Search**: Implements `rag_semantic_search` in `search_service.py` to query the user's saved items using HNSW cosine distance, returning the top 8–12 context matches.
* **Structured RAG Prompt & Quality Gates**: Synthesizes a 2-4 sentence answer in `ai_cascade.py` grounded strictly in retrieved items. Requires literal title citations, prevents clinical/psychological terminology, and rejects template phrases (e.g. *"You seem interested in..."*).
* **HTML Delivery Mode**: Safely HTML-escapes content and converts double asterisks to bold tags, preventing Telegram parsing errors on underscores in filenames like `file_33.pdf`.

---

## 2. Testing and Regression Verification

All tests run completely offline with zero external API calls or network leaks.
* **New Tests**: `test_conversational_rag.py`, `test_context_rotation.py`, and `test_insight_pipeline.py` verify all logic, parameters, and cron operations.
* **Regression Checks**: Run full test suite with 100% success.
  ```bash
  $ pytest
  ===================== 348 passed in 23.70s ======================
  ```

---

## 3. Manual Verification Steps
Please refer to the walkthrough file [walkthrough.md](file:///C:/Users/pri27/.gemini/antigravity/brain/8ef787b4-e243-4191-aef5-2b553c3bff40/walkthrough.md) for step-by-step instructions on verifying the changes in your local Telegram and DB testing environment.
