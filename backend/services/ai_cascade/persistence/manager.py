import logging
import asyncio
import json
from typing import Any, Optional
from backend.services.ai_cascade.models import BaseAIResult

logger = logging.getLogger(__name__)


class PersistenceManager:
    def __init__(self):
        # Local record log for Phase 1 verification
        self.persisted_records = []

    def save_result(
        self,
        result: BaseAIResult,
        cache_hit: bool = False,
        user_id: Optional[int] = None,
        execution_context: Optional[Any] = None
    ) -> None:
        """
        Saves the structured result.
        Enforces boundaries: DO Persist (Summary, tags, metadata)
        DO NOT Persist (Raw prompts, API keys, full provider response payloads).
        Never persists on Cache Hit.
        """
        if cache_hit:
            logger.info("Cache Hit: skipping persistence according to spec guidelines.")
            return

        # Filter metadata (dropping raw responses or security-sensitive details)
        filtered_metadata = {
            k: v for k, v in result.metadata.items()
            if k not in ("raw_response", "api_key", "prompt", "raw_prompt", "credentials")
        }

        # Build clean persistence document
        doc = {
            "provider_used": result.provider_used,
            "model_used": result.model_used,
            "metadata": filtered_metadata,
        }

        # Append fields if they exist on the specialized subclasses
        for field in ("summary", "tags", "key_points", "insights", "questions", "text", "transcript", "answer"):
            if hasattr(result, field):
                doc[field] = getattr(result, field)

        self.persisted_records.append(doc)
        logger.info("Persisted AI Result successfully: %s", str(doc))

        # Async PostgreSQL Write and Event Publishing
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._async_db_write(result, user_id, execution_context))
            loop.create_task(self._publish_domain_events(result, user_id, execution_context))
        except RuntimeError:
            pass

    async def _async_db_write(
        self,
        result: BaseAIResult,
        user_id: Optional[int] = None,
        execution_context: Optional[Any] = None
    ) -> None:
        """Asynchronously writes the complete decision log details to PostgreSQL."""
        from backend.db.connection import _pool
        if _pool is None:
            logger.warning("PersistenceManager: Database pool is not initialized. Skipping decision log database write.")
            return

        try:
            # Build sanitized output payload
            sanitized_output = {}
            for field in ("summary", "tags", "key_points", "insights", "questions", "text", "transcript", "answer"):
                if hasattr(result, field):
                    sanitized_output[field] = getattr(result, field)

            # Extract execution context details
            request_id = "unknown"
            execution_id = "unknown"
            task_type = "unknown"
            pipeline_name = "unknown"
            attempts_list = []

            if execution_context is not None:
                request_id = getattr(execution_context, "request_id", "unknown")
                execution_id = getattr(execution_context, "execution_id", "unknown")
                
                # Fetch task and pipeline name if available
                # Fallback to result class attributes or metadata
                pipeline_name = getattr(execution_context, "pipeline_name", "unknown")
                if pipeline_name == "unknown" and hasattr(result, "pipeline"):
                    pipeline_name = getattr(result, "pipeline")
                if pipeline_name == "unknown":
                    pipeline_name = result.__class__.__name__.replace("Result", "").lower()
                task_type = pipeline_name

                # Gather candidate attempts history
                attempts = getattr(execution_context, "attempts", [])
                for att in attempts:
                    attempts_list.append({
                        "provider": att.get("provider", ""),
                        "model": att.get("model", ""),
                        "latency_ms": att.get("latency_ms", 0.0),
                        "status": att.get("status", ""),
                        "error": att.get("error", "")
                    })
            else:
                # Synchronous adapter fallback
                pipeline_name = result.__class__.__name__.replace("Result", "").lower()
                task_type = pipeline_name

            success = result.provider_used is not None and result.provider_used != "none"
            error_message = None
            if not success:
                error_message = attempts_list[-1].get("error") if attempts_list else "All candidates in plan failed."

            async with _pool.connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO ai_decision_logs (
                        user_id, request_id, execution_id, task, pipeline,
                        provider_used, model_used, success, attempts, final_output,
                        error_message, cache_hit, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    """,
                    (
                        user_id,
                        request_id,
                        execution_id,
                        task_type,
                        pipeline_name,
                        result.provider_used,
                        result.model_used,
                        success,
                        json.dumps(attempts_list),
                        json.dumps(sanitized_output),
                        error_message,
                        False
                    )
                )
                await conn.commit()
            logger.info("Persisted AI Decision Log for request_id=%s, execution_id=%s", request_id, execution_id)
        except Exception as err:
            logger.warning("PersistenceManager: Database write to ai_decision_logs failed: %s", err)

    async def _publish_domain_events(
        self,
        result: BaseAIResult,
        user_id: Optional[int] = None,
        execution_context: Optional[Any] = None
    ) -> None:
        """Publishes typed domain events to the Event Bus asynchronously."""
        try:
            from backend.services.ai_cascade.events.event_bus import (
                event_bus, SummaryGenerated, RAGAnswered, InsightGenerated,
                QuizGenerated, OCRCompleted, TranscriptionCompleted
            )
            
            uid = user_id or 0
            req_id = getattr(execution_context, "request_id", None) if execution_context else None
            
            class_name = result.__class__.__name__
            if class_name == "SummaryResult":
                summary = getattr(result, "summary", "")
                tags = getattr(result, "tags", [])
                await event_bus.publish(SummaryGenerated(
                    request_id=req_id,
                    user_id=uid,
                    summary=summary,
                    tags=tags
                ))
            elif class_name == "RAGResult":
                answer = getattr(result, "answer", "")
                question = result.metadata.get("question", "What was the query?")
                await event_bus.publish(RAGAnswered(
                    request_id=req_id,
                    user_id=uid,
                    question=question,
                    answer=answer
                ))
            elif class_name == "InsightResult":
                insight_text = getattr(result, "insight_text", "") or getattr(result, "summary", "")
                await event_bus.publish(InsightGenerated(
                    request_id=req_id,
                    user_id=uid,
                    insight_text=insight_text
                ))
            elif class_name == "QuizResult":
                quiz_data = result.metadata.get("quiz_data", {}) or getattr(result, "quiz_data", {}) or {}
                await event_bus.publish(QuizGenerated(
                    request_id=req_id,
                    user_id=uid,
                    quiz_data=quiz_data
                ))
            elif class_name == "OCRResult":
                text = getattr(result, "text", "") or getattr(result, "summary", "")
                await event_bus.publish(OCRCompleted(
                    request_id=req_id,
                    user_id=uid,
                    text_length=len(text)
                ))
            elif class_name == "TranscriptionResult":
                duration = result.metadata.get("duration_seconds", 0.0) or 0.0
                await event_bus.publish(TranscriptionCompleted(
                    request_id=req_id,
                    user_id=uid,
                    duration_seconds=duration
                ))
        except Exception as e:
            logger.warning("PersistenceManager: Failed to publish domain events: %s", e)


persistence_manager = PersistenceManager()

