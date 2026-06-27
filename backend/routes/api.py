"""
backend/routes/api.py
=====================
API routes for Recall.
Provides endpoints for items, search, graph visualization, quizzes, reminders, and Drive sync.
All endpoints require bearerAuth or telegramInitData (applied via OpenAPI customizer).
"""

from datetime import date, datetime, timezone, timedelta
import logging
from typing import List, Optional
from fastapi import APIRouter, Path, Query, Response, status, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
import psycopg

from backend.middleware.twa_auth import get_current_user, UserContext
from backend.db.connection import get_db
from backend.services.sm2 import update_sm2
from backend.services.rate_limiter import rate_limit
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
    UserMeResponse,
    UserMeUpdateRequest,
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
    dependencies=[Depends(rate_limit("items", 120))],
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
        
        from backend.config import settings
        if settings.ENV != "test":
            from backend.services.user_service import get_and_update_user_streak
            await get_and_update_user_streak(cur, user.id)
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
from datetime import datetime, timezone

@router.post(
    "/search",
    response_model=RAGSearchResponse,
    tags=["search"],
    summary="Search items with RAG",
    description="Performs a hybrid search and generates a synthesised RAG answer if at least 3 sources are found.",
    responses={401: {"model": ErrorResponse}},
    dependencies=[Depends(rate_limit("search", 60))],
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
                relevance=r["score"],
                source_type=r.get("source_type", "text"),
                source_url=r.get("source_url"),
                tags=r.get("tags", []),
                created_at=r.get("created_at", datetime.now(timezone.utc))
            )
        )
        summaries.append(r["summary"] or "")

    # Conditional RAG answer generation
    answer = None
    if req.rag and len(results_limited) >= 3:
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
    dependencies=[Depends(rate_limit("graph", 30))],
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
        use_hub_only = len(item_rows) > 200
        async with db.cursor() as cur:
            if use_hub_only:
                # Skip full pairwise similarity search. Only compare items sharing a semantic hub.
                await cur.execute(
                    """
                    SELECT s.id AS source_id, t.id AS target_id, t.dist
                    FROM (
                        SELECT id, embedding
                        FROM items
                        WHERE id = ANY(%s) AND user_id = %s
                    ) s
                    CROSS JOIN LATERAL (
                        SELECT t_inner.id AS id, (s.embedding <=> t_inner.embedding) AS dist
                        FROM items t_inner
                        WHERE t_inner.user_id = %s AND t_inner.id != s.id
                          AND EXISTS (
                              SELECT 1 FROM semantic_hubs
                              WHERE user_id = %s
                                AND s.id = ANY(member_ids)
                                AND t_inner.id = ANY(member_ids)
                          )
                        ORDER BY dist
                        LIMIT 6
                    ) t
                    """,
                    (recent_item_ids, user.id, user.id, user.id)
                )
            else:
                # Normal pairwise comparison via HNSW index
                await cur.execute(
                    """
                    SELECT s.id AS source_id, t.id AS target_id, t.dist
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
                        LIMIT 6
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
async def get_due_quizzes(
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    """Get due quizzes."""
    async with db.cursor() as cur:
        await cur.execute(
            """
            SELECT id, user_id, item_id, question, options, correct_index, explanation, ease_factor, interval_days, next_review, created_at
            FROM quizzes
            WHERE user_id = %s
              AND next_review <= CURRENT_DATE
            ORDER BY next_review ASC
            LIMIT 10;
            """,
            (user.id,)
        )
        rows = await cur.fetchall()
        
    quizzes = []
    for r in rows:
        import json
        opts = r[4]
        if isinstance(opts, str):
            opts = json.loads(opts)
        quizzes.append(
            QuizResponse(
                id=r[0],
                user_id=r[1],
                item_id=r[2],
                question=r[3],
                options=opts,
                correct_index=r[5],
                explanation=r[6],
                ease_factor=r[7],
                interval_days=r[8],
                next_review=r[9],
                created_at=r[10],
            )
        )
    return quizzes

@router.post(
    "/quizzes/{id}/answer",
    response_model=QuizResponse,
    tags=["quizzes"],
    summary="Submit quiz answer",
    description="Records response quality (0-5) and updates SM-2 scheduling parameters for the quiz.",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid response quality."},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse, "description": "Access denied."},
        404: {"model": ErrorResponse, "description": "Quiz not found."},
    },
    dependencies=[Depends(rate_limit("quiz_answer", 120))],
)
async def answer_quiz(
    id: int = Path(..., description="Quiz ID."),
    req: QuizAnswerRequest = None,
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    """Answer quiz."""
    if req is None or not (0 <= req.quality <= 5):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quality must be between 0 and 5."
        )
        
    async with db.cursor() as cur:
        # Fetch the quiz
        await cur.execute(
            """
            SELECT id, user_id, item_id, question, options, correct_index, explanation, ease_factor, interval_days, next_review, created_at
            FROM quizzes
            WHERE id = %s AND user_id = %s;
            """,
            (id, user.id)
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quiz not found."
            )
            
        current_ef = row[7]
        current_interval = row[8]
        
        # Calculate new SM-2 values
        new_ef, new_interval = update_sm2(current_ef, current_interval, req.quality)
        
        # Server-side review date calculation
        new_next_review = date.today() + timedelta(days=new_interval)
        
        # Update the quiz
        await cur.execute(
            """
            UPDATE quizzes
            SET ease_factor = %s,
                interval_days = %s,
                next_review = %s
            WHERE id = %s AND user_id = %s;
            """,
            (new_ef, new_interval, new_next_review, id, user.id)
        )
        # Log to quiz_answers
        await cur.execute(
            """
            INSERT INTO quiz_answers (user_id, quiz_id, quality)
            VALUES (%s, %s, %s);
            """,
            (user.id, id, req.quality)
        )
        await db.commit()
        
        import json
        opts = row[4]
        if isinstance(opts, str):
            opts = json.loads(opts)
            
        return QuizResponse(
            id=row[0],
            user_id=row[1],
            item_id=row[2],
            question=row[3],
            options=opts,
            correct_index=row[5],
            explanation=row[6],
            ease_factor=new_ef,
            interval_days=new_interval,
            next_review=new_next_review,
            created_at=row[10],
        )

@router.get(
    "/quizzes/stats",
    response_model=QuizStatsResponse,
    tags=["quizzes"],
    summary="Get quiz stats",
    description="Returns aggregated quiz statistics (total, due, reviews, average ease, mastered definition) for the user.",
    responses={401: {"model": ErrorResponse}},
)
async def get_quiz_stats(
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    """Get quiz statistics."""
    async with db.cursor() as cur:
        await cur.execute(
            """
            WITH stats AS (
              SELECT
                (SELECT COUNT(*) FROM quizzes WHERE user_id = %s) AS total,
                (SELECT COUNT(*) FROM quizzes WHERE user_id = %s AND next_review <= CURRENT_DATE) AS due_today,
                (SELECT COUNT(*) FROM quiz_answers WHERE user_id = %s) AS answered_all_time,
                (SELECT COALESCE(AVG(ease_factor), 2.5) FROM quizzes WHERE user_id = %s) AS avg_ease_factor,
                (SELECT COUNT(*) FROM quizzes WHERE user_id = %s AND ease_factor >= 2.5 AND interval_days >= 7) AS mastered
            ),
            history_days AS (
              SELECT 
                d::date AS review_date,
                TO_CHAR(d, 'Dy') AS day_name
              FROM generate_series(CURRENT_DATE - INTERVAL '6 days', CURRENT_DATE, '1 day') d
            ),
            history_counts AS (
              SELECT 
                hd.review_date,
                hd.day_name,
                COUNT(qa.id) AS count
              FROM history_days hd
              LEFT JOIN quiz_answers qa 
                ON qa.answered_at::date = hd.review_date AND qa.user_id = %s
              GROUP BY hd.review_date, hd.day_name
              ORDER BY hd.review_date ASC
            ),
            history_json AS (
              SELECT COALESCE(json_agg(json_build_object('date', review_date, 'day', day_name, 'count', count)), '[]'::json) AS last_7_days
              FROM history_counts
            )
            SELECT 
              s.total,
              s.due_today,
              s.answered_all_time,
              s.avg_ease_factor,
              s.mastered,
              hj.last_7_days
            FROM stats s, history_json hj;
            """,
            (user.id, user.id, user.id, user.id, user.id, user.id)
        )
        row = await cur.fetchone()
        if not row:
            return {
                "total": 0,
                "due_today": 0,
                "answered_all_time": 0,
                "avg_ease_factor": 0.0,
                "mastered": 0,
                "mastered_definition": "ease_factor >= 2.5 AND interval_days >= 7",
                "last_7_days": [],
            }
        
        total, due_today, answered_all_time, avg_ease_factor, mastered, last_7_days = row
        
        import json
        if isinstance(last_7_days, str):
            history_data = json.loads(last_7_days)
        else:
            history_data = last_7_days
            
        return {
            "total": total,
            "due_today": due_today,
            "answered_all_time": answered_all_time,
            "avg_ease_factor": float(avg_ease_factor) if avg_ease_factor is not None else 0.0,
            "mastered": mastered,
            "mastered_definition": "ease_factor >= 2.5 AND interval_days >= 7",
            "last_7_days": history_data,
        }

# ---------------------------------------------------------------------------
# Reminders Group
# ---------------------------------------------------------------------------
@router.get(
    "/reminders",
    response_model=List[ReminderResponse],
    tags=["reminders"],
    summary="Get reminders",
    description="Returns all reminders configured by the user.",
    responses={401: {"model": ErrorResponse}},
)
async def get_reminders(
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    async with db.cursor() as cur:
        await cur.execute(
            """
            SELECT id, user_id, item_id, message, remind_at, status, created_at
            FROM reminders
            WHERE user_id = %s
            ORDER BY remind_at ASC;
            """,
            (user.id,)
        )
        rows = await cur.fetchall()
        
    reminders = []
    for r_id, r_user_id, r_item_id, r_message, r_remind_at, r_status, r_created_at in rows:
        reminders.append(
            ReminderResponse(
                id=r_id,
                user_id=r_user_id,
                item_id=r_item_id,
                message=r_message,
                remind_at=r_remind_at,
                status=r_status,
                created_at=r_created_at
            )
        )
    return reminders

@router.post(
    "/reminders",
    response_model=ReminderResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["reminders"],
    summary="Create reminder",
    description="Saves a new reminder message scheduled for a specific UTC timestamp.",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid time or active reminders limit reached."},
        401: {"model": ErrorResponse, "description": "Not authenticated."},
    },
)
async def create_new_reminder(
    req: ReminderCreateRequest,
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    from datetime import datetime, timezone
    from backend.services.reminder_service import create_reminder
    
    # 1. Normalize and validate remind_at
    remind_at = req.remind_at
    if remind_at.tzinfo is None:
        remind_at = remind_at.replace(tzinfo=timezone.utc)
    else:
        remind_at = remind_at.astimezone(timezone.utc)
        
    now = datetime.now(timezone.utc)
    if remind_at <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reminder time must be in the future."
        )
        
    try:
        reminder_id, final_message, was_truncated = await create_reminder(
            user.id, req.message, remind_at, db
        )
        await db.commit()
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err)
        )
    except Exception as err:
        logger.error("Failed to create reminder via API: %s", err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create reminder."
        )
        
    # Fetch the newly created reminder details
    async with db.cursor() as cur:
        await cur.execute(
            """
            SELECT id, user_id, item_id, message, remind_at, status, created_at
            FROM reminders
            WHERE id = %s AND user_id = %s;
            """,
            (reminder_id, user.id)
        )
        row = await cur.fetchone()
        
    if not row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve created reminder."
        )
        
    r_id, r_user_id, r_item_id, r_message, r_remind_at, r_status, r_created_at = row
        
    return ReminderResponse(
        id=r_id,
        user_id=r_user_id,
        item_id=r_item_id,
        message=r_message,
        remind_at=r_remind_at,
        status=r_status,
        created_at=r_created_at
    )

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
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    async with db.cursor() as cur:
        await cur.execute(
            """
            DELETE FROM reminders
            WHERE id = %s AND user_id = %s
            RETURNING id;
            """,
            (id, user.id)
        )
        row = await cur.fetchone()
        await db.commit()
        
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reminder not found."
        )
        
    # Remove from Redis sorted set
    from backend.services.redis_client import redis
    try:
        await redis.zrem("reminders:active", str(id))
    except Exception as e:
        logger.warning("Failed to remove deleted reminder %d from Redis active zset: %s", id, e)
        
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# ---------------------------------------------------------------------------
# Drive Group
# ---------------------------------------------------------------------------
@router.post(
    "/drive/sync",
    status_code=status.HTTP_200_OK,
    tags=["drive"],
    summary="Sync Google Drive",
    description="Triggers a synchronization of Recall items to Google Drive as a Google Doc.",
    responses={
        401: {"model": ErrorResponse},
        429: {"model": ErrorResponse, "description": "Sync limit exceeded (max 5 requests per hour)."},
    },
    dependencies=[Depends(rate_limit("sync", 5, 3600))],
)
async def sync_drive(
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db)
):
    """Sync items to Google Drive."""
    from backend.services.drive_sync import sync_user_to_drive
    await sync_user_to_drive(user.id, db)
    return {"status": "ok", "message": "Google Drive synchronization completed successfully."}

@router.delete(
    "/drive",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["drive"],
    summary="Disconnect Google Drive",
    description="Clears the user's stored Google refresh token, disconnecting Google Drive integration.",
    responses={401: {"model": ErrorResponse}},
)
async def disconnect_drive(
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db)
):
    """Disconnect Google Drive integration."""
    # 1. Fetch user's current Google refresh token
    async with db.cursor() as cur:
        await cur.execute(
            "SELECT google_refresh_token FROM users WHERE id = %s;",
            (user.id,)
        )
        row = await cur.fetchone()
        google_refresh_token = row[0] if row else None

    # 2. If it is already NULL/disconnected, return 204
    if not google_refresh_token:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # 3. Decrypt token securely
    from backend.services.encryption import decrypt
    try:
        decrypted_token = decrypt(google_refresh_token)
    except Exception:
        logger.error("Failed to decrypt Google refresh token during disconnect. Proceeding anyway.")
        decrypted_token = None

    # 4. Invoke Google token revocation endpoint if token is present
    if decrypted_token:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = f"https://oauth2.googleapis.com/revoke?token={decrypted_token}"
                resp = await client.post(url)
                resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            # Do NOT log the exception object e or e.request.url to avoid token leakage
            status_code = e.response.status_code
            if status_code == 400:
                logger.info("Google token revoke returned 400 (already revoked). Proceeding to clear local token.")
            elif status_code == 503:
                logger.error("Google token revoke returned 503. Proceeding to clear local token anyway.")
            else:
                logger.error(f"Google token revoke failed with status {status_code}. Proceeding anyway.")
        except Exception:
            # Secure error logging: do NOT log the exception or request/response info directly
            logger.error("Network or connection error reaching Google token revoke endpoint. Proceeding anyway.")

    # 5. Reset columns locally in all cases (ensure disconnect succeeds)
    async with db.cursor() as cur:
        await cur.execute(
            """
            UPDATE users
            SET google_refresh_token = NULL,
                google_last_sync = NULL
            WHERE id = %s;
            """,
            (user.id,)
        )
        await db.commit()

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


# ---------------------------------------------------------------------------
# WebSocket Group
# ---------------------------------------------------------------------------
from fastapi import WebSocket, WebSocketDisconnect

class ConnectionManager:
    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        from backend.routes.websocket import active_connections
        if user_id in active_connections:
            try:
                await active_connections[user_id].close(code=1000)
            except Exception:
                pass
        active_connections[user_id] = websocket

    def disconnect(self, user_id: int, websocket: WebSocket):
        from backend.routes.websocket import active_connections
        if user_id in active_connections and active_connections[user_id] == websocket:
            del active_connections[user_id]

    async def send_personal_message(self, message: dict, user_id: int):
        from backend.routes.websocket import broadcast
        await broadcast(user_id, message)

manager = ConnectionManager()

# ---------------------------------------------------------------------------
# User Profile & Settings Group
# ---------------------------------------------------------------------------
@router.get(
    "/me",
    response_model=UserMeResponse,
    tags=["profile"],
    summary="Get user profile and settings",
    description="Returns current authenticated user details, timezone offset, and stats.",
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse, "description": "User not found."},
    },
)
async def get_user_me(
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    async with db.cursor() as cur:
        await cur.execute(
            "SELECT timezone_offset, streak_count, google_refresh_token, google_last_sync, digest_enabled FROM users WHERE id = %s;",
            (user.id,)
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        db_offset = row[0] or 0
        has_drive = row[2] is not None
        google_last_sync = row[3]
        digest_enabled = row[4] if row[4] is not None else True

        from backend.services.user_service import get_and_update_user_streak
        streak = await get_and_update_user_streak(cur, user.id)
        await db.commit()

        # Convert minutes (stored in DB) to hours for API layer (float division)
        offset_hours = round(db_offset / 60.0, 2)

        # Total saves
        await cur.execute(
            "SELECT COUNT(*) FROM items WHERE user_id = %s;",
            (user.id,)
        )
        total_saves_row = await cur.fetchone()
        total_saves = total_saves_row[0] if total_saves_row else 0

        # Quizzes answered
        await cur.execute(
            "SELECT COUNT(*) FROM quizzes WHERE user_id = %s;",
            (user.id,)
        )
        quizzes_row = await cur.fetchone()
        quizzes_answered = quizzes_row[0] if quizzes_row else 0

        # last_7_days_activity (UTC-based)
        await cur.execute(
            """
            WITH days AS (
              SELECT generate_series(timezone('utc', now())::date - 6, timezone('utc', now())::date, '1 day')::date AS day
            )
            SELECT d.day, COUNT(i.id) > 0 AS has_activity
            FROM days d
            LEFT JOIN items i ON i.user_id = %s AND i.created_at::date = d.day
            GROUP BY d.day
            ORDER BY d.day;
            """,
            (user.id,)
        )
        activity_rows = await cur.fetchall()
        last_7_days_activity = [row[1] for row in activity_rows]

        # last_activity_date (UTC-based)
        await cur.execute(
            "SELECT MAX(created_at) FROM items WHERE user_id = %s;",
            (user.id,)
        )
        last_activity_row = await cur.fetchone()
        last_activity_date = last_activity_row[0] if last_activity_row else None

        if google_last_sync and google_last_sync.tzinfo is None:
            google_last_sync = google_last_sync.replace(tzinfo=timezone.utc)
        if last_activity_date and last_activity_date.tzinfo is None:
            last_activity_date = last_activity_date.replace(tzinfo=timezone.utc)

        return {
            "timezone_offset": offset_hours,
            "streak_count": streak,
            "drive_connected": has_drive,
            "google_last_sync": google_last_sync.isoformat() if google_last_sync else None,
            "total_saves": total_saves,
            "quizzes_answered": quizzes_answered,
            "last_7_days_activity": last_7_days_activity,
            "last_activity_date": last_activity_date,
            "digest_enabled": digest_enabled,
        }

@router.patch(
    "/me",
    response_model=UserMeResponse,
    tags=["profile"],
    summary="Update user settings",
    description="Updates user settings (e.g., timezone_offset in hours, stored as minutes in DB).",
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse, "description": "User not found."},
    },
)
async def update_user_me(
    req: UserMeUpdateRequest,
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    async with db.cursor() as cur:
        # Check if user exists
        await cur.execute(
            "SELECT timezone_offset FROM users WHERE id = %s;",
            (user.id,)
        )
        user_exists = await cur.fetchone()
        if not user_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Only update fields that are provided in the request
        update_fields = []
        params = []

        if req.timezone_offset is not None:
            # Convert hours to minutes
            offset_minutes = int(req.timezone_offset * 60)
            update_fields.append("timezone_offset = %s")
            params.append(offset_minutes)

        if req.digest_enabled is not None:
            update_fields.append("digest_enabled = %s")
            params.append(req.digest_enabled)

        if update_fields:
            params.append(user.id)
            query = f"UPDATE users SET {', '.join(update_fields)} WHERE id = %s;"
            await cur.execute(query, tuple(params))
            await db.commit()

        # Fetch the updated user details
        await cur.execute(
            "SELECT timezone_offset, streak_count, google_refresh_token, google_last_sync, digest_enabled FROM users WHERE id = %s;",
            (user.id,)
        )
        row = await cur.fetchone()
        db_offset = row[0] or 0
        has_drive = row[2] is not None
        google_last_sync = row[3]
        digest_enabled = row[4] if row[4] is not None else True

        from backend.services.user_service import get_and_update_user_streak
        streak = await get_and_update_user_streak(cur, user.id)
        await db.commit()
        offset_hours = round(db_offset / 60.0, 2)

        # Total saves
        await cur.execute(
            "SELECT COUNT(*) FROM items WHERE user_id = %s;",
            (user.id,)
        )
        total_saves_row = await cur.fetchone()
        total_saves = total_saves_row[0] if total_saves_row else 0

        # Quizzes answered
        await cur.execute(
            "SELECT COUNT(*) FROM quizzes WHERE user_id = %s;",
            (user.id,)
        )
        quizzes_row = await cur.fetchone()
        quizzes_answered = quizzes_row[0] if quizzes_row else 0

        # last_7_days_activity (UTC-based)
        await cur.execute(
            """
            WITH days AS (
              SELECT generate_series(timezone('utc', now())::date - 6, timezone('utc', now())::date, '1 day')::date AS day
            )
            SELECT d.day, COUNT(i.id) > 0 AS has_activity
            FROM days d
            LEFT JOIN items i ON i.user_id = %s AND i.created_at::date = d.day
            GROUP BY d.day
            ORDER BY d.day;
            """,
            (user.id,)
        )
        activity_rows = await cur.fetchall()
        last_7_days_activity = [row[1] for row in activity_rows]

        # last_activity_date (UTC-based)
        await cur.execute(
            "SELECT MAX(created_at) FROM items WHERE user_id = %s;",
            (user.id,)
        )
        last_activity_row = await cur.fetchone()
        last_activity_date = last_activity_row[0] if last_activity_row else None

        if google_last_sync and google_last_sync.tzinfo is None:
            google_last_sync = google_last_sync.replace(tzinfo=timezone.utc)
        if last_activity_date and last_activity_date.tzinfo is None:
            last_activity_date = last_activity_date.replace(tzinfo=timezone.utc)

        return {
            "timezone_offset": offset_hours,
            "streak_count": streak,
            "drive_connected": has_drive,
            "google_last_sync": google_last_sync.isoformat() if google_last_sync else None,
            "total_saves": total_saves,
            "quizzes_answered": quizzes_answered,
            "last_7_days_activity": last_7_days_activity,
            "last_activity_date": last_activity_date,
            "digest_enabled": digest_enabled,
        }

@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["profile"],
    summary="Delete user account",
    description="Deletes the user account and clears all associated data via database cascade.",
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse, "description": "User not found."},
    },
)
async def delete_user_me(
    response: Response,
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    async with db.cursor() as cur:
        # Check if user exists
        await cur.execute(
            "SELECT id FROM users WHERE id = %s;",
            (user.id,)
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Perform deletion
        await cur.execute(
            "DELETE FROM users WHERE id = %s;",
            (user.id,)
        )
        await db.commit()

    # Clear auth cookies
    response.delete_cookie("recall_session", httponly=True, secure=True, samesite="lax")
    response.delete_cookie("jwt", httponly=True, secure=True, samesite="lax")

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/export",
    tags=["profile"],
    summary="Export user data (GDPR)",
    description="Streams all user-owned data (profile info, decrypted items, reminders, and quizzes) as a JSON file.",
    responses={
        401: {"model": ErrorResponse},
        429: {"model": ErrorResponse, "description": "Export rate limit exceeded (1 export per 24 hours)."},
    },
    dependencies=[Depends(rate_limit("export", 1, 86400))],
)
async def export_user_data(
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db)
):
    from fastapi.responses import StreamingResponse
    import json
    from datetime import datetime, timezone

    async def export_generator():
        # 1. Fetch user profile
        async with db.cursor() as cur:
            await cur.execute(
                "SELECT telegram_chat_id, streak_count, timezone_offset, created_at FROM users WHERE id = %s;",
                (user.id,)
            )
            user_row = await cur.fetchone()
            
        if not user_row:
            yield "{}"
            return

        user_data = {
            "telegram_chat_id": user_row[0],
            "streak_count": user_row[1],
            "timezone_offset": user_row[2],
            "created_at": user_row[3].isoformat() if user_row[3] else None
        }

        export_date = datetime.now(timezone.utc).isoformat()
        
        # Start main JSON document and user profile info
        yield '{\n  "export_date": "%s",\n  "user": %s,\n  "items": [' % (
            export_date,
            json.dumps(user_data, indent=4).replace("\n", "\n  ")
        )

        # 2. Query and stream items
        item_count = 0
        first_item = True
        
        async with db.cursor() as cur:
            await cur.execute(
                """
                SELECT id, source_type, source_url, raw_text, summary, title, tags, created_at
                FROM items
                WHERE user_id = %s
                ORDER BY created_at DESC;
                """,
                (user.id,)
            )
            async for row in cur:
                item_id, source_type, source_url, raw_text, summary, title, tags, created_at = row
                
                # Decrypt raw_text
                raw_text_decrypted = None
                if raw_text:
                    try:
                        from backend.services.encryption import decrypt
                        raw_text_decrypted = decrypt(raw_text)
                    except Exception:
                        raw_text_decrypted = "[Decryption Failed]"

                item_dict = {
                    "id": item_id,
                    "source_type": source_type,
                    "source_url": source_url,
                    "raw_text_decrypted": raw_text_decrypted,
                    "summary": summary,
                    "title": title,
                    "tags": tags or [],
                    "created_at": created_at.isoformat() if created_at else None
                }

                item_json = json.dumps(item_dict, indent=4).replace("\n", "\n    ")
                
                if not first_item:
                    yield ",\n    " + item_json
                else:
                    yield "\n    " + item_json
                    first_item = False
                
                item_count += 1

        # Close items array and start reminders array
        yield '\n  ],\n  "reminders": ['

        # 3. Query and stream reminders
        first_reminder = True
        async with db.cursor() as cur:
            await cur.execute(
                """
                SELECT id, item_id, message, remind_at, status, created_at
                FROM reminders
                WHERE user_id = %s
                ORDER BY remind_at DESC;
                """,
                (user.id,)
            )
            async for row in cur:
                rem_id, rem_item_id, message, remind_at, status, created_at = row
                rem_dict = {
                    "id": rem_id,
                    "item_id": rem_item_id,
                    "message": message,
                    "remind_at": remind_at.isoformat() if remind_at else None,
                    "status": status,
                    "created_at": created_at.isoformat() if created_at else None
                }

                rem_json = json.dumps(rem_dict, indent=4).replace("\n", "\n    ")
                
                if not first_reminder:
                    yield ",\n    " + rem_json
                else:
                    yield "\n    " + rem_json
                    first_reminder = False

        # Close reminders array and start quizzes array
        yield '\n  ],\n  "quizzes": ['

        # 4. Query and stream quizzes
        first_quiz = True
        async with db.cursor() as cur:
            await cur.execute(
                """
                SELECT id, item_id, question, options, correct_index, explanation, ease_factor, interval_days, next_review, created_at
                FROM quizzes
                WHERE user_id = %s
                ORDER BY created_at DESC;
                """,
                (user.id,)
            )
            async for row in cur:
                q_id, q_item_id, question, options, correct_index, explanation, ease_factor, interval_days, next_review, created_at = row
                from datetime import date
                q_dict = {
                    "id": q_id,
                    "item_id": q_item_id,
                    "question": question,
                    "options": options,
                    "correct_index": correct_index,
                    "explanation": explanation,
                    "ease_factor": ease_factor,
                    "interval_days": interval_days,
                    "next_review": next_review.isoformat() if isinstance(next_review, (datetime, date)) else str(next_review) if next_review else None,
                    "created_at": created_at.isoformat() if created_at else None
                }

                q_json = json.dumps(q_dict, indent=4).replace("\n", "\n    ")
                
                if not first_quiz:
                    yield ",\n    " + q_json
                else:
                    yield "\n    " + q_json
                    first_quiz = False

        # Close quizzes array and document
        yield '\n  ]\n}'
        
        # Structured audit log containing user_id, export_date, and item_count ONLY
        logger.info(
            "Audit Log - Export completed: user_id=%d, export_date=%s, item_count=%d",
            user.id,
            export_date,
            item_count
        )

    # Format Content-Disposition header with current date
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    headers = {
        "Content-Disposition": f'attachment; filename="recall-export-{date_str}.json"'
    }

    return StreamingResponse(
        export_generator(),
        media_type="application/json",
        headers=headers
    )


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    jwt_cookie = websocket.cookies.get("recall_session") or websocket.cookies.get("jwt")
    if not jwt_cookie:
        await websocket.close(code=4001)
        return

    try:
        from backend.middleware.twa_auth import verify_jwt
        from backend.config import settings
        payload = verify_jwt(jwt_cookie, settings.JWT_SECRET)
        user_id_str = payload.get("sub")
        if not user_id_str:
            await websocket.close(code=4001)
            return
        user_id = int(user_id_str)
    except Exception:
        await websocket.close(code=4001)
        return

    await manager.connect(user_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
    except Exception:
        manager.disconnect(user_id, websocket)

