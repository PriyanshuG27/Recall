"""
backend/services/image_ingester.py
==================================
Service layer for image ingestion (OCR & captioning) in Recall.
"""

import os
import uuid
import logging
import httpx
from PIL import Image
from psycopg import AsyncConnection

from backend.config import settings
from backend.services.encryption import encrypt
from backend.services.search_service import embed_text
from backend.services.ai_cascade import AICascade, ai_cascade

logger = logging.getLogger(__name__)

def extract_urls_from_ocr(ocr_text: str) -> list[str]:
    import re
    url_start_re = re.compile(r'^(https?://|www\.)', re.IGNORECASE)
    url_char_re = re.compile(r'^[a-zA-Z0-9_.\-~%!$&\'()*+,;=:@/?#]+$')

    lines = [line.strip() for line in ocr_text.split("\n") if line.strip()]
    reconstructed_urls = []
    
    current_url = ""
    for line in lines:
        if url_start_re.match(line):
            if current_url:
                reconstructed_urls.append(current_url)
            current_url = line
        elif current_url:
            if " " not in line and url_char_re.match(line):
                current_url += line
            else:
                reconstructed_urls.append(current_url)
                current_url = ""
                
    if current_url:
        reconstructed_urls.append(current_url)
        
    final_urls = []
    for u in reconstructed_urls:
        u = re.sub(r'[.,;!]+$', '', u)
        if u.lower().startswith("www."):
            u = "http://" + u
        if u.lower().startswith("http://") or u.lower().startswith("https://"):
            final_urls.append(u)
            
    return final_urls

async def download_telegram_image(file_id: str, local_path: str) -> None:
    """Downloads an image from Telegram API and saves it locally."""
    from backend.services.telegram_downloader import download_telegram_file_robust
    await download_telegram_file_robust(file_id, local_path, max_size_bytes=10 * 1024 * 1024)

