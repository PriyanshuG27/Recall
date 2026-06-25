"""
backend/services/url_ingester.py
================================
Service layer for URL scraping and ingestion in Recall.
"""

import logging
import httpx
from bs4 import BeautifulSoup
from psycopg import AsyncConnection
from backend.services.encryption import encrypt
from backend.services.search_service import embed_text
from backend.services.ai_cascade import AICascade

logger = logging.getLogger(__name__)

async def scrape_url(url: str) -> tuple[str, str]:
    """
    Scrapes the given URL and returns (title, clean_text).
    If scraping fails, returns (URL, URL).
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning("Scraping URL %s returned status %d", url, resp.status_code)
                return url, url
            
            html = resp.text
            soup = BeautifulSoup(html, "html.parser")
            
            # Extract title
            title = "Untitled Link"
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
            
            # Clean up scripts, styles, and other metadata
            for script_or_style in soup(["script", "style", "meta", "noscript", "header", "footer", "nav"]):
                script_or_style.decompose()
                
            # Get text
            text = soup.get_text(separator="\n")
            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = "\n".join(chunk for chunk in chunks if chunk)
            
            if not clean_text:
                clean_text = f"URL: {url}"
                
            return title, clean_text[:10000] # Cap text content to prevent LLM token issues
    except Exception as e:
        logger.error("Failed to scrape URL %s: %s", url, e)
        return url, url

async def ingest_url(url: str, user_id: int, db: AsyncConnection) -> int:
    """
    Scrapes, encrypts, embeds, and saves URL content.
    Returns the inserted item's ID.
    """
    # 1. Scrape content
    title, text_content = await scrape_url(url)
    
    raw_text = f"URL: {url}\nTitle: {title}\nContent:\n{text_content}"
    
    # 2. Generate summary & tags
    cascade = AICascade()
    summary = f"Summary snippet of {title}: {text_content[:200]}..."
    tags = ["url"]
    try:
        ai_res = await cascade.summarise(raw_text)
        summary = ai_res.get("summary") or summary
        tags = ai_res.get("tags") or tags
    except Exception as e:
        logger.error("Failed to generate AI summary/tags for URL %s: %s", url, e)
        
    normalized_tags = [t.strip().lower() for t in tags if isinstance(t, str) and t.strip()][:5]
    
    # 3. Generate embedding
    embedding = await embed_text(raw_text)
    
    # 4. Encrypt raw text
    encrypted_raw_text = encrypt(raw_text)
    
    if hasattr(db, "connection"):
        db_ctx = db.connection()
    else:
        class DummyContext:
            async def __aenter__(self):
                return db
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        db_ctx = DummyContext()

    async with db_ctx as conn:
        if hasattr(db, "connection"):
            await conn.execute("SET statement_timeout = '30s'")
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO items (user_id, source_type, source_url, raw_text, summary, title, embedding, tags)
                VALUES (%s, 'url', %s, %s, %s, %s, %s::vector, %s)
                RETURNING id;
                """,
                (user_id, url, encrypted_raw_text, summary, title, embedding, normalized_tags)
            )
            row = await cur.fetchone()
            if not row:
                raise RuntimeError("Failed to insert URL item")
            item_id = row[0]
            await conn.commit()
        
    logger.info("Successfully ingested URL item_id=%d for user_id=%d", item_id, user_id)
    return item_id
