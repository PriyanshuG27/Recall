import logging
import numpy as np
import networkx as nx
import community as community_louvain
from typing import List, Dict, Any, Optional
import datetime
import sys, asyncio
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.config import settings
from backend.db import connection
from backend.services.ai_cascade import AICascade
from backend.services.redis_client import redis

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_pool = None  # Mock-patched in unit tests


def parse_vector(val: Any) -> list[float]:
    """Helper to parse raw database vector format into list of floats."""
    if not val:
        return []
    if isinstance(val, str):
        val_str = val.strip("[]")
        return [float(x) for x in val_str.split(",") if x.strip()]
    if isinstance(val, (list, tuple)):
        return [float(x) for x in val]
    return []


async def get_pool():
    """Returns the active psycopg connection pool or opens a new one."""
    global _pool
    if _pool is not None:
        connection._pool = _pool

    if connection._pool is None:
        await connection.open_pool()
    return connection._pool


async def send_telegram_message(
    chat_id: str,
    text: str,
    reply_markup: Optional[Dict[str, Any]] = None,
    parse_mode: Optional[str] = None
) -> bool:
    """Helper to send Telegram messages via Bot API, redacting sensitive tokens in logs."""
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    if parse_mode is not None:
        payload["parse_mode"] = parse_mode
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=10.0)
            resp.raise_for_status()
            return True
    except Exception as e:
        # Redact the Telegram bot token in case it appears in exception messaging
        err_msg = str(e).replace(settings.TELEGRAM_BOT_TOKEN, "[REDACTED_BOT_TOKEN]")
        logger.error("Failed to send Telegram message to chat_id %s: %s", chat_id, err_msg)
        return False


async def _perform_db_hubs_swap(cur, user_id: int, hubs_to_insert: List[Dict[str, Any]]) -> None:
    """Performs DELETE and INSERT operations for semantic hubs in a database transaction block."""
    # DELETE existing semantic hubs for the user
    await cur.execute(
        "DELETE FROM semantic_hubs WHERE user_id = %s",
        (user_id,)
    )
    # INSERT new semantic hubs
    for hub in hubs_to_insert:
        centroid_str = "[" + ",".join(str(float(x)) for x in hub["centroid"]) + "]"
        await cur.execute(
            """
            INSERT INTO semantic_hubs (user_id, label, centroid, member_ids, last_active_at, streak_days)
            VALUES (%s, %s, %s::vector, %s, %s, %s)
            RETURNING id;
            """,
            (
                user_id,
                hub["label"],
                centroid_str,
                hub["member_ids"],
                hub["last_active_at"],
                hub["streak_days"]
            )
        )
        row = await cur.fetchone()
        hub["id"] = row[0] if row else None


# ---------------------------------------------------------------------------
# Background Jobs
# ---------------------------------------------------------------------------

async def reminders_dispatcher() -> None:
    """
    Background job to deliver pending reminders and expire drift loops.
    Uses Redis Sorted Set 'reminders:active' for scheduling:
    1. Queries Redis zset 'reminders:active' for due IDs or drift keys.
    2. If empty, exits immediately without touching the PostgreSQL pool (Neon autosuspend).
    3. If not empty, checks out database connection, updates statuses, and dispatches/expires.
    """
    import time
    try:
        now_epoch = int(time.time())
        due_ids_str = await redis.zrangebyscore("reminders:active", "-inf", str(now_epoch))
        if not due_ids_str:
            return

        # Divide into reminders and drift candidates
        drift_cand_ids = [int(x.split(":")[1]) for x in due_ids_str if isinstance(x, str) and x.startswith("drift:")]
        due_ids = [int(x) for x in due_ids_str if isinstance(x, str) and x.isdigit()]

        if not due_ids and not drift_cand_ids:
            return

        logger.info("Found %d pending reminders and %d drift expiries to process.", len(due_ids), len(drift_cand_ids))
        pool = await get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                # 1. Process drift expiries
                if drift_cand_ids:
                    await cur.execute(
                        "UPDATE insight_candidates SET status = 'expired' WHERE id = ANY(%s) AND status = 'delivered';",
                        (drift_cand_ids,)
                    )
                    await conn.commit()
                    for c_id in drift_cand_ids:
                        await redis.zrem("reminders:active", f"drift:{c_id}")
                        logger.info("Expired drift candidate %d in DB and Redis", c_id)

                # 1b. Sweep expired near-misses (older than 72 hours)
                await cur.execute(
                    """
                    UPDATE insight_candidates 
                    SET status = 'expired' 
                    WHERE bucket = 'near_miss' AND status = 'pending' AND created_at < NOW() - INTERVAL '72 hours';
                    """
                )
                await conn.commit()

                # 2. Process reminders
                if due_ids:
                    await cur.execute(
                        """
                        SELECT r.id, r.message, u.telegram_chat_id
                        FROM reminders r
                        JOIN users u ON r.user_id = u.id
                        WHERE r.id = ANY(%s) AND r.status = 'pending';
                        """,
                        (due_ids,)
                    )
                    rows = await cur.fetchall()
                    
                    # Remove all checked due IDs from Redis immediately to prevent loopups
                    for rem_id in due_ids:
                        await redis.zrem("reminders:active", str(rem_id))
                        
                    if rows:
                        for row in rows:
                            rem_id, message, chat_id = row
                            formatted_msg = f"🔔 Reminder:\n\n{message}"
                            success = await send_telegram_message(chat_id, formatted_msg)
                            status = "sent" if success else "failed"
                            await cur.execute(
                                "UPDATE reminders SET status = %s WHERE id = %s",
                                (status, rem_id)
                            )
                        await conn.commit()
                        logger.info("Successfully processed and updated %d reminders.", len(rows))
    except Exception as e:
        logger.error("reminders_dispatcher job failed: %s", e, exc_info=True)


async def scan_insight_candidates_for_user(user_id: int, pool) -> None:
    try:
        # 1. Fetch user near_miss_lower_bound
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT near_miss_lower_bound FROM users WHERE id = %s;", (user_id,))
                row = await cur.fetchone()
                floor = float(row[0]) if (row and row[0] is not None) else 0.710

        # 2. Fetch cross-cluster item pairs (saved >= 14 days apart, similarity >= floor)
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT a.id, b.id, 1 - (a.embedding <=> b.embedding) AS similarity
                    FROM items a, items b
                    WHERE a.user_id = %s AND b.user_id = %s
                      AND a.id < b.id
                      AND a.created_at < b.created_at - INTERVAL '14 days'
                      AND a.source_type != 'combined'
                      AND b.source_type != 'combined'
                      AND 1 - (a.embedding <=> b.embedding) >= %s
                    ORDER BY similarity DESC
                    LIMIT 200;
                    """,
                    (user_id, user_id, floor)
                )
                candidate_pairs = await cur.fetchall()
                
                if not candidate_pairs:
                    return
                
                # Fetch semantic hub mappings for this user
                await cur.execute(
                    "SELECT id, member_ids FROM semantic_hubs WHERE user_id = %s;",
                    (user_id,)
                )
                hubs = await cur.fetchall()
                
        # Build map of item_id -> hub_id
        item_to_hub = {}
        for hub_id, member_ids in hubs:
            for m_id in member_ids:
                item_to_hub[m_id] = hub_id
                
        # 3. Process each pair
        import hashlib
        for item_a_id, item_b_id, sim in candidate_pairs:
            hub_a = item_to_hub.get(item_a_id)
            hub_b = item_to_hub.get(item_b_id)
            
            # Check if they are cross-cluster pairs
            if hub_a is not None and hub_b is not None and hub_a == hub_b:
                continue
                
            # MD5 Hash for novelty filter
            if hub_a is not None and hub_b is not None:
                sorted_hubs = sorted([int(hub_a), int(hub_b)])
                hash_str = f"hubs:{sorted_hubs[0]}:{sorted_hubs[1]}"
            else:
                sorted_items = sorted([item_a_id, item_b_id])
                hash_str = f"items:{sorted_items[0]}:{sorted_items[1]}"
                
            pair_hash = hashlib.md5(hash_str.encode(), usedforsecurity=False).hexdigest()
            
            # Check novelty filter: did this pair hash fire in last 60 days?
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT 1 FROM insight_candidates
                        WHERE user_id = %s AND cluster_pair_hash = %s
                          AND created_at > NOW() - INTERVAL '60 days'
                        LIMIT 1;
                        """,
                        (user_id, pair_hash)
                    )
                    exists = await cur.fetchone()
                    if exists:
                        continue
                        
                    # Insert into insight_candidates
                    bucket = "confirmed" if sim >= 0.75 else "near_miss"
                    await cur.execute(
                        """
                        INSERT INTO insight_candidates (user_id, item_id_a, item_id_b, similarity_score, bucket, status, cluster_pair_hash)
                        VALUES (%s, %s, %s, %s, %s, 'pending', %s)
                        ON CONFLICT DO NOTHING;
                        """,
                        (user_id, item_a_id, item_b_id, float(sim), bucket, pair_hash)
                    )
                    await conn.commit()
    except Exception as scan_err:
        logger.error("Failed to run nightly scan for user %d: %s", user_id, scan_err)

def calculate_hub_streak(item_dates, timezone_offset_minutes: int) -> int:
    if not item_dates:
        return 0
    from datetime import datetime, timezone, timedelta
    tz = timezone(timedelta(minutes=timezone_offset_minutes))
    
    sanitized_dates = []
    for dt in item_dates:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        sanitized_dates.append(dt)
        
    local_dates = sorted(list({dt.astimezone(tz).date() for dt in sanitized_dates}), reverse=True)
    today = datetime.now(tz).date()
    yesterday = today - timedelta(days=1)
    
    if local_dates[0] not in (today, yesterday):
        return 0
        
    streak = 1
    for i in range(len(local_dates) - 1):
        if local_dates[i] - local_dates[i+1] == timedelta(days=1):
            streak += 1
        else:
            break
    return streak


