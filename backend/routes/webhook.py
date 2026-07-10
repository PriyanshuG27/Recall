import time
import logging
import asyncio
import httpx
import json
from typing import Optional, Tuple, Any
from datetime import date, datetime, timezone, time as dt_time, timedelta

from fastapi import APIRouter, Depends, Request, BackgroundTasks
from pydantic import BaseModel
from backend.services.sm2 import update_sm2

from backend.config import settings
from backend.db.connection import get_db, transaction_context
from backend.services.user_service import upsert_user
from backend.services.rate_limiter import check_rate_limit, RateLimitExceeded
from backend.services.redis_client import redis
from backend.services.ai_cascade import mask_pii
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
            
    # 3.5 Location
    if "location" in message:
        return "location", json.dumps(message["location"]), None
        
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
from backend.services.http_client import get_http_client
class _HttpProxy:
    def __getattr__(self, name):
        return getattr(get_http_client(), name)
http_client = _HttpProxy()


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
async def send_telegram_ack(
    chat_id: str,
    ack_message: str,
    parse_mode: Optional[str] = None,
    reply_to_message_id: Optional[int] = None,
    reply_markup: Optional[dict] = None
):
    """Sends an immediate message back to the Telegram chat using the shared connection pool."""
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": ack_message
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_to_message_id is not None:
        payload["reply_to_message_id"] = reply_to_message_id
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
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
    import hmac
    from fastapi import HTTPException
    
    token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    webhook_secret = settings.TELEGRAM_WEBHOOK_SECRET
    if webhook_secret:
        if not token or not hmac.compare_digest(token, webhook_secret):
            logger.warning("Telegram webhook received unauthorized request (invalid or missing secret token).")
            raise HTTPException(status_code=403, detail="Unauthorized")

    start_time = time.perf_counter()
    base_url = str(request.base_url).rstrip("/")
    try:
        update = await request.json()
        update_id = update.get("update_id")
        message = update.get("message")
        callback_query = update.get("callback_query")
        
        if update_id is None or (not message and not callback_query):
            logger.warning("Received invalid/empty Telegram update (missing update_id or message/callback_query).")
            return {"status": "ok", "detail": "invalid_update"}
            
        update_id_str = str(update_id)
        
        if callback_query:
            message = callback_query.get("message", {})
            chat_id = str(message.get("chat", {}).get("id"))
        else:
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
        
        # 4.2 Handle Callback Query
        if callback_query:
            callback_query_id = callback_query.get("id")
            data = callback_query.get("data", "")
            
            # Acknowledge immediately to stop Telegram loading spinner instantly!
            is_onboarding_or_settings = (
                data == "quiz:next" or
                data == "onboarding_tz_menu" or
                data == "onboarding_tz_back" or
                data == "onboarding_tz_custom" or
                data == "onboarding_tz_location_request" or
                data.startswith("onboarding_drive_sync:") or
                data.startswith("onboarding_drive_disconnect:") or
                data.startswith("onboarding_skip:") or
                data.startswith("onboarding_opt:") or
                data.startswith("onboarding_tz_set:") or
                data.startswith("candidate_confirm:") or
                data.startswith("candidate_drift:")
            )
            if is_onboarding_or_settings:
                url_ans = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
                try:
                    await http_client.post(url_ans, json={"callback_query_id": callback_query_id})
                except Exception as ans_err:
                    logger.error("Failed to answer callback query: %s", ans_err)
            
            user_id = await upsert_user(chat_id, db)
            
            if data.startswith("candidate_confirm:"):
                cand_id = int(data.split(":")[1])
                orig_text = callback_query.get("message", {}).get("text", "")
                background_tasks.add_task(
                    process_candidate_confirm_background,
                    cand_id,
                    user_id,
                    chat_id,
                    callback_query.get("message", {}).get("message_id"),
                    orig_text
                )
                return {"status": "ok"}
                
            elif data.startswith("candidate_drift:"):
                cand_id = int(data.split(":")[1])
                orig_text = callback_query.get("message", {}).get("text", "")
                background_tasks.add_task(
                    process_candidate_drift_background,
                    cand_id,
                    user_id,
                    chat_id,
                    callback_query.get("message", {}).get("message_id"),
                    orig_text
                )
                return {"status": "ok"}

            if data == "quiz:next":
                async with db.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT id, question, options, correct_index, explanation
                        FROM quizzes
                        WHERE user_id = %s
                          AND next_review <= CURRENT_DATE
                        ORDER BY next_review ASC
                        LIMIT 1;
                        """,
                        (user_id,)
                    )
                    row = await cur.fetchone()
                    
                is_photo = "photo" in callback_query.get("message", {})
                
                if not row:
                    if is_photo:
                        url_send = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
                        payload_send = {
                            "chat_id": chat_id,
                            "text": "🎉 No quizzes due! Come back tomorrow.",
                            "parse_mode": "HTML"
                        }
                        background_tasks.add_task(http_client.post, url_send, json=payload_send)
                        
                        url_markup = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/editMessageReplyMarkup"
                        payload_markup = {
                            "chat_id": chat_id,
                            "message_id": callback_query["message"]["message_id"],
                            "reply_markup": {"inline_keyboard": []}
                        }
                        background_tasks.add_task(http_client.post, url_markup, json=payload_markup)
                    else:
                        url_edit = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/editMessageText"
                        payload_edit = {
                            "chat_id": chat_id,
                            "message_id": callback_query["message"]["message_id"],
                            "text": "🎉 No quizzes due! Come back tomorrow.",
                            "parse_mode": "HTML",
                            "reply_markup": {"inline_keyboard": []}
                        }
                        background_tasks.add_task(http_client.post, url_edit, json=payload_edit)
                    logger.info("Processed quiz:next: no quizzes left for chat_id %s", chat_id)
                else:
                    quiz_id, question, options_val, correct_index, explanation = row
                    if isinstance(options_val, str):
                        opts = json.loads(options_val)
                    else:
                        opts = options_val
                        
                    inline_keyboard = [
                        [{"text": f"A. {opts[0]}", "callback_data": f"quiz:{quiz_id}:0"}],
                        [{"text": f"B. {opts[1]}", "callback_data": f"quiz:{quiz_id}:1"}],
                        [{"text": f"C. {opts[2]}", "callback_data": f"quiz:{quiz_id}:2"}],
                        [{"text": f"D. {opts[3]}", "callback_data": f"quiz:{quiz_id}:3"}]
                    ]
                    
                    if is_photo:
                        url_send = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
                        payload_send = {
                            "chat_id": chat_id,
                            "text": f"<b>{question}</b>",
                            "parse_mode": "HTML",
                            "reply_markup": {
                                "inline_keyboard": inline_keyboard
                            }
                        }
                        background_tasks.add_task(http_client.post, url_send, json=payload_send)
                        
                        url_markup = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/editMessageReplyMarkup"
                        payload_markup = {
                            "chat_id": chat_id,
                            "message_id": callback_query["message"]["message_id"],
                            "reply_markup": {"inline_keyboard": []}
                        }
                        background_tasks.add_task(http_client.post, url_markup, json=payload_markup)
                    else:
                        url_edit = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/editMessageText"
                        payload_edit = {
                            "chat_id": chat_id,
                            "message_id": callback_query["message"]["message_id"],
                            "text": f"<b>{question}</b>",
                            "parse_mode": "HTML",
                            "reply_markup": {
                                "inline_keyboard": inline_keyboard
                            }
                        }
                        background_tasks.add_task(http_client.post, url_edit, json=payload_edit)
                    logger.info("Processed quiz:next: loaded next quiz %d for chat_id %s", quiz_id, chat_id)
                    
            if data.startswith("onboarding_skip:"):
                parts = data.split(":")
                if len(parts) == 2:
                    step = int(parts[1])
                    current_step_str = await redis.get(f"onboarding_step:{chat_id}")
                    if current_step_str and int(current_step_str) == step:
                        background_tasks.add_task(advance_onboarding_step, chat_id, user_id, step, db, background_tasks)
                return {"status": "ok", "detail": "onboarding_skip_processed"}
                
            elif data == "onboarding_tz_menu" or data == "onboarding_tz_back":
                timezone_keyboard = {
                    "inline_keyboard": [
                        [
                            {"text": "GMT-8 (PST)", "callback_data": "onboarding_tz_set:-480"},
                            {"text": "GMT-5 (EST)", "callback_data": "onboarding_tz_set:-300"}
                        ],
                        [
                            {"text": "GMT+0 (UTC)", "callback_data": "onboarding_tz_set:0"},
                            {"text": "GMT+1 (BST/CET)", "callback_data": "onboarding_tz_set:60"}
                        ],
                        [
                            {"text": "GMT+5:30 (IST)", "callback_data": "onboarding_tz_set:330"},
                            {"text": "GMT+8 (SGT/CST)", "callback_data": "onboarding_tz_set:480"}
                        ],
                        [
                            {"text": "Custom Offset 🌍", "callback_data": "onboarding_tz_custom"}
                        ],
                        [
                            {"text": "Auto-Detect via Location 📍", "callback_data": "onboarding_tz_location_request"}
                        ],
                        [
                            {"text": "« Back to Settings", "callback_data": "onboarding_tz_back" if data == "onboarding_tz_menu" else "onboarding_tz_menu"}
                        ]
                    ]
                }
                
                url_edit = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/editMessageText"
                if data == "onboarding_tz_menu":
                    payload_edit = {
                        "chat_id": chat_id,
                        "message_id": callback_query["message"]["message_id"],
                        "text": "⏰ *Select Your Timezone Offset*\n\nChoose one of the standard options below or configure a custom hour offset:",
                        "parse_mode": "Markdown",
                        "reply_markup": timezone_keyboard
                    }
                else:
                    backup_url = f"{settings.VITE_API_URL or 'http://localhost:8000'}/api/auth/google?chat_id={chat_id}"
                    dashboard_url = settings.WEBSITE_URL
                    payload_edit = {
                        "chat_id": chat_id,
                        "message_id": callback_query["message"]["message_id"],
                        "text": "⚙️ *Setup & Settings*\n\nOnboarding complete! To get the most out of Recall, let's configure your settings:\n\n1. **Timezone**: Ensures your daily digests, Morning Mystery, and reminders arrive at the correct local hour.\n2. **Web Dashboard**: Access your interactive 3D mind-graph.\n3. **Google Drive**: Secure automated daily backups of your saved items.",
                        "parse_mode": "Markdown",
                        "reply_markup": {
                            "inline_keyboard": [
                                [{"text": "Set Timezone ⏰", "callback_data": "onboarding_tz_menu"}],
                                [{"text": "Web Dashboard 🌐", "url": dashboard_url}],
                                [{"text": "Backup to Drive 💾", "url": backup_url}]
                            ]
                        }
                    }
                background_tasks.add_task(http_client.post, url_edit, json=payload_edit)
                return {"status": "ok", "detail": "timezone_menu_processed"}

            elif data.startswith("onboarding_tz_set:"):
                parts = data.split(":")
                if len(parts) == 2:
                    try:
                        offset_minutes = int(parts[1])
                    except ValueError:
                        offset_minutes = 0
                        
                    background_tasks.add_task(
                        process_timezone_set_background,
                        offset_minutes,
                        user_id,
                        chat_id,
                        callback_query["message"]["message_id"],
                        base_url
                    )
                return {"status": "ok", "detail": "timezone_set_processed"}

            elif data == "onboarding_tz_custom":
                await redis.setex(f"pending_timezone:{chat_id}", 300, "1")
                
                url_edit = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/editMessageText"
                payload_edit = {
                    "chat_id": chat_id,
                    "message_id": callback_query["message"]["message_id"],
                    "text": "🌍 *Custom Timezone Setup*\n\nPlease reply to this message with your UTC offset in hours.\n\n*Examples*:\n• `+5.5` for GMT+5:30 (India)\n• `-8` for GMT-8:00 (PST)\n• `+0` for GMT/UTC\n• `+1` for GMT+1:00 (BST)\n\n_Type `cancel` to return to settings._",
                    "parse_mode": "Markdown",
                    "reply_markup": {
                        "inline_keyboard": [
                            [{"text": "« Cancel", "callback_data": "onboarding_tz_back"}]
                        ]
                    }
                }
                background_tasks.add_task(http_client.post, url_edit, json=payload_edit)
                return {"status": "ok", "detail": "timezone_custom_prompted"}
                
            elif data == "onboarding_tz_location_request":
                # Send message with reply keyboard requesting location
                url_msg = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
                payload_msg = {
                    "chat_id": chat_id,
                    "text": "📍 Please tap the button below to share your location and auto-detect your timezone offset:",
                    "reply_markup": {
                        "keyboard": [
                            [{"text": "Share Location 📍", "request_location": True}]
                        ],
                        "resize_keyboard": True,
                        "one_time_keyboard": True
                    }
                }
                background_tasks.add_task(http_client.post, url_msg, json=payload_msg)
                return {"status": "ok", "detail": "location_requested"}
                
            elif data.startswith("onboarding_drive_sync:"):
                parts = data.split(":", 1)
                cb_base_url = parts[1] if len(parts) > 1 else ""
                background_tasks.add_task(background_drive_sync, user_id, chat_id, cb_base_url)
                settings_msg, markup = await get_onboarding_settings_payload(chat_id, user_id, "🔄 *Google Drive backup sync started in the background...*", cb_base_url)
                url_edit = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/editMessageText"
                payload_edit = {
                    "chat_id": chat_id,
                    "message_id": callback_query["message"]["message_id"],
                    "text": settings_msg,
                    "parse_mode": "Markdown",
                    "reply_markup": markup
                }
                background_tasks.add_task(http_client.post, url_edit, json=payload_edit)
                return {"status": "ok", "detail": "drive_sync_started"}
                
            elif data.startswith("onboarding_drive_disconnect:"):
                parts = data.split(":", 1)
                cb_base_url = parts[1] if len(parts) > 1 else ""
                background_tasks.add_task(
                    process_drive_disconnect_background,
                    user_id,
                    chat_id,
                    callback_query["message"]["message_id"],
                    cb_base_url
                )
                return {"status": "ok", "detail": "drive_disconnected"}
                
            elif data.startswith("onboarding_opt:"):
                parts = data.split(":")
                if len(parts) == 2:
                    choice = parts[1]
                    pending_item_id = await redis.get(f"pending_context:{chat_id}")
                    if pending_item_id:
                        item_id = int(pending_item_id)
                        await redis.delete(f"pending_context:{chat_id}")
                        
                        note_text = ""
                        if choice == "for_me":
                            note_text = "Just for me"
                        elif choice == "act":
                            note_text = "To act on it"
                        elif choice == "share":
                            note_text = "To share with someone"
                        elif choice == "mind":
                            note_text = "Still on my mind"
                        elif choice == "done":
                            note_text = "Already done its job"
                            
                        background_tasks.add_task(
                            process_onboarding_opt_background,
                            note_text,
                            item_id,
                            user_id
                        )
                            
                        url_ans = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
                        background_tasks.add_task(http_client.post, url_ans, json={"callback_query_id": callback_query_id, "text": "Preference saved! ✓"})
                        
                        emoji = "👤" if choice == "for_me" else "🚀" if choice == "act" else "👥" if choice == "share" else "💭" if choice == "mind" else "✓"
                        url_edit = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/editMessageText"
                        payload_edit = {
                            "chat_id": chat_id,
                            "message_id": callback_query["message"]["message_id"],
                            "text": f"{emoji} *Preference saved*: {note_text}.",
                            "parse_mode": "Markdown"
                        }
                        background_tasks.add_task(http_client.post, url_edit, json=payload_edit)
                    else:
                        url_ans = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
                        background_tasks.add_task(http_client.post, url_ans, json={"callback_query_id": callback_query_id, "text": "Session expired or already saved."})
                return {"status": "ok", "detail": "onboarding_opt_processed"}
                
            elif data.startswith("quiz:"):
                parts = data.split(":")
                if len(parts) == 3:
                    try:
                        quiz_id = int(parts[1])
                        selected_idx = int(parts[2])
                    except ValueError:
                        url_ans = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
                        background_tasks.add_task(http_client.post, url_ans, json={"callback_query_id": callback_query_id})
                        return {"status": "ok", "detail": "callback_query_invalid_params"}
                        
                    async with db.cursor() as cur:
                        await cur.execute(
                            """
                            SELECT user_id, ease_factor, interval_days, correct_index, explanation, question, options, next_review
                            FROM quizzes
                            WHERE id = %s;
                            """,
                            (quiz_id,)
                        )
                        row = await cur.fetchone()
                        
                        if not row:
                            url_ans = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
                            background_tasks.add_task(http_client.post, url_ans, json={"callback_query_id": callback_query_id})
                            logger.info("Stale callback/non-existent quiz ID %d: silently ignored", quiz_id)
                            return {"status": "ok", "detail": "quiz_not_found"}
                            
                        owner_id, ease_factor, interval_days, correct_index, explanation, question, options, next_review = row
                        
                        if owner_id != user_id:
                            url_ans = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
                            background_tasks.add_task(
                                http_client.post,
                                url_ans,
                                json={"callback_query_id": callback_query_id, "text": "This quiz does not belong to you."}
                            )
                            return {"status": "ok", "detail": "quiz_ownership_rejected"}
                            
                        if next_review > date.today():
                            url_ans = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
                            background_tasks.add_task(http_client.post, url_ans, json={"callback_query_id": callback_query_id})
                            return {"status": "ok", "detail": "stale_callback_ignored"}
                            
                        is_correct = (selected_idx == correct_index)
                        
                        # Fast path answer Callback Query immediately!
                        url_ans = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
                        payload_ans = {
                            "callback_query_id": callback_query_id,
                            "text": "Correct! 🎉" if is_correct else "Incorrect. ❌"
                        }
                        background_tasks.add_task(
                            http_client.post,
                            url_ans,
                            json=payload_ans
                        )
                        
                        background_tasks.add_task(
                            process_quiz_answer_db_and_ui,
                            chat_id,
                            user_id,
                            quiz_id,
                            selected_idx,
                            is_correct,
                            ease_factor,
                            interval_days,
                            correct_index,
                            explanation,
                            options,
                            callback_query["message"]["message_id"]
                        )
                        logger.info("Processed callback_query answer instantly, background task queued for quiz %d, user %d", quiz_id, user_id)

            elif data.startswith("quiz_me:"):
                parts = data.split(":")
                if len(parts) == 2:
                    try:
                        item_id = int(parts[1])
                        background_tasks.add_task(
                            process_quiz_me_callback,
                            chat_id,
                            user_id,
                            item_id,
                            callback_query_id
                        )
                    except ValueError:
                        pass
                return {"status": "ok", "detail": "callback_query_processed"}

            elif data.startswith("remind_me:"):
                parts = data.split(":")
                if len(parts) == 2:
                    try:
                        item_id = int(parts[1])
                        background_tasks.add_task(
                            process_remind_me_callback,
                            chat_id,
                            user_id,
                            item_id,
                            callback_query_id
                        )
                    except ValueError:
                        pass
                return {"status": "ok", "detail": "callback_query_processed"}

            elif data.startswith("remind_set:"):
                parts = data.split(":")
                if len(parts) == 3:
                    try:
                        item_id = int(parts[1])
                        interval = parts[2]
                        message_id = callback_query["message"]["message_id"]
                        background_tasks.add_task(
                            process_remind_set_callback,
                            chat_id,
                            user_id,
                            item_id,
                            interval,
                            callback_query_id,
                            message_id
                        )
                    except (ValueError, KeyError):
                        pass

            return {"status": "ok", "detail": "callback_query_processed"}
        
        # 4.4 Check if the message is a reply to a bot success message (allowing tagging / context note annotation)
        text_content = message.get("text", "")
        reply_to_message = message.get("reply_to_message")
        if reply_to_message and text_content and not text_content.strip().startswith("/"):
            replied_message_id = reply_to_message.get("message_id")
            if replied_message_id:
                user_id = await upsert_user(chat_id, db)
                item_id_str = await redis.get(f"message_to_item:{chat_id}:{replied_message_id}")
                if item_id_str:
                    import re
                    item_id = int(item_id_str)
                    text_val = text_content.strip()
                    
                    # Check if this message is tags (hashtags)
                    tags = re.findall(r"#([a-zA-Z0-9_-]+)", text_val)
                    if tags:
                        normalized_tags = [t.strip().lower() for t in tags]
                        async with db.cursor() as cur:
                            await cur.execute("SELECT tags FROM items WHERE id = %s AND user_id = %s;", (item_id, user_id))
                            row = await cur.fetchone()
                            existing_tags = row[0] if row and row[0] else []
                            new_tags = list(set(existing_tags + normalized_tags))[:5]
                            await cur.execute(
                                "UPDATE items SET tags = %s WHERE id = %s AND user_id = %s;",
                                (new_tags, item_id, user_id)
                            )
                            await db.commit()
                        
                        try:
                            from backend.routes.websocket import broadcast
                            await broadcast(user_id, {
                                "type": "new_node",
                                "node": {
                                    "id": str(item_id),
                                    "title": "",
                                    "source_type": "url",
                                    "created_at": datetime.now(timezone.utc).isoformat()
                                }
                            })
                        except Exception as ws_err:
                            logger.error("Failed to broadcast reply tags update: %s", ws_err)

                        tags_display = " ".join(f"#{t}" for t in new_tags)
                        ack_msg = f"🏷️ *Tags updated*: {tags_display} ✓"
                        background_tasks.add_task(send_telegram_ack, chat_id, ack_msg, "Markdown")
                        logger.info("Updated tags for item_id=%d from reply message", item_id)
                        return {"status": "ok", "detail": "reply_tags_saved"}
                    else:
                        async with db.cursor() as cur:
                            await cur.execute(
                                "UPDATE items SET context_note = %s WHERE id = %s AND user_id = %s;",
                                (text_val, item_id, user_id)
                            )
                            await db.commit()
                        
                        try:
                            from backend.routes.websocket import broadcast
                            await broadcast(user_id, {
                                "type": "new_node",
                                "node": {
                                    "id": str(item_id),
                                    "title": "",
                                    "source_type": "url",
                                    "created_at": datetime.now(timezone.utc).isoformat()
                                }
                            })
                        except Exception as ws_err:
                            logger.error("Failed to broadcast reply context note update: %s", ws_err)

                        ack_msg = f"💭 *Context note saved*: \"{text_val}\" ✓"
                        background_tasks.add_task(send_telegram_ack, chat_id, ack_msg, "Markdown")
                        logger.info("Saved context note for item_id=%d from reply message", item_id)
                        return {"status": "ok", "detail": "reply_context_note_saved"}
                else:
                    # Check if the replied-to message is from a user (not a bot)
                    from_user = reply_to_message.get("from", {})
                    if not from_user.get("is_bot"):
                        # Defer the reply! Store it in Redis list
                        logger.info("Deferring reply for message_id=%d in chat_id=%s because item is still processing", replied_message_id, chat_id)
                        
                        reply_payload = json.dumps({
                            "text": text_content.strip(),
                            "message_id": message.get("message_id")
                        })
                        await redis.rpush(f"deferred_replies:{chat_id}:{replied_message_id}", reply_payload)
                        await redis.expire(f"deferred_replies:{chat_id}:{replied_message_id}", 3600)
                        
                        import re
                        tags = re.findall(r"#([a-zA-Z0-9_-]+)", text_content.strip())
                        if tags:
                            tags_display = " ".join(f"#{t.lower()}" for t in tags)
                            ack_msg = f"🏷️ *Tags queued*: {tags_display} ✓"
                        else:
                            ack_msg = f"💭 *Context note queued*: \"{text_content.strip()}\" ✓"
                        
                        background_tasks.add_task(send_telegram_ack, chat_id, ack_msg, "Markdown", message.get("message_id"))
                        return {"status": "ok", "detail": "reply_deferred"}
        
        # 4.5 Check for bot commands or login OTP
        text_content = message.get("text", "")
        if text_content:
            stripped_text = text_content.strip()
            # Check if it's a 6-digit OTP code
            if len(stripped_text) == 6 and stripped_text.isdigit():
                from backend.services.redis_client import redis as _redis
                token = await _redis.get(f"bot_web_login_otp:{stripped_text}")
                if token:
                    user_id = await upsert_user(chat_id, db)
                    await _redis.setex(f"bot_web_login:{token.decode('utf-8') if isinstance(token, bytes) else token}", 300, str(user_id))
                    await _redis.delete(f"bot_web_login_otp:{stripped_text}")
                    
                    ack_msg = (
                        "✅ <b>Browser login confirmed!</b>\n\n"
                        "Switch back to your browser tab — you're now logged in."
                    )
                    background_tasks.add_task(send_telegram_ack, chat_id, ack_msg, "HTML", None, None)
                    logger.info("Bot-session OTP login: stored token for user %d", user_id)
                    return {"status": "ok", "detail": "web_login_otp_confirmed"}

        if text_content and text_content.strip().startswith("/"):
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
                # ── Bot-session web login ──────────────────────────────────
                # When the browser initiates a bot-login, it opens:
                #   t.me/AtriumHub_bot?start=weblogin_<token>
                # The bot stores the token → user_id in Redis so the browser
                # can poll /auth/bot-session/poll?token=<token> to complete login.
                if args.startswith("weblogin_"):
                    token = args[len("weblogin_"):]
                    if token:
                        await redis.setex(f"bot_web_login:{token}", 300, str(user_id))
                        ack_msg = (
                            "✅ <b>Browser login confirmed!</b>\n\n"
                            "Switch back to your browser tab — you're now logged in."
                        )
                        background_tasks.add_task(send_telegram_ack, chat_id, ack_msg, "HTML", None, None)
                        logger.info("Bot-session web login: stored token for user %d", user_id)
                        return {"status": "ok", "detail": "web_login_token_stored"}

                # ── Normal /start flow ─────────────────────────────────────
                # Check if user already finished onboarding
                async with db.cursor() as cur:
                    await cur.execute("SELECT initial_onboarding_completed FROM users WHERE id = %s;", (user_id,))
                    row = await cur.fetchone()
                    initial_onboarding_completed = row[0] if row else False
                    
                if not initial_onboarding_completed:
                    async with db.cursor() as cur:
                        await cur.execute("SELECT COUNT(*) FROM items WHERE user_id = %s;", (user_id,))
                        count_row = await cur.fetchone()
                        item_count = count_row[0] if count_row else 0
                else:
                    item_count = 3
                    
                if item_count < 3:
                    welcome_msg = (
                        "Welcome to Recall! Let's build your initial mind-graph.\n\n"
                        "Question 1/3: What is a book or article you read recently that changed how you think?"
                    )
                    markup = {"inline_keyboard": [
                        [{"text": "Open Atrium 🧠", "web_app": {"url": settings.WEBSITE_URL}}],
                        [{"text": "Skip Question ⏭️", "callback_data": "onboarding_skip:1"}]
                    ]}
                    await redis.setex(f"onboarding_step:{chat_id}", 86400, "1")
                    background_tasks.add_task(send_telegram_ack, chat_id, welcome_msg, "HTML", None, markup)
                else:
                    welcome_msg_standard = (
                        "Welcome back to Recall! Forward me any link, voice note, PDF, or image and I'll remember it for you.\n\n"
                        "💡 <b>We also support screenshots!</b> You can send us screenshots of your <b>WhatsApp Saved Messages</b> (or chats containing links), and we will automatically scrape, clean, and save them for you!"
                    )
                    returning_markup = {"inline_keyboard": [
                        [{"text": "Open Atrium 🧠", "web_app": {"url": settings.WEBSITE_URL}}]
                    ]}
                    background_tasks.add_task(send_telegram_ack, chat_id, welcome_msg_standard, "HTML", None, returning_markup)
                    
                logger.info("Processed /start: created/retrieved user %d for chat_id %s", user_id, chat_id)
                return {"status": "ok", "detail": "welcome_sent"}
                
            elif command_part == "/reset_onboarding":
                async with db.cursor() as cur:
                    await cur.execute("DELETE FROM items WHERE user_id = %s;", (user_id,))
                    await cur.execute("UPDATE users SET onboarding_day = 0, onboarding_last_sent = NULL, timezone_offset = 0, initial_onboarding_completed = FALSE WHERE id = %s;", (user_id,))
                    
                    # Log audit
                    from backend.services.audit_service import log_audit
                    await log_audit(
                        db=db,
                        user_id=user_id,
                        action="reset_onboarding",
                        details={"channel": "telegram"},
                        request_id=f"tg_{chat_id}"
                    )
                    
                    await db.commit()
                await redis.delete(f"onboarding_step:{chat_id}")
                await redis.delete(f"pending_context:{chat_id}")
                await redis.delete(f"pending_timezone:{chat_id}")
                
                welcome_msg = (
                    "🔄 *Onboarding reset successful!* All items deleted.\n\n"
                     "Let's build your initial mind-graph.\n\n"
                     "Question 1/3: What is a book or article you read recently that changed how you think?"
                )
                markup = {"inline_keyboard": [[{"text": "Skip Question ⏭️", "callback_data": "onboarding_skip:1"}]]}
                await redis.setex(f"onboarding_step:{chat_id}", 86400, "1")
                url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
                payload = {
                    "chat_id": chat_id,
                    "text": welcome_msg,
                    "parse_mode": "Markdown",
                    "reply_markup": markup
                }
                background_tasks.add_task(http_client.post, url, json=payload)
                logger.info("Processed /reset_onboarding: reset user %d onboarding", user_id)
                return {"status": "ok", "detail": "onboarding_reset"}
                
            elif command_part == "/settings":
                background_tasks.add_task(send_onboarding_settings_card, chat_id, user_id, "", base_url)
                logger.info("Processed /settings command for user %d", user_id)
                return {"status": "ok", "detail": "settings_sent"}
                
            elif command_part == "/help":
                help_msg = (
                    "📚 Recall Commands:\n\n"
                    "⚙️ Account & Setup:\n"
                    "/start — Set up your account\n"
                    "/connect_drive — Connect Google Drive backup\n"
                    "/digest — Toggle daily morning digests (enabled/disabled)\n\n"
                    "🔍 Search & Retrieval:\n"
                    "/search <query> — Search saved items\n"
                    "/list — Show your last 10 saves\n"
                    "/file <id> — Retrieve a saved item by ID\n"
                    "/tags — Show your top tags\n"
                    "/delete <id> — Delete an item by ID\n\n"
                    "⏰ Learning & Reminders:\n"
                    "/remind <time> <message> — Set a reminder (e.g., /remind 2h Review ML notes)\n"
                    "/remind <time> <item_id> — Set a reminder for an item (e.g., /remind tomorrow morning 123)\n"
                    "/quiz — Get a due quiz question\n"
                    "/streak — Show your daily save streak\n"
                    "/stats — View your knowledge stats\n\n"
                    "💡 Tip: Forward me any link, document, text, voice note, or image and I will save it automatically!"
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

            elif command_part == "/quiz":
                async with db.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT id, question, options, correct_index, explanation
                        FROM quizzes
                        WHERE user_id = %s
                          AND next_review <= CURRENT_DATE
                        ORDER BY next_review ASC
                        LIMIT 1;
                        """,
                        (user_id,)
                    )
                    row = await cur.fetchone()
                    
                if not row:
                    quiz_msg = "🎉 No quizzes due! Come back tomorrow."
                    background_tasks.add_task(send_telegram_ack, chat_id, quiz_msg)
                    logger.info("Processed /quiz: no quizzes due for chat_id %s", chat_id)
                else:
                    quiz_id, question, options_val, correct_index, explanation = row
                    if isinstance(options_val, str):
                        opts = json.loads(options_val)
                    else:
                        opts = options_val
                        
                    inline_keyboard = [
                        [{"text": f"A. {opts[0]}", "callback_data": f"quiz:{quiz_id}:0"}],
                        [{"text": f"B. {opts[1]}", "callback_data": f"quiz:{quiz_id}:1"}],
                        [{"text": f"C. {opts[2]}", "callback_data": f"quiz:{quiz_id}:2"}],
                        [{"text": f"D. {opts[3]}", "callback_data": f"quiz:{quiz_id}:3"}]
                    ]
                        
                    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
                    payload = {
                        "chat_id": chat_id,
                        "text": f"<b>{question}</b>",
                        "parse_mode": "HTML",
                        "reply_markup": {
                            "inline_keyboard": inline_keyboard
                        }
                    }
                    background_tasks.add_task(http_client.post, url, json=payload)
                    logger.info("Processed /quiz: sent due quiz %d to chat_id %s", quiz_id, chat_id)
                    
                return {"status": "ok", "detail": "quiz_processed"}
                
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
                    from backend.services.ai_cascade import check_prompt_injection
                    injection_warning = check_prompt_injection(args)
                    if injection_warning:
                        search_msg = f"🔍 Query: {args}\n💡 {injection_warning}"
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
                                from backend.services.ai_cascade import AICascade, ai_cascade
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
                                summary = item.get("summary") or ""
                                summary_snippet = summary[:100] + "..." if len(summary) > 100 else summary
                                summary_part = f" - {summary_snippet}" if summary_snippet else ""
                                lines.append(f"{idx}. [{source_type}] {display_title}{summary_part} — /file_{item['id']}")
                            search_msg = "\n".join(lines)
                        
                background_tasks.add_task(send_telegram_ack, chat_id, search_msg)
                logger.info("Processed /search %s for chat_id %s", mask_pii(args), chat_id)
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
                        async with transaction_context(db):
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
                                    "DELETE FROM reminders WHERE item_id = %s AND user_id = %s;",
                                    (item_id, user_id)
                                )
                                await cur.execute(
                                    "DELETE FROM insight_candidates WHERE (item_id_a = %s OR item_id_b = %s) AND user_id = %s;",
                                    (item_id, item_id, user_id)
                                )
                                await cur.execute(
                                    "DELETE FROM entity_mentions WHERE item_id = %s AND user_id = %s;",
                                    (item_id, user_id)
                                )
                                await cur.execute(
                                    """
                                    DELETE FROM relationships 
                                    WHERE ((source_type = 'item' AND source_id = %s) 
                                       OR (target_type = 'item' AND target_id = %s) 
                                       OR (item_id = %s)) 
                                      AND user_id = %s;
                                    """,
                                    (item_id, item_id, item_id, user_id)
                                )
                                await cur.execute(
                                    "DELETE FROM items WHERE id = %s AND user_id = %s;",
                                    (item_id, user_id)
                                )
                                rows_deleted = cur.rowcount
                                if rows_deleted > 0:
                                    from backend.services.audit_service import log_audit
                                    await log_audit(
                                        db=db,
                                        user_id=user_id,
                                        action="delete_item",
                                        details={"item_id": item_id, "channel": "telegram"},
                                        request_id=f"tg_{chat_id}"
                                    )
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
                    
                    from backend.services.user_service import get_and_update_user_streak
                    streak_count = await get_and_update_user_streak(cur, user_id)
                    await db.commit()
                    
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

            elif command_part == "/streak":
                async with db.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT streak_count, last_activity_date
                        FROM users
                        WHERE id = %s;
                        """,
                        (user_id,)
                    )
                    row = await cur.fetchone()
                    streak_count = row[0] if (row and row[0] is not None) else 0
                    await db.commit()
                
                streak_msg = f"🔥 {streak_count} day streak! Keep saving knowledge."
                background_tasks.add_task(send_telegram_ack, chat_id, streak_msg)
                logger.info("Processed /streak for chat_id %s", chat_id)
                return {"status": "ok", "detail": "streak_sent"}

            elif command_part == "/digest":
                async with db.cursor() as cur:
                    await cur.execute(
                        "SELECT digest_enabled FROM users WHERE id = %s;",
                        (user_id,)
                    )
                    row = await cur.fetchone()
                    current_status = row[0] if (row and row[0] is not None) else True
                    
                    new_status = not current_status
                    await cur.execute(
                        "UPDATE users SET digest_enabled = %s WHERE id = %s;",
                        (new_status, user_id)
                    )
                    await db.commit()
                    
                if new_status:
                    digest_msg = "📬 Daily digest enabled! You will receive morning summaries at 08:00 AM local time."
                else:
                    digest_msg = "📬 Daily digest disabled. You will no longer receive morning summaries."
                    
                background_tasks.add_task(send_telegram_ack, chat_id, digest_msg)
                logger.info("Processed /digest for chat_id %s, set to %s", chat_id, new_status)
                return {"status": "ok", "detail": "digest_toggled"}

            elif command_part == "/remind":
                if not args:
                    remind_err = "Sorry, I didn't understand that time.\n\nTry:\n/remind 2h Read those notes"
                    background_tasks.add_task(send_telegram_ack, chat_id, remind_err)
                    return {"status": "ok", "detail": "remind_invalid"}
                    
                from backend.services.reminder_service import parse_time_expression, create_reminder
                delta, absolute_format, message = parse_time_expression(args)
                
                if delta is None and absolute_format is None:
                    remind_err = "Sorry, I didn't understand that time.\n\nTry:\n/remind 2h Read those notes"
                    background_tasks.add_task(send_telegram_ack, chat_id, remind_err)
                    return {"status": "ok", "detail": "remind_invalid"}
                    
                if not message:
                    remind_err = "Please provide a message for your reminder.\n\nTry:\n/remind 2h Read those notes"
                    background_tasks.add_task(send_telegram_ack, chat_id, remind_err)
                    return {"status": "ok", "detail": "remind_invalid"}
                
                # Detect if the reminder references a saved item ID
                cleaned_msg = message.strip()
                item_id_ref = None
                item_found = False
                item_title = ""
                
                # Check different reference formats:
                if cleaned_msg.isdigit():
                    item_id_ref = int(cleaned_msg)
                elif cleaned_msg.lower().startswith("item:") and cleaned_msg[5:].strip().isdigit():
                    item_id_ref = int(cleaned_msg[5:].strip())
                elif cleaned_msg.lower().startswith("file:") and cleaned_msg[5:].strip().isdigit():
                    item_id_ref = int(cleaned_msg[5:].strip())
                elif cleaned_msg.startswith("/file_") and cleaned_msg[6:].strip().isdigit():
                    item_id_ref = int(cleaned_msg[6:].strip())
                elif cleaned_msg.startswith("/get_") and cleaned_msg[5:].strip().isdigit():
                    item_id_ref = int(cleaned_msg[5:].strip())
                
                if item_id_ref is not None:
                    async with db.cursor() as cur:
                        await cur.execute(
                            "SELECT title FROM items WHERE id = %s AND user_id = %s;",
                            (item_id_ref, user_id)
                        )
                        item_row = await cur.fetchone()
                        if item_row:
                            item_title = item_row[0] or "Untitled Item"
                            message = f"Review Item: {item_title}\nRetrieve: /file_{item_id_ref}"
                            item_found = True
                
                # Fetch user's timezone_offset
                async with db.cursor() as cur:
                    await cur.execute(
                        "SELECT timezone_offset FROM users WHERE id = %s;",
                        (user_id,)
                    )
                    user_row = await cur.fetchone()
                    timezone_offset = user_row[0] if (user_row and user_row[0] is not None) else 0
                    
                # Calculate remind_at in UTC
                if delta is not None:
                    remind_at_utc = datetime.now(timezone.utc) + delta
                else:
                    utc_now = datetime.now(timezone.utc)
                    user_local = utc_now + timedelta(minutes=timezone_offset)
                    
                    if absolute_format in ("tomorrow", "tomorrow_morning"):
                        target_date = user_local.date() + timedelta(days=1)
                        target_local_dt = datetime.combine(target_date, dt_time(9, 0))
                    elif absolute_format == "tomorrow_evening":
                        target_date = user_local.date() + timedelta(days=1)
                        target_local_dt = datetime.combine(target_date, dt_time(19, 0))
                    elif absolute_format == "next_week":
                        target_date = user_local.date() + timedelta(days=7)
                        target_local_dt = datetime.combine(target_date, dt_time(9, 0))
                    else:
                        remind_err = "Sorry, I didn't understand that time.\n\nTry:\n/remind 2h Read those notes"
                        background_tasks.add_task(send_telegram_ack, chat_id, remind_err)
                        return {"status": "ok", "detail": "remind_invalid"}
                        
                    remind_at_utc = target_local_dt - timedelta(minutes=timezone_offset)
                    remind_at_utc = remind_at_utc.replace(tzinfo=timezone.utc)
                
                try:
                    reminder_id, final_message, was_truncated = await create_reminder(
                        user_id, message, remind_at_utc, db
                    )
                    await db.commit()
                except ValueError as val_err:
                    background_tasks.add_task(send_telegram_ack, chat_id, str(val_err))
                    return {"status": "ok", "detail": "remind_limit_exceeded"}
                except Exception as err:
                    logger.error("Failed to create reminder: %s", err)
                    background_tasks.add_task(send_telegram_ack, chat_id, "Failed to set reminder. Please try again.")
                    return {"status": "ok", "detail": "remind_failed"}
                
                # Format response datetime in user's local timezone
                user_local_target = remind_at_utc + timedelta(minutes=timezone_offset)
                formatted_dt = user_local_target.strftime("%d %b %Y at %H:%M")
                
                if item_found:
                    reply_msg = f"⏰ Reminder set for item '{item_title}' on {formatted_dt} ✓"
                else:
                    reply_msg = f"⏰ Reminder set for {formatted_dt} ✓"
                    
                if was_truncated:
                    reply_msg += "\n(Note: Your reminder message was truncated to 500 characters.)"
                    
                background_tasks.add_task(send_telegram_ack, chat_id, reply_msg)
                logger.info("Processed /remind: created reminder %d for user %d", reminder_id, user_id)
                return {"status": "ok", "detail": "remind_processed"}
                
            else:
                unknown_msg = "Unknown command. Type /help to see all commands."
                background_tasks.add_task(send_telegram_ack, chat_id, unknown_msg)
                logger.info("Processed unknown command %s for chat_id %s", command_part, chat_id)
                return {"status": "ok", "detail": "unknown_command_sent"}
            
        # 5. Detect content type
        content_type, text_content, file_id = detect_content_type(message)
        logger.info("Detected message content type '%s' for update_id=%s.", content_type, update_id_str)
        
        # 5.5 Handle location-based timezone auto-detection
        if content_type == "location" and text_content:
            try:
                loc_data = json.loads(text_content)
                lon = float(loc_data.get("longitude", 0.0))
                offset_hours = round(lon / 15.0 * 2) / 2
                offset_minutes = int(offset_hours * 60)
                
                user_id = await upsert_user(chat_id, db)
                async with db.cursor() as cur:
                    await cur.execute(
                        "UPDATE users SET timezone_offset = %s WHERE id = %s;",
                        (offset_minutes, user_id)
                    )
                    await db.commit()
                
                url_dismiss = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
                background_tasks.add_task(http_client.post, url_dismiss, json={
                    "chat_id": chat_id,
                    "text": "📍 Location received. Resolving timezone...",
                    "reply_markup": {"remove_keyboard": True}
                })
                
                sign = "+" if offset_minutes >= 0 else "-"
                h_abs = abs(offset_minutes) // 60
                m_abs = abs(offset_minutes) % 60
                tz_str = f"GMT{sign}{h_abs:02d}:{m_abs:02d}"
                status_banner = f"📍 Timezone set to {tz_str} from your location."
                background_tasks.add_task(send_onboarding_settings_card, chat_id, user_id, status_banner, base_url)
                return {"status": "ok", "detail": "timezone_location_detected"}
            except Exception as loc_err:
                logger.error("Failed to parse/save location timezone: %s", loc_err)
                user_id = await upsert_user(chat_id, db)
                background_tasks.add_task(send_onboarding_settings_card, chat_id, user_id, "⚠️ Failed to auto-detect timezone from location.", base_url)
                return {"status": "ok", "detail": "timezone_location_failed"}
        
        # 6. Check onboarding state
        user_id = await upsert_user(chat_id, db)
        onboarding_step_str = await redis.get(f"onboarding_step:{chat_id}")
        
        is_onboarding = False
        if onboarding_step_str:
            is_onboarding = True
        else:
            async with db.cursor() as cur:
                await cur.execute("SELECT initial_onboarding_completed FROM users WHERE id = %s;", (user_id,))
                row = await cur.fetchone()
                initial_onboarding_completed = row[0] if row else False
                
            if not initial_onboarding_completed:
                async with db.cursor() as cur:
                    await cur.execute("SELECT COUNT(*) FROM items WHERE user_id = %s;", (user_id,))
                    count_row = await cur.fetchone()
                    item_count = count_row[0] if count_row else 0
                if item_count < 3:
                    is_onboarding = True
                    onboarding_step_str = "1"
                    await redis.setex(f"onboarding_step:{chat_id}", 86400, "1")

        if is_onboarding:
            step = int(onboarding_step_str)
            
            if content_type != "text" or not text_content:
                unsupported_msg = "Please reply with a text answer to seed your graph, or click 'Skip Question'."
                markup = {"inline_keyboard": [[{"text": "Skip Question ⏭️", "callback_data": f"onboarding_skip:{step}"}]]}
                url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
                payload = {
                    "chat_id": chat_id,
                    "text": unsupported_msg,
                    "reply_markup": markup
                }
                background_tasks.add_task(http_client.post, url, json=payload)
                return {"status": "ok", "detail": "onboarding_invalid_type"}
                
            if text_content.strip().lower() == "skip":
                background_tasks.add_task(advance_onboarding_step, chat_id, user_id, step, db, background_tasks)
                return {"status": "ok", "detail": "onboarding_text_skip"}
                
            # Length guardrail (at least 3 words)
            if len(text_content.strip().split()) < 3:
                short_msg = "That's a bit short! Could you tell me a little more? Or click 'Skip' to move on."
                markup = {"inline_keyboard": [[{"text": "Skip Question ⏭️", "callback_data": f"onboarding_skip:{step}"}]]}
                url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
                payload = {
                    "chat_id": chat_id,
                    "text": short_msg,
                    "reply_markup": markup
                }
                background_tasks.add_task(http_client.post, url, json=payload)
                return {"status": "ok", "detail": "onboarding_input_too_short"}
                
            # Queue onboarding task
            import uuid
            import structlog
            correlation_id = structlog.contextvars.get_contextvars().get("correlation_id") or str(uuid.uuid4())
            task = {
                "update_id": update_id_str,
                "chat_id": chat_id,
                "content_type": "text",
                "text": text_content,
                "is_onboarding": True,
                "onboarding_step": step,
                "message_id": message.get("message_id"),
                "correlation_id": correlation_id
            }
            background_tasks.add_task(redis.lpush, "atrium:tasks", json.dumps(task))
            
            ack_msg = "Got it! Summarizing and adding to your graph..."
            background_tasks.add_task(send_telegram_ack, chat_id, ack_msg, None, message.get("message_id"))
            return {"status": "ok", "detail": "onboarding_task_queued"}

        # 6.5 Check for custom timezone offset text reply
        if content_type == "text" and text_content:
            is_pending_tz = await redis.get(f"pending_timezone:{chat_id}")
            if is_pending_tz:
                await redis.delete(f"pending_timezone:{chat_id}")
                cleaned_val = text_content.strip()
                if cleaned_val.lower() == "cancel":
                    background_tasks.add_task(send_onboarding_settings_card, chat_id, user_id, "", base_url)
                    return {"status": "ok", "detail": "timezone_setup_cancelled"}
                
                try:
                    parse_val = cleaned_val
                    if parse_val.startswith("+"):
                        parse_val = parse_val[1:]
                    hours = float(parse_val)
                    if -12.0 <= hours <= 14.0:
                        offset_minutes = int(hours * 60)
                        async with db.cursor() as cur:
                            await cur.execute(
                                "UPDATE users SET timezone_offset = %s WHERE id = %s;",
                                (offset_minutes, user_id)
                            )
                            await db.commit()
                        
                        sign = "+" if offset_minutes >= 0 else "-"
                        h_abs = abs(offset_minutes) // 60
                        m_abs = abs(offset_minutes) % 60
                        tz_str = f"GMT{sign}{h_abs:02d}:{m_abs:02d}"
                        status_banner = f"✅ *Timezone configured successfully to {tz_str}!*"
                        background_tasks.add_task(send_onboarding_settings_card, chat_id, user_id, status_banner, base_url)
                        return {"status": "ok", "detail": "custom_timezone_set"}
                except ValueError:
                    pass
                
                await redis.setex(f"pending_timezone:{chat_id}", 300, "1")
                err_msg = "⚠️ I couldn't parse that. Please reply with a valid number like `+5.5`, `-8`, or `+0`. Type `cancel` to go back."
                url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
                background_tasks.add_task(http_client.post, url, json={
                    "chat_id": chat_id,
                    "text": err_msg,
                    "parse_mode": "Markdown",
                    "reply_markup": {
                        "inline_keyboard": [
                            [{"text": "« Cancel", "callback_data": "onboarding_tz_back"}]
                        ]
                    }
                })
                return {"status": "ok", "detail": "custom_timezone_invalid"}

        # 6.8 Check for pending self-description reply
        if content_type == "text" and text_content:
            is_pending_sd = await redis.get(f"pending_self_description:{chat_id}")
            if is_pending_sd:
                await redis.delete(f"pending_self_description:{chat_id}")
                async with db.cursor() as cur:
                    await cur.execute(
                        "UPDATE users SET self_description = %s WHERE id = %s;",
                        (text_content.strip(), user_id)
                    )
                    await db.commit()
                # Send confirmation
                url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
                background_tasks.add_task(http_client.post, url, json={
                    "chat_id": chat_id,
                    "text": "Got it! Your stated interests have been saved to your profile. ✓",
                    "parse_mode": "Markdown"
                })
                return {"status": "ok", "detail": "self_description_saved"}

        # 7. Check for pending context note capture (steady state only)
        if content_type == "text" and text_content:
            pending_item_id = await redis.get(f"pending_context:{chat_id}")
            if pending_item_id:
                await redis.delete(f"pending_context:{chat_id}")
                background_tasks.add_task(
                    save_context_note,
                    int(pending_item_id),
                    user_id,
                    text_content,
                    chat_id
                )
                return {"status": "ok", "detail": "context_note_capture_triggered"}

        # 7.5 Check for Conversational Graph RAG Query (steady state only)
        if content_type == "text" and text_content:
            is_question = False
            cleaned_text = text_content.strip()
            if cleaned_text.endswith("?"):
                is_question = True
            else:
                question_words = ("who", "what", "where", "when", "why", "how", "can", "is", "are", "do", "does", "did", "would", "could", "should", "will", "tell me", "explain")
                lower_text = cleaned_text.lower()
                if any(lower_text.startswith(word + " ") or lower_text.startswith(word + "?") for word in question_words):
                    is_question = True
            
            if is_question:
                pending_ctx = await redis.get(f"pending_context:{chat_id}")
                if not pending_ctx:
                    background_tasks.add_task(
                        handle_conversational_rag,
                        chat_id,
                        user_id,
                        text_content,
                        db,
                        message.get("message_id")
                    )
                    return {"status": "ok", "detail": "conversational_rag_triggered"}

        # 8. Steady-state Batch Debouncing
        if content_type != "unsupported":
            item_payload = {
                "update_id": update_id_str,
                "content_type": content_type,
                "text": text_content,
                "file_id": file_id,
                "timestamp": time.time(),
                "message_id": message.get("message_id")
            }
            # Add payload and update last active time in Redis atomically via pipeline
            expected_time = str(time.time())
            pipeline_res = await redis.pipeline([
                ["RPUSH", f"batch:{chat_id}", json.dumps(item_payload)],
                ["SETEX", f"batch_last:{chat_id}", "60", expected_time]
            ])
            batch_len = int(pipeline_res[0])
            
            background_tasks.add_task(wait_and_process_batch, chat_id, user_id, expected_time)
            
            # Send immediate ACK only for the first item in the batch
            if batch_len == 1:
                ack_message = ACK_MESSAGES.get(content_type, ACK_MESSAGES["unsupported"])
                background_tasks.add_task(send_telegram_ack, chat_id, ack_message, None, message.get("message_id"))
                
            logger.info("Queued item in debounce batch for chat_id %s, batch_size=%d", chat_id, batch_len)
        else:
            unsupported_msg = ACK_MESSAGES["unsupported"]
            background_tasks.add_task(send_telegram_ack, chat_id, unsupported_msg, None, message.get("message_id"))
            logger.info("Skipped queue for unsupported content type on update_id=%s, chat_id=%s", update_id_str, chat_id)
        
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


# ---------------------------------------------------------------------------
# Telegram Button Callback Query Helper Functions (Executed in Background)
# ---------------------------------------------------------------------------

async def process_quiz_me_callback(chat_id: str, user_id: int, item_id: int, callback_query_id: str):
    from backend.db.connection import _pool
    if not _pool:
        logger.error("DB pool is not initialised in process_quiz_me_callback.")
        return

    # Acknowledge callback query
    url_ans = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    try:
        await http_client.post(url_ans, json={"callback_query_id": callback_query_id})
    except Exception as e:
        logger.warning("Failed to answer callback query: %s", e)

    try:
        async with _pool.connection() as conn:
            if hasattr(conn, "execute"):
                await conn.execute("SET statement_timeout = '30s'")
            async with conn.cursor() as cur:
                # 1. Check if quiz already exists
                await cur.execute(
                    "SELECT id, question, options, correct_index, explanation FROM quizzes WHERE item_id = %s AND user_id = %s LIMIT 1;",
                    (item_id, user_id)
                )
                row = await cur.fetchone()

                if not row:
                    # 2. Fetch the item's summary / content to generate quiz
                    await cur.execute(
                        "SELECT source_type, raw_text, summary, title FROM items WHERE id = %s AND user_id = %s;",
                        (item_id, user_id)
                    )
                    item_row = await cur.fetchone()
                    if not item_row:
                        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
                        await http_client.post(url, json={"chat_id": chat_id, "text": "Item not found."})
                        return

                    source_type, raw_text, summary, title = item_row
                    from backend.services.encryption import decrypt
                    if raw_text:
                        try:
                            text_content = decrypt(raw_text)
                        except Exception:
                            text_content = raw_text
                    else:
                        text_content = ""

                    text_for_quiz = summary or text_content or title or ""

                    # 3. Call AICascade to generate quiz
                    from backend.services.ai_cascade import AICascade, ai_cascade
                    cascade = AICascade()
                    try:
                        quiz_data = await cascade.generate_quiz(text_for_quiz)
                    except Exception as e:
                        logger.error("Failed to generate quiz via AICascade: %s", e)
                        quiz_data = None

                    if not quiz_data:
                        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
                        await http_client.post(url, json={"chat_id": chat_id, "text": "Sorry, I couldn't generate a quiz question for this item. Please try again."})
                        return

                    # 4. Insert the new quiz
                    await cur.execute(
                        """
                        INSERT INTO quizzes (user_id, item_id, question, options, correct_index, explanation)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id, question, options, correct_index, explanation;
                        """,
                        (
                            user_id,
                            item_id,
                            quiz_data["question"],
                            json.dumps(quiz_data["options"]),
                            quiz_data["correct_index"],
                            quiz_data["explanation"]
                        )
                    )
                    row = await cur.fetchone()
                    await conn.commit()

        # 5. Format and send the quiz
        quiz_id, question, options_val, correct_index, explanation = row
        if isinstance(options_val, str):
            opts = json.loads(options_val)
        else:
            opts = options_val

        inline_keyboard = [
            [{"text": f"A. {opts[0]}", "callback_data": f"quiz:{quiz_id}:0"}],
            [{"text": f"B. {opts[1]}", "callback_data": f"quiz:{quiz_id}:1"}],
            [{"text": f"C. {opts[2]}", "callback_data": f"quiz:{quiz_id}:2"}],
            [{"text": f"D. {opts[3]}", "callback_data": f"quiz:{quiz_id}:3"}]
        ]

        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": f"<b>{question}</b>",
            "parse_mode": "HTML",
            "reply_markup": {
                "inline_keyboard": inline_keyboard
            }
        }
        await http_client.post(url, json=payload)
    except Exception as e:
        logger.exception("Error in process_quiz_me_callback: %s", e)
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        await http_client.post(url, json={"chat_id": chat_id, "text": "An error occurred while processing your quiz request."})


async def process_remind_me_callback(chat_id: str, user_id: int, item_id: int, callback_query_id: str):
    # Acknowledge callback query
    url_ans = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    try:
        await http_client.post(url_ans, json={"callback_query_id": callback_query_id})
    except Exception as e:
        logger.warning("Failed to answer callback query: %s", e)

    inline_keyboard = [
        [
            {"text": "⏰ In 1 Hour", "callback_data": f"remind_set:{item_id}:1h"},
            {"text": "⏰ In 3 Hours", "callback_data": f"remind_set:{item_id}:3h"}
        ],
        [
            {"text": "🌅 Tomorrow Morning", "callback_data": f"remind_set:{item_id}:tomorrow"},
            {"text": "📅 Next Week", "callback_data": f"remind_set:{item_id}:next_week"}
        ]
    ]

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": "Select when you would like to be reminded:",
        "reply_markup": {
            "inline_keyboard": inline_keyboard
        }
    }
    try:
        await http_client.post(url, json=payload)
    except Exception as e:
        logger.error("Failed to send reminder duration choices: %s", e)


async def process_remind_set_callback(
    chat_id: str,
    user_id: int,
    item_id: int,
    interval: str,
    callback_query_id: str,
    message_id: int
):
    from backend.db.connection import _pool
    if not _pool:
        logger.error("DB pool is not initialised in process_remind_set_callback.")
        return

    try:
        async with _pool.connection() as conn:
            if hasattr(conn, "execute"):
                await conn.execute("SET statement_timeout = '30s'")
            async with conn.cursor() as cur:
                # 1. Fetch timezone offset
                await cur.execute("SELECT timezone_offset FROM users WHERE id = %s;", (user_id,))
                row = await cur.fetchone()
                timezone_offset = row[0] if (row and row[0] is not None) else 0

                # 2. Fetch item title
                await cur.execute("SELECT title FROM items WHERE id = %s AND user_id = %s;", (item_id, user_id))
                item_row = await cur.fetchone()
                item_title = item_row[0] or "Saved Item" if item_row else "Saved Item"

        # 3. Calculate reminder time in UTC
        utc_now = datetime.now(timezone.utc)
        if interval == "1h":
            remind_at_utc = utc_now + timedelta(hours=1)
        elif interval == "3h":
            remind_at_utc = utc_now + timedelta(hours=3)
        else:
            user_local = utc_now + timedelta(minutes=timezone_offset)
            if interval == "tomorrow":
                target_date = user_local.date() + timedelta(days=1)
                target_local_dt = datetime.combine(target_date, dt_time(9, 0))
            elif interval == "next_week":
                target_date = user_local.date() + timedelta(days=7)
                target_local_dt = datetime.combine(target_date, dt_time(9, 0))
            else:
                remind_at_utc = utc_now + timedelta(hours=1)
                
            remind_at_utc = target_local_dt - timedelta(minutes=timezone_offset)
            remind_at_utc = remind_at_utc.replace(tzinfo=timezone.utc)

        # 4. Create and save the reminder
        message = f"Review Item: {item_title}\nRetrieve: /file_{item_id}"
        from backend.services.reminder_service import create_reminder
        
        async with _pool.connection() as conn:
            reminder_id, final_message, was_truncated = await create_reminder(
                user_id, message, remind_at_utc, conn, item_id=item_id
            )
            await conn.commit()

        user_local_target = remind_at_utc + timedelta(minutes=timezone_offset)
        formatted_dt = user_local_target.strftime("%d %b %Y at %H:%M")
        confirm_text = f"⏰ Reminder set for item '{item_title}' on {formatted_dt} ✓"

        # 5. Edit selection message to confirm
        url_ans = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
        await http_client.post(url_ans, json={"callback_query_id": callback_query_id, "text": "Reminder set! ⏰"})

        url_edit = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/editMessageText"
        payload_edit = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": confirm_text,
            "reply_markup": {"inline_keyboard": []}
        }
        await http_client.post(url_edit, json=payload_edit)
    except Exception as e:
        logger.error("Failed to set callback reminder: %s", e)
        url_ans = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
        await http_client.post(url_ans, json={"callback_query_id": callback_query_id})
        
        url_edit = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/editMessageText"
        payload_edit = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": "❌ Failed to set reminder. Please try again.",
            "reply_markup": {"inline_keyboard": []}
        }
        await http_client.post(url_edit, json=payload_edit)


# ---------------------------------------------------------------------------
# Phase 1 Conversational Onboarding & Debouncing Helper Functions
# ---------------------------------------------------------------------------

async def advance_onboarding_step(chat_id: str, user_id: int, current_step: int, db: psycopg.AsyncConnection, background_tasks: Optional[BackgroundTasks] = None, base_url: str = ""):
    next_step = current_step + 1
    if next_step <= 3:
        await redis.setex(f"onboarding_step:{chat_id}", 86400, str(next_step))
        if next_step == 2:
            msg = "Question 2/3: What is a hobby or technical topic you are obsessed with right now?\n\n(Click 'Skip' if you don't want to answer)"
            markup = {"inline_keyboard": [[{"text": "Skip Question ⏭️", "callback_data": "onboarding_skip:2"}]]}
        else: # next_step == 3
            msg = "Question 3/3: What is a problem or project you are currently working on at work or in life?\n\n(Click 'Skip' if you don't want to answer)"
            markup = {"inline_keyboard": [[{"text": "Skip Question ⏭️", "callback_data": "onboarding_skip:3"}]]}
            
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": msg,
            "reply_markup": markup
        }
        await http_client.post(url, json=payload)
    else:
        # Completed onboarding!
        await redis.delete(f"onboarding_step:{chat_id}")
        async with db.cursor() as cur:
            await cur.execute("UPDATE users SET initial_onboarding_completed = TRUE WHERE id = %s;", (user_id,))
            await db.commit()
            
        if background_tasks:
            background_tasks.add_task(trigger_first_session_magic, chat_id, user_id, base_url)
        else:
            await trigger_first_session_magic(chat_id, user_id, base_url)


async def get_onboarding_settings_payload(chat_id: str, user_id: int, status_banner: str = "", base_url: str = ""):
    from backend.db.connection import _pool
    
    google_refresh_token = None
    google_last_sync = None
    timezone_offset = 0
    
    if _pool:
        try:
            async with _pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT google_refresh_token, google_last_sync, timezone_offset FROM users WHERE id = %s;", (user_id,))
                    row = await cur.fetchone()
                    if row:
                        google_refresh_token, google_last_sync, timezone_offset = row
        except Exception as db_err:
            logger.error("Failed to query user drive status in settings card: %s", db_err)

    is_connected = google_refresh_token is not None
    
    sign = "+" if timezone_offset >= 0 else "-"
    h_abs = abs(timezone_offset) // 60
    m_abs = abs(timezone_offset) % 60
    tz_str = f"GMT{sign}{h_abs:02d}:{m_abs:02d}"

    backup_url = f"{settings.VITE_API_URL or 'http://localhost:8000'}/api/auth/google?chat_id={chat_id}"
    if base_url:
        backup_url = f"{base_url}/api/auth/google?chat_id={chat_id}"
        
    dashboard_url = settings.WEBSITE_URL

    # Always rewrite localhost and 127.0.0.1 to lvh.me so Telegram Bot API allows loopbacks in inline keyboard buttons
    backup_url = backup_url.replace("localhost", "lvh.me").replace("127.0.0.1", "lvh.me")
    dashboard_url = dashboard_url.replace("localhost", "lvh.me").replace("127.0.0.1", "lvh.me")

    settings_msg = (
        f"{status_banner}\n"
        "⚙️ *Setup & Settings*\n\n"
        "Onboarding complete! To get the most out of Recall, let's configure your settings:\n\n"
        f"1. **Timezone**: {tz_str} (Ensures digests and reminders arrive at the correct local hour).\n"
        f"2. **Web Dashboard**: Access your interactive 3D mind-graph.\n"
    )
    
    if is_connected:
        sync_time_str = ""
        if google_last_sync:
            sync_time_str = f" (Last sync: {google_last_sync.strftime('%d %b %H:%M')})"
        settings_msg += f"3. **Google Drive**: Connected ✅{sync_time_str}"
    else:
        settings_msg += "3. **Google Drive**: Secure automated daily backups of your saved items."

    inline_keyboard = [
        [{"text": "Set Timezone ⏰", "callback_data": "onboarding_tz_menu"}],
        [{"text": "Web Dashboard 🌐", "url": dashboard_url}]
    ]

    if is_connected:
        inline_keyboard.append([
            {"text": "Sync Drive Now 🔄", "callback_data": f"onboarding_drive_sync:{base_url}"},
            {"text": "Disconnect Drive 🔌", "callback_data": f"onboarding_drive_disconnect:{base_url}"}
        ])
    else:
        inline_keyboard.append([{"text": "Backup to Drive 💾", "url": backup_url}])

    settings_msg = settings_msg.strip()
    markup = {"inline_keyboard": inline_keyboard}
    return settings_msg, markup


async def send_onboarding_settings_card(chat_id: str, user_id: int, status_banner: str = "", base_url: str = ""):
    settings_msg, markup = await get_onboarding_settings_payload(chat_id, user_id, status_banner, base_url)
    
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": settings_msg,
        "parse_mode": "Markdown",
        "reply_markup": markup
    }
    
    await http_client.post(url, json=payload)


async def background_drive_sync(user_id: int, chat_id: str, base_url: str = ""):
    from backend.db.connection import _pool
    from backend.services.drive_sync import sync_user_to_drive
    try:
        if _pool:
            async with _pool.connection() as conn:
                await sync_user_to_drive(user_id, conn)
            
            # Send completion message and refresh settings card
            url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": "✅ *Google Drive backup sync completed successfully!*"
            }
            await http_client.post(url, json=payload)
                
            await send_onboarding_settings_card(chat_id, user_id, base_url=base_url)
    except Exception as e:
        logger.error("Background drive sync failed for user %d: %s", user_id, e)
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": "⚠️ *Google Drive backup sync failed. Please try again later.*"
        }
        await http_client.post(url, json=payload)


async def trigger_first_session_magic(chat_id: str, user_id: int, base_url: str = ""):
    # Send a completion message first
    complete_msg = "🎉 Onboarding complete! Your starting mind-graph has been seeded.\n\nRunning first-session scan..."
    await send_telegram_ack(chat_id, complete_msg)
    
    from backend.db.connection import _pool
    if not _pool:
        return
    try:
        async with _pool.connection() as conn:
            async with conn.cursor() as cur:
                # Get the 3 items
                await cur.execute(
                    "SELECT id, title, summary, tags, context_note, passive_context FROM items WHERE user_id = %s ORDER BY created_at DESC LIMIT 3;",
                    (user_id,)
                )
                rows = await cur.fetchall()
                
        if len(rows) < 2:
            seed_msg = (
                "Your graph is seeded! Start forwarding links, audio, or PDFs to grow it.\n\n"
                "💡 <b>We also support screenshots!</b> You can send us screenshots of your <b>WhatsApp Saved Messages</b> (or chats containing links), and we will automatically scrape, clean, and save them for you!"
            )
            await send_telegram_ack(chat_id, seed_msg, "HTML")
            await send_onboarding_settings_card(chat_id, user_id, base_url=base_url)
            return
            
        best_pair = None
        best_sim = 0.0
        
        async with _pool.connection() as conn:
            async with conn.cursor() as cur:
                for i in range(len(rows)):
                    for j in range(i+1, len(rows)):
                        id1, t1, s1, tg1, cn1, pc1 = rows[i]
                        id2, t2, s2, tg2, cn2, pc2 = rows[j]
                        await cur.execute(
                            "SELECT 1 - (embedding <=> (SELECT embedding FROM items WHERE id = %s)) FROM items WHERE id = %s;",
                            (id2, id1)
                        )
                        sim_row = await cur.fetchone()
                        sim = sim_row[0] if (sim_row and sim_row[0] is not None) else 0.0
                        if sim > best_sim:
                            best_sim = sim
                            best_pair = (rows[i], rows[j])
                            
        if best_pair and best_sim >= 0.68:
            item_a, item_b = best_pair
            
            from backend.services.ai_cascade import AICascade, ai_cascade
            cascade = AICascade()
            cascade._force_production_llm = True
            
            dict_a = {"title": item_a[1], "summary": item_a[2], "tags": item_a[3], "context_note": item_a[4], "passive_context": item_a[5]}
            dict_b = {"title": item_b[1], "summary": item_b[2], "tags": item_b[3], "context_note": item_b[4], "passive_context": item_b[5]}
            
            insight = await cascade.generate_insight(dict_a, dict_b, 1)
            if insight:
                await send_telegram_ack(chat_id, "🔍 Scan complete: I found a connection between your seed topics!")
                msg = f"💡 **Recall Connection**:\n\n{insight}"
                await send_telegram_ack(chat_id, msg)
            else:
                scan_complete_msg = (
                    "Scan complete! No strong conceptual connections found yet, but they are saved. Forward me more links to find deeper connections!\n\n"
                    "💡 <b>We also support screenshots!</b> You can send us screenshots of your <b>WhatsApp Saved Messages</b> (or chats containing links), and we will automatically scrape, clean, and save them for you!"
                )
                await send_telegram_ack(chat_id, scan_complete_msg, "HTML")
        else:
            scan_complete_msg = (
                "Scan complete! No strong conceptual connections found yet, but they are saved. Forward me more links to find deeper connections!\n\n"
                "💡 <b>We also support screenshots!</b> You can send us screenshots of your <b>WhatsApp Saved Messages</b> (or chats containing links), and we will automatically scrape, clean, and save them for you!"
            )
            await send_telegram_ack(chat_id, scan_complete_msg, "HTML")
            
        await send_onboarding_settings_card(chat_id, user_id, base_url=base_url)
    except Exception as e:
        logger.error("First session magic failed: %s", e)


async def save_context_note(item_id: int, user_id: int, note_text: str, chat_id: str):
    from backend.db.connection import _pool
    from backend.services.redis_client import redis
    if not _pool:
        logger.error("DB pool not initialized in save_context_note")
        return
    try:
        # 1. Reset ignore count since they replied
        await redis.delete(f"context_prompt:ignore_count:{chat_id}")
        
        # 2. Fetch and delete the pending mood variant name
        variant_name = await redis.get(f"pending_context_variant:{chat_id}")
        if variant_name:
            await redis.delete(f"pending_context_variant:{chat_id}")
            reply_len = len(note_text)
            await redis._request("", ["HINCRBY", f"context_prompt:scores:{chat_id}", variant_name, str(reply_len)])
            
        async with _pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE items SET context_note = %s WHERE id = %s AND user_id = %s;",
                    (note_text.strip(), item_id, user_id)
                )
                await conn.commit()
        await send_telegram_ack(chat_id, "Got it, context note attached! ✓")
        logger.info("Saved context note for item_id %d, user_id %d", item_id, user_id)
    except Exception as e:
        logger.error("Failed to save context note: %s", e)


async def wait_and_process_batch(chat_id: str, user_id: int, expected_time: str):
    await asyncio.sleep(4.0)
    # Check if a newer message has arrived and reset the timer
    last_time = await redis.get(f"batch_last:{chat_id}")
    if last_time != expected_time:
        return

    # Fetch items and clean up the keys in Redis in a single pipelined request
    pipeline_res = await redis.pipeline([
        ["LRANGE", f"batch:{chat_id}", "0", "-1"],
        ["DEL", f"batch:{chat_id}"],
        ["DEL", f"batch_last:{chat_id}"]
    ])
    raw_items = pipeline_res[0]

    if not raw_items:
        return

    items = [json.loads(x) for x in raw_items]
    
    import uuid
    import structlog
    correlation_id = structlog.contextvars.get_contextvars().get("correlation_id") or str(uuid.uuid4())
    batch_task = {
        "chat_id": chat_id,
        "user_id": user_id,
        "is_batch": True,
        "items": items,
        "correlation_id": correlation_id
    }
    
    await redis.lpush("atrium:tasks", json.dumps(batch_task))
    logger.info("Consolidated batch task of %d items queued for chat_id %s", len(items), chat_id)


async def handle_conversational_rag(
    chat_id: str,
    user_id: int,
    query: str,
    db: psycopg.AsyncConnection,
    reply_to_message_id: Optional[int] = None
):
    """
    Background worker task to retrieve RAG context, run the AI cascade,
    and reply to conversational question messages back on Telegram.
    """
    try:
        from backend.services.search_service import rag_semantic_search
        from backend.services.ai_cascade import AICascade, ai_cascade, check_prompt_injection

        # Check for query injection first
        injection_warning = check_prompt_injection(query)
        if injection_warning:
            await send_telegram_ack(
                chat_id,
                injection_warning,
                None,
                reply_to_message_id
            )
            return

        # 1. Retrieve context
        items = await rag_semantic_search(query, user_id, db, limit=12)

        if not items:
            await send_telegram_ack(
                chat_id,
                "Your graph is empty! Please save some links, PDFs, images, or voice notes first so I can understand your thinking.",
                None,
                reply_to_message_id
            )
            logger.info("Conversational query: user_id=%d query=%r query_type=conversational results=0", user_id, mask_pii(query))
            return

        # 2. Generate synthesized answer
        cascade = AICascade()
        answer = await cascade.answer_graph_question(query, items)

        if not answer:
            answer = "I couldn't analyze the graph for this question right now. Please try again later."

        # Log search query for analytics
        logger.info(
            "Conversational query: user_id=%d, query=%r, answer=%r",
            user_id,
            mask_pii(query),
            mask_pii(answer),
            extra={"query_type": "conversational"}
        )

        # 3. Send message back to user via Telegram safely using HTML parse mode
        import html
        import re
        escaped_answer = html.escape(answer)
        # Convert any markdown bold (*text*) to HTML bold (<b>text</b>)
        formatted_answer = re.sub(r'\*(.*?)\*', r'<b>\1</b>', escaped_answer)

        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": formatted_answer,
            "parse_mode": "HTML"
        }
        if reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id
        resp = await http_client.post(url, json=payload)
        resp.raise_for_status()

    except Exception as e:
        logger.error("Failed to execute conversational RAG: %s", e)
        try:
            await send_telegram_ack(
                chat_id,
                "Sorry, I ran into an error while checking your graph. Please try again.",
                None,
                reply_to_message_id
            )
        except Exception:
            pass


async def process_quiz_answer_db_and_ui(
    chat_id: str,
    user_id: int,
    quiz_id: int,
    selected_idx: int,
    is_correct: bool,
    ease_factor: float,
    interval_days: int,
    correct_index: int,
    explanation: str,
    options: Any,
    message_id: int
):
    from backend.services.sm2 import update_sm2
    from datetime import date, timedelta
    import httpx
    import json
    import backend.db.connection as db_conn
    
    quality = 5 if is_correct else 2
    new_ef, new_interval = update_sm2(ease_factor, interval_days, quality)
    new_next_review = date.today() + timedelta(days=new_interval)
    
    try:
        conn_ctx = await db_conn.get_background_db_connection()
        async with conn_ctx as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE quizzes
                    SET ease_factor = %s,
                        interval_days = %s,
                        next_review = %s
                    WHERE id = %s;
                    """,
                    (new_ef, new_interval, new_next_review, quiz_id)
                )
                await cur.execute(
                    """
                    INSERT INTO quiz_answers (user_id, quiz_id, quality)
                    VALUES (%s, %s, %s);
                    """,
                    (user_id, quiz_id, quality)
                )
                await conn.commit()
                    
        if isinstance(options, str):
            opts = json.loads(options)
        else:
            opts = options
            
        correct_option = opts[correct_index] if 0 <= correct_index < len(opts) else ""
        explanation_text = explanation or ""
        
        if is_correct:
            result_text = f"✅ Correct!\n\n{explanation_text}\n\nNext review: {new_next_review.strftime('%Y-%m-%d')}"
        else:
            result_text = f"❌ The answer was {correct_option}\n\n{explanation_text}\n\nReview again in 1 day."
            
        url_edit = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/editMessageText"
        payload_edit = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": result_text,
            "parse_mode": "HTML",
            "reply_markup": {
                "inline_keyboard": [
                    [{"text": "Next Quiz →", "callback_data": "quiz:next"}]
                ]
            }
        }
        await http_client.post(url_edit, json=payload_edit)
            
    except Exception as e:
        logger.error("Failed to save quiz answer for quiz_id %d in background: %s", quiz_id, e)


