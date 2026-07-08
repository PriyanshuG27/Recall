import pytest
import asyncio
import unittest.mock as mock
from backend.config import settings
from backend.services.reranker import FastEmbedReranker, BaseReranker

class MockCrossEncoder:
    def __init__(self, model_name=None):
        self.model_name = model_name
        self.called_rerank = []

    def rerank(self, query, passages):
        self.called_rerank.append((query, passages))
        # Return high score for passages containing 'target', low otherwise
        return [10.0 if "target" in p.lower() else -5.0 for p in passages]


def test_base_reranker_interface():
    # BaseReranker cannot be instantiated directly or lacks abstract method implementation
    with pytest.raises(TypeError):
        BaseReranker()


@pytest.mark.asyncio
async def test_reranker_passage_hierarchy():
    reranker = FastEmbedReranker()
    mock_encoder = MockCrossEncoder()
    reranker._model = mock_encoder

    # Test doc list with different hierarchy layers
    docs = [
        {"id": 1, "matched_chunk_text": "This is target chunk text"},
        {"id": 2, "chunk_text": "This is target chunk_text text"},
        {"id": 3, "searchable_text": "This is target searchable text"},
        {"id": 4, "title": "target", "summary": "title text"},
        {"id": 5, "raw_text": "fernet_placeholder_to_decrypt"},
    ]

    # Mock settings to enable reranker and allow mock model name
    with mock.patch.object(settings, "ENABLE_RERANKING", True), \
         mock.patch.object(settings, "RERANKER_MODEL", "mock_model"), \
         mock.patch.object(settings, "RERANK_TOP_N", 5), \
         mock.patch("backend.services.encryption.decrypt", return_value="This is target decrypted text"):
         
        results = await reranker.rerank("target query", docs)
        
        # Verify that all docs got high positive scores due to the matching 'target' keyword
        assert len(results) == 5
        for doc in results:
            assert doc["rerank_score"] == 10.0


@pytest.mark.asyncio
async def test_reranker_fallback_on_error():
    reranker = FastEmbedReranker()
    
    # Force model initialization to fail
    def failing_get_model():
        raise RuntimeError("Failed to load ONNX model")
        
    reranker._get_model = failing_get_model
    
    docs = [{"id": 1, "title": "A"}, {"id": 2, "title": "B"}]
    
    with mock.patch.object(settings, "ENABLE_RERANKING", True), \
         mock.patch.object(settings, "RERANKER_MODEL", "failing_model"), \
         mock.patch.object(settings, "RERANK_TOP_N", 2):
         
        results = await reranker.rerank("query", docs)
        
        # Should gracefully fall back to original results list limit
        assert len(results) == 2
        assert results[0]["title"] == "A"
        assert "rerank_score" not in results[0]


@pytest.mark.asyncio
async def test_reranker_timeout_graceful():
    reranker = FastEmbedReranker()
    
    # Emulate slow execution inside model.rerank
    class SlowCrossEncoder:
        def rerank(self, query, passages):
            import time
            time.sleep(3.0)  # Exceeds the 1.0s mock timeout boundary
            return [1.0] * len(passages)
            
    reranker._model = SlowCrossEncoder()
    docs = [{"id": 1, "title": "A"}, {"id": 2, "title": "B"}]
    
    with mock.patch.object(settings, "ENABLE_RERANKING", True), \
         mock.patch.object(settings, "RERANKER_MODEL", "slow_model"), \
         mock.patch.object(settings, "RERANK_TIMEOUT_SECONDS", 0.1), \
         mock.patch.object(settings, "RERANK_TOP_N", 2):
         
        results = await reranker.rerank("query", docs)
        
        # Rerank should time out and gracefully return the original candidate order
        assert len(results) == 2
        assert "rerank_score" not in results[0]


@pytest.mark.asyncio
async def test_reranker_preload_warmup():
    reranker = FastEmbedReranker()
    mock_encoder = MockCrossEncoder()
    
    with mock.patch("fastembed.rerank.cross_encoder.TextCrossEncoder", return_value=mock_encoder) as mock_cls, \
         mock.patch.object(settings, "RERANKER_MODEL", "mock_model"):
         
        reranker.preload()
        assert reranker._model is mock_encoder
        mock_cls.assert_called_once_with(model_name="mock_model")
        # Warmup dummy query should be called
        assert len(mock_encoder.called_rerank) == 1
        assert mock_encoder.called_rerank[0][0] == "warmup"
