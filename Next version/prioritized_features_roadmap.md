# Recall Unified Master Backlog & Roadmap

This document serves as the single consolidated blueprint for the Recall platform. It reconciles and merges the master specification `Recall_Addiction_Architecture_v3` (v3) with the corrective psychological document `Recall_Fixed_Architecture` (Fixed), resolving all discrepancies (such as the near-miss similarity bands and the Pulse score milestone thresholds).

---

## 1. What Has Been Completed (Phases 0–3 Baseline)

The baseline frameworks for the first four phases of the Addiction Architecture have already been successfully built, verified, and unit-tested offline:

* **Phase 0 (Quality Gate)**: HARDENED the primary LLM cascade prompt templates with strict specificity rules, anti-forcing constraints, and negative examples (achieving 20/20 on Qwen/Llama and Gemini Flash fallbacks).
* **Phase 1 (Basic Ingestion & Friction-Reduction)**: Created the Redis 4-second debouncer, 3-question conversational onboarding with inline skip callbacks, single-request JSON cascade schema, pairwise similarity clustering to combined parent nodes, and completed all 4 Phase 1 backfill tasks (Passive Context Ingestion, Onboarding Callback Buttons, Mid-Graph Re-Engagement cron, Settings & Timezone Setup Integration).
* **Phase 2 (Candidate loops)**: Added `insight_candidates` table, nightly Louvain scans (cosine similarity $\ge 0.60$, saved $\ge 14$ days apart), 60-day MD5 novelty filters, the two-part Morning Mystery (8 AM) and Evening Answer (8 PM) cron loops, and dynamic AI mood-angle rotation (8 angles, epsilon-greedy variant selection, context history of 4).
* **Phase 3 (Urgency, Rhythm, and Calibrations)**: Implemented 2D Map Canvas pulsing and color-draining edge decay, PostgreSQL `save_time_bucket` categorization, weekly concentration pattern scan notifications, weekly empirical near-miss lower floor calibration (starts at 0.71, autotunes to 0.73 or 0.69 based on conversions), and randomized/jittered weekly Recall Moments (max 1 send per 7 days, randomized 10 AM–4 PM local time).

---

## 2. The 7-Phase Unified Roadmap (Phases 0 to 6)

Below is the unified implementation plan. It integrates all Part 8 mechanics (friction-reduction) and Part 6 dashboard mappings into their correct dependency-based phases:

### Phase 0: Quality Gate & Evaluator (Completed)
* **Goal**: Validate that AI-generated summaries and connection insights represent grounded, non-generic observations rather than abstract category summaries.
* **Backend**: None.
* **AI & Prompts**: Hardened Llama 3.3 70B primary system prompt and Gemini 2.5 Flash formatting constraint with few-shot examples and strict anti-forcing rules (e.g. output `NO_GENUINE_TENSION` on unrelated topics).

---

### Phase 1: Foundation, Seeding & Friction-Reduction (Completed)
* **Goal**: Minimize first-session friction, seed the initial graph structure, and capture context notes on every save.
* **Backend**: Parent table `items` has `context_note` column.
* **Redis**: Debounce batch list `batch:{chat_id}` with 4-second timer, onboarding step tracker `onboarding_step:{chat_id}`.
* **Friction & Streaks**: Global `users.streak_count` is maintained purely for backward compatibility. All addiction streak mechanics are calculated as **thinking-streaks** per cluster, derived dynamically from `semantic_hubs.last_active_at`.
* **[COMPLETED] Passive Context Metadata Ingestion (Section 8.2)**: 
  * *Backend*: Add a `passive_context` JSONB column to the `items` table.
  * *Ingestion*: Populate it at ingest with: `time_of_day` (morning/afternoon/evening/night), `day_of_week`, `prior_cluster_activity_24h` (count of saves in the last 24h), `input_method` (text, voice, link, pdf, image), and `session_gap_hours` (hours since last save). Use as weak signal fallback when `context_note` is NULL.
