import fitz # PyMuPDF
import re
import io
import os
import logging
import pytesseract
from PIL import Image
from typing import List, Optional, Any
from psycopg import AsyncConnection

from backend.services.encryption import encrypt
from backend.services.search_service import embed_text

logger = logging.getLogger(__name__)

def check_tesseract_available() -> bool:
    """Check if local Tesseract OCR binary is installed and configured."""
    # Check standard Windows path first to avoid PATH issues in background workers
    std_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(std_path):
        pytesseract.pytesseract.tesseract_cmd = std_path
        return True
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False

async def extract_pdf_text(pdf_path: str, cascade: Optional[Any] = None) -> str:
    """
    Extract plain text from a PDF file using PyMuPDF (fitz).
    Enforces layout sorting (sort=True) for multi-column documents.
    If a page is scanned/image-only, falls back to local Tesseract OCR or budgeted Gemini Vision.
    """
    doc = fitz.open(pdf_path)
    text_parts = []
    page_count = len(doc)
    
    tesseract_ok = check_tesseract_available()
    if not tesseract_ok:
        logger.warning("Local Tesseract binary not found. Scanned pages will fall back to Gemini Vision.")
        
    for page_idx, page in enumerate(doc):
        # Extract text in reading order (sort=True)
        page_text = page.get_text("text", sort=True)
        
        # Detect if the page is scanned/visual (contains very little digital text)
        if len(page_text.strip()) < 50:
            logger.info("Scanned or visual page detected at page %d/%d", page_idx + 1, page_count)
            try:
                # Render page to high-quality image (150 DPI)
                pix = page.get_pixmap(dpi=150)
                image_bytes = pix.tobytes("png")
                
                if tesseract_ok:
                    # Run local OCR (free, local, no rate limit)
                    img = Image.open(io.BytesIO(image_bytes))
                    # Run OCR in executor to avoid blocking the main event loop
                    import asyncio
                    loop = asyncio.get_running_loop()
                    ocr_text = await loop.run_in_executor(
                        None, 
                        lambda: pytesseract.image_to_string(img)
                    )
                    page_text = ocr_text.strip() or f"[Scanned Page {page_idx + 1} (No text recognized)]"
                else:
                    # Fallback to Gemini Vision with budget (first 5 and last 3 pages)
                    is_within_budget = (page_idx < 5) or (page_idx >= page_count - 3)
                    if is_within_budget and cascade is not None:
                        caption = await cascade.caption_image(image_bytes)
                        if caption:
                            page_text = f"[Scanned Page {page_idx + 1} Visual Content: {caption}]"
                        else:
                            page_text = f"[Scanned Page {page_idx + 1} (Visual extraction failed)]"
                    else:
                        page_text = f"[Scanned Page {page_idx + 1}: skipped to respect API rate limits/budgets]"
            except Exception as e:
                logger.error("Failed to perform OCR/Visual fallback on page %d: %s", page_idx + 1, e)
                page_text = f"[Scanned Page {page_idx + 1} (Extraction error)]"
                
        text_parts.append(page_text)
        
    doc.close()
    return "\n".join(text_parts)

def chunk_text(text: str, chunk_size_words: int = 300) -> List[str]:
    """
    Split text into sentence-bounded chunks of roughly chunk_size_words (~400 tokens).
    """
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    chunks = []
    current_chunk = []
    current_word_count = 0
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        words = sentence.split()
        sentence_word_count = len(words)
        
        if current_word_count + sentence_word_count > chunk_size_words and current_chunk:
            chunks.append(" ".join(current_chunk))
            current_chunk = []
            current_word_count = 0
            
        current_chunk.append(sentence)
        current_word_count += sentence_word_count
        
    if current_chunk:
        chunks.append(" ".join(current_chunk))
        
    return chunks

