# AI_CASCADE — Recall

| Field | Value |
|-------|-------|
| Version | 0.1.1 |
| Date | 2026-06-19 |
| Status | Active |

---

## Overview

Every AI task follows a multi-tier cascade. In production, a 4-tier cascade is used. Each tier is attempted in order; on failure, the next tier is tried. Tier 3 guarantees no data loss.

```
[Production Cascade]
Task received
    |
    v
[Tier 0: Modal GPU] ----FAIL----> [Tier 1: Groq] ----FAIL----> [Tier 2: Gemini]
                                                                      |
                                                                    FAIL
                                                                      v
                                                          [Tier 3: Bookmark]
```

In local development, setting `LOCAL_MODE=true` flips the cascade to prioritize local execution:

```
[Local Development Cascade (LOCAL_MODE=true)]
Task received
    |
    v
[Tier 0: Ollama (Local)] ----FAIL----> [Tier 1: Modal GPU] ----FAIL----> [Tier 2: Groq] ----FAIL----> [Tier 3: Gemini] ----FAIL----> [Tier 4: Bookmark]
```

---

## Tier 0 — Modal Serverless GPU (PRIMARY)

| Property | Value |
|----------|-------|
| Models | Whisper large-v3 (STT) + Llama 3.3 70B (summary/quiz) + MiniLM-L6-v2 (embed) |
| Why position 0 | Highest quality; self-hosted; pay-per-second (no monthly cost when idle) |
| Limits | Modal free tier: 30 GPU-hours/month; cold start 2-5 s |
| Failover trigger | HTTP error, timeout > 30 s, or Modal service unavailable |
| Fallback output | Full transcript + summary + 384-dim embedding + quiz |

**Cold start behaviour**: First call after idle may take 2-5 s (up to 10s depending on container spin-up) for GPU container to warm. Keep the Telegram bot's response asynchronous. Immediately reply with "Processing your [content type]..." so the user knows the system is active, while the background queue waits for Modal to warm up. Groq (Tier 1) handles concurrent requests during warmup.

---

## Tier 1 — Groq Cloud API (PRIMARY CLOUD FALLBACK)

| Property | Value |
|----------|-------|
| Models | Whisper large-v3-turbo (STT) + Qwen3-32b (Primary LLM) + Llama 4 Scout 17b (Overflow LLM) |
| Why position 1 | Fastest external inference; free tier; excellent for burst; Qwen3-32b offers 60 RPM and high-fidelity reasoning |
| Limits | 60 RPM for Qwen3-32b, 30 RPM / 30K TPM for Llama 4 Scout; 500K TPD limits |
| Failover trigger | 429 (rate limited), 5xx, or timeout > 20 s |
| Fallback output | Full transcript + summary + (embedding via MiniLM fallback) |

> Groq does not serve embedding models. MiniLM embedding falls back to Modal or is computed locally if Groq is used for STT/summary.
> **Overflow routing**: Qwen3-32b is the primary for general text tasks and quizzes (due to high 60 RPM limit and 96.1% MATH score). Llama 4 Scout 17b is selected for long-document/PDF contexts (up to 30K TPM / 10M token context window) and as an overflow model.

---

## Tier 2 — Gemini 3.1 Flash-Lite (SECONDARY CLOUD FALLBACK)

| Property | Value |
|----------|-------|
| Models | Gemini 3.1 Flash-Lite (multimodal: text, summary, STT via audio upload) |
| Why position 2 | Generous free limits (30 RPM / 1500 RPD / 1M TPM); large context window |
| Limits | 30 RPM hard cap; 1500 requests/day |
| Failover trigger | 429, 5xx, quota exhausted |
| Fallback output | Summary only (no transcript for voice; uses audio-to-text capability) |

---

## Tier 3 — Ollama (LOCAL MODE ONLY)

| Property | Value |
|----------|-------|
| Models | Any model served by local Ollama instance (e.g. gemma3:4b, phi4-mini) |
| Why position 3 | Developer escape hatch; only active locally when `LOCAL_MODE=true` is set. |
| Activation | `OLLAMA_HOST` env var must be set; skipped in production cascade. |
| Limits | Depends on local hardware; no enforced rate limit |
| Failover trigger | Connection refused, timeout > 60 s, or OLLAMA_HOST not set |
| Fallback output | Summary only; no transcription |

---

## Tier 4 — Bookmark Fallback (GUARANTEED)

| Property | Value |
|----------|-------|
| Action | Save item as bookmark with minimal metadata (source_url, title if extractable) |
| Why position 4 | Zero data loss guarantee; always succeeds |
| Limits | None |
| Trigger | All Tiers 0-3 have failed (or Tiers 0-2 in production cascade) |
| Output | Item inserted with source_type preserved; raw_text=NULL; summary=NULL; embedding=NULL |
| User notification | "Could not process [content type]. Saved as bookmark. We'll retry later." |
| Retry path | Task payload written to dead_letter_queue; admin can re-enqueue |

---

## Cascade Decision Matrix

| Content Type | Tier 0 Task | Tier 1 Task | Tier 2 Task | T4 |
|-------------|-------------|-------------|-------------|-----|
| Voice/Audio | Whisper STT + Llama 3.3 70B | Groq Whisper-Turbo + Qwen3-32b | Gemini STT+summary | Bookmark |
| YouTube URL | yt-dlp + Whisper STT + Llama 3.3 70B | yt-dlp + Groq Whisper-Turbo | yt-dlp + Gemini | Bookmark |
| Plain URL | Scrape + MiniLM embed + Llama 3.3 70B | Scrape + Qwen3-32b summary | Scrape + Gemini | Bookmark |
| PDF | PyMuPDF + MiniLM + Llama 3.3 70B | PyMuPDF + Llama 4 Scout | PyMuPDF + Gemini | Bookmark |
| Image | Tesseract + MiniLM + Llama 3.3 70B | Tesseract + Qwen3-32b | Tesseract + Gemini | Bookmark |
| Text | MiniLM + Llama 3.3 70B | Qwen3-32b | Gemini | Bookmark |

---

## Cascade Timeout Budget

| Tier | Timeout |
|------|---------|
| 0 — Modal | 30 s |
| 1 — Groq | 20 s |
| 2 — Gemini | 20 s |
| 3 — Ollama | 60 s |
| Total max | ~130 s (extreme case) |

In practice, Tier 0 or Tier 1 handles >95% of requests.

---

## Override

Set `COMPUTE_PROVIDER` env var to `groq`, `gemini`, `ollama`, or `modal` to pin to a specific tier. For testing and CI only.
