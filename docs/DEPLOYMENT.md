> **Audience**: DevOps Engineers, Maintainers  
> **Estimated Reading Time**: 5 min

# Deployment

This guide covers infrastructure hosting targets and environment configuration for **Recall**.

---

## 1. Environment Variables (27 Total)

Managed in `backend/config.py` using Pydantic `BaseSettings`.

### Mandatory Required Variables (7)
| Variable | Validation | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Regex `^\d+:[A-Za-z0-9_-]{35}$` | Telegram Bot API token from @BotFather |
| `DATABASE_URL` | Neon URL with `?sslmode=require` | Main Neon PostgreSQL database URL |
| `UPSTASH_REDIS_REST_URL` | Valid REST URL | Upstash Redis REST API endpoint |
| `UPSTASH_REDIS_REST_TOKEN` | Token string | Upstash Redis REST authentication token |
| `FERNET_KEY` | 32 URL-safe base64 bytes | Key for Fernet symmetric encryption |
| `JWT_SECRET` | Min 32 hex characters | Secret for signing JWT session cookies |
| `WEBSITE_URL` | Valid URL string | Base public URL of hosted frontend dashboard |

### Optional Variables (20)
* `MODAL_API_TOKEN`: Modal serverless GPU API token.
* `GROQ_API_KEY`: Groq Cloud API key for Llama 3 70B & Whisper Turbo.
* `GEMINI_API_KEY`: Google Gemini API key for multimodal summaries.
* `OPENROUTER_API_KEY`: OpenRouter API key fallback.
* `NVIDIA_API_KEY`: NVIDIA NIM API key fallback.
* `COMPUTE_PROVIDER`: Compute provider override.
* `INTERNAL_API_KEY`: Admin queue header key (`X-Internal-Key`).
* `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`: Google OAuth credentials.
* `VITE_API_URL`, `VITE_BOT_USERNAME`: Frontend environment configuration references.
* `HF_TOKEN`: HuggingFace inference token.
* `COBALT_API_URL`: Cobalt video metadata scraping instance URL.
* `BROWSER_FOR_COOKIES`, `IG_COOKIES_B64`: Cookie scraping options.
* `ENV`: Environment mode (`"development"`, `"staging"`, `"production"`).

---

## 2. Infrastructure Hosting Targets

1. **Backend Web Service (Render / Railway)**: Uvicorn server: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`. Health probe: `GET /health` (< 5ms).
2. **Frontend SPA (Vercel / Netlify)**: Vite build output: `frontend/dist/`. Rewrite: `/* -> /index.html`.
3. **Database (Neon PostgreSQL 16)**: PostgreSQL 16 serverless instance with `vector` and `pg_trgm` extensions enabled.
4. **Queue & Cache (Upstash Redis)**: Serverless Redis REST endpoint for task queue and WebSocket pub/sub.
5. **Serverless GPU Apps (Modal)**: GPU app deployment configs in `backend/modal_apps/`.


---

← [Development](DEVELOPMENT.md) | [Security](SECURITY.md) →

## Related Documentation

[README](../README.md) · [Index](INDEX.md) · [Architecture](ARCHITECTURE.md) · [Database](DATABASE.md) · [API](API.md) · [Features](FEATURES.md)  
[Development](DEVELOPMENT.md) · **Deployment** · [Security](SECURITY.md) · [Testing](TESTING.md) · [Contributing](CONTRIBUTING.md) · [Diagrams](DIAGRAMS.md) · [ADRs](adr/README.md)
