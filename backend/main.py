"""
backend/main.py
===============
FastAPI application entry point for Recall API.

Startup sequence:
  1. validate_crypto_keys() — fast-fail if FERNET_KEY / JWT_SECRET / BOT_TOKEN are invalid.
  2. open_pool()            — open async psycopg3 connection pool.

Shutdown sequence:
  1. close_pool()           — drain and close pool gracefully.

Security:
  - CORS allows ONLY settings.WEBSITE_URL — never wildcard.
  - Global exception handler returns generic 500 — no stack traces to clients.
  - /docs and /redoc are DISABLED in production (ENV=production).
"""

import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Logging — structured, nothing sensitive
# ---------------------------------------------------------------------------
from backend.config import mask_filter

# Custom premium formatter for logging
class BeautifulLoggerFormatter(logging.Formatter):
    CYAN = "\x1b[36m"
    YELLOW = "\x1b[33m"
    RED = "\x1b[31m"
    BOLD_RED = "\x1b[31;1m"
    GREY = "\x1b[90m"
    RESET = "\x1b[0m"

    def format(self, record: logging.LogRecord) -> str:
        # Time format: HH:MM:SS
        time_str = self.formatTime(record, "%H:%M:%S")
        
        # Color-coded level mapping with custom icons
        level = record.levelname
        if record.levelno == logging.INFO:
            level_str = f"{self.CYAN}ℹ INFO{self.RESET}"
        elif record.levelno == logging.WARNING:
            level_str = f"{self.YELLOW}⚠ WARN{self.RESET}"
        elif record.levelno == logging.ERROR:
            level_str = f"{self.RED}✗ ERROR{self.RESET}"
        elif record.levelno == logging.CRITICAL:
            level_str = f"{self.BOLD_RED}💥 CRITICAL{self.RESET}"
        else:
            level_str = level

        # Clean up logger name prefix (e.g. backend.routes.webhook -> routes.webhook)
        logger_name = record.name
        if logger_name.startswith("backend."):
            logger_name = logger_name[8:]

        # Format line: [time] [level] [name]: message
        formatted = f"[{time_str}] [{level_str}] [{self.GREY}{logger_name}{self.RESET}] {record.getMessage()}"
        
        # Handle exceptions
        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)
            
        return formatted


# Initialize standard logging configuration
logging.basicConfig(level=logging.INFO)

# Apply secret masking filter and the premium BeautifulLoggerFormatter to all handlers
root_logger = logging.getLogger()
if mask_filter:
    root_logger.addFilter(mask_filter)

beautiful_formatter = BeautifulLoggerFormatter()

for handler in root_logger.handlers:
    if mask_filter:
        handler.addFilter(mask_filter)
    handler.setFormatter(beautiful_formatter)


# Suppress verbose third-party loggers to prevent log clutter
for logger_name in [
    "watchfiles.main",
    "watchfiles",
    "apscheduler",
    "sentence_transformers",
    "huggingface_hub",
    "httpx",
    "httpcore",
    "urllib3",
    "uvicorn.access",
]:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

