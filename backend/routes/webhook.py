import time
import logging
import asyncio
import httpx
import json
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, Request, BackgroundTasks
from pydantic import BaseModel

from backend.config import settings
from backend.db.connection import get_db
from backend.services.user_service import upsert_user
from backend.services.rate_limiter import check_rate_limit, RateLimitExceeded
import psycopg

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Content Type ACK Messages
# ---------------------------------------------------------------------------
ACK_MESSAGES = {
    "voice": "Processing your voice note...",
    "pdf": "Processing your PDF...",
    "url": "Processing your link...",
    "photo": "Processing your image...",
    "text": "Processing your text...",
    "unsupported": "Sorry, I can only process voice notes, PDFs, links, images, and text."
}


# check_rate_limit is imported from backend.services.rate_limiter


# ---------------------------------------------------------------------------
# Content Type Detection Helper
# ---------------------------------------------------------------------------
def detect_content_type(message: dict) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Detects the content type of a Telegram message and extracts necessary content.
    Returns (content_type, text_content, file_id).
    """
    # 1. Voice & Audio
    if "voice" in message:
        file_id = message["voice"].get("file_id")
        return "voice", None, file_id
        
    if "audio" in message:
        file_id = message["audio"].get("file_id")
        return "voice", None, file_id
        
    # 2. PDF & Audio Documents
    if "document" in message:
        doc = message["document"]
        mime_type = doc.get("mime_type") or ""
        file_name = doc.get("file_name") or ""
        if "pdf" in mime_type.lower() or file_name.lower().endswith(".pdf"):
            return "pdf", None, doc.get("file_id")
        elif "audio/" in mime_type.lower() or file_name.lower().endswith((".mp3", ".m4a", ".wav", ".aac", ".ogg", ".opus", ".flac")):
            return "voice", None, doc.get("file_id")
            
    # 3. Photo (extract largest size)
    if "photo" in message:
        photo_sizes = message["photo"]
        if photo_sizes:
            file_id = photo_sizes[-1].get("file_id")
            return "photo", None, file_id
            
    # 4. Text/URL
    if "text" in message:
        text = message["text"]
        entities = message.get("entities", [])
        is_url = False
        for entity in entities:
            if entity.get("type") == "url":
                is_url = True
                break
        if not is_url:
            if text.strip().startswith(("http://", "https://", "www.")):
                is_url = True
        
        if is_url:
            return "url", text, None
        else:
            return "text", text, None
            
    return "unsupported", None, None


# ---------------------------------------------------------------------------
# Global HTTP Client Session for Connection Pooling
# ---------------------------------------------------------------------------
http_client = httpx.AsyncClient(timeout=15.0)


# ---------------------------------------------------------------------------
# Upstash Redis REST Command Helper
# ---------------------------------------------------------------------------
async def run_upstash_command(command: list) -> dict:
    """Sends a REST request to Upstash Redis using the shared connection pool."""
    url = settings.UPSTASH_REDIS_REST_URL
    token = settings.UPSTASH_REDIS_REST_TOKEN
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    resp = await http_client.post(url, json=command, headers=headers)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Telegram API sendMessage Helper
# ---------------------------------------------------------------------------
async def send_telegram_ack(chat_id: str, ack_message: str):
    """Sends an immediate message back to the Telegram chat using the shared connection pool."""
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": ack_message
    }
    try:
        resp = await http_client.post(url, json=payload)
        resp.raise_for_status()
        logger.info("Telegram ACK successfully sent to chat_id %s: '%s'", chat_id, ack_message)
    except Exception as e:
        logger.error("Failed to send Telegram ACK to chat_id %s: %s", chat_id, e)


async def send_telegram_media(chat_id: str, source_type: str, file_id: str, caption: Optional[str] = None):
    """Sends a stored file back to the Telegram chat using its file_id."""
    bot_token = settings.TELEGRAM_BOT_TOKEN
    method = "sendDocument"
    param_name = "document"
    
    if source_type == "voice":
        method = "sendVoice"
        param_name = "voice"
    elif source_type in ("photo", "image"):
        method = "sendPhoto"
        param_name = "photo"
        
    url = f"https://api.telegram.org/bot{bot_token}/{method}"
    payload = {
        "chat_id": chat_id,
        param_name: file_id
    }
    if caption:
        payload["caption"] = caption
        
    try:
        resp = await http_client.post(url, json=payload)
        resp.raise_for_status()
        logger.info("Successfully sent %s media to chat_id %s using file_id %s", source_type, chat_id, file_id)
    except Exception as e:
        logger.error("Failed to send %s media to chat_id %s: %s", source_type, chat_id, e)



# ---------------------------------------------------------------------------
# POST /webhook Endpoint
# ---------------------------------------------------------------------------
@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: psycopg.AsyncConnection = Depends(get_db)
):
    """
    FastAPI webhook handler for Telegram Bot updates.
    Enforces idempotency, parses message type, pushes tasks, and responds in < 50ms.
    """
    start_time = time.perf_counter()
    try:
        update = await request.json()
        update_id = update.get("update_id")
        message = update.get("message")
        
        if update_id is None or not message:
            logger.warning("Received invalid/empty Telegram update (missing update_id or message).")
            return {"status": "ok", "detail": "invalid_update"}
            
        update_id_str = str(update_id)
        chat_id = str(message.get("chat", {}).get("id"))
        if not chat_id:
            logger.warning("Received update_id %s with missing chat ID.", update_id_str)
            return {"status": "ok", "detail": "invalid_chat"}
            
        logger.info("Processing Telegram update: update_id=%s, chat_id=%s", update_id_str, chat_id)

        # 3. Idempotency check: atomic INSERT ... ON CONFLICT DO NOTHING
        async with db.cursor() as cur:
            await cur.execute(
                "INSERT INTO processed_updates (update_id) VALUES (%s) ON CONFLICT (update_id) DO NOTHING",
                (update_id_str,)
            )
            rows_affected = cur.rowcount
            await db.commit()
            
        if rows_affected == 0:
            logger.info("Duplicate update_id %s received; silently discarding.", update_id_str)
            return {"status": "ok", "detail": "duplicate"}
            
        # 4. Rate limit check
        await check_rate_limit(chat_id)
        
        # 4.5 Check for bot commands
        text_content = message.get("text", "")
        if text_content and text_content.strip().startswith("/"):
            from datetime import datetime, timezone
            user_id = await upsert_user(chat_id, db)
            
            cleaned_text = text_content.strip()
            parts = cleaned_text.split(maxsplit=1)
            command_part = parts[0].split("@")[0].lower()  # Handle bot username suffix
            args = parts[1].strip() if len(parts) > 1 else ""
            
            # Map clickable /file_123 or /get_123 to command_part="/file" and args="123"
            if command_part.startswith("/file_"):
                args = command_part.replace("/file_", "")
                command_part = "/file"
            elif command_part.startswith("/get_"):
                args = command_part.replace("/get_", "")
                command_part = "/file"
            
            if command_part == "/start":
                welcome_msg = "Welcome to Recall! Forward me any link, voice note, PDF, or image and I'll remember it for you."
                background_tasks.add_task(send_telegram_ack, chat_id, welcome_msg)
                logger.info("Processed /start: created/retrieved user %d for chat_id %s", user_id, chat_id)
                return {"status": "ok", "detail": "welcome_sent"}
                
            elif command_part == "/help":
                help_msg = (
                    "📚 Recall Commands:\n"
                    "/start — Set up your account\n"
                    "/search <query> — Find saved items\n"
                    "/list — Show your last 10 saves\n"
                    "/file <id> — Retrieve a saved file, link, or note by ID\n"
                    "/delete <id> — Delete an item by ID\n"
                    "/quiz — Get a due quiz question\n"
                    "/remind <time> <message> — Set a reminder (e.g. /remind 2h Review ML notes)\n"
                    "/stats — Your knowledge stats\n"
                    "/streak — Current save streak\n"
                    "/connect_drive — Connect Google Drive backup\n"
                    "/tags — Show your top tags"
                )
                background_tasks.add_task(send_telegram_ack, chat_id, help_msg)
                logger.info("Processed /help for chat_id %s", chat_id)
                return {"status": "ok", "detail": "help_sent"}

            elif command_part == "/tags":
                async with db.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT DISTINCT unnest(tags) AS tag, COUNT(*) AS count
                        FROM items
                        WHERE user_id = %s
                        GROUP BY tag
                        ORDER BY count DESC
                        LIMIT 10;
                        """,
                        (user_id,)
                    )
                    rows = await cur.fetchall()

                if not rows:
                    tags_msg = "🏷 Your top tags:\nYou haven't saved any items with tags yet."
                else:
                    lines = ["🏷 Your top tags:"]
                    for idx, (tag, count) in enumerate(rows, 1):
                        lines.append(f"{idx}. {tag} ({count})")
                    tags_msg = "\n".join(lines)

                background_tasks.add_task(send_telegram_ack, chat_id, tags_msg)
                logger.info("Processed /tags command for chat_id %s, returned %d tags", chat_id, len(rows))
                return {"status": "ok", "detail": "tags_processed"}
                
            elif command_part in ("/file", "/get"):
                if not args:
                    file_msg = "Please provide an item ID: /file 42"
                    background_tasks.add_task(send_telegram_ack, chat_id, file_msg)
                else:
                    try:
                        item_id = int(args)
                        async with db.cursor() as cur:
                            await cur.execute(
                                "SELECT source_type, source_url, raw_text, title FROM items WHERE id = %s AND user_id = %s;",
                                (item_id, user_id)
                            )
                            row = await cur.fetchone()
                            
                        if not row:
                            file_msg = "Item not found."
                            background_tasks.add_task(send_telegram_ack, chat_id, file_msg)
                        else:
                            source_type, source_url, raw_text, title = row
                            if source_type in ("pdf", "voice", "photo", "image"):
                                if source_url:
                                    # Send the file back using its stored file_id
                                    caption = title or f"{source_type.capitalize()} file"
                                    background_tasks.add_task(send_telegram_media, chat_id, source_type, source_url, caption)
                                else:
                                    file_msg = f"This {source_type} item does not have a saved Telegram file ID."
                                    background_tasks.add_task(send_telegram_ack, chat_id, file_msg)
                            elif source_type == "url":
                                file_msg = f"🔗 Here is the link you saved:\n{source_url}"
                                background_tasks.add_task(send_telegram_ack, chat_id, file_msg)
                            else:
                                # Decrypt raw text for notes
                                from backend.services.encryption import decrypt
                                try:
                                    decrypted = decrypt(raw_text)
                                except Exception:
                                    decrypted = raw_text
                                file_msg = f"📝 Saved Note:\n{decrypted}"
                                background_tasks.add_task(send_telegram_ack, chat_id, file_msg)
                    except ValueError:
                        file_msg = "Please provide a valid item ID: /file 42"
                        background_tasks.add_task(send_telegram_ack, chat_id, file_msg)
                return {"status": "ok", "detail": "file_processed"}
                
            elif command_part == "/search":
                if not args:
                    search_msg = "Please provide a search query: /search machine learning"
                else:
                    from backend.services.search_service import hybrid_search
                    results = await hybrid_search(args, user_id, db)
                    if not results:
                        search_msg = f"🔍 No results found for \"{args}\"."
                    else:
                        # Limit to top-5 results
                        results_limited = results[:5]
                        
                        # Generate synthesised RAG answer if results count >= 3
                        answer = None
                        if len(results_limited) >= 3:
                            from backend.services.ai_cascade import AICascade
                            cascade = AICascade()
                            try:
                                summaries = [r["summary"] or "" for r in results_limited]
                                answer = await cascade.answer_question(args, summaries)
                            except Exception as e:
                                logger.error("RAG answer generation in bot /search failed: %s", e)
                                answer = None
                        
                        lines = [f"🔍 Query: {args}"]
                        if answer:
                            lines.append(f"💡 {answer}")
                        lines.append("")
                        lines.append("Sources:")
                        for idx, item in enumerate(results_limited, 1):
                            source_type = item["source_type"]
                            title = item["title"]
                            display_title = title or (
                                "Voice note" if source_type == "voice"
                                else "PDF" if source_type == "pdf"
                                else "Image" if source_type in ("photo", "image")
                                else "Link" if source_type == "url"
                                else "Text"
                            )
                            lines.append(f"{idx}. [{source_type}] {display_title} — /file_{item['id']}")
                        search_msg = "\n".join(lines)
                        
                background_tasks.add_task(send_telegram_ack, chat_id, search_msg)
                logger.info("Processed /search %s for chat_id %s", args, chat_id)
                return {"status": "ok", "detail": "search_processed"}

            elif command_part == "/list":
                async with db.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT id, title, source_type, created_at FROM items
                        WHERE user_id = %s
                        ORDER BY created_at DESC
                        LIMIT 10;
                        """,
                        (user_id,)
                    )
                    rows = await cur.fetchall()
                    
                if not rows:
                    list_msg = "📋 Your last 10 saves:\nYou haven't saved any items yet."
                else:
                    lines = ["📋 Your last 10 saves:"]
                    for idx, (item_id, title, source_type, created_at) in enumerate(rows, 1):
                        display_title = title or (
                            "Voice note" if source_type == "voice"
                            else "PDF" if source_type == "pdf"
                            else "Image" if source_type in ("photo", "image")
                            else "Link" if source_type == "url"
                            else "Text"
                        )
                        
                        if created_at.tzinfo is not None:
                            now = datetime.now(timezone.utc)
                        else:
                            now = datetime.now(timezone.utc).replace(tzinfo=None)
                            
                        diff = now - created_at
                        diff_seconds = int(diff.total_seconds())
                        
                        if diff_seconds < 60:
                            rel_time = "just now"
                        elif diff_seconds < 3600:
                            mins = diff_seconds // 60
                            rel_time = f"{mins} minute ago" if mins == 1 else f"{mins} minutes ago"
                        elif diff_seconds < 86400:
                            hours = diff_seconds // 3600
                            rel_time = f"{hours} hour ago" if hours == 1 else f"{hours} hours ago"
                        elif diff_seconds < 172800:
                            rel_time = "yesterday"
                        else:
                            days = diff.days
                            rel_time = f"{days} days ago"
                            
                        lines.append(f"{idx}. [{source_type}] {display_title} ({rel_time}) — /file_{item_id}")
                    list_msg = "\n".join(lines)
                    
                background_tasks.add_task(send_telegram_ack, chat_id, list_msg)
                logger.info("Processed /list for chat_id %s, items=%d", chat_id, len(rows))
                return {"status": "ok", "detail": "list_sent"}
                
            elif command_part == "/delete":
                if not args:
                    delete_msg = "Please provide a valid item ID: /delete 42"
                else:
                    try:
                        item_id = int(args)
                        async with db.cursor() as cur:
                            await cur.execute(
                                "DELETE FROM quizzes WHERE item_id = %s AND user_id = %s;",
                                (item_id, user_id)
                            )
                            await cur.execute(
                                "DELETE FROM item_chunks WHERE item_id = %s AND user_id = %s;",
                                (item_id, user_id)
                            )
                            await cur.execute(
                                "DELETE FROM items WHERE id = %s AND user_id = %s;",
                                (item_id, user_id)
                            )
                            rows_deleted = cur.rowcount
                            await db.commit()
                        if rows_deleted > 0:
                            delete_msg = "Deleted ✓"
                        else:
                            delete_msg = "Item not found."
                    except ValueError:
                        delete_msg = "Please provide a valid item ID: /delete 42"
                        
                background_tasks.add_task(send_telegram_ack, chat_id, delete_msg)
                logger.info("Processed /delete %s for chat_id %s", args, chat_id)
                return {"status": "ok", "detail": "delete_processed"}
                
            elif command_part == "/stats":
                async with db.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT source_type, COUNT(*) 
                        FROM items 
                        WHERE user_id = %s 
                        GROUP BY source_type;
                        """,
                        (user_id,)
                    )
                    items_rows = await cur.fetchall()
                    
                    await cur.execute(
                        "SELECT COUNT(*) FROM quizzes WHERE user_id = %s;",
                        (user_id,)
                    )
                    quiz_row = await cur.fetchone()
                    quizzes_answered = quiz_row[0] if quiz_row else 0
                    
                    await cur.execute(
                        "SELECT streak_count FROM users WHERE id = %s;",
                        (user_id,)
                    )
                    user_row = await cur.fetchone()
                    streak_count = user_row[0] if user_row else 0
                    
                total_saves = 0
                links_count = 0
                voice_count = 0
                pdfs_count = 0
                images_count = 0
                texts_count = 0
                
                for source_type, count in items_rows:
                    total_saves += count
                    if source_type == "url":
                        links_count = count
                    elif source_type == "voice":
                        voice_count = count
                    elif source_type in ("pdf", "document"):
                        pdfs_count = count
                    elif source_type in ("photo", "image"):
                        images_count = count
                    elif source_type == "text":
                        texts_count = count
                        
                stats_line = f"— Links: {links_count} | Voice: {voice_count} | PDFs: {pdfs_count} | Images: {images_count}"
                if texts_count > 0:
                    stats_line += f" | Texts: {texts_count}"
                    
                stats_msg = (
                    "📊 Your Recall stats:\n"
                    f"Total saves: {total_saves}\n"
                    f"{stats_line}\n"
                    f"Quizzes answered: {quizzes_answered}\n"
                    f"Current streak: 🔥 {streak_count} days"
                )
                background_tasks.add_task(send_telegram_ack, chat_id, stats_msg)
                logger.info("Processed /stats for chat_id %s", chat_id)
                return {"status": "ok", "detail": "stats_sent"}
                
            else:
                unknown_msg = "Unknown command. Type /help to see all commands."
                background_tasks.add_task(send_telegram_ack, chat_id, unknown_msg)
                logger.info("Processed unknown command %s for chat_id %s", command_part, chat_id)
                return {"status": "ok", "detail": "unknown_command_sent"}
            
        # 5. Detect content type
        content_type, text_content, file_id = detect_content_type(message)
        logger.info("Detected message content type '%s' for update_id=%s.", content_type, update_id_str)
        
        # 6. Dispatch immediate Telegram ACK
        ack_message = ACK_MESSAGES.get(content_type, ACK_MESSAGES["unsupported"])
        background_tasks.add_task(send_telegram_ack, chat_id, ack_message)
        
        # 7. Push task JSON to Upstash Redis queue (LPUSH recall:tasks) ONLY if supported
        if content_type != "unsupported":
            task = {
                "update_id": update_id_str,
                "chat_id": chat_id,
                "content_type": content_type
            }
            if content_type in ("text", "url"):
                task["text"] = text_content
            elif content_type in ("voice", "pdf", "photo"):
                task["file_id"] = file_id
                
            command = ["LPUSH", "recall:tasks", json.dumps(task)]
            background_tasks.add_task(run_upstash_command, command)
            logger.info(
                "Queued background task (Redis push) for update_id=%s, chat_id=%s, type=%s",
                update_id_str, chat_id, content_type
            )
        else:
            logger.info(
                "Skipped Redis queue push for unsupported content type on update_id=%s, chat_id=%s",
                update_id_str, chat_id
            )
        
    except RateLimitExceeded as e:
        logger.warning(
            "Rate limit exceeded for chat_id %s: returning 200 to Telegram (retry_after=%.1fs).",
            chat_id, e.retry_after
        )
        return {"status": "ok", "detail": "rate_limited"}
    except Exception as e:
        logger.exception("Exception caught in webhook handler: %s", e)
        # Always return 200 to stop delivery retry loop storms
        return {"status": "ok", "detail": "error_handled"}
        
    finally:
        elapsed = (time.perf_counter() - start_time) * 1000
        logger.info("Webhook request finished in %.2f ms", elapsed)
        
    return {"status": "ok"}
