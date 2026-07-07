import asyncio
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from backend.services.ai_cascade.models import (
    ExecutionPlan,
    ExecutionContext,
    BaseAIResult,
    SummaryResult,
    RAGResult,
    QuizResult,
    OCRResult,
    InsightResult,
    TranscriptionResult
)
from backend.services.ai_cascade.providers.manager import provider_manager
from backend.services.ai_cascade.models import AIState
from backend.services.ai_cascade.shared.exceptions import ProviderError, OutputValidationError
from backend.services.ai_cascade.validators import ValidatorRegistry
from backend.services.ai_cascade.executor.retry import RetryEngine
from backend.services.ai_cascade.events.event_bus import (
    event_bus, LLMRequestStarted, ProviderSelected, LLMRequestFinished,
    ProviderFailed, ExecutionSucceeded, ExecutionFailed
)
from backend.services.ai_cascade.telemetry.cost_manager import CostManager


RESULT_CLASSES = {
    "summary": SummaryResult,
    "rag": RAGResult,
    "quiz": QuizResult,
    "ocr": OCRResult,
    "insight": InsightResult,
    "transcription": TranscriptionResult
}


class ExecutionEngine:
    def __init__(self):
        self.provider_manager = provider_manager
        self.retry_engine = RetryEngine()
        # Strictly cap concurrent AI tasks to 3
        self.semaphore = asyncio.Semaphore(3)

    async def execute_plan(
        self,
        plan: ExecutionPlan,
        context: ExecutionContext,
        system_prompt: str,
        user_prompt: str,
        capability: str = "text_generation",
        extra_args: dict | None = None
    ) -> BaseAIResult:
        """
        Executes the plan by iterating through providers in order.
        Updates state and timestamps in ExecutionContext.
        Uses Validator checks and RetryEngine.
        """
        from backend.services.ai_cascade.telemetry.cost_manager import current_user_id_var
        user_id = current_user_id_var.get()
        async with self.semaphore:
            context.status = AIState.RUNNING
            context.started_at = datetime.utcnow()
            
            await event_bus.publish(LLMRequestStarted(request_id=context.request_id))

            last_error = None
            validator = ValidatorRegistry.get_validator(plan.pipeline)

            for provider_name in plan.providers:
                # 1. Dynamically resolve active model_ids for this provider
                from backend.services.ai_cascade.config import settings as cascade_settings
                from backend.services.ai_cascade.registry.model_registry import ModelRegistry, ModelCapability
                provider_cfg = cascade_settings.get_provider_config(provider_name)
                cfg_models = provider_cfg.get("models", {})
                active_models = [m for m, meta in cfg_models.items() if meta.get("status") == "active"]
                if not active_models:
                    models = [
                        m.model_id for m in ModelRegistry._models.values()
                        if m.provider_name == provider_name and m.is_active
                    ]
                    active_models = [models[0]] if models else ["default-model"]

                # Intersect with registry capabilities to ensure correct routing (e.g. speech vs text)
                pipeline_cap_map = {
                    "transcription": ModelCapability.SPEECH_TO_TEXT,
                    "quiz": ModelCapability.STRUCTURED_JSON,
                    "ocr": ModelCapability.VISION,
                }
                req_cap = pipeline_cap_map.get(plan.pipeline, ModelCapability.TEXT_GENERATION)
                
                registry_models = [
                    m.model_id for m in ModelRegistry._models.values()
                    if m.provider_name == provider_name and req_cap in m.capabilities
                ]
                
                matched_models = [m for m in active_models if m in registry_models]
                if not matched_models:
                    matched_models = active_models

                # 2. Configuration & Capability Validation (Provider-Level Check)
                try:
                    from backend.services.ai_cascade.providers.base import ProviderCapability
                    cap_map = {
                        "transcription": ProviderCapability.TRANSCRIPTION,
                    }
                    cap = cap_map.get(plan.pipeline, ProviderCapability.CHAT_COMPLETION)
                    self.provider_manager.validate_provider(provider_name, cap)
                except Exception as e:
                    context.attempts.append({
                        "provider": provider_name,
                        "model": matched_models[0] if matched_models else "default-model",
                        "latency_ms": 0.0,
                        "status": "failed_validation",
                        "error": str(e)
                    })
                    continue

                # 3. Health-Based Skipping (Provider-Level Check)
                is_healthy = await self.provider_manager.is_healthy(provider_name)
                if not is_healthy:
                    context.attempts.append({
                        "provider": provider_name,
                        "model": matched_models[0] if matched_models else "default-model",
                        "latency_ms": 0.0,
                        "status": "unhealthy",
                        "error": "Circuit breaker open."
                    })
                    continue

                provider = self.provider_manager.get_provider(provider_name)

                # Loop through all matched active models for this provider
                provider_success = False
                for model_id in matched_models:
                    await event_bus.publish(ProviderSelected(
                        request_id=context.request_id,
                        provider=provider_name,
                        model=model_id
                    ))

                    # Extract custom timeout and retries from provider configuration
                    from backend.services.ai_cascade.config import settings
                    provider_cfg = settings.get_provider_config(provider_name)
                    timeout = provider_cfg.get("timeout", 15.0)
                    retries = provider_cfg.get("retries", 1)

                    # Hydrate messages payload
                    messages = []
                    if system_prompt:
                        messages.append({"role": "system", "content": system_prompt})
                    messages.append({"role": "user", "content": user_prompt})

                    t0 = time.perf_counter()
                    try:
                        # Check model deprecation status
                        from backend.services.ai_cascade.providers.deprecation import deprecation_manager
                        deprecation_manager.check_model_deprecation(provider_name, model_id)

                        # Execute provider call using the RetryEngine
                        raw_response = await self.retry_engine.execute_with_retry(
                            provider=provider,
                            messages=messages,
                            model=model_id,
                            timeout=timeout,
                            retries=retries,
                            request_id=context.request_id,
                            capability=capability,
                            extra_args=extra_args
                        )
                        latency = (time.perf_counter() - t0) * 1000.0

                        if raw_response is not None:
                            # Clean and parse JSON response via the validator
                            parsed_data = validator.parse_json(raw_response)
                            validator.validate(parsed_data)

                            # Success trigger -> report to ProviderManager
                            await self.provider_manager.report_success(provider_name)
                            context.status = AIState.SUCCEEDED
                            context.finished_at = datetime.utcnow()

                            prompt_tokens = CostManager.estimate_tokens(system_prompt or "") + CostManager.estimate_tokens(user_prompt or "")
                            completion_tokens = CostManager.estimate_tokens(raw_response or "")
                            
                            await event_bus.publish(LLMRequestFinished(
                                request_id=context.request_id,
                                user_id=user_id,
                                provider=provider_name,
                                model=model_id,
                                latency_ms=latency,
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                                success=True,
                                pipeline=plan.pipeline,
                                prompt_version=plan.prompt_version
                            ))
                            await event_bus.publish(ExecutionSucceeded(
                                request_id=context.request_id,
                                provider=provider_name,
                                model=model_id
                            ))

                            context.attempts.append({
                                "provider": provider_name,
                                "model": model_id,
                                "latency_ms": latency,
                                "status": "succeeded",
                                "error": ""
                            })

                            # Instantiate correct typed result class
                            result_cls = RESULT_CLASSES.get(plan.pipeline, BaseAIResult)
                            
                            # Populate fields based on class requirements
                            fields = {
                                "provider_used": provider_name,
                                "model_used": model_id,
                                "metadata": {
                                    "raw_response": raw_response,
                                    "execution_id": context.execution_id
                                }
                            }
                            
                            # Pack parsed variables (e.g. summary, tags, key_points)
                            for key, val in parsed_data.items():
                                fields[key] = val

                            return result_cls(**fields)

                    except Exception as e:
                        latency = (time.perf_counter() - t0) * 1000.0
                        last_error = e
                        
                        await event_bus.publish(ProviderFailed(
                            request_id=context.request_id,
                            provider=provider_name,
                            error=str(e)
                        ))
                        
                        prompt_tokens = CostManager.estimate_tokens(system_prompt or "") + CostManager.estimate_tokens(user_prompt or "")
                        await event_bus.publish(LLMRequestFinished(
                            request_id=context.request_id,
                            user_id=user_id,
                            provider=provider_name,
                            model=model_id,
                            latency_ms=latency,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=0,
                            success=False,
                            error=str(e),
                            pipeline=plan.pipeline,
                            prompt_version=plan.prompt_version
                        ))

                        context.attempts.append({
                            "provider": provider_name,
                            "model": model_id,
                            "latency_ms": latency,
                            "status": "failed",
                            "error": str(e)
                        })

                # Failover trigger: only report provider failure after all models for the provider failed
                await self.provider_manager.report_failure(provider_name)

            # All providers failed
            context.status = AIState.FAILED
            context.finished_at = datetime.utcnow()
            await event_bus.publish(ExecutionFailed(request_id=context.request_id, error=str(last_error)))
            raise ProviderError(f"All providers in the plan failed. Last error: {last_error}")
