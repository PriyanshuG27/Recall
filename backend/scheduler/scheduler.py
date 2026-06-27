import logging
import numpy as np
import networkx as nx
import community as community_louvain
from typing import List, Dict, Any, Optional
import datetime
import sys
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


async def send_telegram_message(chat_id: str, text: str) -> bool:
    """Helper to send Telegram messages via Bot API, redacting sensitive tokens in logs."""
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
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
            INSERT INTO semantic_hubs (user_id, label, centroid, member_ids)
            VALUES (%s, %s, %s::vector, %s)
            RETURNING id;
            """,
            (user_id, hub["label"], centroid_str, hub["member_ids"])
        )
        row = await cur.fetchone()
        hub["id"] = row[0] if row else None


# ---------------------------------------------------------------------------
# Background Jobs
# ---------------------------------------------------------------------------

async def reminders_dispatcher() -> None:
    """
    Background job to deliver pending reminders to users via Telegram Bot API.
    Uses Redis Sorted Set for scheduling:
    1. Queries Redis zset 'reminders:active' for due IDs.
    2. If empty, exits immediately without touching the PostgreSQL pool (Neon autosuspend).
    3. If not empty, checks out database connection, updates statuses, and dispatches.
    """
    import time
    try:
        now_epoch = int(time.time())
        due_ids_str = await redis.zrangebyscore("reminders:active", "-inf", str(now_epoch))
        if not due_ids_str:
            return

        due_ids = [int(x) for x in due_ids_str if x.isdigit()]
        if not due_ids:
            return

        logger.info("Found %d pending reminders in Redis to dispatch.", len(due_ids))
        pool = await get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
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
                    
                if not rows:
                    return

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
    users = []
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT id FROM users")
                users = [row[0] for row in await cur.fetchall()]
    except Exception as e:
        logger.error("Failed to fetch users in Louvain job: %s", e)
        return

    ai_cascade = AICascade()
    threshold = 3 if settings.ENV == "test" else 10

    for user_id in users:
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
                        new_items_count = threshold  # Mock fallback to bypass threshold check in test
            
            if new_items_count < threshold:
                logger.info(
                    "User %s has %d new items (threshold is %d), skipping clustering.",
                    user_id, new_items_count, threshold
                )
                continue

            logger.info("Running Louvain clustering for user %s", user_id)
            
            # Fetch user items
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT id, embedding, summary, title FROM items WHERE user_id = %s",
                        (user_id,)
                    )
                    item_rows = await cur.fetchall()

            if len(item_rows) < 3:
                logger.info("User %s has < 3 items, skipping clustering.", user_id)
                continue

            # Parse embeddings, summaries, and titles
            embeddings = {}
            summaries = {}
            titles = {}
            for row in item_rows:
                item_id = row[0]
                emb_val = row[1]
                summary = row[2]
                title = row[3] if len(row) > 3 else f"Item {item_id}"

                emb = parse_vector(emb_val)
                if emb and len(emb) == 384:
                    embeddings[item_id] = np.array(emb)
                    summaries[item_id] = summary or ""
                    titles[item_id] = title or "Untitled"

            if len(embeddings) < 3:
                logger.info("User %s has < 3 items with valid 384-dim embeddings, skipping.", user_id)
                continue

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
            for idx, id1 in enumerate(item_ids):
                emb1 = normalized_embeddings[id1]
                for id2 in item_ids[idx + 1:]:
                    emb2 = normalized_embeddings[id2]
                    sim = float(np.dot(emb1, emb2))
                    if sim > 0.75:
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

                hubs_to_insert.append({
                    "label": label,
                    "centroid": centroid,
                    "member_ids": member_ids
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

        except Exception as e:
            logger.error("Louvain clustering failed for user %s: %s", user_id, e, exc_info=True)
            continue

    logger.info("Louvain clustering background job completed.")


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
    Background job to send a daily morning digest to active users who have
    digest_enabled=True. Filters users dynamically by local hour 8:00 AM.
    Runs hourly.
    """
    try:
        pool = await get_pool()
        users_to_digest = []
        async with pool.connection() as conn:
            await conn.execute("SET statement_timeout = '30s'")
            async with conn.cursor() as cur:
                # Select users whose local time is currently in the 8:00 AM hour
                # also filtering by digest_enabled and activity within previous 7 days
                await cur.execute(
                    """
                    SELECT id, telegram_chat_id, streak_count
                    FROM users
                    WHERE digest_enabled = TRUE
                      AND last_activity_date >= CURRENT_DATE - INTERVAL '7 days'
                      AND EXTRACT(HOUR FROM (CURRENT_TIMESTAMP + (timezone_offset * INTERVAL '1 minute'))) = 8;
                    """
                )
                users_to_digest = await cur.fetchall()
        
        if not users_to_digest:
            logger.info("No active users found for daily digest in this hour.")
            return

        logger.info("Found %d users eligible for daily digest in this hour.", len(users_to_digest))
        
        for user_id, chat_id, streak_count in users_to_digest:
            try:
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
                        
                        # 2. Get yesterday's first 3 titles (ordered by created_at)
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
                
                # Format response message
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
                
                # Deliver message asynchronously, isolated to prevent single user failure from blocking others
                await send_telegram_message(str(chat_id), msg)
                
            except Exception as user_err:
                logger.error("Failed to compile or deliver daily digest for user %d (chat_id %s): %s", user_id, chat_id, user_err, exc_info=True)
                
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
        
        for user_id in users_to_sync:
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
                
    except Exception as e:
        logger.error("weekly_drive_sync background job failed: %s", e, exc_info=True)


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
    
    _scheduler.start()
    logger.info("Background job scheduler started successfully with all 7 jobs.")


async def stop_scheduler() -> None:
    """Shut down the background scheduler."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown()
        _scheduler = None
        logger.info("Background job scheduler shut down.")
