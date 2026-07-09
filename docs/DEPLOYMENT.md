> **Audience**: DevOps Engineers, Maintainers  
> **Estimated Reading Time**: 6 min

# Deployment

This guide covers infrastructure hosting targets, environment configuration, and deployment topology for **Recall** under the frozen cost-effective architecture.

---

## 1. Environment Variables (28 Total)

Managed in `backend/config.py` using Pydantic `BaseSettings`.

### Mandatory Required Variables (8)
| Variable | Purpose |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token from @BotFather (Regex `^\d+:[A-Za-z0-9_-]{35}$`) |
| `DATABASE_URL` | Main Neon PostgreSQL database URL (with `?sslmode=require`) |
| `UPSTASH_REDIS_REST_URL` | Upstash Redis REST API endpoint |
| `UPSTASH_REDIS_REST_TOKEN` | Upstash Redis REST authentication token |
| `FERNET_KEY` | Key for Fernet symmetric encryption (32 URL-safe base64 bytes) |
| `JWT_SECRET` | Secret for signing JWT session cookies (Min 32 hex characters) |
| `WEBSITE_URL` | Base public URL of hosted frontend dashboard |
| `REMOTE_AI_URL` | Base URL of the Azure Student VM AI Service (e.g., `http://<azure-ip>:8001`) |

