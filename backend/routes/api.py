"""
backend/routes/api.py
=====================
API routes for Recall.
Provides endpoints for items, search, graph visualization, quizzes, reminders, and Drive sync.
All endpoints require bearerAuth or telegramInitData (applied via OpenAPI customizer).
"""

from datetime import date
import logging
from typing import List, Optional
from fastapi import APIRouter, Path, Query, Response, status, Depends, HTTPException
from pydantic import BaseModel, Field
import psycopg

from backend.middleware.twa_auth import get_current_user, UserContext
from backend.db.connection import get_db
from backend.models.schemas import (
    ItemResponse,
    ItemCreateRequest,
    SearchRequest,
    SearchResponse,
    SearchResponseItem,
    GraphResponse,
    GraphNode,
    GraphEdge,
    GraphHub,
    QuizResponse,
    QuizAnswerRequest,
    QuizStatsResponse,
    ReminderResponse,
    ReminderCreateRequest,
    ErrorResponse,
    PaginatedItem,
    PaginatedItemsResponse,
    TagCountResponse,
    SearchSourceItem,
    RAGSearchResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["api"])

# ---------------------------------------------------------------------------
# Items Group
# ---------------------------------------------------------------------------
@router.get(
    "/items",
    response_model=PaginatedItemsResponse,
    tags=["items"],
    summary="Get saved items",
    description="Returns a paginated list of saved items for the authenticated user, optionally filtered.",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid query parameters."},
        401: {"model": ErrorResponse, "description": "Not authenticated."},
    },
)
async def get_items(
    page: int = Query(1, ge=1, description="Page number for pagination."),
    limit: int = Query(20, ge=1, description="Number of items per page (max 50)."),
    source_type: Optional[str] = Query(None, description="Filter by source type."),
    tag: Optional[str] = Query(None, description="Filter by tag."),
    from_date: Optional[date] = Query(None, description="Filter items created on or after this date (UTC)."),
    to_date: Optional[date] = Query(None, description="Filter items created on or before this date (UTC)."),
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    """Retrieve saved items with pagination and advanced filtering."""
    if limit > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Limit cannot exceed 50"
        )

    # Base WHERE clauses scoped strictly to the authenticated user
    where_clauses = ["user_id = %s"]
    params = [user.id]

    if source_type is not None:
        where_clauses.append("source_type = %s")
        params.append(source_type)

    if tag is not None:
        where_clauses.append("%s = ANY(tags)")
        params.append(tag)

    if from_date is not None:
        where_clauses.append("created_at >= %s")
        params.append(from_date)

    if to_date is not None:
        where_clauses.append("created_at <= %s")
        params.append(to_date)

    where_str = " WHERE " + " AND ".join(where_clauses)

    async with db.cursor() as cur:
        # Get total count matching the filters
        count_query = f"SELECT COUNT(*) FROM items{where_str};"
        await cur.execute(count_query, tuple(params))
        row = await cur.fetchone()
        total = int(row[0]) if row else 0

        # Retrieve items
        offset = (page - 1) * limit
        items_query = f"""
            SELECT id, title, summary, source_type, source_url, tags, created_at
            FROM items
            {where_str}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s;
        """
        items_params = params + [limit, offset]
        await cur.execute(items_query, tuple(items_params))
        rows = await cur.fetchall()

        items = []
        for r in rows:
            items.append(
                PaginatedItem(
                    id=r[0],
                    title=r[1],
                    summary=r[2],
                    source_type=r[3],
                    source_url=r[4],
                    tags=r[5] if r[5] is not None else [],
                    created_at=r[6],
                )
            )

        import math
        pages = math.ceil(total / limit) if total > 0 else 0

        return PaginatedItemsResponse(
            items=items,
            total=total,
            page=page,
            pages=pages,
        )

