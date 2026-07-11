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
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Union

from backend.config import settings
from backend.exceptions import DuplicateItemException
import backend.db.connection as db_conn
from backend.services.user_service import upsert_user
from backend.services.redis_client import redis
from backend.services.dlq import write_to_dlq, send_failure_message
from backend.services.encryption import encrypt, decrypt
from backend.services.search_service import embed_text
from backend.services.ai_cascade import AICascade, ai_cascade, current_mood_var

# Ingesters
from backend.services.pdf_ingester import ingest_pdf
from backend.services.url_ingester import ingest_url
from backend.services.voice_ingester import ingest_voice
from backend.services.image_ingester import ingest_image

logger = logging.getLogger(__name__)

# Concurrency semaphore (initialized lazily inside the event loop)
worker_semaphore = None

async def get_next_mood_category(chat_id: str) -> str:
    all_moods = ["curiosity", "timing", "future", "friction", "identity", "connection", "stakes", "surprise"]
    
    try:
        # 1. Fetch variant history
        history_resp = await redis._request("", ["LRANGE", f"context_prompt:history:{chat_id}", "0", "-1"])
        history = []
        if isinstance(history_resp, dict) and isinstance(history_resp.get("result"), list):
            history = history_resp["result"]
        elif isinstance(history_resp, list):
            history = history_resp
            
        # Filter eligible moods (not in history)
        eligible = [m for m in all_moods if m not in history]
        if not eligible:
            eligible = all_moods
            
        # 2. Get scores from Redis hash
        scores_resp = await redis._request("", ["HGETALL", f"context_prompt:scores:{chat_id}"])
        scores_list = []
        if isinstance(scores_resp, dict) and isinstance(scores_resp.get("result"), list):
            scores_list = scores_resp["result"]
        elif isinstance(scores_resp, list):
            scores_list = scores_resp
            
        scores = {}
        if isinstance(scores_list, list):
            for idx in range(0, len(scores_list), 2):
                if idx + 1 < len(scores_list):
                    k = scores_list[idx]
                    try:
                        v = int(scores_list[idx+1])
                    except ValueError:
                        v = 0
                    scores[k] = v
                    
        # 3. Select next mood using epsilon-greedy (70% best, 30% explore)
        import random
        if random.random() < 0.7:
            best_mood = eligible[0]
            best_val = scores.get(best_mood, 0)
            for m in eligible:
                val = scores.get(m, 0)
                if val > best_val:
                    best_val = val
                    best_mood = m
            selected = best_mood
        else:
            selected = random.choice(eligible)
            
        # 4. Update history
        await redis._request("", ["LPUSH", f"context_prompt:history:{chat_id}", selected])
        await redis._request("", ["LTRIM", f"context_prompt:history:{chat_id}", "0", "3"])
        return selected
    except Exception as e:
        logger.error("Failed to determine next mood category: %s", e)
        import random
        return random.choice(all_moods)

async def send_context_prompt_with_checks(chat_id: str, user_id: int, item_id: int, context_prompt: str, mood_category: Optional[str] = None):
    try:
        # 1. Check if paused
        pause_val_str = await redis.get(f"context_prompt:pause_saves:{chat_id}")
        if pause_val_str and pause_val_str.isdigit():
            pause_val = int(pause_val_str)
            if pause_val > 0:
                new_pause_val = pause_val - 1
                if new_pause_val <= 0:
                    await redis.delete(f"context_prompt:pause_saves:{chat_id}")
                else:
                    await redis.setex(f"context_prompt:pause_saves:{chat_id}", 86400, str(new_pause_val))
                logger.info("Context prompt is paused for user %d (remaining saves to skip: %d)", user_id, pause_val)
                return

        # 3. Deliver context prompt
        await send_telegram_message(chat_id, context_prompt)
        await redis.setex(f"pending_context:{chat_id}", 600, str(item_id))
        if mood_category:
            await redis.setex(f"pending_context_variant:{chat_id}", 600, mood_category)
            
    except Exception as err:
        logger.error("Failed to run context prompt check and dispatch: %s", err)

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

# Inline keyboard shown below every successfully saved item
def build_recall_keyboard(item_id: int) -> dict:
    """Build the inline keyboard for a successfully saved item."""
    website_url = settings.WEBSITE_URL
    # Telegram Bot API rejects 'localhost' or '127.0.0.1' URLs in inline buttons.
    # If using local dev without a tunnel, fall back to a mock public domain to prevent 400 Bad Request.
    if "localhost" in website_url or "127.0.0.1" in website_url:
        website_url = "https://recall-dev.example.com"
        
    return {
        "inline_keyboard": [[
            {"text": "Open in Recall", "url": f"{website_url}/archive?item={item_id}"},
            {"text": "Quiz Me", "callback_data": f"quiz_me:{item_id}"},
            {"text": "Remind Me", "callback_data": f"remind_me:{item_id}"},
        ]]
    }

# Divider used in intelligence-brief style messages
_DIVIDER = "\u2500\u2500 \u2500\u2500 \u2500\u2500 \u2500\u2500 \u2500\u2500"


def _truncate_summary(summary: str, max_chars: int = 3000) -> str:
    """Truncate summary to at most max_chars characters, breaking at a word boundary."""
    if len(summary) <= max_chars:
        return summary
    truncated = summary[:max_chars].rsplit(" ", 1)[0]
    return truncated.rstrip(".,;:") + "…"




def _format_tags(tags: list) -> str:
    """Return a space-separated tag string like '#tag1  #tag2  #tag3'."""
    if not tags:
        return ""
    return "  ".join(f"#{t}" for t in tags)


def _build_success_message(emoji_title: str, summary: str, tags: list) -> str:
    """
    Build the Phase-6 intelligence-brief success message:

        📄 filename.pdf

        Summary in one or two compact sentences.

        ── ── ── ── ──
        #tag1  #tag2  #tag3

        Saved.
    """
    summary_text = _truncate_summary(summary)
    tag_line = _format_tags(tags)
    parts = [emoji_title, "", summary_text, "", _DIVIDER]
    if tag_line:
        parts.append(tag_line)
    parts.append("")
    parts.append("Saved.")
    return "\n".join(parts)