async def ingest_image(file_id: str, user_id: int, chat_id: str, db: AsyncConnection, user_context: str | None = None) -> int:
    """
    Ingests an image from Telegram.
    Downloads, performs OCR via Tesseract (or falls back to Gemini captioning),
    summarises, embeds, encrypts, and saves it.
    """
    # Create temp directory in workspace
    tmp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    
    temp_filename = f"{uuid.uuid4()}.jpg"
    temp_path = os.path.join(tmp_dir, temp_filename)
    
    try:
        # 1. Download
        await download_telegram_image(file_id, temp_path)
        
        # Read image bytes for Gemini fallback
        with open(temp_path, "rb") as f:
            image_bytes = f.read()
            
        import hashlib
        content_hash = hashlib.sha256(image_bytes).hexdigest()[:16]
        
        from backend.exceptions import DuplicateItemException
        if hasattr(db, "connection"):
            async with db.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT id FROM items WHERE user_id=%s AND content_hash=%s LIMIT 1", (user_id, content_hash))
                    row = await cur.fetchone()
                    if row:
                        raise DuplicateItemException(row[0])
        else:
            async with db.cursor() as cur:
                await cur.execute("SELECT id FROM items WHERE user_id=%s AND content_hash=%s LIMIT 1", (user_id, content_hash))
                row = await cur.fetchone()
                if row:
                    raise DuplicateItemException(row[0])
            
        # 2. OCR using PaddleOCR
        ocr_text = ""
        try:
            from backend.services.ocr_service import perform_ocr
            ocr_text = await perform_ocr(temp_path)
            logger.info("PaddleOCR completed. Extracted length: %d chars", len(ocr_text))
        except Exception as ocr_err:
            logger.warning("PaddleOCR failed: %s. Falling back to captioning.", ocr_err)
            ocr_text = ""
 
        cascade = AICascade()
        
        # Determine if we use OCR or Gemini captioning
        context_prompt = None
        extracted_urls = []
        is_only_links = False
        if len(ocr_text) > 50:
            logger.info("Using OCR text for image ingestion (length > 50)")
            raw_text = f"OCR Text:\n{ocr_text}"
            
            # Extract and clean URLs via AI cascade, falling back to regex if needed
            try:
                ai_meta = await cascade.extract_clean_urls_and_meta(ocr_text)
                extracted_urls = ai_meta.get("urls") or []
                is_only_links = bool(ai_meta.get("is_only_links", False))
            except Exception as ai_url_err:
                logger.warning("AI URL/meta cleanup failed: %s. Falling back to regex extraction.", ai_url_err)
                extracted_urls = []
                
            if not extracted_urls:
                extracted_urls = extract_urls_from_ocr(ocr_text)
                
            if extracted_urls:
                # Filter out redundant base domains (e.g. https://www.instagram.com) if more specific sub-links of the same domain are present
                specific_urls = [u for u in extracted_urls if len(u.rstrip("/").split("/")) > 3]
                if specific_urls:
                    def clean_proto(url):
                        return url.replace("https://", "").replace("http://", "").rstrip("/")
                    filtered_urls = []
                    for u in extracted_urls:
                        parts = u.rstrip("/").split("/")
                        if len(parts) <= 3:
                            u_clean = clean_proto(u)
                            if any(clean_proto(su).startswith(u_clean) for su in specific_urls):
                                logger.info("Discarding redundant base domain link: %s", u)
                                continue
                        filtered_urls.append(u)
                    extracted_urls = filtered_urls
                
            logger.info("Extracted URLs from OCR (final): %s, is_only_links: %s", extracted_urls, is_only_links)
            
            # Summarise OCR text
            summarizer_input = ocr_text
            if user_context:
                summarizer_input = f"[User's Note/Context: {user_context}]\n" + ocr_text
            ai_res = await cascade.summarise(summarizer_input, chat_id=chat_id, user_id=user_id)
            summary = ai_res.get("summary") or f"OCR summary: {ocr_text[:100]}..."
            tags = ai_res.get("tags") or ["image", "ocr"]
            context_prompt = ai_res.get("context_prompt")
            title = f"OCR: {ocr_text[:80].strip()}"
        else:
            logger.info("OCR text <= 50 chars. Requesting Gemini caption...")
            caption = await cascade.caption_image(image_bytes)
            if not caption:
                raise ValueError("Gemini captioning failed — caption was empty or failed.")
                
            raw_text = f"Image Caption:\n{caption}"
            if user_context:
                raw_text += f"\n[User's Note/Context: {user_context}]"
            
            if user_context:
                ai_res = await cascade.summarise(f"[User's Note/Context: {user_context}]\nImage Caption: {caption}", chat_id=chat_id, user_id=user_id)
                summary = ai_res.get("summary") or caption
                tags = ai_res.get("tags") or ["image", "caption"]
                context_prompt = ai_res.get("context_prompt")
            else:
                summary = caption
                tags = ["image", "caption"]
                context_prompt = None
            title = f"Image: {caption[:80].strip()}"
 
        normalized_tags = [t.strip().lower() for t in tags if isinstance(t, str) and t.strip()][:5]
        
        # Ingest extracted URLs first to see if they succeed
        url_item_ids = []
        if extracted_urls:
            from backend.services.url_ingester import ingest_url
            from backend.services.youtube_ingester import ingest_youtube, ingest_instagram
            for url in extracted_urls:
                try:
                    is_youtube = "youtube.com" in url.lower() or "youtu.be" in url.lower()
                    is_instagram = "instagram.com" in url.lower() or "instagr.am" in url.lower()
                    if is_youtube:
                        logger.info("Routing extracted YouTube URL to specialized ingester: %s", url)
                        url_item_id = await ingest_youtube(url, user_id, db, user_context=user_context)
                    elif is_instagram:
                        logger.info("Routing extracted Instagram URL to specialized ingester: %s", url)
                        url_item_id = await ingest_instagram(url, user_id, db, user_context=user_context)
                    else:
                        logger.info("Scraping and ingesting extracted URL: %s", url)
                        url_item_id = await ingest_url(url, user_id, db, user_context=user_context)
                        
                    if url_item_id:
                        url_item_ids.append(url_item_id)
                except Exception as url_err:
                    logger.error("Failed to ingest extracted URL %s: %s", url, url_err)

        # Insert main image item only if we have other text, OR if URL ingestion failed
        item_id = None
        if not is_only_links or not url_item_ids:
            # 3. Embed
            embedding = await embed_text(raw_text)
            
            # 4. Encrypt
            encrypted_raw_text = encrypt(raw_text)
            
            # 5. Insert image item
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
                        INSERT INTO items (user_id, source_type, source_url, raw_text, summary, title, embedding, tags, content_hash, context_prompt)
                        VALUES (%s, 'image', %s, %s, %s, %s, %s::vector, %s, %s, %s)
                        RETURNING id;
                        """,
                        (user_id, file_id, encrypted_raw_text, summary, title, embedding, normalized_tags, content_hash, context_prompt)
                    )
                    row = await cur.fetchone()
                    if not row:
                        raise RuntimeError("Failed to insert image item")
                    item_id = row[0]
                    await conn.commit()
                
            logger.info("Successfully ingested image item_id=%d for user_id=%d", item_id, user_id)

        # Return list of all ingested item IDs
        result_ids = []
        if item_id:
            result_ids.append(item_id)
        result_ids.extend(url_item_ids)
        return result_ids
        
    finally:
        # Clean up temp file
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                logger.info("Deleted temporary image file %s", temp_path)
            except Exception as e:
                logger.warning("Failed to delete temp image file %s: %s", temp_path, e)