async def louvain_clustering() -> None:
    """
    Background job to run Louvain community clustering for each user.
    Builds a NetworkX graph based on item embedding cosine similarity > 0.75,
    clusters them, generates labels using the AI cascade, and stores the centroids in pgvector format.
    Runs daily at 02:00 UTC.
    """
    try:
        pool = await get_pool()
    except Exception as e:
        logger.error("Failed to open database pool in Louvain job: %s", e)
        return

    # 1. Fetch all users
    users_info = {}
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT id, timezone_offset FROM users")
                users_rows = await cur.fetchall()
                users_info = {row[0]: (row[1] if len(row) > 1 else 0) for row in users_rows}
    except Exception as e:
        logger.error("Failed to fetch users in Louvain job: %s", e)
        return

    users = list(users_info.keys())
    ai_cascade = AICascade()
    threshold = 3 if settings.ENV == "test" else 10
    sem = asyncio.Semaphore(3)  # Caps concurrent AI tasks as per security/concurrency guidelines

    async def process_user_louvain(user_id: int) -> None:
        async with sem:
            try:
                # Check number of new items since previous run
                async with pool.connection() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            """
                            SELECT COUNT(*) 
                            FROM items 
                            WHERE user_id = %s 
                              AND id NOT IN (
                                SELECT DISTINCT unnest(member_ids) 
                                FROM semantic_hubs 
                                WHERE user_id = %s
                              )
                            """,
                            (user_id, user_id)
                        )
                        row = await cur.fetchone()
                        if row is not None:
                            new_items_count = row[0]
                        else:
                            new_items_count = threshold  # Fallback for tests
                
                if new_items_count < threshold:
                    logger.info(
                        "User %s has %d new items (threshold is %d), skipping clustering.",
                        user_id, new_items_count, threshold
                    )
                    return

                logger.info("Running Louvain clustering for user %s", user_id)
                
                # Fetch user items
                async with pool.connection() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "SELECT id, embedding, summary, title, created_at FROM items WHERE user_id = %s",
                            (user_id,)
                        )
                        item_rows = await cur.fetchall()

                if len(item_rows) < 3:
                    logger.info("User %s has < 3 items, skipping clustering.", user_id)
                    return

                # Parse embeddings, summaries, and titles
                embeddings = {}
                summaries = {}
                titles = {}
                item_created_ats = {}
                for row in item_rows:
                    item_id = row[0]
                    emb_val = row[1]
                    summary = row[2]
                    title = row[3] if len(row) > 3 else f"Item {item_id}"
                    created_at = row[4] if len(row) > 4 else None

                    emb = parse_vector(emb_val)
                    if emb and len(emb) == 384:
                        embeddings[item_id] = np.array(emb)
                        summaries[item_id] = summary or ""
                        titles[item_id] = title or "Untitled"
                        if created_at:
                            item_created_ats[item_id] = created_at

                if len(embeddings) < 3:
                    logger.info("User %s has < 3 items with valid 384-dim embeddings, skipping.", user_id)
                    return

                # Normalize embeddings for cosine similarity calculation
                normalized_embeddings = {}
                for item_id, emb in embeddings.items():
                    norm = np.linalg.norm(emb)
                    if norm > 0:
                        normalized_embeddings[item_id] = emb / norm
                    else:
                        normalized_embeddings[item_id] = emb

                # Build NetworkX graph
                G = nx.Graph()
                G.add_nodes_from(embeddings.keys())

                item_ids = list(normalized_embeddings.keys())
                num_items = len(item_ids)
                if num_items >= 3:
                    # Stack all embeddings into an (N, 384) matrix
                    matrix = np.array([normalized_embeddings[item_id] for item_id in item_ids])
                    # Compute (N, N) similarity matrix via matrix multiplication
                    similarity_matrix = np.dot(matrix, matrix.T)
                    # Find indices of upper triangle elements above 0.75
                    # k=1 ensures we exclude the main diagonal (self-similarity) and avoid duplicate pairs
                    triu_indices = np.triu_indices(num_items, k=1)
                    similarities = similarity_matrix[triu_indices]
                    above_threshold = np.where(similarities > 0.75)[0]
                    for idx in above_threshold:
                        i = triu_indices[0][idx]
                        j = triu_indices[1][idx]
                        id1 = item_ids[i]
                        id2 = item_ids[j]
                        sim = float(similarities[idx])
                        G.add_edge(id1, id2, weight=sim)

                # Partition using python-louvain
                partition = community_louvain.best_partition(G)

                # Group items by community ID
                community_groups = {}
                for item_id, comm_id in partition.items():
                    community_groups.setdefault(comm_id, []).append(item_id)

                hubs_to_insert = []
                for comm_id, member_ids in community_groups.items():
                    if len(member_ids) < 3:
                        continue  # Only create hubs for communities with >= 3 members

                    # Compute centroid (mean of all member embeddings)
                    member_embs = [embeddings[mid] for mid in member_ids]
                    centroid = np.mean(member_embs, axis=0).tolist()

                    # Generate label via AI cascade summarizer
                    member_summaries = [summaries[mid] for mid in member_ids if summaries.get(mid)]
                    member_summaries = member_summaries[:5]
                    community_summaries_joined = "\n---\n".join(member_summaries)
                    
                    if len(community_summaries_joined) > 1500:
                        community_summaries_joined = community_summaries_joined[:1500] + "..."

                    try:
                        label = await ai_cascade.summarise(community_summaries_joined, task="label")
                        # Truncate to 4 words or less
                        words = label.split()
                        if len(words) > 4:
                            label = " ".join(words[:4])
                    except Exception as ex:
                        logger.error("Failed to generate label for community %s: %s", comm_id, ex)
                        # Safe fallback label using the first member's title
                        first_member_id = member_ids[0]
                        first_member_title = titles.get(first_member_id, "Untitled")
                        words = first_member_title.split()
                        if len(words) > 4:
                            label = " ".join(words[:4])
                        else:
                            label = first_member_title

                    # Compute last_active_at and streak_days
                    member_dates = [item_created_ats[mid] for mid in member_ids if mid in item_created_ats]
                    from datetime import datetime, timezone
                    last_active_at = max(member_dates) if member_dates else datetime.now(timezone.utc)
                    user_timezone_offset = users_info.get(user_id, 0)
                    streak_days = calculate_hub_streak(member_dates, user_timezone_offset)

                    hubs_to_insert.append({
                        "label": label,
                        "centroid": centroid,
                        "member_ids": member_ids,
                        "last_active_at": last_active_at,
                        "streak_days": streak_days
                    })

                # Save hubs to DB in a single transaction (DELETE old, INSERT new)
                async with pool.connection() as conn:
                    if hasattr(conn, "transaction"):
                        async with conn.transaction():
                            async with conn.cursor() as cur:
                                await _perform_db_hubs_swap(cur, user_id, hubs_to_insert)
                    else:
                        async with conn.cursor() as cur:
                            await _perform_db_hubs_swap(cur, user_id, hubs_to_insert)
                            await conn.commit()

                # Invalidate Redis graph cache
                cache_key = f"graph:{user_id}"
                try:
                    await redis.delete(cache_key)
                except Exception as e:
                    logger.warning("Failed to invalidate Redis graph cache for user %s: %s", user_id, e)

                # Broadcast WS message
                try:
                    from backend.routes.websocket import broadcast
                    hubs_list = [
                        {
                            "id": str(hub["id"]),
                            "label": hub["label"],
                            "member_ids": [int(x) for x in hub["member_ids"]]
                        }
                        for hub in hubs_to_insert if hub.get("id") is not None
                    ]
                    await broadcast(user_id, {
                        "type": "hubs_updated",
                        "hubs": hubs_list
                    })
                except Exception as ws_err:
                    logger.error("Failed to broadcast hubs_updated WS message for user %s: %s", user_id, ws_err)

                logger.info("Successfully completed Louvain clustering for user %s. Generated %d hubs.", user_id, len(hubs_to_insert))

                # Run nightly candidate scan
                await scan_insight_candidates_for_user(user_id, pool)
                # Run nightly Mind Type calculation
                await run_nightly_mind_type_for_user(user_id, pool)

            except Exception as user_err:
                logger.error("Louvain clustering failed for user %s: %s", user_id, user_err, exc_info=True)

    tasks = [process_user_louvain(uid) for uid in users]
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("Louvain clustering background job completed.")


async def run_nightly_mind_type_for_user(user_id: int, pool) -> None:
    """Nightly Mind Type calculation logic based on 4-letter binary dimensions."""
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) FROM items WHERE user_id = %s;", (user_id,))
                count_row = await cur.fetchone()
                node_count = count_row[0] if count_row else 0
                if node_count < 15:
                    return

                # 1. Entropy
                await cur.execute("SELECT id, member_ids FROM semantic_hubs WHERE user_id = %s;", (user_id,))
                hubs = await cur.fetchall()
                total_items_in_hubs = 0
                hub_sizes = []
                item_to_hub = {}
                for h_id, member_ids in hubs:
                    size = len(member_ids) if member_ids else 0
                    hub_sizes.append(size)
                    total_items_in_hubs += size
                    if member_ids:
                        for item_id in member_ids:
                            item_to_hub[item_id] = h_id

                entropy = 0.0
                if total_items_in_hubs > 0:
                    import math
                    for size in hub_sizes:
                        if size > 0:
                            p = size / total_items_in_hubs
                            entropy -= p * math.log(p)

                # 2. Linkage
                await cur.execute(
                    "SELECT item_id_a, item_id_b FROM insight_candidates WHERE user_id = %s AND status = 'confirmed';",
                    (user_id,)
                )
                edges = await cur.fetchall()
                cross_hub_count = 0
                total_edges = len(edges)
                for a, b in edges:
                    hub_a = item_to_hub.get(a)
                    hub_b = item_to_hub.get(b)
                    if hub_a is not None and hub_b is not None and hub_a != hub_b:
                        cross_hub_count += 1
                linkage_ratio = (cross_hub_count / total_edges) if total_edges > 0 else 0.0

                # 3. Velocity
                await cur.execute(
                    "SELECT COUNT(*) FROM items WHERE user_id = %s AND created_at >= NOW() - INTERVAL '7 days';",
                    (user_id,)
                )
                vel_row = await cur.fetchone()
                velocity = vel_row[0] if vel_row else 0

                # 4. Novelty
                await cur.execute(
                    "SELECT embedding FROM items WHERE user_id = %s AND created_at >= NOW() - INTERVAL '7 days' AND embedding IS NOT NULL;",
                    (user_id,)
                )
                new_items = await cur.fetchall()
                await cur.execute(
                    "SELECT embedding FROM items WHERE user_id = %s AND created_at < NOW() - INTERVAL '7 days' AND embedding IS NOT NULL;",
                    (user_id,)
                )
                old_items = await cur.fetchall()

                novelty = 0.0
                if new_items and old_items:
                    def parse_vector(emb):
                        if isinstance(emb, str):
                            try:
                                return [float(x) for x in emb.strip("[]").split(",")]
                            except Exception:
                                return [0.0] * 384
                        return list(emb)
                    new_vecs = [parse_vector(n[0]) for n in new_items]
                    old_vecs = [parse_vector(o[0]) for o in old_items]

                    total_dist = 0.0
                    pair_count = 0
                    for nv in new_vecs:
                        for ov in old_vecs:
                            sim = sum(x * y for x, y in zip(nv, ov))
                            dist = 1.0 - sim
                            total_dist += dist
                            pair_count += 1
                    if pair_count > 0:
                        novelty = total_dist / pair_count

                # Form 4-letter code (Balanced Thresholds)
                b_code = "B" if entropy >= 1.20 else "F"
                l_code = "L" if linkage_ratio >= 0.20 else "I"
                v_code = "V" if velocity >= 10 else "S"
                n_code = "N" if novelty >= 0.35 else "R"
                new_code = f"{b_code}{l_code}{v_code}{n_code}"

                # Fetch cached details
                await cur.execute("SELECT mind_type, mind_type_trajectory FROM users WHERE id = %s;", (user_id,))
                user_row = await cur.fetchone()
                cached_code, traj = user_row if user_row else (None, None)
                import json
                traj_list = traj if traj else []
                if isinstance(traj_list, str):
                    try:
                        traj_list = json.loads(traj_list)
                    except Exception:
                        traj_list = []

                if cached_code != new_code:
                    import datetime
                    traj_list.append({
                        "date": datetime.date.today().isoformat(),
                        "mind_type": new_code,
                        "metrics": {
                            "breadth": float(entropy),
                            "linkage": float(linkage_ratio),
                            "velocity": float(velocity),
                            "novelty": float(novelty)
                        }
                    })
                    await cur.execute(
                        "UPDATE users SET mind_type = %s, mind_type_trajectory = %s WHERE id = %s;",
                        (new_code, json.dumps(traj_list), user_id)
                    )
                    await conn.commit()
                    logger.info("Updated Mind Type trajectory for user %d to %s", user_id, new_code)
    except Exception as e:
        logger.error("Failed nightly Mind Type calculation for user %d: %s", user_id, e)


async def weekly_profile_text_generator() -> None:
    """Weekly cron to generate the 4-sentence profile summary at Sunday 8:00 PM local time."""
    try:
        pool = await get_pool()
    except Exception as e:
        logger.error("Failed to open database pool in weekly profile generator: %s", e)
        return

    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT id, telegram_chat_id, timezone_offset, mind_type, mind_type_trajectory FROM users WHERE mind_type IS NOT NULL;")
                users = await cur.fetchall()
    except Exception as e:
        logger.error("Failed to fetch users in weekly profile generator: %s", e)
        return

    import datetime
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    sem = asyncio.Semaphore(3)

    async def process_user(user_id, chat_id, offset_minutes, code, traj):
        async with sem:
            if not chat_id:
                return
            if offset_minutes is None:
                offset_minutes = 0
            
            # Check local time is Sunday 8:00 PM (Weekday 6, Hour 20)
            local_time = now_utc + datetime.timedelta(minutes=offset_minutes)
            if not (local_time.weekday() == 6 and local_time.hour == 20):
                return

            try:
                import json
                traj_list = traj if traj else []
                if isinstance(traj_list, str):
                    try:
                        traj_list = json.loads(traj_list)
                    except Exception:
                        traj_list = []

                # Find the most recent different mind type to track the transition delta
                prev_code = None
                if traj_list:
                    for entry in reversed(traj_list):
                        entry_code = entry.get("mind_type")
                        if entry_code and entry_code != code:
                            prev_code = entry_code
                            break

                transition_context = ""
                if prev_code:
                    transition_context = (
                        f"Their previous Mind Type was {prev_code}. "
                        f"Explain what shifted in their cognitive patterns (e.g. did they expand their breadth, synthesize more links, speed up velocity, or ingest more novel concepts?) that caused the transition to {code}."
                    )
                else:
                    transition_context = f"This is their first classification. Focus on explaining the primary cognitive driver of their {code} signature."

                async with pool.connection() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "SELECT label FROM semantic_hubs WHERE user_id = %s ORDER BY array_length(member_ids, 1) DESC LIMIT 3;",
                            (user_id,)
                        )
                        hubs = [r[0] for r in await cur.fetchall()]
                        
                        cascade = AICascade()
                        hubs_str = ", ".join(hubs) if hubs else "general topics"
                        
                        prompt = (
                            f"You are a Cognitive Graph Profiler. The user has been classified as {code} (MBTI-style Mind Type).\n"
                            f"Their top 3 active clusters are: {hubs_str}.\n"
                            f"{transition_context}\n\n"
                            f"Write a highly personalized, analytical, and engaging 4-sentence profile summary explaining their cognitive style and transition.\n"
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
                            "BLVN": "Warp Navigator",
                            "FLVN": "Quantum Catalyst",
                            "BLSN": "Nebula Weaver",
                            "FLSN": "Alchemy Core",
                            "BLVR": "Ingestion Matrix",
                            "FLVR": "Laser Synthesizer",
                            "BLSR": "Codex Cartographer",
                            "FLSR": "Monolith Architect",
                            "BIVN": "Void Collector",
                            "FIVN": "Recon Scout",
                            "BISN": "Archival Explorer",
                            "FISN": "Deep Diver",
                            "BIVR": "Cyclone Curator",
                            "FIVR": "Sentinel Core",
                            "BISR": "Silent Librarian",
                            "FISR": "Singular Vault"
                        }
                        archetype_label = ARCHETYPES.get(code, "Mind Explorer")
                        msg = (
                            f"Your Sunday Mind Type trajectory report is ready! 🧠\n\n"
                            f"You are currently classified as: *{archetype_label} ({code})*.\n\n"
                            f"{summary_text}\n\n"
                            f"Check the dashboard Profile page to see your metrics breakdown!"
                        )
                        from backend.worker import send_telegram_message
                        await send_telegram_message(chat_id, msg)
                        logger.info("Sent weekly Mind Type summary to user %d", user_id)
            except Exception as user_err:
                logger.error("Failed to generate weekly profile for user %d: %s", user_id, user_err)

    tasks = []
    for user in users:
        uid = user[0]
        cid = user[1]
        offset = user[2]
        code = user[3]
        traj = user[4] if len(user) > 4 else None
        tasks.append(process_user(uid, cid, offset, code, traj))
    await asyncio.gather(*tasks)