async def send_telegram_message(
    chat_id: str,
    text: str,
    reply_markup: Optional[dict] = None,
    reply_to_message_id: Optional[int] = None
) -> Optional[int]:
    """Helper to send a message back to the Telegram chat. Returns message_id if successful."""
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    
    # 1. Escape HTML special characters
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    # 1.5 Clean up escaped backticks and convert markdown code blocks/inline code to HTML tags
    escaped = escaped.replace("\\`", "`")
    # Convert block code: ``` [lang] \n [code] \n ```
    escaped = re.sub(r'```(?:[a-zA-Z0-9_-]+)?\n?(.*?)\n?```', r'<pre><code>\1</code></pre>', escaped, flags=re.DOTALL)
    # Convert inline code: `code`
    escaped = re.sub(r'`(.*?)`', r'<code>\1</code>', escaped)
    
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
    
    # 3. Process line-by-line for headers, lists, italics, and title beautification
    lines = formatted.split("\n")
    if lines:
        # Beautify title line if it starts with an emoji
        first_line = lines[0]
        emojis = ("🎥 ", "📸 ", "📄 ", "🎙 ", "🖼 ", "🔗 ")
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
                
            # Convert Markdown italics (*text* or _text_) to <i>text</i> safely bypassing URLs
            urls = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', line)
            masked_line = line
            for idx_url, url_str in enumerate(urls):
                masked_line = masked_line.replace(url_str, f"TEMPURLPLACEHOLDER{idx_url}")
                
            masked_line = re.sub(r'\*(.*?)\*', r'<i>\1</i>', masked_line)
            masked_line = re.sub(r'((?:^|\s))_(?!_)(.+?)(?<!_)_(?=\s|$)', r'\1<i>\2</i>', masked_line)
            
            for idx_url, url_str in enumerate(urls):
                masked_line = masked_line.replace(f"TEMPURLPLACEHOLDER{idx_url}", url_str)
                
            lines[idx] = masked_line
            
    final_text = "\n".join(lines)
    
    payload: Dict[str, Any] = {
        "chat_id": str(chat_id),
        "text": final_text,
        "parse_mode": "HTML"
    }
    if reply_markup is not None:
        import json as _json
        payload["reply_markup"] = _json.dumps(reply_markup)
    if reply_to_message_id is not None:
        payload["reply_to_message_id"] = reply_to_message_id
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            logger.info("Sent Telegram message to chat_id %s", chat_id)
            return resp.json().get("result", {}).get("message_id")
    except Exception as e:
        logger.error("Failed to send Telegram message to chat_id %s: %s", chat_id, e)
        return None


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
        passive_ctx = await compute_passive_context(user_id, source_type, db)
        time_bucket = json.loads(passive_ctx).get("time_of_day")
        await cur.execute(
            "UPDATE items SET passive_context = %s, save_time_bucket = %s WHERE id = %s;",
            (passive_ctx, time_bucket, item_id)
        )
        await db.commit()
    return item_id

async def check_user_milestones(user_id: int, chat_id: str) -> None:
    """Checks the user's total node count and processes milestone unlocks and alerts."""
    try:
        async with db_conn._pool.connection() as conn:
            async with conn.cursor() as cur:
                # 1. Fetch total node count
                await cur.execute("SELECT COUNT(*) FROM items WHERE user_id = %s;", (user_id,))
                count_row = await cur.fetchone()
                node_count = count_row[0] if count_row else 0
                
                # 2. Fetch current unlocked milestones
                await cur.execute("SELECT node_milestones FROM users WHERE id = %s;", (user_id,))
                user_row = await cur.fetchone()
                milestones_dict = user_row[0] if user_row and user_row[0] else {"unlocked": []}
                if isinstance(milestones_dict, str):
                    try:
                        milestones_dict = json.loads(milestones_dict)
                    except Exception:
                        milestones_dict = {"unlocked": []}
                unlocked_list = milestones_dict.get("unlocked", [])
                
                MILESTONES = {
                    5: ("pattern_report", "First Pattern Report unlocks. \"Here is what your mind has been working on.\""),
                    15: ("mind_type", "Mind Type unlocks. Computed from graph structure, not a quiz. Check the Profile page on the dashboard to view your cognitive trajectory!"),
                    30: ("predictions", "Monthly Prediction activates. The graph is now deep enough to forecast your next areas of inquiry (first prediction arriving within 48 hours)."),
                    50: ("hearth", "Hearth unlocks. You can now pair with a friend and grow a shared Hearth space."),
                    100: ("ranked_pulse", "Pulse Score ranked status unlocks. See where you sit relative to density benchmarks."),
                    200: ("public_graph", "Public Graph unlocks. Share a read-only visual map of your mind with the world.")
                }
                
                for threshold, (feature_key, alert_suffix) in MILESTONES.items():
                    if node_count >= threshold and feature_key not in unlocked_list:
                        unlocked_list.append(feature_key)
                        await cur.execute(
                            "UPDATE users SET node_milestones = %s WHERE id = %s;",
                            (json.dumps({"unlocked": unlocked_list}), user_id)
                        )
                        await conn.commit()
                        
                        msg = f"Your graph just crossed {threshold} nodes. {alert_suffix}"
                        await send_telegram_message(chat_id, msg)
                        logger.info("User %d unlocked milestone %d (%s)", user_id, threshold, feature_key)
                        
                        if threshold == 5:
                            prompt_msg = (
                                "Your graph is starting to take shape! 🧠\n\n"
                                "In one sentence, *what do you think you're mostly interested in right now?*"
                            )
                            await redis.setex(f"pending_self_description:{chat_id}", 86400 * 7, "1")
                            await send_telegram_message(chat_id, prompt_msg)
                            logger.info("User %d prompted for self-description", user_id)
                            
                        if threshold == 15:
                            try:
                                await cur.execute("SELECT mind_type_summary FROM users WHERE id = %s;", (user_id,))
                                sum_row = await cur.fetchone()
                                if sum_row and sum_row[0]:
                                    logger.info("User %d already has a mind type summary, skipping instant generation", user_id)
                                    continue
                                    
                                from backend.scheduler.scheduler import run_nightly_mind_type_for_user
                                await run_nightly_mind_type_for_user(user_id, db_conn._pool)
                                
                                await cur.execute("SELECT mind_type FROM users WHERE id = %s;", (user_id,))
                                mt_row = await cur.fetchone()
                                code = mt_row[0] if mt_row else None
                                
                                if code:
                                    await cur.execute(
                                        "SELECT label FROM semantic_hubs WHERE user_id = %s ORDER BY array_length(member_ids, 1) DESC LIMIT 3;",
                                        (user_id,)
                                    )
                                    hubs = [r[0] for r in await cur.fetchall()]
                                    hubs_str = ", ".join(hubs) if hubs else "general topics"
                                    
                                    from backend.services.ai_cascade import ai_cascade
                                    cascade = ai_cascade
                                    prompt = (
                                        f"You are a Cognitive Graph Profiler. The user has been classified as {code} (MBTI-style Mind Type).\n"
                                        f"Their top 3 active clusters are: {hubs_str}.\n\n"
                                        f"Write a highly personalized, analytical, and engaging 4-sentence profile summary explaining their cognitive style based on these topics.\n"
                                        f"Constraint: Do not use clinical jargon, do not use template words, and connect the topics explicitly."
                                    )
                                    summary_text = await cascade.call_llm(prompt)
                                    if not summary_text or len(summary_text) < 10:
                                        summary_text = f"You are actively building a graph of ideas under {hubs_str}. Your current Mind Type is {code}."
                                        
                                    await cur.execute(
                                        "UPDATE users SET mind_type_summary = %s, mind_type_detailed = NULL WHERE id = %s;",
                                        (summary_text, user_id)
                                    )
                                    await conn.commit()
                                    
                                    ARCHETYPES = {
                                        "BLVN": "Polymath Explorer",
                                        "FISR": "Deep Specialist",
                                        "FLSR": "Master Synthesizer",
                                        "BIVN": "Dynamic Collector"
                                    }
                                    archetype_label = ARCHETYPES.get(code, "Mind Explorer")
                                    trajectory_alert = (
                                        f"Your active Mind Type is: *{archetype_label} ({code})*.\n\n"
                                        f"{summary_text}\n\n"
                                        f"Check the dashboard Profile page to see your metrics breakdown!"
                                    )
                                    await send_telegram_message(chat_id, trajectory_alert)
                                    logger.info("Generated initial Mind Type profile for user %d", user_id)
                            except Exception as init_err:
                                logger.error(
                                    "mind_type_profile_generation_failed",
                                    user_id=user_id,
                                    error=str(init_err),
                                    exc_info=True
                                )
    except Exception as milestone_err:
        logger.error(
            "milestone_check_failed",
            user_id=user_id,
            error=str(milestone_err),
            exc_info=True
        )


