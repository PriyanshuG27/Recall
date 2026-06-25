"""
backend/worker.py
=================
Task worker loop for Recall.
Pulls tasks from Upstash Redis, resolves user context, executes the ingestion pipelines
inside a concurrency semaphore, and performs DLQ error handling.
"""

import os
import re
import json
import uuid
import time
import logging
import asyncio
import httpx
import hashlib
from typing import Optional, Dict, Any

from backend.config import settings
from backend.exceptions import DuplicateItemException
from backend.db.connection import _pool
from backend.services.user_service import upsert_user
from backend.services.redis_client import redis
from backend.services.dlq import write_to_dlq, send_failure_message
from backend.services.encryption import encrypt, decrypt
from backend.services.search_service import embed_text
from backend.services.ai_cascade import AICascade

# Ingesters
from backend.services.pdf_ingester import ingest_pdf
from backend.services.url_ingester import ingest_url
from backend.services.voice_ingester import ingest_voice
from backend.services.image_ingester import ingest_image

logger = logging.getLogger(__name__)

# Concurrency semaphore (initialized lazily inside the event loop)
worker_semaphore = None

def clean_latex_for_telegram(text: str) -> str:
    """
    Cleans up LaTeX mathematical formulas in text to make them readable in Telegram chat (HTML mode),
    by replacing block/inline LaTeX markers with clean unicode symbols and enclosing them in <code> tags.
    """
    def clean_formula(formula: str) -> str:
        # Remove \text{...} -> ...
        formula = re.sub(r'\\text\{([^}]+)\}', r'\1', formula)
        # Remove \mathrm{...} -> ...
        formula = re.sub(r'\\mathrm\{([^}]+)\}', r'\1', formula)
        # Convert \frac{A}{B} -> (A) / (B)
        formula = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', r'(\1) / (\2)', formula)
        # Convert \sqrt{A} -> √(A)
        formula = re.sub(r'\\sqrt\{([^}]+)\}', r'√(\1)', formula)
        # Remove \left and \right formatting
        formula = formula.replace(r'\left', '').replace(r'\right', '')
        # Replace LaTeX greek/math symbols
        replacements = {
            r'\alpha': 'α',
            r'\beta': 'β',
            r'\gamma': 'γ',
            r'\delta': 'δ',
            r'\epsilon': 'ε',
            r'\theta': 'θ',
            r'\lambda': 'λ',
            r'\mu': 'μ',
            r'\pi': 'π',
            r'\sigma': 'σ',
            r'\omega': 'ω',
            r'\sin': 'sin',
            r'\cos': 'cos',
            r'\tan': 'tan',
            r'\softmax': 'softmax',
            r'\cdot': '·',
            r'\times': '×',
            r'\infty': '∞',
            r'\approx': '≈',
            r'\neq': '≠',
            r'\le': '≤',
            r'\ge': '≥',
            # Superscripts
            '^T': 'ᵀ',
            '^2': '²',
            '^3': '³',
            # Subscripts
            '_k': 'ₖ',
            '_i': 'ᵢ',
            '_j': 'ⱼ',
            '_n': 'ₙ',
            '_{model}': '_model',
            '_{k}': 'ₖ',
            '_{i}': 'ᵢ',
            '_{j}': 'ⱼ',
            '_{n}': 'ₙ',
        }
        for k, v in replacements.items():
            formula = formula.replace(k, v)
            
        # Clean up double parentheses if they exist, e.g. ((A)) -> (A)
        formula = re.sub(r'\(\(([^)]+)\)\)', r'(\1)', formula)
        # Remove remaining backslashes before basic letters
        formula = re.sub(r'\\([a-zA-Z])', r'\1', formula)
        
        return formula.strip()

    # Convert block formulas: \[ ... \] or $$ ... $$
    block_patterns = [r'\\\[(.*?)\\\]', r'\$\$(.*?)\$\$']
    for pattern in block_patterns:
        matches = re.findall(pattern, text, flags=re.DOTALL)
        for m in matches:
            cleaned = clean_formula(m)
            if pattern.startswith(r'\\\['):
                raw_match = f"\\[{m}\\]"
            else:
                raw_match = f"$${m}$$"
            text = text.replace(raw_match, f"<code>{cleaned}</code>")

    # Convert inline formulas: \( ... \) or $ ... $
    inline_patterns = [r'\\\((.*?)\\\)', r'\$([^$\n]+)\$']
    for pattern in inline_patterns:
        matches = re.findall(pattern, text)
        for m in matches:
            if not m.strip():
                continue
            if pattern == r'\$([^$\n]+)\$':
                if ' ' in m and not any(c in m for c in ['=', '+', '-', '\\', '_', '^', '*', '/', '&lt;', '&gt;']):
                    continue
                if m.isdigit() or len(m) <= 1:
                    continue
            cleaned = clean_formula(m)
            if pattern.startswith(r'\\\('):
                raw_match = f"\\({m}\\)"
            else:
                raw_match = f"${m}$"
            text = text.replace(raw_match, f"<code>{cleaned}</code>")

    return text

