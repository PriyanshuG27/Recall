# Manual Verification Test Suite — Desktop Web & Telegram Core Features

This document provides step-by-step manual verification procedures for all core **Desktop Web Dashboard**, **Chrome Extension**, and **Telegram Bot** features that can be fully tested right now on desktop.

---

## 🧪 Test Case 1: OKF (Obsidian Knowledge Format) Export & Import

### Objective:
Verify exporting user knowledge graph as an OKF `.zip` archive (containing Markdown files with YAML frontmatter) and re-importing an archive.

### Steps:
1. Open the Web Dashboard and navigate to **Settings** (`/settings`).
2. Scroll to the **Data & Exports** section and click **Export Knowledge Base (OKF .zip)**.
   - **Expected**: A `.zip` archive downloads containing formatted Markdown files (`.md`) with YAML frontmatter headers (`title`, `tags`, `source_url`, `created_at`).
3. Under **Import Knowledge Base**, select the downloaded `.zip` file (or an Obsidian vault zip) and click **Upload & Import**.
   - **Expected**: A success toast appears: `"Import completed: X items created/updated."`, and the items appear in your Archive.

---

## 🧪 Test Case 2: Chrome Extension (Context Notes & AI Tags)

### Objective:
Verify saving web pages via the Chrome extension popup with custom context notes and suggested AI tags.

### Steps:
1. Open any article or website (e.g. Wikipedia) in Google Chrome.
2. Click the **Recall** Chrome Extension icon in your browser toolbar.
   - **Expected**: The popup opens displaying the current tab title, URL, custom **Context Note** text area, and **Suggested Tags**.
3. Type a note in the **Write a context note...** text area (e.g. *"Important reference for agentic AI design"*).
4. Click one of the **Suggested Tags** chips (e.g. `+ai`).
5. Click **Save to Recall**.
   - **Expected**: A temporary checkmark `✓` badge appears on the extension toolbar icon, and the page is ingested with the custom context note and selected tag.

---

## 🧪 Test Case 3: SM-2 Spaced Repetition Drill & Stats (`/drill`)

### Objective:
Verify interactive card review drills, retention metric calculations, and SM-2 parameter updates.

### Steps:
1. Navigate to **Drill / Quiz** mode on the Web Dashboard (`/drill`).
2. Observe the current review card displaying a title, question prompt, and 4 vertically stacked choices.
3. Click an option choice:
   - **Expected**: Immediate visual feedback (green for correct, red for incorrect), retention streak updates, and smooth transition to the next card.
4. Click **View Detailed Analytics** to open the `QuizStatsPanel`:
   - **Expected**: Visual retention charts, Ease Factor distribution bars, and upcoming 7-day review schedule load correctly.

---

## 🧪 Test Case 4: Telegram Bot Ingestion & Context Replies

### Objective:
Verify forwarding links, text notes, screenshots, and context annotations to `@RecallBot`.

### Steps:
1. In Telegram, send any webpage link (e.g. `https://news.ycombinator.com`) to `@RecallBot`.
   - **Expected**: Under 50ms, the bot replies with an ACK message confirming ingestion into your mind graph.
2. Reply directly to the bot's confirmation message with a context note (e.g., *"Read this for startup ideas"*).
   - **Expected**: Bot replies: `💭 Context note queued: "Read this for startup ideas" ✓`.

---

## 🧪 Test Case 5: Weekly Mind Map Cards & Quiz Triggers

### Objective:
Verify weekly visual mind map card photos sent to Telegram and inline quiz trigger buttons.

### Steps:
1. In Telegram, locate a **Weekly Mind Map** photo message sent by `@RecallBot` (or trigger via test).
2. Click the **Review Constellation ⚡** inline button below the photo.
   - **Expected**: The bot acknowledges the click in under 10ms, clears the reply markup from the photo message to prevent double-clicks, and sends the interactive review quiz in a clean new text message.

---

## 🧪 Test Case 6: Cognitive Bridges & Kintsugi Synapse Matrix (`/bridges`)

### Objective:
Verify viewing connected friend bridges, Kintsugi decay progression, and gold seams.

### Steps:
1. Navigate to **Bridges** on the Web Dashboard (`/bridges`).
2. Select an active friend connection from the sidebar.
   - **Expected**:
     - Synapse cards display overlapping topics with similarity scores.
     - Inactive synapses display Kintsugi decay stages (`WEAKENED`, `FRACTURED`, `CRACKED`, `BROKEN`) with gold seam repair indicators.
3. Click **Perform Ceremony** on a broken synapse card.
   - **Expected**: The ceremony timestamp updates and a success toast confirms the synapse repair.