### Optional & Integration Variables (20)
* `EMBEDDING_PROVIDER`: Embedding generator option (`"remote"` to run FastEmbed on Azure VM; fallback `"local"`).
* `RERANKER_PROVIDER`: Reranker generator option (`"remote"` to run Reranker on Azure VM; fallback `"local"`).
* `SENTENCE_SPLITTER`: Text splitter option (`"remote"` to run spaCy on Azure VM; fallback `"spacy"`/`"regex"`).
* `GROQ_API_KEY`: Groq Cloud API key for Llama 3 70B & Whisper Turbo.
* `GEMINI_API_KEY`: Google Gemini API key for summaries and Gemini 2.5 Flash OCR (LLM fallback).
* `NVIDIA_API_KEY`: NVIDIA NIM API key for primary OCR (NVIDIA NIM OCR) and fallback models.
* `OPENROUTER_API_KEY`: OpenRouter API key fallback.
* `INTERNAL_API_KEY`: Admin queue header key (`X-Internal-Key`).
* `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`: Google OAuth credentials.
* `VITE_API_URL`, `VITE_BOT_USERNAME`: Frontend environment configuration references.
* `COBALT_API_URL`: Cobalt video metadata scraping instance URL (see [Section 3: Self-Hosted Cobalt Deployment](#3-self-hosted-cobalt-deployment-guide) for details).
* `COBALT_API_KEY`: Optional API key for authenticating requests to your self-hosted Cobalt instance.
* `BROWSER_FOR_COOKIES`, `IG_COOKIES_B64`: Cookie scraping options.
* `ENV`: Environment mode (`"development"`, `"staging"`, `"production"`).
* `MODAL_API_TOKEN`: (Optional/Deprecated) Modal serverless GPU API token.

---

## 2. Infrastructure Hosting Targets & Deployment Topology

Recall uses a split, zero-out-of-pocket production deployment strategy designed to minimize cost, bypass resource constraints (RAM/CPU), and keep system components decoupled.

```mermaid
flowchart TD
    subgraph Frontend_Host ["Vercel (Free)"]
        FE["Next.js / Vite SPA\n(Auth UI + Canvas Visuals)"]
    end

    subgraph Backend_Host ["Koyeb Free Tier (512 MB RAM)"]
        KOYEB_APP["Unified FastAPI Server\n(API + APScheduler + In-Process Worker)"]
    end

    subgraph AI_Host ["Azure Student VM (1 GB RAM)"]
        AI_SVC["Unified AI Service\n(FastEmbed, Reranker, spaCy)"]
        Cobalt["Cobalt Service\n(Media Downloader on Port 9000)"]
    end

    subgraph Cloud_APIs ["Third-Party Serverless"]
        Nvidia["NVIDIA NIM API\n(Primary OCR)"]
        Gemini["Gemini API\n(OCR Fallback, Summary)"]
        Groq["Groq API\n(Whisper Audio, LLM)"]
    end

    subgraph Managed_DB ["Serverless Storage"]
        DB[(Neon PostgreSQL\npgvector + pg_trgm)]
        Redis[(Upstash Redis\nQueue + Cache)]
    end

    FE -->|HTTP/WebSocket| KOYEB_APP
    KOYEB_APP -->|Queue Jobs / Read Queue| Redis
    KOYEB_APP -->|PostgreSQL Queries| DB
    KOYEB_APP -->|NVIDIA OCR| Nvidia
    KOYEB_APP -->|Gemini Fallback OCR / Summary| Gemini
    KOYEB_APP -->|Whisper Transcription| Groq
    KOYEB_APP -->|Unified AI Requests| AI_SVC
    KOYEB_APP -->|Media Download Requests| Cobalt
```

### Component Details & Cost Breakdown

| Component | Target Provider | Hosted Services / Roles | Resource Profile & Memory Footprint | Monthly Cost |
|---|---|---|---|---|
| **Frontend** | **Vercel** (Free Tier) | Next.js/Vite frontend static assets, Authentication UI. | N/A | **₹0** |
| **Core Backend** | **Koyeb** (Free Plan) | Single unified service running FastAPI API routes, business logic, background queue worker in-process (`RUN_WORKER_INLINE=True`), and APScheduler cron loops. Does **NOT** run OCR or local ML models. | **~150–300 MB RSS** (Leaves 200+ MB headroom out of 512 MB) | **₹0** |
| **AI Service** | **Azure Student VM** | Dedicated 1 GB VM hosting all heavy ML models (FastEmbed, Reranker, spaCy) and the Cobalt media downloader fallback service (runs on port 9000). Only the Koyeb backend communicates with this VM. | **~509 MB RSS + ~50 MB Cobalt** (Leaves ~400+ MB headroom out of 1 GB) | **₹0** (Covered by Azure Student credits) |
| **OCR Pipeline** | **NVIDIA / Gemini** | Image/PDF OCR processing. **NVIDIA NIM OCR** serves as the primary high-speed extractor, with **Gemini 2.5 Flash** as the multimodal LLM fallback. No local models. | Serverless | **₹0** (Using free NVIDIA NIM and Google AI Studio credits) |
| **Database** | **Neon** | Serverless PostgreSQL 16 database, vector storage via `pgvector`, fuzzy text indexes via `pg_trgm`, auto-backups. | Serverless | **₹0** (Within free limits) |
| **Task Queue / Cache** | **Upstash** | Serverless Redis instance for task queue, rate limiting, and session caching. | Serverless | **₹0** (Within free limits) |
| **LLMs & Audio** | **Gemini + Groq** | Gemini for vision and long-context reasoning; Groq for Whisper audio transcription and low-latency LLM tasks. | Serverless | **₹0** (Within free tier limits) |

---

### Step-by-Step Deployment Instructions

#### A. Azure Student VM (AI Service & Ingestion Setup)
1. **Provision VM**: Set up a Standard B1s or B1ms VM (1 GB RAM, Ubuntu 22.04 LTS) under your Azure Student subscription.
2. **Enable a 2 GB Swap File** (Crucial: Protects the 1 GB VM from crashing during transient memory spikes):
   ```bash
   sudo fallocate -l 2G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   ```
3. **AI Service API Setup**: Clone the repository and configure the AI service to run a lightweight FastAPI interface exposing:
   * `POST /embed`
   * `POST /rerank`
   * `POST /search-ai` (or `POST /semantic-search`)
4. **Run AI Service**: Wrap the application under `systemd` or run via Docker:
   ```bash
   # Run unified AI service on port 8001
   uvicorn ai_service.main:app --host 0.0.0.0 --port 8001
   ```
5. **Deploy Cobalt**: Launch a self-hosted Cobalt instance inside Docker on the same VM listening on port `9000`. 
   > [!TIP]
   > Do **not** initially set a hard memory limit cap on Cobalt. Run it uncapped first, monitor its footprint for a week under typical user loads, and only apply a container limit (e.g., `--memory="300m"`) if you notice it leaking or starving the AI service.
6. **Firewall & Security**: Configure the Azure Network Security Group (NSG) to allow inbound traffic on ports `8001` (AI Service) and `9000` (Cobalt) **only** from your Koyeb backend's IP block. Secure both endpoints with authorization keys (e.g., `INTERNAL_API_KEY`, `COBALT_API_KEY`).

#### B. Koyeb (Core Backend Setup)
1. Create a new service on Koyeb (Free tier, 512 MB RAM).
2. Add your database, Redis, and API key environment variables in the Koyeb service settings (including `REMOTE_AI_URL=http://<your-azure-ip>:8001` and `COBALT_API_URL=http://<your-azure-ip>:9000`).
3. Set the following environment variables to run the worker in-process and delegate heavy ML work to the Azure VM:
   ```bash
   RUN_WORKER_INLINE="true"
   EMBEDDING_PROVIDER="remote"
   RERANKER_PROVIDER="remote"
   SENTENCE_SPLITTER="remote"
   ```
4. Deploy the backend by linking your GitHub repository to Koyeb.

#### C. Vercel (Frontend Setup)
1. Link your frontend directory to Vercel.
2. Configure the `VITE_API_URL` environment variable to point to your Koyeb backend URL.
3. Deploy.

---

## 3. Post-Deployment Verification & Validation Checklist

Before declaring the architecture fully production-ready, perform the following stress-test on the Azure Student VM:
1. Start FastEmbed, Reranker, spaCy, and Cobalt simultaneously.
2. Trigger **3–5 concurrent Instagram Reel / TikTok downloads** while simultaneously running a document ingestion task through the embedding pipeline.
3. Open `htop` (or monitor via command line) and verify:
   * **RAM Usage** (`free -h`): Stays within acceptable limits (~660–810 MB idle, not triggering high cache eviction).
   * **Swap Activity** (`swapon --show`): Minimal usage. Swap handles transient spikes successfully without system freeze.
   * **CPU Load**: Load averages return back to normal levels post-ingest.

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