# Suppress psycopg.pool connection warnings on shutdown/cancellation
logging.getLogger("psycopg.pool").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan: startup + shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs startup logic before yield, shutdown logic after."""
    # --- STARTUP ---
    from backend.config import settings
    from backend.db.connection import open_pool
    import asyncio

    if settings is None:
        raise RuntimeError(
            "CRITICAL: Settings failed to load. "
            "Check that all required environment variables are set."
        )

    # Initialize structured logging config
    from backend.services.logging_config import configure_logging
    configure_logging()

    # Initialize Sentry if DSN is set
    if settings.SENTRY_DSN:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastAPIIntegration
        from backend.services.pii_masker import mask_payload

        def before_send(event, hint):
            # Scrub any potential PII values in extra payload fields recursively
            if "extra" in event:
                event["extra"] = mask_payload(event["extra"])
            # Scrub stack trace local variables to prevent stack frame PII leakage
            if "exception" in event and "values" in event["exception"]:
                for value in event["exception"]["values"]:
                    if "stacktrace" in value and "frames" in value["stacktrace"]:
                        for frame in value["stacktrace"]["frames"]:
                            if "vars" in frame:
                                frame["vars"] = mask_payload(frame["vars"])
            return event

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.SENTRY_ENV,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            integrations=[FastAPIIntegration()],
            before_send=before_send
        )

    # Validate cryptographic keys — raises ValueError on bad format
    settings.validate_crypto_keys()
    logger.info("Atrium API started — crypto keys validated.")

    # Initialize Event Bus
    from backend.services.ai_cascade.events.event_bus import event_bus
    event_bus.initialize()

    # Open the async DB connection pool
    await open_pool()

    # Dynamic startup migrations — all use IF NOT EXISTS so safe on every boot
    try:
        import backend.db.connection as db_conn
        if db_conn._pool is not None:
            async with db_conn._pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "ALTER TABLE users ADD COLUMN IF NOT EXISTS initial_onboarding_completed BOOLEAN DEFAULT FALSE;"
                    )
                    await cur.execute(
                        "ALTER TABLE users ADD COLUMN IF NOT EXISTS mind_type_detailed TEXT;"
                    )
                await conn.commit()
            logger.info("Database startup migration: initial_onboarding_completed column ensured.")
            logger.info("Database startup migration: mind_type_detailed column ensured.")
    except Exception as migration_err:
        logger.error("Failed to run startup database migration: %s", migration_err)

    # Initialize shared HTTP client
    import httpx
    app.state.client = httpx.AsyncClient(timeout=10.0)
    logger.info("Lifespan shared HTTP client initialized.")

    # Preload and warm up the SOTA Rerank model if enabled locally
    if settings.ENABLE_RERANKING and settings.RERANK_PRELOAD_ON_STARTUP and getattr(settings, "RERANKER_PROVIDER", "local") != "remote":
        from backend.services.reranker import reranker_service
        await asyncio.to_thread(reranker_service.preload)

    # Start the background task worker loop (skipped if RUN_WORKER_INLINE is False or in test mode)
    import sys
    if settings.ENV != "test" and "pytest" not in sys.modules and settings.RUN_WORKER_INLINE:
        from backend.worker import start_worker_task
        app.state.worker_task = asyncio.create_task(start_worker_task())
        logger.info("Atrium task worker loop started in background (inline).")

    try:
        import backend.db.connection as db_conn
        from backend.services.redis_client import redis
        import json
        
        if db_conn._pool is not None:
            async with db_conn._pool.connection() as conn:
                async with conn.cursor() as cur:
                    # 1. Clean up already-retried DLQ entries older than 2h to stop the spam loop
                    await cur.execute(
                        "DELETE FROM dead_letter_queue WHERE retried = TRUE AND failed_at < NOW() - INTERVAL '2 hours';"
                    )
                    deleted = cur.rowcount if cur.rowcount is not None else 0

                    # 2. Requeue recent unretried tasks (6h window, not 24h)
                    await cur.execute(
                        """
                        SELECT id, task_payload FROM dead_letter_queue
                        WHERE retried = FALSE AND failed_at > NOW() - INTERVAL '6 hours'
                        LIMIT 5;
                        """
                    )
                    rows = await cur.fetchall()
                    
                    requeued_count = 0
                    for row in rows:
                        dlq_id, payload_raw = row
                        if isinstance(payload_raw, str):
                            payload = json.loads(payload_raw)
                        else:
                            payload = payload_raw

                        # Tag the payload so the worker knows this is a DLQ retry
                        # and won't re-DLQ it if it fails again
                        payload["from_dlq"] = True

                        await redis.lpush("atrium:tasks", json.dumps(payload))
                        from backend.worker import notify_new_task
                        notify_new_task()
                        await cur.execute("UPDATE dead_letter_queue SET retried = TRUE WHERE id = %s;", (dlq_id,))
                        requeued_count += 1
                        
                    if deleted > 0 or requeued_count > 0:
                        await conn.commit()
                    if deleted > 0:
                        logger.info("Cleaned up %d old retried DLQ entries.", deleted)
                    if requeued_count > 0:
                        logger.info("Auto-requeued %d unretried tasks from DLQ on startup", requeued_count)
    except Exception as startup_retry_err:
        logger.error("Failed to execute startup DLQ auto-retry: %s", startup_retry_err)
    # Start background scheduler (skipped in test mode)
    if settings.ENV != "test" and "pytest" not in sys.modules:
        from backend.scheduler.scheduler import start_scheduler
        await start_scheduler(app)
        logger.info("Atrium background scheduler started.")

    yield  # ← application runs here

    # --- SHUTDOWN ---
    # Gracefully await and cancel outstanding analytics background tasks
    from backend.services.analytics_service import shutdown_background_tasks
    await shutdown_background_tasks(timeout=5.0)

    # Cancel the task worker loop
    if hasattr(app.state, "worker_task"):
        app.state.worker_task.cancel()
        try:
            await app.state.worker_task
        except asyncio.CancelledError:
            pass
        logger.info("Atrium task worker loop stopped.")
        
        # Await outstanding background worker tasks (max 30s timeout)
        try:
            from backend.worker import worker_background_tasks
            if worker_background_tasks:
                logger.info("Awaiting %d active background worker tasks...", len(worker_background_tasks))
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*worker_background_tasks, return_exceptions=True),
                        timeout=30.0
                    )
                    logger.info("All background worker tasks completed gracefully.")
                except asyncio.TimeoutError:
                    logger.warning("Timed out waiting for background worker tasks to complete. Cancelling remaining %d tasks...", len(worker_background_tasks))
                    for task in list(worker_background_tasks):
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*worker_background_tasks, return_exceptions=True)
                    logger.info("All cancelled background worker tasks terminated.")
        except Exception as shutdown_err:
            logger.error("Error during graceful shutdown of worker tasks: %s", shutdown_err)


    # Close shared HTTP client
    from backend.services.http_client import close_http_client
    await close_http_client()
    logger.info("Lifespan shared HTTP client closed.")

    # Stop background scheduler
    from backend.scheduler.scheduler import stop_scheduler
    await stop_scheduler()

    from backend.db.connection import close_pool
    await close_pool()
    
    # Shutdown Event Bus
    from backend.services.ai_cascade.events.event_bus import event_bus
    event_bus.shutdown()
    
    logger.info("Atrium API shutdown complete.")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
def _get_docs_url() -> str | None:
    """Disable Swagger UI in production."""
    try:
        from backend.config import settings
        if settings and settings.ENV == "production":
            return None
    except Exception:
        pass
    return "/docs"


def _get_redoc_url() -> str | None:
    """Disable ReDoc in production."""
    try:
        from backend.config import settings
        if settings and settings.ENV == "production":
            return None
    except Exception:
        pass
    return "/redoc"


app = FastAPI(
    title="Atrium API",
    version="0.1.0",
    description=(
        "Atrium — AI-powered second brain. "
        "Ingest links, voice notes, PDFs and images via Telegram. "
        "Search, map, and quiz your knowledge via the web dashboard."
    ),
    lifespan=lifespan,
    docs_url=_get_docs_url(),
    redoc_url=_get_redoc_url(),
)


# ---------------------------------------------------------------------------
# CORS — restrict to frontend origin ONLY (never wildcard)
# ---------------------------------------------------------------------------
def _get_allowed_origins() -> list[str]:
    try:
        from backend.config import settings
        if settings and settings.WEBSITE_URL:
            return [settings.WEBSITE_URL]
    except Exception:
        pass
    # Fallback for local dev only — never used in production
    return ["http://localhost:5173"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_allowed_origins(),
    allow_credentials=True,       # Required for httpOnly cookie auth
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)



# ---------------------------------------------------------------------------
# HTTP Security Headers Middleware
# ---------------------------------------------------------------------------
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    # CSP: Allow self, inline script elements, and FastAPI docs dependencies
    csp_directives = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: https://fastapi.tiangolo.com;"
    )
    response.headers["Content-Security-Policy"] = csp_directives
    return response


from backend.middleware.structured_logging_middleware import structured_logging_middleware
app.middleware("http")(structured_logging_middleware)

# ---------------------------------------------------------------------------
from backend.services.rate_limiter import RateLimitExceeded

@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    retry_seconds = int(exc.retry_after)
    return JSONResponse(
        status_code=429,
        headers={"Retry-After": str(retry_seconds)},
        content={
            "error": "rate_limit_exceeded",
            "retry_after": retry_seconds
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all for unhandled exceptions.
    Logs the full traceback internally but returns only a generic message
    and a correlation ID to the client — no stack traces, no exception types.
    """
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    logger.exception(
        "Unhandled exception on %s %s [Correlation ID: %s]",
        request.method,
        request.url.path,
        correlation_id,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "correlation_id": correlation_id
        },
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
from backend.routes.webhook import router as webhook_router
from backend.routes.auth import router as auth_router
from backend.routes.api import router as api_router
from backend.routes.websocket import router as websocket_router
from backend.routes.hearth import router as hearth_router
from backend.routes.metrics import router as metrics_router

