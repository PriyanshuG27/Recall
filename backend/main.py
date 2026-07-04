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
class SecretMaskingFilter(logging.Filter):
    """
    Filters all log messages and redacts sensitive information such as
    the Telegram Bot Token, Fernet key, JWT secret, database passwords,
    and other API keys.
    """
    def __init__(self):
        super().__init__()
        self.telegram_pattern = re.compile(r"bot\d+:[A-Za-z0-9_-]+")

    def mask_text(self, text: str) -> str:
        # Mask Telegram bot tokens in URLs (e.g., bot8764400085:AAFo3...)
        text = self.telegram_pattern.sub("bot<REDACTED>", text)
        
        try:
            from backend.config import settings
            if settings:
                secrets = [
                    settings.TELEGRAM_BOT_TOKEN,
                    settings.FERNET_KEY,
                    settings.JWT_SECRET,
                    settings.UPSTASH_REDIS_REST_TOKEN,
                ]
                
                # Extract and mask DB password if present
                db_url = settings.DATABASE_URL
                if db_url:
                    # Match password component in connection string
                    match = re.search(r":([^@:]+)@", db_url)
                    if match:
                        secrets.append(match.group(1))
                
                # Mask other optional API keys/secrets
                for key in ["MODAL_API_TOKEN", "GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "NVIDIA_API_KEY"]:
                    val = getattr(settings, key, None)
                    if val:
                        secrets.append(val)
                
                for secret in secrets:
                    if secret and len(secret) > 4:
                        text = text.replace(secret, "<REDACTED>")
        except Exception:
            pass
            
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.mask_text(record.msg)
        if record.args:
            new_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    new_args.append(self.mask_text(arg))
                else:
                    new_args.append(arg)
            record.args = tuple(new_args)
        return True

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
mask_filter = SecretMaskingFilter()
root_logger = logging.getLogger()
root_logger.addFilter(mask_filter)

beautiful_formatter = BeautifulLoggerFormatter()

for handler in root_logger.handlers:
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

    # Validate cryptographic keys — raises ValueError on bad format
    settings.validate_crypto_keys()
    logger.info("Recall API started — crypto keys validated.")

    # Open the async DB connection pool
    await open_pool()

    # Initialize shared HTTP client
    import httpx
    app.state.client = httpx.AsyncClient(timeout=10.0)
    logger.info("Lifespan shared HTTP client initialized.")

    # Start the background task worker loop (skipped in test mode to prevent test suites from hanging)
    import sys
    if settings.ENV != "test" and "pytest" not in sys.modules:
        from backend.worker import start_worker_task
        app.state.worker_task = asyncio.create_task(start_worker_task())
        logger.info("Recall task worker loop started in background.")

    # Auto-retry recent DLQ tasks on startup (limit 5, failed < 24h ago)
    try:
        from backend.db.connection import _pool
        from backend.services.redis_client import redis
        import json
        
        if _pool is not None:
            async with _pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT id, task_payload FROM dead_letter_queue
                        WHERE retried = FALSE AND failed_at > NOW() - INTERVAL '24 hours'
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
                            
                        await redis.lpush("recall:tasks", json.dumps(payload))
                        await cur.execute("UPDATE dead_letter_queue SET retried = TRUE WHERE id = %s;", (dlq_id,))
                        requeued_count += 1
                        
                    if requeued_count > 0:
                        await conn.commit()
                        logger.info("Auto-requeued %d unretried tasks from DLQ on startup", requeued_count)
    except Exception as startup_retry_err:
        logger.error("Failed to execute startup DLQ auto-retry: %s", startup_retry_err)
    # Start background scheduler (skipped in test mode)
    if settings.ENV != "test" and "pytest" not in sys.modules:
        from backend.scheduler.scheduler import start_scheduler
        await start_scheduler(app)
        logger.info("Recall background scheduler started.")

    yield  # ← application runs here

    # --- SHUTDOWN ---
    # Cancel the task worker loop
    if hasattr(app.state, "worker_task"):
        app.state.worker_task.cancel()
        try:
            await app.state.worker_task
        except asyncio.CancelledError:
            pass
        logger.info("Recall task worker loop stopped.")

    # Close shared HTTP client
    from backend.services.http_client import close_http_client
    await close_http_client()
    logger.info("Lifespan shared HTTP client closed.")

    # Stop background scheduler
    from backend.scheduler.scheduler import stop_scheduler
    await stop_scheduler()

    from backend.db.connection import close_pool
    await close_pool()
    logger.info("Recall API shutdown complete.")


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
    title="Recall API",
    version="0.1.0",
    description=(
        "Recall — AI-powered second brain. "
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
    to the client — no stack traces, no exception types.
    """
    logger.exception(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={"error": "internal_server_error"},
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
from backend.routes.webhook import router as webhook_router
from backend.routes.auth import router as auth_router
from backend.routes.api import router as api_router
from backend.routes.websocket import router as websocket_router
from backend.routes.bridges import router as bridges_router

app.include_router(webhook_router)
app.include_router(auth_router)
app.include_router(api_router)
app.include_router(websocket_router)
app.include_router(bridges_router)

@app.get(
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


# ---------------------------------------------------------------------------
# OpenAPI Customisation & Security Definitions
# ---------------------------------------------------------------------------
from fastapi.openapi.utils import get_openapi
from backend.config import settings

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
        
    openapi_schema = get_openapi(
        title="Recall API",
        version="0.1.0",
        description=(
            "Recall — AI-powered second brain. "
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
            "name": "recall_session",
            "description": "JWT stored in the httpOnly 'recall_session' cookie.",
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
