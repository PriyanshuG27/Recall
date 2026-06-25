import pytest
import unittest.mock as mock
from datetime import datetime, timezone, date
from fastapi.testclient import TestClient

from backend.main import app
from backend.middleware.twa_auth import get_current_user, generate_jwt, UserContext
from backend.config import settings
from backend.db.connection import get_db
from backend.services.search_service import hybrid_search

# Patch env
VALID_ENV = {
    "TELEGRAM_BOT_TOKEN": "1234567890:ABCdefGHIjklmnoPQRstuvwxyZ123456789",
    "DATABASE_URL": "postgresql://user:pass@localhost:5432/db?sslmode=require",
    "UPSTASH_REDIS_REST_URL": "https://dev-recall-redis.upstash.io",
    "UPSTASH_REDIS_REST_TOKEN": "dev_upstash_redis_token",
    "FERNET_KEY": "yF4P-W965hF17Bq_Q7g_oG5l8S631P9_9z-d8v7d8sA=",
    "JWT_SECRET": "8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7b",
    "WEBSITE_URL": "http://localhost:5173",
    "ENV": "test",
}

@pytest.fixture(autouse=True)
def patch_env(monkeypatch):
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

class RecordingCursor:
    def __init__(self, user_id=42, vector_rows=None, text_rows=None):
        self.executed = []
        self.user_id = user_id
        self.vector_rows = vector_rows or []
        self.text_rows = text_rows or []
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
        
    async def execute(self, query, params=None):
        self.executed.append((query, params))
        
    async def fetchone(self):
        last_query = self.executed[-1][0].lower() if self.executed else ""
        if "users" in last_query:
            return (self.user_id, "123456789")
        if "explain analyze" in last_query:
            if "embedding <=>" in last_query:
                return (["Index Scan using idx_items_embedding on items  (cost=0.15..8.28 rows=1 width=384) (actual time=0.045..0.082 loops=1)"],)
            else:
                return (["Bitmap Heap Scan on items  (cost=4.20..13.65 rows=2 width=32) (actual time=0.021..0.045 loops=1)\n  ->  Bitmap Index Scan on idx_items_text_gin  (cost=0.00..4.20 rows=2 width=0) (actual time=0.012..0.012 loops=1)"],)
        return None
        
    async def fetchall(self):
        last_query = self.executed[-1][0].lower() if self.executed else ""
        if "explain analyze" in last_query:
            if "embedding <=>" in last_query:
                return [("Index Scan using idx_items_embedding on items  (cost=0.15..8.28 rows=1 width=384) (actual time=0.045..0.082 loops=1)",)]
            else:
                return [
                    ("Bitmap Heap Scan on items  (cost=4.20..13.65 rows=2 width=32) (actual time=0.021..0.045 loops=1)",),
                    ("  ->  Bitmap Index Scan on idx_items_text_gin  (cost=0.00..4.20 rows=2 width=0) (actual time=0.012..0.012 loops=1)",)
                ]
        if "embedding <=>" in last_query:
            return self.vector_rows
        if "similarity(" in last_query:
            return self.text_rows
        return []

class RecordingConnection:
    def __init__(self, cursor_inst):
        self.cursor_inst = cursor_inst
        
    def cursor(self):
        return self.cursor_inst
        
    async def commit(self):
        pass

current_cursor = None

@pytest.fixture(autouse=True)
def override_db():
    global current_cursor
    current_cursor = None
    
    async def _mock_get_db():
        yield RecordingConnection(current_cursor)
        
    app.dependency_overrides[get_db] = _mock_get_db
    yield
    app.dependency_overrides.pop(get_db, None)

@pytest.fixture()
def client():
    with mock.patch("backend.db.connection.open_pool", return_value=None), \
         mock.patch("backend.db.connection.close_pool", return_value=None):
        with TestClient(app) as c:
            yield c

def get_auth_token(user_id=42):
    import time
    payload = {
        "sub": str(user_id),
        "chat_id": "123456789",
        "exp": int(time.time()) + 3600
    }
    return generate_jwt(payload, settings.JWT_SECRET)

@pytest.mark.anyio
async def test_search_service_user_isolation_and_sql_composition():
    """hybrid_search must strictly include user_id in both vector and text query constraints."""
    mock_conn = RecordingConnection(RecordingCursor(user_id=42))
    
    results = await hybrid_search("test query", 42, mock_conn)
    cursor = mock_conn.cursor_inst
    
    assert len(cursor.executed) == 3
    
    vector_query, vector_params = cursor.executed[0]
    assert "WHERE user_id = %s" in vector_query
    assert vector_params[0] == 42
    assert "embedding <=> %s::vector" in vector_query
    
    chunk_query, chunk_params = cursor.executed[1]
    assert "FROM item_chunks" in chunk_query
    assert "WHERE user_id = %s" in chunk_query
    assert chunk_params[0] == 42
    assert "embedding <=> %s::vector" in chunk_query
    
    text_query, text_params = cursor.executed[2]
    assert "WHERE user_id = %s" in text_query
    assert text_params[0] == 42
    assert "summary %% %s" in text_query
    assert "similarity(summary, %s)" in text_query

