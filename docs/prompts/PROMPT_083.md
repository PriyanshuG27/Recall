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

* @python-pro
* @image-processing
* @ai-processing

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
✅ @python-pro loaded
✅ @image-processing loaded
✅ @ai-processing loaded
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

## PROMPT 083 — Image OCR Quality + Preprocessing

**Skills:** `python-pro`, `image-processing`, `ai-processing`

```
Enhance image ingestion quality using Pillow image preprocessing prior to Tesseract OCR and Gemini visual captioning fallbacks.

Pipeline (`backend/services/ocr_service.py`):
```python
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
import io

def preprocess_and_ocr_image(image_bytes: bytes) -> dict:
    image = Image.open(io.BytesIO(image_bytes))
    
    # 1. Convert to grayscale & enhance contrast
    image = image.convert('L')
    image = ImageEnhance.Contrast(image).enhance(2.0)
    image = image.filter(ImageFilter.SHARPEN)
    
    # 2. Resize if width < 800px
    if image.width < 800:
        ratio = 1200.0 / image.width
        image = image.resize((1200, int(image.height * ratio)), Image.Resampling.LANCZOS)
        
    # 3. Adaptive binarization
    image = image.point(lambda p: 0 if p < 128 else 255, '1')
    
    # 4. Tesseract OCR with confidence filtering (>60%)
    data = pytesseract.image_to_data(image, lang='eng+hin+fra+deu', output_type=pytesseract.Output.DICT)
    high_conf_words = [data['text'][i] for i in range(len(data['text'])) if int(data['conf'][i]) >= 60 and data['text'][i].strip()]
    
    # 5. Fallback trigger check
    if len(high_conf_words) < 10:
        return {"ocr_text": None, "trigger_gemini_fallback": True}
        
    return {"ocr_text": " ".join(high_conf_words), "trigger_gemini_fallback": False}
```

Rules:
- All image manipulations MUST execute in memory via `io.BytesIO` (zero temporary file writes to disk).
- Enforce a strict 30-second processing timeout per image.

Gate Check:
[ ] Preprocessed images produce higher OCR text extraction accuracy
[ ] Low-confidence images (< 10 words) cleanly trigger Gemini visual fallback
[ ] Embedded QR codes extracted and routed as URL ingestion items
[ ] In-memory processing verified (no temp files left on disk)
```
