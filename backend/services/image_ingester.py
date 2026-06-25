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
import pytesseract
from psycopg import AsyncConnection

from backend.config import settings
from backend.services.encryption import encrypt
from backend.services.search_service import embed_text
from backend.services.ai_cascade import AICascade

logger = logging.getLogger(__name__)

async def download_telegram_image(file_id: str, local_path: str) -> None:
    """Downloads an image from Telegram API and saves it locally."""
    from backend.services.telegram_downloader import download_telegram_file_robust
    await download_telegram_file_robust(file_id, local_path, max_size_bytes=10 * 1024 * 1024)

async def ingest_image(file_id: str, user_id: int, chat_id: str, db: AsyncConnection) -> int:
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
            
        # 2. OCR using Tesseract (lang='eng' by default)
        ocr_text = ""
        try:
            # Check standard Windows path first to avoid PATH issues in background workers
            std_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            if os.path.exists(std_path):
                pytesseract.pytesseract.tesseract_cmd = std_path
                
            # Open PIL image
            img = Image.open(temp_path)
            ocr_text = pytesseract.image_to_string(img, lang="eng").strip()
            logger.info("Tesseract OCR completed. Extracted length: %d chars", len(ocr_text))
        except Exception as ocr_err:
            # If Tesseract is not installed or raises an error, log it and treat as empty OCR
            logger.warning("Tesseract OCR failed (Tesseract may not be installed on system): %s. Falling back to captioning.", ocr_err)
            ocr_text = ""

        cascade = AICascade()
        
        # Determine if we use OCR or Gemini captioning
        if len(ocr_text) > 50:
            logger.info("Using OCR text for image ingestion (length > 50)")
            raw_text = f"OCR Text:\n{ocr_text}"
            
            # Summarise OCR text
            ai_res = await cascade.summarise(ocr_text, chat_id)
            summary = ai_res.get("summary") or f"OCR summary: {ocr_text[:100]}..."
            tags = ai_res.get("tags") or ["image", "ocr"]
            title = f"OCR: {ocr_text[:80].strip()}"
        else:
            logger.info("OCR text <= 50 chars. Requesting Gemini caption...")
            caption = await cascade.caption_image(image_bytes)
            if not caption:
                raise ValueError("Gemini captioning failed — caption was empty or failed.")
                
            raw_text = f"Image Caption:\n{caption}"
            summary = caption
            tags = ["image", "caption"]
            title = f"Image: {caption[:80].strip()}"

        normalized_tags = [t.strip().lower() for t in tags if isinstance(t, str) and t.strip()][:5]
        
        # 3. Embed
        embedding = await embed_text(raw_text)
        
        # 4. Encrypt
        encrypted_raw_text = encrypt(raw_text)
        
        # 5. Insert
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
                    INSERT INTO items (user_id, source_type, source_url, raw_text, summary, title, embedding, tags, content_hash)
                    VALUES (%s, 'image', %s, %s, %s, %s, %s::vector, %s, %s)
                    RETURNING id;
                    """,
                    (user_id, file_id, encrypted_raw_text, summary, title, embedding, normalized_tags, content_hash)
                )
                row = await cur.fetchone()
                if not row:
                    raise RuntimeError("Failed to insert image item")
                item_id = row[0]
                await conn.commit()
            
        logger.info("Successfully ingested image item_id=%d for user_id=%d", item_id, user_id)
        return item_id
        
    finally:
        # Clean up temp file
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                logger.info("Deleted temporary image file %s", temp_path)
            except Exception as e:
                logger.warning("Failed to delete temp image file %s: %s", temp_path, e)
