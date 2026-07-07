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
from backend.services.ai_cascade import AICascade, ai_cascade

import asyncio
import re

logger = logging.getLogger(__name__)

def _clean_google_doc_title(html: str) -> str:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    title = "Google Document"
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
        title = re.sub(r"\s*-\s*Google\s*(Docs|Sheets|Slides|Drive)$", "", title, flags=re.IGNORECASE)
    return title

def _write_temp_pdf_content(content: bytes) -> str:
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(content)
        return tmp.name

def _parse_url_html(html: str) -> tuple[str, str]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    title = "Untitled Link"
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    
    # Clean up scripts, styles, and other metadata
    for script_or_style in soup(["script", "style", "meta", "noscript", "header", "footer", "nav"]):
        script_or_style.decompose()
        
    text = soup.get_text(separator="\n")
    return title, text

async def scrape_url(url: str, user_id = None, db = None) -> tuple[str, str]:
    """
    Scrapes the given URL and returns (title, clean_text).
    Supports parsing Google Docs, Sheets, Slides, and general Google Drive files.
    If scraping fails, returns (URL, URL).
    """
    import re
    import os

    # Check if URL is Google Doc/Sheet/Slide or general Google Drive file
    doc_match = re.search(r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)", url)
    sheet_match = re.search(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    slide_match = re.search(r"docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)", url)
    drive_match = re.search(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)", url)

    google_file_id = None
    google_type = None

    if doc_match:
        google_file_id = doc_match.group(1)
        google_type = "document"
    elif sheet_match:
        google_file_id = sheet_match.group(1)
        google_type = "spreadsheet"
    elif slide_match:
        google_file_id = slide_match.group(1)
        google_type = "presentation"
    elif drive_match:
        google_file_id = drive_match.group(1)
        google_type = "file"

    if google_file_id:
        # Try authenticated route if we have user credentials
        access_token = None
        if user_id and db:
            try:
                # Fetch refresh token from users
                if hasattr(db, "cursor"):
                    async with db.cursor() as cur:
                        await cur.execute("SELECT google_refresh_token FROM users WHERE id = %s;", (user_id,))
                        row = await cur.fetchone()
                        encrypted_token = row[0] if row else None
                else:
                    async with db.connection() as conn:
                        async with conn.cursor() as cur:
                            await cur.execute("SELECT google_refresh_token FROM users WHERE id = %s;", (user_id,))
                            row = await cur.fetchone()
                            encrypted_token = row[0] if row else None

                if encrypted_token:
                    from backend.services.encryption import decrypt
                    refresh_token = decrypt(encrypted_token)

                    # Exchange refresh token for access token
                    from backend.config import settings
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        token_resp = await client.post(
                            "https://oauth2.googleapis.com/token",
                            data={
                                "client_id": settings.GOOGLE_CLIENT_ID,
                                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                                "refresh_token": refresh_token,
                                "grant_type": "refresh_token",
                            }
                        )
                        token_resp.raise_for_status()
                        access_token = token_resp.json().get("access_token")
            except Exception as token_err:
                logger.error("Failed to get Google access token for scraping: %s", token_err)

        content_text = None
        title = "Untitled Google File"

        if access_token:
            headers = {"Authorization": f"Bearer {access_token}"}
            async with httpx.AsyncClient(timeout=15.0) as client:
                try:
                    # Get file metadata to find title and mimeType
                    meta_resp = await client.get(
                        f"https://www.googleapis.com/drive/v3/files/{google_file_id}",
                        headers=headers
                    )
                    meta_resp.raise_for_status()
                    meta_data = meta_resp.json()
                    title = meta_data.get("name", title)
                    mime_type = meta_data.get("mimeType", "")

                    # Determine how to fetch content
                    if mime_type == "application/vnd.google-apps.document" or google_type == "document":
                        # Export Doc as plain text
                        export_resp = await client.get(
                            f"https://www.googleapis.com/drive/v3/files/{google_file_id}/export?mimeType=text/plain",
                            headers=headers
                        )
                        export_resp.raise_for_status()
                        content_text = export_resp.text
                    elif mime_type == "application/vnd.google-apps.spreadsheet" or google_type == "spreadsheet":
                        # Export Sheet as CSV
                        export_resp = await client.get(
                            f"https://www.googleapis.com/drive/v3/files/{google_file_id}/export?mimeType=text/csv",
                            headers=headers
                        )
                        export_resp.raise_for_status()
                        content_text = export_resp.text
                    elif mime_type == "application/vnd.google-apps.presentation" or google_type == "presentation":
                        # Export Slide as plain text
                        export_resp = await client.get(
                            f"https://www.googleapis.com/drive/v3/files/{google_file_id}/export?mimeType=text/plain",
                            headers=headers
                        )
                        export_resp.raise_for_status()
                        content_text = export_resp.text
                    else:
                        # Fetch binary file or text file
                        file_resp = await client.get(
                            f"https://www.googleapis.com/drive/v3/files/{google_file_id}?alt=media",
                            headers=headers
                        )
                        file_resp.raise_for_status()
                        # If PDF, parse PDF content
                        if mime_type == "application/pdf" or file_resp.content.startswith(b"%PDF"):
                            import tempfile
                            from backend.services.pdf_ingester import extract_pdf_text
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                                tmp.write(file_resp.content)
                                tmp_path = tmp.name
                            try:
                                content_text = await extract_pdf_text(tmp_path)
                            finally:
                                if os.path.exists(tmp_path):
                                    os.remove(tmp_path)
                        else:
                            content_text = file_resp.text
                except Exception as api_err:
                    logger.error("Failed to fetch Google file via API: %s", api_err)

        # Fallback to public endpoints if we couldn't get content authenticated
        if not content_text:
            from backend.services.http_client import get_http_client
            client = get_http_client()
            if True:
                try:
                    # Get title from normal URL scrape first
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                    }
                    resp = await client.get(url, headers=headers, timeout=15.0, follow_redirects=True)
                    if resp.status_code == 200:
                        loop = asyncio.get_running_loop()
                        title = await loop.run_in_executor(None, _clean_google_doc_title, resp.text)
                except Exception as title_err:
                    logger.error("Failed to get public Google file title: %s", title_err)

                # Now fetch the public export/download content
                try:
                    if google_type == "document":
                        export_url = f"https://docs.google.com/document/d/{google_file_id}/export?format=txt"
                        exp_resp = await client.get(export_url, timeout=15.0)
                        if exp_resp.status_code == 200:
                            content_text = exp_resp.text
                    elif google_type == "spreadsheet":
                        export_url = f"https://docs.google.com/spreadsheets/d/{google_file_id}/export?format=csv"
                        exp_resp = await client.get(export_url, timeout=15.0)
                        if exp_resp.status_code == 200:
                            content_text = exp_resp.text
                    elif google_type == "presentation":
                        export_url = f"https://docs.google.com/presentation/d/{google_file_id}/export?format=txt"
                        exp_resp = await client.get(export_url, timeout=15.0)
                        if exp_resp.status_code == 200:
                            content_text = exp_resp.text
                    elif google_type == "file":
                        dl_url = f"https://drive.google.com/uc?id={google_file_id}&export=download"
                        exp_resp = await client.get(dl_url, timeout=15.0)
                        if exp_resp.status_code == 200:
                            if exp_resp.content.startswith(b"%PDF"):
                                from backend.services.pdf_ingester import extract_pdf_text
                                loop = asyncio.get_running_loop()
                                tmp_path = await loop.run_in_executor(None, _write_temp_pdf_content, exp_resp.content)
                                try:
                                    content_text = await extract_pdf_text(tmp_path)
                                finally:
                                    if os.path.exists(tmp_path):
                                        os.remove(tmp_path)
                            else:
                                content_text = exp_resp.text
                except Exception as exp_err:
                    logger.error("Failed to fetch public Google file export: %s", exp_err)

        if content_text is not None:
            # Strip BOM if present
            if content_text.startswith("\ufeff"):
                content_text = content_text[1:]
            return title, content_text[:10000]

    # Standard URL scraping logic (non-Google Docs/Drive)
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        from backend.services.http_client import get_http_client
        client = get_http_client()
        if True:
            resp = await client.get(url, headers=headers, timeout=10.0, follow_redirects=True)
            
            # Check for private Google Drive redirect to login screen
            if "drive.google.com" in url.lower():
                if "accounts.google.com" in str(resp.url) or "ServiceLogin" in resp.text:
                    raise ValueError("private Google Drive link")

            if resp.status_code != 200:
                logger.warning("Scraping URL %s returned status %d", url, resp.status_code)
                return url, url
            
            html = resp.text
            loop = asyncio.get_running_loop()
            title, text = await loop.run_in_executor(None, _parse_url_html, html)
            
            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = "\n".join(chunk for chunk in chunks if chunk)
            
            if not clean_text:
                clean_text = f"URL: {url}"
                
            return title, clean_text[:10000] # Cap text content to prevent LLM token issues
    except Exception as e:
        if isinstance(e, ValueError) and str(e) == "private Google Drive link":
            raise
        logger.error("Failed to scrape URL %s: %s", url, e)
        return url, url

