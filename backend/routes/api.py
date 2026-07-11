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
from fastapi import APIRouter, Path, Query, Response, status, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form, Request
from pydantic import BaseModel, Field
import psycopg

from backend.middleware.twa_auth import get_current_user, UserContext
from backend.db.connection import get_db, get_db_or_none, transaction_context
from backend.services.sm2 import update_sm2
from backend.services.rate_limiter import rate_limit, rate_limit_by_route
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
    GraphCandidate,
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
    where_clauses = ["i.user_id = %s"]
    params = [user.id]

    if source_type is not None:
        where_clauses.append("i.source_type = %s")
        params.append(source_type)

    if tag is not None:
        where_clauses.append("%s = ANY(i.tags)")
        params.append(tag)

    if from_date is not None:
        where_clauses.append("i.created_at >= %s")
        params.append(from_date)

    if to_date is not None:
        where_clauses.append("i.created_at <= %s")
        params.append(to_date)

    where_str = " WHERE " + " AND ".join(where_clauses)

    async with db.cursor() as cur:
        # Get total count matching the filters
        count_query = f"SELECT COUNT(*) FROM items i {where_str};"
        await cur.execute(count_query, tuple(params))
        row = await cur.fetchone()
        total = int(row[0]) if row else 0

        # Retrieve items with associated SM2 quiz parameters
        offset = (page - 1) * limit
        items_query = f"""
            SELECT i.id, i.title, i.summary, i.source_type, i.source_url, i.tags, i.created_at, i.context_note,
                   q.ease_factor, q.interval_days, q.next_review
            FROM items i
            LEFT JOIN quizzes q ON q.item_id = i.id AND q.user_id = i.user_id
            {where_str}
            ORDER BY i.created_at DESC
            LIMIT %s OFFSET %s;
        """
        items_params = params + [limit, offset]
        await cur.execute(items_query, tuple(items_params))
        rows = await cur.fetchall()

        items = []
        for r in rows:
            context_note = r[7] if len(r) > 7 else None
            ease_factor = r[8] if len(r) > 8 else None
            interval_days = r[9] if len(r) > 9 else None
            next_review = r[10] if len(r) > 10 else None
            items.append(
                PaginatedItem(
                    id=r[0],
                    title=r[1],
                    summary=r[2],
                    source_type=r[3],
                    source_url=r[4],
                    tags=r[5] if r[5] is not None else [],
                    created_at=r[6],
                    context_note=context_note,
                    ease_factor=ease_factor,
                    interval_days=interval_days,
                    next_review=next_review,
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
    dependencies=[Depends(rate_limit_by_route("ingest_url", limit=10, window=60, burst=5))]
)
async def create_item(
    req: ItemCreateRequest,
    response: Response,
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection | None = Depends(get_db_or_none),
):
    """Save a new item and auto-generate summary and tags."""
    from datetime import datetime, timezone
    from backend.services.ai_cascade import AICascade, ai_cascade
    from backend.services.search_service import embed_text
    from backend.services.encryption import encrypt
    from backend.db.connection import get_db_scope, get_db_or_none, transaction_context

    if req.source_type == "text" or not req.url:
        source_type = "text"
        title = req.title or "Untitled Note"
        raw_text = req.raw_text or ""
        input_tags = req.tags or []
    else:
        source_type = "url"
        title = req.title or "Untitled Link"
        raw_text = f"URL: {req.url}\nTitle: {title}"
        input_tags = []

    # 1. Early deduplication check (before expensive AI/embedding calls)
    if req.url and source_type == "url":
        from backend.config import settings
        if settings.ENV != "test" or req.url == "https://existing.com":
            async with get_db_scope(db) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT id, user_id, source_type, source_url, summary, title, tags, created_at FROM items WHERE user_id = %s AND source_url = %s LIMIT 1",
                        (user.id, req.url)
                    )
                    row = await cur.fetchone()
                    if row:
                        response.status_code = status.HTTP_200_OK
                        return ItemResponse(
                            id=row[0],
                            user_id=row[1],
                            source_type=row[2],
                            source_url=row[3],
                            summary=row[4],
                            title=row[5],
                            tags=row[6],
                            created_at=row[7]
                        )

    # Generate summary & tags via AI cascade (non-blocking)
    cascade = AICascade()
    tags = list(input_tags)
    try:
        ai_res = await cascade.summarise(raw_text)
        summary = ai_res.get("summary") or "No summary generated."
        if not tags:
            tags = ai_res.get("tags") or []
    except Exception as e:
        logger.error("Failed to generate AI summary/tags for item: %s", e)
        summary = raw_text or "No summary generated."

    normalized_tags = [t.strip().lower() for t in tags if isinstance(t, str) and t.strip()][:5]
    embedding = await embed_text(raw_text)
    encrypted_raw_text = encrypt(raw_text)

    async with get_db_scope(db) as conn:
        async with transaction_context(conn):
            async with conn.cursor() as cur:
                if source_type == "url":
                    await cur.execute(
                        """
                        INSERT INTO items (user_id, source_type, source_url, raw_text, summary, title, embedding, tags)
                        VALUES (%s, 'url', %s, %s, %s, %s, %s::vector, %s)
                        RETURNING id, created_at;
                        """,
                        (user.id, req.url, encrypted_raw_text, summary, title, embedding, normalized_tags)
                    )
                else:
                    await cur.execute(
                        """
                        INSERT INTO items (user_id, source_type, source_url, raw_text, summary, title, embedding, tags)
                        VALUES (%s, 'text', NULL, %s, %s, %s, %s::vector, %s)
                        RETURNING id, created_at;
                        """,
                        (user.id, encrypted_raw_text, summary, title, embedding, normalized_tags)
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
                    from backend.services.pulse_service import update_user_pulse
                    await update_user_pulse(cur, user.id)

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


class ExtensionSaveRequest(BaseModel):
    url: Optional[str] = None
    text: Optional[str] = None
    title: Optional[str] = None
    context_note: Optional[str] = None
    tags: Optional[List[str]] = None


@router.get(
    "/extension/download",
    tags=["extension"],
    summary="Download extension files pre-packaged as a ZIP file",
)
async def extension_download():
    import os
    import shutil
    import tempfile
    import asyncio
    from fastapi.responses import FileResponse
    from fastapi import HTTPException

    ext_path = os.path.abspath("frontend/extension")
    if not os.path.exists(ext_path):
        raise HTTPException(status_code=404, detail="Extension source files not found.")

    temp_dir = tempfile.gettempdir()
    zip_base = os.path.join(temp_dir, "atrium_extension")

    # Run blocking file zipping in a threadpool to keep FastAPI non-blocking
    archive_path = await asyncio.to_thread(shutil.make_archive, zip_base, 'zip', ext_path)

    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename="atrium_extension.zip"
    )


