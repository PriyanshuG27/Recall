import asyncio
import pytest
import unittest.mock as mock
from typing import Dict, Any

from backend.services.ai_cascade.shared.exceptions import (
    OutputValidationError,
    ProviderError,
    CascadeTimeoutError,
    RateLimitExceededError
)
from backend.services.ai_cascade.models import ExecutionPlan, ExecutionContext, SummaryResult
from backend.services.ai_cascade.executor.engine import ExecutionEngine
from backend.services.ai_cascade.executor.retry import RetryEngine
from backend.services.ai_cascade.validators import ValidatorRegistry
from backend.services.ai_cascade.validators.base import BaseValidator
from backend.services.ai_cascade.cache.health_store import health_store
from backend.services.ai_cascade.providers.manager import provider_manager


# ==============================================================================
# 1. VALIDATOR TESTS
# ==============================================================================

def test_base_validator_clean_json():
    validator = ValidatorRegistry.get_validator("summary")
    raw_md = "```json\n{\n  \"summary\": \"This is clean.\"\n}\n```"
    cleaned = validator.clean_markdown_json(raw_md)
    assert cleaned == "{\n  \"summary\": \"This is clean.\"\n}"


def test_base_validator_heuristic_recovery():
    validator = ValidatorRegistry.get_validator("summary")
    junk_output = "Some explanation before the json:\n{\n  \"summary\": \"Success\"\n}\nExplanation after."
    recovered = validator.extract_json_arrays(junk_output)
    assert recovered == "{\n  \"summary\": \"Success\"\n}"


def test_concrete_validator_summary_success():
    validator = ValidatorRegistry.get_validator("summary")
    valid_data = {
        "summary": "This is a valid summary of length greater than 5.",
        "tags": ["ml", "ai"],
        "key_points": ["Point 1", "Point 2"],
        "context_prompt": "What got you interested?"
    }
    assert validator.validate(valid_data) is True


def test_concrete_validator_summary_invalid():
    validator = ValidatorRegistry.get_validator("summary")
    invalid_data = {
        # Missing required "summary" key
        "tags": ["ml"],
        "key_points": []
    }
    with pytest.raises(OutputValidationError):
        validator.validate(invalid_data)


# ==============================================================================
# 2. RETRY ENGINE & SEMAPHORE TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_retry_engine_backoff():
    retry_engine = RetryEngine()
    mock_provider = mock.AsyncMock()
    
    # Simulate timeout on first call, success on second
    mock_provider.chat_completion.side_effect = [
        CascadeTimeoutError("Connection timed out"),
        "{\"summary\": \"Retry succeeded\"}"
    ]
    
    res = await retry_engine.execute_with_retry(
        provider=mock_provider,
        messages=[{"role": "user", "content": "test"}],
        model="mock-model",
        timeout=5.0,
        retries=1,
        backoff_factor=0.01,  # Fast sleep in tests
        min_delay=0.01,
        jitter=0.005
    )
    
    assert res == "{\"summary\": \"Retry succeeded\"}"
    assert mock_provider.chat_completion.call_count == 2


@pytest.mark.asyncio
async def test_retry_engine_rate_limit_cooldown():
    retry_engine = RetryEngine()
    mock_provider = mock.AsyncMock()
    
    # Simulate rate limit on first call, success on second
    mock_provider.chat_completion.side_effect = [
        RateLimitExceededError("Too many requests"),
        "{\"summary\": \"Succeeded after 429\"}"
    ]
    
    # Patch asyncio.sleep so we don't block tests
    with mock.patch("asyncio.sleep", new_callable=mock.AsyncMock) as mock_sleep:
        res = await retry_engine.execute_with_retry(
            provider=mock_provider,
            messages=[{"role": "user", "content": "test"}],
            model="mock-model",
            timeout=5.0,
            retries=1
        )
        assert res == "{\"summary\": \"Succeeded after 429\"}"
        mock_sleep.assert_called_once_with(5.0)


@pytest.mark.asyncio
async def test_engine_semaphore_concurrency():
    engine = ExecutionEngine()
    
    # Let's mock a provider that sleeps 0.2 seconds to simulate long-running calls
    mock_provider = mock.AsyncMock()
    async def slow_completion(*args, **kwargs):
        await asyncio.sleep(0.1)
        return "{\"summary\": \"Task finished\", \"tags\": [], \"key_points\": []}"
    mock_provider.chat_completion.side_effect = slow_completion
    
    # Register mock provider safely using patch.object
    with mock.patch.object(engine.provider_manager, "get_provider", return_value=mock_provider):
        from backend.services.ai_cascade.models import AITask
        task = AITask(input_data={"text": "hello"})
        plan = ExecutionPlan(
            task=task,
            pipeline="summary",
            providers=["mock-provider"],
            prompt_version="v1",
            schema_version="1"
        )
        contexts = [ExecutionContext() for _ in range(5)]
        
        # Run 5 tasks concurrently
        tasks = [
            engine.execute_plan(plan, ctx, "", "Prompt") for ctx in contexts
        ]
        
        # Execute concurrently and verify all finish successfully
        results = await asyncio.gather(*tasks)
        assert len(results) == 5
        for r in results:
            assert isinstance(r, SummaryResult)
            assert r.summary == "Task finished"


# ==============================================================================
# 3. CIRCUIT BREAKER & HEALTH STORE TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_circuit_breaker_flow():
    # In mock mode, health_store uses mocked redis which returns None/0.
    # Let's mock Redis explicitly to simulate actual circuit breaking.
    mock_redis_data = {}
    
    async def mock_get(key):
        return mock_redis_data.get(key)
    async def mock_setex(key, seconds, value):
        mock_redis_data[key] = value
        return True
    async def mock_delete(key):
        mock_redis_data.pop(key, None)
        return 1

    with mock.patch("backend.services.redis_client.redis.get", mock_get), \
         mock.patch("backend.services.redis_client.redis.setex", mock_setex), \
         mock.patch("backend.services.redis_client.redis.delete", mock_delete):
         
         # 1. Initially healthy
         assert await health_store.is_healthy("groq") is True
         
         # 2. Report 2 failures (threshold is 3)
         await provider_manager.report_failure("groq")
         await provider_manager.report_failure("groq")
         assert await health_store.is_healthy("groq") is True
         
         # 3. Third failure opens the circuit
         await provider_manager.report_failure("groq")
         assert await health_store.is_healthy("groq") is False
         
         # 4. Report success closes circuit and resets counter
         await provider_manager.report_success("groq")
         assert await health_store.is_healthy("groq") is True
