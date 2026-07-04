import pytest
import unittest.mock as mock
from backend.services.search_service import embed_text, _generate_embedding_uncached, hybrid_search

@pytest.mark.asyncio
async def test_embed_text_in_test_env():
    with mock.patch("backend.config.settings.ENV", "test"):
        emb = await embed_text("quantum physics")
        assert len(emb) == 384
        assert pytest.approx(sum(x*x for x in emb)) == 1.0

@pytest.mark.asyncio
async def test_embed_text_cache_hit():
    mock_redis = mock.AsyncMock()
    mock_redis.get.return_value = '["0.1"]' + str([0.1]*383).replace('[', ', ').replace(']', '')
    
    # Force ENV to prod to test cache path
    with mock.patch("backend.config.settings.ENV", "production"), \
         mock.patch("backend.services.redis_client.redis", mock_redis):
        emb = await embed_text("cached text")
        assert len(emb) == 384

@pytest.mark.asyncio
async def test_generate_embedding_uncached_modal():
    with mock.patch("backend.config.settings.MODAL_API_TOKEN", "real_token_123"):
        mock_resp = mock.Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [0.05] * 384

        with mock.patch("httpx.AsyncClient.post", new_callable=mock.AsyncMock, return_value=mock_resp):
            emb = await _generate_embedding_uncached("modal test")
            assert len(emb) == 384

@pytest.mark.asyncio
async def test_generate_embedding_uncached_hf():
    with mock.patch("backend.config.settings.MODAL_API_TOKEN", None), \
         mock.patch("backend.config.settings.HF_TOKEN", "hf_real_token"):
        mock_resp = mock.Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [[0.05] * 384]

        with mock.patch("httpx.AsyncClient.post", new_callable=mock.AsyncMock, return_value=mock_resp):
            emb = await _generate_embedding_uncached("hf test")
            assert len(emb) == 384

@pytest.mark.asyncio
async def test_generate_embedding_uncached_gemini():
    with mock.patch("backend.config.settings.MODAL_API_TOKEN", None), \
         mock.patch("backend.config.settings.HF_TOKEN", None), \
         mock.patch("backend.config.settings.GEMINI_API_KEY", "real_gemini_key"):
        mock_resp = mock.Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"embedding": {"values": [0.05] * 384}}

        with mock.patch("httpx.AsyncClient.post", new_callable=mock.AsyncMock, return_value=mock_resp):
            emb = await _generate_embedding_uncached("gemini test")
            assert len(emb) == 384