async def process_candidate_confirm_background(cand_id: int, user_id: int, chat_id: str, message_id: int, orig_text: str):
    import backend.db.connection as db_conn
    try:
        conn_ctx = await db_conn.get_background_db_connection()
        async with conn_ctx as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE insight_candidates SET status = 'confirmed', expires_at = NULL WHERE id = %s AND user_id = %s;",
                    (cand_id, user_id)
                )
                await conn.commit()
        await redis.zrem("reminders:active", f"drift:{cand_id}")
        
        clean_text = orig_text.split("💡")[0].strip()
        confirm_msg = f"{clean_text}\n\n🔗 *Connection saved permanently to your Mind Map!* ✓"
        
        url_edit = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/editMessageText"
        await http_client.post(url_edit, json={
            "chat_id": chat_id,
            "message_id": message_id,
            "text": confirm_msg,
            "parse_mode": "Markdown"
        })
    except Exception as e:
        logger.error("Failed to process candidate confirm in background for candidate %d: %s", cand_id, e)


async def process_candidate_drift_background(cand_id: int, user_id: int, chat_id: str, message_id: int, orig_text: str):
    import backend.db.connection as db_conn
    try:
        conn_ctx = await db_conn.get_background_db_connection()
        async with conn_ctx as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE insight_candidates SET status = 'expired' WHERE id = %s AND user_id = %s;",
                    (cand_id, user_id)
                )
                await conn.commit()
        await redis.zrem("reminders:active", f"drift:{cand_id}")
        
        clean_text = orig_text.split("💡")[0].strip()
        drift_msg = f"{clean_text}\n\n💨 *Connection dissolved (let it drift).* ✓"
        
        url_edit = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/editMessageText"
        await http_client.post(url_edit, json={
            "chat_id": chat_id,
            "message_id": message_id,
            "text": drift_msg,
            "parse_mode": "Markdown"
        })
    except Exception as e:
        logger.error("Failed to process candidate drift in background for candidate %d: %s", cand_id, e)