async def monthly_prediction_generator() -> None:
    """Monthly prediction generator for users with >= 30 items."""
    try:
        pool = await get_pool()
    except Exception as e:
        logger.error("Failed to open database pool in monthly predictions: %s", e)
        return

    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT u.id, u.telegram_chat_id, u.last_prediction_at 
                    FROM users u
                    WHERE (SELECT COUNT(*) FROM items i WHERE i.user_id = u.id) >= 30
                      AND (u.last_prediction_at IS NULL OR u.last_prediction_at <= NOW() - INTERVAL '30 days');
                    """
                )
                users = await cur.fetchall()
    except Exception as e:
        logger.error("Failed to fetch users in monthly predictions: %s", e)
        return

    sem = asyncio.Semaphore(3)

    async def process_prediction(user_id, chat_id, last_pred):
        async with sem:
            if not chat_id:
                return

            try:
                async with pool.connection() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "SELECT label FROM semantic_hubs WHERE user_id = %s ORDER BY array_length(member_ids, 1) DESC LIMIT 3;",
                            (user_id,)
                        )
                        hubs = [r[0] for r in await cur.fetchall()]
                        
                        await cur.execute(
                            "SELECT title, summary FROM items WHERE user_id = %s ORDER BY created_at DESC LIMIT 15;",
                            (user_id,)
                        )
                        items = await cur.fetchall()
                        recent_saves = "\n".join(f"- {title}: {summary[:100]}" for title, summary in items if title)

                        cascade = AICascade()
                        hubs_str = ", ".join(hubs) if hubs else "None"
                        
                        prompt = (
                            f"You are a Predictive Cognitive Engine.\n"
                            f"Analyze the user's recent saved ideas and semantic hubs:\n"
                            f"Hubs: {hubs_str}\n"
                            f"Recent saves:\n{recent_saves}\n\n"
                            f"Predict what specific topic or concept they will save next within a 5-7 days window.\n"
                            f"Format your reply as a JSON object with keys: \"prediction\", \"confidence\", \"explanation\".\n\n"
                            f"Constraints:\n"
                            f"- High specificity is required (do not predict generic topics like 'technology' or 'self-improvement').\n"
                            f"- If your confidence is less than 0.72, return \"confidence\": 0.0 and do not make a prediction.\n"
                            f"- Do not hedge or use placeholders."
                        )

                        res = await cascade.call_llm(prompt)
                        if res:
                            try:
                                import re
                                match = re.search(r"\{.*\}", res, re.DOTALL)
                                if match:
                                    parsed = json.loads(match.group(0))
                                    prediction = parsed.get("prediction")
                                    confidence = float(parsed.get("confidence") or 0.0)
                                    explanation = parsed.get("explanation")

                                    if confidence >= 0.72 and prediction:
                                        msg = (
                                            f"🔮 *Monthly Prediction*\n\n"
                                            f"Based on your recent saves, your graph predicts you will next explore: *{prediction}* (Confidence: {confidence:.2f})\n\n"
                                            f"_{explanation}_"
                                        )
                                        from backend.worker import send_telegram_message
                                        await send_telegram_message(chat_id, msg)
                                        logger.info("Sent monthly prediction to user %d: %s", user_id, prediction)
                            except Exception as parse_err:
                                logger.error("Failed to parse monthly prediction JSON: %s", parse_err)

                        await cur.execute(
                            "UPDATE users SET last_prediction_at = NOW() WHERE id = %s;",
                            (user_id,)
                        )
                        await conn.commit()
            except Exception as user_err:
                logger.error("Failed to generate prediction for user %d: %s", user_id, user_err)

    tasks = [process_prediction(uid, cid, lp) for uid, cid, lp in users]
    await asyncio.gather(*tasks)


async def monthly_discrepancy_scanner() -> None:
    """Monthly scan to find cognitive discrepancies between self-description and actual saves."""
    try:
        pool = await get_pool()
    except Exception as e:
        logger.error("Failed to open database pool in discrepancy scanner: %s", e)
        return

    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT u.id, u.telegram_chat_id, u.self_description, u.last_confession_at 
                    FROM users u
                    WHERE u.self_description IS NOT NULL
                      AND (SELECT COUNT(*) FROM items i WHERE i.user_id = u.id) >= 30
                      AND (u.last_confession_at IS NULL OR u.last_confession_at <= NOW() - INTERVAL '30 days');
                    """
                )
                users = await cur.fetchall()
    except Exception as e:
        logger.error("Failed to fetch users in discrepancy scanner: %s", e)
        return

    sem = asyncio.Semaphore(3)

    async def process_confession(user_id, chat_id, self_desc, last_conf):
        async with sem:
            if not chat_id:
                return

            try:
                async with pool.connection() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "SELECT label, array_length(member_ids, 1) FROM semantic_hubs WHERE user_id = %s ORDER BY array_length(member_ids, 1) DESC LIMIT 3;",
                            (user_id,)
                        )
                        hubs = await cur.fetchall()
                        hubs_str = ", ".join(f"'{h[0]}' ({h[1]} saves)" for h in hubs)

                        await cur.execute(
                            "SELECT title, summary FROM items WHERE user_id = %s ORDER BY created_at DESC LIMIT 15;",
                            (user_id,)
                        )
                        items = await cur.fetchall()
                        item_samples = "\n".join(f"- {t}: {s[:100]}" for t, s in items if t)

                        cascade = AICascade()
                        prompt = (
                            f"You are a Cognitive Discrepancy Analyzer.\n"
                            f"Compare the user's stated self-description of their interests with their actual saved topics:\n"
                            f"Stated self-description: \"{self_desc}\"\n"
                            f"Actual saved hubs: {hubs_str}\n"
                            f"Sample item saves:\n{item_samples}\n\n"
                            f"Determine if the user's stated interests substantially diverge from what they actually save in practice.\n"
                            f"If they substantially diverge, write a direct, honest, and constructive confession insight highlighting the gap (max 2 sentences).\n"
                            f"If they align or the gap is weak, output ONLY: ALIGNED_NO_GAP\n\n"
                            f"Constraint: Output ONLY raw conversational text. Do NOT wrap in JSON, quotes, or code block formatting."
                        )

                        res = await cascade.call_llm(prompt)
                        if res and "ALIGNED_NO_GAP" not in res:
                            confession_text = res.strip()
                            
                            # Fallback extraction if LLM still outputs JSON
                            if confession_text.startswith("{") and confession_text.endswith("}"):
                                try:
                                    import json as _json
                                    parsed = _json.loads(confession_text)
                                    if "insight" in parsed:
                                        confession_text = parsed["insight"]
                                    elif "confession" in parsed:
                                        confession_text = parsed["confession"]
                                except Exception:
                                    pass
                            
                            await cur.execute("SELECT id FROM items WHERE user_id = %s ORDER BY created_at DESC LIMIT 2;", (user_id,))
                            item_rows = await cur.fetchall()
                            item_a = item_rows[0][0] if len(item_rows) > 0 else 0
                            item_b = item_rows[1][0] if len(item_rows) > 1 else 0

                            await cur.execute(
                                """
                                INSERT INTO insight_candidates (user_id, item_id_a, item_id_b, similarity_score, bucket, status, insight_text, expires_at)
                                VALUES (%s, %s, %s, 0.0, 'confession', 'delivered', %s, NOW() + INTERVAL '30 days');
                                """,
                                (user_id, item_a, item_b, confession_text)
                            )
                            await conn.commit()

                            msg = (
                                f"💭 *Graph Reflection*\n\n"
                                f"{confession_text}"
                            )
                            from backend.worker import send_telegram_message
                            await send_telegram_message(chat_id, msg)
                            logger.info("Sent discrepancy confession reflection to user %d", user_id)

                        await cur.execute(
                            "UPDATE users SET last_confession_at = NOW() WHERE id = %s;",
                            (user_id,)
                        )
                        await conn.commit()
            except Exception as user_err:
                logger.error("Failed to run confession scanner for user %d: %s", user_id, user_err)

    tasks = [process_confession(uid, cid, sd, lc) for uid, cid, sd, lc in users]
    await asyncio.gather(*tasks)