def get_summarization_context(full_text: str, max_chars: int = 60000) -> str:
    """
    Produce a context-aware segment of the document for summarization.
    If full_text is within max_chars, returns the entire text.
    Otherwise, applies head-tail sampling (first 40k + last 20k) to preserve abstract and conclusion.
    """
    if len(full_text) <= max_chars:
        return full_text
        
    head_size = 40000
    tail_size = 20000
    
    # Adjust in case max_chars is different than 60000
    if max_chars != 60000:
        head_size = int(max_chars * 0.67)
        tail_size = max_chars - head_size
        
    head = full_text[:head_size]
    tail = full_text[-tail_size:]
    
    return f"{head}\n\n[... TEXT TRUNCATED FOR CONTEXT LIMITS ...]\n\n{tail}"

async def ingest_pdf(
    pdf_path: str,
    user_id: int,
    title: str,
    source_url: Optional[str],
    db: AsyncConnection
) -> int:
    """
    Extract, chunk, embed, and store PDF contents.
    Creates an items row and associated item_chunks rows in a single transaction.
    """
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
        
    import hashlib
    content_hash = hashlib.sha256(pdf_bytes).hexdigest()[:16]
    
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

    # Initialize cascade for OCR fallback and summarization
    from backend.services.ai_cascade import AICascade
    cascade = AICascade()

    # 1. Extract full text from PDF (async OCR)
    full_text = await extract_pdf_text(pdf_path, cascade)
    
    # 2. Chunk text into segments of roughly 300 words
    chunks = chunk_text(full_text, chunk_size_words=300)
    if not chunks:
        chunks = ["(Empty PDF)"]
        
    # 3. Generate embeddings for all chunks
    chunk_embeddings = []
    for chunk in chunks:
        emb = await embed_text(chunk)
        chunk_embeddings.append(emb)
        
    # Use chunk 0 embedding for items.embedding
    first_chunk_embedding = chunk_embeddings[0]
    
    # Encrypt the full raw text for storage
    encrypted_raw_text = encrypt(full_text)
    
    # Generate summary & tags using the AI cascade
    tags = []
    try:
        # Get head-tail sampled context for document-level summary (up to 60,000 characters)
        summary_context = get_summarization_context(full_text, max_chars=60000)
        ai_res = await cascade.summarise(summary_context)
        summary = ai_res.get("summary")
        tags = ai_res.get("tags") or []
    except Exception as e:
        logger.error("Failed to generate AI summary/tags for PDF %s: %s", title, e)
        summary = f"Summary of PDF: {title}. Contains {len(chunks)} sections."
        if len(chunks) > 0:
            summary += f" First excerpt: {chunks[0][:150]}..."

    # Normalize tags: lowercase, strip, keep max 5
    normalized_tags = [t.strip().lower() for t in tags if isinstance(t, str) and t.strip()][:5]

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
            # INSERT parent item
            insert_item_query = """
                INSERT INTO items (user_id, title, source_type, source_url, raw_text, summary, embedding, tags, content_hash)
                VALUES (%s, %s, %s, %s, %s, %s, %s::vector, %s, %s)
                RETURNING id;
            """
            await cur.execute(
                insert_item_query,
                (user_id, title, "pdf", source_url, encrypted_raw_text, summary, first_chunk_embedding, normalized_tags, content_hash)
            )
            row = await cur.fetchone()
            if not row:
                raise RuntimeError("Failed to insert parent PDF item")
            item_id = row[0]
            
            # INSERT item_chunks
            insert_chunk_query = """
                INSERT INTO item_chunks (item_id, user_id, chunk_index, chunk_text, embedding)
                VALUES (%s, %s, %s, %s, %s::vector);
            """
            for idx, (chunk, emb) in enumerate(zip(chunks, chunk_embeddings)):
                chunk_excerpt = chunk[:2000]
                await cur.execute(
                    insert_chunk_query,
                    (item_id, user_id, idx, chunk_excerpt, emb)
                )
                
            await conn.commit()

    # Invalidate graph cache
    from backend.services.redis_client import redis
    try:
        await redis.delete(f"graph:{user_id}")
        logger.info("Invalidated graph cache for user %d on PDF ingestion", user_id)
    except Exception as e:
        logger.error("Failed to invalidate graph cache for user %d: %s", user_id, e)
        
    logger.info("Successfully ingested PDF: item_id=%d, chunks=%d for user_id=%d", item_id, len(chunks), user_id)
    return item_id