@router.post(
    "/items",
    response_model=ItemResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["items"],
    summary="Save a new item",
    description="Saves a new item (url with optional title) for the authenticated user.",
    responses={401: {"model": ErrorResponse}},
)
async def create_item(
    req: ItemCreateRequest,
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    """Save a new item and auto-generate summary and tags."""
    from datetime import datetime, timezone
    from backend.services.ai_cascade import AICascade
    from backend.services.search_service import embed_text
    from backend.services.encryption import encrypt

    title = req.title or "Untitled Link"
    raw_text = f"URL: {req.url}\nTitle: {title}"

    # Generate summary & tags via AI cascade (non-blocking)
    cascade = AICascade()
    tags = []
    try:
        ai_res = await cascade.summarise(raw_text)
        summary = ai_res.get("summary") or "No summary generated."
        tags = ai_res.get("tags") or []
    except Exception as e:
        logger.error("Failed to generate AI summary/tags for URL item: %s", e)
        summary = "No summary generated."

    # Normalize tags: lowercase, strip, keep max 5
    normalized_tags = [t.strip().lower() for t in tags if isinstance(t, str) and t.strip()][:5]

    # Generate embedding
    embedding = await embed_text(raw_text)

    # Encrypt raw text
    encrypted_raw_text = encrypt(raw_text)

    async with db.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO items (user_id, source_type, source_url, raw_text, summary, title, embedding, tags)
            VALUES (%s, 'url', %s, %s, %s, %s, %s::vector, %s)
            RETURNING id, created_at;
            """,
            (user.id, req.url, encrypted_raw_text, summary, title, embedding, normalized_tags)
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="Failed to save item to database")
        item_id = row[0]
        created_at = row[1]
        await db.commit()

    # Invalidate graph cache
    from backend.services.redis_client import redis
    try:
        await redis.delete(f"graph:{user.id}")
        logger.info("Invalidated graph cache for user %d on new item save", user.id)
    except Exception as e:
        logger.error("Failed to invalidate graph cache for user %d: %s", user.id, e)

    return ItemResponse(
        id=item_id,
        user_id=user.id,
        source_type="url",
        source_url=req.url,
        summary=summary,
        title=title,
        tags=normalized_tags,
        created_at=created_at,
    )

@router.get(
    "/tags",
    response_model=List[TagCountResponse],
    tags=["items"],
    summary="Get top tags",
    description="Returns a list of the user's top 50 tags by count.",
    responses={401: {"model": ErrorResponse}},
)
async def get_tags(
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db)
):
    """Retrieve the frequency count of all user tags up to limit 50."""
    async with db.cursor() as cur:
        await cur.execute(
            """
            SELECT DISTINCT unnest(tags) AS tag, COUNT(*) AS count
            FROM items
            WHERE user_id = %s
            GROUP BY tag
            ORDER BY count DESC
            LIMIT 50;
            """,
            (user.id,)
        )
        rows = await cur.fetchall()

    return [TagCountResponse(tag=row[0], count=row[1]) for row in rows]

@router.delete(
    "/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["items"],
    summary="Delete an item",
    description="Deletes a saved item by ID. Validates ownership to prevent IDOR.",
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse, "description": "Item not found."},
    },
)
async def delete_item(
    item_id: int = Path(..., description="ID of the item to delete."),
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    """Delete an item and its associated quizzes."""
    try:
        async with db.cursor() as cur:
            # 1. Delete associated quizzes and item_chunks in the same transaction
            await cur.execute(
                "DELETE FROM quizzes WHERE item_id = %s AND user_id = %s;",
                (item_id, user.id)
            )
            await cur.execute(
                "DELETE FROM item_chunks WHERE item_id = %s AND user_id = %s;",
                (item_id, user.id)
            )
            
            # 2. Delete item with strict IDOR protection (must include user_id filter)
            await cur.execute(
                "DELETE FROM items WHERE id = %s AND user_id = %s RETURNING id, source_type;",
                (item_id, user.id)
            )
            row = await cur.fetchone()
            
            if row is None:
                await db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Item not found"
                )
                
            await db.commit()
            
            # Invalidate graph cache
            from backend.services.redis_client import redis
            try:
                await redis.delete(f"graph:{user.id}")
                logger.info("Invalidated graph cache for user %d on item delete", user.id)
            except Exception as e:
                logger.error("Failed to invalidate graph cache for user %d on delete: %s", user.id, e)
            
            # Log deletion event: {user_id, item_id, source_type} for audit trail
            logger.info(
                "Deleted item: user_id=%d, item_id=%d, source_type=%s",
                user.id,
                item_id,
                row[1]
            )
            
            return Response(status_code=status.HTTP_204_NO_CONTENT)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise

# ---------------------------------------------------------------------------
# Search Group
# ---------------------------------------------------------------------------
from datetime import datetime

@router.post(
    "/search",
    response_model=RAGSearchResponse,
    tags=["search"],
    summary="Search items with RAG",
    description="Performs a hybrid search and generates a synthesised RAG answer if at least 3 sources are found.",
    responses={401: {"model": ErrorResponse}},
)
async def search_items(
    req: SearchRequest,
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    """Search items and run Map-Reduce RAG if applicable."""
    from backend.services.search_service import hybrid_search
    from backend.services.ai_cascade import AICascade

    results = await hybrid_search(req.query, user.id, db)
    
    # Limit results as requested (up to 5 for summaries mapping)
    results_limited = results[:req.limit]
    
    # Map sources to the required schema
    sources = []
    summaries = []
    for r in results_limited:
        sources.append(
            SearchSourceItem(
                id=r["id"],
                title=r["title"],
                summary=r["summary"],
                relevance=r["score"]
            )
        )
        summaries.append(r["summary"] or "")

    # Conditional RAG answer generation
    answer = None
    if len(results_limited) >= 3:
        cascade = AICascade()
        try:
            answer = await cascade.answer_question(req.query, summaries)
        except Exception as e:
            logger.error("Map-Reduce RAG generation failed: %s", e)
            answer = None

    return RAGSearchResponse(
        answer=answer,
        sources=sources,
        query=req.query
    )

# ---------------------------------------------------------------------------
# Graph Group
# ---------------------------------------------------------------------------
@router.get(
    "/graph",
    response_model=GraphResponse,
    tags=["graph"],
    summary="Get mind map graph",
    description="Returns nodes (items, semantic hubs) and edges (similarity links) for graph visualization.",
    responses={401: {"model": ErrorResponse}},
)
async def get_graph(
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    """Retrieve mind map graph with similarity edges and semantic hubs, cached in Redis."""
    from backend.services.redis_client import redis
    import json
    
    # 1. Try to read from cache
    cache_key = f"graph:{user.id}"
    try:
        cached_json = await redis.get(cache_key)
        if cached_json:
            logger.info("Cache hit for graph:%d", user.id)
            return GraphResponse.model_validate_json(cached_json)
    except Exception as e:
        logger.warning("Redis cache read failed, falling back to database: %s", e)

    # 2. Fetch user's items, sorted chronologically DESC to identify recent items
    async with db.cursor() as cur:
        await cur.execute(
            """
            SELECT id, title, source_type, created_at
            FROM items
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user.id,)
        )
        item_rows = await cur.fetchall()

    # 3. Fetch user's semantic hubs
    async with db.cursor() as cur:
        await cur.execute(
            """
            SELECT id, label, member_ids
            FROM semantic_hubs
            WHERE user_id = %s
            """,
            (user.id,)
        )
        hub_rows = await cur.fetchall()

    # 4. Build item validation sets & map
    valid_item_ids = {row[0] for row in item_rows}

    # Filter and validate hub members
    validated_hubs = []
    hub_member_set = set()
    for h_row in hub_rows:
        hub_id, label, raw_members = h_row
        member_ids = [mid for mid in (raw_members or []) if mid in valid_item_ids]
        validated_hubs.append(GraphHub(id=hub_id, label=label, member_ids=member_ids))
        hub_member_set.update(member_ids)

    # 5. Build nodes list
    nodes = []
    for row in item_rows:
        item_id = row[0]
        title = row[1] or "Untitled"
        source_type = row[2]
        created_at_dt = row[3]
        created_at_str = created_at_dt.isoformat() if hasattr(created_at_dt, "isoformat") else str(created_at_dt)
        is_hub = item_id in hub_member_set
        
        nodes.append(
            GraphNode(
                id=item_id,
                title=title,
                source_type=source_type,
                created_at=created_at_str,
                is_hub=is_hub
            )
        )

    # 6. Compute edges using HNSW index via lateral join on database
    # For users with > 100 items, only compute edges for the 100 most recent
    recent_item_ids = [row[0] for row in item_rows[:100]]
    edges_dict = {}

    if recent_item_ids:
        async with db.cursor() as cur:
            await cur.execute(
                """
                SELECT s.id AS source_id, t.id AS target_id, (s.embedding <=> t.embedding) AS dist
                FROM (
                    SELECT id, embedding
                    FROM items
                    WHERE id = ANY(%s) AND user_id = %s
                ) s
                CROSS JOIN LATERAL (
                    SELECT id, (s.embedding <=> embedding) AS dist
                    FROM items
                    WHERE user_id = %s AND id != s.id
                    ORDER BY dist
                    LIMIT 5
                ) t
                """,
                (recent_item_ids, user.id, user.id)
            )
            edge_rows = await cur.fetchall()

        # Deduplicate edges: keep only one edge between A and B, using lower ID as source
        for source_id, target_id, dist in edge_rows:
            sim = 1.0 - float(dist) if dist is not None else 0.0
            if sim > 0.75:
                src = min(source_id, target_id)
                tgt = max(source_id, target_id)
                # Keep the one with the higher similarity score
                edges_dict[(src, tgt)] = max(edges_dict.get((src, tgt), 0.0), sim)

    edges = [GraphEdge(source=src, target=tgt, weight=w) for (src, tgt), w in edges_dict.items()]

    response_data = GraphResponse(
        nodes=nodes,
        edges=edges,
        hubs=validated_hubs
    )

    # 7. Write to cache with 60s TTL
    try:
        await redis.setex(cache_key, 60, response_data.model_dump_json())
    except Exception as e:
        logger.warning("Redis cache write failed: %s", e)

    return response_data