async def process_task(task: Dict[str, Any], task_json: Optional[str] = None, semaphore: Optional[asyncio.Semaphore] = None) -> None:
    """Processes a single task context. Semaphore slot is assumed to be acquired by caller if passed."""
    from structlog.contextvars import bind_contextvars, clear_contextvars
    chat_id = str(task.get("chat_id"))
    correlation_id = task.get("correlation_id") or str(uuid.uuid4())
    
    clear_contextvars()
    bind_contextvars(correlation_id=correlation_id, chat_id=chat_id)
    
    try:
        update_id = task.get("update_id")
        content_type = task.get("content_type")
        file_id = task.get("file_id")
        text_content = task.get("text")
        
        logger.info("Processing task: update_id=%s, type=%s", update_id, content_type)
        
        # Verify pool is open
        if db_conn._pool is None:
            logger.error("Database connection pool is not initialized.")
            return
            
        user_id = None
        
        try:
            # 1. Resolve user_id in a short, dedicated connection checkout
            async with db_conn._pool.connection() as conn:
                await conn.execute("SET statement_timeout = '30s'")
                user_id = await upsert_user(chat_id, conn)
                await conn.commit()
            
            bind_contextvars(correlation_id=correlation_id, chat_id=chat_id, user_id=user_id)

            # Check for previous ignore once before starting steady-state ingestion
            prev_pending = await redis.get(f"pending_context:{chat_id}")
            if prev_pending and isinstance(prev_pending, (str, bytes)):
                await redis.delete(f"pending_context:{chat_id}")
                await redis.delete(f"pending_context_variant:{chat_id}")
                
                ignore_count_resp = await redis._request("", ["INCR", f"context_prompt:ignore_count:{chat_id}"])
                ignore_count = 0
                if isinstance(ignore_count_resp, dict) and "result" in ignore_count_resp:
                    ignore_count = int(ignore_count_resp["result"] or 0)
                elif isinstance(ignore_count_resp, (int, str)):
                    ignore_count = int(ignore_count_resp)
                    
                if ignore_count >= 3:
                    await redis.setex(f"context_prompt:pause_saves:{chat_id}", 86400, "5")
                    await redis.delete(f"context_prompt:ignore_count:{chat_id}")
                    logger.info("User %d ignored context prompt 3 consecutive times. Paused for 5 saves.", user_id)

            # 2. Onboarding flow routing
            is_new = False
            if task.get("is_onboarding"):
                await process_onboarding_task(task, user_id, chat_id)
                is_new = True
            # 3. Batch flow routing
            elif task.get("is_batch"):
                is_new = await process_batch_task(task, user_id, chat_id)
            else:
                # 4. Standard single-item processing routing
                res = await process_single_item(task, user_id, chat_id, is_batch_item=False)
                if isinstance(res, tuple):
                    _, is_new = res
                else:
                    is_new = (res is not None)

            # Run milestone checks after successful item processing
            if is_new:
                await check_user_milestones(user_id, chat_id)

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

                    # If this task already came from the DLQ and failed again,
                    # discard it permanently — do NOT re-DLQ or re-notify the user.
                    # This prevents the infinite startup-requeue → fail → DLQ loop.
                    if task_payload.get("from_dlq"):
                        logger.warning(
                            "DLQ retry failed permanently for update_id=%s user=%s — discarding.",
                            update_id, user_id
                        )
                    else:
                        # Checkout a clean connection to guarantee write success even if primary timed out
                        async with db_conn._pool.connection() as fallback_conn:
                            await fallback_conn.execute("SET statement_timeout = '30s'")
                            await write_to_dlq(user_id, task_payload, error_message, fallback_conn)
                            await save_minimal_bookmark(user_id, content_type or "unknown", file_id, text_content, fallback_conn)
                            try:
                                from backend.services.streak_service import update_streak
                                await update_streak(user_id, fallback_conn)
                            except Exception as streak_err:
                                logger.error("Failed to update fallback user streak: %s", streak_err)
                            await fallback_conn.commit()
                            
                        await send_failure_message(chat_id, content_type or "unknown")
                except Exception as dlq_err:
                    logger.error("Failed to complete fallback DLQ/bookmark flow: %s", dlq_err)
    finally:
        if task_json:
            try:
                await redis.lrem("atrium:processing", 1, task_json)
            except Exception as clean_err:
                logger.error("Failed to clean task from processing queue: %s", clean_err)
        if semaphore is not None:
            semaphore.release()