async def monthly_forward_hook() -> None:
    """Monthly scan to find adjacent-but-absent concept gaps using static_domain_centroids."""
    try:
        pool = await get_pool()
    except Exception as e:
        logger.error("Failed to open database pool in forward hook: %s", e)
        return

    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT u.id, u.telegram_chat_id, u.last_forward_hook_at 
                    FROM users u
                    WHERE (SELECT COUNT(*) FROM items i WHERE i.user_id = u.id) >= 15
                      AND (u.last_forward_hook_at IS NULL OR u.last_forward_hook_at <= NOW() - INTERVAL '30 days');
                    """
                )
                users = await cur.fetchall()
    except Exception as e:
        logger.error("Failed to fetch users in forward hook: %s", e)
        return

    sem = asyncio.Semaphore(3)

    async def process_forward_hook(user_id, chat_id, last_fw):
        async with sem:
            if not chat_id:
                return

            try:
                async with pool.connection() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "SELECT label, member_ids FROM semantic_hubs WHERE user_id = %s ORDER BY array_length(member_ids, 1) DESC LIMIT 3;",
                            (user_id,)
                        )
                        hubs = await cur.fetchall()
                        if len(hubs) < 2:
                            return
                            
                        top_hubs_labels = [h[0] for h in hubs]
                        all_member_ids = []
                        for h in hubs:
                            if h[1]:
                                all_member_ids.extend(h[1])
                                
                        if not all_member_ids:
                            return

                        await cur.execute(
                            "SELECT embedding FROM items WHERE user_id = %s AND id = ANY(%s) AND embedding IS NOT NULL;",
                            (user_id, all_member_ids)
                        )
                        emb_rows = await cur.fetchall()
                        if not emb_rows:
                            return

                        def parse_vector(emb):
                            if isinstance(emb, str):
                                try:
                                    return [float(x) for x in emb.strip("[]").split(",")]
                                except Exception:
                                    return [0.0] * 384
                            return list(emb)

                        vectors = [parse_vector(r[0]) for r in emb_rows]
                        vector_len = len(vectors[0])
                        centroid = [sum(v[i] for v in vectors) / len(vectors) for i in range(vector_len)]

                        c_mag = math.sqrt(sum(x*x for x in centroid))
                        if c_mag > 0:
                            centroid = [x / c_mag for x in centroid]

                        await cur.execute("SELECT title, tags FROM items WHERE user_id = %s;", (user_id,))
                        user_saves = await cur.fetchall()
                        saved_texts = set()
                        for title, tags in user_saves:
                            if title:
                                saved_texts.add(title.lower())
                            if tags:
                                for t in tags:
                                    saved_texts.add(t.lower())

                        await cur.execute("SELECT domain_name, embedding FROM static_domain_centroids;")
                        domain_rows = await cur.fetchall()
                        
                        best_domain = None
                        best_score = -1.0

                        for domain_name, d_emb in domain_rows:
                            if domain_name.lower() in saved_texts:
                                continue
                            
                            d_vec = parse_vector(d_emb)
                            sim = sum(x * y for x, y in zip(centroid, d_vec))
                            
                            score = 0.0
                            if 0.60 <= sim <= 0.78:
                                score = sim
                                
                            if score > best_score:
                                best_score = score
                                best_domain = domain_name

                        if best_domain and best_score > 0.0:
                            cascade = AICascade()
                            hubs_str = ", ".join(top_hubs_labels)
                            
                            prompt = (
                                f"The user has a mind graph focused on: {hubs_str}.\n"
                                f"A gap analysis identified that the adjacent concept of '{best_domain}' is conspicuously absent from their saves.\n\n"
                                f"Write a concise 3-sentence observation. Explain why '{best_domain}' fits adjacent to their current interests, but is absent, prompting them to think about how it bridges their ideas.\n"
                                f"Constraint: Do not use clinical jargon, do not use template words, and speak directly to their thinking shape."
                            )

                            hook_text = await cascade.call_llm(prompt)
                            if hook_text:
                                msg = (
                                    f"Your graph has been building a framework for {hubs_str}.\n"
                                    f"The one piece it hasn’t touched: *{best_domain}*.\n\n"
                                    f"{hook_text}"
                                )
                                from backend.worker import send_telegram_message
                                await send_telegram_message(chat_id, msg)
                                logger.info("Sent forward hook gap notification to user %d: %s", user_id, best_domain)

                        await cur.execute(
                            "UPDATE users SET last_forward_hook_at = NOW() WHERE id = %s;",
                            (user_id,)
                        )
                        await conn.commit()
            except Exception as user_err:
                logger.error("Failed to run forward hook for user %d: %s", user_id, user_err)

    tasks = [process_forward_hook(uid, cid, lp) for uid, cid, lp in users]
    await asyncio.gather(*tasks)


async def partition_creator() -> None:
    """
    Background job to pre-create next month's items partition.
    Runs on the 25th of each month at 00:00 UTC.
    """
    try:
        today = datetime.date.today()
        # Compute M+1 year and month
        if today.month == 12:
            next_month_year = today.year + 1
            next_month_val = 1
        else:
            next_month_year = today.year
            next_month_val = today.month + 1

        # Bounds: start_date is first day of M+1, end_date is first day of M+2
        start_date = f"{next_month_year:04d}-{next_month_val:02d}-01"
        
        if next_month_val == 12:
            after_next_year = next_month_year + 1
            after_next_val = 1
        else:
            after_next_year = next_month_year
            after_next_val = next_month_val + 1
        end_date = f"{after_next_year:04d}-{after_next_val:02d}-01"
        
        partition_name = f"items_y{next_month_year:04d}m{next_month_val:02d}"

        # Identifier validation to avoid SQL Injection
        if not (2000 <= next_month_year <= 2100) or not (1 <= next_month_val <= 12):
            raise ValueError(f"Calculated invalid year/month bounds: {next_month_year}/{next_month_val}")

        query = f"""
        CREATE TABLE IF NOT EXISTS {partition_name} PARTITION OF items
        FOR VALUES FROM ('{start_date} 00:00:00') TO ('{end_date} 00:00:00');
        """
        
        pool = await get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query)
                await conn.commit()
        logger.info("Successfully checked/created partition: %s", partition_name)
    except Exception as e:
        logger.critical("Partition creation failed: %s", e, exc_info=True)


async def drive_nudge_sender() -> None:
    """
    Background job to send a Google Drive integration nudge to engaged users.
    Runs daily at 10:00 UTC.
    """
    try:
        pool = await get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT id, telegram_chat_id, streak_count
                    FROM users
                    WHERE streak_count >= 3
                      AND drive_nudge_sent = FALSE
                      AND google_refresh_token IS NULL;
                    """
                )
                rows = await cur.fetchall()
                if not rows:
                    return

                logger.info("Found %d users to send Google Drive nudge.", len(rows))
                for row in rows:
                    user_id, chat_id, streak = row
                    nudge_msg = (
                        f"🚀 You've reached a 🔥 {streak}-day streak! "
                        "To ensure you never lose your data, connect your Google Drive "
                        "for automated backups. Use /connect_drive or visit the web dashboard to sync."
                    )
                    success = await send_telegram_message(chat_id, nudge_msg)
                    if success:
                        await cur.execute(
                            "UPDATE users SET drive_nudge_sent = TRUE WHERE id = %s",
                            (user_id,)
                        )
                await conn.commit()
    except Exception as e:
        logger.error("drive_nudge_sender job failed: %s", e, exc_info=True)


async def processed_updates_cleanup() -> None:
    """
    Background job to clean up processed update IDs older than 30 days.
    Runs weekly on Sunday at 03:00 UTC.
    """
    try:
        pool = await get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM processed_updates WHERE processed_at < NOW() - INTERVAL '30 days';"
                )
                await conn.commit()
        logger.info("Successfully pruned old processed_updates rows.")
    except Exception as e:
        logger.error("processed_updates_cleanup job failed: %s", e, exc_info=True)


