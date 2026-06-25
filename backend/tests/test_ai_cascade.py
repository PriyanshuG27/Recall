import pytest
import unittest.mock as mock
import sys
from backend.services.ai_cascade import AICascade
from backend.config import settings

@pytest.fixture
def override_test_guard():
    # Helper to bypass the unit test check inside AICascade
    cascade = AICascade()
    cascade._force_production_llm = True
    return cascade

def test_strip_thinking():
    cascade = AICascade()
    
    # 1. No think block
    assert cascade._strip_thinking("Hello World") == "Hello World"
    
    # 2. Basic think block
    text = "<think>some thoughts</think>Hello World"
    assert cascade._strip_thinking(text) == "Hello World"
    
    # 3. Multiline think block
    text_multiline = "<think>\nline 1\nline 2\n</think>\nResult content"
    assert cascade._strip_thinking(text_multiline) == "Result content"
    
    # 4. Empty text
    assert cascade._strip_thinking("") == ""
    assert cascade._strip_thinking(None) == ""

@pytest.mark.asyncio
async def test_summary_cascade_modal_success(monkeypatch, override_test_guard):
    orig_token = settings.MODAL_API_TOKEN
    settings.MODAL_API_TOKEN = "real-modal-token"
    
    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json = mock.Mock(return_value={"summary": "Modal generated summary"})
    
    async def mock_post(*args, **kwargs):
        return mock_resp
        
    monkeypatch.setattr("httpx.AsyncClient.post", mock_post)
    
    try:
        res = await override_test_guard._run_summary_cascade("test text", None)
        assert res == "Modal generated summary"
    finally:
        settings.MODAL_API_TOKEN = orig_token

@pytest.mark.asyncio
async def test_summary_cascade_groq_success(monkeypatch, override_test_guard):
    orig_token = settings.MODAL_API_TOKEN
    orig_groq = settings.GROQ_API_KEY
    orig_provider = settings.COMPUTE_PROVIDER
    
    settings.MODAL_API_TOKEN = None
    settings.GROQ_API_KEY = "real-groq-key"
    settings.COMPUTE_PROVIDER = "groq"
    
    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json = mock.Mock(return_value={
        "choices": [{
            "message": {
                "content": "<think>reasoning</think>Groq summary"
            }
        }]
    })
    
    async def mock_post(*args, **kwargs):
        return mock_resp
        
    monkeypatch.setattr("httpx.AsyncClient.post", mock_post)
    
    try:
        res = await override_test_guard._run_summary_cascade("test text", None)
        # Note: _run_summary_cascade doesn't call _strip_thinking, summarise does.
        assert res == "<think>reasoning</think>Groq summary"
    finally:
        settings.MODAL_API_TOKEN = orig_token
        settings.GROQ_API_KEY = orig_groq
        settings.COMPUTE_PROVIDER = orig_provider

@pytest.mark.asyncio
async def test_summary_cascade_gemini_success(monkeypatch, override_test_guard):
    orig_token = settings.MODAL_API_TOKEN
    orig_groq = settings.GROQ_API_KEY
    orig_gemini = settings.GEMINI_API_KEY
    orig_provider = settings.COMPUTE_PROVIDER
    
    settings.MODAL_API_TOKEN = None
    settings.GROQ_API_KEY = None
    settings.GEMINI_API_KEY = "real-gemini-key"
    settings.COMPUTE_PROVIDER = "gemini"
    
    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json = mock.Mock(return_value={
        "candidates": [{
            "content": {
                "parts": [{"text": "Gemini summary text"}]
            }
        }]
    })
    
    async def mock_post(*args, **kwargs):
        return mock_resp
        
    monkeypatch.setattr("httpx.AsyncClient.post", mock_post)
    
    try:
        res = await override_test_guard._run_summary_cascade("test text", None)
        assert res == "Gemini summary text"
    finally:
        settings.MODAL_API_TOKEN = orig_token
        settings.GROQ_API_KEY = orig_groq
        settings.GEMINI_API_KEY = orig_gemini
        settings.COMPUTE_PROVIDER = orig_provider

@pytest.mark.asyncio
async def test_summarise_overall_flow(monkeypatch, override_test_guard):
    cascade = override_test_guard
    
    # Mock summary and tag calls
    cascade._run_summary_cascade = mock.AsyncMock(return_value="<think>think</think>Final summary output")
    cascade._generate_tags_llm = mock.AsyncMock(return_value=["tag1", "TAG2", "  tag3  "])
    
    res = await cascade.summarise("test text")
    assert res["summary"] == "Final summary output" # verified that thinking was stripped!
    assert res["tags"] == ["tag1", "tag2", "tag3"]