* **[COMPLETED] Onboarding Callback Buttons (Section 6.3)**:
  * *Telegram Bot*: Modify the onboarding Day 1 message creation in `webhook.py` to use `InlineKeyboardMarkup` callback buttons ("was this for you?" / "plan to act or share?"). Parse callback query payloads in the webhook router instead of waiting for text replies.
* **[COMPLETED] Mid-Graph Re-Engagement (Section 8.3)**:
  * *Cron Job*: Query users in the 5–30 node threshold who have been silent for exactly 5 days. Send a Telegram prompt targeting their last saved item to pull them back into the graph creation loop.
* **[COMPLETED] Onboarding Settings, Auth & Timezone Integration**:
  * *Telegram Bot*: Send a settings & setup inline keyboard card at the end of the onboarding flow (after the first-session magic scan completes).
  * *Visual Layout*:
    * Button 1: `Set Timezone ⏰` -> triggers callback query showing standard presets: GMT-8 (PST), GMT-5 (EST), GMT+0 (UTC), GMT+1 (BST/CET), GMT+5:30 (IST), GMT+8 (SGT), and a Custom select option. Updates `users.timezone_offset` (in minutes) in the database.
    * Button 2: `Web Dashboard 🌐` -> URL button linking to `settings.WEBSITE_URL`.
    * Button 3: `Backup to Drive 💾` -> URL button linking to Google OAuth URL: `f"{settings.VITE_API_URL}/auth/google?chat_id={chat_id}"`.

---

### Phase 2: Loops, Candidate Scan & Conversational RAG (Completed)
* **Goal**: Generate nightly cross-cluster candidate connections and dispatch the daily open-loop/closed-loop mystery messages.
* **Backend**: `insight_candidates` table with columns: `id`, `user_id`, `item_id_a`, `item_id_b`, `similarity_score`, `bucket`, `status`, `expires_at`, and `insight_text`.
* **Loops**: Morning Mystery clue (8 AM local, sets 12h expiry on candidate) -> Evening Answer resolution (8 PM local, LLM generates specific tension summary).
* **[COMPLETED] Conversational Graph RAG Interface (Section 8.6)**:
  * *Telegram Bot*: In `webhook.py`, detect incoming question intents (using heuristics like `?` or starting with question words).
  * *RAG Engine*: Run a semantic vector query on the user's `items` table, extract the top 8–12 context summaries, and pass them to the AI cascade to reply conversationally to the user's question without creating a new node.

---

### Phase 3: Urgency, Rhythm, and Calibrations (Completed)
* **Goal**: Establish visual urgency, calibrate near-miss thresholds, and analyze weekly save rhythms.
* **Drift Window Dashboard Decay (Section 6.2 & 7.1)**:
  * *Frontend (2D Map Canvas)*: Render decaying edges between active candidates on the 2D Mind Map (`MapCanvas.jsx`). As the 6-hour `expires_at` countdown ticks down, the edge pulses, thins, and drains color and opacity in real time.
* **Temporal Rhythm Mechanic (Section 8.4)**:
  * *Backend*: Populate `items.save_time_bucket` (morning/afternoon/evening/night).
  * *Cron Job*: Run a weekly scanner to detect time concentration patterns (e.g., "You save philosophy content almost exclusively after 10 PM") and queue them for monthly surprise notifications.
