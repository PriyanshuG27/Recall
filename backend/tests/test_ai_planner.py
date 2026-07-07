import pytest
from backend.services.ai_cascade.models import AITask
from backend.services.ai_cascade.planner import CapabilityPlanner, AIPlanner
from backend.services.ai_cascade.registry.model_registry import ModelCapability


def test_capability_planner_filtering():
    planner = CapabilityPlanner()
    
    # Check text capabilities filtering
    text_models = planner.plan_capabilities([ModelCapability.TEXT_GENERATION])
    assert len(text_models) > 0
    # Every model must support text generation
    for model in text_models:
        assert ModelCapability.TEXT_GENERATION in model.capabilities

    # Check speech capability filtering (like Whisper)
    speech_models = planner.plan_capabilities([ModelCapability.SPEECH_TO_TEXT])
    assert len(speech_models) > 0
    for model in speech_models:
        assert ModelCapability.SPEECH_TO_TEXT in model.capabilities

    # Check context size filtering (should exclude smaller context windows)
    large_context_models = planner.plan_capabilities(
        [ModelCapability.TEXT_GENERATION],
        max_context_needed=100000
    )
    for model in large_context_models:
        assert model.context_window >= 100000
        # gpt-oss-120b context window is smaller, shouldn't be here
        assert model.model_id != "openai/gpt-oss-120b"


def test_ai_planner_produces_valid_plan():
    planner = AIPlanner()
    task = AITask(input_data={"text": "generate a summary of this document"})
    
    # Generate plan for summary pipeline
    plan = planner.plan_execution(task, "summary")
    
    assert plan.task == task
    assert plan.pipeline == "summary"
    assert plan.providers == ["groq", "nvidia", "cerebras", "gemini", "openrouter"]
    assert plan.prompt_version == "v1.0"
    assert plan.schema_version == "1.0"
    assert plan.retry_policy["policy"] == "default"
    assert plan.cache_policy["policy"] == "strict"
    assert plan.security_policy["mask_pii"] is True
    assert plan.timeout_policy["timeout_seconds"] == 15


def test_ai_planner_raises_on_invalid_pipeline():
    planner = AIPlanner()
    task = AITask(input_data={"text": "test"})
    
    with pytest.raises(ValueError):
        planner.plan_execution(task, "nonexistent-pipeline")
