import pytest
from backend.services.ai_cascade.models import BaseAIResult, SummaryResult
from backend.services.ai_cascade.persistence import persistence_manager
from backend.services.ai_cascade.executor import response_composer


def test_persistence_manager_boundaries():
    # Reset local state log
    persistence_manager.persisted_records = []

    res = SummaryResult(
        provider_used="nvidia",
        model_used="qwen",
        summary="A short summary.",
        tags=["nlp"],
        metadata={
            "raw_response": "{'full_payload': 'big'}",
            "api_key": "sk-secret-key",
            "execution_id": "exec-123"
        }
    )

    # Normal save (should filter out raw response and secret keys)
    persistence_manager.save_result(res, cache_hit=False)
    assert len(persistence_manager.persisted_records) == 1
    
    saved = persistence_manager.persisted_records[0]
    assert saved["summary"] == "A short summary."
    assert saved["tags"] == ["nlp"]
    assert saved["provider_used"] == "nvidia"
    assert saved["metadata"] == {"execution_id": "exec-123"}  # filtered
    assert "raw_response" not in saved["metadata"]
    assert "api_key" not in saved["metadata"]


def test_persistence_manager_cache_hit_skip():
    persistence_manager.persisted_records = []
    
    res = BaseAIResult(provider_used="groq", model_used="llama", metadata={})
    
    # Save with cache hit (should be a no-op / skip DB write)
    persistence_manager.save_result(res, cache_hit=True)
    assert len(persistence_manager.persisted_records) == 0


def test_response_composer_outputs():
    # 1. Base Result
    res_base = BaseAIResult(
        provider_used="gemini",
        model_used="gemini-3.1",
        metadata={"execution_id": "xyz"}
    )
    dto_base = response_composer.compose_response(res_base)
    assert dto_base["provider"] == "gemini"
    assert dto_base["model"] == "gemini-3.1"
    assert dto_base["success"] is True

    # 2. Summary Result
    res_sum = SummaryResult(
        provider_used="nvidia",
        model_used="qwen",
        summary="Final summary text",
        tags=["nlp", "recall"],
        context_prompt="Search related notes"
    )
    dto_sum = response_composer.compose_response(res_sum)
    assert dto_sum["summary"] == "Final summary text"
    assert dto_sum["tags"] == ["nlp", "recall"]
    assert dto_sum["context_prompt"] == "Search related notes"
