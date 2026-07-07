# Production Operations & Runbook (05_PRODUCTION)

**Purpose:** This document defines the strict operational procedures, infrastructure topology, and disaster recovery strategies required to run Recall safely in a production environment. 

---

## 1. Deployment
*   **Infrastructure Strategy:** Recall utilizes Platform-as-a-Service (PaaS) to minimize DevOps overhead for V1.
*   **Frontend:** React SPA is deployed on Vercel. Deploys trigger automatically on pushes to the `main` branch.
*   **Backend API & Workers:** FastAPI and asyncio workers are deployed on Render or Koyeb using immutable Docker containers. The API and Worker run as separate services scaled independently.
*   **Database:** Neon Serverless PostgreSQL.
*   **Queue/Cache:** Upstash Serverless Redis.

## 2. Monitoring
*   **System Metrics:** CPU, RAM, and network I/O are monitored via the PaaS provider dashboards (Render/Koyeb).
*   **Database Metrics:** Connection pool limits, query latency, and index hit rates are monitored via the Neon control panel.
*   **AI Metrics:** Token usage, provider latencies (Groq/Gemini), and cost accumulation are monitored via Langfuse SaaS.
*   **Queue Health:** Redis `LLEN recall:tasks` and `LLEN recall:processing` must be actively monitored. A queue length > 100 triggers a high-latency alert.

## 3. Scaling
*   **Web Tier:** The FastAPI web tier scales horizontally automatically based on CPU utilization (>70%).
*   **Worker Tier:** The background worker tier scales horizontally based on queue depth. Each worker enforces a strict `Semaphore(3)` limit to cap concurrent LLM API calls.
*   **Database:** Scales vertically via Neon's auto-suspend and auto-scale compute endpoints.
*   **Connection Limits:** Scaling workers linearly increases active Postgres connections. If workers exceed 5 instances, a PgBouncer multiplexer must be deployed in front of Neon.

## 4. Security
*   **Secrets Management:** All API keys (Groq, Gemini, Telegram) and the `FERNET_KEY` are injected via secure PaaS environment variables. They are never committed to version control.
*   **Encryption:** The `FERNET_KEY` handles AES-128 symmetric encryption for `items.raw_text`.
*   **API Security:** All webhooks validate the `X-Telegram-Bot-Api-Secret-Token`. Web UI relies on httpOnly, Secure JWT cookies.
*   **Tenant Isolation:** All database reads/writes strictly enforce `WHERE user_id = $1` at the query builder level.

## 5. Observability
*   **Logging:** `structlog` outputs JSON lines to stdout. Logs are aggregated by the PaaS provider (or forwarded to Datadog).
*   **Correlation:** Every incoming request is assigned an `X-Request-ID` via FastAPI middleware. This ID propagates through the Redis queue into the worker logs.
*   **Error Tracking:** Sentry SDK intercepts all unhandled exceptions in the API and workers, attaching the `X-Request-ID` and stack traces.

## 6. Backups
*   **Database (Continuous):** Neon provides continuous Point-in-Time Recovery (PITR) with a 7-day retention window.
*   **Database (Cold Storage):** A weekly APScheduler cron triggers a `pg_dump` (schema and data) which is pushed to an encrypted AWS S3 bucket.
*   **Secrets:** The `FERNET_KEY` and third-party API tokens are backed up in a secure offline password vault (e.g., 1Password/Bitwarden) restricted to core admins.

## 7. Rollback
*   **Code Rollback:** Since deployments use immutable Docker image tags, rolling back a severe regression requires reverting the PaaS deployment to the previous known-good image tag (an instant traffic shift).
*   **Database Rollback:** Handled via Alembic `downgrade` scripts. 
    *   *Rule:* No `upgrade` migration may be merged unless a verified, non-destructive `downgrade` script exists.
*   **AI Degradation Rollback:** If an LLM provider degrades, environmental variables (`PRIMARY_MODEL`) can be hot-swapped to route traffic to the fallback provider without a code deploy.

## 8. Incident Response
*   **Severity 1 (Data Loss / Security Breach):**
    1. Lock down API access (toggle `MAINTENANCE_MODE=true`).
    2. Rotate `FERNET_KEY` and third-party API tokens.
    3. Identify breach vector using structlog JSON streams.
    4. Restore DB from Neon PITR if corruption occurred.
*   **Severity 2 (System Outage):**
    1. Check Sentry for unhandled exceptions.
    2. Check Redis queue length (`recall:tasks`).
    3. Scale up worker containers or pause ingestion if API rate limits (HTTP 429) are causing infinite loops.

## 9. Load Testing
*   **Mechanism:** Use `Locust` to simulate 500 concurrent users pushing 1,000 Telegram webhooks per minute.
*   **Objectives:** Verify the webhook endpoint returns HTTP 200 in <50ms under load, and verify that the worker `Semaphore(3)` successfully throttles outbound LLM calls without crashing the container.

## 10. Health Checks
*   **Endpoint:** `/health`
*   **Checks Performed:** 
    1. API responsiveness (200 OK).
    2. PostgreSQL connection check (`SELECT 1`).
    3. Redis ping (`PING`).
*   **Liveness Probe:** Used by Koyeb/Render to restart stalled API containers.

## 11. Disaster Recovery
*   **Scenario: Regional Data Center Outage:**
    *   Since Render/Neon are multi-zone, rely on cloud provider redundancies.
*   **Scenario: Provider Ban (e.g., Groq terminates account):**
    *   Update `PRIMARY_PROVIDER` to `gemini` in environment variables. The AI Cascade engine handles the routing switch seamlessly.
*   **Scenario: Total Database Loss:**
    *   Provision a new Postgres instance.
    *   Restore from the weekly S3 `pg_dump` cold backup.

## 12. CI/CD
*   **Continuous Integration:** GitHub Actions runs `pytest`, `flake8`, `mypy`, and `promptfoo` (for AI regression testing) on every Pull Request.
*   **Continuous Deployment:** Merging a PR into `main` automatically triggers Vercel (Frontend) and Koyeb/Render (Backend) image builds and deployments.

## 13. Versioning
*   **Format:** Semantic Versioning (SemVer) `MAJOR.MINOR.PATCH`.
*   **MAJOR:** Breaking schema changes or fundamental UX redesigns.
*   **MINOR:** New pipelines, AI providers, or feature additions.
*   **PATCH:** Bug fixes, prompt tweaks, and security patches.
*   **API:** All external REST endpoints are prefixed with `/api/v1/`.

## 14. Release Strategy
*   **Feature Flags:** Large features (e.g., GraphRAG extraction) are merged into `main` but hidden behind an environment variable toggle (`ENABLE_GRAPH_RAG=false`).
*   **Dark Launching:** New AI pipelines run in the background (logging results to Langfuse) without returning data to the user until quality is verified via `promptfoo`.

## 15. Production Checklist (Pre-Launch)
*   [ ] `FERNET_KEY` is securely generated and injected via PaaS, not hardcoded.
*   [ ] Telegram Webhook HMAC validation is enabled and tested.
*   [ ] Structlog JSON formatting is enabled (`LOG_FORMAT=json`).
*   [ ] Sentry DSN is configured and tested.
*   [ ] Redis `brpoplpush` heartbeat reaper is active.
*   [ ] Alembic migrations are up to date and `head` matches DB schema.
*   [ ] Neon Postgres connection pool limits are configured correctly against max worker count.