async def process_onboarding_task(task: Dict[str, Any], user_id: int, chat_id: str) -> None:
    text_content = task.get("text")
    step = task.get("onboarding_step")
    
    cascade = AICascade()
    ai_res = await cascade.summarise(text_content, chat_id, task="onboarding")
    
    if ai_res == "INVALID_ONBOARDING_INPUT":
        short_msg = "I didn't quite catch that. Try explaining it another way, or click 'Skip'!"
        markup = {"inline_keyboard": [[{"text": "Skip Question ⏭️", "callback_data": f"onboarding_skip:{step}"}]]}
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": short_msg,
            "reply_markup": markup
        }
        if task.get("message_id") is not None:
            payload["reply_to_message_id"] = task.get("message_id")
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=payload)
        return
        
    summary = ai_res["summary"]
    tags = ai_res["tags"]
    title = text_content[:80].strip() or f"Onboarding Seed {step}"
    embedding = await embed_text(text_content)
    encrypted_raw_text = encrypt(text_content)
    content_hash = hashlib.sha256(text_content.encode()).hexdigest()[:16]
    
    async with db_conn._pool.connection() as conn:
        await conn.execute("SET statement_timeout = '30s'")
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO items (user_id, source_type, raw_text, summary, title, embedding, tags, content_hash)
                VALUES (%s, 'onboarding', %s, %s, %s, %s::vector, %s, %s)
                RETURNING id;
                """,
                (user_id, encrypted_raw_text, summary, title, embedding, tags, content_hash)
            )
            row = await cur.fetchone()
            item_id = row[0] if row else None
            if item_id:
                passive_ctx = await compute_passive_context(user_id, 'onboarding', conn)
                time_bucket = json.loads(passive_ctx).get("time_of_day")
                await cur.execute(
                    "UPDATE items SET passive_context = %s, save_time_bucket = %s WHERE id = %s;",
                    (passive_ctx, time_bucket, item_id)
                )
            await conn.commit()
            
    if item_id:
        bot_reply = f"Saved: {title} ✓"
        await send_telegram_message(chat_id, bot_reply, reply_to_message_id=task.get("message_id"))
        
        from backend.routes.webhook import advance_onboarding_step
        async with db_conn._pool.connection() as conn:
            await advance_onboarding_step(chat_id, user_id, step, conn, None)


async def process_batch_task(task: Dict[str, Any], user_id: int, chat_id: str) -> bool:
    batch_items = task.get("items", [])
    if not batch_items:
        return False
        
    saved_ids = []
    any_new = False
    item_to_msg_id = {}
    for item in batch_items:
        sub_task = {
            "update_id": item.get("update_id"),
            "chat_id": chat_id,
            "content_type": item.get("content_type"),
            "text": item.get("text"),
            "file_id": item.get("file_id"),
            "message_id": item.get("message_id")
        }
        try:
            res = await process_single_item(sub_task, user_id, chat_id, is_batch_item=True)
            if isinstance(res, tuple):
                sub_res, sub_is_new = res
            else:
                sub_res = res
                sub_is_new = (res is not None)
                
            if sub_res:
                if isinstance(sub_res, list):
                    saved_ids.extend(sub_res)
                    for rid in sub_res:
                        item_to_msg_id[rid] = item.get("message_id")
                else:
                    saved_ids.append(sub_res)
                    item_to_msg_id[sub_res] = item.get("message_id")
                if sub_is_new:
                    any_new = True
        except Exception as e:
            logger.error("Failed to ingest sub task in batch: %s", e)
            
    if not saved_ids:
        await send_telegram_message(chat_id, "None of the items in this batch could be saved.")
        return False
        
    saved_nodes = []
    async with db_conn._pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, title, summary, tags, embedding::text, source_type, source_url, raw_text
                FROM items
                WHERE id = ANY(%s) AND user_id = %s;
                """,
                (saved_ids, user_id)
            )
            rows = await cur.fetchall()
            for r in rows:
                emb_str = r[4]
                emb = [float(x) for x in emb_str.strip("[]").split(",")] if emb_str else []
                saved_nodes.append({
                    "id": r[0],
                    "title": r[1],
                    "summary": r[2],
                    "tags": r[3] or [],
                    "embedding": emb,
                    "source_type": r[5],
                    "source_url": r[6],
                    "raw_text": r[7]
                })
                
    if not saved_nodes:
        return any_new
        
    n = len(saved_nodes)
    parent_map = list(range(n))
    
    def find(i):
        if parent_map[i] == i:
            return i
        parent_map[i] = find(parent_map[i])
        return parent_map[i]
        
    def union(i, j):
        root_i = find(i)
        root_j = find(j)
        if root_i != root_j:
            parent_map[root_i] = root_j
            
    def dot_product(v1, v2):
        return sum(x*y for x, y in zip(v1, v2))
    def magnitude(v):
        return sum(x*x for x in v) ** 0.5
    def cosine_similarity(v1, v2):
        mag1 = magnitude(v1)
        mag2 = magnitude(v2)
        if mag1 == 0 or mag2 == 0:
            return 0.0
        return dot_product(v1, v2) / (mag1 * mag2)
        
    for i in range(n):
        for j in range(i+1, n):
            sim = cosine_similarity(saved_nodes[i]["embedding"], saved_nodes[j]["embedding"])
            if sim >= 0.85:
                union(i, j)
                
    groups = {}
    for i in range(n):
        root = find(i)
        if root not in groups:
            groups[root] = []
        groups[root].append(saved_nodes[i])
        
    final_saves = []
    
    for root, group_items in groups.items():
        if len(group_items) == 1:
            item = group_items[0]
            final_saves.append({
                "type": "single",
                "id": item["id"],
                "title": item["title"],
                "summary": item["summary"],
                "tags": item["tags"],
                "source_type": item["source_type"],
                "message_id": item_to_msg_id.get(item["id"])
            })
        else:
            cascade = AICascade()
            joint_meta = await cascade.generate_joint_summary_and_title(group_items)
            joint_title = joint_meta["title"]
            joint_summary = joint_meta["summary"]
            joint_prompt = joint_meta.get("context_prompt") or "Saved! Since these are related, what is the main link between them that you want to remember?"
            joint_tags = list(set().union(*(it["tags"] for it in group_items)))[:5]
            joint_emb = [sum(x)/len(group_items) for x in zip(*(it["embedding"] for it in group_items))]
            
            decrypted_texts = []
            for it in group_items:
                raw = it["raw_text"]
                if raw:
                    try:
                        decrypted = decrypt(raw)
                    except Exception:
                        decrypted = raw
                    decrypted_texts.append(decrypted)
            combined_raw = "\n\n".join(decrypted_texts)
            encrypted_combined = encrypt(combined_raw)
            
            urls = []
            for it in group_items:
                url = it["source_url"]
                if url:
                    urls.append(url)
                else:
                    urls.append(f"atrium:item:{it['id']}")
            joint_source_url = json.dumps(urls)
            
            async with db_conn._pool.connection() as conn:
                await conn.execute("SET statement_timeout = '30s'")
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO items (user_id, source_type, raw_text, summary, title, embedding, tags, source_url, context_prompt)
                        VALUES (%s, 'combined', %s, %s, %s, %s::vector, %s, %s, %s)
                        RETURNING id;
                        """,
                        (user_id, encrypted_combined, joint_summary, joint_title, joint_emb, joint_tags, joint_source_url, joint_prompt)
                    )
                    parent_row = await cur.fetchone()
                    parent_id = parent_row[0] if parent_row else None
                    if parent_id:
                        passive_ctx = await compute_passive_context(user_id, 'combined', conn)
                        time_bucket = json.loads(passive_ctx).get("time_of_day")
                        await cur.execute(
                            "UPDATE items SET passive_context = %s, save_time_bucket = %s WHERE id = %s;",
                            (passive_ctx, time_bucket, parent_id)
                        )
                    await conn.commit()
                    
            if parent_id:
                group_msg_ids = [item_to_msg_id.get(it["id"]) for it in group_items if item_to_msg_id.get(it["id"])]
                last_msg_id = group_msg_ids[-1] if group_msg_ids else None
                final_saves.append({
                    "type": "combined",
                    "id": parent_id,
                    "title": joint_title,
                    "summary": joint_summary,
                    "tags": joint_tags,
                    "source_type": "combined",
                    "message_id": last_msg_id
                })
                
                original_ids = [it["id"] for it in group_items]
                async with db_conn._pool.connection() as conn:
                    await conn.execute("SET statement_timeout = '30s'")
                    async with db_conn.transaction_context(conn):
                        async with conn.cursor() as cur:
                            await cur.execute(
                                "DELETE FROM quizzes WHERE item_id = ANY(%s) AND user_id = %s;",
                                (original_ids, user_id)
                            )
                            await cur.execute(
                                "DELETE FROM item_chunks WHERE item_id = ANY(%s) AND user_id = %s;",
                                (original_ids, user_id)
                            )
                            await cur.execute(
                                "DELETE FROM reminders WHERE item_id = ANY(%s) AND user_id = %s;",
                                (original_ids, user_id)
                            )
                            await cur.execute(
                                """
                                DELETE FROM insight_candidates 
                                WHERE (item_id_a = ANY(%s) OR item_id_b = ANY(%s)) 
                                  AND user_id = %s;
                                """,
                                (original_ids, original_ids, user_id)
                            )
                            await cur.execute(
                                "DELETE FROM entity_mentions WHERE item_id = ANY(%s) AND user_id = %s;",
                                (original_ids, user_id)
                            )
                            await cur.execute(
                                """
                                DELETE FROM relationships 
                                WHERE ((source_type = 'item' AND source_id = ANY(%s)) 
                                   OR (target_type = 'item' AND target_id = ANY(%s)) 
                                   OR (item_id = ANY(%s))) 
                                  AND user_id = %s;
                                """,
                                (original_ids, original_ids, original_ids, user_id)
                            )
                            await cur.execute(
                                "DELETE FROM items WHERE id = ANY(%s) AND user_id = %s;",
                                (original_ids, user_id)
                            )
                        
                from backend.services.pdf_ingester import chunk_text
                chunk_idx = 0
                for it in group_items:
                    raw_text = ""
                    if it["raw_text"]:
                        try:
                            raw_text = decrypt(it["raw_text"])
                        except Exception:
                            raw_text = it["raw_text"]
                            
                    source_label = it["source_url"] or it["title"] or "Source Item"
                    prefix = f"[Source: {source_label}] "
                    
                    chunks = await chunk_text(raw_text)
                    if not chunks:
                        chunks = [raw_text or "(Empty content)"]
                        
                    for chunk in chunks:
                        chunk_text_prefixed = prefix + chunk
                        chunk_excerpt = chunk_text_prefixed[:500]
                        chunk_emb = await embed_text(chunk_text_prefixed)
                        
                        async with db_conn._pool.connection() as conn:
                            await conn.execute("SET statement_timeout = '30s'")
                            async with conn.cursor() as cur:
                                await cur.execute(
                                    """
                                    INSERT INTO item_chunks (item_id, user_id, chunk_index, chunk_text, embedding, chunk_version)
                                    VALUES (%s, %s, %s, %s, %s::vector, %s);
                                    """,
                                    (parent_id, user_id, chunk_idx, chunk_excerpt, chunk_emb, settings.DEFAULT_CHUNK_VERSION)
                                )
                                await conn.commit()
                        chunk_idx += 1
                        
    async with db_conn._pool.connection() as streak_conn:
        await streak_conn.execute("SET statement_timeout = '30s'")
        from backend.services.streak_service import update_streak
        await update_streak(user_id, streak_conn)
        await streak_conn.commit()
        
    try:
        await redis.delete(f"graph:{user_id}")
    except Exception as e:
        logger.error("Failed to delete graph cache: %s", e)
        
    for save in final_saves:
        user_msg_id = save.get("message_id")
        if user_msg_id:
            try:
                deferred_key = f"deferred_replies:{chat_id}:{user_msg_id}"
                deferred_data = await redis.lrange(deferred_key, 0, -1)
                if deferred_data:
                    logger.info("Processing %d deferred replies for message_id=%s, item_id=%d", len(deferred_data), user_msg_id, save["id"])
                    import re
                    for reply_str in deferred_data:
                        try:
                            reply = json.loads(reply_str)
                            text_val = reply.get("text", "").strip()
                            if text_val:
                                tags = re.findall(r"#([a-zA-Z0-9_-]+)", text_val)
                                if tags:
                                    normalized_tags = [t.strip().lower() for t in tags]
                                    async with db_conn._pool.connection() as conn:
                                        await conn.execute("SET statement_timeout = '30s'")
                                        async with conn.cursor() as cur:
                                            await cur.execute("SELECT tags FROM items WHERE id = %s AND user_id = %s;", (save["id"], user_id))
                                            row = await cur.fetchone()
                                            existing_tags = row[0] if row and row[0] else []
                                            new_tags = list(set(existing_tags + normalized_tags))[:5]
                                            await cur.execute(
                                                "UPDATE items SET tags = %s WHERE id = %s AND user_id = %s;",
                                                (new_tags, save["id"], user_id)
                                            )
                                            await conn.commit()
                                            save["tags"] = new_tags
                                else:
                                    async with db_conn._pool.connection() as conn:
                                        await conn.execute("SET statement_timeout = '30s'")
                                        async with conn.cursor() as cur:
                                            await cur.execute(
                                                "UPDATE items SET context_note = %s WHERE id = %s AND user_id = %s;",
                                                (text_val, save["id"], user_id)
                                            )
                                            await conn.commit()
                        except Exception as e:
                            logger.error("Failed to parse/process deferred reply: %s", e)
                    await redis.delete(deferred_key)
            except Exception as def_err:
                logger.error("Failed to process deferred replies: %s", def_err)

        try:
            from backend.routes.websocket import broadcast
            await broadcast(user_id, {
                "type": "new_node",
                "node": {
                    "id": str(save["id"]),
                    "title": save["title"],
                    "source_type": save["source_type"],
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
            })
        except Exception as ws_err:
            logger.error("Failed to broadcast batch WS: %s", ws_err)
            
        emoji = "🗂" if save["type"] == "combined" else (
            "🎥" if save["source_type"] == "youtube"
            else "🔗" if save["source_type"] == "url"
            else "📄" if save["source_type"] == "pdf"
            else "🎙" if save["source_type"] == "voice"
            else "📝" if save["source_type"] == "text"
            else "🖼"
        )
        bot_reply = _build_success_message(f"{emoji} {save['title']}", save["summary"], save["tags"])
        user_msg_id = save.get("message_id")
        msg_id = await send_telegram_message(chat_id, bot_reply, reply_markup=build_recall_keyboard(save["id"]), reply_to_message_id=user_msg_id)
        if msg_id:
            try:
                await redis.setex(f"message_to_item:{chat_id}:{msg_id}", 604800, str(save["id"]))
                if user_msg_id:
                    await redis.setex(f"message_to_item:{chat_id}:{user_msg_id}", 604800, str(save["id"]))
            except Exception as r_err:
                logger.error("Failed to cache message_to_item mapping: %s", r_err)

    # Dynamic Context Note Why Question (Prompt only once for the most relevant save in batch)
    if final_saves:
        priority = {"combined": 5, "url": 4, "youtube": 4, "pdf": 4, "voice": 4, "text": 3, "image": 2}
        primary_save = max(final_saves, key=lambda s: priority.get(s.get("source_type", "image"), 1))
        try:
            async with db_conn._pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT context_prompt FROM items WHERE id = %s AND user_id = %s;", (primary_save["id"], user_id))
                    row = await cur.fetchone()
            context_prompt = row[0] if row and row[0] else "Saved! Drop a quick 1-sentence note if you want to attach your current thoughts to this."
            await send_context_prompt_with_checks(chat_id, user_id, primary_save["id"], context_prompt)
        except Exception as ctx_err:
            logger.error("Failed to prompt dynamic batch context note: %s", ctx_err)
            
    return any_new


async def process_single_item(task: Dict[str, Any], user_id: int, chat_id: str, is_batch_item: bool = False) -> Optional[int]:
    mood_category = await get_next_mood_category(chat_id)
    await redis.setex(f"context_prompt:current_mood:{chat_id}", 300, mood_category)
    current_mood_var.set(mood_category)

    content_type = task.get("content_type")
    file_id = task.get("file_id")
    text_content = task.get("text")
    update_id = task.get("update_id")
    item_id = None
    
    # Retrieve user context from deferred replies in Redis (if any exist for the original message)
    user_context = None
    user_msg_id = task.get("message_id")
    if user_msg_id:
        try:
            deferred_key = f"deferred_replies:{chat_id}:{user_msg_id}"
            deferred_data = await redis.lrange(deferred_key, 0, -1)
            if deferred_data:
                text_notes = []
                import re
                for reply_str in deferred_data:
                    try:
                        reply = json.loads(reply_str)
                        text_val = reply.get("text", "").strip()
                        # Capture only text notes, ignoring pure hashtag strings
                        if text_val and not re.match(r"^#[a-zA-Z0-9_-]+(?:\s+#[a-zA-Z0-9_-]+)*$", text_val):
                            text_notes.append(text_val)
                    except Exception:
                        pass
                if text_notes:
                    user_context = "; ".join(text_notes)
                    logger.info("Found user context for message_id=%d: %s", user_msg_id, user_context)
        except Exception as r_err:
            logger.error("Failed to read deferred replies for user context: %s", r_err)

    if content_type == "text":
        if not text_content:
            raise ValueError("Text content missing in task")
        
        content_hash = hashlib.sha256(text_content.encode()).hexdigest()[:16]
        async with db_conn._pool.connection() as conn:
            await conn.execute("SET statement_timeout = '30s'")
            async with conn.cursor() as cur:
                await cur.execute("SELECT id, created_at FROM items WHERE user_id=%s AND content_hash=%s LIMIT 1", (user_id, content_hash))
                row = await cur.fetchone()
                if row:
                    if not is_batch_item:
                        saved_date = row[1].strftime("%d %b %Y") if hasattr(row[1], "strftime") else str(row[1])[:10]
                        bot_reply = f"Already saved on {saved_date}."
                        await send_telegram_message(chat_id, bot_reply)
                    return row[0], False
        
        cascade = AICascade()
        summarizer_input = text_content
        if user_context:
            summarizer_input = f"[User's Note/Context: {user_context}]\n" + text_content
        ai_res = await cascade.summarise(summarizer_input, chat_id, mood_category=mood_category)
        summary = ai_res.get("summary") or f"Text note summary: {text_content[:100]}..."
        tags = ai_res.get("tags") or ["text"]
        context_prompt = ai_res.get("context_prompt")
        
        normalized_tags = [t.strip().lower() for t in tags if isinstance(t, str) and t.strip()][:5]
        embedding = await embed_text(text_content)
        encrypted_raw_text = encrypt(text_content)
        title = text_content[:80].strip() or "Text Note"
        
        async with db_conn._pool.connection() as conn:
            await conn.execute("SET statement_timeout = '30s'")
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO items (user_id, source_type, raw_text, summary, title, embedding, tags, content_hash, context_prompt)
                    VALUES (%s, 'text', %s, %s, %s, %s::vector, %s, %s, %s)
                    RETURNING id;
                    """,
                    (user_id, encrypted_raw_text, summary, title, embedding, normalized_tags, content_hash, context_prompt)
                )
                row = await cur.fetchone()
                if not row:
                    raise RuntimeError("Failed to insert text item")
                item_id = row[0]
                await conn.commit()
            
        if not is_batch_item:
            bot_reply = _build_success_message(f"📝 {title}", summary, normalized_tags)
            await send_telegram_message(chat_id, bot_reply, reply_markup=build_recall_keyboard(item_id))
            
    elif content_type == "url":
        if not text_content:
            raise ValueError("URL content missing in task")
        
        async with db_conn._pool.connection() as conn:
            await conn.execute("SET statement_timeout = '30s'")
            async with conn.cursor() as cur:
                await cur.execute("SELECT id, title, created_at FROM items WHERE user_id=%s AND source_url=%s LIMIT 1", (user_id, text_content))
                row = await cur.fetchone()
                if row:
                    if not is_batch_item:
                        saved_date = row[2].strftime("%d %b %Y") if hasattr(row[2], "strftime") else str(row[2])[:10]
                        bot_reply = f"Already saved on {saved_date}."
                        await send_telegram_message(chat_id, bot_reply)
                    return row[0], False
        
        is_youtube = "youtube.com" in text_content.lower() or "youtu.be" in text_content.lower()
        is_instagram = "instagram.com" in text_content.lower() or "instagr.am" in text_content.lower()
        if is_youtube:
            from backend.services.youtube_ingester import ingest_youtube
            item_id = await ingest_youtube(text_content, user_id, db_conn._pool, user_context=user_context)
        elif is_instagram:
            from backend.services.youtube_ingester import ingest_instagram
            item_id = await ingest_instagram(text_content, user_id, db_conn._pool, user_context=user_context)
        else:
            try:
                item_id = await ingest_url(text_content, user_id, db_conn._pool, user_context=user_context)
            except ValueError as e:
                if "private Google Drive link" in str(e):
                    if not is_batch_item:
                        bot_reply = "That Drive file is private. Share it publicly to save it."
                        await send_telegram_message(chat_id, bot_reply)
                    return None, False
                raise
        
        async with db_conn._pool.connection() as conn:
            await conn.execute("SET statement_timeout = '30s'")
            async with conn.cursor() as cur:
                await cur.execute("SELECT title, summary, tags FROM items WHERE id = %s AND user_id = %s;", (item_id, user_id))
                row = await cur.fetchone()
        title = row[0] if row else "URL Link"
        summary = row[1] if row else ""
        item_tags = row[2] if row else []
        
        if not is_batch_item:
            if is_youtube:
                if "Could not process" in summary:
                    bot_reply = "Couldn't process that. Try again in a moment."
                    await send_telegram_message(chat_id, bot_reply)
                else:
                    bot_reply = _build_success_message(f"🎥 {title}", summary, item_tags or [])
                    await send_telegram_message(chat_id, bot_reply, reply_markup=build_recall_keyboard(item_id))
            elif is_instagram:
                if "Could not process" in summary:
                    bot_reply = "Couldn't process that. Try again in a moment."
                    await send_telegram_message(chat_id, bot_reply)
                else:
                    bot_reply = _build_success_message(f"📸 {title}", summary, item_tags or [])
                    await send_telegram_message(chat_id, bot_reply, reply_markup=build_recall_keyboard(item_id))
            else:
                bot_reply = _build_success_message(f"🔗 {title}", summary, item_tags or [])
                await send_telegram_message(chat_id, bot_reply, reply_markup=build_recall_keyboard(item_id))
        
    elif content_type == "pdf":
        if not file_id:
            raise ValueError("PDF file_id missing in task")
        
        tmp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        temp_path = os.path.join(tmp_dir, f"{uuid.uuid4()}.pdf")
        
        try:
            from backend.services.telegram_downloader import download_telegram_file_robust
            file_path = await download_telegram_file_robust(file_id, temp_path, max_size_bytes=20 * 1024 * 1024)
            filename = file_path.split("/")[-1] if "/" in file_path else "document.pdf"
            
            try:
                item_id = await ingest_pdf(temp_path, user_id, filename, file_id, db_conn._pool, user_context=user_context)
            except DuplicateItemException as dup_exc:
                saved_date = getattr(dup_exc, "saved_date", None)
                if saved_date and hasattr(saved_date, "strftime"):
                    date_str = saved_date.strftime("%d %b %Y")
                else:
                    date_str = str(saved_date)[:10] if saved_date else "a previous date"
                if not is_batch_item:
                    bot_reply = f"Already saved on {date_str}."
                    await send_telegram_message(chat_id, bot_reply)
                return getattr(dup_exc, "item_id", None), False
            
            async with db_conn._pool.connection() as conn:
                await conn.execute("SET statement_timeout = '30s'")
                async with conn.cursor() as cur:
                    await cur.execute("SELECT summary, tags FROM items WHERE id = %s AND user_id = %s;", (item_id, user_id))
                    row = await cur.fetchone()
            summary = row[0] if row else "No summary available."
            item_tags = row[1] if row else []
            
            if not is_batch_item:
                bot_reply = _build_success_message(f"📄 {filename}", summary, item_tags or [])
                await send_telegram_message(chat_id, bot_reply, reply_markup=build_recall_keyboard(item_id))
            
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
            item_id = await ingest_voice(file_id, user_id, chat_id, db_conn._pool, user_context=user_context)
        except DuplicateItemException as dup_exc:
            saved_date = getattr(dup_exc, "saved_date", None)
            if saved_date and hasattr(saved_date, "strftime"):
                date_str = saved_date.strftime("%d %b %Y")
            else:
                date_str = str(saved_date)[:10] if saved_date else "a previous date"
            if not is_batch_item:
                bot_reply = f"Already saved on {date_str}."
                await send_telegram_message(chat_id, bot_reply)
            return getattr(dup_exc, "item_id", None), False
        
        async with db_conn._pool.connection() as conn:
            await conn.execute("SET statement_timeout = '30s'")
            async with conn.cursor() as cur:
                await cur.execute("SELECT summary, tags FROM items WHERE id = %s AND user_id = %s;", (item_id, user_id))
                row = await cur.fetchone()
        if row:
            summary = row[0]
            item_tags = row[1] if row[1] else []
        else:
            summary = "Voice note saved."
            item_tags = []
            
        if not is_batch_item:
            bot_reply = _build_success_message("🎙 Voice note", summary, item_tags)
            await send_telegram_message(chat_id, bot_reply, reply_markup=build_recall_keyboard(item_id))
            
    elif content_type in ("photo", "image"):
        if not file_id:
            raise ValueError("Image file_id missing in task")
            
        try:
            res = await ingest_image(file_id, user_id, chat_id, db_conn._pool, user_context=user_context)
        except DuplicateItemException as dup_exc:
            saved_date = getattr(dup_exc, "saved_date", None)
            if saved_date and hasattr(saved_date, "strftime"):
                date_str = saved_date.strftime("%d %b %Y")
            else:
                date_str = str(saved_date)[:10] if saved_date else "a previous date"
            if not is_batch_item:
                bot_reply = f"Already saved on {date_str}."
                await send_telegram_message(chat_id, bot_reply)
            return getattr(dup_exc, "item_id", None), False
            
        item_ids = res if isinstance(res, list) else [res]
        primary_id = item_ids[0] if item_ids else None
        
        for saved_id in item_ids:
            try:
                async with db_conn._pool.connection() as conn:
                    await conn.execute("SET statement_timeout = '30s'")
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "SELECT source_type, title, summary, tags, source_url FROM items WHERE id = %s AND user_id = %s;", 
                            (saved_id, user_id)
                        )
                        row = await cur.fetchone()
                if row:
                    i_type = row[0]
                    i_title = row[1] or ""
                    i_summary = row[2] or ""
                    i_tags = row[3] if row[3] else []
                    i_url = row[4] or ""
                    
                    if not is_batch_item:
                        if i_type == "image":
                            prefix = "🖼 Image"
                            title_to_use = i_title or "Image Note"
                        elif i_type == "url":
                            is_youtube = "youtube.com" in i_url.lower() or "youtu.be" in i_url.lower()
                            is_instagram = "instagram.com" in i_url.lower() or "instagr.am" in i_url.lower()
                            if is_youtube:
                                prefix = "🎥"
                            elif is_instagram:
                                prefix = "📸"
                            else:
                                prefix = "🔗"
                            title_to_use = i_title or "URL Link"
                        else:
                            prefix = "📝"
                            title_to_use = i_title or "Item"
                            
                        bot_reply = _build_success_message(f"{prefix} {title_to_use}", i_summary, i_tags)
                        await send_telegram_message(chat_id, bot_reply, reply_markup=build_recall_keyboard(saved_id))
                        await asyncio.sleep(1.0) # Rate limit protection between multiple notifications
            except Exception as loop_err:
                logger.error("Error processing success notification for item %s: %s", saved_id, loop_err)
                    
        item_id = primary_id
            
    else:
        logger.warning("Unsupported content type '%s'", content_type)
        
    if item_id:
        try:
            async with db_conn._pool.connection() as conn:
                await conn.execute("SET statement_timeout = '30s'")
                async with conn.cursor() as cur:
                    passive_ctx = await compute_passive_context(user_id, content_type or "unknown", conn)
                    time_bucket = json.loads(passive_ctx).get("time_of_day")
                    await cur.execute(
                        "UPDATE items SET passive_context = %s, save_time_bucket = %s WHERE id = %s;",
                        (passive_ctx, time_bucket, item_id)
                    )
                    await conn.commit()
        except Exception as passive_err:
            logger.error("Failed to update passive_context for item %d: %s", item_id, passive_err)

        if not is_batch_item:
            # Standard post-save updates
            try:
                from backend.services.streak_service import update_streak
                async with db_conn._pool.connection() as streak_conn:
                    await streak_conn.execute("SET statement_timeout = '30s'")
                    await update_streak(user_id, streak_conn)
                    await streak_conn.commit()
            except Exception as streak_err:
                logger.error("Failed to update user streak: %s", streak_err)

            try:
                await redis.delete(f"graph:{user_id}")
            except Exception as e:
                logger.error("Failed to delete graph cache: %s", e)
                
            try:
                from backend.routes.websocket import broadcast
                async with db_conn._pool.connection() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "SELECT id, title, source_type, created_at FROM items WHERE id = %s AND user_id = %s;",
                            (item_id, user_id)
                        )
                        item_row = await cur.fetchone()
                if item_row:
                    node_id, node_title, node_source_type, node_created_at = item_row
                    await broadcast(user_id, {
                        "type": "new_node",
                        "node": {
                            "id": str(node_id),
                            "title": node_title,
                            "source_type": node_source_type,
                            "created_at": node_created_at.isoformat() if hasattr(node_created_at, "isoformat") else str(node_created_at)
                        }
                    })
            except Exception as ws_err:
                logger.error("Failed to broadcast new_node WS message: %s", ws_err)

            # Dynamic Context Note
            try:
                async with db_conn._pool.connection() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute("SELECT context_prompt FROM items WHERE id = %s AND user_id = %s;", (item_id, user_id))
                        tag_row = await cur.fetchone()
                if tag_row and tag_row[0]:
                    context_prompt = tag_row[0]
                    await send_context_prompt_with_checks(chat_id, user_id, item_id, context_prompt, mood_category)
            except Exception as ctx_err:
                logger.error("Failed to prompt dynamic context note: %s", ctx_err)

        # Trigger Entity & Relationship Extraction
        try:
            async with db_conn._pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT raw_text, summary FROM items WHERE id = %s AND user_id = %s;", (item_id, user_id))
                    item_row = await cur.fetchone()
            if item_row:
                raw_encrypted, summary = item_row
                decrypted_text = ""
                if raw_encrypted:
                    try:
                        from backend.services.encryption import decrypt
                        decrypted_text = decrypt(raw_encrypted)
                    except Exception:
                        pass
                content_text = decrypted_text if decrypted_text else (summary or "")
                
                from backend.services.entity_extractor import extract_and_resolve_entities
                await extract_and_resolve_entities(item_id, user_id, content_text, db_conn._pool)
        except Exception as ext_err:
            logger.error("Failed to run entity extraction on item %d: %s", item_id, ext_err)

    return item_id, True

