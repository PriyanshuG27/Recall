import pytest
from unittest import mock
from pydantic import ValidationError

from backend.config import settings
from backend.services.redis_client import redis
from backend.services.ai_cascade.registry.model_registry import ModelRegistry, ModelCapability, ModelMetadata
from backend.services.ai_cascade.registry.router import AIRouter, RoutingRequirements

@pytest.fixture(autouse=True)
def clean_breaker_state():
    # Reset circuit breaker mock or redis state before each test
    pass

# ==============================================================================
# ROUTER REGISTRY FILTERING & SORTING TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_select_candidate_models_by_capability():
    # Speech to text capability should only select whisper/modal-transcribe models
    req = RoutingRequirements(capability=ModelCapability.SPEECH_TO_TEXT)
    candidates = await AIRouter.select_candidate_models(req)
    for c in candidates:
        assert ModelCapability.SPEECH_TO_TEXT in c.capabilities
        assert c.provider_name in ["groq", "modal", "gemini"]

    # Vision capability should select Gemini
    req_vision = RoutingRequirements(capability=ModelCapability.VISION)
    candidates_vision = await AIRouter.select_candidate_models(req_vision)
    for c in candidates_vision:
        assert ModelCapability.VISION in c.capabilities
        assert c.provider_name == "gemini"


@pytest.mark.asyncio
async def test_select_candidate_models_by_token_limit():
    # Requesting large context should filter out low context models (like openrouter-gpt-oss: 4096 context window)
    req = RoutingRequirements(
        capability=ModelCapability.TEXT_GENERATION,
        context_tokens_needed=20000
    )
    # Using small input payload
    candidates = await AIRouter.select_candidate_models(req, input_size_chars=0)
    for c in candidates:
        assert c.max_context_tokens >= 20000
        assert c.model_id != "openai/gpt-oss-120b:free"

    # Using very large input payload (e.g. 120k chars ~ 30k tokens)
    candidates_large = await AIRouter.select_candidate_models(req, input_size_chars=120000)
    for c in candidates_large:
        assert c.max_context_tokens >= 30000


@pytest.mark.asyncio
async def test_select_candidate_models_sorting_cost_and_override(monkeypatch):
    # Set preferred compute provider
    monkeypatch.setattr(settings, "COMPUTE_PROVIDER", "groq")

    req = RoutingRequirements(
        capability=ModelCapability.TEXT_GENERATION,
        optimization_strategy="cost"
    )
    candidates = await AIRouter.select_candidate_models(req)
    
    # Preferred provider (groq) models must be listed before other providers
    first_provider = candidates[0].provider_name
    assert first_provider == "groq"


# ==============================================================================
# ROUTER CASCADE & CIRCUIT BREAKER TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_router_cascade_success(monkeypatch):
    # Mock settings keys to permit calls
    monkeypatch.setattr(settings, "GROQ_API_KEY", "mock-groq-key")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "mock-gemini-key")

    groq_meta = ModelRegistry.get_model("qwen/qwen3-32b")
    gemini_meta = ModelRegistry.get_model("gemini-3.1-flash-lite")
    
    async def mock_select(*args, **kwargs):
        return [groq_meta, gemini_meta]
    
    monkeypatch.setattr(AIRouter, "select_candidate_models", mock_select)

    # 1. Primary provider (Groq) fails with an exception, secondary (Gemini) succeeds
    mock_groq = mock.AsyncMock()
    mock_groq.chat_completion.side_effect = Exception("Groq Rate Limit")
    
    mock_gemini = mock.AsyncMock()
    mock_gemini.chat_completion.return_value = "Gemini fallback response text"

    monkeypatch.setitem(AIRouter.adapters, "groq", mock_groq)
    monkeypatch.setitem(AIRouter.adapters, "gemini", mock_gemini)

    req = RoutingRequirements(capability=ModelCapability.TEXT_GENERATION)
    res = await AIRouter.route_task(
        task_name="test_cascade",
        payload="Hi",
        requirements=req,
        user_id=1
    )

    assert res == "Gemini fallback response text"
    
    # Groq should have been called and failed
    mock_groq.chat_completion.assert_called_once()
    # Gemini should have been called as fallback
    mock_gemini.chat_completion.assert_called_once()


@pytest.mark.asyncio
async def test_circuit_breaker_degradation_blocking(monkeypatch):
    # Mock settings keys to permit calls
    monkeypatch.setattr(settings, "GROQ_API_KEY", "mock-groq-key")
    
    # 1. Simulate that groq is blocked (tripped breaker)
    async def mock_blocked(key):
        if "ai_breaker:blocked:groq" in key:
            return "blocked"
        return None
        
    monkeypatch.setattr(redis, "get", mock_blocked)

    # Request Text Gen
    req = RoutingRequirements(capability=ModelCapability.TEXT_GENERATION)
    candidates = await AIRouter.select_candidate_models(req)
    
    # Groq models should not be in candidate list because it's blocked/unhealthy
    for c in candidates:
        assert c.provider_name != "groq"


@pytest.mark.asyncio
async def test_router_raises_on_all_failed(monkeypatch):
    # Mock settings keys to permit calls
    monkeypatch.setattr(settings, "GROQ_API_KEY", "mock-groq-key")

    mock_groq = mock.AsyncMock()
    mock_groq.chat_completion.side_effect = Exception("Groq Down")
    monkeypatch.setitem(AIRouter.adapters, "groq", mock_groq)

    groq_meta = ModelRegistry.get_model("qwen/qwen3-32b")
    async def mock_select(*args, **kwargs):
        return [groq_meta]
    monkeypatch.setattr(AIRouter, "select_candidate_models", mock_select)

    req = RoutingRequirements(capability=ModelCapability.TEXT_GENERATION)
    
    # Router should raise RuntimeError after failing all candidates
    with pytest.raises(RuntimeError) as exc_info:
        await AIRouter.route_task(
            task_name="test_all_fail",
            payload="Hello",
            requirements=req,
            user_id=1
        )
    assert "All candidate models failed" in str(exc_info.value)