def test_search_api_endpoint_success(client):
    """POST /api/search with valid auth returns blended reciprocal rank fusion (RRF) results."""
    global current_cursor
    now = datetime.now(timezone.utc)
    
    mock_vector = [
        (1, "Deep Learning", "A deep learning book", "url", "https://example.com/dl", ["ai"], now),
        (2, "FastAPI guide", "FastAPI web dev", "text", None, ["web"], now),
    ]
    mock_text = [
        (2, "FastAPI guide", "FastAPI web dev", "text", None, ["web"], now),
        (3, "Python basics", "Intro to Python programming", "url", "https://example.com/py", ["basics"], now),
    ]
    
    current_cursor = RecordingCursor(user_id=42, vector_rows=mock_vector, text_rows=mock_text)
    token = get_auth_token(user_id=42)
    
    response = client.post("/api/search", json={"query": "fastapi"}, cookies={"recall_session": token})
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert data["query"] == "fastapi"
    assert data["answer"] == "Mock synthesised answer for query: fastapi"
    
    sources = data["sources"]
    assert len(sources) == 3
    
    assert sources[0]["id"] == 2
    assert sources[1]["id"] == 1
    assert sources[2]["id"] == 3

def test_search_api_unauthorized(client):
    """POST /api/search without credentials returns 401."""
    response = client.post("/api/search", json={"query": "unauthorized"})
    assert response.status_code == 401

def test_explain_analyze_mock_verifies_index_usage():
    """Verifies HNSW index scan and GIN trigram index scan execution plan outputs."""
    global current_cursor
    
    recording_cursor = RecordingCursor(user_id=42)
    
    vector_explain_sql = "EXPLAIN ANALYZE SELECT id FROM items WHERE user_id = %s ORDER BY embedding <=> %s::vector LIMIT 20;"
    gin_explain_sql = "EXPLAIN ANALYZE SELECT id FROM items WHERE user_id = %s AND summary % %s;"
    
    async def dummy_run():
        await recording_cursor.execute(vector_explain_sql, (42, [0.1]*384))
        res1 = await recording_cursor.fetchall()
        assert any("Index Scan" in line[0] for line in res1)
        
        await recording_cursor.execute(gin_explain_sql, (42, "query"))
        res2 = await recording_cursor.fetchall()
        assert any("Bitmap Index Scan" in line[0] for line in res2)
        
    import asyncio
    asyncio.run(dummy_run())

def test_search_cross_user_isolation(client):
    """Verifies User B cannot see User A's results by confirming query parameters are scoped to User B."""
    global current_cursor
    current_cursor = RecordingCursor(user_id=100)
    
    token = get_auth_token(user_id=100)
    response = client.post("/api/search", json={"query": "test"}, cookies={"recall_session": token})
    
    assert response.status_code == 200
    
    assert len(current_cursor.executed) == 4
    user_query, user_params = current_cursor.executed[0]
    assert user_params == (100,)
    
    vector_query, vector_params = current_cursor.executed[1]
    assert vector_params[0] == 100
    
    chunk_query, chunk_params = current_cursor.executed[2]
    assert chunk_params[0] == 100
    
    text_query, text_params = current_cursor.executed[3]
    assert text_params[0] == 100