# Global task ownership registry and shutdown event
worker_background_tasks = set()
shutdown_event = asyncio.Event()

async def start_worker_task() -> None:
    """Runs the worker continuous loop polling Upstash Redis."""
    global worker_background_tasks, shutdown_event
    redis_fail_start = None
    
    logger.info("Recall background worker thread started.")
    
    # Recover leftovers from previous run
    try:
        leftovers = await redis.lrange("atrium:processing", 0, -1)
        if leftovers:
            logger.info("Found %d unprocessed tasks in atrium:processing queue. Recovering...", len(leftovers))
            pipeline_cmds = []
            for task_str in leftovers:
                pipeline_cmds.append(["LPUSH", "atrium:tasks", task_str])
                pipeline_cmds.append(["LREM", "atrium:processing", "1", task_str])
            await redis.pipeline(pipeline_cmds)
            logger.info("Recovered %d tasks back to atrium:tasks.", len(leftovers))
    except Exception as recovery_err:
        logger.error("Failed to recover tasks from atrium:processing: %s", recovery_err)
    
    idle_sleep = 1.0
    
    # Initialize the concurrency semaphore explicitly
    global worker_semaphore
    semaphore = asyncio.Semaphore(3)
    worker_semaphore = semaphore
    
    holding_semaphore = False
    while not shutdown_event.is_set():
        try:
            await semaphore.acquire()
            holding_semaphore = True
        except asyncio.CancelledError:
            logger.info("Worker semaphore acquire cancelled.")
            break

        if shutdown_event.is_set():
            semaphore.release()
            holding_semaphore = False
            break

        try:
            # Poll Upstash Redis using BRPOPLPUSH with 2s timeout
            task_json = await redis.brpoplpush("atrium:tasks", "atrium:processing", timeout=2)
            
            # Reset Redis failure tracking if reachable
            if redis_fail_start is not None:
                logger.info("Re-established connection to Upstash Redis.")
                redis_fail_start = None
                
            if task_json:
                idle_sleep = 1.0
                try:
                    task = json.loads(task_json)
                    try:
                        t = asyncio.create_task(process_task(task, task_json, semaphore))
                        worker_background_tasks.add(t)
                        t.add_done_callback(worker_background_tasks.discard)
                        holding_semaphore = False
                    except Exception as spawn_err:
                        logger.error("Failed to spawn process_task task: %s", spawn_err)
                        semaphore.release()
                        holding_semaphore = False
                except json.JSONDecodeError as parse_err:
                    logger.error("Failed to parse task JSON: %s. Value: %s", parse_err, task_json)
                    try:
                        await redis.lrem("atrium:processing", 1, task_json)
                    except Exception as clean_err:
                        logger.error("Failed to clean invalid task from processing queue: %s", clean_err)
                    semaphore.release()
                    holding_semaphore = False
            else:
                semaphore.release()
                holding_semaphore = False
                # brpoplpush blocks for 2 seconds, so we loop back immediately without sleeping.
                    
        except asyncio.CancelledError:
            if holding_semaphore:
                semaphore.release()
                holding_semaphore = False
            logger.info("Worker polling loop cancelled.")
            break
        except Exception as redis_err:
            if holding_semaphore:
                semaphore.release()
                holding_semaphore = False
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
            
            await asyncio.sleep(5.0)


