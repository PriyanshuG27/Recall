import logging
import numpy as np
import networkx as nx
import community as community_louvain
from typing import List, Dict, Any, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

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


async def louvain_clustering() -> None:
    """
    Background job to run Louvain community clustering for each user.
    Builds a NetworkX graph based on item embedding cosine similarity > 0.75,
    clusters them, generates labels using the AI cascade, and stores the centroids in pgvector format.
    """
    global _pool
    if _pool is not None:
        connection._pool = _pool

    if connection._pool is None:
        try:
            await connection.open_pool()
        except Exception as e:
            logger.error("Failed to open database pool in Louvain job: %s", e)
            return

    # 1. Fetch all users
    users = []
    try:
        async with connection._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT id FROM users")
                users = [row[0] for row in await cur.fetchall()]
    except Exception as e:
        logger.error("Failed to fetch users in Louvain job: %s", e)
        return

    ai_cascade = AICascade()

    for user_id in users:
        try:
            logger.info("Running Louvain clustering for user %s", user_id)
            
            # Fetch user items
            async with connection._pool.connection() as conn:
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
                # Take only the first 5 summaries to prevent TPM/RPM/Request Too Large issues on Groq
                member_summaries = member_summaries[:5]
                community_summaries_joined = "\n---\n".join(member_summaries)
                
                # Truncate total text length to 1500 characters to be absolutely safe with token limits
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
                    # Truncate title to 4 words or less
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
            async with connection._pool.connection() as conn:
                async with conn.cursor() as cur:
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
            # Log error and skip user - never crash job
            logger.error("Louvain clustering failed for user %s: %s", user_id, e, exc_info=True)
            continue

    logger.info("Louvain clustering background job completed.")


async def start_scheduler(app=None) -> None:
    """Initialize and start the background scheduler."""
    global _scheduler
    if _scheduler is not None:
        return

    _scheduler = AsyncIOScheduler()
    # Add daily Louvain clustering job at 02:00 UTC with misfire_grace_time=60
    _scheduler.add_job(
        louvain_clustering,
        trigger=CronTrigger(hour=2, minute=0, timezone="UTC"),
        id="louvain_clustering",
        misfire_grace_time=60
    )
    _scheduler.start()
    logger.info("Background job scheduler started successfully.")


async def stop_scheduler() -> None:
    """Shut down the background scheduler."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown()
        _scheduler = None
        logger.info("Background job scheduler shut down.")
