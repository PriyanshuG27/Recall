"""
backend/models/schemas.py
==========================
Pydantic schemas for the Recall API.
Ensures proper response structures and that raw_text never leaks.
"""

from __future__ import annotations
from pydantic import BaseModel, Field, AfterValidator
from typing import List, Optional, Annotated
from datetime import datetime, timezone, date as datetime_date

def make_utc_aware(dt: datetime) -> datetime:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

AwareDateTime = Annotated[datetime, AfterValidator(make_utc_aware)]

# ---------------------------------------------------------------------------
# Items schemas
# ---------------------------------------------------------------------------
class ItemResponse(BaseModel):
    id: int = Field(..., description="Internal surrogate ID of the item.")
    user_id: int = Field(..., description="Owner's internal user ID.")
    source_type: str = Field(..., description="Type of ingest source (e.g. url, voice, pdf, image, text).")
    source_url: Optional[str] = Field(None, description="Original source URL.")
    summary: str = Field(..., description="LLM-generated plain-text summary.")
    title: Optional[str] = Field(None, description="Extracted or generated title.")
    tags: List[str] = Field(default_factory=list, description="List of auto-generated tags.")
    created_at: AwareDateTime = Field(..., description="Item creation timestamp.")

class ItemCreateRequest(BaseModel):
    url: Optional[str] = Field(None, description="The URL of the item to add.")
    title: Optional[str] = Field(None, description="The optional title of the item.")
    raw_text: Optional[str] = Field(None, description="Raw note text content.")
    source_type: Optional[str] = Field(None, description="Type of ingest source.")
    tags: Optional[List[str]] = Field(None, description="Custom tags list.")


class PaginatedItem(BaseModel):
    id: int = Field(..., description="Internal surrogate ID of the item.")
    title: Optional[str] = Field(None, description="Extracted or generated title.")
    summary: str = Field(..., description="LLM-generated plain-text summary.")
    source_type: str = Field(..., description="Type of ingest source.")
    source_url: Optional[str] = Field(None, description="Original source URL.")
    tags: List[str] = Field(default_factory=list, description="List of auto-generated tags.")
    created_at: AwareDateTime = Field(..., description="Item creation timestamp.")
    context_note: Optional[str] = Field(None, description="User-provided context note.")
    ease_factor: Optional[float] = Field(None, description="SM-2 ease factor.")
    interval_days: Optional[int] = Field(None, description="SM-2 interval days.")
    next_review: Optional[datetime_date] = Field(None, description="Scheduled review date.")


class PaginatedItemsResponse(BaseModel):
    items: List[PaginatedItem] = Field(..., description="List of items for the current page.")
    total: int = Field(..., description="Total number of items matching filters.")
    page: int = Field(..., description="Current page number.")
    pages: int = Field(..., description="Total number of pages available.")

class TagCountResponse(BaseModel):
    tag: str = Field(..., description="The tag string.")
    count: int = Field(..., description="The frequency count of this tag.")

# ---------------------------------------------------------------------------
# Search schemas
# ---------------------------------------------------------------------------
class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query string.")
    limit: int = Field(5, ge=1, description="Maximum number of results to return (default 5).")
    rag: bool = Field(True, description="Whether to run RAG generation (default True).")

class SearchResponseItem(BaseModel):
    id: int = Field(..., description="Internal surrogate ID of the item.")
    title: Optional[str] = Field(None, description="Extracted or generated title.")
    summary: str = Field(..., description="LLM-generated plain-text summary.")
    source_type: str = Field(..., description="Type of ingest source.")
    source_url: Optional[str] = Field(None, description="Original source URL.")
    created_at: AwareDateTime = Field(..., description="Creation timestamp in ISO format.")

class SearchResultItem(BaseModel):
    item: ItemResponse = Field(..., description="Matched item metadata.")
    score: float = Field(..., description="Relevance score (cosine similarity or text match rank).")

class SearchResponse(BaseModel):
    results: List[SearchResultItem] = Field(..., description="List of matched items sorted by relevance.")

class SearchSourceItem(BaseModel):
    id: int = Field(..., description="Internal surrogate ID of the item.")
    title: Optional[str] = Field(None, description="Extracted or generated title.")
    summary: str = Field(..., description="LLM-generated plain-text summary.")
    relevance: float = Field(..., description="Relevance score (RRF or similarity).")
    source_type: str = Field("text", description="Source type of the item.")
    source_url: Optional[str] = Field(None, description="Source URL of the item.")
    tags: List[str] = Field(default_factory=list, description="Tags associated with the item.")
    created_at: AwareDateTime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp.")

class RAGSearchResponse(BaseModel):
    answer: Optional[str] = Field(None, description="Synthesised answer generated from context, or null if skipped/failed.")
    sources: List[SearchSourceItem] = Field(..., description="List of matched source items used for context.")
    query: str = Field(..., description="The original search query.")

# ---------------------------------------------------------------------------
# Mind Map Graph schemas
# ---------------------------------------------------------------------------
class GraphNode(BaseModel):
    id: int = Field(..., description="Internal surrogate ID of the item.")
    title: str = Field(..., description="Extracted or generated title of the item.")
    source_type: str = Field(..., description="Type of ingest source.")
    created_at: AwareDateTime = Field(..., description="Creation timestamp in ISO format.")
    is_hub: bool = Field(..., description="True if the item is a member of any semantic hub.")

class GraphEdge(BaseModel):
    source: int = Field(..., description="Source node item ID.")
    target: int = Field(..., description="Target node item ID.")
    weight: float = Field(..., description="Edge weight representing cosine similarity.")

