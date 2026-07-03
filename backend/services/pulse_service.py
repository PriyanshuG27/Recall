"""
backend/services/pulse_service.py
=================================
Calculates and updates user pulse score metrics based on cognitive activity, 
saved items logarithmic density, and SM2 memory retention success rates.
"""

import math
import logging
from datetime import datetime, timezone
import psycopg

logger = logging.getLogger(__name__)

async def calculate_user_pulse(cur: psycopg.AsyncCursor, user_id: int) -> int:
    """
    Calculates the current cognitive pulse score for a user.
    Formula: Pulse = 15.0 * ln(items + 1) + 50.0 * retention_rate - 5.0 * days_inactive
    Clamped between 0 and 100.
    """
    # 1. Total items count
    await cur.execute("SELECT COUNT(*) FROM items WHERE user_id = %s;", (user_id,))
    row = await cur.fetchone()
    items_count = int(row[0]) if row else 0

    # 2. Retention rate from last 30 days quiz attempts
    await cur.execute(
        """
        SELECT COUNT(CASE WHEN quality >= 3 THEN 1 END) AS correct_count,
               COUNT(*) AS total_count
        FROM quiz_answers
        WHERE user_id = %s AND answered_at >= NOW() - INTERVAL '30 days';
        """,
        (user_id,)
    )
    row = await cur.fetchone()
    if row and row[1] and int(row[1]) > 0:
        retention_rate = float(row[0]) / float(row[1])
    else:
        # Default to 0.5 retention rate if no quiz answers exist in the last 30 days
        retention_rate = 0.5

    # 3. Days inactive since last save or last quiz completed
    await cur.execute(
        """
        SELECT COALESCE(
            GREATEST(
                (SELECT MAX(created_at) FROM items WHERE user_id = %s),
                (SELECT MAX(answered_at) FROM quiz_answers WHERE user_id = %s)
            ),
            (SELECT created_at FROM users WHERE id = %s)
        );
        """,
        (user_id, user_id, user_id)
    )
    row = await cur.fetchone()
    
    last_active = None
    if row and row[0]:
        last_active = row[0]
        if not isinstance(last_active, datetime):
            if isinstance(last_active, str):
                try:
                    last_active = datetime.fromisoformat(last_active)
                except Exception:
                    last_active = datetime.now(timezone.utc)
            else:
                last_active = datetime.now(timezone.utc)
        if last_active.tzinfo is None:
            last_active = last_active.replace(tzinfo=timezone.utc)
    else:
        last_active = datetime.now(timezone.utc)

    days_inactive = (datetime.now(timezone.utc) - last_active).days
    days_inactive = max(0, days_inactive)

    # 4. Apply formula weights
    score_items = 15.0 * math.log(items_count + 1)
    score_retention = 50.0 * retention_rate
    score_decay = 5.0 * days_inactive

    pulse = score_items + score_retention - score_decay
    pulse = max(0, min(100, int(round(pulse))))

    logger.debug(
        "Pulse calculation detail for user_id=%d: items_count=%d (score=%.2f), "
        "retention_rate=%.2f (score=%.2f), days_inactive=%d (decay=%.2f) -> raw=%.2f, final=%d",
        user_id, items_count, score_items, retention_rate, score_retention,
        days_inactive, score_decay, (score_items + score_retention - score_decay), pulse
    )
    return pulse


async def update_user_pulse(cur: psycopg.AsyncCursor, user_id: int) -> int:
    """Calculates user pulse score and updates the users table."""
    pulse = await calculate_user_pulse(cur, user_id)
    await cur.execute(
        "UPDATE users SET pulse_score = %s WHERE id = %s;",
        (pulse, user_id)
    )
    return pulse
