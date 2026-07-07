import pytest
import unittest.mock as mock
from backend.services.ai_cascade.models import AITask, ExecutionPlan, ExecutionContext
from backend.services.ai_cascade.executor import ExecutionEngine
from backend.services.ai_cascade.providers.registry import provider_registry
from backend.services.ai_cascade.providers.manager import provider_manager
from backend.services.ai_cascade.models import AIState
from backend.services.ai_cascade.shared.exceptions import ProviderError


# We reuse the MockProvider from test_ai_providers_foundation
class MockSuccessProvider:
    @property
    def provider_name(self) -> str:
        return "mocksuccess"

    async def chat_completion(self, *args, **kwargs) -> str:
        return '{"summary": "Success"}'


class MockFailProvider:
    @property
    def provider_name(self) -> str:
        return "mockfail"

    async def chat_completion(self, *args, **kwargs) -> str:
        raise ValueError("API connection failed")


@pytest.mark.asyncio
async def test_execution_engine_success_flow():
    provider_registry.register("mocksuccess", MockSuccessProvider)

    task = AITask(input_data={"text": "hello"})
    plan = ExecutionPlan(
        task=task,
        pipeline="summary",
        providers=["mocksuccess"],
        prompt_version="v1",
        schema_version="1"
    )
    context = ExecutionContext()
    assert context.status == AIState.QUEUED

    engine = ExecutionEngine()
    result = await engine.execute_plan(plan, context, "System", "User")

    assert context.status == AIState.SUCCEEDED
    assert context.started_at is not None
    assert context.finished_at is not None
    assert result.provider_used == "mocksuccess"
    assert "Success" in result.metadata["raw_response"]


@pytest.mark.asyncio
async def test_execution_engine_fallback_and_skipping():
    provider_registry.register("mockfail", MockFailProvider)
    provider_registry.register("mocksuccess", MockSuccessProvider)

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

        # Let's verify mockfail registers correctly
        await provider_manager.report_success("mockfail")
        await provider_manager.report_success("mocksuccess")

        task = AITask(input_data={"text": "hello"})
        # Fail first, then succeed
        plan = ExecutionPlan(
            task=task,
            pipeline="summary",
            providers=["mockfail", "mocksuccess"],
            prompt_version="v1",
            schema_version="1"
        )
        context = ExecutionContext()
        engine = ExecutionEngine()

        result = await engine.execute_plan(plan, context, "System", "User")
        assert context.status == AIState.SUCCEEDED
        assert result.provider_used == "mocksuccess"  # Fell back successfully!

        # Report failure 2 more times to trip the circuit (consecutive failures threshold is 3)
        await provider_manager.report_failure("mockfail")
        await provider_manager.report_failure("mockfail")

        # mockfail should now be marked unhealthy
        assert await provider_manager.is_healthy("mockfail") is False

        # A subsequent plan listing mockfail first should skip it entirely and use mocksuccess
        context2 = ExecutionContext()
        result2 = await engine.execute_plan(plan, context2, "System", "User")
        assert context2.status == AIState.SUCCEEDED
    assert result2.provider_used == "mocksuccess"
