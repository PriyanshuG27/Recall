# 🚨 GLOBAL EXECUTION PROTOCOL (MANDATORY)

This protocol overrides every other instruction in this prompt.

---

# Phase 0 — Repository Loading (BLOCKING)

Before **any** reasoning, planning, implementation, refactoring, testing, tool usage, architecture decisions, or code generation:

## Step 1 — Load Repository Context

Read **completely**:

* `AGENTS.md`
* Every document under `/docs`
* Every document referenced by `AGENTS.md`
* Every dependency listed in **Required Dependencies**

Do **not** skip documents because they appear unrelated.

If **any** required file cannot be found or read:

* STOP immediately.
* Report the missing file(s).
* Do **not** continue.
* Wait for further instructions.

---

# Phase 1 — Dependency Loading (BLOCKING)

## Required Dependencies

Read the following dependencies completely before continuing:

* @javascript-testing-patterns
* @react-best-practices
* @testing-patterns

Read every dependency **from beginning to end**.

Do **not**:

* skim
* summarize without reading
* rely on memory
* assume previous prompts already loaded them

Every architectural, implementation, security, performance, testing, and design decision must comply with these dependencies.

---

# Phase 2 — Verification (REQUIRED)

Before writing **any** code, output exactly:

```text
### Repository Verification

✅ AGENTS.md loaded
✅ Repository documentation loaded
✅ @javascript-testing-patterns loaded
✅ @react-best-practices loaded
✅ @testing-patterns loaded
```

Only mark a dependency as loaded if it was actually located, opened, and completely read.

---

# Phase 3 — Compliance Summary (REQUIRED)

For **every** dependency and repository document:

Provide:

* 3–5 important implementation rules
* the relevant section/reference
* how those rules affect this implementation

Do **not** continue if this cannot be done.

---

# Phase 4 — Implementation Plan (REQUIRED)

Before generating code provide:

* Architecture overview
* Files to modify/create
* Backend changes
* Frontend changes
* Database changes
* API changes
* Scheduler changes (if any)
* Security considerations
* Performance considerations
* Testing strategy

---

# GLOBAL REPOSITORY RULES

These rules apply regardless of the prompt.

## Architecture

* Fixed stack:

  * FastAPI
  * React + Vite
  * Neon PostgreSQL + pgvector + pg_trgm
  * Upstash Redis
  * Modal GPU
  * Render
  * Vercel

* Do not introduce new libraries without explicit justification.

* Prefer stdlib and already-approved packages.

---

## Database

* Parameterized SQL only.
* Never build SQL via string interpolation.
* Every user query must be scoped to the authenticated user.
* Use transactions where required.
* Respect existing indexes.

---

## Security

* Never expose:

  * TELEGRAM_BOT_TOKEN
  * JWT_SECRET
  * FERNET_KEY

* Never log:

  * plaintext
  * tokens
  * secrets
  * encrypted values

* Encrypt before DB write where required.

* Secret comparisons must always use:

```python
hmac.compare_digest(...)
```

Never use `==`.

---

## Authentication

Every `/api/*` endpoint must authenticate using the project's existing authentication middleware.

Never duplicate authentication logic.

---

## Performance

Maintain repository targets including:

* Webhook ACK <50 ms
* Canvas 60 FPS @ 500 nodes
* Vector search <10 ms
* Text search <5 ms

Heavy work must remain asynchronous.

---

## Error Handling

* Specific exception handling only.
* No broad silent failures.
* Never expose stack traces.
* Preserve repository retry behavior.
* Scheduler jobs must configure the required `misfire_grace_time`.

---

## Testing

Every new function requires corresponding unit tests.

Backend:

* pytest

Frontend:

* Vitest

Mock:

* AI services
* Telegram
* Redis
* Google APIs
* Chrome APIs
* External services

### IMPORTANT

Create or update tests.

**Do NOT execute them.**

---

## Coding Rules

* Reuse existing project abstractions.
* Avoid duplicate logic.
* Keep implementations modular.
* Follow repository conventions.
* Prefer composition over duplication.

---

# Failure Policy

If any dependency, AGENTS.md, or required documentation cannot be loaded:

* STOP.
* Do not generate code.
* Do not guess.
* Report what is missing.
* Wait for further instructions.

Implementation before completing all loading and verification phases is considered invalid.

---

# TASK

## PROMPT 076 — Frontend Test Suite: Vitest

**Skills:** `javascript-testing-patterns`, `react-best-practices`, `testing-patterns`

