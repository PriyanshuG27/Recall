import json
import logging
from typing import Any, Dict, Optional
from backend.services.ai_cascade.models import AITask, ExecutionContext, PipelineContext, SummaryResult
from backend.services.ai_cascade.planner.ai_planner import AIPlanner
from backend.services.ai_cascade.pipelines.summary import SummaryPipeline
from backend.services.ai_cascade.security import security_layer
from backend.services.ai_cascade.cache import cache_manager
from backend.services.ai_cascade.executor.engine import ExecutionEngine
from backend.services.ai_cascade.executor import response_composer
from backend.services.ai_cascade.persistence import persistence_manager

logger = logging.getLogger(__name__)


class LegacyAdapter:
    def __init__(self):
        self.planner = AIPlanner()
        self.engine = ExecutionEngine()

    async def execute_summary_pipeline(
        self,
        text: str,
        mood_category: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Executes the summary pipeline following the V9 Spec flowchart:
        AITask -> Planner -> Plan -> Pipeline -> Security -> Cache -> Capability -> Provider -> Executor -> Persistence -> Composer
        """
        # Input Validation: Skip execution entirely for empty or extremely short inputs to prevent unnecessary database/Redis calls
        if not text or not text.strip() or len(text.strip()) < 5:
            logger.info("LegacyAdapter: Input text is too short or empty. Skipping execution.")
            dummy_result = SummaryResult(
                provider_used="none",
                model_used="none",
                summary="",
                tags=[],
                key_points=[],
                context_prompt="",
                metadata={}
            )
            return response_composer.compose_response(dummy_result)

        # 1. Instantiate AITask
        task = AITask(input_data={"transcript": text})

        # 2. Planner -> Plan
        plan = self.planner.plan_execution(task, "summary")

        # 3. Pipeline
        pipeline = SummaryPipeline()

        # 4. Prompt Context Builder -> Render prompts
        metadata = {}
        if mood_category:
            metadata["mood_category"] = mood_category
        pipeline_context = PipelineContext(transcript=text, metadata=metadata)
        system_prompt = pipeline.build_system_prompt(pipeline_context)
        user_prompt = pipeline.build_user_prompt(pipeline_context)

        # 5. Security Layer
        security_layer.validate_prompt(system_prompt)
        security_layer.validate_prompt(user_prompt)

        # 6. Cache Manager (Bypass check)
        cached_result = None
        from backend.services.ai_cascade.config import settings
        if settings.enable_cache:
            cached_result = await cache_manager.get_llm_response(
                normalized_input=text,
                prompt_version=plan.prompt_version,
                pipeline_name="summary"
            )
        if cached_result:
            logger.info("LegacyAdapter: Cache Hit, bypassing execution and persistence.")
            from backend.services.ai_cascade.events.event_bus import event_bus, CacheHit
            await event_bus.publish(CacheHit(
                pipeline="summary",
                key=f"summary:{hash(text)}",
                user_id=user_id
            ))
            return cached_result

        # 7. AI Executor & Fallbacks
        execution_context = ExecutionContext()
        result = await self.engine.execute_plan(plan, execution_context, system_prompt, user_prompt)

        # 8. Reconstruct structured SummaryResult (or use directly if already populated)
        if isinstance(result, SummaryResult):
            summary_result = result
        else:
            summary_result = SummaryResult(
                provider_used=result.provider_used,
                model_used=result.model_used,
                summary=getattr(result, "summary", ""),
                key_points=getattr(result, "key_points", []),
                tags=getattr(result, "tags", []),
                context_prompt=getattr(result, "context_prompt", ""),
                metadata=result.metadata
            )

        # 9. Persistence Manager
        persistence_manager.save_result(
            summary_result,
            cache_hit=False,
            user_id=user_id,
            execution_context=execution_context
        )

        # 10. Response Composer
        response = response_composer.compose_response(summary_result)

        # 11. Write back to LLM Cache
        if settings.enable_cache:
            await cache_manager.set_llm_response(
                normalized_input=text,
                prompt_version=plan.prompt_version,
                pipeline_name="summary",
                response_data=response
            )

        return response


legacy_adapter = LegacyAdapter()
