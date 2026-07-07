import pytest
import unittest.mock as mock
from typing import List, Optional
from backend.services.ai_cascade.providers.base import BaseProvider
from backend.services.ai_cascade.providers.registry import provider_registry
from backend.services.ai_cascade.providers.factory import provider_factory
from backend.services.ai_cascade.providers.manager import provider_manager


# Create a mock provider for testing
class MockProvider(BaseProvider):
    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def supported_capabilities(self) -> List[str]:
        return ["TEXT", "JSON"]

    async def initialize(self) -> None:
        self.initialized = True

    async def shutdown(self) -> None:
        self.initialized = False

    async def chat_completion(
        self,
        prompt: str,
        model_id: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[str] = None,
        **kwargs
    ) -> str:
        return f"Mock response: {prompt}"


def test_registry_registration():
    provider_registry.register("mock", MockProvider)
    cls = provider_registry.get_provider_class("mock")
    assert cls == MockProvider

    with pytest.raises(ValueError):
        provider_registry.get_provider_class("nonexistent")


def test_factory_singleton():
    provider_registry.register("mock", MockProvider)
    p1 = provider_factory.get_provider("mock")
    p2 = provider_factory.get_provider("mock")
    assert p1 is p2  # should be same cached singleton instance
    assert isinstance(p1, MockProvider)


@pytest.mark.asyncio
async def test_manager_health_flow():
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

        assert await provider_manager.is_healthy("mock") is True
        
        # Mark unhealthy by hitting default circuit breaker threshold (3 failures)
        await provider_manager.report_failure("mock")
        await provider_manager.report_failure("mock")
        await provider_manager.report_failure("mock")
        assert await provider_manager.is_healthy("mock") is False

        # Mark healthy again
        await provider_manager.report_success("mock")
        assert await provider_manager.is_healthy("mock") is True
