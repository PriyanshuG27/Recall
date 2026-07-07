import os
import json
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from backend.services.ai_cascade.events.event_bus import (
    event_bus, BaseEvent, CacheHit, LLMRequestFinished, EventPriority
)
from backend.services.ai_cascade.analytics.prompt_analytics import prompt_analytics
from backend.services.ai_cascade.benchmark.runner import BenchmarkRunner
from backend.services.ai_cascade.shared.exceptions import ModelDeprecationError
from backend.services.ai_cascade.providers.deprecation import deprecation_manager

class DummyEvent(BaseEvent):
    value: str
    priority: EventPriority = EventPriority.LOW


@pytest.mark.asyncio
async def test_event_bus_subscriber_isolation():
    """Verify that a subscriber throwing an exception does not prevent other subscribers from executing."""
    event_bus.clear_subscribers()
    event_bus.initialize()

    success_called = False
    
    class ThrowingHandler:
        async def handle(self, event: BaseEvent) -> None:
            raise RuntimeError("Subscriber Crash Simulation!")

    class SuccessHandler:
        async def handle(self, event: BaseEvent) -> None:
            nonlocal success_called
            success_called = True

    event_bus.subscribe(DummyEvent, ThrowingHandler())
    event_bus.subscribe(DummyEvent, SuccessHandler())

    await event_bus.publish(DummyEvent(request_id="test-req", value="hello"))
    assert success_called is True
    event_bus.clear_subscribers()


@pytest.mark.asyncio
async def test_event_bus_multiple_subscribers():
    """Verify multiple subscribers receive the same published event."""
    event_bus.clear_subscribers()
    event_bus.initialize()

    calls = []

    class HandlerA:
        async def handle(self, event: BaseEvent) -> None:
            calls.append("A")

    class HandlerB:
        async def handle(self, event: BaseEvent) -> None:
            calls.append("B")

    event_bus.subscribe(DummyEvent, HandlerA())
    event_bus.subscribe(DummyEvent, HandlerB())

    await event_bus.publish(DummyEvent(request_id="test-req", value="hello"))
    assert "A" in calls
    assert "B" in calls
    event_bus.clear_subscribers()


@pytest.mark.asyncio
async def test_event_bus_zero_subscribers():
    """Verify publishing an event with zero subscribers completes cleanly."""
    event_bus.clear_subscribers()
    event_bus.initialize()
    
    await event_bus.publish(DummyEvent(request_id="test-req", value="hello"))
    event_bus.clear_subscribers()


@pytest.mark.asyncio
async def test_event_bus_concurrent_publish():
    """Verify thread/async safety and race conditions under concurrent publishing."""
    event_bus.clear_subscribers()
    event_bus.initialize()

    count = 0

    class CountingHandler:
        async def handle(self, event: BaseEvent) -> None:
            nonlocal count
            await asyncio.sleep(0.01)
            count += 1

    event_bus.subscribe(DummyEvent, CountingHandler())

    tasks = [event_bus.publish(DummyEvent(request_id=f"req-{i}", value="hello")) for i in range(10)]
    await asyncio.gather(*tasks)

    assert count == 10
    event_bus.clear_subscribers()


@pytest.mark.asyncio
async def test_prompt_analytics_cache_hit():
    """Verify CacheHit updates prompt analytics stats."""
    prompt_analytics.shutdown()
    prompt_analytics.initialize()
    event_bus.initialize()

    event = CacheHit(
        request_id="cache-req",
        pipeline="summary",
        key="summary_cache_key"
    )
    
    await event_bus.publish(event)
    
    metrics = prompt_analytics.get_prompt_metrics(hours=24)
    assert len(metrics) > 0
    cache_hit_metric = next(m for m in metrics if m["pipeline"] == "summary")
    assert cache_hit_metric["cache_hit_rate"] == 1.0
    assert cache_hit_metric["total_calls"] == 1
    
    prompt_analytics.shutdown()
    event_bus.clear_subscribers()


@pytest.mark.asyncio
async def test_deprecation_manager_trips():
    """Verify DeprecationManager raises ModelDeprecationError on retired models."""
    from backend.services.ai_cascade.config import settings
    settings.providers = {
        "groq": {
            "enabled": True,
            "priority": 1,
            "timeout": 10,
            "retries": 1,
            "cooldown": 60,
            "circuit_threshold": 3,
            "health_check_interval": 30,
            "models": {
                "openai/gpt-oss-120b": {
                    "status": "retired",
                    "replacement": "gemini-3.1-flash-lite"
                }
            }
        }
    }

    with pytest.raises(ModelDeprecationError) as exc_info:
        deprecation_manager.check_model_deprecation("groq", "openai/gpt-oss-120b")
    
    assert "retired and cannot be run" in str(exc_info.value)
    settings.load_configs()


@pytest.mark.asyncio
async def test_benchmark_runner_survives_provider_failure():
    """Verify benchmark runner compiles successfully even if a provider attempt fails."""
    import tempfile
    
    temp_json = [
        {
            "id": 1,
            "name": "Test Ingestion",
            "type": "short_text",
            "input_text": "Brief input summary statement.",
            "expected_summary": "Expected output statement.",
            "expected_tags": ["test"],
            "expected_keywords": ["statement"],
            "target_min_len": 5,
            "target_max_len": 50
        }
    ]
    
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False, encoding="utf-8") as tmp:
        json.dump(temp_json, tmp)
        tmp_path = tmp.name

    try:
        runner = BenchmarkRunner(tmp_path)
        from backend.services.ai_cascade.providers.groq import GroqProvider
        from backend.services.ai_cascade.providers.gemini import GeminiProvider
        
        orig_groq = GroqProvider.chat_completion
        orig_gemini = GeminiProvider.chat_completion
        
        async def mock_groq_fail(*args, **kwargs):
            raise RuntimeError("Groq Outage Simulation!")
            
        async def mock_gemini_success(*args, **kwargs):
            return json.dumps({
                "summary": "Expected output statement.",
                "tags": ["test"],
                "key_points": ["statement"],
                "context_prompt": "Prompt"
            })
            
        GroqProvider.chat_completion = mock_groq_fail
        GeminiProvider.chat_completion = mock_gemini_success
        
        report = await runner.run()
        
        assert report["average_weighted_score"] > 0.0
        assert report["results"][0]["status"] == "succeeded"
        
        GroqProvider.chat_completion = orig_groq
        GeminiProvider.chat_completion = orig_gemini
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
