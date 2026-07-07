"""
backend/routes/hearth.py
========================
Hearth feature endpoints — shared home progression for paired users.

Multiple journeys supported: a user can have multiple active pairs (one per
unique partner). Leaving a journey hard-deletes the pair row — progress is
permanently gone, as warned to the user.

All endpoints require JWT cookie auth (get_current_user).
Uses psycopg3 AsyncConnection cursor queries with dict_row row_factory.
Query placeholders use %s (psycopg3 standard) instead of pg-specific $1/$2.
"""

import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from psycopg.rows import dict_row

from backend.middleware.twa_auth import get_current_user, UserContext
from backend.db.connection import get_db
from backend.config import settings
from backend.services.http_client import get_http_client

logger = logging.getLogger(__name__)
router = APIRouter(tags=["hearth"])


# ── Row helper ────────────────────────────────────────────────────────────────

def get_row_val(row, key: str, index: int):
    """Safely extracts value from row supporting both dict and tuple formats."""
    if not row:
        return None
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[index]
    except (IndexError, TypeError):
        return None


# ── Score formula ────────────────────────────────────────────────────────────

def shared_days_to_score(days: int) -> float:
    """
    Maps shared active days → 0–96 POC score.
    Curved: fast early (breeze first month), slow later (1 year to Villa).
    """
    if days <= 20:   return days * 0.80
    if days <= 40:   return 16 + (days - 20) * 0.85
    if days <= 65:   return 33 + (days - 40) * 0.76
    if days <= 120:  return 52 + (days - 65) * 0.38
    return min(96.0, 73 + (days - 120) * 0.30)


STAGE_THRESHOLDS = [
    (0,   "Hut"),
    (20,  "Cottage"),
    (40,  "House"),
    (65,  "Manor"),
    (120, "Villa"),
    (200, "Castle"),
]


def get_stage(days: int) -> str:
    stage = "Hut"
    for threshold, name in STAGE_THRESHOLDS:
        if days >= threshold:
            stage = name
    return stage


# ── Telegram helper ──────────────────────────────────────────────────────────

async def _notify_telegram(chat_id: str, text: str) -> None:
    """Send a Telegram message. Fire-and-forget — never raises."""
    try:
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        client = get_http_client()
        await client.post(url, json={"chat_id": chat_id, "text": text}, timeout=5.0)
    except Exception as exc:
        logger.error("Hearth: Telegram notify failed for chat_id %s: %s", chat_id, exc)


# ── Request bodies ───────────────────────────────────────────────────────────

class AcceptBody(BaseModel):
    invite_code: str


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _build_journey_dict(cur, pair: dict, user_id: int) -> dict:
    """Given a pair row and the requesting user_id, return a journey object."""
    user_a_id  = get_row_val(pair, "user_a_id", 1)
    user_b_id  = get_row_val(pair, "user_b_id", 2)
    pair_id    = get_row_val(pair, "id", 0)
    days       = get_row_val(pair, "shared_days", 3) or 0
    created_at = get_row_val(pair, "created_at", 4)

    partner_id = user_b_id if user_a_id == user_id else user_a_id

    await cur.execute(
        "SELECT first_name, username FROM users WHERE id = %s;",
        (partner_id,),
    )
    partner = await cur.fetchone()
    partner_name = "Partner"
    if partner:
        p_first = get_row_val(partner, "first_name", 0)
        p_user  = get_row_val(partner, "username",   1)
        partner_name = p_first or p_user or "Partner"

    await cur.execute(
        """
        SELECT 1 FROM items
        WHERE user_id = %s AND created_at::date = CURRENT_DATE
        LIMIT 1;
        """,
        (partner_id,),
    )
    partner_active_today = bool(await cur.fetchone())

    await cur.execute(
        """
        SELECT 1 FROM items
        WHERE user_id = %s AND created_at::date = CURRENT_DATE
        LIMIT 1;
        """,
        (user_id,),
    )
    self_active_today = bool(await cur.fetchone())

    score      = shared_days_to_score(days)
    paired_since = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)

    return {
        "pair_id":              str(pair_id),
        "is_paired":            True,
        "score":                round(score, 2),
        "shared_days":          days,
        "stage":                get_stage(days),
        "partner_name":         partner_name,
        "partner_id":           partner_id,
        "partner_active_today": partner_active_today,
        "self_active_today":    self_active_today,
        "paired_since":         paired_since,
    }


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/api/hearth")
async def get_hearth(
    user: UserContext = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Return all active journeys for the current user.
    Response: { journeys: [...] }
    Empty list means unpaired.
    """
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, user_a_id, user_b_id, shared_days, created_at
            FROM journey_pairs
            WHERE (user_a_id = %s OR user_b_id = %s)
            ORDER BY created_at DESC;
            """,
            (user.id, user.id),
        )
        pairs = await cur.fetchall()

        journeys = []
        for pair in pairs:
            journey = await _build_journey_dict(cur, pair, user.id)
            journeys.append(journey)

    return {"journeys": journeys}