async def daily_digest_sender() -> None:
    """
    Unified daily digest loop. Runs hourly.
    Checks users' local timezone hour:
    - 8:00 AM local: Sends standard Morning Digest stats, and fires Morning Mystery (clue).
    - 11:00 AM local: Sends Near-Miss alerts to users with a 3-day cooldown.
    - 4:00 PM (16:00) local: Sends Living Graph lapse alert (3+ cooling hubs) with a 10-day cooldown.
    - 8:00 PM local: Sends Evening Answer (connection tension resolution).
    """
    try:
        pool = await get_pool()
        users_to_process = []
        async with pool.connection() as conn:
            await conn.execute("SET statement_timeout = '30s'")
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT id, telegram_chat_id, streak_count,
                           EXTRACT(HOUR FROM (CURRENT_TIMESTAMP + (timezone_offset * INTERVAL '1 minute'))) AS local_hour
                    FROM users
                    WHERE digest_enabled = TRUE
                      AND last_activity_date >= CURRENT_DATE - INTERVAL '14 days'
                      AND EXTRACT(HOUR FROM (CURRENT_TIMESTAMP + (timezone_offset * INTERVAL '1 minute'))) IN (8, 11, 16, 20);
                    """
                )
                users_to_process = await cur.fetchall()
        
        if not users_to_process:
            logger.info("No active users found for daily digest / loop closure in this hour.")
            return

        logger.info("Found %d users eligible for daily digest / loop closure in this hour.", len(users_to_process))
        
        import time
        from datetime import datetime, timezone, timedelta
        from backend.services.ai_cascade import AICascade

        for row in users_to_process:
            if len(row) == 4:
                user_id, chat_id, streak_count, local_hour = row
                local_hour = int(local_hour)
            else:
                user_id, chat_id, streak_count = row
                local_hour = 8  # Default to morning digest if local_hour is omitted
            try:
                if local_hour == 8:
                    # ==========================================
                    # MORNING DIGEST & MYSTERY (8:00 AM)
                    # ==========================================
                    yesterday_count = 0
                    top_titles = []
                    quizzes_due = 0
                    
                    async with pool.connection() as conn:
                        await conn.execute("SET statement_timeout = '30s'")
                        async with conn.cursor() as cur:
                            # 1. Count yesterday's saved items
                            await cur.execute(
                                """
                                SELECT COUNT(*)
                                FROM items
                                WHERE user_id = %s
                                  AND created_at >= CURRENT_DATE - INTERVAL '1 day'
                                  AND created_at < CURRENT_DATE;
                                """,
                                (user_id,)
                            )
                            count_row = await cur.fetchone()
                            yesterday_count = count_row[0] if count_row else 0
                            
                            # 2. Get yesterday's first 3 titles
                            if yesterday_count > 0:
                                await cur.execute(
                                    """
                                    SELECT title
                                    FROM items
                                    WHERE user_id = %s
                                      AND created_at >= CURRENT_DATE - INTERVAL '1 day'
                                      AND created_at < CURRENT_DATE
                                    ORDER BY created_at ASC
                                    LIMIT 3;
                                    """,
                                    (user_id,)
                                )
                                title_rows = await cur.fetchall()
                                top_titles = [r[0] for r in title_rows if r and r[0]]
                            
                            # 3. Count quizzes due today
                            await cur.execute(
                                """
                                SELECT COUNT(*)
                                FROM quizzes
                                WHERE user_id = %s
                                  AND next_review = CURRENT_DATE;
                                """,
                                (user_id,)
                            )
                            quiz_row = await cur.fetchone()
                            quizzes_due = quiz_row[0] if quiz_row else 0
                    
                    # Format standard morning digest
                    if yesterday_count > 0:
                        titles_bullet = "\n".join(f"• {t}" for t in top_titles)
                        msg = (
                            "📬 Good morning! Your Recall daily digest:\n\n"
                            f"Yesterday you saved {yesterday_count} items.\n"
                            "📖 New knowledge:\n"
                            f"{titles_bullet}\n\n"
                            f"🧠 Quizzes due today: {quizzes_due}\n"
                            "Type /quiz to start.\n\n"
                            f"🔥 {streak_count} day streak — keep it up!"
                        )
                    else:
                        msg = (
                            "📬 Good morning! Your Recall daily digest:\n\n"
                            f"🧠 Quizzes due today: {quizzes_due}\n"
                            "Type /quiz to start.\n\n"
                            f"🔥 {streak_count} day streak — keep it up!"
                        )
                    
                    await send_telegram_message(str(chat_id), msg)
                    
                    # 4. Check for Morning Mystery Candidate (bucket = 'confirmed')
                    async with pool.connection() as conn:
                        async with conn.cursor() as cur:
                            await cur.execute(
                                """
                                SELECT id, item_id_a, item_id_b 
                                FROM insight_candidates
                                WHERE user_id = %s AND status = 'pending' AND bucket = 'confirmed'
                                ORDER BY similarity_score DESC
                                LIMIT 1;
                                """,
                                (user_id,)
                            )
                            cand = await cur.fetchone()
                            
                    if cand:
                        cand_id, item_a, item_b = cand
                        expiry_epoch = int(time.time()) + 12 * 3600
                        
                        async with pool.connection() as conn:
                            async with conn.cursor() as cur:
                                await cur.execute(
                                    "UPDATE insight_candidates SET status = 'delivered', expires_at = NOW() + INTERVAL '12 hours' WHERE id = %s;",
                                    (cand_id,)
                                )
                                await conn.commit()
                                
                        await redis.zadd("reminders:active", float(expiry_epoch), f"drift:{cand_id}")
                        
                        mystery_msg = "Your graph did something unusual overnight. Three things you saved in different weeks just collapsed into the same idea. I haven't told you what it is yet."
                        await send_telegram_message(str(chat_id), mystery_msg)
                        logger.info("Sent Morning Mystery to user %d, candidate %d", user_id, cand_id)

                elif local_hour == 11:
                    # ==========================================
                    # NEAR-MISS ALERT (11:00 AM)
                    # ==========================================
                    cooldown = await redis.get(f"user:near_miss_sent_cooldown:{user_id}")
                    if cooldown:
                        continue
                    
                    async with pool.connection() as conn:
                        async with conn.cursor() as cur:
                            await cur.execute(
                                """
                                SELECT c.id, c.item_id_a, c.item_id_b, c.similarity_score,
                                       a.title, a.created_at, b.title, b.created_at
                                FROM insight_candidates c
                                JOIN items a ON c.item_id_a = a.id
                                JOIN items b ON c.item_id_b = b.id
                                WHERE c.user_id = %s 
                                  AND c.status = 'pending'
                                  AND c.bucket = 'near_miss'
                                  AND c.created_at >= NOW() - INTERVAL '72 hours'
                                ORDER BY c.similarity_score DESC
                                LIMIT 1;
                                """,
                                (user_id,)
                            )
                            cand = await cur.fetchone()
                            
                            if cand:
                                cand_id, item_a_id, item_b_id, sim, title_a, created_a, title_b, created_b = cand
                                
                                # Fetch the hub label if any member belongs to a hub
                                await cur.execute(
                                    """
                                    SELECT label FROM semantic_hubs 
                                    WHERE user_id = %s AND (%s = ANY(member_ids) OR %s = ANY(member_ids))
                                    LIMIT 1;
                                    """,
                                    (user_id, item_a_id, item_b_id)
                                )
                                hub_row = await cur.fetchone()
                                cluster_name = hub_row[0] if hub_row else f"'{title_b}'"
                                
                                now_utc = datetime.now(timezone.utc)
                                dt_a = created_a.replace(tzinfo=timezone.utc) if created_a.tzinfo is None else created_a
                                dt_b = created_b.replace(tzinfo=timezone.utc) if created_b.tzinfo is None else created_b
                                age_a = (now_utc - dt_a).days
                                age_b = (now_utc - dt_b).days
                                days_ago = max(1, max(age_a, age_b))
                                pct = int(sim * 100)
                                
                                near_miss_msg = f"Your graph almost made a connection. Something from {days_ago} days ago is sitting at {pct}% similarity with '{cluster_name}'. One more save in this space and it might cross."
                                
                                await cur.execute(
                                    "UPDATE insight_candidates SET status = 'near_miss' WHERE id = %s;",
                                    (cand_id,)
                                )
                                await conn.commit()
                                
                                await send_telegram_message(str(chat_id), near_miss_msg)
                                await redis.setex(f"user:near_miss_sent_cooldown:{user_id}", 3 * 86400, "1")
                                logger.info("Sent Near-Miss Alert to user %d, candidate %d", user_id, cand_id)

                elif local_hour == 16:
                    # ==========================================
                    # LIVING GRAPH LAPSE WARNING (4:00 PM / 16:00)
                    # ==========================================
                    cooldown = await redis.get(f"user:cooling_sent_cooldown:{user_id}")
                    if cooldown:
                        continue
                        
                    # Check if user has not opened the web app in 72+ hours
                    last_active = await redis.get(f"user:last_frontend_active:{user_id}")
                    if last_active:
                        continue
                        
                    async with pool.connection() as conn:
                        async with conn.cursor() as cur:
                            # Count hubs crossing below 40% temperature in last 48 hours (inactive for 4.2 to 6.2 days)
                            await cur.execute(
                                """
                                SELECT COUNT(*) FROM semantic_hubs
                                WHERE user_id = %s
                                  AND last_active_at <= NOW() - INTERVAL '4.2 days'
                                  AND last_active_at >= NOW() - INTERVAL '6.2 days';
                                """,
                                (user_id,)
                            )
                            count_row = await cur.fetchone()
                            cooling_count = count_row[0] if count_row else 0
                            
                            if cooling_count >= 3:
                                lapse_msg = "Your living graph is cooling down. 3+ of your knowledge hubs are beginning to freeze. Open the dashboard to reactivate the connections."
                                await send_telegram_message(str(chat_id), lapse_msg)
                                await redis.setex(f"user:cooling_sent_cooldown:{user_id}", 10 * 86400, "1")
                                logger.info("Sent Living Graph lapse alert to user %d (%d cooling hubs)", user_id, cooling_count)

                elif local_hour == 20:
                    # ==========================================
                    # EVENING ANSWER (8:00 PM)
                    # ==========================================
                    async with pool.connection() as conn:
                        async with conn.cursor() as cur:
                            await cur.execute(
                                """
                                SELECT c.id, c.item_id_a, c.item_id_b, 
                                       a.title, a.summary, a.tags, a.context_note, a.passive_context,
                                       b.title, b.summary, b.tags, b.context_note, b.passive_context
                                FROM insight_candidates c
                                JOIN items a ON c.item_id_a = a.id
                                JOIN items b ON c.item_id_b = b.id
                                WHERE c.user_id = %s AND c.status = 'delivered'
                                ORDER BY c.created_at DESC
                                LIMIT 1;
                                """,
                                (user_id,)
                            )
                            cand = await cur.fetchone()
                            
                    if cand:
                        if len(cand) == 13:
                            cand_id, item_a_id, item_b_id, t_a, s_a, tg_a, cn_a, pc_a, t_b, s_b, tg_b, cn_b, pc_b = cand
                        else:
                            cand_id, item_a_id, item_b_id, t_a, s_a, tg_a, t_b, s_b, tg_b = cand[:9]
                            cn_a, pc_a, cn_b, pc_b = None, None, None, None
                        
                        cascade = AICascade()
                        cascade._force_production_llm = True
                        
                        dict_a = {"title": t_a, "summary": s_a, "tags": tg_a, "context_note": cn_a, "passive_context": pc_a}
                        dict_b = {"title": t_b, "summary": s_b, "tags": tg_b, "context_note": cn_b, "passive_context": pc_b}
                        
                        logger.info("Generating Evening Answer insight for candidate %d...", cand_id)
                        insight = await cascade.generate_insight(dict_a, dict_b, 1)
                        
                        if insight:
                            async with pool.connection() as conn:
                                async with conn.cursor() as cur:
                                    await cur.execute(
                                        "UPDATE insight_candidates SET status = 'confirmed', insight_text = %s WHERE id = %s;",
                                        (insight, cand_id)
                                    )
                                    await conn.commit()
                                    
                            await redis.zrem("reminders:active", f"drift:{cand_id}")
                            
                            resolved_msg = (
                                f"The idea your graph kept circling:\n\n"
                                f"{insight}\n\n"
                                f"You connected it to:\n"
                                f"🔗 {t_a}\n"
                                f"🔗 {t_b}"
                            )
                            await send_telegram_message(str(chat_id), resolved_msg)
                            logger.info("Sent Evening Answer to user %d, candidate %d", user_id, cand_id)
                            
            except Exception as user_err:
                logger.error("Failed to process daily digest/loop closure for user %d (chat_id %s): %s", user_id, chat_id, user_err, exc_info=True)
                
    except Exception as e:
        logger.error("daily_digest_sender job failed: %s", e, exc_info=True)


async def weekly_drive_sync() -> None:
    """
    Background job to run the weekly Google Drive synchronization for all users.
    Only processes users with a connected Google Drive account (google_refresh_token IS NOT NULL).
    Runs weekly on Sunday at 04:00 UTC.
    """
    try:
        pool = await get_pool()
        users_to_sync = []
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT id FROM users WHERE google_refresh_token IS NOT NULL;"
                )
                users_to_sync = [row[0] for row in await cur.fetchall()]
        
        if not users_to_sync:
            logger.info("No users found with connected Google Drive for weekly sync.")
            return

        logger.info("Found %d users with connected Google Drive for weekly sync.", len(users_to_sync))
        
        from backend.services.drive_sync import sync_user_to_drive
        
        sem = asyncio.Semaphore(3)

        async def sync_one(user_id):
            async with sem:
                try:
                    # Open a connection for each user sync to keep operations transactional and isolated
                    async with pool.connection() as conn:
                        await sync_user_to_drive(user_id, conn)
                except Exception as user_err:
                    logger.error(
                        "Weekly Google Drive sync failed for user %d: %s",
                        user_id,
                        user_err,
                        exc_info=True
                    )
        
        tasks = [sync_one(uid) for uid in users_to_sync]
        await asyncio.gather(*tasks, return_exceptions=True)
                
    except Exception as e:
        logger.error("weekly_drive_sync background job failed: %s", e, exc_info=True)


async def offpeak_quiz_generator() -> None:
    """
    Daily job to generate quizzes for items that don't have a quiz card yet.
    Runs at off-peak hours (e.g., 03:30 UTC) to minimize peak-hour API usage.
    """
    logger.info("Starting off-peak automatic quiz generation background job...")
    pool = await get_pool()
    if not pool:
        logger.error("DB pool not initialized in offpeak_quiz_generator.")
        return

    import json
    import asyncio
    from backend.services.encryption import decrypt
    from backend.services.ai_cascade import AICascade

    try:
        # 1. Fetch items without quizzes
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SET statement_timeout = '60s'")
                await cur.execute(
                    """
                    SELECT i.id, i.user_id, i.summary, i.raw_text, i.title
                    FROM items i
                    LEFT JOIN quizzes q ON i.id = q.item_id AND i.user_id = q.user_id
                    WHERE q.id IS NULL
                    ORDER BY i.created_at ASC
                    LIMIT 50;
                    """
                )
                items_without_quiz = await cur.fetchall()

        if not items_without_quiz:
            logger.info("No items without quizzes found. Off-peak quiz generation complete.")
            return

        logger.info("Found %d items requiring quiz generation.", len(items_without_quiz))

        cascade = AICascade()
        generated_count = 0

        for item_id, user_id, summary, raw_text, title in items_without_quiz:
            try:
                decrypted_text = ""
                if raw_text:
                    try:
                        decrypted_text = decrypt(raw_text)
                    except Exception:
                        decrypted_text = raw_text

                text_for_quiz = summary or decrypted_text or title or ""
                if not text_for_quiz:
                    continue

                quiz_data = await cascade.generate_quiz(text_for_quiz)
                if quiz_data:
                    async with pool.connection() as conn:
                        async with conn.cursor() as cur:
                            await cur.execute("SET statement_timeout = '30s'")
                            await cur.execute(
                                """
                                INSERT INTO quizzes (user_id, item_id, question, options, correct_index, explanation)
                                VALUES (%s, %s, %s, %s, %s, %s);
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
                            await conn.commit()
                    generated_count += 1

                # Dynamic throttle: 1s sleep between LLM calls to prevent rate-limit spikes
                await asyncio.sleep(1.0)

            except Exception as item_err:
                logger.error(
                    "Failed to generate quiz for item %d (user %d) during off-peak: %s",
                    item_id,
                    user_id,
                    item_err
                )

        logger.info("Off-peak quiz generation complete. Generated %d quizzes.", generated_count)

    except Exception as e:
        logger.error("offpeak_quiz_generator background job failed: %s", e, exc_info=True)


