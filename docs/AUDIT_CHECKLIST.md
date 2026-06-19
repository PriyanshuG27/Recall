# Recall — Production Audit Checklist

**Version:** 1.0  
**Scope:** Run before every production deploy. Tick every box. If any check fails, resolve it before deploying.

---

## SECTION A — Database & Infrastructure Audit

### A1. Database Schema & Migrations
- [ ] Run DDL schema verification on Neon production database.
- [ ] Confirm `vector` and `pg_trgm` extensions are installed:
  ```sql
  CREATE EXTENSION IF NOT EXISTS vector;
  CREATE EXTENSION IF NOT EXISTS pg_trgm;
  ```
- [ ] Confirm all 8 core tables exist and columns match `BACKEND_SCHEMA.md` exactly.
- [ ] Verify that current and next month's partitions exist for the `items` table:
  ```sql
  -- Pre-create partitions for the current and next month if not created by scheduler
  CREATE TABLE IF NOT EXISTS items_y2026m06 PARTITION OF items FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
  ```
- [ ] Verify database indexes (`idx_items_user`, `idx_items_embedding` using HNSW, `idx_items_text_gin` using GIN, `idx_reminders_time_status`) are built.

### A2. Redis Configuration
- [ ] Verify connection to Upstash Redis REST endpoint.
- [ ] Test Redis connection and simple ping-pong using `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN`.
- [ ] Confirm sliding window keys are cleared or initialized correctly.

---

## SECTION B — Security & Secrets Audit

### B1. Code Leakage Checks
- [ ] Run code scan for hardcoded tokens:
  ```bash
  git grep -Ei "gemini_api_key|groq_api_key|telegram_bot_token|fernet_key|jwt_secret|google_client"
  ```
  $\rightarrow$ Ensure zero results in committed codebase.
- [ ] Verify `.env`, `.env.local`, `.venv/` and similar configuration directories are listed in `.gitignore`.

### B2. Environment Variables Mapping
- [ ] Verify all 15 backend environment variables are set in the Render dashboard:
  - `MODAL_API_TOKEN`, `TELEGRAM_BOT_TOKEN`, `DATABASE_URL`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `FERNET_KEY`, `JWT_SECRET`, `WEBSITE_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`.
- [ ] Verify all 2 frontend environment variables are set in the Vercel dashboard:
  - `VITE_API_URL`, `VITE_BOT_USERNAME`.

### B3. OAuth Credentials & Security Scope
- [ ] Verify Google Client ID matches Google Cloud Console.
- [ ] Confirm Google Redirect URI is exactly set to production callback:
  - `https://api.recall-app.com/auth/google/callback` (or your Render domain callback).
- [ ] Confirm OAuth scopes requested are restricted strictly to `drive.file` to prevent excessive file system access.
- [ ] Verify `FERNET_KEY` is exactly 32 URL-safe base64-encoded bytes (test token encryption/decryption with key).

---

## SECTION C — Deployment & Services Audit

### C1. Modal Serverless Deploy
- [ ] Verify local Modal token setup: `modal token set ...`
- [ ] Run test execution of the Modal app locally.
- [ ] Deploy the Modal serverless app to production:
  ```bash
  modal deploy app.py
  ```
- [ ] Test the deployment URL endpoint and update backend `MODAL_API_TOKEN` if changed.

### C2. Backend (Render) & Webhook Registration
- [ ] Deploy the FastAPI backend service to Render:
  - Ensure build command is `pip install -r requirements.txt`.
  - Ensure start command is `uvicorn main:app --host 0.0.0.0 --port $PORT`.
- [ ] Trigger Telegram Bot Webhook registration:
  - Call API endpoint: `https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=<RENDER_BACKEND_URL>/webhook`
  - Confirm webhook returns success: `{"ok": true, "result": true, "description": "Webhook was set"}`.

### C3. Frontend (Vercel) Build
- [ ] Verify frontend build command compiles React + Vite without TypeScript/Linting errors.
- [ ] Confirm build settings in Vercel:
  - Framework Preset: `Vite`.
  - Output Directory: `dist`.
- [ ] Check production deployment URL and confirm TLS certificates are valid (HTTPS active).

---

## SECTION D — Operations & Monitoring Audit

### D1. Uptime Robot & Keepalive
- [ ] Set up Uptime Robot HTTP monitor for backend health:
  - Target URL: `<RENDER_BACKEND_URL>/health`.
  - Frequency: Every 5 minutes (prevents Render free tier cold starts/spin-downs).
- [ ] Test that `GET /health` returns `200 OK` instantly with minimal latency.

### D2. APScheduler Verification
- [ ] Check backend application logs on Render start to verify scheduled tasks initialize:
  - `reminders_dispatcher` (runs every minute)
  - `louvain_clustering` (runs daily at 02:00 UTC)
  - `partition_creator` (runs monthly on the 25th at 00:00 UTC)
  - `drive_nudge_sender` (runs daily at 10:00 UTC)
  - `processed_updates_cleanup` (runs weekly)

### D3. Rate Limiting & DLQ Test
- [ ] Perform mock script execution to verify sliding window rate-limiter returns `429 Too Many Requests` on exceeding 20 req/min.
- [ ] Confirm failing ingestion tasks (e.g. invalid format ingestion) are routed successfully to `dead_letter_queue` and users receive the fallback bookmark nudge.