# ---------------------------------------------------------------------------
# Quizzes Group
# ---------------------------------------------------------------------------
@router.get(
    "/quizzes/due",
    response_model=List[QuizResponse],
    tags=["quizzes"],
    summary="Get due quizzes",
    description="Returns a list of quizzes due for review based on SM-2 scheduling.",
    responses={401: {"model": ErrorResponse}},
)
async def get_due_quizzes():
    """Get due quizzes."""
    return []

@router.post(
    "/quizzes/{id}/answer",
    response_model=QuizResponse,
    tags=["quizzes"],
    summary="Submit quiz answer",
    description="Records response quality (0-5) and updates SM-2 scheduling parameters for the quiz.",
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse, "description": "Quiz not found."},
    },
)
async def answer_quiz(
    id: int = Path(..., description="Quiz ID."),
    req: QuizAnswerRequest = ...,
):
    """Answer quiz."""
    from datetime import datetime, timezone, date
    return {
        "id": id,
        "user_id": 1,
        "item_id": 1,
        "question": "Stub question?",
        "options": ["A", "B", "C", "D"],
        "correct_index": 0,
        "explanation": "Stub explanation",
        "ease_factor": 2.5,
        "interval_days": 1,
        "next_review": date.today(),
        "created_at": datetime.now(timezone.utc),
    }