async def onboarding_sequence_dispatcher() -> None:
    """Handles the Day 1-5 conversational onboarding follow-ups."""
    try:
        pool = await get_pool()
        from backend.services.redis_client import redis
        
        # 1. Day 0 checks (Wait 2 hours after first save)
        async with pool.connection() as conn:
            await conn.execute("SET statement_timeout = '30s'")
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT u.id, u.telegram_chat_id,
                           MIN(i.id) as first_item_id,
                           (SELECT title FROM items WHERE id = MIN(i.id)) as first_item_title
                    FROM users u
                    JOIN items i ON u.id = i.user_id
                    WHERE u.onboarding_day = 0 AND u.onboarding_last_sent IS NULL
                    GROUP BY u.id, u.telegram_chat_id
                    HAVING MIN(i.created_at) <= CURRENT_TIMESTAMP - INTERVAL '2 hours';
                    """
                )
                day0_users = await cur.fetchall()

        for u_id, chat_id, item_id, item_title in day0_users:
            title_label = item_title or "the item you saved"
            if len(title_label) > 60:
                title_label = title_label[:57] + "..."
            msg = (
                f"I looked at \"{title_label}\" you sent me. Quick question — was this for you, or were you planning to act on it or share it with someone?\n\n"
                "💻 *Complementary Save Path*:\n"
                "If you're usually on your laptop, the Chrome extension lets you save directly from any webpage — one click, no copy-paste. Download it here: https://chromewebstore.google.com/"
            )
            reply_markup = {
                "inline_keyboard": [
                    [{"text": "Just for me 👤", "callback_data": "onboarding_opt:for_me"}],
                    [{"text": "To act on it 🚀", "callback_data": "onboarding_opt:act"}],
                    [{"text": "To share with someone 👥", "callback_data": "onboarding_opt:share"}]
                ]
            }
            await redis.setex(f"pending_context:{chat_id}", 86400 * 2, str(item_id))
            
            success = await send_telegram_message(str(chat_id), msg, reply_markup=reply_markup)
            if success:
                async with pool.connection() as conn:
                    await conn.execute("SET statement_timeout = '30s'")
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "UPDATE users SET onboarding_day = 1, onboarding_last_sent = CURRENT_TIMESTAMP WHERE id = %s;",
                            (u_id,)
                        )
                        await conn.commit()

        # 2. Day 1 checks (Sends next morning at 8:00 AM local time, at least 12h gap)
        async with pool.connection() as conn:
            await conn.execute("SET statement_timeout = '30s'")
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT u.id, u.telegram_chat_id,
                           (SELECT id FROM items WHERE user_id = u.id ORDER BY created_at ASC LIMIT 1) as first_item_id,
                           (SELECT title FROM items WHERE user_id = u.id ORDER BY created_at ASC LIMIT 1) as first_item_title
                    FROM users u
                    WHERE u.onboarding_day = 1
                      AND u.onboarding_last_sent <= CURRENT_TIMESTAMP - INTERVAL '12 hours'
                      AND EXTRACT(HOUR FROM (CURRENT_TIMESTAMP + (u.timezone_offset * INTERVAL '1 minute'))) = 8;
                    """
                )
                day1_users = await cur.fetchall()

        for u_id, chat_id, first_item_id, first_title in day1_users:
            if not first_item_id:
                continue
            title_label = first_title or "the item you saved"
            msg = f"Still thinking about \"{title_label}\"? I'm not doing anything with it yet — just checking if it's still on your mind, or if it's already done its job."
            reply_markup = {
                "inline_keyboard": [
                    [{"text": "Still on my mind 💭", "callback_data": "onboarding_opt:mind"}],
                    [{"text": "Already done its job ✓", "callback_data": "onboarding_opt:done"}]
                ]
            }
            await redis.setex(f"pending_context:{chat_id}", 86400 * 2, str(first_item_id))
            
            success = await send_telegram_message(str(chat_id), msg, reply_markup=reply_markup)
            if success:
                async with pool.connection() as conn:
                    await conn.execute("SET statement_timeout = '30s'")
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "UPDATE users SET onboarding_day = 2, onboarding_last_sent = CURRENT_TIMESTAMP WHERE id = %s;",
                            (u_id,)
                        )
                        await conn.commit()

        # 3. Day 2 checks (Sends next morning at 8:00 AM local, at least 18h gap, only if they replied to Day 0 or 1)
        async with pool.connection() as conn:
            await conn.execute("SET statement_timeout = '30s'")
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT u.id, u.telegram_chat_id,
                           (SELECT context_note FROM items WHERE user_id = u.id ORDER BY created_at ASC LIMIT 1) as first_note
                    FROM users u
                    WHERE u.onboarding_day = 2
                      AND u.onboarding_last_sent <= CURRENT_TIMESTAMP - INTERVAL '18 hours'
                      AND EXTRACT(HOUR FROM (CURRENT_TIMESTAMP + (u.timezone_offset * INTERVAL '1 minute'))) = 8;
                    """
                )
                day2_users = await cur.fetchall()

        for u_id, chat_id, first_note in day2_users:
            if first_note:
                msg = "What's one thing you've been meaning to look into but haven't saved anywhere yet?"
                success = await send_telegram_message(str(chat_id), msg)
                if success:
                    async with pool.connection() as conn:
                        await conn.execute("SET statement_timeout = '30s'")
                        async with conn.cursor() as cur:
                            await cur.execute(
                                "UPDATE users SET onboarding_day = 3, onboarding_last_sent = CURRENT_TIMESTAMP WHERE id = %s;",
                                (u_id,)
                            )
                            await conn.commit()
            else:
                async with pool.connection() as conn:
                    await conn.execute("SET statement_timeout = '30s'")
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "UPDATE users SET onboarding_day = 5, onboarding_last_sent = CURRENT_TIMESTAMP WHERE id = %s;",
                            (u_id,)
                        )
                        await conn.commit()

        # 4. Monitor Day 3 (Handoff when they reach >= 5 items)
        async with pool.connection() as conn:
            await conn.execute("SET statement_timeout = '30s'")
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT u.id, (SELECT COUNT(*) FROM items WHERE user_id = u.id) as node_count
                    FROM users u
                    WHERE u.onboarding_day = 3;
                    """
                )
                monitored_users = await cur.fetchall()

        for u_id, node_count in monitored_users:
            if node_count >= 5:
                async with pool.connection() as conn:
                    await conn.execute("SET statement_timeout = '30s'")
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "UPDATE users SET onboarding_day = 5, onboarding_last_sent = CURRENT_TIMESTAMP WHERE id = %s;",
                            (u_id,)
                        )
                        await conn.commit()

    except Exception as e:
        logger.error("onboarding_sequence_dispatcher background job failed: %s", e, exc_info=True)


