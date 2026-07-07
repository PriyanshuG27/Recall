import os
import pytest
from backend.services.ai_cascade.config import settings


def test_provider_configs_loaded():
    assert len(settings.providers) > 0
    groq_cfg = settings.get_provider_config("groq")
    assert groq_cfg["enabled"] is True
    assert groq_cfg["priority"] == 0
    assert groq_cfg["timeout"] == 10
    assert groq_cfg["retries"] == 1
    assert groq_cfg["cooldown"] == 60
    assert groq_cfg["circuit_threshold"] == 3
    assert groq_cfg["health_check_interval"] == 30


def test_pipeline_configs_loaded():
    assert len(settings.pipelines) > 0
    summary_cfg = settings.get_pipeline_config("summary")
    assert summary_cfg["cache"] is True
    assert summary_cfg["validator"] == "SummaryValidator"
    assert summary_cfg["schema"] == "summary.json"
    assert summary_cfg["providers"] == ["groq", "nvidia", "cerebras", "gemini", "openrouter"]


def test_feature_flags_default_and_overrides():
    # Defaults should be true
    assert settings.enable_cerebras is True
    assert settings.enable_cache is True

    # Test environment overrides
    os.environ["ENABLE_CEREBRAS"] = "false"
    os.environ["ENABLE_CACHE"] = "false"

    assert settings.enable_cerebras is False
    assert settings.enable_cache is False

    # Reset environment variables
    os.environ.pop("ENABLE_CEREBRAS", None)
    os.environ.pop("ENABLE_CACHE", None)