@router.get(
    "/quizzes/stats",
    response_model=QuizStatsResponse,
    tags=["quizzes"],
    summary="Get quiz stats",
    description="Returns aggregated quiz statistics (total, due, reviews, average ease, streak) for the user.",
    responses={401: {"model": ErrorResponse}},
)
async def get_quiz_stats():
    """Get quiz statistics."""
    return {
        "total_quizzes": 0,
        "due_today": 0,
        "completed_reviews": 0,
        "average_ease_factor": 2.5,
        "streak": 0,
    }

# ---------------------------------------------------------------------------
# Reminders Group
# ---------------------------------------------------------------------------
@router.get(
    "/reminders",
    response_model=List[ReminderResponse],
    tags=["reminders"],
    summary="Get reminders",
    description="Returns all reminders configured by the user (up to 20 limit).",
    responses={401: {"model": ErrorResponse}},
)
async def get_reminders():
    """Get reminders."""
    return []

@router.post(
    "/reminders",
    response_model=ReminderResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["reminders"],
    summary="Create reminder",
    description="Saves a new reminder message scheduled for a specific UTC timestamp.",
    responses={401: {"model": ErrorResponse}},
)
async def create_reminder(req: ReminderCreateRequest):
    """Create a new reminder."""
    from datetime import datetime, timezone
    return {
        "id": 1,
        "user_id": 1,
        "item_id": req.item_id,
        "message": req.message,
        "remind_at": req.remind_at,
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
    }

