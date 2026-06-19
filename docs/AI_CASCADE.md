# AI_CASCADE — Recall

| Field | Value |
|-------|-------|
| Version | 0.1.0 |
| Date | 2026-06-19 |
| Status | Draft |

---

## Overview

Every AI task follows a 5-tier cascade. Each tier is attempted in order; on failure, the next tier is tried. Tier 4 guarantees no data loss.

```
Task received
    |
    v
[Tier 0: Modal GPU] ----FAIL----> [Tier 1: Groq] ----FAIL----> [Tier 2: Gemini]
                                                                      |
                                                                    FAIL
                                                                      v
                                                          [Tier 3: Ollama] ----FAIL----> [Tier 4: Bookmark]
```

---

## Tier 0 — Modal Serverless GPU (PRIMARY)

| Property | Value |
|----------|-------|
| Models | Whisper large-v3 (STT) + Llama 3 8B (summary/quiz) + MiniLM-L6-v2 (embed) |
| Why position 0 | Highest quality; self-hosted; pay-per-second (no monthly cost when idle) |
| Limits | Modal free tier: 30 GPU-hours/month; cold start 2-5 s |
| Failover trigger | HTTP error, timeout > 30 s, or Modal service unavailable |
| Fallback output | Full transcript + summary + 384-dim embedding + quiz |

**Cold start behaviour**: First call after idle may take 2-5 s (up to 10s depending on container spin-up) for GPU container to warm. Keep the Telegram bot's response asynchronous. Immediately reply with "Processing your [content type]..." so the user knows the system is active, while the background queue waits for Modal to warm up. Groq (Tier 1) handles concurrent requests during warmup.

---

## Tier 1 — Groq Cloud API

| Property | Value |
|----------|-------|
| Models | Whisper (STT) + Llama 3 8B / 70B (summary/quiz) |
| Why position 1 | Fastest external inference; free tier; excellent for burst |
| Limits | Free tier RPM/RPD not published; typically 30 RPM for Whisper |
| Failover trigger | 429 (rate limited), 5xx, or timeout > 20 s |
| Fallback output | Full transcript + summary + (embedding via MiniLM fallback) |

> Groq does not serve embedding models. MiniLM embedding falls back to Modal or is computed locally if Groq is used for STT/summary.

---

## Tier 2 — Gemini 3.1 Flash-Lite

| Property | Value |
|----------|-------|
| Models | Gemini 3.1 Flash-Lite (multimodal: text, summary, STT via audio upload) |
| Why position 2 | Generous free limits (30 RPM / 1500 RPD / 1M TPM); large context window |
| Limits | 30 RPM hard cap; 1500 requests/day |
| Failover trigger | 429, 5xx, quota exhausted |
| Fallback output | Summary only (no transcript for voice; uses audio-to-text capability) |

---

## Tier 3 — Ollama (Local)

| Property | Value |
|----------|-------|
| Models | Any model served by local Ollama instance (e.g. llama3, mistral) |
| Why position 3 | Optional; developer escape hatch; no external API dependency |
| Activation | `OLLAMA_HOST` env var must be set; skipped if absent |
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
| Trigger | All Tiers 0-3 have failed |
| Output | Item inserted with source_type preserved; raw_text=NULL; summary=NULL; embedding=NULL |
| User notification | "Could not process [content type]. Saved as bookmark. We'll retry later." |
| Retry path | Task payload written to dead_letter_queue; admin can re-enqueue |

---

## Cascade Decision Matrix

| Content Type | Tier 0 Task | Tier 1 Task | Tier 2 Task | T4 |
|-------------|-------------|-------------|-------------|-----|
| Voice/Audio | Whisper STT + Llama3 summary | Groq Whisper + Llama3 | Gemini STT+summary | Bookmark |
| YouTube URL | yt-dlp + Whisper STT + Llama3 | yt-dlp + Groq Whisper | yt-dlp + Gemini | Bookmark |
| Plain URL | Scrape + MiniLM embed + Llama3 | Scrape + Groq summary | Scrape + Gemini | Bookmark |
| PDF | PyMuPDF + MiniLM + Llama3 | PyMuPDF + Groq | PyMuPDF + Gemini | Bookmark |
| Image | Tesseract + MiniLM + Llama3 | Tesseract + Groq | Tesseract + Gemini | Bookmark |
| Text | MiniLM + Llama3 | Groq | Gemini | Bookmark |

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
