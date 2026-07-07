import logging
import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol, List, Dict, Type, Optional, Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class EventPriority(Enum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class BaseEvent(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    request_id: Optional[str] = None
    user_id: Optional[int] = None
    priority: EventPriority = EventPriority.NORMAL


class EventHandler(Protocol):
    async def handle(self, event: BaseEvent) -> None:
        ...


# ------------------------------------------------------------------------------
# System Events
# ------------------------------------------------------------------------------
class LLMRequestStarted(BaseEvent):
    provider: Optional[str] = None
    model: Optional[str] = None
    priority: EventPriority = EventPriority.LOW


class LLMRequestFinished(BaseEvent):
    provider: str
    model: str
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    success: bool
    error: str = ""
    pipeline: str = ""
    prompt_version: str = ""
    priority: EventPriority = EventPriority.LOW


class CacheHit(BaseEvent):
    pipeline: str
    key: str
    priority: EventPriority = EventPriority.LOW


class CircuitBreakerOpened(BaseEvent):
    provider: str
    consecutive_failures: int
    priority: EventPriority = EventPriority.HIGH


class ProviderFailed(BaseEvent):
    provider: str
    error: str
    priority: EventPriority = EventPriority.NORMAL


class ProviderSelected(BaseEvent):
    provider: str
    model: str
    priority: EventPriority = EventPriority.LOW


class RetryAttempted(BaseEvent):
    provider: str
    model: str
    attempt_num: int
    backoff_seconds: float
    priority: EventPriority = EventPriority.NORMAL


class ExecutionSucceeded(BaseEvent):
    provider: str
    model: str
    priority: EventPriority = EventPriority.NORMAL


class ExecutionFailed(BaseEvent):
    error: str
    priority: EventPriority = EventPriority.HIGH


class ModelDeprecatedWarning(BaseEvent):
    provider: str
    model: str
    replacement: str
    priority: EventPriority = EventPriority.NORMAL


# ------------------------------------------------------------------------------
# Domain Events
# ------------------------------------------------------------------------------
class SummaryGenerated(BaseEvent):
    user_id: int
    item_id: Optional[int] = None
    summary: str
    tags: List[str]
    priority: EventPriority = EventPriority.HIGH


class RAGAnswered(BaseEvent):
    user_id: int
    question: str
    answer: str
    priority: EventPriority = EventPriority.HIGH


class InsightGenerated(BaseEvent):
    user_id: int
    insight_text: str
    priority: EventPriority = EventPriority.HIGH


class QuizGenerated(BaseEvent):
    user_id: int
    quiz_data: Dict[str, Any]
    priority: EventPriority = EventPriority.HIGH


class OCRCompleted(BaseEvent):
    user_id: int
    text_length: int
    priority: EventPriority = EventPriority.HIGH


class TranscriptionCompleted(BaseEvent):
    user_id: int
    duration_seconds: float
    priority: EventPriority = EventPriority.HIGH


# ------------------------------------------------------------------------------
# Event Bus Manager
# ------------------------------------------------------------------------------
class EventBus:
    def __init__(self):
        self._subscribers: Dict[Type[BaseEvent], List[EventHandler]] = {}
        self._is_initialized = False

    def initialize(self) -> None:
        """Initialize the event bus and verify readiness."""
        self._is_initialized = True
        logger.info("EventBus initialized and ready to publish events.")
        from backend.services.ai_cascade.analytics.prompt_analytics import prompt_analytics
        prompt_analytics.initialize()

    def shutdown(self) -> None:
        """Shutdown the event bus and clear subscriptions."""
        from backend.services.ai_cascade.analytics.prompt_analytics import prompt_analytics
        prompt_analytics.shutdown()
        self.clear_subscribers()
        self._is_initialized = False
        logger.info("EventBus shut down cleanly.")

    def clear_subscribers(self) -> None:
        """Clear all active subscriptions."""
        self._subscribers.clear()

    def subscribe(self, event_type: Type[BaseEvent], handler: EventHandler) -> None:
        """Subscribe a protocol-compliant handler to an event type."""
        handlers = self._subscribers.setdefault(event_type, [])
        if handler not in handlers:
            handlers.append(handler)

    def unsubscribe(self, event_type: Type[BaseEvent], handler: EventHandler) -> None:
        """Unsubscribe a handler from an event type."""
        if event_type in self._subscribers:
            handlers = self._subscribers[event_type]
            if handler in handlers:
                handlers.remove(handler)

    async def publish(self, event: BaseEvent) -> None:
        """Publish an event asynchronously to all subscribed handlers with safety isolation."""
        if not self._is_initialized:
            logger.debug("EventBus: publish called before initialize.")
            return

        event_type = type(event)
        handlers = self._subscribers.get(event_type, [])
        if not handlers:
            return

        async def safe_handle(h: EventHandler, evt: BaseEvent) -> None:
            try:
                await h.handle(evt)
            except Exception as err:
                logger.exception("EventBus: Handler %s crashed while handling event %s: %s", h, type(evt).__name__, err)

        tasks = [safe_handle(handler, event) for handler in handlers]
        await asyncio.gather(*tasks)


event_bus = EventBus()