async def send_telegram_message(chat_id: str, text: str) -> None:
    """Helper to send a message back to the Telegram chat."""
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    
    # 1. Escape HTML special characters
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    # 2. Clean LaTeX math equations for Telegram HTML display
    escaped = clean_latex_for_telegram(escaped)
    
    # 2. Convert Markdown **bold** to HTML <b>bold</b>
    parts = escaped.split("**")
    bolded_parts = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            bolded_parts.append(f"<b>{part}</b>")
        else:
            bolded_parts.append(part)
    formatted = "".join(bolded_parts)
    
    # 3. Process line-by-line for headers, lists, italics, and footer beautification
    lines = formatted.split("\n")
    if lines:
        # Beautify title line if it starts with an emoji
        first_line = lines[0]
        emojis = ("🎥 ", "📸 ", "📄 ", "🎙 ", "🖼 ")
        for emoji in emojis:
            if first_line.startswith(emoji):
                title_content = first_line[len(emoji):]
                lines[0] = f"{emoji}<b>{title_content}</b>"
                break
                
        for idx in range(len(lines)):
            line = lines[idx]
            
            # Convert Markdown headers to Bold in Telegram HTML
            if line.startswith("### "):
                line = f"<b>{line[4:]}</b>"
            elif line.startswith("## "):
                line = f"<b>{line[3:]}</b>"
            elif line.startswith("# "):
                line = f"<b>{line[2:]}</b>"
                
            # Convert Markdown italics (*text* or _text_) to <i>text</i>
            line = re.sub(r'\*(.*?)\*', r'<i>\1</i>', line)
            line = re.sub(r'_(.*?)_', r'<i>\1</i>', line)
            
            # Beautify footer/acknowledgements
            if line == "Saved ✓":
                line = "<b>Saved ✓</b>"
            elif line.endswith(" | Saved ✓"):
                base = line[:-10]
                line = f"{base} | <b>Saved ✓</b>"
            elif line.startswith("Saved ✓ — "):
                title_content = line[10:]
                line = f"<b>Saved ✓</b> — {title_content}"
                
            lines[idx] = line
            
    final_text = "\n".join(lines)
    
    payload = {
        "chat_id": str(chat_id),
        "text": final_text,
        "parse_mode": "HTML"
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            logger.info("Sent Telegram message to chat_id %s", chat_id)
    except Exception as e:
        logger.error("Failed to send Telegram message to chat_id %s: %s", chat_id, e)


async def save_minimal_bookmark(user_id: int, source_type: str, file_id: Optional[str], text: Optional[str], db) -> int:
    """Saves a minimal fallback bookmark item in items table on ingestion failure."""
    raw_content = text or file_id or "Fallback content"
    encrypted_raw = encrypt(raw_content)
    summary = f"Could not process your {source_type}. Saved as a placeholder bookmark."
    title = f"Bookmark: {source_type.capitalize()} note"
    
    # Mock embedding
    val = 1.0 / (384 ** 0.5)
    mock_emb = [val] * 384
    
    tags = ["bookmark", source_type]
    
    async with db.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO items (user_id, source_type, raw_text, summary, title, embedding, tags)
            VALUES (%s, %s, %s, %s, %s, %s::vector, %s)
            RETURNING id;
            """,
            (user_id, source_type, encrypted_raw, summary, title, mock_emb, tags)
        )
        row = await cur.fetchone()
        if not row:
            raise RuntimeError("Failed to insert minimal bookmark")
        item_id = row[0]
        await db.commit()
    return item_id

async def process_task(task: Dict[str, Any]) -> None:
    """Processes a single task context inside the concurrency semaphore."""
    global worker_semaphore
    if worker_semaphore is None:
        worker_semaphore = asyncio.Semaphore(3)
        
    async with worker_semaphore:
        update_id = task.get("update_id")
        chat_id = str(task.get("chat_id"))
        content_type = task.get("content_type")
        file_id = task.get("file_id")
        text_content = task.get("text")
        
        logger.info("Processing task: update_id=%s, chat_id=%s, type=%s", update_id, chat_id, content_type)
        
        # Verify pool is open
        if _pool is None:
            logger.error("Database connection pool is not initialized.")
            return
            
        user_id = None
        
        try:
            # 1. Resolve user_id in a short, dedicated connection checkout
            async with _pool.connection() as conn:
                await conn.execute("SET statement_timeout = '30s'")
                user_id = await upsert_user(chat_id, conn)
                await conn.commit()

            # Route by content_type
            item_id = None
            
            if content_type == "text":
                if not text_content:
                    raise ValueError("Text content missing in task")
                
                # Deduplication check (short connection block)
                content_hash = hashlib.sha256(text_content.encode()).hexdigest()[:16]
                async with _pool.connection() as conn:
                    await conn.execute("SET statement_timeout = '30s'")
                    async with conn.cursor() as cur:
                        await cur.execute("SELECT id FROM items WHERE user_id=%s AND content_hash=%s LIMIT 1", (user_id, content_hash))
                        row = await cur.fetchone()
                        if row:
                            bot_reply = "This looks like something you've already saved."
                            await send_telegram_message(chat_id, bot_reply)
                            return
                
                cascade = AICascade()
                ai_res = await cascade.summarise(text_content, chat_id)
                summary = ai_res.get("summary") or f"Text note summary: {text_content[:100]}..."
                tags = ai_res.get("tags") or ["text"]
                
                normalized_tags = [t.strip().lower() for t in tags if isinstance(t, str) and t.strip()][:5]
                embedding = await embed_text(text_content)
                encrypted_raw_text = encrypt(text_content)
                title = text_content[:80].strip() or "Text Note"
                
                async with _pool.connection() as conn:
                    await conn.execute("SET statement_timeout = '30s'")
                    async with conn.cursor() as cur:
                        await cur.execute(
                            """
                            INSERT INTO items (user_id, source_type, raw_text, summary, title, embedding, tags, content_hash)
                            VALUES (%s, 'text', %s, %s, %s, %s::vector, %s, %s)
                            RETURNING id;
                            """,
                            (user_id, encrypted_raw_text, summary, title, embedding, normalized_tags, content_hash)
                        )
                        row = await cur.fetchone()
                        if not row:
                            raise RuntimeError("Failed to insert text item")
                        item_id = row[0]
                        await conn.commit()
                    
                bot_reply = f"Saved ✓ — [{title}]"
                await send_telegram_message(chat_id, bot_reply)
                
            elif content_type == "url":
                if not text_content:
                    raise ValueError("URL content missing in task")
                
                # Deduplication check (short connection block)
                async with _pool.connection() as conn:
                    await conn.execute("SET statement_timeout = '30s'")
                    async with conn.cursor() as cur:
                        await cur.execute("SELECT id, title FROM items WHERE user_id=%s AND source_url=%s LIMIT 1", (user_id, text_content))
                        row = await cur.fetchone()
                        if row:
                            bot_reply = f"Already saved! Item ID: {row[0]} — {row[1]}"
                            await send_telegram_message(chat_id, bot_reply)
                            return
                
                is_youtube = "youtube.com" in text_content.lower() or "youtu.be" in text_content.lower()
                is_instagram = "instagram.com" in text_content.lower() or "instagr.am" in text_content.lower()
                if is_youtube:
                    from backend.services.youtube_ingester import ingest_youtube
                    item_id = await ingest_youtube(text_content, user_id, _pool)
                elif is_instagram:
                    from backend.services.youtube_ingester import ingest_instagram
                    item_id = await ingest_instagram(text_content, user_id, _pool)
                else:
                    item_id = await ingest_url(text_content, user_id, _pool)
                
                # Fetch saved details for bot reply (short connection block)
                async with _pool.connection() as conn:
                    await conn.execute("SET statement_timeout = '30s'")
                    async with conn.cursor() as cur:
                        await cur.execute("SELECT title, summary FROM items WHERE id = %s AND user_id = %s;", (item_id, user_id))
                        row = await cur.fetchone()
                title = row[0] if row else "URL Link"
                summary = row[1] if row else ""
                
                if is_youtube:
                    if "Could not process" in summary:
                        bot_reply = f"Could not process this YouTube video. Saved as bookmark. We'll retry later."
                    else:
                        bot_reply = f"🎥 {title}\n\n{summary}\n\nSaved ✓"
                elif is_instagram:
                    if "Could not process" in summary:
                        bot_reply = f"Could not process this Instagram Reel. Saved as bookmark. We'll retry later."
                    else:
                        bot_reply = f"📸 {title}\n\n{summary}\n\nSaved ✓"
                else:
                    bot_reply = f"Saved ✓ — {title}"
                await send_telegram_message(chat_id, bot_reply)
                
            elif content_type == "pdf":
                if not file_id:
                    raise ValueError("PDF file_id missing in task")
                
                # Download PDF locally in workspace temp folder
                tmp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp")
                os.makedirs(tmp_dir, exist_ok=True)
                temp_path = os.path.join(tmp_dir, f"{uuid.uuid4()}.pdf")
                
                try:
                    from backend.services.telegram_downloader import download_telegram_file_robust
                    file_path = await download_telegram_file_robust(file_id, temp_path, max_size_bytes=20 * 1024 * 1024)
                    filename = file_path.split("/")[-1] if "/" in file_path else "document.pdf"
                    # Open fitz to count pages
                    import fitz
                    doc = fitz.open(temp_path)
                    page_count = len(doc)
                    doc.close()
                    
                    try:
                        item_id = await ingest_pdf(temp_path, user_id, filename, file_id, _pool)
                    except DuplicateItemException:
                        bot_reply = "This looks like something you've already saved."
                        await send_telegram_message(chat_id, bot_reply)
                        return
                    
                    # Fetch generated summary (short connection block)
                    async with _pool.connection() as conn:
                        await conn.execute("SET statement_timeout = '30s'")
                        async with conn.cursor() as cur:
                            await cur.execute("SELECT summary FROM items WHERE id = %s AND user_id = %s;", (item_id, user_id))
                            row = await cur.fetchone()
                    summary = row[0] if row else "No summary available."
                    
                    bot_reply = f"📄 {filename}\n\n{summary}\n\nPages: {page_count} | Saved ✓"
                    await send_telegram_message(chat_id, bot_reply)
                    
                finally:
                    if os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except Exception:
                            pass
                            
            elif content_type == "voice":
                if not file_id:
                    raise ValueError("Voice file_id missing in task")
                
                try:
                    item_id = await ingest_voice(file_id, user_id, chat_id, _pool)
                except DuplicateItemException:
                    bot_reply = "This looks like something you've already saved."
                    await send_telegram_message(chat_id, bot_reply)
                    return
                
                # Fetch saved details (short connection block)
                async with _pool.connection() as conn:
                    await conn.execute("SET statement_timeout = '30s'")
                    async with conn.cursor() as cur:
                        await cur.execute("SELECT raw_text, summary FROM items WHERE id = %s AND user_id = %s;", (item_id, user_id))
                        row = await cur.fetchone()
                if row:
                    decrypted_transcript = decrypt(row[0])
                    summary = row[1]
                else:
                    decrypted_transcript = "Transcription not retrieved."
                    summary = "Summary not retrieved."
                    
                bot_reply = f"🎙 Transcribed:\n{decrypted_transcript[:200]}...\n\n📝 Summary:\n{summary}\n\nSaved ✓"
                await send_telegram_message(chat_id, bot_reply)
                
            elif content_type in ("photo", "image"):
                if not file_id:
                    raise ValueError("Image file_id missing in task")
                    
                try:
                    item_id = await ingest_image(file_id, user_id, chat_id, _pool)
                except DuplicateItemException:
                    bot_reply = "This looks like something you've already saved."
                    await send_telegram_message(chat_id, bot_reply)
                    return
                
                # Fetch saved details (short connection block)
                async with _pool.connection() as conn:
                    await conn.execute("SET statement_timeout = '30s'")
                    async with conn.cursor() as cur:
                        await cur.execute("SELECT raw_text, summary FROM items WHERE id = %s AND user_id = %s;", (item_id, user_id))
                        row = await cur.fetchone()
                if row:
                    decrypted_raw = decrypt(row[0])
                    summary = row[1]
                else:
                    decrypted_raw = ""
                    summary = ""
                    
                if decrypted_raw.startswith("OCR Text:"):
                    ocr_content = decrypted_raw.replace("OCR Text:\n", "")
                    bot_reply = f"🖼 Extracted text:\n{ocr_content[:200]}...\n\nSaved ✓"
                else:
                    caption_content = decrypted_raw.replace("Image Caption:\n", "")
                    bot_reply = f"🖼 Caption: {caption_content}\n\nSaved ✓"
                    
                await send_telegram_message(chat_id, bot_reply)
                
            else:
                logger.warning("Worker received unsupported content type '%s' on update_id=%s. Discarding.", content_type, update_id)
                return
            
            # Invalidate graph cache
            try:
                await redis.delete(f"graph:{user_id}")
            except Exception as e:
                logger.error("Failed to delete graph cache: %s", e)
            logger.info("Successfully completed processing for update_id=%s, invalidated graph cache.", update_id)

        except Exception as exc:
            logger.exception("Task worker encountered exception processing update_id=%s:", update_id)
            error_message = str(exc)
            
            # Fallback flow using a fresh connection checkout
            if user_id:
                try:
                    task_payload = {
                        "chat_id": chat_id,
                        "content_type": content_type or "unknown",
                        "file_id": file_id,
                        "update_id": update_id or "unknown",
                        "attempted_tiers": [0],
                        "last_error": error_message
                    }
                    # Checkout a clean connection to guarantee write success even if primary timed out
                    async with _pool.connection() as fallback_conn:
                        await fallback_conn.execute("SET statement_timeout = '30s'")
                        await write_to_dlq(user_id, task_payload, error_message, fallback_conn)
                        await save_minimal_bookmark(user_id, content_type or "unknown", file_id, text_content, fallback_conn)
                        await fallback_conn.commit()
                        
                    await send_failure_message(chat_id, content_type or "unknown")
                except Exception as dlq_err:
                    logger.error("Failed to complete fallback DLQ/bookmark flow: %s", dlq_err)

async def start_worker_task() -> None:
    """Runs the worker continuous loop polling Upstash Redis."""
    redis_fail_start = None
    
    logger.info("Recall background worker thread started.")
    
    while True:
        try:
            # Poll Upstash Redis using BRPOP with 5s timeout
            # brpop returns (key, value) or None
            res = await redis.brpop("recall:tasks", timeout=5)
            
            # Reset Redis failure tracking if reachable
            if redis_fail_start is not None:
                logger.info("Re-established connection to Upstash Redis.")
                redis_fail_start = None
                
            if res:
                _, task_json = res
                try:
                    task = json.loads(task_json)
                    # Process asynchronously inside the semaphore
                    asyncio.create_task(process_task(task))
                except Exception as parse_err:
                    logger.error("Failed to parse task JSON: %s. Value: %s", parse_err, task_json)
                    
        except Exception as redis_err:
            if redis_fail_start is None:
                redis_fail_start = time.perf_counter()
                logger.warning("Upstash Redis became unreachable in worker loop: %s", redis_err)
            else:
                elapsed = time.perf_counter() - redis_fail_start
                if elapsed > 30.0:
                    logger.critical(
                        "CRITICAL: Upstash Redis has been unreachable for %.1f seconds in worker loop.",
                        elapsed
                    )
            
            # Brief sleep before retrying
            await asyncio.sleep(2.0)
