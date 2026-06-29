"""
backend/db/connection.py
========================
Async PostgreSQL connection pool using psycopg3 (psycopg[async]).

Pool config:
  min_size=1, max_size=5  — respects Neon free-tier connection limit.
  Connection timeout: 5 s
  Query timeout:     30 s (applied per-cursor via options)

Exposes:
  get_db()        — FastAPI dependency that yields a single AsyncConnection.
  init_schema()   — Reads schema.sql and applies it to the DB (used by `make schema`).
  db_health_check() — Lightweight SELECT 1 liveness check.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import psycopg
from psycopg_pool import AsyncConnectionPool
from fastapi import HTTPException

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pool singleton — created on FastAPI startup, closed on shutdown
# ---------------------------------------------------------------------------
_pool: AsyncConnectionPool | None = None


async def open_pool() -> None:
    """Open the connection pool. Call from FastAPI lifespan startup."""
    global _pool

    # Import here to avoid circular imports at module load time
    from backend.config import settings  # noqa: PLC0415

    if settings is None:
        raise RuntimeError("Settings failed to load — cannot open DB pool.")

    if "sslmode" not in settings.DATABASE_URL:
        logger.warning(
            "DATABASE_URL does not contain 'sslmode'. "
            "Neon requires ?sslmode=require for encrypted connections."
        )

    async def check_conn(conn) -> None:
        await conn.execute("SELECT 1;")

    _pool = AsyncConnectionPool(
        conninfo=settings.DATABASE_URL,
        min_size=0,
        max_size=5,
        timeout=15.0,         # seconds to wait for a connection from the pool
        max_idle=240.0,       # close idle connections before Neon drops them (5m)
        check=check_conn,     # Validate connection health on checkout
        open=False,            # we open manually below
    )
    await _pool.open()
    logger.info("Database connection pool opened (min=0, max=5, max_idle=240s).")
    try:
        async with _pool.connection() as conn:
            await conn.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS context_prompt TEXT;")
            await conn.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS passive_context JSONB;")
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_day INT DEFAULT 0;")
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_last_sent TIMESTAMP DEFAULT NULL;")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS insight_candidates (
                    id                 SERIAL PRIMARY KEY,
                    user_id            INT REFERENCES users(id) ON DELETE CASCADE,
                    item_id_a          INT NOT NULL,
                    item_id_b          INT NOT NULL,
                    similarity_score   FLOAT NOT NULL,
                    bucket             VARCHAR(20) NOT NULL,
                    status             VARCHAR(20) DEFAULT 'pending',
                    insight_text       TEXT,
                    expires_at         TIMESTAMP,
                    cluster_pair_hash  VARCHAR(32),
                    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_candidates_user_status ON insight_candidates(user_id, status);")
            await conn.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS save_time_bucket VARCHAR(20);")
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS near_miss_lower_bound NUMERIC(4, 3) DEFAULT 0.710;")
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_recall_moment_at TIMESTAMP WITH TIME ZONE;")
            await conn.commit()
        logger.info("Dynamic schema check completed: items.context_prompt, items.passive_context, items.save_time_bucket, and insight_candidates verified/added.")
    except Exception as ddl_err:
        logger.error("Failed to run dynamic schema update: %s", ddl_err)


async def close_pool() -> None:
    """Close the connection pool. Call from FastAPI lifespan shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database connection pool closed.")


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------
async def get_db() -> AsyncGenerator[psycopg.AsyncConnection, None]:
    """
    FastAPI dependency that yields a checked-out AsyncConnection.

    Usage:
        @router.get("/example")
        async def handler(db: psycopg.AsyncConnection = Depends(get_db)):
            ...
    """
    if _pool is None:
        raise HTTPException(status_code=503, detail="Database pool is not initialised.")

    try:
        async with _pool.connection() as conn:
            # Apply a 30-second statement timeout to all queries on this connection
            await conn.execute("SET statement_timeout = '30s'")
            yield conn
    except psycopg.OperationalError as exc:
        logger.error("Database operational error: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Database temporarily unavailable. Please try again."
        ) from exc


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
async def db_health_check() -> bool:
    """
    Lightweight liveness check — runs SELECT 1 against the pool.
    Returns True if the database is reachable, False otherwise.
    Does NOT raise — safe to call from /health without risking 500s.
    """
    if _pool is None:
        return False
    try:
        async with _pool.connection() as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("DB health check failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Schema initialiser (used by `make schema`)
# ---------------------------------------------------------------------------
async def init_schema() -> None:
    """
    Reads backend/db/schema.sql and executes it against the database.

    This is idempotent — all DDL statements use IF NOT EXISTS.
    Run via:
        make schema
    or:
        python -c "import asyncio; from backend.db.connection import init_schema; asyncio.run(init_schema())"
    """
    schema_path = Path(__file__).parent / "schema.sql"
    if not schema_path.exists():
        raise FileNotFoundError(f"schema.sql not found at {schema_path}")

    sql = schema_path.read_text(encoding="utf-8")

    # We open a fresh temporary connection (pool may not be running yet)
    from backend.config import settings  # noqa: PLC0415

    if settings is None:
        raise RuntimeError("Settings failed to load — cannot initialise schema.")

    logger.info("Applying schema from %s ...", schema_path)
    async with await psycopg.AsyncConnection.connect(settings.DATABASE_URL) as conn:
        await conn.execute(sql)
        await conn.commit()
    logger.info("Schema applied successfully.")


if __name__ == "__main__":
    # Allow direct execution: python -m backend.db.connection
    logging.basicConfig(level=logging.INFO)
    asyncio.run(init_schema())
