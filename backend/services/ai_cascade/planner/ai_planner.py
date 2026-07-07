from backend.services.ai_cascade.models import AITask, ExecutionPlan
from backend.services.ai_cascade.config import settings


class AIPlanner:
    def plan_execution(self, task: AITask, pipeline_name: str) -> ExecutionPlan:
        """
        Translates a user task and its pipeline configuration into an immutable,
        declarative ExecutionPlan detailing the cascade, policies, and prompt versioning.
        """
        pipe_cfg = settings.get_pipeline_config(pipeline_name)
        if not pipe_cfg:
            raise ValueError(f"Pipeline '{pipeline_name}' is not configured in settings.")

        # Extract config values
        providers = pipe_cfg.get("providers", [])
        cache_enabled = pipe_cfg.get("cache", True)

        # Dynamically re-rank providers using CapabilityPlanner if enabled
        if settings.enable_capability_planner:
            try:
                from backend.services.ai_cascade.pipelines import (
                    SummaryPipeline, RAGPipeline, QuizPipeline, OCRPipeline, InsightPipeline, TranscriptionPipeline
                )
                PIPELINES_REGISTRY = {
                    "summary": SummaryPipeline,
                    "rag": RAGPipeline,
                    "quiz": QuizPipeline,
                    "ocr": OCRPipeline,
                    "insight": InsightPipeline,
                    "transcription": TranscriptionPipeline
                }
                pipeline_cls = PIPELINES_REGISTRY.get(pipeline_name)
                if pipeline_cls:
                    pipeline_inst = pipeline_cls()
                    required_caps = pipeline_inst.required_capabilities
                    
                    from backend.services.ai_cascade.planner.capability import CapabilityPlanner
                    capability_planner = CapabilityPlanner()
                    ranked_models = capability_planner.plan_capabilities(required_caps)
                    
                    dynamic_providers = []
                    for model in ranked_models:
                        if model.provider_name not in dynamic_providers:
                            dynamic_providers.append(model.provider_name)
                    
                    # Intersect with configured providers for safety compliance
                    providers = [p for p in dynamic_providers if p in providers]
            except Exception as plan_err:
                # Fail gracefully back to default configured providers
                pass

        # Create localized execution policies
        retry_policy = {"policy": "default", "max_retries": 1}
        cache_policy = {"policy": "strict" if cache_enabled else "disabled"}
        security_policy = {"policy": "default", "mask_pii": True}
        timeout_policy = {"policy": "aggressive", "timeout_seconds": 15}

        # Build plan
        return ExecutionPlan(
            task=task,
            pipeline=pipeline_name,
            providers=providers,
            prompt_version="v1.0",
            schema_version="1.0",
            retry_policy=retry_policy,
            cache_policy=cache_policy,
            security_policy=security_policy,
            timeout_policy=timeout_policy
        )