@router.get("/api/hearth/status")
async def get_hearth_status(
    user: UserContext = Depends(get_current_user),
    db=Depends(get_db),
):
    """Quick check: is the user paired? Do they have a pending invite?"""
    async with db.cursor() as cur:
        await cur.execute(
            """
            SELECT 1 FROM journey_pairs
            WHERE (user_a_id = %s OR user_b_id = %s)
            LIMIT 1;
            """,
            (user.id, user.id),
        )
        is_paired = bool(await cur.fetchone())

        await cur.execute(
            """
            SELECT 1 FROM journey_invites
            WHERE inviter_id = %s AND status = 'pending' AND expires_at > NOW()
            LIMIT 1;
            """,
            (user.id,),
        )
        has_pending_invite = bool(await cur.fetchone())

    return {"is_paired": is_paired, "has_pending_invite": has_pending_invite}


@router.post("/api/hearth/invite")
async def create_invite(
    user: UserContext = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Generate a Hearth invite code.
    Multiple journeys are allowed — no longer blocked by existing pairs.
    Returns existing pending invite if one exists.
    """
    async with db.cursor(row_factory=dict_row) as cur:
        # Return existing pending invite if one exists
        await cur.execute(
            """
            SELECT invite_code FROM journey_invites
            WHERE inviter_id = %s AND status = 'pending' AND expires_at > NOW()
            ORDER BY created_at DESC LIMIT 1;
            """,
            (user.id,),
        )
        existing_invite = await cur.fetchone()
        if existing_invite:
            code = get_row_val(existing_invite, "invite_code", 0)
            return {
                "invite_code": code,
                "invite_url":  f"https://t.me/recall_bot?start=hearth_{code}",
                "expires_in":  "7 days",
            }

        # Generate new code: format RCL-XXXX-XXXX
        raw  = secrets.token_urlsafe(9).upper().replace("-", "").replace("_", "")[:8]
        code = f"RCL-{raw[:4]}-{raw[4:8]}"

        await cur.execute(
            """
            INSERT INTO journey_invites (inviter_id, invite_code)
            VALUES (%s, %s);
            """,
            (user.id, code),
        )
        await db.commit()

    return {
        "invite_code": code,
        "invite_url":  f"https://t.me/recall_bot?start=hearth_{code}",
        "expires_in":  "7 days",
    }


@router.post("/api/hearth/accept")
async def accept_invite(
    body: AcceptBody,
    user: UserContext = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Accept a Hearth invite code and create the pair.
    Multiple journeys are supported — only guards: no self-pair,
    and no duplicate active pair with the same person (DB unique constraint).
    Both users receive a Telegram notification.
    """
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, inviter_id FROM journey_invites
            WHERE invite_code = %s
              AND status = 'pending'
              AND expires_at > NOW();
            """,
            (body.invite_code,),
        )
        invite = await cur.fetchone()

        if not invite:
            raise HTTPException(status_code=404, detail="Invalid or expired invite code")

        inviter_id = get_row_val(invite, "inviter_id", 1)
        invite_id  = get_row_val(invite, "id", 0)

        if inviter_id == user.id:
            raise HTTPException(status_code=400, detail="Cannot pair with yourself")

        # Check if this exact pair already exists (prevents duplicate with same person)
        a_id, b_id = sorted([inviter_id, user.id])
        await cur.execute(
            """
            SELECT 1 FROM journey_pairs
            WHERE user_a_id = %s AND user_b_id = %s
            LIMIT 1;
            """,
            (a_id, b_id),
        )
        if await cur.fetchone():
            raise HTTPException(
                status_code=400,
                detail="You already have an active journey with this person"
            )

        # Transaction: create pair + mark invite accepted
        async with db.transaction():
            await cur.execute(
                """
                INSERT INTO journey_pairs (user_a_id, user_b_id)
                VALUES (%s, %s);
                """,
                (a_id, b_id),
            )
            await cur.execute(
                "UPDATE journey_invites SET status = 'accepted' WHERE id = %s;",
                (invite_id,),
            )

        # Fetch inviter info for Telegram nudge
        await cur.execute(
            "SELECT telegram_chat_id, first_name FROM users WHERE id = %s;",
            (inviter_id,),
        )
        inviter = await cur.fetchone()
        inviter_chat_id = get_row_val(inviter, "telegram_chat_id", 0)

        await cur.execute(
            "SELECT COALESCE(first_name, username, 'Someone') AS name FROM users WHERE id = %s;",
            (user.id,),
        )
        accepter_row  = await cur.fetchone()
        accepter_name = get_row_val(accepter_row, "name", 0) or "Someone"

    if inviter_chat_id:
        await _notify_telegram(
            inviter_chat_id,
            f"🔥 {accepter_name} lit your Hearth. Your journey begins.",
        )

    return {"success": True, "message": "Hearth lit"}


@router.delete("/api/hearth/leave/{pair_id}")
async def leave_journey(
    pair_id: int,
    user: UserContext = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Hard-delete a journey pair. Progress is permanently gone.
    User was explicitly warned before this is called.
    Notifies partner via Telegram.
    """
    async with db.cursor(row_factory=dict_row) as cur:
        # Verify ownership — user must be part of this pair
        await cur.execute(
            """
            SELECT id, user_a_id, user_b_id
            FROM journey_pairs
            WHERE id = %s AND (user_a_id = %s OR user_b_id = %s);
            """,
            (pair_id, user.id, user.id),
        )
        pair = await cur.fetchone()
        if not pair:
            raise HTTPException(status_code=404, detail="Journey not found")

        user_a_id  = get_row_val(pair, "user_a_id", 1)
        user_b_id  = get_row_val(pair, "user_b_id", 2)
        partner_id = user_b_id if user_a_id == user.id else user_a_id

        # Fetch partner's chat ID for notification
        await cur.execute(
            "SELECT telegram_chat_id FROM users WHERE id = %s;",
            (partner_id,),
        )
        partner_row     = await cur.fetchone()
        partner_chat_id = get_row_val(partner_row, "telegram_chat_id", 0)

        await cur.execute(
            "SELECT COALESCE(first_name, username, 'Someone') AS name FROM users WHERE id = %s;",
            (user.id,),
        )
        leaver_row  = await cur.fetchone()
        leaver_name = get_row_val(leaver_row, "name", 0) or "Someone"

        # Hard delete — data is gone as warned
        async with db.transaction():
            await cur.execute(
                "DELETE FROM journey_pairs WHERE id = %s;",
                (pair_id,),
            )

    if partner_chat_id:
        await _notify_telegram(
            partner_chat_id,
            f"💔 {leaver_name} has ended your Hearth journey. Their door is closed.",
        )

    return {"success": True}
