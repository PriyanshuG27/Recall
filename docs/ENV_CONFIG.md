# ENV_CONFIG — Recall

| Field | Value |
|-------|-------|
| Version | 0.1.0 |
| Date | 2026-06-19 |
| Status | Draft |

---

## Backend Variables (Render)

| Variable | Purpose | Where to Get | Required | Notes |
|----------|---------|--------------|----------|-------|
| `MODAL_API_TOKEN` | Authenticates calls to Modal serverless GPU endpoints | Modal dashboard -> Settings -> API Tokens | Yes (Tier 0) | Without this, falls to Tier 1 |
| `TELEGRAM_BOT_TOKEN` | Bot API auth + TWA initData HMAC signing key | @BotFather -> /newbot | **Required** | Never expose client-side |
| `DATABASE_URL` | Neon PostgreSQL pooled connection string | Neon dashboard -> Connection Details -> Pooled | **Required** | Must include `?sslmode=require` |
| `UPSTASH_REDIS_REST_URL` | Upstash Redis REST endpoint | Upstash console -> REST API | **Required** | Ends in `.upstash.io` |
| `UPSTASH_REDIS_REST_TOKEN` | Upstash Redis auth token | Upstash console -> REST API | **Required** | — |
| `GROQ_API_KEY` | Groq Cloud API (Tier 1 Whisper-Turbo + Qwen3 / Llama 4) | console.groq.com -> API Keys | Yes (Tier 1) | Without this, falls to Tier 2 |
| `GEMINI_API_KEY` | Gemini 3.1 Flash-Lite (Tier 2 fallback) | Google AI Studio -> Get API Key | Yes (Tier 2) | Without this, falls to Tier 3/4 |
| `FERNET_KEY` | AES-128 symmetric encryption for raw_text + google_refresh_token | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` | **Required** | Rotation requires migrating all encrypted rows |
| `JWT_SECRET` | Signs website session JWTs (7-day expiry, httpOnly cookie) | `python -c "import secrets; print(secrets.token_hex(32))"` | **Required** | Change requires all users to re-login |
| `WEBSITE_URL` | Vercel frontend URL; used in OAuth redirect construction | Vercel dashboard after deploy | **Required** | Include `https://`, no trailing slash |
| `GOOGLE_CLIENT_ID` | Google OAuth 2.0 client ID | Google Cloud Console -> Credentials | Yes (Drive) | — |
| `GOOGLE_CLIENT_SECRET` | Google OAuth 2.0 client secret | Google Cloud Console -> Credentials | Yes (Drive) | — |
| `GOOGLE_REDIRECT_URI` | OAuth callback URL registered in Google Cloud Console | Set to `https://<render-url>/auth/google/callback` | Yes (Drive) | Must match exactly what is in GCP |
| `OLLAMA_HOST` | Ollama local model server URL (e.g. `http://localhost:11434`) | Self-hosted Ollama instance | Optional | Active in local development cascade |
| `LOCAL_MODE` | Boolean flag to prioritize local Ollama execution over API tiers | Set to `true` or `false` | Optional | Development only; default: `false` |
| `COMPUTE_PROVIDER` | Override cascade tier for testing (e.g. `groq`, `gemini`, `ollama`, `modal`) | — | Optional | Development / CI only |

---

## Frontend Variables (Vercel)

| Variable | Purpose | Where to Get | Required |
|----------|---------|--------------|----------|
| `VITE_API_URL` | Backend FastAPI base URL | Render dashboard after deploy | **Required** |
| `VITE_BOT_USERNAME` | Bot username without `@` (for Telegram Login Widget) | @BotFather or Telegram bot profile | **Required** |

---

## Optional Scraping Variables (Render)

| Variable | Purpose | Where to Get | Required |
|----------|---------|--------------|----------|
| `ZENROWS_KEY` | ZenRows web scraping proxy (Instagram Tier 0) | zenrows.com dashboard | Optional |
| `SCRAPINGBEE_KEY` | ScrapingBee proxy (Instagram Tier 1) | scrapingbee.com dashboard | Optional |
| `SCRAPERAPI_KEY` | ScraperAPI proxy (Instagram Tier 2) | scraperapi.com dashboard | Optional |

> If all three scraping keys are absent, Instagram Reel ingestion falls back to direct yt-dlp, then bookmark.

---

## Variable Count Summary

| Service | Count |
|---------|-------|
| Render (backend) | 15 |
| Vercel (frontend) | 2 |
| Optional scraping | 3 |
| **Total** | **20** |

---

## Security Notes

- All secrets are stored as environment variables; never committed to source control.
- `FERNET_KEY` and `JWT_SECRET` are the two highest-sensitivity variables — treat as root credentials.
- `TELEGRAM_BOT_TOKEN` must never appear in frontend code or logs.
- Scraping API keys are rate-limited; monitor usage dashboards monthly.
