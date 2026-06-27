import logging
from datetime import datetime, timedelta, timezone, time
from typing import Optional, Tuple
from psycopg import AsyncConnection
from backend.services.redis_client import redis

logger = logging.getLogger(__name__)

def parse_time_expression(text: str) -> Tuple[Optional[timedelta], Optional[str], str]:
    """
    Parses natural language time expressions from the start of the text.
    Does not use regular expressions.
    Returns:
      (delta, absolute_format, remaining_message)
    """
    tokens = [t.strip() for t in text.split() if t.strip()]
    if not tokens:
        return None, None, ""
        
    t0_lower = tokens[0].lower()
    
    # 1. Check for two-word absolute expressions first
    if len(tokens) >= 2:
        t1_lower = tokens[1].lower()
        # "tomorrow morning"
        if t0_lower == "tomorrow" and t1_lower == "morning":
            message = " ".join(tokens[2:])
            return None, "tomorrow_morning", message
        # "tomorrow evening"
        if t0_lower == "tomorrow" and t1_lower == "evening":
            message = " ".join(tokens[2:])
            return None, "tomorrow_evening", message
        # "next week"
        if t0_lower == "next" and t1_lower == "week":
            message = " ".join(tokens[2:])
            return None, "next_week", message
            
    # 2. Check for one-word absolute expressions
    if t0_lower == "tomorrow":
        message = " ".join(tokens[1:])
        return None, "tomorrow", message
        
    # 3. Check for relative expressions (Xm, Xmin, Xh, Xhr, Xd, Xday)
    suffixes = [
        ("min", timedelta(minutes=1)),
        ("m", timedelta(minutes=1)),
        ("hr", timedelta(hours=1)),
        ("h", timedelta(hours=1)),
        ("day", timedelta(days=1)),
        ("d", timedelta(days=1)),
    ]
    
    for suffix, base_delta in suffixes:
        if t0_lower.endswith(suffix):
            val_part = t0_lower[:-len(suffix)]
            if val_part.isdigit():
                val = int(val_part)
                if base_delta.days > 0:
                    delta = timedelta(days=val * base_delta.days)
                elif base_delta.seconds // 3600 > 0:
                    delta = timedelta(hours=val * (base_delta.seconds // 3600))
                else:
                    delta = timedelta(minutes=val * (base_delta.seconds // 60))
                    
                message = " ".join(tokens[1:])
                return delta, None, message
                
    return None, None, ""


async def create_reminder(
    user_id: int,
    message: str,
    remind_at_utc: datetime,
    db: AsyncConnection
) -> Tuple[int, str, bool]:
    """
    Validates and creates a new reminder for the user.
    Enforces the active reminder limit (max 20) and message length truncation (max 500).
    
    Returns:
      (reminder_id, final_message, was_truncated)
    """
    # 1. Enforce active reminder limit
    async with db.cursor() as cur:
        await cur.execute(
            """
            SELECT COUNT(*) FROM reminders
            WHERE user_id = %s AND status = 'pending';
            """,
            (user_id,)
        )
        row = await cur.fetchone()
        active_count = row[0] if row else 0
        if active_count >= 20:
            raise ValueError("You have reached the limit of 20 active reminders.")
            
        # 2. Enforce message truncation
        was_truncated = False
        if len(message) > 500:
            message = message[:500]
            was_truncated = True
            
        # 3. Insert reminder
        await cur.execute(
            """
            INSERT INTO reminders (user_id, message, remind_at, status)
            VALUES (%s, %s, %s, 'pending')
            RETURNING id;
            """,
            (user_id, message, remind_at_utc, )
        )
        insert_row = await cur.fetchone()
        if not insert_row:
            raise RuntimeError("Failed to persist reminder.")
        reminder_id = insert_row[0]
        
        # 4. Add to Redis sorted set for scheduling
        score = int(remind_at_utc.timestamp())
        try:
            await redis.zadd("reminders:active", score, str(reminder_id))
        except Exception as e:
            logger.error("Failed to add reminder %d to Redis zset: %s", reminder_id, e)
            raise RuntimeError(f"Failed to schedule reminder in Redis: {e}") from e
        
    return reminder_id, message, was_truncated
