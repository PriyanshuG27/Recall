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
        timeout=30.0,         # seconds to wait for a connection from the pool (Neon cold starts can take 15-20s)
        max_idle=240.0,       # close idle connections before Neon drops them (5m)
        check=check_conn,     # Validate connection health on checkout
        open=False,            # we open manually below
    )
    await _pool.open()
    logger.info("Database connection pool opened (min=0, max=5, max_idle=240s).")
    try:
        import os
        schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
        with open(schema_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()

        async with _pool.connection() as conn:
            await conn.execute(schema_sql)
            await conn.commit()
        logger.info("Dynamic schema check completed: tables and columns verified/added successfully from schema.sql.")
        await seed_static_centroids(_pool)
    except Exception as ddl_err:
        logger.error("Failed to run dynamic schema update: %s", ddl_err)


async def seed_static_centroids(pool) -> None:
    """Seed the 200 static domain centroids if the table is empty."""
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) FROM static_domain_centroids;")
                row = await cur.fetchone()
                if row and row[0] > 0:
                    return
                
                logger.info("Seeding static_domain_centroids table with 200 general knowledge domains...")
                from backend.services.search_service import embed_text
                
                domains = [
                    # Philosophy & Ethics (30)
                    "Stoicism", "Epistemology", "Existentialism", "Ethics", "Utilitarianism", "Metaphysics", "Nihilism", "Absurdism", 
                    "Phenomenology", "Scholasticism", "Hermeneutics", "Dialectics", "Cynicism", "Epicureanism", "Rationalism", "Empiricism",
                    "Pragmatism", "Dualism", "Solipsism", "Virtue Ethics", "Postmodernism", "Deontology", "Aesthetics", "Eastern Philosophy",
                    "Taoism", "Buddhism", "Confucianism", "Logical Positivism", "Political Philosophy", "Philosophy of Mind",
                    # Science & Mathematics (40)
                    "Quantum Mechanics", "Astrophysics", "Organic Chemistry", "Evolutionary Biology", "Genetics", "Neuroscience", "Cognitive Science",
                    "Chaos Theory", "Linear Algebra", "Calculus", "Topology", "Number Theory", "Probability Theory", "Game Theory", "Thermodynamics",
                    "Information Theory", "Fractal Geometry", "Complexity Science", "Special Relativity", "General Relativity", "Particle Physics",
                    "String Theory", "Cosmology", "Molecular Biology", "Immunology", "Neuroanatomy", "Epidemiology", "Plate Tectonics", "Meteorology",
                    "Astronomy", "Quantum Computing", "Statistical Mechanics", "Number Theory", "Cryptography", "Graph Theory", "Discrete Mathematics",
                    "Set Theory", "Mathematical Logic", "Abstract Algebra", "Fluid Dynamics",
                    # Computer Science & Technology (40)
                    "Software Architecture", "Machine Learning", "Deep Learning", "Database Systems", "Functional Programming", 
                    "Object-Oriented Design", "Distributed Systems", "Compiler Design", "Cyber Security", "Computer Networks", "Operating Systems",
                    "Algorithm Complexity", "Automata Theory", "Artificial Intelligence", "Natural Language Processing", "Computer Vision",
                    "Reinforcement Learning", "Cloud Computing", "DevOps", "Frontend Engineering", "Backend Engineering", "System Design",
                    "Blockchain Technology", "Web3 Development", "Internet of Things", "Human-Computer Interaction", "Virtual Reality",
                    "Augmented Reality", "Embedded Systems", "Parallel Computing", "Graphics Programming", "Web Security", "Penetration Testing",
                    "API Design", "Agile Methodologies", "Test-Driven Development", "Microservices", "Serverless Architecture", "Containerization",
                    "Database Normalization",
                    # History & Politics (30)
                    "World War II", "Roman Empire", "French Revolution", "Industrial Revolution", "Cold War", "Renaissance", "Classical Antiquity",
                    "Marxism", "Capitalism", "Liberalism", "Anarchism", "Geopolitics", "Ancient Egypt", "American Civil War", "Feudalism", 
                    "Decolonization", "Ottoman Empire", "British Empire", "Ancient Greece", "Middle Ages", "Russian Revolution", "Civil Rights Movement",
                    "Globalization", "Imperialism", "Feudal Japan", "World War I", "Age of Discovery", "Scientific Revolution", "Enlightenment",
                    "Fascism",
                    # Business & Economics (30)
                    "Microeconomics", "Macroeconomics", "Behavioral Economics", "Venture Capital", "Corporate Finance", "Game Development",
                    "Product Management", "Brand Strategy", "Supply Chain Management", "Cryptocurrencies", "Marketing Analytics", 
                    "Business Model Innovation", "Financial Markets", "Asset Valuation", "Game Theory", "Startup Equity", "Valuation Models",
                    "Strategic Management", "Consumer Behavior", "Design Thinking", "Search Engine Optimization", "Growth Hacking", 
                    "Sales Strategy", "Operations Research", "Development Economics", "Game Economics", "Mergers & Acquisitions", "Monetary Policy",
                    "Fiscal Policy", "Econometrics",
                    # Art, Literature & Media (20)
                    "Creative Writing", "Modern Art", "Renaissance Painting", "Architecture", "Cinematography", "Screenwriting", 
                    "Literary Criticism", "Music Theory", "Graphic Design", "Photography", "Sculpture", "Impressionism", "Surrealism",
                    "Typography", "Color Theory", "Game Design", "Narrative Design", "Poetry", "Art History", "Classical Music",
                    # Psychology & Self-Improvement (10)
                    "Habit Formation", "Cognitive Behavioral Therapy", "Meditation & Mindfulness", "Emotional Intelligence", "Sleep Science",
                    "Productivity Systems", "Psychoanalysis", "Behavioral Psychology", "Developmental Psychology", "Social Psychology"
                ]
                
                sem = asyncio.Semaphore(5)
                async def process_domain(domain):
                    async with sem:
                        emb = await embed_text(domain)
                        return domain, emb
                
                tasks = [process_domain(d) for d in domains]
                results = await asyncio.gather(*tasks)
                
                for domain, emb in results:
                    await cur.execute(
                        "INSERT INTO static_domain_centroids (domain_name, embedding) VALUES (%s, %s) ON CONFLICT (domain_name) DO NOTHING;",
                        (domain, emb)
                    )
                await conn.commit()
                logger.info("Successfully seeded 200 static domain centroids.")
    except Exception as seed_err:
        logger.error("Failed to seed static domain centroids: %s", seed_err)


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
