import logging
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel

from backend.config import settings
from backend.services.redis_client import redis
from backend.services.dlq import write_to_dlq
from backend.services.ai_cascade.registry.model_registry import ModelRegistry, ModelMetadata, ModelCapability
from backend.services.ai_cascade.telemetry.cost_manager import CostManager
from backend.services.ai_cascade.providers.factory import provider_factory
from backend.services.ai_cascade.providers.manager import provider_manager

logger = logging.getLogger(__name__)

class RoutingRequirements(BaseModel):
    capability: ModelCapability
    optimization_strategy: str = "cost"  # "cost", "speed", "quality"
    context_tokens_needed: int = 4096
    json_format: bool = False

class AIRouter:
    adapters = {}

    @classmethod
    def _estimate_tokens(cls, payload: Any) -> int:
        """Fast character-to-token ratio approximation (approx 4 chars per token)."""
        if not payload:
            return 0
        if isinstance(payload, str):
            return len(payload) // 4
        if isinstance(payload, list):
            total_chars = 0
            for msg in payload:
                if isinstance(msg, dict):
                    total_chars += len(msg.get("content", ""))
            return total_chars // 4
        return 0

    @classmethod
    async def select_candidate_models(cls, requirements: RoutingRequirements, input_size_chars: int = 0) -> List[ModelMetadata]:
        # 1. Filter by capability
        candidates = ModelRegistry.get_models_by_capability(requirements.capability)
        
        # 2. Filter by context length boundary checking (using 4 chars per token approximation)
        tokens_needed = requirements.context_tokens_needed
        if input_size_chars > 0:
            tokens_needed = max(tokens_needed, input_size_chars // 4)
            
        candidates = [c for c in candidates if c.max_context_tokens >= tokens_needed]
        
        # 3. Filter by health (circuit breaker)
        healthy_candidates = []
        for c in candidates:
            if await provider_manager.is_healthy(c.provider_name):
                healthy_candidates.append(c)
                
        # 4. Sort candidates based on optimization strategy
        preferred_provider = settings.COMPUTE_PROVIDER
        
        PROVIDER_PRIORITIES = {
            "groq": 0,
            "nvidia": 1,
            "cerebras": 2,
            "gemini": 3,
            "openrouter": 4,
            "modal": 5
        }
        
        def sorting_key(m: ModelMetadata):
            # Prioritize COMPUTE_PROVIDER settings if present
            pref_boost = 0 if preferred_provider and m.provider_name == preferred_provider else 1
            
            provider_prio = PROVIDER_PRIORITIES.get(m.provider_name, 99)
            
            # Sub-sort based on strategy
            if requirements.optimization_strategy == "cost":
                return (pref_boost, provider_prio, m.cost_per_million_input + m.cost_per_million_output)
            elif requirements.optimization_strategy == "speed":
                # Lower latency is better
                return (pref_boost, provider_prio, 0.5 if m.latency_class == "low" else 1.0)
            else:
                return (pref_boost, provider_prio, m.model_id)

        healthy_candidates.sort(key=sorting_key)
        return healthy_candidates

    @classmethod
    async def route_task(
        cls,
        task_name: str,
        payload: Any,
        requirements: RoutingRequirements,
        user_id: int = 0,
        **kwargs
    ) -> Any:
        # Determine payload character length
        input_size_chars = 0
        if isinstance(payload, str):
            input_size_chars = len(payload)
        elif isinstance(payload, list):
            for m in payload:
                if isinstance(m, dict):
                    input_size_chars += len(m.get("content", ""))

        candidates = await cls.select_candidate_models(requirements, input_size_chars=input_size_chars)
        if not candidates:
            err_msg = f"No active or healthy models matched requirements: {requirements}"
            logger.error(err_msg)
            # Write to DLQ
            await cls._write_dlq_safely(user_id, {"task": task_name, "error": err_msg}, err_msg, kwargs.get("db"))
            raise RuntimeError(err_msg)

        last_exception = None
        for model_meta in candidates:
            provider_name = model_meta.provider_name
            adapter = cls.adapters.get(provider_name)
            if not adapter:
                try:
                    adapter = provider_factory.get_provider(provider_name)
                except Exception:
                    continue
            if not adapter:
                continue

            # Check dynamic key settings credentials
            if provider_name == "groq" and not settings.GROQ_API_KEY:
                continue
            if provider_name == "gemini" and not settings.GEMINI_API_KEY:
                continue
            if provider_name == "openrouter" and not settings.OPENROUTER_API_KEY:
                continue
            if provider_name == "nvidia" and not settings.NVIDIA_API_KEY:
                continue
            if provider_name == "modal" and not settings.MODAL_API_TOKEN:
                continue
            if provider_name == "cerebras" and not getattr(settings, "CEREBRAS_API_KEY", None):
                continue

            try:
                # 1. Execute task based on capability contract
                result = None
                timeout = kwargs.get("timeout", 15.0)
                
                # Pre-calculate prompt tokens for logging fallback
                prompt_tokens = cls._estimate_tokens(payload)

                if requirements.capability == ModelCapability.TEXT_GENERATION or requirements.capability == ModelCapability.STRUCTURED_JSON:
                    messages = payload
                    if isinstance(payload, str):
                        messages = [{"role": "user", "content": payload}]
                        
                    # Inject system prompt override if specified
                    system_prompt = kwargs.get("system_prompt")
                    if system_prompt and isinstance(messages, list):
                        # Prepend system message
                        messages = [{"role": "system", "content": system_prompt}] + messages
                        
                    result = await adapter.chat_completion(
                        messages=messages,
                        temperature=kwargs.get("temperature", 0.2),
                        timeout=timeout,
                        json_mode=requirements.json_format,
                        max_tokens=kwargs.get("max_tokens"),
                        model=model_meta.model_id
                    )
                elif requirements.capability == ModelCapability.SPEECH_TO_TEXT:
                    result = await adapter.transcribe(
                        audio_bytes=payload,
                        file_extension=kwargs.get("file_extension", "ogg"),
                        timeout=timeout
                    )
                elif requirements.capability == ModelCapability.VISION:
                    result = await adapter.caption_image(
                        image_bytes=payload,
                        mime_type=kwargs.get("mime_type", "image/jpeg"),
                        timeout=timeout
                    )

                if result is not None:
                    # 2. Record success in circuit breaker
                    await provider_manager.report_success(provider_name)
                    
                    # 3. Log token cost usage
                    completion_tokens = cls._estimate_tokens(result) if isinstance(result, str) else 0
                    duration_seconds = kwargs.get("duration_seconds", 0.0)
                    
                    # Calculate duration for audio transcription if payload is bytes
                    if requirements.capability == ModelCapability.SPEECH_TO_TEXT and isinstance(payload, bytes):
                        # Approximate standard 24kbps (3000 bytes/sec) duration if not specified
                        if duration_seconds == 0.0:
                            duration_seconds = len(payload) / 3000.0
                            
                    await CostManager.log_usage(
                        provider=provider_name,
                        model=model_meta.model_id,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        duration_seconds=duration_seconds,
                        cursor=kwargs.get("cursor")
                    )
                    return result
                else:
                    raise RuntimeError("Adapter returned empty response")
            except Exception as e:
                logger.warning("Provider %s failed for model %s: %s. Fallback triggered.", provider_name, model_meta.model_id, e)
                # Trip breaker failure counter
                await provider_manager.report_failure(provider_name)
                last_exception = e
                continue

        # If all candidates fail, write to DLQ
        err_msg = f"All candidate models failed. Last error: {last_exception}"
        await cls._write_dlq_safely(user_id, {"task": task_name, "payload": str(payload)[:1000]}, err_msg, kwargs.get("db"))
        raise RuntimeError(err_msg)

    @classmethod
    async def _write_dlq_safely(cls, user_id: int, payload: dict, error_message: str, db: Optional[Any]) -> None:
        try:
            if db:
                await write_to_dlq(user_id, payload, error_message, db)
            else:
                import backend.db.connection as db_conn
                if db_conn._pool:
                    async with db_conn._pool.connection() as conn:
                        await write_to_dlq(user_id, payload, error_message, conn)
        except Exception as e:
            logger.error("Failed to write to DLQ: %s", e)