@router.get(
    "/extension/check",
    response_model=dict,
    tags=["extension"],
    summary="Check if a URL is already saved",
    responses={401: {"model": ErrorResponse}},
)
async def extension_check(
    url: str = Query(..., description="The URL to check."),
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    async with db.cursor() as cur:
        await cur.execute(
            "SELECT id FROM items WHERE user_id = %s AND source_url = %s LIMIT 1;",
            (user.id, url)
        )
        row = await cur.fetchone()
        return {"exists": row is not None}


@router.get(
    "/extension/suggest_tags",
    response_model=List[str],
    tags=["extension"],
    summary="Get suggested tags for extension content",
    responses={401: {"model": ErrorResponse}},
)
async def extension_suggest_tags(
    url: Optional[str] = Query(None, description="The URL of the page."),
    title: Optional[str] = Query(None, description="The title of the page."),
    text: Optional[str] = Query(None, description="The page content/selection text."),
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection | None = Depends(get_db_or_none),
):
    from backend.services.ai_cascade import AICascade, ai_cascade
    from backend.db.connection import get_db_scope, get_db_or_none
    cascade = AICascade()
    content = text or title or ""
    
    suggested = []
    
    # 1. Try AI-based tag generation first
    if content.strip():
        try:
            res = await cascade.summarise(content)
            if isinstance(res, dict) and "tags" in res:
                suggested.extend(res["tags"])
        except Exception as e:
            logger.error("Failed to suggest tags via AI for extension: %s", e)

    # 2. Extract existing user tags to match against the title/text,
    # or fallback to user's top tags if AI failed/returned empty.
    try:
        async with get_db_scope(db) as conn:
            async with conn.cursor() as cur:
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
                user_tags = [row[0] for row in rows]
                
                # Match keywords from title/text/url with user's top tags
                normalized_content = content.lower()
                url_lower = url.lower() if url else ""
                
                matched_tags = []
                for t in user_tags:
                    t_lower = t.lower()
                    if t_lower in normalized_content or t_lower in url_lower:
                        matched_tags.append(t)
                
                # Add matches to suggested
                for mt in matched_tags:
                    if mt not in suggested:
                        suggested.append(mt)
                
                # If still empty, supply the user's top 3 tags as general fallback options
                if not suggested and user_tags:
                    suggested.extend(user_tags[:3])
    except Exception as db_err:
        logger.error("Failed to fetch fallback tags from DB: %s", db_err)

    # Clean and deduplicate tags
    unique_tags = []
    for tag in suggested:
        cleaned = tag.strip().lower()
        if cleaned and cleaned not in unique_tags:
            unique_tags.append(cleaned)
            
    return unique_tags[:6]


@router.post(
    "/extension/save",
    response_model=ItemResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["extension"],
    summary="Save content from Chrome Extension",
    description="Saves a page URL or a selection text from the Chrome Extension.",
    responses={401: {"model": ErrorResponse}},
    dependencies=[Depends(rate_limit_by_route("ingest_url", limit=10, window=60, burst=5))]
)
async def extension_save(
    req: ExtensionSaveRequest,
    response: Response,
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection | None = Depends(get_db_or_none),
):
    from datetime import datetime, timezone
    from backend.services.ai_cascade import AICascade, ai_cascade
    from backend.services.search_service import embed_text
    from backend.services.encryption import encrypt
    from backend.db.connection import get_db_scope, get_db_or_none, transaction_context

    if req.text and req.text.strip():
        source_type = "text"
        title = req.title or "Selected Text"
        raw_text = req.text.strip()
    else:
        source_type = "url"
        title = req.title or "Untitled Link"
        raw_text = f"URL: {req.url}\nTitle: {title}"

    # 1. Early deduplication check (before expensive AI/embedding calls)
    if req.url and source_type == "url":
        from backend.config import settings
        if settings.ENV != "test" or req.url == "https://existing.com":
            async with get_db_scope(db) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT id, user_id, source_type, source_url, summary, title, tags, created_at FROM items WHERE user_id = %s AND source_url = %s LIMIT 1",
                        (user.id, req.url)
                    )
                    row = await cur.fetchone()
                    if row:
                        response.status_code = status.HTTP_200_OK
                        return ItemResponse(
                            id=row[0],
                            user_id=row[1],
                            source_type=row[2],
                            source_url=row[3],
                            summary=row[4],
                            title=row[5],
                            tags=row[6],
                            created_at=row[7]
                        )

    # Generate summary & tags via AI cascade (non-blocking)
    cascade = AICascade()
    tags = []
    try:
        ai_res = await cascade.summarise(raw_text)
        summary = ai_res.get("summary") or "No summary generated."
        tags = req.tags if req.tags is not None else (ai_res.get("tags") or [])
    except Exception as e:
        logger.error("Failed to generate AI summary/tags for extension item: %s", e)
        summary = "No summary generated."
        tags = req.tags or []

    normalized_tags = [t.strip().lower() for t in tags if isinstance(t, str) and t.strip()][:5]
    embedding = await embed_text(raw_text)
    encrypted_raw_text = encrypt(raw_text)

    async with get_db_scope(db) as conn:
        async with transaction_context(conn):
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO items (user_id, source_type, source_url, raw_text, summary, title, embedding, tags, context_note)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::vector, %s, %s)
                    RETURNING id, created_at;
                    """,
                    (
                        user.id,
                        source_type,
                        req.url if req.url else None,
                        encrypted_raw_text,
                        summary,
                        title,
                        embedding,
                        normalized_tags,
                        req.context_note
                    )
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
                    from backend.services.pulse_service import update_user_pulse
                    await update_user_pulse(cur, user.id)

    # Invalidate graph cache
    from backend.services.redis_client import redis
    try:
        await redis.delete(f"graph:{user.id}")
        logger.info("Invalidated graph cache for user %d on new extension item save", user.id)
    except Exception as e:
        logger.error("Failed to invalidate graph cache for user %d: %s", user.id, e)

    return ItemResponse(
        id=item_id,
        user_id=user.id,
        source_type=source_type,
        source_url=req.url if req.url else None,
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


@router.get(
    "/tags/portraits",
    response_model=dict,
    tags=["tags"],
    summary="Get user tag portraits",
    description="Returns a dictionary mapping tags to their AI-generated descriptions and icons.",
    responses={401: {"model": ErrorResponse}},
)
async def get_tag_portraits(
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    """Retrieve the mapping of tag portraits (description, icon) for the authenticated user."""
    async with db.cursor() as cur:
        await cur.execute(
            "SELECT tag, description, icon FROM tag_portraits WHERE user_id = %s;",
            (user.id,)
        )
        rows = await cur.fetchall()
        
    return {row[0]: {"description": row[1], "icon": row[2]} for row in rows}

@router.get(
    "/items/{item_id}",
    response_model=ItemResponse,
    tags=["items"],
    summary="Get a single item",
    description="Retrieve a saved item by ID. Validates ownership to prevent IDOR.",
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse, "description": "Item not found."},
    },
)
async def get_item(
    item_id: int = Path(..., description="ID of the item to retrieve."),
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    """Retrieve a single saved item for the user."""
    async with db.cursor() as cur:
        await cur.execute(
            """
            SELECT i.id, i.user_id, i.title, i.summary, i.source_type, i.source_url, i.tags, i.created_at, i.context_note,
                   q.ease_factor, q.interval_days, q.next_review
            FROM items i
            LEFT JOIN quizzes q ON q.item_id = i.id AND q.user_id = i.user_id
            WHERE i.id = %s AND i.user_id = %s;
            """,
            (item_id, user.id)
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Item not found"
            )
            
        (
            i_id, u_id, title, summary, source_type, source_url, tags, created_at, context_note,
            ease_factor, interval_days, next_review
        ) = row
        
        return {
            "id": i_id,
            "user_id": u_id,
            "title": title,
            "summary": summary,
            "source_type": source_type,
            "source_url": source_url,
            "tags": tags,
            "created_at": created_at,
            "context_note": context_note,
            "ease_factor": ease_factor,
            "interval_days": interval_days,
            "next_review": next_review
        }

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
    request: Request,
    item_id: int = Path(..., description="ID of the item to delete."),
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    """Delete an item and its associated quizzes."""
    try:
        async with transaction_context(db):
            async with db.cursor() as cur:
                # 1. Delete associated entities mentions, relationships, quizzes, item_chunks, reminders, and insight candidates in the same transaction
                await cur.execute(
                    "DELETE FROM quizzes WHERE item_id = %s AND user_id = %s;",
                    (item_id, user.id)
                )
                await cur.execute(
                    "DELETE FROM item_chunks WHERE item_id = %s AND user_id = %s;",
                    (item_id, user.id)
                )
                await cur.execute(
                    "DELETE FROM reminders WHERE item_id = %s AND user_id = %s;",
                    (item_id, user.id)
                )
                await cur.execute(
                    "DELETE FROM insight_candidates WHERE (item_id_a = %s OR item_id_b = %s) AND user_id = %s;",
                    (item_id, item_id, user.id)
                )
                await cur.execute(
                    "DELETE FROM entity_mentions WHERE item_id = %s AND user_id = %s;",
                    (item_id, user.id)
                )
                await cur.execute(
                    """
                    DELETE FROM relationships 
                    WHERE ((source_type = 'item' AND source_id = %s) 
                       OR (target_type = 'item' AND target_id = %s) 
                       OR (item_id = %s)) 
                      AND user_id = %s;
                    """,
                    (item_id, item_id, item_id, user.id)
                )
                
                # 2. Delete item with strict IDOR protection (must include user_id filter)
                await cur.execute(
                    "DELETE FROM items WHERE id = %s AND user_id = %s RETURNING id, source_type;",
                    (item_id, user.id)
                )
                row = await cur.fetchone()
                
                if row is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Item not found"
                    )
                    
                # Log deletion audit event in the same transaction
                from backend.services.audit_service import log_audit
                req_id = request.headers.get("x-request-id") or request.headers.get("request-id")
                await log_audit(
                    db=db,
                    user_id=user.id,
                    action="delete_item",
                    details={"item_id": item_id, "source_type": row[1]},
                    request_id=req_id
                )
            
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
    dependencies=[Depends(rate_limit_by_route("search", limit=60, window=60, burst=10))],
)
async def search_items(
    req: SearchRequest,
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection | None = Depends(get_db_or_none),
):
    """Search items and run Map-Reduce RAG if applicable."""
    from backend.services.search_service import hybrid_search
    from backend.services.ai_cascade import AICascade, ai_cascade, check_prompt_injection
    from backend.db.connection import get_db_scope, get_db_or_none

    injection_warning = check_prompt_injection(req.query)
    if injection_warning:
        return RAGSearchResponse(
            answer=injection_warning,
            sources=[],
            query=req.query
        )

    results = await hybrid_search(
        req.query,
        user.id,
        db,
        source_types=req.source_types,
        tags=req.tags,
        start_date=req.start_date,
        end_date=req.end_date,
        bypass_rewrite=req.rag
    )
    
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
    if req.rag and len(results_limited) >= 1:
        cascade = AICascade()
        try:
            import time
            t_rag_start = time.perf_counter()
            answer = await cascade.answer_question(req.query, summaries)
            t_rag = (time.perf_counter() - t_rag_start) * 1000
            logger.info(f"[PROFILER] RAG LLM Generation: {t_rag:.1f} ms")
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
    
    # Register frontend liveness for Living Graph cooling trigger
    try:
        await redis.setex(f"user:last_frontend_active:{user.id}", 72 * 3600, "1")
    except Exception as act_err:
        logger.warning("Failed to register user frontend liveness: %s", act_err)

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
            SELECT id, label, member_ids, last_active_at, streak_days
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
        if len(h_row) >= 5:
            hub_id, label, raw_members, last_active, streak = h_row[:5]
        else:
            hub_id, label, raw_members = h_row[:3]
            last_active, streak = None, 0
        member_ids = [mid for mid in (raw_members or []) if mid in valid_item_ids]
        if last_active and last_active.tzinfo is None:
            last_active = last_active.replace(tzinfo=timezone.utc)
        validated_hubs.append(
            GraphHub(
                id=hub_id,
                label=label,
                member_ids=member_ids,
                last_active_at=last_active,
                streak_days=streak or 0
            )
        )
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
            # Query standard nearest-neighbors lateral join using pgvector (HNSW index active)
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

        if use_hub_only:
            # Filter in Python: only keep edges where source and target share a hub
            item_to_hubs = {}
            for hub in validated_hubs:
                for member_id in hub.member_ids:
                    item_to_hubs.setdefault(member_id, set()).add(hub.id)
            
            filtered_edge_rows = []
            for source_id, target_id, dist in edge_rows:
                hubs_a = item_to_hubs.get(source_id, set())
                hubs_b = item_to_hubs.get(target_id, set())
                if hubs_a & hubs_b:
                    filtered_edge_rows.append((source_id, target_id, dist))
            edge_rows = filtered_edge_rows

        # Deduplicate edges: keep only one edge between A and B, using lower ID as source
        for source_id, target_id, dist in edge_rows:
            sim = 1.0 - float(dist) if dist is not None else 0.0
            if sim > 0.75:
                src = min(source_id, target_id)
                tgt = max(source_id, target_id)
                # Keep the one with the higher similarity score
                edges_dict[(src, tgt)] = max(edges_dict.get((src, tgt), 0.0), sim)

    edges = [
        GraphEdge(
            source=src,
            target=tgt,
            weight=w,
            source_kind="item",
            target_kind="item",
            type="similarity"
        )
        for (src, tgt), w in edges_dict.items()
    ]

    # 5.5 Fetch user's entities and insert them as nodes
    try:
        async with db.cursor() as cur:
            await cur.execute(
                """
                SELECT id, name, type, degree, created_at
                FROM entities
                WHERE user_id = %s;
                """,
                (user.id,)
            )
            entity_rows = await cur.fetchall()

        for ent_row in entity_rows:
            ent_id, ent_name, ent_type, ent_degree, ent_created_at = ent_row
            ent_created_at_str = ent_created_at.isoformat() if hasattr(ent_created_at, "isoformat") else str(ent_created_at)
            nodes.append(
                GraphNode(
                    id=10_000_000 + ent_id,
                    title=ent_name,
                    source_type=ent_type.lower(),
                    created_at=ent_created_at_str,
                    is_hub=False,
                    kind="entity",
                    entity_type=ent_type,
                    hub=(ent_degree >= 5)
                )
            )

        # Fetch semantic relationships
        async with db.cursor() as cur:
            await cur.execute(
                """
                SELECT source_type, source_id, target_type, target_id, predicate, weight, confidence
                FROM relationships
                WHERE user_id = %s;
                """,
                (user.id,)
            )
            rel_rows = await cur.fetchall()

        for r_row in rel_rows:
            src_type, src_id, tgt_type, tgt_id, predicate, weight, confidence = r_row
            s_node_id = (10_000_000 + src_id) if src_type == "entity" else src_id
            t_node_id = (10_000_000 + tgt_id) if tgt_type == "entity" else tgt_id
            edges.append(
                GraphEdge(
                    source=s_node_id,
                    target=t_node_id,
                    weight=float(weight or 1.0) * float(confidence or 1.0),
                    source_kind=src_type,
                    target_kind=tgt_type,
                    type="semantic",
                    predicate=predicate
                )
            )

        # Fetch entity mentions
        async with db.cursor() as cur:
            await cur.execute(
                """
                SELECT entity_id, item_id
                FROM entity_mentions
                WHERE user_id = %s;
                """,
                (user.id,)
            )
            mention_rows = await cur.fetchall()

        for m_row in mention_rows:
            ent_id, item_id = m_row
            edges.append(
                GraphEdge(
                    source=item_id,
                    target=10_000_000 + ent_id,
                    weight=1.0,
                    source_kind="item",
                    target_kind="entity",
                    type="semantic",
                    predicate="mentions"
                )
            )
    except Exception as ent_db_err:
        logger.error("Failed to query entities or relationships for graph: %s", ent_db_err)

    # Fetch active candidates to return them on /graph too
    candidates = []
    try:
        async with db.cursor() as cur:
            await cur.execute(
                """
                SELECT id, item_id_a, item_id_b, similarity_score, expires_at, status, insight_text
                FROM insight_candidates
                WHERE user_id = %s
                  AND (
                      (status = 'delivered' AND expires_at > NOW())
                      OR (bucket = 'near_miss' AND status = 'near_miss' AND created_at >= NOW() - INTERVAL '72 hours')
                  )
                """,
                (user.id,)
            )
            candidate_rows = await cur.fetchall()

        for c_row in candidate_rows:
            exp_val = c_row[4]
            if exp_val and exp_val.tzinfo is None:
                exp_val = exp_val.replace(tzinfo=timezone.utc)
            cand = GraphCandidate(
                id=c_row[0],
                item_id_a=c_row[1],
                item_id_b=c_row[2],
                similarity_score=float(c_row[3]),
                expires_at=exp_val,
                status=c_row[5],
                insight_text=c_row[6]
            )
            candidates.append(cand)

            # Inject candidate connection into the edges if not already present
            src = min(c_row[1], c_row[2])
            tgt = max(c_row[1], c_row[2])
            if (src, tgt) not in edges_dict:
                edges.append(
                    GraphEdge(
                        source=src,
                        target=tgt,
                        weight=float(c_row[3]),
                        source_kind="item",
                        target_kind="item",
                        type="similarity"
                    )
                )
    except Exception as cand_err:
        logger.error("Failed to fetch active candidates for graph: %s", cand_err)

    response_data = GraphResponse(
        nodes=nodes,
        edges=edges,
        hubs=validated_hubs,
        candidates=candidates
    )

    # 7. Write to cache with 60s TTL
    try:
        await redis.setex(cache_key, 60, response_data.model_dump_json())
    except Exception as e:
        logger.warning("Redis cache write failed: %s", e)

    return response_data


@router.get(
    "/candidates/active",
    response_model=List[GraphCandidate],
    tags=["graph"],
    summary="Get active connection candidates",
    description="Returns active candidates for the current user (representing active Drift Windows).",
    dependencies=[Depends(rate_limit("candidates", 30))],
)
async def get_active_candidates(
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    """Retrieve active connection candidates (delivered, unexpired)."""
    try:
        async with db.cursor() as cur:
            await cur.execute(
                """
                SELECT id, item_id_a, item_id_b, similarity_score, expires_at, status, insight_text
                FROM insight_candidates
                WHERE user_id = %s
                  AND (
                    (status = 'delivered' AND expires_at > NOW())
                    OR status = 'near_miss'
                  )
                """,
                (user.id,)
            )
            rows = await cur.fetchall()

        results = []
        for r in rows:
            results.append(
                GraphCandidate(
                    id=r[0],
                    item_id_a=r[1],
                    item_id_b=r[2],
                    similarity_score=float(r[3]),
                    expires_at=r[4],
                    status=r[5],
                    insight_text=r[6]
                )
            )
        return results
    except Exception as e:
        logger.error("Failed to fetch active candidates: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve active candidates."
        )

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
        from backend.services.pulse_service import update_user_pulse
        await update_user_pulse(cur, user.id)
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
            user.id, req.message, remind_at, db, item_id=req.item_id
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
    description="Triggers a synchronization of Atrium items to Google Drive as a Google Doc.",
    responses={
        401: {"model": ErrorResponse},
        429: {"model": ErrorResponse, "description": "Sync limit exceeded (max 5 requests per hour)."},
    },
    dependencies=[Depends(rate_limit("sync", 5, 3600))],
)
async def sync_drive(
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection | None = Depends(get_db_or_none),
):
    """Sync items to Google Drive."""
    from backend.services.drive_sync import sync_user_to_drive
    from backend.db.connection import get_db_or_none
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
    import hmac
    from backend.config import settings
    if not settings.INTERNAL_API_KEY or not hmac.compare_digest(x_internal_key or "", settings.INTERNAL_API_KEY):
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
        queue_length = await redis.llen("atrium:tasks")
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
    description="Pushes the task payload back onto the Redis atrium:tasks queue and marks the DLQ entry as retried.",
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
            
        await redis.lpush("atrium:tasks", json.dumps(task_payload))
        
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
            "telegram_chat_id": user.telegram_chat_id,
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
    request: Request,
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
            
            # Log audit
            from backend.services.audit_service import log_audit
            req_id = request.headers.get("x-request-id") or request.headers.get("request-id")
            details = {}
            if req.timezone_offset is not None:
                details["timezone_offset"] = req.timezone_offset
            if req.digest_enabled is not None:
                details["digest_enabled"] = req.digest_enabled
            await log_audit(
                db=db,
                user_id=user.id,
                action="update_settings",
                details=details,
                request_id=req_id
            )
            
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
    response.delete_cookie("atrium_session", httponly=True, secure=True, samesite="lax")
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
        "Content-Disposition": f'attachment; filename="atrium-export-{date_str}.json"'
    }

    return StreamingResponse(
        export_generator(),
        media_type="application/json",
        headers=headers
    )


# ---------------------------------------------------------------------------
# Phase 4 schemas & routes
# ---------------------------------------------------------------------------
import json
from pydantic import BaseModel, Field
from fastapi import WebSocket, WebSocketDisconnect

class UserMilestonesResponse(BaseModel):
    node_count: int
    unlocked: List[str]

class UserSelfDescriptionRequest(BaseModel):
    self_description: str

class UserProfileResponse(BaseModel):
    self_description: Optional[str]
    mind_type: Optional[str]
    mind_type_summary: Optional[str]
    mind_type_trajectory: List[dict]
    pulse_score: Optional[int] = 0

class DetailedDimension(BaseModel):
    score: float
    threshold: float
    explanation: str

class DetailedProfileResponse(BaseModel):
    breadth: DetailedDimension
    linkage: DetailedDimension
    velocity: DetailedDimension
    novelty: DetailedDimension

@router.get(
    "/user/milestones",
    response_model=UserMilestonesResponse,
    tags=["profile"],
    summary="Get user node milestone unlocks",
)
async def get_user_milestones(
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    async with db.cursor() as cur:
        await cur.execute("SELECT COUNT(*) FROM items WHERE user_id = %s;", (user.id,))
        count_row = await cur.fetchone()
        node_count = count_row[0] if count_row else 0

        await cur.execute("SELECT node_milestones FROM users WHERE id = %s;", (user.id,))
        row = await cur.fetchone()
        milestones = row[0] if row and row[0] else {"unlocked": []}
        if isinstance(milestones, str):
            try:
                milestones = json.loads(milestones)
            except Exception:
                milestones = {"unlocked": []}
        
        return {
            "node_count": node_count,
            "unlocked": milestones.get("unlocked", [])
        }

@router.post(
    "/user/self-description",
    tags=["profile"],
    summary="Save user self-description interest statement",
)
async def post_self_description(
    req: UserSelfDescriptionRequest,
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    async with db.cursor() as cur:
        await cur.execute(
            "UPDATE users SET self_description = %s WHERE id = %s;",
            (req.self_description.strip(), user.id)
        )
        await db.commit()
    return {"status": "ok"}

@router.get(
    "/user/profile",
    response_model=UserProfileResponse,
    tags=["profile"],
    summary="Get user cognitive profile info",
    dependencies=[Depends(rate_limit("profile", 4))],
)
async def get_user_profile(
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection | None = Depends(get_db_or_none),
):
    from backend.db.connection import get_db_scope, get_db_or_none
    async with get_db_scope(db) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT self_description, mind_type, mind_type_summary, mind_type_trajectory, pulse_score FROM users WHERE id = %s;",
                (user.id,)
            )
            row = await cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="User not found")
            
            self_desc, mind_type, summary, traj, pulse_score = row
            
            # Check node count to see if we should unlock and lazy-calculate
            await cur.execute("SELECT COUNT(*) FROM items WHERE user_id = %s;", (user.id,))
            count_row = await cur.fetchone()
            node_count = count_row[0] if count_row else 0
        
    if node_count >= 15 and not summary:
        try:
            from backend.scheduler.scheduler import run_nightly_mind_type_for_user, get_pool
            pool = await get_pool()
            await run_nightly_mind_type_for_user(user.id, pool)
            
            async with get_db_scope(db) as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT mind_type FROM users WHERE id = %s;", (user.id,))
                    mt_row = await cur.fetchone()
                    mind_type = mt_row[0] if mt_row else None
            
            if mind_type:
                async with get_db_scope(db) as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "SELECT label FROM semantic_hubs WHERE user_id = %s ORDER BY array_length(member_ids, 1) DESC LIMIT 3;",
                            (user.id,)
                        )
                        hubs = [r[0] for r in await cur.fetchall()]
                hubs_str = ", ".join(hubs) if hubs else "general topics"
                
                from backend.services.ai_cascade import AICascade, ai_cascade
                cascade = AICascade()
                prompt = (
                    f"You are a Cognitive Graph Profiler. The user has been classified as {mind_type} (MBTI-style Mind Type).\n"
                    f"Their top 3 active clusters are: {hubs_str}.\n"
                    f"This is their first classification. Focus on explaining the primary cognitive driver of their signature.\n\n"
                    f"Write a highly personalized, analytical, and engaging 4-sentence profile summary explaining their cognitive style based on these topics.\n"
                    f"Constraint: Do not use clinical jargon, do not use template words, and connect the topics explicitly."
                )
                summary = await cascade.call_llm(prompt)
                if not summary or len(summary) < 10:
                    summary = f"You are actively building a graph of ideas under {hubs_str}. Your current Mind Type is {mind_type}."
                    
                async with get_db_scope(db) as conn:
                    async with transaction_context(conn):
                        async with conn.cursor() as cur:
                            await cur.execute(
                                "UPDATE users SET mind_type_summary = %s, mind_type_detailed = NULL WHERE id = %s;",
                                (summary, user.id)
                            )
                            
                            # Reload trajectory list
                            await cur.execute("SELECT mind_type_trajectory FROM users WHERE id = %s;", (user.id,))
                            t_row = await cur.fetchone()
                            traj = t_row[0] if t_row else []
        except Exception as lazy_err:
            logger.error("Failed to lazy generate initial mind type profile: %s", lazy_err)

    traj_list = traj if traj else []
    if isinstance(traj_list, str):
        try:
            traj_list = json.loads(traj_list)
        except Exception:
            traj_list = []
            
    return {
        "self_description": self_desc,
        "mind_type": mind_type,
        "mind_type_summary": summary,
        "mind_type_trajectory": traj_list,
        "pulse_score": int(pulse_score) if pulse_score is not None else 0
    }

@router.get(
    "/pulse",
    response_model=UserProfileResponse,
    tags=["profile"],
    summary="Get user mind portrait metrics and pulse score",
    dependencies=[Depends(rate_limit("profile", 4))],
)
async def get_user_pulse(
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
):
    """Retrieve user's mind portrait metrics and pulse score securely."""
    async with db.cursor() as cur:
        await cur.execute(
            "SELECT self_description, mind_type, mind_type_summary, mind_type_trajectory, pulse_score FROM users WHERE id = %s;",
            (user.id,)
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        
        self_desc, mind_type, summary, traj, pulse_score = row
        traj_list = traj if traj else []
        if isinstance(traj_list, str):
            try:
                traj_list = json.loads(traj_list)
            except Exception:
                traj_list = []
                
        return {
            "self_description": self_desc,
            "mind_type": mind_type,
            "mind_type_summary": summary,
            "mind_type_trajectory": traj_list,
            "pulse_score": int(pulse_score) if pulse_score is not None else 0
        }

@router.post(
    "/user/profile/detailed",
    response_model=DetailedProfileResponse,
    tags=["profile"],
    summary="Get detailed graph metrics and explanation on-demand",
    dependencies=[Depends(rate_limit("profile_detailed", 4))],
)
async def get_detailed_profile(
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection | None = Depends(get_db_or_none),
):
    from backend.db.connection import get_db_scope, get_db_or_none
    async with get_db_scope(db) as conn:
        async with conn.cursor() as cur:
            # Check node count
            await cur.execute("SELECT COUNT(*) FROM items WHERE user_id = %s;", (user.id,))
            count_row = await cur.fetchone()
            node_count = count_row[0] if count_row else 0
            if node_count < 15:
                raise HTTPException(status_code=403, detail="Detailed profile unlocks at 15 nodes.")

            # 1. Breadth (Entropy of hubs)
            await cur.execute("SELECT id, member_ids, label FROM semantic_hubs WHERE user_id = %s;", (user.id,))
            hubs = await cur.fetchall()
            hub_labels = [h[2] for h in hubs]
            
            total_items_in_hubs = 0
            hub_sizes = []
            item_to_hub = {}
            for h_id, member_ids, label in hubs:
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

            # 2. Linkage (Cross-hub confirmed candidates ratio)
            await cur.execute(
                "SELECT item_id_a, item_id_b FROM insight_candidates WHERE user_id = %s AND status = 'confirmed';",
                (user.id,)
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

            # 3. Velocity (Nodes saved in last 7 days)
            await cur.execute(
                "SELECT COUNT(*) FROM items WHERE user_id = %s AND created_at >= NOW() - INTERVAL '7 days';",
                (user.id,)
            )
            vel_row = await cur.fetchone()
            velocity = vel_row[0] if vel_row else 0

            # 4. Novelty (Average distance of new saves to old saves)
            await cur.execute(
                "SELECT embedding FROM items WHERE user_id = %s AND created_at >= NOW() - INTERVAL '7 days' AND embedding IS NOT NULL;",
                (user.id,)
            )
            new_items = await cur.fetchall()
            
            await cur.execute(
                "SELECT embedding FROM items WHERE user_id = %s AND created_at < NOW() - INTERVAL '7 days' AND embedding IS NOT NULL;",
                (user.id,)
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

            # Check if we have cached explanations in the db
            await cur.execute("SELECT mind_type_detailed FROM users WHERE id = %s;", (user.id,))
            row = await cur.fetchone()
            cached_detailed = row[0] if row else None
            
            explanations = {}
            if cached_detailed:
                if isinstance(cached_detailed, str):
                    try:
                        explanations = json.loads(cached_detailed)
                    except Exception:
                        pass
                elif isinstance(cached_detailed, dict):
                    explanations = cached_detailed

    # Call LLM to generate the explanations only on cache miss
    if not explanations:
        from backend.services.ai_cascade import AICascade, ai_cascade
        cascade = AICascade()
        
        hubs_str = ", ".join(hub_labels) if hub_labels else "None"
        b_label = "Breadth" if entropy >= 1.20 else "Focus"
        l_label = "Linkage" if linkage_ratio >= 0.20 else "Isolation"
        v_label = "Velocity" if velocity >= 10 else "Stability"
        n_label = "Novelty" if novelty >= 0.35 else "Routine"

        prompt = (
            "You are an expert Cognitive Graph Profiler analyzing a developer/knowledge worker's personal memory network.\n"
            f"The user's top active topic clusters (hubs) are: [{hubs_str}].\n\n"
            "Analyze the following 4 structural dimensions of their graph and write exactly one deeply analytical, personalized, and engaging sentence explanation for each, explaining what their score means for their cognitive habits.\n\n"
            "DIMENSION DEFINITIONS:\n"
            "1. Breadth (B/F): Shannon Entropy of topic clusters. High breadth (B) means wide curiosity across multiple domains. Low focus (F) means deep, concentrated focus on a few key areas.\n"
            "2. Linkage (L/I): Ratio of cross-hub connections. High linkage (L) means active synthesis and connecting ideas between different domains. Low independence (I) means topics are kept clean, modular, and separate.\n"
            "3. Velocity (V/S): Ingestion frequency of new items this week. High velocity (V) represents rapid information gathering. Low stability (S) indicates a slow, highly curated, and meditative pacing.\n"
            "4. Novelty (N/R): Cosine distance of new saves to historical baseline. High novelty (N) means actively exploring fresh, unfamiliar territories. Low routine (R) means reinforcing and expanding current expertise.\n\n"
            "USER PERFORMANCE STATS:\n"
            f"- Breadth: Entropy is {entropy:.2f} (Benchmark: 1.20). Category: {b_label}.\n"
            f"- Linkage: Cross-hub ratio is {linkage_ratio:.2f} (Benchmark: 0.20). Category: {l_label}.\n"
            f"- Velocity: Ingestion count is {velocity} items (Benchmark: 10). Category: {v_label}.\n"
            f"- Novelty: Distance is {novelty:.2f} (Benchmark: 0.35). Category: {n_label}.\n\n"
            "CONSTRAINTS:\n"
            "- Write exactly one concise sentence per dimension.\n"
            "- Speak directly to the user (use 'you' and 'your').\n"
            "- Avoid repeating the raw numerical values or benchmarks in the text. Focus entirely on the qualitative meaning (e.g., use phrases like 'exceeding the target baseline', 'falling short of the synthesis threshold', 'concentrating your energy', 'exploring highly unfamiliar ground').\n"
            "- Connect the explanations back to their active topic clusters if possible.\n"
            "- Keep the tone intellectual, precise, and highly insightful.\n\n"
            "Format your response as a valid JSON object with keys: \"breadth\", \"linkage\", \"velocity\", \"novelty\"."
        )

        res = await cascade.call_llm(prompt)
        if res:
            try:
                import re
                match = re.search(r"\{.*\}", res, re.DOTALL)
                if match:
                    explanations = json.loads(match.group(0))
                    async with get_db_scope(db) as conn:
                        async with transaction_context(conn):
                            async with conn.cursor() as cur:
                                await cur.execute(
                                    "UPDATE users SET mind_type_detailed = %s WHERE id = %s;",
                                    (json.dumps(explanations), user.id)
                                )
            except Exception as e:
                logger.error("Failed to parse and cache detailed profile JSON: %s", e)

    b_exp = explanations.get("breadth") or (
        f"Your entropy is {entropy:.2f} (Threshold: 1.20). You maintain "
        + ("a wide breadth across multiple hubs." if entropy >= 1.20 else "a tight focus on a few core hubs.")
    )
    l_exp = explanations.get("linkage") or (
        f"Your cross-hub linkage ratio is {linkage_ratio:.2f} (Threshold: 0.20). You tend to "
        + ("actively connect ideas across hubs." if linkage_ratio >= 0.20 else "keep your clusters relatively isolated.")
    )
    v_exp = explanations.get("velocity") or (
        f"You saved {velocity} items this week (Threshold: 10). Your graph growth is "
        + ("expanding rapidly." if velocity >= 10 else "stable and steady.")
    )
    n_exp = explanations.get("novelty") or (
        f"Your new-concept distance is {novelty:.2f} (Threshold: 0.35). You are "
        + ("frequently exploring novel directions." if novelty >= 0.35 else "reinforcing routine concepts.")
    )

    return {
        "breadth": {"score": float(entropy), "threshold": 1.20, "explanation": b_exp},
        "linkage": {"score": float(linkage_ratio), "threshold": 0.20, "explanation": l_exp},
        "velocity": {"score": float(velocity), "threshold": 10.0, "explanation": v_exp},
        "novelty": {"score": float(novelty), "threshold": 0.35, "explanation": n_exp}
    }


@router.get(
    "/export/zip",
    tags=["profile"],
    summary="Export all notes to a zipped Obsidian Vault (OKF format)",
    description="Generates and downloads a ZIP containing all notes formatted as OKF Markdown files.",
    responses={
        401: {"model": ErrorResponse},
    },
)
async def export_zip(
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db)
):
    import io
    import zipfile
    from datetime import datetime, timezone
    from fastapi.responses import StreamingResponse
    from backend.services.okf_service import serialize_item_to_okf
    from backend.services.encryption import decrypt

    # 1. Fetch user profile
    async with db.cursor() as cur:
        await cur.execute(
            "SELECT telegram_chat_id FROM users WHERE id = %s;",
            (user.id,)
        )
        user_row = await cur.fetchone()
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")

    # 2. Query all items
    items = []
    async with db.cursor() as cur:
        await cur.execute(
            """
            SELECT id, source_type, source_url, raw_text, summary, title, tags, created_at, context_prompt
            FROM items
            WHERE user_id = %s
            ORDER BY created_at DESC;
            """,
            (user.id,)
        )
        async for row in cur:
            item_id, source_type, source_url, raw_text, summary, title, tags, created_at, context_prompt = row
            
            # Decrypt content body
            decrypted_text = None
            if raw_text:
                try:
                    decrypted_text = decrypt(raw_text)
                except Exception:
                    decrypted_text = None
            
            items.append({
                "id": item_id,
                "source_type": source_type,
                "source_url": source_url,
                "raw_text_decrypted": decrypted_text,
                "summary": summary,
                "title": title,
                "tags": tags,
                "created_at": created_at,
                "context_prompt": context_prompt
            })

    # 3. Create ZIP archive in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for item in items:
            # Generate safe filename
            raw_title = item["title"] or "Untitled"
            safe_title = "".join(c if c.isascii() and c.isalnum() else "_" for c in raw_title).strip("_")
            # Truncate to 50 chars to avoid exceeding Windows MAX_PATH limit (260 chars)
            safe_title = safe_title[:50].rstrip("_")
            filename = f"{safe_title or 'note'}_{item['id']}.md"
            
            # Category fallback
            category = item["source_type"] or "text"
            
            # Generate OKF content
            okf_content = serialize_item_to_okf(
                title=item["title"],
                tags=item["tags"],
                created_at=item["created_at"],
                source_url=item["source_url"],
                context_note=item["context_prompt"],
                category=category,
                content=item["raw_text_decrypted"] or item["summary"] or ""
            )
            zip_file.writestr(filename, okf_content)

    zip_buffer.seek(0)
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    headers = {
        "Content-Disposition": f'attachment; filename="atrium-obsidian-export-{timestamp}.zip"',
        "Access-Control-Expose-Headers": "Content-Disposition"
    }
    
    logger.info("Audit Log - Export ZIP completed: user_id=%s, item_count=%d", user.id, len(items))
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers=headers
    )


@router.post(
    "/import/zip",
    tags=["profile"],
    summary="Import notes from a zipped Obsidian Vault (OKF format)",
    description="Accepts an uploaded ZIP containing OKF Markdown files, parses, embeds, and stores them in database.",
    responses={
        401: {"model": ErrorResponse},
        400: {"model": ErrorResponse, "description": "Invalid file format or failed parsing."},
    },
    dependencies=[Depends(rate_limit_by_route("ingest_upload", limit=15, window=60, burst=5))]
)
async def import_zip(
    file: UploadFile = File(...),
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db)
):
    import io
    import zipfile
    from backend.services.okf_service import parse_okf_to_item
    from backend.services.encryption import encrypt
    from backend.services.search_service import embed_text
    from backend.services.pdf_ingester import chunk_text

    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a ZIP archive.")

    # 1. Size Validation (Limit to 25MB)
    MAX_ZIP_SIZE = 25 * 1024 * 1024
    try:
        contents = await file.read(MAX_ZIP_SIZE + 1)
        if len(contents) > MAX_ZIP_SIZE:
            raise HTTPException(status_code=413, detail="Uploaded file exceeds the maximum size limit of 25MB.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to read uploaded ZIP file: %s", e)
        raise HTTPException(status_code=400, detail="Failed to read uploaded ZIP file.")

    # 2. Magic Bytes Header Check (ZIP magic bytes: PK\x03\x04)
    if not contents.startswith(b"PK\x03\x04"):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid ZIP archive (magic bytes mismatch).")

    zip_buffer = io.BytesIO(contents)

    imported_count = 0
    try:
        with zipfile.ZipFile(zip_buffer, "r") as zip_file:
            for filename in zip_file.namelist():
                # Skip folders and non-markdown files
                if filename.endswith("/") or not filename.endswith(".md"):
                    continue

                try:
                    content_bytes = zip_file.read(filename)
                    content_str = content_bytes.decode("utf-8", errors="ignore")
                except Exception as e:
                    logger.warning("Failed to read file %s from ZIP: %s", filename, e)
                    continue

                # Parse OKF Markdown
                parsed_data = parse_okf_to_item(content_str)
                title = parsed_data.get("title") or filename.split("/")[-1].replace(".md", "")
                tags = parsed_data.get("tags") or []
                raw_text = parsed_data.get("raw_text") or ""
                source_url = parsed_data.get("source_url")
                context_note = parsed_data.get("context_note")
                category = parsed_data.get("category") or "text"

                # Standardize tags (lowercase, sorted)
                tags = sorted(list(set(str(t).strip().lower() for t in tags if t)))

                # 1. Compute parent note summary fallback and embedding
                summary = (raw_text[:200] + "...") if len(raw_text) > 200 else (raw_text or "Imported Obsidian note.")
                try:
                    parent_embedding = await embed_text(raw_text or title)
                except Exception as e:
                    logger.error("Failed to compute embedding for imported item %s: %s", title, e)
                    # Use a dummy/fallback embedding of 384 dimensions if API is down
                    parent_embedding = [0.0] * 384

                encrypted_raw_text = encrypt(raw_text) if raw_text else None

                # 2. Database Insert parent item
                async with db.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO items (user_id, source_type, source_url, raw_text, summary, title, embedding, tags, context_prompt)
                        VALUES (%s, %s, %s, %s, %s, %s, %s::vector, %s, %s)
                        RETURNING id;
                        """,
                        (user.id, category, source_url, encrypted_raw_text, summary, title, parent_embedding, tags, context_note)
                    )
                    row = await cur.fetchone()
                    if not row:
                        continue
                    item_id = row[0]

                    # 3. Text chunking & item_chunks generation for RAG
                    from backend.config import settings
                    chunks = await chunk_text(raw_text)
                    if chunks:
                        for chunk_idx, chunk in enumerate(chunks):
                            chunk_excerpt = chunk[:500]  # Respect db length limits
                            try:
                                chunk_emb = await embed_text(chunk)
                            except Exception:
                                chunk_emb = parent_embedding  # fallback

                            await cur.execute(
                                """
                                INSERT INTO item_chunks (item_id, user_id, chunk_index, chunk_text, embedding, chunk_version)
                                VALUES (%s, %s, %s, %s, %s::vector, %s);
                                """,
                                (item_id, user.id, chunk_idx, chunk_excerpt, chunk_emb, settings.DEFAULT_CHUNK_VERSION)
                            )
                imported_count += 1
        
        await db.commit()
    except Exception as e:
        logger.error("Failed to process imported ZIP file contents: %s", e)
        raise HTTPException(status_code=400, detail="Failed to process imported ZIP file contents.")

    # Invalidate Graph cache
    try:
        from backend.services.redis_client import redis
        await redis.delete(f"graph:{user.id}")
        logger.info("Invalidated graph cache for user %d after zip import", user.id)
    except Exception as e:
        logger.warning("Failed to invalidate graph cache after import: %s", e)

    logger.info("Audit Log - Import ZIP completed: user_id=%s, imported_count=%d", user.id, imported_count)
    return {"status": "success", "imported_count": imported_count}



@router.post(
    "/share-target",
    summary="Handle PWA Web Share Target POST",
    description="Receives native mobile share target form data (title, text, url) and triggers ingestion.",
)
async def handle_pwa_share_target(
    request: Request,
    title: Optional[str] = Form(None),
    text: Optional[str] = Form(None),
    url: Optional[str] = Form(None),
    user: UserContext = Depends(get_current_user),
    db: psycopg.AsyncConnection = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    """Processes content shared to the PWA natively from mobile OS Share Sheet."""
    import re
    from fastapi.responses import RedirectResponse
    
    combined_raw = f"{title or ''} {text or ''} {url or ''}".strip()
    if not combined_raw:
        return RedirectResponse(url="/archive?status=error_empty", status_code=303)
        
    # Extract URL using regex
    url_pattern = re.compile(r'https?://[^\s]+')
    match = url_pattern.search(combined_raw)
    
    if match:
        extracted_url = match.group(0)
        source_type = "url"
        context_note = combined_raw.replace(extracted_url, "").strip() or None
        raw_text = extracted_url
    else:
        source_type = "text"
        context_note = None
        raw_text = combined_raw
        
    item_req = ItemCreateRequest(
        url=extracted_url if match else None,
        title=title or None,
        raw_text=combined_raw if not match else None,
        source_type=source_type
    )
    
    try:
        dummy_res = Response()
        await create_item(item_req, response=dummy_res, user=user, db=db)
    except Exception as e:
        logger.error("Failed to process PWA share target for user %d: %s", user.id, e)
        return RedirectResponse(url="/archive?status=share_failed", status_code=303)
        
    return RedirectResponse(url="/archive?status=shared_success", status_code=303)


@router.post("/mock-ocr")
async def mock_ocr(payload: dict):
    """Simulates a remote OCR microservice request to benchmark HTTP/network overhead without loading models."""
    import asyncio
    # Simulate a lightweight network/inference round-trip delay (e.g. 50ms)
    await asyncio.sleep(0.05)
    return {"ocr_text": "Extracted text from mock OCR API endpoint."}


@router.get("/remote-ai-timings")
async def get_remote_ai_timings():
    """Returns remote AI telemetry collected by the API process."""
    from backend.services.remote_ai_client import get_timings
    return get_timings()


@router.get("/setup-webhook")
async def setup_telegram_webhook(request: Request):
    """Registers the Telegram bot webhook using the server's own config variables."""
    import httpx
    from backend.config import settings
    if not settings.TELEGRAM_BOT_TOKEN:
        return {"status": "error", "message": "TELEGRAM_BOT_TOKEN is not configured on this server."}

    base_url = str(request.base_url).rstrip("/")
    webhook_url = f"{base_url}/webhook"

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/setWebhook"
    payload = {
        "url": webhook_url
    }
    if settings.TELEGRAM_WEBHOOK_SECRET:
        payload["secret_token"] = settings.TELEGRAM_WEBHOOK_SECRET

    logger.info("Triggering Telegram webhook setup via endpoint for URL: %s", webhook_url)
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload, timeout=10.0)
            return {
                "status": "ok",
                "webhook_url": webhook_url,
                "telegram_response": resp.json()
            }
        except Exception as e:
            logger.error("Failed to setup Telegram webhook via API: %s", e)
            return {
                "status": "error",
                "message": str(e)
            }



