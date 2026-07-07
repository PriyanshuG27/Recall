import pytest
import unittest.mock as mock
from typing import Set

from backend.config import settings
from backend.services.http_client import get_http_client
from backend.services.ai_cascade.providers.base import ProviderCapability
from backend.services.ai_cascade.providers.groq import GroqProvider
from backend.services.ai_cascade.providers.gemini import GeminiProvider
from backend.services.ai_cascade.providers.openrouter import OpenRouterProvider
from backend.services.ai_cascade.providers.nvidia import NvidiaProvider
from backend.services.ai_cascade.providers.modal import ModalProvider
from backend.services.ai_cascade.providers.cerebras import CerebrasProvider

# -------------------------------------------------------------------------
# 1. Instantiation and Capabilities Verification
# -------------------------------------------------------------------------

def test_provider_instantiation():
    groq = GroqProvider()
    assert groq.provider_name == "groq"
    assert ProviderCapability.CHAT_COMPLETION in groq.supported_capabilities
    assert ProviderCapability.TRANSCRIPTION in groq.supported_capabilities
    assert ProviderCapability.VISION not in groq.supported_capabilities

    gemini = GeminiProvider()
    assert gemini.provider_name == "gemini"
    assert ProviderCapability.CHAT_COMPLETION in gemini.supported_capabilities
    assert ProviderCapability.TRANSCRIPTION in gemini.supported_capabilities
    assert ProviderCapability.VISION in gemini.supported_capabilities

    openrouter = OpenRouterProvider()
    assert openrouter.provider_name == "openrouter"
    assert ProviderCapability.CHAT_COMPLETION in openrouter.supported_capabilities
    assert ProviderCapability.TRANSCRIPTION not in openrouter.supported_capabilities

    nvidia = NvidiaProvider()
    assert nvidia.provider_name == "nvidia"
    assert ProviderCapability.CHAT_COMPLETION in nvidia.supported_capabilities
    assert ProviderCapability.TRANSCRIPTION not in nvidia.supported_capabilities

    modal = ModalProvider()
    assert modal.provider_name == "modal"
    assert ProviderCapability.CHAT_COMPLETION in modal.supported_capabilities
    assert ProviderCapability.TRANSCRIPTION in modal.supported_capabilities

    cerebras = CerebrasProvider()
    assert cerebras.provider_name == "cerebras"
    assert ProviderCapability.CHAT_COMPLETION in cerebras.supported_capabilities
    assert ProviderCapability.TRANSCRIPTION not in cerebras.supported_capabilities


# -------------------------------------------------------------------------
# 2. Key Presence Verification (Returns None if Key is Missing)
# -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_providers_no_keys(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", None)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", None)
    monkeypatch.setattr(settings, "NVIDIA_API_KEY", None)
    monkeypatch.setattr(settings, "MODAL_API_TOKEN", None)
    monkeypatch.setattr(settings, "CEREBRAS_API_KEY", None)

    messages = [{"role": "user", "content": "Hello"}]

    assert await GroqProvider().chat_completion(messages, 0.7, 5.0) is None
    assert await GroqProvider().transcribe(b"data", "mp3", 5.0) is None

    assert await GeminiProvider().chat_completion(messages, 0.7, 5.0) is None
    assert await GeminiProvider().transcribe(b"data", "mp3", 5.0) is None
    assert await GeminiProvider().caption_image(b"data", "image/png", 5.0) is None

    assert await OpenRouterProvider().chat_completion(messages, 0.7, 5.0) is None
    assert await NvidiaProvider().chat_completion(messages, 0.7, 5.0) is None
    assert await ModalProvider().chat_completion(messages, 0.7, 5.0) is None
    assert await ModalProvider().transcribe(b"data", "mp3", 5.0) is None
    assert await CerebrasProvider().chat_completion(messages, 0.7, 5.0) is None


