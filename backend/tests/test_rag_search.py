import pytest
import time
from datetime import datetime, timezone
import unittest.mock as mock
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.ai_cascade import AICascade
from backend.middleware.twa_auth import generate_jwt
from backend.config import settings
from backend.db.connection import get_db

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

# --- DB & TEST CLIENT FIXTURES ---

class RecordingCursor:
    def __init__(self, rows=None):
        self.executed = []
        self.rows = rows or []
        self.rowcount = 1
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
        
    async def execute(self, query, params=None):
        self.executed.append((query, params))
        
    async def fetchone(self):
        last_query = self.executed[-1][0].lower() if self.executed else ""
        if "users" in last_query:
            return (42, "123456789")
        return None
        
    async def fetchall(self):
        return self.rows

class RecordingConnection:
    def __init__(self, cursor_inst):
        self.cursor_inst = cursor_inst
        
    def cursor(self):
        return self.cursor_inst
        
    async def commit(self):
        pass

current_cursor = None

@pytest.fixture()
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

def get_auth_token():
    payload = {
        "sub": "42",
        "chat_id": "123456789",
        "exp": int(time.time()) + 3600
    }
    return generate_jwt(payload, settings.JWT_SECRET)

# --- RAG SEARCH TESTS ---

def test_rag_skipped_on_no_sources(client, override_db):
    """POST /api/search skips RAG generation and returns answer = null if there are no sources."""
    global current_cursor
    
    # 0 mock items returned by hybrid_search
    mock_results = []
    current_cursor = RecordingCursor()
    
    token = get_auth_token()
    
    with mock.patch("backend.services.search_service.hybrid_search", return_value=mock_results) as mock_search, \
         mock.patch("backend.services.ai_cascade.AICascade.answer_question") as mock_answer_question:
         
         response = client.post("/api/search", json={"query": "fastapi"}, cookies={"recall_session": token})
         assert response.status_code == 200
         
         data = response.json()
         assert data["query"] == "fastapi"
         assert data["answer"] is None  # Skipped
         assert len(data["sources"]) == 0
         
         mock_answer_question.assert_not_called()

def test_rag_generated_on_at_least_3_sources(client, override_db):
    """POST /api/search synthesises an answer if there are >= 3 sources."""
    global current_cursor
    
    now = datetime.now(timezone.utc)
    mock_results = [
        {"id": 1, "title": "Title 1", "summary": "Summary 1", "source_type": "url", "source_url": None, "score": 0.8, "created_at": now},
        {"id": 2, "title": "Title 2", "summary": "Summary 2", "source_type": "pdf", "source_url": None, "score": 0.7, "created_at": now},
        {"id": 3, "title": "Title 3", "summary": "Summary 3", "source_type": "text", "source_url": None, "score": 0.6, "created_at": now},
    ]
    current_cursor = RecordingCursor()
    token = get_auth_token()
    
    with mock.patch("backend.services.search_service.hybrid_search", return_value=mock_results) as mock_search:
        response = client.post("/api/search", json={"query": "python"}, cookies={"recall_session": token})
        assert response.status_code == 200
        
        data = response.json()
        assert data["query"] == "python"
        assert data["answer"] == "Mock synthesised answer for query: python"
        assert len(data["sources"]) == 3

def test_rag_failure_returns_sources_without_answer(client, override_db):
    """POST /api/search returns sources list without answer (no crash) if RAG generation fails."""
    global current_cursor
    
    now = datetime.now(timezone.utc)
    mock_results = [
        {"id": 1, "title": "Title 1", "summary": "Summary 1", "source_type": "url", "source_url": None, "score": 0.8, "created_at": now},
        {"id": 2, "title": "Title 2", "summary": "Summary 2", "source_type": "pdf", "source_url": None, "score": 0.7, "created_at": now},
        {"id": 3, "title": "Title 3", "summary": "Summary 3", "source_type": "text", "source_url": None, "score": 0.6, "created_at": now},
    ]
    current_cursor = RecordingCursor()
    token = get_auth_token()
    
    # Mock answer_question throwing an exception
    with mock.patch("backend.services.search_service.hybrid_search", return_value=mock_results), \
         mock.patch("backend.services.ai_cascade.AICascade.answer_question", side_effect=Exception("LLM Timeout")):
         
        response = client.post("/api/search", json={"query": "ai"}, cookies={"recall_session": token})
        assert response.status_code == 200
        
        data = response.json()
        assert data["query"] == "ai"
        assert data["answer"] is None  # Gracefully caught and defaulted to null
        assert len(data["sources"]) == 3

