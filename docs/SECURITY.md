# SECURITY — Recall

| Field | Value |
|-------|-------|
| Version | 0.1.0 |
| Date | 2026-06-19 |
| Status | Draft |

---

## Threat Model Summary

| Threat | Mitigation |
|--------|-----------|
| Telegram webhook spoofing | TELEGRAM_BOT_TOKEN secret; Telegram TLS delivery |
| Session hijacking (web) | httpOnly cookie; JWT 7-day expiry; JWT_SECRET server-side only |
| TWA session spoofing | HMAC-SHA256 of initData signed with TELEGRAM_BOT_TOKEN |
| DB data breach | raw_text + google_refresh_token Fernet-encrypted at rest |
| OAuth token theft | Refresh token Fernet-encrypted; access tokens never persisted |
| Cross-user data access | All queries parameterised with user_id from verified JWT |
| Replay attacks (webhook) | Telegram update_id dedup via processed_updates table |
| Brute-force / flooding | Redis sliding window rate limiter (20 req/user/min) |

---

## TLS (In Transit)

| Link | TLS Provider | Notes |
|------|-------------|-------|
| Browser -> Vercel | Vercel Edge (Let's Encrypt) | Automatic, no config |
| Browser / Bot -> Render | Render (Let's Encrypt) | Automatic |
| Render -> Neon | Neon TLS (required) | `?sslmode=require` in DATABASE_URL |
| Render -> Upstash | HTTPS REST | Upstash enforces TLS |
| Render -> Modal | HTTPS | Modal API TLS |
| Render -> Groq / Gemini | HTTPS | Provider enforces TLS |
| Telegram -> Render | HTTPS | Telegram only delivers webhooks to HTTPS endpoints |

No unencrypted links in any data path.

---

## Encryption at Rest

| Data | Encrypted | Method | Key |
|------|-----------|--------|-----|
| `items.raw_text` | YES | Fernet AES-128 | `FERNET_KEY` |
| `users.google_refresh_token` | YES | Fernet AES-128 | `FERNET_KEY` |
| `items.summary` | **NO** | — | Required for GIN trigram index |
| `items.title` | **NO** | — | Required for display queries |
| `items.embedding` | **NO** | — | Required for HNSW vector search |
| `items.tags` | **NO** | — | Required for tag filter queries |
| `quizzes.*` | **NO** | — | LLM-derived; not user-original text |
| `reminders.message` | **NO** | — | User-authored; low sensitivity |

> **No E2EE claim.** The server generates embeddings and summaries, so it processes plaintext during ingestion. The encrypted fields protect data in a DB breach scenario, not against the application operator.

---

## Authentication Layers

See `AUTH_ARCHITECTURE.md` for full sequence diagrams.

### Layer 1 — Identity
- `users.telegram_chat_id` is the primary identity.
- Set on first `/start` message; never changeable.

### Layer 2a — Telegram Web App (TWA)
- `initData` string from `window.Telegram.WebApp.initData`.
- HMAC-SHA256 computed server-side using `TELEGRAM_BOT_TOKEN` as key.
- Validated on every TWA API call.

### Layer 2b — Website (Telegram Login Widget)
- Widget sends signed hash to `GET /auth/telegram`.
- Server validates SHA256 hash using `TELEGRAM_BOT_TOKEN`.
- Issues JWT (7-day, httpOnly cookie, signed with `JWT_SECRET`).

### Layer 3 — Google OAuth
- Scope: `drive.file` only (files created by Recall; cannot access existing Drive files).
- Refresh token Fernet-encrypted before DB write.
- Access token never persisted; obtained at sync time via refresh.

---

## Honest Claims

| Claim | True? | Details |
|-------|-------|---------|
| "Your data is encrypted" | Partial | raw_text encrypted; summary/embedding/title are not |
| "Server never sees your content" | **False** | Server processes plaintext to generate embeddings and summaries |
| "TLS protects data in transit" | True | All links use TLS |
| "Google Drive access is limited" | True | drive.file scope; cannot read pre-existing Drive files |
| "Tokens are encrypted at rest" | True | Fernet AES-128 on refresh tokens |

---

## Key Rotation Procedure

1. Generate new `FERNET_KEY`.
2. Write migration script: decrypt all `raw_text` + `google_refresh_token` with old key, re-encrypt with new key.
3. Run migration in a transaction.
4. Update Render env var.
5. Redeploy backend.

> Do not rotate without the migration step — existing encrypted rows become unreadable.