async def compute_passive_context(user_id: int, source_type: str, conn) -> str:
    """Computes passive context JSON object for weak LLM signals."""
    async with conn.cursor() as cur:
        await cur.execute("SELECT timezone_offset FROM users WHERE id = %s;", (user_id,))
        row = await cur.fetchone()
        offset_minutes = row[0] if (row and row[0] is not None) else 0

    utc_now = datetime.now(timezone.utc)
    local_time = utc_now + timedelta(minutes=offset_minutes)

    hour = local_time.hour
    if 6 <= hour < 12:
        time_of_day = "morning"
    elif 12 <= hour < 17:
        time_of_day = "afternoon"
    elif 17 <= hour < 22:
        time_of_day = "evening"
    else:
        time_of_day = "night"

    day_of_week = local_time.strftime("%A")

    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT COUNT(*) FROM items WHERE user_id = %s AND created_at >= NOW() - INTERVAL '24 hours';",
            (user_id,)
        )
        row_count = await cur.fetchone()
        prior_cluster_activity_24h = row_count[0] if row_count else 0

    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT created_at FROM items WHERE user_id = %s ORDER BY created_at DESC LIMIT 1;",
            (user_id,)
        )
        row_prev = await cur.fetchone()
        if row_prev and hasattr(row_prev[0], "tzinfo"):
            prev_created_at = row_prev[0]
            if prev_created_at.tzinfo is None:
                prev_created_at = prev_created_at.replace(tzinfo=timezone.utc)
            gap = (utc_now - prev_created_at).total_seconds() / 3600.0
            session_gap_hours = round(gap, 2)
        else:
            session_gap_hours = None

    passive_context_dict = {
        "time_of_day": time_of_day,
        "day_of_week": day_of_week,
        "prior_cluster_activity_24h": prior_cluster_activity_24h,
        "input_method": source_type,
        "session_gap_hours": session_gap_hours
    }
    return json.dumps(passive_context_dict)


if __name__ == "__main__":
    import sys
    from backend.db.connection import open_pool, close_pool
    
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    async def main():
        await open_pool()
        try:
            worker_task = asyncio.create_task(start_worker_task())
            
            import signal
            def handle_shutdown():
                logger.info("Shutdown signal received. Initiating graceful shutdown...")
                shutdown_event.set()
                
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                try:
                    loop.add_signal_handler(sig, handle_shutdown)
                except NotImplementedError:
                    pass
            
            await worker_task
        except asyncio.CancelledError:
            logger.info("Worker main task cancelled.")
        finally:
            if worker_background_tasks:
                logger.info("Awaiting %d active tasks to complete (max 15s timeout)...", len(worker_background_tasks))
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*worker_background_tasks, return_exceptions=True),
                        timeout=15.0
                    )
                    logger.info("All active tasks completed gracefully.")
                except asyncio.TimeoutError:
                    logger.warning("Graceful shutdown timed out. Cancelling remaining %d tasks...", len(worker_background_tasks))
                    for task in list(worker_background_tasks):
                        task.cancel()
                    await asyncio.gather(*worker_background_tasks, return_exceptions=True)
            await close_pool()
            
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped by KeyboardInterrupt.")

