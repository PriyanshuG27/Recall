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
* `COBALT_API_URL`: Cobalt video metadata scraping instance URL (see [Section 3: Self-Hosted Cobalt Deployment](#3-self-hosted-cobalt-deployment-guide) for details).
* `COBALT_API_KEY`: Optional API key for authenticating requests to your self-hosted Cobalt instance.
* `BROWSER_FOR_COOKIES`, `IG_COOKIES_B64`: Cookie scraping options.
* `ENV`: Environment mode (`"development"`, `"staging"`, `"production"`).

---

## 2. Infrastructure Hosting Targets

1. **Backend Web Service (Hugging Face Spaces - Recommended for Free Hosting)**: Deployed using the **Docker SDK** (which provides 2 vCPUs and 16 GB of RAM for free).
   * **Port**: Must listen on port `7860` (Hugging Face default).
   * **System Dependencies**: The Docker image must install system libraries (`libgl1-mesa-glx`, `libglib2.0-0`, and `libgomp1` via `apt`) to support PaddleOCR and OpenCV locally.
   * **Uptime (Auto-sleep prevention)**: Configure a free monitoring service (e.g., UptimeRobot, Cron-job.org) targeting `GET /health` once every 10–15 minutes to prevent the Space from sleeping after 48 hours of inactivity.
   * **CI/CD (Auto-deployment via GitHub Actions)**: Automate deployments on push to GitHub by generating a Hugging Face Write Token, adding it as a repository secret (`HF_TOKEN`), and creating `.github/workflows/deploy.yml`:
     ```yaml
     name: Deploy to Hugging Face Spaces
     on:
       push:
         branches: [main]
     jobs:
       deploy:
         runs-on: ubuntu-latest
         steps:
           - name: Checkout Repository
             uses: actions/checkout@v3
             with:
               fetch-depth: 0
               lfs: true
           - name: Push to Hugging Face
             env:
               HF_TOKEN: ${{ secrets.HF_TOKEN }}
             run: |
               git push --force https://<your_username>:$HF_TOKEN@huggingface.co/spaces/<your_username>/<your_space_name> main
     ```
   * *Alternative (Koyeb Serverless)*: Runs on 512 MB RAM / 0.1 vCPU. Note that PaddleOCR will fail (OOM) and FastEmbed will be extremely slow on Koyeb's free tier.
2. **Frontend SPA (Vercel / Netlify)**: Vite build output: `frontend/dist/`. Rewrite: `/* -> /index.html`.
3. **Database (Neon PostgreSQL 16)**: PostgreSQL 16 serverless instance with `vector` and `pg_trgm` extensions enabled.
4. **Queue & Cache (Upstash Redis)**: Serverless Redis REST endpoint for task queue and WebSocket pub/sub.
5. **Serverless GPU Apps (Modal - Optional/Deprecated)**: GPU app deployment configs in `backend/modal_apps/`. Since Hugging Face provides enough RAM and CPU capacity to run PaddleOCR and FastEmbed locally, Modal is optional and can be bypassed for standard usage.
6. **Optional Media Downloader Fallback (Cobalt)**: Docker container hosted on Hugging Face Spaces (Docker SDK) or a VPS (see [Section 3](#3-self-hosted-cobalt-deployment-guide)).

---

## 3. Self-Hosted Cobalt Deployment Guide

Cobalt is used as a fallback downloader for Instagram Reels and TikToks when local `yt-dlp` runs into scraper blocks.

To deploy Cobalt successfully, there are critical configuration nuances that are often overlooked during setup:

### A. Crucial Environment Variables (for Cobalt Container)
When deploying Cobalt as a Docker service (e.g., on Hugging Face Spaces, Railway, or a VPS), configure the following environment variables **on the Cobalt instance**:

| Variable Name | Required | Purpose / Setup Nuance |
|---|---|---|
| `API_URL` | **Yes** | **Must be set to the public-facing URL of the Cobalt service** (e.g., `https://username-space-name.hf.space/` or `https://cobalt.yourdomain.com/`). If omitted or misconfigured, Cobalt returns download URLs pointing to `http://localhost:9000` or incorrect ports, causing media download requests from the Recall backend to fail. |
| `API_LISTEN_ADDRESS` | **Yes** | Set to `0.0.0.0` in containerized environments so that the service binds to all interfaces rather than just localhost. |
| `PORT` | **Yes** | The port the container listens on. On Hugging Face Spaces, set this to `7860`. On other platforms, make sure this matches the port mapped/injected by your hosting platform. |
| `CORS_WILDCARD` | No | Set to `1` to allow cross-origin requests from any domain. |

### B. Bypassing Cloud Hosting IP Blocks (Instagram & YouTube)
> [!IMPORTANT]
> Standard cloud hosting providers (Hugging Face/AWS, Railway, Render, AWS, GCP, etc.) utilize public IP ranges that are heavily blacklisted or aggressively rate-limited by Instagram and YouTube. 
> 
> An out-of-the-box Cobalt deployment on these platforms will immediately fail with `429 Too Many Requests` or socket timeouts when trying to scrape Reels.

* **Solution 1: Cloudflare WARP Tunneling (100% Free - Recommended for Hugging Face)**:
  Configure your Hugging Face Space Dockerfile to run both the Cloudflare WARP client (`warp-cli` / `wgcf`) and Cobalt. 
  * Have the WARP client run as a local SOCKS5/HTTP proxy (e.g. at `http://127.0.0.1:1080`).
  * Start the Cobalt server with:
    * `HTTP_PROXY=http://127.0.0.1:1080`
    * `HTTPS_PROXY=http://127.0.0.1:1080`
  This routes all download traffic through Cloudflare's trusted consumer network, bypassing datacenter IP bans completely for free.
* **Solution 2: Residential / Rotating Proxies**: 
  Configure Cobalt's environment variables to route its outbound traffic through a proxy provider:
  * `HTTP_PROXY`: e.g., `http://username:password@proxy.provider.com:port`
  * `HTTPS_PROXY`: e.g., `http://username:password@proxy.provider.com:port`

### C. Security and Access Control
* **API Key Authentication (Recommended)**:
  Configure your self-hosted Cobalt instance to require an API key by setting its authentication settings. Then, define the corresponding `COBALT_API_KEY` environment variable in the Recall backend.
  * The Recall backend will automatically attach `Authorization: Api-Key <your_key>` to all outgoing requests to your Cobalt instance.
* **Obfuscation & Network Isolation**:
  * Keep your `COBALT_API_URL` secret.
  * Optionally, restrict incoming traffic to your Cobalt service (using a reverse proxy like Nginx/Caddy or platform firewalls) so that it only accepts requests originating from the Recall backend's IP address.

---

← [Development](DEVELOPMENT.md) | [Security](SECURITY.md) →

## Related Documentation

[README](../README.md) · [Index](INDEX.md) · [Architecture](ARCHITECTURE.md) · [Database](DATABASE.md) · [API](API.md) · [Features](FEATURES.md)  
[Development](DEVELOPMENT.md) · **Deployment** · [Security](SECURITY.md) · [Testing](TESTING.md) · [Contributing](CONTRIBUTING.md) · [Diagrams](DIAGRAMS.md) · [ADRs](adr/README.md)