async def ingest_url(url: str, user_id: int, db: AsyncConnection, user_context: str | None = None) -> int:
    """
    Scrapes, encrypts, embeds, and saves URL content.
    Returns the inserted item's ID.
    """
    # 1. Scrape content (passing user_id and db to support google drive/docs access)
    title, text_content = await scrape_url(url, user_id, db)
    
    raw_text = f"URL: {url}\nTitle: {title}\nContent:\n{text_content}"
    
    # 2. Generate summary & tags
    cascade = AICascade()
    summary = f"Summary snippet of {title}: {text_content[:200]}..."
    tags = ["url"]
    context_prompt = None
    try:
        summarizer_input = raw_text
        if user_context:
            summarizer_input = f"[User's Note/Context: {user_context}]\n" + raw_text
        ai_res = await cascade.summarise(summarizer_input, user_id=user_id)
        summary = ai_res.get("summary") or summary
        tags = ai_res.get("tags") or tags
        context_prompt = ai_res.get("context_prompt")
    except Exception as e:
        logger.error("Failed to generate AI summary/tags for URL %s: %s", url, e)
        
    normalized_tags = [t.strip().lower() for t in tags if isinstance(t, str) and t.strip()][:5]
    
    # 3. Generate embedding
    is_fallback = (text_content == url)
    if is_fallback:
        embedding = await embed_text(f"{title}\n{summary}")
    else:
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
                INSERT INTO items (user_id, source_type, source_url, raw_text, summary, title, embedding, tags, context_prompt)
                VALUES (%s, 'url', %s, %s, %s, %s, %s::vector, %s, %s)
                RETURNING id;
                """,
                (user_id, url, encrypted_raw_text, summary, title, embedding, normalized_tags, context_prompt)
            )
            row = await cur.fetchone()
            if not row:
                raise RuntimeError("Failed to insert URL item")
            item_id = row[0]
            await conn.commit()
        
    logger.info("Successfully ingested URL item_id=%d for user_id=%d", item_id, user_id)
    return item_id
