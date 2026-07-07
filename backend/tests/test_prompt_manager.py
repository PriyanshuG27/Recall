import pytest
from backend.services.ai_cascade.prompt_manager import PromptManager

def test_prompt_manager_load_existing():
    prompt = PromptManager.get_prompt("summarize", "v1")
    assert "cognitive assistant" in prompt
    assert "JSON keys" in prompt

def test_prompt_manager_not_found():
    with pytest.raises(FileNotFoundError):
        PromptManager.get_prompt("invalid_prompt_name", "v1")
