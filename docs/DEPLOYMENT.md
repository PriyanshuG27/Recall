# DEPLOYMENT — Recall

| Field | Value |
|-------|-------|
| Version | 0.1.0 |
| Date | 2026-06-19 |
| Status | Draft |

---

## Prerequisites

- GitHub repo with `backend/` and `frontend/` directories.
- Accounts on: Neon, Upstash, Modal, Render, Vercel, Uptime Robot, Google Cloud Console, Telegram.

---

## 1. Telegram Bot Setup

1. Message `@BotFather` -> `/newbot` -> choose name and username.
2. Copy `TELEGRAM_BOT_TOKEN`.
3. Run `/setdomain` (for TWA) pointing to your Vercel URL (set after Vercel deploy).
4. Webhook registered in Step 5 (Render) after backend URL is known.

**Verify**: `/getMe` endpoint returns bot details.

---

## 2. Neon (PostgreSQL) Setup

1. Create project at [neon.tech](https://neon.tech) (free tier).
2. Copy pooled connection string -> `DATABASE_URL`.
3. Open SQL editor, run in order:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   CREATE EXTENSION IF NOT EXISTS pg_trgm;
   ```
4. Run full schema DDL from `BACKEND_SCHEMA.md`.
5. Run index creation DDL.

**Verify**: `SELECT extname FROM pg_extension;` returns `vector` and `pg_trgm`.

---

## 3. Upstash (Redis) Setup

1. Create database at [upstash.com](https://upstash.com) -> Redis -> free tier.
2. Copy `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN`.
3. No additional configuration needed (REST API, not persistent TCP).

**Verify**: Upstash console -> Data Browser -> shows empty keyspace.

---

## 4. Modal Setup

1. `pip install modal` -> `modal token new` -> authenticate.
2. Deploy Whisper endpoint: `modal deploy backend/modal_whisper.py`
3. Deploy Llama 3 endpoint: `modal deploy backend/modal_llama.py`
4. Deploy MiniLM endpoint: `modal deploy backend/modal_embed.py`
5. Copy `MODAL_API_TOKEN` from Modal dashboard -> Settings -> API Tokens.

**Verify**: `modal app list` shows three deployed apps with status `deployed`.

---

## 5. Google OAuth Setup

1. Google Cloud Console -> APIs & Services -> Credentials -> Create OAuth 2.0 Client ID.
2. Application type: **Web application**.
3. Authorised redirect URIs: `https://<render-url>/auth/google/callback`.
4. Copy `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.
5. Set `GOOGLE_REDIRECT_URI` = `https://<render-url>/auth/google/callback`.
6. Enable Google Drive API in APIs & Services -> Library.

**Verify**: OAuth consent screen configured; test user added if in testing mode.

---

## 6. Fernet Key Generation

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Store output as `FERNET_KEY`. **Never rotate without migrating existing encrypted rows.**

---

## 7. JWT Secret Generation

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Store output as `JWT_SECRET`.

---

## 8. Render (Backend) Setup

1. New Web Service -> connect GitHub repo -> select `backend/` directory.
2. Build command: `pip install -r requirements.txt`
3. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add all backend env vars (see `ENV_CONFIG.md`).
5. After first deploy, copy the Render URL (e.g. `https://recall-api.onrender.com`).
6. Register Telegram webhook:
   ```
   GET https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://recall-api.onrender.com/webhook
   ```

**Verify**:
- `GET https://recall-api.onrender.com/health` returns `{"status": "ok"}`.
- `GET https://api.telegram.org/bot<TOKEN>/getWebhookInfo` shows `url` set and `pending_update_count: 0`.

---

## 9. Vercel (Frontend) Setup

1. New Project -> import GitHub repo -> select `frontend/` directory.
2. Framework preset: **Vite**.
3. Add frontend env vars: `VITE_API_URL`, `VITE_BOT_USERNAME`.
4. Deploy.
5. Copy Vercel URL -> go back to Telegram BotFather -> `/setdomain <vercel-url>`.
6. Add Vercel URL to Google OAuth authorised origins.

**Verify**: `https://<vercel-url>` loads dashboard; Telegram Login Widget renders.

---

## 10. Uptime Robot Setup

1. New monitor -> HTTP(s) -> URL: `https://recall-api.onrender.com/health`.
2. Interval: **5 minutes**.
3. Alert contact: email (optional).

**Verify**: Monitor shows green status; Render logs show `/health` requests every 5 min.

---

## Deployment Order

```
1. Neon DB      -> have DATABASE_URL
2. Upstash      -> have Redis credentials
3. Modal        -> have MODAL_API_TOKEN
4. Google OAuth -> have client credentials
5. Generate FERNET_KEY + JWT_SECRET
6. Render       -> deploy backend with all env vars
7. Register webhook with Telegram
8. Vercel       -> deploy frontend
9. BotFather    -> setdomain to Vercel URL
10. Uptime Robot -> configure keepalive
```