class GraphHub(BaseModel):
    id: int = Field(..., description="Hub ID.")
    label: str = Field(..., description="LLM-generated community label.")
    member_ids: List[int] = Field(..., description="List of validated member item IDs in the hub.")
    last_active_at: Optional[AwareDateTime] = Field(None, description="Most recent member item timestamp.")
    streak_days: int = Field(0, description="Consecutive active days of saves in this hub.")

class GraphCandidate(BaseModel):
    id: int = Field(..., description="Candidate internal ID.")
    item_id_a: int = Field(..., description="Source item node ID.")
    item_id_b: int = Field(..., description="Target item node ID.")
    similarity_score: float = Field(..., description="Candidate connection similarity.")
    insight_text: Optional[str] = Field(None, description="Tension connection insight text.")
    expires_at: Optional[AwareDateTime] = Field(None, description="Drift countdown expiration time.")
    status: str = Field(..., description="Connection status enum.")

class GraphResponse(BaseModel):
    nodes: List[GraphNode] = Field(..., description="List of item nodes.")
    edges: List[GraphEdge] = Field(..., description="List of similarity edges.")
    hubs: List[GraphHub] = Field(..., description="List of semantic hubs.")
    candidates: List[GraphCandidate] = Field(default=[], description="List of active connection candidates.")

# ---------------------------------------------------------------------------
# Quizzes schemas
# ---------------------------------------------------------------------------
class QuizResponse(BaseModel):
    id: int = Field(..., description="Quiz ID.")
    user_id: int = Field(..., description="Owner's internal user ID.")
    item_id: int = Field(..., description="Reference to the tested item.")
    question: str = Field(..., description="LLM-generated question.")
    options: List[str] = Field(..., description="List of answer choices.")
    correct_index: int = Field(..., description="0-based index of correct option.")
    explanation: Optional[str] = Field(None, description="LLM-generated explanation.")
    ease_factor: float = Field(..., description="SM-2 ease factor.")
    interval_days: int = Field(..., description="SM-2 interval in days.")
    next_review: datetime_date = Field(..., description="Scheduled review date.")
    created_at: AwareDateTime = Field(..., description="Quiz creation timestamp.")

class QuizAnswerRequest(BaseModel):
    quality: int = Field(..., ge=0, le=5, description="SM-2 response quality score (0 to 5).")

class QuizHistoryDay(BaseModel):
    day: str = Field(..., description="Day name abbreviation (e.g. Mon, Tue).")
    date: datetime_date = Field(..., description="Date of the tracking day.")
    count: int = Field(..., description="Number of quizzes answered.")

class QuizStatsResponse(BaseModel):
    total: int = Field(..., description="Total quizzes created.")
    due_today: int = Field(..., description="Quizzes due for review today.")
    answered_all_time: int = Field(..., description="Total reviews answered all time.")
    avg_ease_factor: float = Field(..., description="Average SM-2 ease factor.")
    mastered: int = Field(..., description="Number of mastered quizzes.")
    mastered_definition: str = Field(..., description="Definition of mastered.")
    last_7_days: List[QuizHistoryDay] = Field(..., description="Quiz activity over the last 7 days.")

# ---------------------------------------------------------------------------
# Reminders schemas
# ---------------------------------------------------------------------------
class ReminderResponse(BaseModel):
    id: int = Field(..., description="Reminder ID.")
    user_id: int = Field(..., description="Owner's internal user ID.")
    item_id: Optional[int] = Field(None, description="Optional linked item ID.")
    message: str = Field(..., description="Reminder text message.")
    remind_at: AwareDateTime = Field(..., description="Scheduled delivery timestamp (UTC).")
    status: str = Field(..., description="Delivery status ('pending', 'sent', 'failed').")
    created_at: AwareDateTime = Field(..., description="Reminder creation timestamp.")

class ReminderCreateRequest(BaseModel):
    item_id: Optional[int] = Field(None, description="Optional linked item ID.")
    message: str = Field(..., description="Reminder message body.")
    remind_at: AwareDateTime = Field(..., description="Scheduled delivery timestamp (UTC).")

# ---------------------------------------------------------------------------
# Error response schemas
# ---------------------------------------------------------------------------
class ErrorResponse(BaseModel):
    error: str = Field(..., description="Programmatic error code.")
    message: str = Field(..., description="Human-readable error description.")

# ---------------------------------------------------------------------------
# User profile & settings schemas
# ---------------------------------------------------------------------------
class UserMeResponse(BaseModel):
    timezone_offset: float = Field(..., description="Timezone offset in hours.")
    streak_count: int = Field(..., description="Current daily review streak.")
    drive_connected: bool = Field(..., description="Whether Google Drive is connected.")
    total_saves: int = Field(..., description="Total count of saved items.")
    quizzes_answered: int = Field(..., description="Total quizzes answered.")
    google_last_sync: Optional[str] = Field(None, description="ISO-8601 formatted timestamp of the last successful Google Drive sync.")
    last_7_days_activity: List[bool] = Field(..., description="Active status for each of the last 7 days (UTC based).")
    last_activity_date: Optional[AwareDateTime] = Field(None, description="ISO-8601 formatted timestamp of the user's last saved item.")
    digest_enabled: bool = Field(True, description="Whether the user wants daily digests.")
    telegram_chat_id: Optional[str] = Field(None, description="Telegram Chat ID or username of the user.")

class UserMeUpdateRequest(BaseModel):
    timezone_offset: Optional[float] = Field(None, ge=-12.0, le=14.0, description="Timezone offset in hours.")
    digest_enabled: Optional[bool] = Field(None, description="Whether to enable or disable daily morning digests.")
