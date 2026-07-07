import logging
import math
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Tuple
import numpy as np
import psycopg

from backend.config import settings
from backend.services.search_service import embed_text

logger = logging.getLogger(__name__)

# Configurable utility blacklist of low-information tags
UTILITY_BLACKLIST = {
    "unknown", "bookmark", "misc", "general", "saved", 
    "imported", "inbox", "note", "untagged", "temp"
}

# Standard exceptions for short tags under 3 characters
ALLOWED_SHORT_TAGS = {"api", "jwt", "db", "git", "ai", "ux", "ui"}

class HubCandidate:
    def __init__(self, tag: str, score_raw: float, count: int):
        self.tag = tag
        self.score_raw = score_raw
        self.count = count
        self.score_final = score_raw


async def calculate_active_hubs(user_id: int, db: psycopg.AsyncConnection) -> List[str]:
    """
    Computes and updates the top active visual hubs for a user using a hybrid scoring algorithm
    with recency, frequency, velocity, hysteresis, and semantic diversification.
    """
    logger.info("Calculating active hubs for user %d", user_id)
    now = datetime.now(timezone.utc)

    async with db.cursor() as cur:
        # 1. Get total number of notes for target count K
        await cur.execute("SELECT COUNT(*) FROM items WHERE user_id = %s;", (user_id,))
        total_notes = (await cur.fetchone())[0]

        if total_notes < 3:
            logger.info("User %d has %d notes (< 3), clearing active hubs.", user_id, total_notes)
            await cur.execute("DELETE FROM active_hubs WHERE user_id = %s;", (user_id,))
            await db.commit()
            return []

        # Calculate K (adaptive ceiling)
        # K = clamp(round(8 + 4 * log10(total_notes)), 8, 25)
        n_val = max(1, total_notes)
        target_k = int(np.clip(np.round(8 + 4 * math.log10(n_val)), 8.0, 25.0))
        logger.info("Adaptive hub target count K for user %d is %d", user_id, target_k)

        # 2. Fetch previously active hubs to apply hysteresis and lifespan
        await cur.execute(
            "SELECT tag, created_at FROM active_hubs WHERE user_id = %s;",
            (user_id,)
        )
        prev_hubs_rows = await cur.fetchall()
        # Map tag -> created_at (tz-aware datetime)
        prev_hubs = {}
        for row in prev_hubs_rows:
            tag_name, created_dt = row
            if created_dt and created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            prev_hubs[tag_name] = created_dt

        # 3. Fetch all items with tags and creation timestamps
        await cur.execute(
            """
            SELECT id, tags, created_at 
            FROM items 
            WHERE user_id = %s AND tags IS NOT NULL;
            """,
            (user_id,)
        )
        item_rows = await cur.fetchall()

    if not item_rows:
        logger.info("No tagged items found for user %d.", user_id)
        return []

    # Map tags to their member item creation datetimes
    tag_buckets: Dict[str, List[datetime]] = {}
    for item_id, tags, created_at in item_rows:
        if not tags:
            continue
        # Make sure created_at is tz-aware
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
            
        for tag in tags:
            tag_clean = tag.strip().lower()
            # Filter utility blacklist
            if tag_clean in UTILITY_BLACKLIST:
                continue
            # Filter short tags unless standard exception
            if len(tag_clean) < 3 and tag_clean not in ALLOWED_SHORT_TAGS:
                continue
            tag_buckets.setdefault(tag, []).append(created_at)

    candidates: List[HubCandidate] = []

    # 4. Calculate scores for all valid tags
    for tag, dts in tag_buckets.items():
        count = len(dts)
        if count < 3:
            continue  # Tag must have at least 3 notes to be a hub candidate

        # A. Frequency: sqrt(n)
        s_freq = math.sqrt(count)

        # B. Recency: sum(exp(-0.05 * days_diff)) [14-day half-life]
        s_recency = 0.0
        r_fast = 0.0
        r_slow = 0.0
        
        for dt in dts:
            diff_days = max(0.0, (now - dt).total_seconds() / 86400.0)
            s_recency += math.exp(-0.05 * diff_days)
            r_fast += math.exp(-0.23 * diff_days)      # 3-day half-life
            r_slow += math.exp(-0.023 * diff_days)     # 30-day half-life

        # C. Velocity: Fast / (Slow + 1)
        s_velocity = r_fast / (r_slow + 1.0)

        # D. Weighted Score
        score_raw = (
            settings.HUB_RECENCY_WEIGHT * s_recency +
            settings.HUB_FREQUENCY_WEIGHT * s_freq +
            settings.HUB_VELOCITY_WEIGHT * s_velocity
        )
        candidates.append(HubCandidate(tag, score_raw, count))

    if not candidates:
        logger.info("No eligible hub candidates found for user %d.", user_id)
        # Clear database active hubs if none exist
        async with db.cursor() as cur:
            await cur.execute("DELETE FROM active_hubs WHERE user_id = %s;", (user_id,))
            await db.commit()
        return []

    # 5. Apply Hysteresis Boost
    for c in candidates:
        if c.tag in prev_hubs:
            c.score_final = c.score_raw * settings.HUB_HYSTERESIS_BOOST
        else:
            c.score_final = c.score_raw

    # Sort candidates by final score descending
    candidates.sort(key=lambda x: x.score_final, reverse=True)

    # 6. Pre-select tags protected by Minimum Lifespan
    selected_hubs: List[str] = []
    lifespan_limit = timedelta(days=settings.HUB_MIN_LIFESPAN_DAYS)

    # We only protect if they still have >= 3 items (sanity check)
    protected_tags = set()
    for c in candidates:
        if c.tag in prev_hubs:
            created_dt = prev_hubs[c.tag]
            if (now - created_dt) < lifespan_limit:
                protected_tags.add(c.tag)
                selected_hubs.append(c.tag)
                if len(selected_hubs) >= target_k:
                    break

    logger.info("User %d: Pre-selected %d hubs under minimum lifespan protection.", user_id, len(selected_hubs))

    # 7. Fetch embeddings for all candidate tags to run the semantic diversification pass
    tag_embeddings: Dict[str, List[float]] = {}
    for c in candidates:
        try:
            # embed_text handles testing mocks and Redis caching internally
            tag_embeddings[c.tag] = await embed_text(c.tag)
        except Exception as embed_err:
            logger.error("Failed to generate embedding for tag '%s': %s", c.tag, embed_err)
            # Fallback to zero vector if embedding fails
            tag_embeddings[c.tag] = [0.0] * 384

    # 8. Diversification Pass: Scan-through remaining candidates
    skipped_candidates: List[HubCandidate] = []

    for c in candidates:
        if len(selected_hubs) >= target_k:
            break
        if c.tag in selected_hubs:
            continue

        tag_vector = np.array(tag_embeddings[c.tag])
        norm_tag = np.linalg.norm(tag_vector)
        
        too_similar = False
        for sel_tag in selected_hubs:
            sel_vector = np.array(tag_embeddings[sel_tag])
            norm_sel = np.linalg.norm(sel_vector)
            
            if norm_tag > 0 and norm_sel > 0:
                sim = float(np.dot(tag_vector, sel_vector) / (norm_tag * norm_sel))
            else:
                sim = 0.0

            if sim >= settings.HUB_DIVERSITY_THRESHOLD:
                too_similar = True
                break

        if not too_similar:
            selected_hubs.append(c.tag)
        else:
            skipped_candidates.append(c)

    # 9. Fallback Pass: Fill up remaining target slots from skipped candidates
    for c in skipped_candidates:
        if len(selected_hubs) >= target_k:
            break
        if c.tag not in selected_hubs:
            selected_hubs.append(c.tag)

    # 10. Update the database active_hubs table
    async with db.cursor() as cur:
        # Insert or update each selected hub
        for tag in selected_hubs:
            if tag in prev_hubs:
                # Keep original created_at timestamp
                orig_created = prev_hubs[tag]
                await cur.execute(
                    """
                    INSERT INTO active_hubs (user_id, tag, created_at, last_active_at)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id, tag) DO UPDATE
                    SET last_active_at = CURRENT_TIMESTAMP;
                    """,
                    (user_id, tag, orig_created)
                )
            else:
                # New active hub gets current timestamp
                await cur.execute(
                    """
                    INSERT INTO active_hubs (user_id, tag, created_at, last_active_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id, tag) DO UPDATE
                    SET last_active_at = CURRENT_TIMESTAMP;
                    """,
                    (user_id, tag)
                )

        # Delete any tags that are no longer active
        if selected_hubs:
            await cur.execute(
                """
                DELETE FROM active_hubs 
                WHERE user_id = %s AND tag != ALL(%s);
                """,
                (user_id, selected_hubs)
            )
        else:
            await cur.execute(
                "DELETE FROM active_hubs WHERE user_id = %s;",
                (user_id,)
            )

        await db.commit()

    logger.info("Successfully updated active hubs for user %d: %s", user_id, selected_hubs)
    return selected_hubs