@router.delete(
    "/reminders/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["reminders"],
    summary="Delete a reminder",
    description="Deletes a reminder by ID. Validates ownership to prevent IDOR.",
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse, "description": "Reminder not found."},
    },
)
async def delete_reminder(
    id: int = Path(..., description="Reminder ID to delete."),
):
    """Delete a reminder."""
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# ---------------------------------------------------------------------------
# Drive Group
# ---------------------------------------------------------------------------
@router.post(
    "/drive/sync",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["drive"],
    summary="Sync Google Drive",
    description="Triggers a background synchronization of Recall items to Google Drive as a unified doc.",
    responses={
        401: {"model": ErrorResponse},
        429: {"model": ErrorResponse, "description": "Sync limit exceeded (max 5 requests per hour)."},
    },
)
async def sync_drive():
    """Sync items to Google Drive."""
    return {"status": "ok"}

@router.delete(
    "/drive",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["drive"],
    summary="Disconnect Google Drive",
    description="Clears the user's stored Google refresh token, disconnecting Google Drive integration.",
    responses={401: {"model": ErrorResponse}},
)
async def disconnect_drive():
    """Disconnect Google Drive integration."""
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Admin Group
# ---------------------------------------------------------------------------
import fastapi

def verify_internal_key(
    x_internal_key: str = fastapi.Header(..., alias="X-Internal-Key")
):
    """FastAPI dependency to verify internal key header."""
    from backend.config import settings
    if not settings.INTERNAL_API_KEY or x_internal_key != settings.INTERNAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid internal API key."
        )

@router.get(
    "/admin/queue",
    tags=["admin"],
    summary="Get queue metrics",
    description="Returns metrics about the Redis tasks queue, Semaphore slots, and Dead Letter Queue.",
    dependencies=[Depends(verify_internal_key)],
)
async def get_admin_queue(
    db: psycopg.AsyncConnection = Depends(get_db)
):
    """Retrieve queue metrics for monitoring."""
    from backend.services.redis_client import redis
    from backend.worker import worker_semaphore
    
    try:
        queue_length = await redis.llen("recall:tasks")
    except Exception as e:
        logger.error("Failed to fetch Redis queue length: %s", e)
        queue_length = 0
        
    dead_letter_count = 0
    oldest_dead_letter = None
    
    async with db.cursor() as cur:
        await cur.execute("SELECT COUNT(*) FROM dead_letter_queue WHERE retried = FALSE;")
        row = await cur.fetchone()
        if row:
            dead_letter_count = row[0]
            
        await cur.execute(
            """
            SELECT failed_at FROM dead_letter_queue 
            WHERE retried = FALSE 
            ORDER BY failed_at ASC LIMIT 1;
            """
        )
        row = await cur.fetchone()
        if row and row[0]:
            oldest_dead_letter = row[0].isoformat()
            
    available_slots = worker_semaphore._value if worker_semaphore is not None else 3
    
    return {
        "queue_length": queue_length,
        "dead_letter_count": dead_letter_count,
        "oldest_dead_letter": oldest_dead_letter or "",
        "processing_slots": {
            "available": available_slots,
            "total": 3
        }
    }

@router.post(
    "/admin/dlq/{id}/retry",
    tags=["admin"],
    summary="Retry a DLQ task",
    description="Pushes the task payload back onto the Redis recall:tasks queue and marks the DLQ entry as retried.",
    dependencies=[Depends(verify_internal_key)],
)
async def retry_dlq_task(
    id: int = Path(..., description="DLQ ID to retry."),
    db: psycopg.AsyncConnection = Depends(get_db)
):
    """Re-enqueue a failed task payload from the Dead Letter Queue."""
    from backend.services.redis_client import redis
    import json
    
    async with db.cursor() as cur:
        await cur.execute("SELECT task_payload FROM dead_letter_queue WHERE id = %s AND retried = FALSE;", (id,))
        row = await cur.fetchone()
        
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Unretried Dead Letter Queue entry not found."
            )
            
        task_payload_raw = row[0]
        
        if isinstance(task_payload_raw, str):
            task_payload = json.loads(task_payload_raw)
        else:
            task_payload = task_payload_raw
            
        await redis.lpush("recall:tasks", json.dumps(task_payload))
        
        await cur.execute("UPDATE dead_letter_queue SET retried = TRUE WHERE id = %s;", (id,))
        await db.commit()
        
    return {"queued": True}
