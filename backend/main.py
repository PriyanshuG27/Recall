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
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Logging — structured, nothing sensitive
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
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

    yield  # ← application runs here

    # --- SHUTDOWN ---
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
# Global exception handler — NEVER expose internal details to clients
# ---------------------------------------------------------------------------
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