@pytest.mark.anyio
async def test_token_truncation_limits_characters():
    """Verify that answer_question truncates the prompt to respect token limits (approx 12k chars)."""
    cascade = AICascade()
    
    # Extremely long summaries context
    long_summaries = ["This is a long summary. " * 500] * 5  # Total ~60,000 characters
    
    # Verify it doesn't crash and truncates long summaries correctly
    with mock.patch("backend.services.ai_cascade.executor.retry.RetryEngine.execute_with_retry", new_callable=mock.AsyncMock) as mock_retry:
        mock_retry.return_value = "Synthesised answer"
        with mock.patch("backend.services.ai_cascade.settings.ENV", "production"):
            
            cascade._force_production_llm = True
            res = await cascade.answer_question("What is AI?", long_summaries)
            assert res == "Synthesised answer"
            
            mock_retry.assert_called_once()
            called_messages = mock_retry.call_args[1]["messages"]
            called_prompt = called_messages[1]["content"]
            # Prompt must be capped to around 12,000 characters
            assert len(called_prompt) <= 12000

# --- BOT SEARCH COMMAND TESTS ---

def test_bot_search_command_with_rag(client, override_db):
    """Telegram webhook formats reply with synthesized answer if sources >= 3."""
    global current_cursor
    
    now = datetime.now(timezone.utc)
    mock_results = [
        {"id": 1, "title": "Title 1", "summary": "Summary 1", "source_type": "url", "source_url": None, "score": 0.8, "created_at": now},
        {"id": 2, "title": "Title 2", "summary": "Summary 2", "source_type": "pdf", "source_url": None, "score": 0.7, "created_at": now},
        {"id": 3, "title": "Title 3", "summary": "Summary 3", "source_type": "text", "source_url": None, "score": 0.6, "created_at": now},
    ]
    current_cursor = RecordingCursor()
    
    webhook_payload = {
        "update_id": 10001,
        "message": {
            "chat": {"id": 123456789},
            "text": "/search machine learning",
            "date": 1441645532
        }
    }
    
    with mock.patch("backend.services.search_service.hybrid_search", return_value=mock_results), \
         mock.patch("backend.routes.webhook.send_telegram_ack") as mock_ack, \
         mock.patch("backend.routes.webhook.run_upstash_command", return_value={}) as mock_redis, \
         mock.patch("backend.routes.webhook.check_rate_limit", return_value=None):
         
        response = client.post("/webhook", json=webhook_payload)
        assert response.status_code == 200
        
        mock_ack.assert_called_once()
        chat_id, reply_text = mock_ack.call_args[0]
        assert chat_id == "123456789"
        assert "Query: machine learning" in reply_text
        assert "💡 Mock synthesised answer for query: machine learning" in reply_text
        assert "Sources:" in reply_text
        assert "1. [url] Title 1" in reply_text
        assert "2. [pdf] Title 2" in reply_text
        assert "3. [text] Title 3" in reply_text

def test_bot_search_command_without_rag(client, override_db):
    """Telegram webhook formats reply without RAG answer section if sources < 3."""
    global current_cursor
    
    now = datetime.now(timezone.utc)
    mock_results = [
        {"id": 1, "title": "Title 1", "summary": "Summary 1", "source_type": "url", "source_url": None, "score": 0.8, "created_at": now},
        {"id": 2, "title": "Title 2", "summary": "Summary 2", "source_type": "pdf", "source_url": None, "score": 0.7, "created_at": now},
    ]
    current_cursor = RecordingCursor()
    
    webhook_payload = {
        "update_id": 10002,
        "message": {
            "chat": {"id": 123456789},
            "text": "/search machine learning",
            "date": 1441645532
        }
    }
    
    with mock.patch("backend.services.search_service.hybrid_search", return_value=mock_results), \
         mock.patch("backend.routes.webhook.send_telegram_ack") as mock_ack, \
         mock.patch("backend.routes.webhook.run_upstash_command", return_value={}) as mock_redis, \
         mock.patch("backend.routes.webhook.check_rate_limit", return_value=None):
         
        response = client.post("/webhook", json=webhook_payload)
        assert response.status_code == 200
        
        mock_ack.assert_called_once()
        chat_id, reply_text = mock_ack.call_args[0]
        assert chat_id == "123456789"
        assert "Query: machine learning" in reply_text
        assert "💡" not in reply_text  # RAG skipped since results count < 3
        assert "Sources:" in reply_text
        assert "1. [url] Title 1" in reply_text
        assert "2. [pdf] Title 2" in reply_text