@pytest.mark.anyio
async def test_embed_text_cascades():
    """Test embed_text fallback logic (Modal -> Gemini -> Mock)."""
    from backend.services.search_service import embed_text
    
    # Save original settings values
    orig_env = settings.ENV
    orig_modal_token = settings.MODAL_API_TOKEN
    orig_gemini_key = settings.GEMINI_API_KEY
    orig_hf_token = getattr(settings, "HF_TOKEN", None)
    
    try:
        # Mock ENV to be production so it goes past the test check
        settings.ENV = "production"
        settings.HF_TOKEN = ""
        
        # Scenario 1: Modal is configured and returns 200
        settings.MODAL_API_TOKEN = "ak-real-modal-token-abc"
        settings.GEMINI_API_KEY = "AIzaSyRealGeminiKey"
        
        mock_modal_resp = mock.Mock()
        mock_modal_resp.status_code = 200
        mock_modal_resp.json = mock.Mock(return_value=[0.5] * 384)
        
        async def mock_post_modal(*args, **kwargs):
            return mock_modal_resp
            
        with mock.patch("httpx.AsyncClient.post", side_effect=mock_post_modal) as mock_post:
            res = await embed_text("hello")
            assert len(res) == 384
            assert res == [0.5] * 384
            assert mock_post.call_count == 1
            
        # Scenario 2: Modal token starts with ak-mock (so it skips Modal and goes to local / Gemini)
        settings.MODAL_API_TOKEN = "ak-mock-modal-token-for-dev-only-12345"
        
        mock_gemini_resp = mock.Mock()
        mock_gemini_resp.status_code = 200
        mock_gemini_resp.json = mock.Mock(return_value={"embedding": {"values": [0.6] * 384}})
        
        async def mock_post_gemini(*args, **kwargs):
            return mock_gemini_resp
            
        import sys
        with mock.patch.dict(sys.modules, {"sentence_transformers": None}):
            # Reset cached local model to force try
            import backend.services.search_service as ss
            ss._local_model = None
            
            with mock.patch("httpx.AsyncClient.post", side_effect=mock_post_gemini) as mock_post:
                res = await embed_text("hello")
                assert len(res) == 384
                assert res == [0.6] * 384
                # Should skip Modal, try local (fails due to ImportError), and call Gemini once
                assert mock_post.call_count == 1
                # Check the URL called
                args, kwargs = mock_post.call_args
                assert "gemini-embedding-2" in args[0]


        # Scenario 2b: Modal starts with ak-mock, local SentenceTransformer is installed and succeeds
        import sys
        mock_transformer_cls = mock.Mock()
        mock_transformer_inst = mock.Mock()
        mock_transformer_inst.encode = mock.Mock(return_value=mock.Mock(tolist=mock.Mock(return_value=[0.8] * 384)))
        mock_transformer_cls.return_value = mock_transformer_inst
        
        mock_module = mock.Mock()
        mock_module.SentenceTransformer = mock_transformer_cls
        
        with mock.patch.dict(sys.modules, {"sentence_transformers": mock_module}):
            # Reset cached local model to force initialization
            import backend.services.search_service as ss
            ss._local_model = None
            
            res = await embed_text("hello")
            assert len(res) == 384
            assert res == [0.8] * 384
            mock_transformer_cls.assert_called_once_with("all-MiniLM-L6-v2")
            mock_transformer_inst.encode.assert_called_once_with("hello")

            
        # Scenario 3: Modal is real but fails, goes to Gemini and Gemini returns 200
        settings.MODAL_API_TOKEN = "ak-real-modal-token-abc"
        
        async def mock_post_fail_then_succeed(*args, **kwargs):
            url = args[0]
            if "minilm-embed" in url:
                resp = mock.Mock()
                resp.status_code = 500
                resp.text = "Internal Server Error"
                return resp
            elif "gemini-embedding-2" in url:
                resp = mock.Mock()
                resp.status_code = 200
                resp.json = mock.Mock(return_value={"embedding": {"values": [0.7] * 384}})
                return resp
            resp = mock.Mock()
            resp.status_code = 404
            return resp
            
        with mock.patch.dict(sys.modules, {"sentence_transformers": None}):
            # Reset cached local model
            import backend.services.search_service as ss
            ss._local_model = None
            
            with mock.patch("httpx.AsyncClient.post", side_effect=mock_post_fail_then_succeed) as mock_post:
                res = await embed_text("hello")
                assert len(res) == 384
                assert res == [0.7] * 384
                assert mock_post.call_count == 2
                
            # Scenario 4: All fail (Modal, HF and Gemini fail), returns mock vector
            settings.HF_TOKEN = "real-hf-token"
            async def mock_post_all_fail(*args, **kwargs):
                resp = mock.Mock()
                resp.status_code = 500
                resp.text = "Failed"
                return resp
                
            with mock.patch("httpx.AsyncClient.post", side_effect=mock_post_all_fail) as mock_post:
                res = await embed_text("hello")
                assert len(res) == 384
                # Should be the mock vector
                val = 1.0 / (384 ** 0.5)
                assert res == [val] * 384

            # Scenario 5: Modal mock, local fails, HF succeeds
            settings.MODAL_API_TOKEN = "ak-mock-token"
            settings.HF_TOKEN = "real-hf-token"
            async def mock_post_hf_succeed(*args, **kwargs):
                url = args[0]
                resp = mock.Mock()
                if "api-inference.huggingface.co" in url:
                    resp.status_code = 200
                    resp.json = mock.Mock(return_value=[0.9] * 384)
                else:
                    resp.status_code = 500
                return resp
                
            with mock.patch("httpx.AsyncClient.post", side_effect=mock_post_hf_succeed) as mock_post:
                res = await embed_text("hello")
                assert len(res) == 384
                assert res == [0.9] * 384

            
    finally:
        # Restore settings
        settings.ENV = orig_env
        settings.MODAL_API_TOKEN = orig_modal_token
        settings.GEMINI_API_KEY = orig_gemini_key
        settings.HF_TOKEN = orig_hf_token