# -------------------------------------------------------------------------
# 3. Groq Adapter Tests
# -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_groq_chat_completion_success(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-groq-key")

    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json = mock.Mock(return_value={
        "choices": [{"message": {"content": "Hello from Groq"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    })

    async def mock_post(*args, **kwargs):
        return mock_resp

    monkeypatch.setattr("httpx.AsyncClient.post", mock_post)

    provider = GroqProvider()
    response = await provider.chat_completion(
        messages=[{"role": "user", "content": "Hi"}],
        temperature=0.5,
        timeout=10.0
    )
    assert response == "Hello from Groq"


@pytest.mark.asyncio
async def test_groq_chat_completion_think_block_cutoff_fallback(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-groq-key")

    # First model (e.g. Qwen) returns cutoff think block
    mock_resp_cutoff = mock.Mock()
    mock_resp_cutoff.status_code = 200
    mock_resp_cutoff.json = mock.Mock(return_value={
        "choices": [{"message": {"content": "<think>Thinking... but cutoff"}}]
    })

    # Second model returns clean response
    mock_resp_success = mock.Mock()
    mock_resp_success.status_code = 200
    mock_resp_success.json = mock.Mock(return_value={
        "choices": [{"message": {"content": "Clean response"}}]
    })

    responses = [mock_resp_cutoff, mock_resp_success]
    call_count = 0

    async def mock_post(*args, **kwargs):
        nonlocal call_count
        res = responses[call_count]
        call_count += 1
        return res

    monkeypatch.setattr("httpx.AsyncClient.post", mock_post)

    provider = GroqProvider()
    response = await provider.chat_completion(
        messages=[{"role": "user", "content": "Hi"}],
        temperature=0.5,
        timeout=10.0
    )
    assert response == "Clean response"
    assert call_count == 2


@pytest.mark.asyncio
async def test_groq_transcribe_success(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-groq-key")

    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json = mock.Mock(return_value={"text": "Transcription result"})

    async def mock_post(*args, **kwargs):
        return mock_resp

    monkeypatch.setattr("httpx.AsyncClient.post", mock_post)

    provider = GroqProvider()
    result = await provider.transcribe(b"audio-bytes", "mp3", 10.0)
    assert result == "Transcription result"


# -------------------------------------------------------------------------
# 4. Gemini Adapter Tests
# -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gemini_chat_completion_success(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-gemini-key")

    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json = mock.Mock(return_value={
        "candidates": [{"content": {"parts": [{"text": "Hello from Gemini"}]}}],
        "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 5, "totalTokenCount": 10}
    })

    async def mock_post(*args, **kwargs):
        return mock_resp

    monkeypatch.setattr("httpx.AsyncClient.post", mock_post)

    provider = GeminiProvider()
    response = await provider.chat_completion(
        messages=[{"role": "user", "content": "Hi"}],
        temperature=0.5,
        timeout=10.0
    )
    assert response == "Hello from Gemini"


@pytest.mark.asyncio
async def test_gemini_safety_block_defensive(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-gemini-key")

    # Blocked by safety filter returning empty candidates
    mock_resp_blocked = mock.Mock()
    mock_resp_blocked.status_code = 200
    mock_resp_blocked.json = mock.Mock(return_value={"candidates": []})

    async def mock_post(*args, **kwargs):
        return mock_resp_blocked

    monkeypatch.setattr("httpx.AsyncClient.post", mock_post)

    provider = GeminiProvider()
    response = await provider.chat_completion(
        messages=[{"role": "user", "content": "Blocked message"}],
        temperature=0.5,
        timeout=10.0
    )
    assert response is None  # Should return None safely without raising KeyError


@pytest.mark.asyncio
async def test_gemini_transcribe_success(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-gemini-key")

    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json = mock.Mock(return_value={
        "candidates": [{"content": {"parts": [{"text": "Transcribed by Gemini"}]}}]
    })

    async def mock_post(*args, **kwargs):
        return mock_resp

    monkeypatch.setattr("httpx.AsyncClient.post", mock_post)

    provider = GeminiProvider()
    result = await provider.transcribe(b"audio-bytes", "wav", 10.0)
    assert result == "Transcribed by Gemini"


@pytest.mark.asyncio
async def test_gemini_caption_image_success(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-gemini-key")

    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json = mock.Mock(return_value={
        "candidates": [{"content": {"parts": [{"text": "A beautiful view of mountains"}]}}]
    })

    async def mock_post(*args, **kwargs):
        return mock_resp

    monkeypatch.setattr("httpx.AsyncClient.post", mock_post)

    provider = GeminiProvider()
    result = await provider.caption_image(b"image-bytes", "image/png", 10.0)
    assert result == "A beautiful view of mountains"


# -------------------------------------------------------------------------
# 5. OpenRouter Adapter Tests
# -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_openrouter_success(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "test-openrouter-key")

    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json = mock.Mock(return_value={
        "choices": [{"message": {"content": "Hello from OpenRouter"}}]
    })

    async def mock_post(*args, **kwargs):
        return mock_resp

    monkeypatch.setattr("httpx.AsyncClient.post", mock_post)

    provider = OpenRouterProvider()
    response = await provider.chat_completion(
        messages=[{"role": "user", "content": "Hi"}],
        temperature=0.5,
        timeout=10.0
    )
    assert response == "Hello from OpenRouter"


# -------------------------------------------------------------------------
# 6. Nvidia NIM Adapter Tests
# -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_nvidia_success(monkeypatch):
    monkeypatch.setattr(settings, "NVIDIA_API_KEY", "test-nvidia-key")

    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json = mock.Mock(return_value={
        "choices": [{"message": {"content": "Hello from Nvidia"}}],
    })

    async def mock_post(*args, **kwargs):
        return mock_resp

    monkeypatch.setattr("httpx.AsyncClient.post", mock_post)

    provider = NvidiaProvider()
    response = await provider.chat_completion(
        messages=[{"role": "user", "content": "Hi"}],
        temperature=0.5,
        timeout=10.0
    )
    assert response == "Hello from Nvidia"


# -------------------------------------------------------------------------
# 7. Modal Adapter Tests
# -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_modal_summary_success(monkeypatch):
    monkeypatch.setattr(settings, "MODAL_API_TOKEN", "test-modal-token")
    monkeypatch.setattr(settings, "MODAL_SUMMARY_URL", "https://modal.run/summarize")

    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json = mock.Mock(return_value={"summary": "Summary output"})

    async def mock_post(*args, **kwargs):
        return mock_resp

    monkeypatch.setattr("httpx.AsyncClient.post", mock_post)

    provider = ModalProvider()
    result = await provider.chat_completion(
        messages=[{"role": "user", "content": "text to summarize"}],
        temperature=0.5,
        timeout=10.0,
        model="summary"
    )
    assert result == "Summary output"


@pytest.mark.asyncio
async def test_modal_tags_success(monkeypatch):
    monkeypatch.setattr(settings, "MODAL_API_TOKEN", "test-modal-token")
    monkeypatch.setattr(settings, "MODAL_TAGS_URL", "https://modal.run/generate-tags")

    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json = mock.Mock(return_value={"tags_raw": "tag1, tag2"})

    async def mock_post(*args, **kwargs):
        return mock_resp

    monkeypatch.setattr("httpx.AsyncClient.post", mock_post)

    provider = ModalProvider()
    result = await provider.chat_completion(
        messages=[
            {"role": "system", "content": "Context info"},
            {"role": "user", "content": "Generate tags"}
        ],
        temperature=0.5,
        timeout=10.0,
        model="tags"
    )
    assert result == "tag1, tag2"


@pytest.mark.asyncio
async def test_modal_rag_success(monkeypatch):
    monkeypatch.setattr(settings, "MODAL_API_TOKEN", "test-modal-token")
    monkeypatch.setattr(settings, "MODAL_RAG_URL", "https://modal.run/rag")

    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json = mock.Mock(return_value={"answer": "RAG response"})

    async def mock_post(*args, **kwargs):
        return mock_resp

    monkeypatch.setattr("httpx.AsyncClient.post", mock_post)

    provider = ModalProvider()
    result = await provider.chat_completion(
        messages=[{"role": "user", "content": "Question"}],
        temperature=0.5,
        timeout=10.0,
        model="rag"
    )
    assert result == "RAG response"


@pytest.mark.asyncio
async def test_modal_transcribe_success(monkeypatch):
    monkeypatch.setattr(settings, "MODAL_API_TOKEN", "test-modal-token")
    monkeypatch.setattr(settings, "MODAL_TRANSCRIBE_URL", "https://modal.run/transcribe")

    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json = mock.Mock(return_value={"transcript": "Modal transcript"})

    async def mock_post(*args, **kwargs):
        return mock_resp

    monkeypatch.setattr("httpx.AsyncClient.post", mock_post)

    provider = ModalProvider()
    result = await provider.transcribe(b"audio-bytes", "wav", 10.0)
    assert result == "Modal transcript"


# -------------------------------------------------------------------------
# 8. Cerebras Adapter Tests
# -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cerebras_success(monkeypatch):
    monkeypatch.setattr(settings, "CEREBRAS_API_KEY", "test-cerebras-key")

    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json = mock.Mock(return_value={
        "choices": [{"message": {"content": "Hello from Cerebras"}}],
    })

    async def mock_post(*args, **kwargs):
        return mock_resp

    monkeypatch.setattr("httpx.AsyncClient.post", mock_post)

    provider = CerebrasProvider()
    response = await provider.chat_completion(
        messages=[{"role": "user", "content": "Hi"}],
        temperature=0.5,
        timeout=10.0
    )
    assert response == "Hello from Cerebras"
