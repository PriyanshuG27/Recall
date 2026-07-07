"""
backend/services/voice_ingester.py
==================================
Service layer for voice note ingestion in Recall.
"""

import os
import uuid
import logging
import httpx
import hashlib
from psycopg import AsyncConnection

from backend.config import settings
from backend.exceptions import DuplicateItemException
from backend.services.encryption import encrypt
from backend.services.search_service import embed_text
from backend.services.ai_cascade import AICascade, ai_cascade

logger = logging.getLogger(__name__)

async def download_telegram_file(file_id: str, tmp_dir: str, file_uuid: str) -> str:
    """Downloads a file from Telegram API, determines extension, saves it, and returns the path."""
    from backend.services.telegram_downloader import get_telegram_file_info, download_telegram_file_robust
    
    file_path, file_size = await get_telegram_file_info(file_id)
    if file_size > 25 * 1024 * 1024:
        raise ValueError("Audio file size exceeds 25 MB limit.")
        
    ext = "ogg"
    if file_path and "." in file_path:
        ext = file_path.split(".")[-1].lower()
        
    local_path = os.path.join(tmp_dir, f"{file_uuid}.{ext}")
    await download_telegram_file_robust(file_id, local_path, max_size_bytes=25 * 1024 * 1024)
    return local_path

async def ingest_voice(file_id: str, user_id: int, chat_id: str, db: AsyncConnection, user_context: str | None = None) -> int:
    """
    Ingests a Telegram voice note / audio file.
    Downloads, transcribes, summarises, embeds, encrypts, and saves it.
    """
    # Create temp directory in workspace
    tmp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    
    file_uuid = str(uuid.uuid4())
    temp_path = None
    
    try:
        # 1. Download
        temp_path = await download_telegram_file(file_id, tmp_dir, file_uuid)
        
        # Extract extension
        ext = "ogg"
        if temp_path and "." in temp_path:
            ext = temp_path.split(".")[-1].lower()
            
        # Read bytes
        with open(temp_path, "rb") as f:
            audio_bytes = f.read()
            
        content_hash = hashlib.sha256(audio_bytes).hexdigest()[:16]
            
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
            
        # 2. Transcribe
        cascade = AICascade()
        transcript = await cascade.transcribe(audio_bytes, chat_id, file_extension=ext)
        if not transcript:
            raise ValueError("Transcription failed — transcript was empty or failed on all tiers.")
            
        # 3. Summarise & tags
        summarizer_input = transcript
        if user_context:
            summarizer_input = f"[User's Note/Context: {user_context}]\n" + transcript
        ai_res = await cascade.summarise(summarizer_input, chat_id=chat_id, user_id=user_id)
        summary = ai_res.get("summary") or f"Transcription summary for voice note: {transcript[:100]}..."
        tags = ai_res.get("tags") or ["voice"]
        context_prompt = ai_res.get("context_prompt")
        
        normalized_tags = [t.strip().lower() for t in tags if isinstance(t, str) and t.strip()][:5]
        
        # 4. Embed
        embedding = await embed_text(transcript)
        
        # 5. Encrypt
        encrypted_raw_text = encrypt(transcript)
        
        # Title: first 80 characters of transcript
        title = transcript[:80].strip() or "Voice Note"
        
        # 6. Insert
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
                    VALUES (%s, 'voice', %s, %s, %s, %s, %s::vector, %s, %s, %s)
                    RETURNING id;
                    """,
                    (user_id, file_id, encrypted_raw_text, summary, title, embedding, normalized_tags, content_hash, context_prompt)
                )
                row = await cur.fetchone()
                if not row:
                    raise RuntimeError("Failed to insert voice note item")
                item_id = row[0]
                await conn.commit()
            
        logger.info("Successfully ingested voice note item_id=%d for user_id=%d", item_id, user_id)
        return item_id
        
    finally:
        # Ensure temp file is always deleted
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                logger.info("Deleted temporary voice note file %s", temp_path)
            except Exception as e:
                logger.warning("Failed to delete temp file %s: %s", temp_path, e)