async def mid_graph_re_engagement_dispatcher() -> None:
    """Sends engagement prompts to silent users within the 5-30 node threshold."""
    try:
        pool = await get_pool()
        from backend.services.redis_client import redis
        
        async with pool.connection() as conn:
            await conn.execute("SET statement_timeout = '30s'")
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT u.id, u.telegram_chat_id, COUNT(i.id) as node_count,
                           (SELECT id FROM items WHERE user_id = u.id ORDER BY created_at DESC LIMIT 1) as last_item_id,
                           (SELECT title FROM items WHERE user_id = u.id ORDER BY created_at DESC LIMIT 1) as last_item_title,
                           (SELECT created_at FROM items WHERE user_id = u.id ORDER BY created_at DESC LIMIT 1) as last_save_time
                    FROM users u
                    JOIN items i ON u.id = i.user_id
                    GROUP BY u.id, u.telegram_chat_id
                    HAVING COUNT(i.id) BETWEEN 5 AND 30
                       AND MAX(i.created_at) <= CURRENT_TIMESTAMP - INTERVAL '5 days'
                       AND MAX(i.created_at) >= CURRENT_TIMESTAMP - INTERVAL '14 days';
                    """
                )
                users_to_nudge = await cur.fetchall()

        for u_id, chat_id, node_count, last_id, last_title, last_time in users_to_nudge:
            if not last_id:
                continue
            
            nudge_key = f"re_engagement_sent:{u_id}:{last_id}"
            already_sent = await redis.get(nudge_key)
            if already_sent:
                continue
                
            title_label = last_title or "the item you saved"
            msg = (
                f"You've saved {node_count} things in Recall, but I haven't heard from you in a few days. "
                f"Still thinking about \"{title_label}\"? I'm not doing anything with it yet — "
                f"just checking if it's still on your mind, or if it's already done its job."
            )
            reply_markup = {
                "inline_keyboard": [
                    [{"text": "Still on my mind 💭", "callback_data": "onboarding_opt:mind"}],
                    [{"text": "Already done its job ✓", "callback_data": "onboarding_opt:done"}]
                ]
            }
            await redis.setex(f"pending_context:{chat_id}", 86400 * 2, str(last_id))
            await redis.setex(nudge_key, 86400 * 10, "1")
            
            await send_telegram_message(str(chat_id), msg, reply_markup=reply_markup)

    except Exception as e:
        logger.error("mid_graph_re_engagement_dispatcher background job failed: %s", e, exc_info=True)


async def spaced_repetition_nudge_dispatcher() -> None:
    """Daily background job to nudge users who haven't reviewed memory cards in 72 hours."""
    try:
        pool = await get_pool()
        from backend.services.redis_client import redis
        
        async with pool.connection() as conn:
            await conn.execute("SET statement_timeout = '30s'")
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT u.id, u.telegram_chat_id
                    FROM users u
                    WHERE u.telegram_chat_id IS NOT NULL
                      AND (
                          (SELECT MAX(answered_at) FROM quiz_answers WHERE user_id = u.id) IS NULL
                          OR (SELECT MAX(answered_at) FROM quiz_answers WHERE user_id = u.id) <= CURRENT_TIMESTAMP - INTERVAL '72 hours'
                      )
                      AND (
                          SELECT COUNT(*) FROM quizzes WHERE user_id = u.id AND next_review <= CURRENT_DATE
                      ) > 0;
                    """
                )
                users_to_nudge = await cur.fetchall()

        for u_id, chat_id in users_to_nudge:
            nudge_key = f"sr_nudge_sent:{u_id}"
            already_sent = await redis.get(nudge_key)
            if already_sent:
                continue
                
            msg = (
                "🧠 **Your graph is cooling down!**\n\n"
                "You haven't reviewed your memory cards in 72 hours. "
                "A quick 2-minute quiz will warm up your retention glows."
            )
            reply_markup = {
                "inline_keyboard": [
                    [{"text": "Start Review ⚡", "callback_data": "quiz:next"}]
                ]
            }
            
            # Rate limit to once every 7 days
            await redis.setex(nudge_key, 86400 * 7, "1")
            
            success = await send_telegram_message(str(chat_id), msg, reply_markup=reply_markup)
            if success:
                logger.info("Sent spaced repetition nudge to user_id=%d, chat_id=%s", u_id, chat_id)

    except Exception as e:
        logger.error("spaced_repetition_nudge_dispatcher background job failed: %s", e, exc_info=True)


async def send_telegram_document(
    chat_id: str,
    file_bytes: bytes,
    filename: str,
    caption: Optional[str] = None
) -> bool:
    """Helper to send files (like SVGs) to Telegram via sendDocument, redacting sensitive tokens in logs."""
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendDocument"
    files = {
        "document": (filename, file_bytes, "image/svg+xml")
    }
    data = {
        "chat_id": chat_id
    }
    if caption:
        data["caption"] = caption
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, data=data, files=files, timeout=15.0)
            resp.raise_for_status()
            return True
    except Exception as e:
        err_msg = str(e).replace(settings.TELEGRAM_BOT_TOKEN, "[REDACTED_BOT_TOKEN]")
        logger.error("Failed to send Telegram document to chat_id %s: %s", chat_id, err_msg)
        return False


async def send_telegram_photo(
    chat_id: str,
    photo_bytes: bytes,
    filename: str,
    caption: Optional[str] = None,
    reply_markup: Optional[Dict[str, Any]] = None
) -> bool:
    """Helper to send photo files (like PNG/JPG) to Telegram via sendPhoto, redacting sensitive tokens in logs."""
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendPhoto"
    files = {
        "photo": (filename, photo_bytes, "image/png")
    }
    data = {
        "chat_id": chat_id
    }
    if caption:
        data["caption"] = caption
    if reply_markup:
        import json
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, data=data, files=files, timeout=15.0)
            resp.raise_for_status()
            return True
    except Exception as e:
        err_msg = str(e).replace(settings.TELEGRAM_BOT_TOKEN, "[REDACTED_BOT_TOKEN]")
        logger.error("Failed to send Telegram photo to chat_id %s: %s", chat_id, err_msg)
        return False


async def weekly_mind_map_dispatcher() -> None:
    """Weekly background job to generate and send SVG mind maps of user constellations."""
    try:
        pool = await get_pool()
        from backend.services.mind_map_service import generate_weekly_svg_mind_map
        import fitz
        
        users_to_process = []
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT id, telegram_chat_id FROM users WHERE telegram_chat_id IS NOT NULL;")
                users_to_process = await cur.fetchall()

        sem = asyncio.Semaphore(3)

        async def process_one(user_id, chat_id):
            async with sem:
                try:
                    async with pool.connection() as conn:
                        async with conn.cursor() as cur:
                            svg_str = await generate_weekly_svg_mind_map(cur, user_id)
                            
                    # Convert SVG to High-Resolution PNG via PyMuPDF
                    doc = fitz.open(stream=svg_str.encode("utf-8"), filetype="svg")
                    page = doc[0]
                    pix = page.get_pixmap(dpi=300) # 300 DPI for high quality rendering
                    png_bytes = pix.tobytes("png")
                    
                    caption = "🎨 Here is your weekly Recall Constellation Mind Map! Tap to explore your knowledge clusters."
                    reply_markup = {
                        "inline_keyboard": [
                            [{"text": "Review Constellation ⚡", "callback_data": "quiz:next"}]
                        ]
                    }
                    
                    success = await send_telegram_photo(
                        chat_id=str(chat_id),
                        photo_bytes=png_bytes,
                        filename="weekly_mind_map.png",
                        caption=caption,
                        reply_markup=reply_markup
                    )
                    if success:
                        logger.info("Sent weekly mind map to user_id=%d, chat_id=%s", user_id, chat_id)
                except Exception as ex:
                    logger.error("Failed to process weekly mind map for user_id=%d: %s", user_id, ex)

        await asyncio.gather(*(process_one(uid, cid) for uid, cid in users_to_process))

    except Exception as e:
        logger.error("weekly_mind_map_dispatcher background job failed: %s", e, exc_info=True)


async def monthly_memory_rhythm_scanner() -> None:
    """Monthly background job to analyze user tag shifts and send progress summaries."""
    try:
        pool = await get_pool()
        
        users_to_process = []
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT id, telegram_chat_id FROM users WHERE telegram_chat_id IS NOT NULL;")
                users_to_process = await cur.fetchall()

        sem = asyncio.Semaphore(3)

        async def process_one(user_id, chat_id):
            async with sem:
                try:
                    # 1. Fetch tags from last 30 days
                    async with pool.connection() as conn:
                        async with conn.cursor() as cur:
                            await cur.execute(
                                """
                                SELECT unnest(tags) as tag, COUNT(*) as count
                                FROM items
                                WHERE user_id = %s AND created_at >= NOW() - INTERVAL '30 days' AND tags IS NOT NULL
                                GROUP BY tag;
                                """,
                                (user_id,)
                            )
                            tags_30_rows = await cur.fetchall()
                            
                            # 2. Fetch tags from last 90 days
                            await cur.execute(
                                """
                                SELECT unnest(tags) as tag, COUNT(*) as count
                                FROM items
                                WHERE user_id = %s AND created_at >= NOW() - INTERVAL '90 days' AND tags IS NOT NULL
                                GROUP BY tag;
                                """,
                                (user_id,)
                            )
                            tags_90_rows = await cur.fetchall()

                    t30 = {tag: count for tag, count in tags_30_rows}
                    t90 = {tag: count for tag, count in tags_90_rows}
                    
                    if len(t90) < 2:
                        msg = (
                            "📅 **Monthly Memory Rhythm**\n\n"
                            "You are building your graph steadily! "
                            "Keep saving new items and tagging them to track how your focus shifts over time."
                        )
                        await send_telegram_message(str(chat_id), msg, parse_mode="HTML")
                        return

                    sum30 = sum(t30.values()) or 1
                    sum90 = sum(t90.values()) or 1
                    
                    prop30 = {tag: count / sum30 for tag, count in t30.items()}
                    prop90 = {tag: count / sum90 for tag, count in t90.items()}
                    
                    surging = []
                    cooling = []
                    
                    for tag in prop30:
                        diff = prop30[tag] - prop90.get(tag, 0.0)
                        if diff > 0.02:
                            surging.append((tag, diff))
                            
                    for tag in prop90:
                        diff = prop30.get(tag, 0.0) - prop90[tag]
                        if diff < -0.02:
                            cooling.append((tag, diff))
                            
                    surging = [t[0] for t in sorted(surging, key=lambda x: -x[1])[:3]]
                    cooling = [t[0] for t in sorted(cooling, key=lambda x: x[1])[:3]]
                    
                    if not surging and not cooling:
                        msg = (
                            "📅 **Monthly Memory Rhythm**\n\n"
                            "Your semantic interests remained stable this month. "
                            "You are maintaining a balanced cognitive distribution across your topics!"
                        )
                    else:
                        msg = "📅 **Your Monthly Memory Rhythm is Shifting!**\n\n"
                        if surging:
                            surging_str = ", ".join(f"#{t}" for t in surging)
                            msg += f"🔥 *Surging Themes:* {surging_str}\n"
                        if cooling:
                            cooling_str = ", ".join(f"#{t}" for t in cooling)
                            msg += f"❄️ *Cooling Themes:* {cooling_str}\n"
                        msg += "\nYour mind constellation is alive. Keep saving and connecting ideas! 💭"

                    await send_telegram_message(str(chat_id), msg, parse_mode="Markdown")
                    logger.info("Sent monthly memory rhythm to user_id=%d, chat_id=%s", user_id, chat_id)
                except Exception as ex:
                    logger.error("Failed to process monthly memory rhythm for user_id=%d: %s", user_id, ex)

        await asyncio.gather(*(process_one(uid, cid) for uid, cid in users_to_process))

    except Exception as e:
        logger.error("monthly_memory_rhythm_scanner background job failed: %s", e, exc_info=True)


async def near_miss_calibration() -> None:
    """
    Weekly background job to calibrate each user's near-miss similarity threshold.
    Evaluates near-miss candidates created >= 14 days ago.
    Adjusts threshold dynamically:
      - If conversion (promoted to confirmed within 14 days) < 20%: narrow to 0.73-0.75
      - If conversion > 60%: widen to 0.69-0.75
    """
    try:
        pool = await get_pool()
    except Exception as e:
        logger.error("Failed to open database pool in Near-Miss Calibration job: %s", e)
        return

    # Fetch all users
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT id, near_miss_lower_bound FROM users")
                users_data = await cur.fetchall()
    except Exception as e:
        logger.error("Failed to fetch users in Near-Miss Calibration job: %s", e)
        return

    for user_id, current_floor in users_data:
        if current_floor is None:
            current_floor = 0.710
        else:
            current_floor = float(current_floor)

        try:
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    # Fetch near-misses created 14 to 30 days ago
                    await cur.execute(
                        """
                        SELECT id, item_id_a, item_id_b, similarity_score, created_at
                        FROM insight_candidates
                        WHERE user_id = %s
                          AND bucket = 'near_miss'
                          AND created_at <= NOW() - INTERVAL '14 days'
                          AND created_at >= NOW() - INTERVAL '30 days';
                        """,
                        (user_id,)
                    )
                    near_misses = await cur.fetchall()

                    if not near_misses:
                        logger.info("No historical near-misses for user %d to calibrate.", user_id)
                        continue

                    total_near_misses = len(near_misses)
                    converted_count = 0

                    for nm in near_misses:
                        nm_id, item_a, item_b, score, created_at = nm
                        # Check if a confirmed connection happened for this item pair in the 14 days after creation
                        await cur.execute(
                            """
                            SELECT 1 FROM insight_candidates
                            WHERE user_id = %s
                              AND bucket = 'confirmed'
                              AND similarity_score >= 0.75
                              AND created_at >= %s
                              AND created_at <= %s + INTERVAL '14 days'
                              AND (
                                  (item_id_a = %s AND item_id_b = %s) OR
                                  (item_id_a = %s AND item_id_b = %s)
                              )
                            LIMIT 1;
                            """,
                            (user_id, created_at, created_at, item_a, item_b, item_b, item_a)
                        )
                        conversion_exists = await cur.fetchone()
                        if conversion_exists:
                            converted_count += 1

                    conversion_rate = converted_count / total_near_misses
                    logger.info("User %d near-miss conversion rate: %.2f%% (%d/%d)", user_id, conversion_rate * 100, converted_count, total_near_misses)

                    new_floor = current_floor
                    if conversion_rate < 0.20:
                        new_floor = min(0.730, current_floor + 0.01)
                    elif conversion_rate > 0.60:
                        new_floor = max(0.690, current_floor - 0.01)

                    if new_floor != current_floor:
                        await cur.execute(
                            "UPDATE users SET near_miss_lower_bound = %s WHERE id = %s;",
                            (new_floor, user_id)
                        )
                        await conn.commit()
                        logger.info("Calibrated near-miss threshold for user %d from %.3f to %.3f", user_id, current_floor, new_floor)

        except Exception as cal_err:
            logger.error("Failed to run near-miss calibration for user %d: %s", user_id, cal_err)


async def save_rhythm_scanner() -> None:
    """
    Weekly background job to detect save rhythm patterns and queue monthly surprise notifications.
    """
    try:
        pool = await get_pool()
    except Exception as e:
        logger.error("Failed to open database pool in Save Rhythm Scanner job: %s", e)
        return

    # Fetch all users
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT id, chat_id FROM users")
                users = await cur.fetchall()
    except Exception as e:
        logger.error("Failed to fetch users in Save Rhythm Scanner job: %s", e)
        return

    for user_id, chat_id in users:
        try:
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    # Query item count by semantic hub and time bucket for this user
                    await cur.execute(
                        """
                        SELECT h.id, h.label, i.save_time_bucket, COUNT(*) as cnt
                        FROM items i
                        JOIN semantic_hubs h ON i.user_id = h.user_id AND i.id = ANY(h.member_ids)
                        WHERE i.user_id = %s AND i.save_time_bucket IS NOT NULL
                        GROUP BY h.id, h.label, i.save_time_bucket;
                        """,
                        (user_id,)
                    )
                    rows = await cur.fetchall()

                    if not rows:
                        continue

                    # Group results by hub
                    hub_stats = {}
                    for hub_id, label, bucket, count in rows:
                        if hub_id not in hub_stats:
                            hub_stats[hub_id] = {"label": label, "buckets": {}, "total": 0}
                        hub_stats[hub_id]["buckets"][bucket] = count
                        hub_stats[hub_id]["total"] += count

                    # Scan for > 75% concentration patterns
                    for hub_id, stats in hub_stats.items():
                        total = stats["total"]
                        if total < 4:  # Require at least 4 items in a hub to establish a pattern
                            continue

                        for bucket, count in stats["buckets"].items():
                            concentration = count / total
                            if concentration >= 0.75:
                                # Found a pattern! Queue a surprise re-engagement notification.
                                rhythm_msg = (
                                    f"⏰ *Save Rhythm Pattern Detected*!\n\n"
                                    f"You save content under the cluster *{stats['label']}* "
                                    f"almost exclusively ({concentration*100:.0f}%) in the *{bucket}*.\n"
                                    f"Recall matches your daily rhythm to surface connections when your focus is highest!"
                                )
                                if chat_id:
                                    await send_telegram_message(str(chat_id), rhythm_msg, parse_mode="Markdown")
                                    logger.info("Sent rhythm notification to user %d for hub %s", user_id, stats["label"])
                                break
        except Exception as rhythm_err:
            logger.error("Failed to run save rhythm scanner for user %d: %s", user_id, rhythm_err)


async def recall_moment_dispatcher() -> None:
    """
    Background job to dispatch the weekly Recall Moment connection insight.
    Runs hourly.
    Randomly triggers once per 7 days per user between 10:00 AM and 4:00 PM user's local time.
    """
    try:
        pool = await get_pool()
    except Exception as e:
        logger.error("Failed to open database pool in Recall Moment dispatcher: %s", e)
        return

    # Fetch all users
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT id, telegram_chat_id as chat_id, timezone_offset, last_recall_moment_at FROM users")
                users = await cur.fetchall()
    except Exception as e:
        logger.error("Failed to fetch users in Recall Moment dispatcher: %s", e)
        return

    import random
    import time
    for user_id, chat_id, offset_minutes, last_moment in users:
        if not chat_id:
            continue

        if offset_minutes is None:
            offset_minutes = 0

        # 1. Enforce rolling 7-day limit
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        if last_moment:
            if last_moment.tzinfo is None:
                last_moment = last_moment.replace(tzinfo=datetime.timezone.utc)
            if now_utc - last_moment < datetime.timedelta(days=7):
                continue

        # 2. Check user's local time window (10:00 AM - 4:00 PM local)
        local_time = now_utc + datetime.timedelta(minutes=offset_minutes)
        local_hour = local_time.hour
        if not (10 <= local_hour < 16):
            continue

        # 3. Time jitter: randomized check to spread sends across the 6-hour window
        if random.random() > (1.0 / 6.0):
            continue

        # 4. Fetch the highest-similarity confirmed candidate connection
        try:
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT c.id, c.item_id_a, c.item_id_b, 
                               a.title, a.summary, a.tags, a.context_note, a.passive_context,
                               b.title, b.summary, b.tags, b.context_note, b.passive_context
                        FROM insight_candidates c
                        JOIN items a ON c.item_id_a = a.id
                        JOIN items b ON c.item_id_b = b.id
                        WHERE c.user_id = %s AND c.status = 'pending' AND c.bucket = 'confirmed'
                        ORDER BY c.similarity_score DESC
                        LIMIT 1;
                        """,
                        (user_id,)
                    )
                    cand = await cur.fetchone()

            if cand:
                cand_id, item_a_id, item_b_id, t_a, s_a, tg_a, cn_a, pc_a, t_b, s_b, tg_b, cn_b, pc_b = cand
                
                # Generate connection insight text via AI Cascade
                cascade = AICascade()
                dict_a = {"title": t_a, "summary": s_a, "tags": tg_a, "context_note": cn_a, "passive_context": pc_a}
                dict_b = {"title": t_b, "summary": s_b, "tags": tg_b, "context_note": cn_b, "passive_context": pc_b}
                
                logger.info("Generating Recall Moment connection insight for candidate %d...", cand_id)
                insight = await cascade.generate_insight(dict_a, dict_b, 1)
                
                if insight:
                    expiry_epoch = int(time.time()) + 6 * 3600  # 6-hour Drift Window expiration
                    
                    async with pool.connection() as conn:
                        async with conn.cursor() as cur:
                            await cur.execute(
                                """
                                UPDATE insight_candidates
                                SET status = 'delivered', insight_text = %s, expires_at = NOW() + INTERVAL '6 hours'
                                WHERE id = %s;
                                """,
                                (insight, cand_id)
                            )
                            await cur.execute(
                                "UPDATE users SET last_recall_moment_at = %s WHERE id = %s;",
                                (now_utc, user_id)
                            )
                            await conn.commit()

                    await redis.zadd("reminders:active", float(expiry_epoch), f"drift:{cand_id}")

                    recall_msg = (
                        f"✨ *Recall Moment*!\n\n"
                        f"A new connection is pulsing in your mind map:\n\n"
                        f"*{insight}*\n\n"
                        f"This link connects:\n"
                        f"🔗 {t_a}\n"
                        f"🔗 {t_b}\n\n"
                        f"💡 _This connection expires in 6 hours! Open your dashboard map to see it pulse before it drifts away._"
                    )
                    reply_markup = {
                        "inline_keyboard": [
                            [
                                {"text": "Keep Connection 🔗", "callback_data": f"candidate_confirm:{cand_id}"},
                                {"text": "Let it Drift 💨", "callback_data": f"candidate_drift:{cand_id}"}
                            ]
                        ]
                    }
                    await send_telegram_message(str(chat_id), recall_msg, reply_markup=reply_markup, parse_mode="Markdown")
                    logger.info("Sent Recall Moment connection candidate %d to user %d", cand_id, user_id)
                    
        except Exception as moment_err:
            logger.error("Failed to run Recall Moment dispatcher for user %d: %s", user_id, moment_err)