```
Write and maintain the complete Vitest component, hook, and page test suite for the Recall Observatory frontend application.

Target Test Files (frontend/src/tests/):
1. `App.test.jsx` & `Sidebar.test.jsx`:
   - Navigation rail rendering: Archive, Map, Drill, Settings, Profile.
   - Verifies active room highlighting, monogram badge, liquid amber droplet effect, and sound toggle.
   - Asserts `Bridges` item is hidden from sidebar rail during Branching POC (`hidden: true`).

2. `ChatDrawer.test.jsx`:
   - Interactive RAG Citations: Tests AI Assistant response rendering numbered citation badges (`[1]`, `[2]`).
   - Citation Click Handling: Asserts clicking citation badge `[1]` switches room to `/map`, pans/zooms camera transform to center cited node at scale $k = 1.35$, selects node, highlights connection lines, and triggers a 3-second gold flare ring.

3. `PWAInstallBanner.test.jsx`:
   - Floating PWA Banner: Dark glassmorphic banner rendering with gold 'R' monogram logo, install button trigger, and close button dismissal.

4. `Archive.test.jsx` & `ArchiveCard.test.jsx`:
   - 3D Glass Cylinder Archive View (`ArchiveCylinder.jsx`, `ArchiveCard.jsx`): Cylinder rotation, card selection, tag pill filtering, modal inspection.

5. `Map.test.jsx`, `MapCanvas.test.jsx`, `GraphControls.test.jsx`, `NodeHoverCard.test.jsx`:
   - 3D Constellation Sky Mind Map (`NebulaCanvas.jsx`, `Graph3DScene.jsx`, `GraphNode3D.jsx`, `GraphEdge3D.jsx`): R3F / Three.js canvas fallback, color-coded glowing star nodes per source_type (Blue: Link, Purple: Voice, Emerald: Image, Crimson: PDF, Amber: Text), 60 FPS flowing edge light particles, orbiting micro-particles around hot/review nodes at radius $1.7\times - 2.2\times$, physics tracking (`useMouseVelocity`, `useScrollVelocity`).

6. `SearchOverlay.test.jsx` & `KeyboardShortcuts.test.jsx`:
   - Command+K / Ctrl+K Global Terminal Finder: Live 300ms debounced search, tag grouping, hotkey listener mounting/unmounting.

7. `AudioEngine.test.jsx`:
   - Web Audio API Synth System: Synthesizer initialization, retro sci-fi sound triggers (click, transition, drill success, modal open/close), mute state persistence.

8. `Drill.test.jsx`, `DrillProgress.test.jsx`, `DrillSummary.test.jsx`:
   - Active Recall Spaced Repetition UI: Flashcard stack navigation, SuperMemo SM-2 answer button scoring (Again, Hard, Good, Easy), progress bar, summary metrics.

9. `Profile.test.jsx`, `StreakBadge.test.jsx`, `StreakPanel.test.jsx`, `QuizStatsPanel.test.jsx`:
   - Profile & Pulse UI: Mind portrait radar chart, cognitive mind type badge, streak counter, quiz performance statistics.

10. `CustomCursor.test.jsx`, `GlitchText.test.jsx`, `RoomTransition.test.jsx`, `SplashScreen.jsx`:
    - Cyber-Noir UI Micro-Animations: Custom magnetic cursor, boot sequence splash screen, glitch text rendering, sound-synced room transitions.

11. `ExtensionPopup.test.jsx`, `ExtensionOptions.test.jsx`, `ExtensionServiceWorker.test.js`:
    - Chrome Extension Manifest v3: Popup web clipper, options sync, JWT token sync.

12. `Bridges.test.jsx`:
    - Top-level skip: `describe.skip('Bridges Page Component', () => { ... })`.

Execution Rules:
- Environment: `@testing-library/react` with `jsdom`.
- Mocks: Mock Web Audio API (`AudioContext`, `OscillatorNode`, `GainNode`) and HTMLCanvasElement / WebGLContext for Three.js.
- Mock fetch / axios for all API interactions.

Gate Check:
[ ] 83 Vitest tests pass with zero warnings
[ ] ChatDrawer citation badge click verified transitioning to Map and triggering camera pan + gold flare ring
[ ] PWAInstallBanner renders floating glassmorphic card with install/close handlers
[ ] Command+K SearchOverlay opens on hotkey and debounces inputs correctly
[ ] Three.js canvas fallback renders gracefully in test DOM environment
[ ] Chrome extension popup and background worker tests pass
[ ] Bridges component tests skipped cleanly
```