* **Near-Miss Calibration (Section 2.2 & 3.3)**:
  * *Backend*: Set the starting near-miss similarity threshold band at **0.71–0.75** (from Fixed, overriding v3's 0.68–0.75).
  * *Cron Job*: Run weekly scans checking conversion rate (near-misses promoted to confirmed within 14 days). If conversion is $< 20\%$, narrow the band to 0.73–0.75; if $> 60\%$, widen it to 0.69–0.75.
* **Recall Moment Cadence**: Max 1 send per rolling 7 days, randomized uniformly between 10 AM–4 PM local time.

---

### Phase 4: Identity, Trajectories, and Tensions
* **Goal**: Formulate the user's cognitive identity profiles and scan for adjacent concepts they are missing.
* **Mind Type Timeline (Section 4.1 & 6.2)**:
  * *Backend*: Add `users.mind_type` column.
  * *Frontend*: Compute graph stats weekly (breadth, depth concentration, cross-hub density) and render a horizontal weekly timeline trajectory strip on the dashboard.
* **Pulse Milestone Unlock System (Section 0.3)**:
  * *Unlocks*: Replace the 100-node locked gate. Pulse is visible from node 1, unlocking milestones:
    - *5 nodes*: First Pattern Report.
    - *15 nodes*: Mind Type unlocks.
    - *30 nodes*: Monthly Prediction activates (revised **5–7 days window**, high specificity, confidence $\ge 0.72$, no hedging).
    - *50 nodes*: Thought Compatibility unlocks.
    - *100 nodes*: Pulse Score ranked.
    - *200 nodes*: Public Graph.
* **Self-Description & Confession (Section 4.2, 4.3 & 7.3)**:
  * *Backend*: Store self-description verbatim in `users.self_description` (captured at 5 saves).
  * *Cron Job*: Run a monthly discrepancy scan against top 3 hubs. Deliver confessions via Telegram, leaving quiet evidence on the dashboard confession views.
* **The Forward Hook (Section 8.5)**:
  * *Backend*: Embed 200 general domains. Run a monthly scan to locate adjacent-but-absent concept gaps, prompting the user via Telegram.

---

### Phase 5: Quantified Identity, Social & Friend Fast-Track
* **Goal**: Scale ambient graph visuals based on Pulse and enable instant relationship comparisons.
* **Pulse Glow (Section 5.1 & 6.2)**:
  * *Backend*: Add `users.pulse_score` column. Compute dynamically using the formula:
    $$\text{Pulse} = \text{total\_items} + 3.0 \times \text{confirmed\_candidates} + 5.0 \times \text{active\_hubs\_30d} - 4.0 \times \text{stale\_hubs\_30d}$$
  * *Frontend*: Tie graph brightness and ambient particle glow in Three.js directly to the Pulse score.
* **Cluster Portrait (Section 5.2)**: Generate visual/text descriptions when a semantic hub reaches $\ge 8$ member nodes.
* **Thought Compatibility Friend Fast-Track Flow (Section 0.4)**:
  * *Telegram Bot*: Enable users to share compatibility links. Friends complete 5 seeding questions native to Telegram (preoccupation, belief shift, interest, recurring tension, unresolved loop) to generate a comparison report in 15 minutes via temporary accounts.
* **Thought Compatibility Dashboard (Section 6.7)**:
  * *Backend*: Add `users_compatibility_links` (user_id, linked_user_id, status: pending/accepted) requiring explicit two-sided opt-in.
  * *Frontend*: Overlay the two graphs side-by-side spatially in Three.js.

---

### Phase 6: Long-Tail Retention & Mobile Capture
* **Goal**: Build bridges for lapsed users, handle returning preoccupations, and enable mobile sharing.
* **Living Graph Telegram Trigger (Section 0.2 & 6.2)**:
  * *Cron Job*: Fire a lapse alert to Telegram if 3+ clusters drop below 40% temperature in 48 hours and the user has not opened the frontend in $\ge 72$ hours. Max once per 10 days.
* **Returning Themes Mechanic (Section 3.1 & 3.2)**:
  * *Cron Job*: Detect cluster-pairs re-emerging after the 60-day suppression window; route them to the returning theme template (max once per theme per 90 days).
* **Weekly Card (Section 7.5)**: Dashboard generates designed minimal card templates ready to export for Instagram Stories.
* **Save-From-Anywhere Share Sheet (Section 8.1)**: Build Xcode and Android manifest share extensions posting direct JSON payloads to the Recall API.