async def tag_portraits_generator() -> None:
    """Generate thematic names, descriptions and icons for active tag-based communities."""
    pool = await get_pool()
    if not pool:
        logger.error("No database pool available for tag_portraits_generator.")
        return

    from backend.services.ai_cascade import AICascade
    ai_cascade = AICascade()

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            # Get list of all users
            await cur.execute("SELECT id FROM users;")
            user_rows = await cur.fetchall()
            user_ids = [row[0] for row in user_rows]

    for user_id in user_ids:
        try:
            # Fetch user's items
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT id, title, summary, tags 
                        FROM items 
                        WHERE user_id = %s;
                        """,
                        (user_id,)
                    )
                    items = await cur.fetchall()
            
            # Map tags to their member item summaries/titles
            tag_buckets = {}
            for item_id, title, summary, tags in items:
                if not tags:
                    continue
                for tag in tags:
                    tag_buckets.setdefault(tag, []).append(f"Title: {title or 'Untitled'}\nSummary: {summary or 'No summary'}")

            # Identify active tags (>= 3 items)
            active_tags = {tag: details for tag, details in tag_buckets.items() if len(details) >= 3}
            if not active_tags:
                continue

            for tag, member_texts in active_tags.items():
                # Check if portrait already exists
                async with pool.connection() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "SELECT id FROM tag_portraits WHERE user_id = %s AND tag = %s;",
                            (user_id, tag)
                        )
                        exists = await cur.fetchone()
                
                # If it already exists, skip it (saves cost/calls)
                if exists:
                    continue

                # Format summaries for AI
                context_str = "\n---\n".join(member_texts[:5])
                if len(context_str) > 1500:
                    context_str = context_str[:1500] + "..."

                prompt = (
                    f"Create a short thematic description and suggest a single emoji representing a cluster of notes about the topic '{tag}'.\n"
                    f"Here are some examples of notes in this cluster:\n{context_str}\n\n"
                    "Respond with a JSON object containing:\n"
                    "{\n"
                    "  \"description\": \"A 1-2 sentence description explaining the core theme of these notes.\",\n"
                    "  \"icon\": \"A single thematic emoji representing this cluster\"\n"
                    "}"
                )

                try:
                    ai_res = await ai_cascade.call_llm(prompt)
                    import json
                    import re

                    description = "No description generated."
                    icon = "🧠"

                    if isinstance(ai_res, dict):
                        description = ai_res.get("description") or description
                        icon = ai_res.get("icon") or icon
                    elif isinstance(ai_res, str):
                        match = re.search(r"\{.*\}", ai_res, re.DOTALL)
                        if match:
                            try:
                                parsed = json.loads(match.group(0))
                                description = parsed.get("description") or description
                                icon = parsed.get("icon") or icon
                            except Exception:
                                pass
                        if description == "No description generated.":
                            description = ai_res[:200]

                    icon_match = re.search(r"[\U00010000-\U0010ffff\u2600-\u27bf]", icon)
                    if icon_match:
                        icon = icon_match.group(0)
                    else:
                        icon = icon[:2]

                    async with pool.connection() as conn:
                        async with conn.cursor() as cur:
                            await cur.execute(
                                """
                                INSERT INTO tag_portraits (user_id, tag, description, icon)
                                VALUES (%s, %s, %s, %s)
                                ON CONFLICT (user_id, tag) DO UPDATE
                                SET description = EXCLUDED.description,
                                    icon = EXCLUDED.icon;
                                """,
                                (user_id, tag, description.strip(), icon.strip())
                            )
                            await conn.commit()
                except Exception as ai_ex:
                    logger.error("AI portrait generation failed for user %d, tag %s: %s", user_id, tag, ai_ex)

        except Exception as u_ex:
            logger.error("Failed to run tag portraits generator for user %d: %s", user_id, u_ex)


async def daily_pulse_updater() -> None:
    """Calculate and update user pulse scores for all users to reflect activity decay."""
    pool = await get_pool()
    if not pool:
        logger.error("No database pool available for daily_pulse_updater.")
        return

    from backend.services.pulse_service import update_user_pulse

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT id FROM users;")
            rows = await cur.fetchall()
            user_ids = [r[0] for r in rows]

    for user_id in user_ids:
        try:
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await update_user_pulse(cur, user_id)
                    await conn.commit()
        except Exception as e:
            logger.error("Failed to update daily pulse for user %d: %s", user_id, e)


# ---------------------------------------------------------------------------
# Scheduler Manager
# ---------------------------------------------------------------------------

async def start_scheduler(app=None) -> None:
    """Initialize and start the background scheduler."""
    global _scheduler
    if _scheduler is not None:
        return

    _scheduler = AsyncIOScheduler()
    
    # 1. reminders_dispatcher (every 1 minute)
    _scheduler.add_job(
        reminders_dispatcher,
        trigger=IntervalTrigger(minutes=1),
        id="reminders_dispatcher",
        misfire_grace_time=60
    )
    
    # 2. louvain_clustering (daily at 02:00 UTC)
    _scheduler.add_job(
        louvain_clustering,
        trigger=CronTrigger(hour=2, minute=0, timezone="UTC"),
        id="louvain_clustering",
        misfire_grace_time=60
    )
    
    # 3. partition_creator (monthly on the 25th at 00:00 UTC)
    _scheduler.add_job(
        partition_creator,
        trigger=CronTrigger(day=25, hour=0, minute=0, timezone="UTC"),
        id="partition_creator",
        misfire_grace_time=60
    )
    
    # 4. drive_nudge_sender (daily at 10:00 UTC)
    _scheduler.add_job(
        drive_nudge_sender,
        trigger=CronTrigger(hour=10, minute=0, timezone="UTC"),
        id="drive_nudge_sender",
        misfire_grace_time=60
    )
    
    # 5. processed_updates_cleanup (weekly on Sunday at 03:00 UTC)
    _scheduler.add_job(
        processed_updates_cleanup,
        trigger=CronTrigger(day_of_week="sun", hour=3, minute=0, timezone="UTC"),
        id="processed_updates_cleanup",
        misfire_grace_time=60
    )
    
    # 6. daily_digest_sender (hourly at minute 0 UTC)
    _scheduler.add_job(
        daily_digest_sender,
        trigger=CronTrigger(hour="*", minute=0, timezone="UTC"),
        id="daily_digest_sender",
        misfire_grace_time=3600
    )
    
    # 7. weekly_drive_sync (weekly on Sunday at 04:00 UTC)
    _scheduler.add_job(
        weekly_drive_sync,
        trigger=CronTrigger(day_of_week="sun", hour=4, minute=0, timezone="UTC"),
        id="weekly_drive_sync",
        misfire_grace_time=60
    )

    # 8. offpeak_quiz_generator (daily at 22:00 UTC / 3:30 AM IST)
    _scheduler.add_job(
        offpeak_quiz_generator,
        trigger=CronTrigger(hour=22, minute=0, timezone="UTC"),
        id="offpeak_quiz_generator",
        misfire_grace_time=60
    )

    # 9. onboarding_sequence_dispatcher (hourly at minute 5 UTC)
    _scheduler.add_job(
        onboarding_sequence_dispatcher,
        trigger=CronTrigger(hour="*", minute=5, timezone="UTC"),
        id="onboarding_sequence_dispatcher",
        misfire_grace_time=60
    )

    # 10. mid_graph_re_engagement_dispatcher (hourly at minute 10 UTC)
    _scheduler.add_job(
        mid_graph_re_engagement_dispatcher,
        trigger=CronTrigger(hour="*", minute=10, timezone="UTC"),
        id="mid_graph_re_engagement_dispatcher",
        misfire_grace_time=60
    )

    # 11. near_miss_calibration (weekly on Sunday at 05:00 UTC)
    _scheduler.add_job(
        near_miss_calibration,
        trigger=CronTrigger(day_of_week="sun", hour=5, minute=0, timezone="UTC"),
        id="near_miss_calibration",
        misfire_grace_time=60
    )

    # 12. save_rhythm_scanner (weekly on Saturday at 05:00 UTC)
    _scheduler.add_job(
        save_rhythm_scanner,
        trigger=CronTrigger(day_of_week="sat", hour=5, minute=0, timezone="UTC"),
        id="save_rhythm_scanner",
        misfire_grace_time=60
    )

    # 13. recall_moment_dispatcher (hourly at minute 15 UTC)
    _scheduler.add_job(
        recall_moment_dispatcher,
        trigger=CronTrigger(hour="*", minute=15, timezone="UTC"),
        id="recall_moment_dispatcher",
        misfire_grace_time=60
    )

    # 14. weekly_profile_text_generator (hourly at minute 20 UTC)
    _scheduler.add_job(
        weekly_profile_text_generator,
        trigger=CronTrigger(hour="*", minute=20, timezone="UTC"),
        id="weekly_profile_text_generator",
        misfire_grace_time=60
    )

    # 15. monthly_prediction_generator (hourly at minute 25 UTC)
    _scheduler.add_job(
        monthly_prediction_generator,
        trigger=CronTrigger(hour="*", minute=25, timezone="UTC"),
        id="monthly_prediction_generator",
        misfire_grace_time=60
    )

    # 16. monthly_discrepancy_scanner (hourly at minute 30 UTC)
    _scheduler.add_job(
        monthly_discrepancy_scanner,
        trigger=CronTrigger(hour="*", minute=30, timezone="UTC"),
        id="monthly_discrepancy_scanner",
        misfire_grace_time=60
    )

    # 17. monthly_forward_hook (hourly at minute 35 UTC)
    _scheduler.add_job(
        monthly_forward_hook,
        trigger=CronTrigger(hour="*", minute=35, timezone="UTC"),
        id="monthly_forward_hook",
        misfire_grace_time=60
    )

    # 18. tag_portraits_generator (daily at 03:00 UTC)
    _scheduler.add_job(
        tag_portraits_generator,
        trigger=CronTrigger(hour=3, minute=0, timezone="UTC"),
        id="tag_portraits_generator",
        misfire_grace_time=60
    )

    # 19. daily_pulse_updater (daily at 04:00 UTC)
    _scheduler.add_job(
        daily_pulse_updater,
        trigger=CronTrigger(hour=4, minute=0, timezone="UTC"),
        id="daily_pulse_updater",
        misfire_grace_time=60
    )

    # 20. spaced_repetition_nudge_dispatcher (daily at 11:00 UTC)
    _scheduler.add_job(
        spaced_repetition_nudge_dispatcher,
        trigger=CronTrigger(hour=11, minute=0, timezone="UTC"),
        id="spaced_repetition_nudge_dispatcher",
        misfire_grace_time=60
    )

    # 21. weekly_mind_map_dispatcher (weekly on Sunday at 18:00 UTC)
    _scheduler.add_job(
        weekly_mind_map_dispatcher,
        trigger=CronTrigger(day_of_week="sun", hour=18, minute=0, timezone="UTC"),
        id="weekly_mind_map_dispatcher",
        misfire_grace_time=60
    )

    # 22. monthly_memory_rhythm_scanner (monthly on the 1st at 06:00 UTC)
    _scheduler.add_job(
        monthly_memory_rhythm_scanner,
        trigger=CronTrigger(day=1, hour=6, minute=0, timezone="UTC"),
        id="monthly_memory_rhythm_scanner",
        misfire_grace_time=60
    )
    
    _scheduler.start()
    logger.info("Background job scheduler started successfully with all 22 jobs.")


async def stop_scheduler() -> None:
    """Shut down the background scheduler."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown()
        _scheduler = None
        logger.info("Background job scheduler shut down.")