app.include_router(webhook_router)
app.include_router(auth_router)
app.include_router(api_router)
app.include_router(websocket_router)
app.include_router(hearth_router)
app.include_router(metrics_router, prefix="/api")

@app.get(
    "/health",
    tags=["ops"],
    summary="Health check",
    response_description="Service is alive",
)
@app.head(
    "/health",
    tags=["ops"],
    summary="Health check",
    response_description="Service is alive",
)
async def health() -> dict:
    """
    Lightweight liveness probe — no DB queries, no external calls.
    Target response time: < 5 ms.
    Used by Render health checks and Uptime Robot monitoring.
    """
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get(
    "/health/readiness",
    tags=["ops"],
    summary="Readiness check",
    response_description="Downstream dependencies are ready",
)
async def readiness() -> dict:
    """
    Readiness probe verifying DB and Redis availability.
    Target response time: < 10 ms (when warm).
    """
    import asyncio
    import backend.db.connection as db_conn
    from backend.services.redis_client import redis
    from fastapi import HTTPException
    
    # 1. Verify PostgreSQL connection with a 2-second timeout
    pg_ok = False
    if db_conn._pool is not None:
        try:
            async def check_pg():
                async with db_conn._pool.connection() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute("SELECT 1;")
                        await cur.fetchone()
                return True
            pg_ok = await asyncio.wait_for(check_pg(), timeout=2.0)
        except Exception as e:
            logger.error("Readiness check: PostgreSQL connection failed: %s", e)
            pg_ok = False
            
    # 2. Verify Upstash Redis connection with a 1-second timeout
    redis_ok = False
    try:
        async def check_redis():
            return await redis.ping()
        redis_ok = await asyncio.wait_for(check_redis(), timeout=1.0)
    except Exception as e:
        logger.error("Readiness check: Upstash Redis connection failed: %s", e)
        redis_ok = False

    if not pg_ok or not redis_ok:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "fail",
                "postgres": "ok" if pg_ok else "fail",
                "redis": "ok" if redis_ok else "fail",
            }
        )
        
    return {
        "status": "ok",
        "postgres": "ok",
        "redis": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# OpenAPI Customisation & Security Definitions
# ---------------------------------------------------------------------------
from fastapi.openapi.utils import get_openapi
from backend.config import settings

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
        
    openapi_schema = get_openapi(
        title="Atrium API",
        version="0.1.0",
        description=(
            "Atrium — AI-powered second brain. "
            "Ingest links, voice notes, PDFs and images via Telegram. "
            "Search, map, and quiz your knowledge via the web dashboard."
        ),
        routes=app.routes,
    )
    
    # Custom security schemes definitions
    openapi_schema["components"]["securitySchemes"] = {
        "bearerAuth": {
            "type": "apiKey",
            "in": "cookie",
            "name": "atrium_session",
            "description": "JWT stored in the httpOnly 'atrium_session' cookie.",
        },
        "telegramInitData": {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
            "description": "Telegram Web App initData in Authorization header (format: TelegramInitData <init_data>).",
        }
    }
    
    # Associate security schemes dynamically with all /api/* endpoints
    for path, path_item in openapi_schema.get("paths", {}).items():
        if path.startswith("/api/"):
            for method in path_item:
                path_item[method]["security"] = [
                    {"bearerAuth": []},
                    {"telegramInitData": []}
                ]
                
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Explicitly disable Swagger UI & ReDoc in production mode
if settings and settings.ENV == "production":
    app.docs_url = None
    app.redoc_url = None