async def process_timezone_set_background(offset_minutes: int, user_id: int, chat_id: str, message_id: int, base_url: str):
    import backend.db.connection as db_conn
    try:
        conn_ctx = await db_conn.get_background_db_connection()
        async with conn_ctx as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE users SET timezone_offset = %s WHERE id = %s;",
                    (offset_minutes, user_id)
                )
                await conn.commit()
                
        sign = "+" if offset_minutes >= 0 else "-"
        hours = abs(offset_minutes) // 60
        mins = abs(offset_minutes) % 60
        tz_str = f"GMT{sign}{hours:02d}:{mins:02d}"
        status_banner = f"✅ *Timezone configured successfully to {tz_str}!*"
        
        settings_msg, markup = await get_onboarding_settings_payload(chat_id, user_id, status_banner, base_url)
        url_edit = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/editMessageText"
        payload_edit = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": settings_msg,
            "parse_mode": "Markdown",
            "reply_markup": markup
        }
        await http_client.post(url_edit, json=payload_edit)
    except Exception as e:
        logger.error("Failed to process timezone set in background for user %d: %s", user_id, e)


async def process_drive_disconnect_background(user_id: int, chat_id: str, message_id: int, cb_base_url: str):
    import backend.db.connection as db_conn
    try:
        google_refresh_token = None
        conn_ctx = await db_conn.get_background_db_connection()
        async with conn_ctx as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT google_refresh_token FROM users WHERE id = %s;",
                    (user_id,)
                )
                row = await cur.fetchone()
                google_refresh_token = row[0] if row else None

            if google_refresh_token:
                from backend.services.encryption import decrypt
                try:
                    decrypted_token = decrypt(google_refresh_token)
                except Exception:
                    decrypted_token = None

                if decrypted_token:
                    try:
                        url_revoke = f"https://oauth2.googleapis.com/revoke?token={decrypted_token}"
                        await http_client.post(url_revoke)
                    except Exception as e:
                        logger.error("Google token revoke failed: %s", e)

                async with conn.cursor() as cur:
                    await cur.execute(
                        "UPDATE users SET google_refresh_token = NULL, google_last_sync = NULL WHERE id = %s;",
                        (user_id,)
                    )
                    await conn.commit()

        settings_msg, markup = await get_onboarding_settings_payload(chat_id, user_id, "🔌 *Google Drive disconnected successfully.*", cb_base_url)
        url_edit = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/editMessageText"
        payload_edit = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": settings_msg,
            "parse_mode": "Markdown",
            "reply_markup": markup
        }
        await http_client.post(url_edit, json=payload_edit)
    except Exception as e:
        logger.error("Failed to process drive disconnect in background for user %d: %s", user_id, e)


async def process_onboarding_opt_background(note_text: str, item_id: int, user_id: int):
    import backend.db.connection as db_conn
    try:
        conn_ctx = await db_conn.get_background_db_connection()
        async with conn_ctx as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE items SET context_note = %s WHERE id = %s AND user_id = %s;",
                    (note_text, item_id, user_id)
                )
                await conn.commit()
    except Exception as e:
        logger.error("Failed to process onboarding option save in background for user %d: %s", user_id, e)



