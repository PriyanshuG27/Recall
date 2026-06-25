import pytest
import time
import json
from datetime import datetime, timezone
import unittest.mock as mock
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.ai_cascade import AICascade
from backend.middleware.twa_auth import generate_jwt, UserContext
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

# --- UNIT TESTS FOR TAG EXTRACTION & NORMALISATION ---

def test_parse_tags_response_valid():
    """Verify that valid JSON list of tags is parsed correctly."""
    cascade = AICascade()
    tags = cascade.parse_tags_response('["python", "machine learning"]')
    assert tags == ["python", "machine learning"]

def test_parse_tags_response_markdown():
    """Verify that JSON enclosed in markdown code fences is parsed correctly."""
    cascade = AICascade()
    tags = cascade.parse_tags_response('```json\n["python", "rust"]\n```')
    assert tags == ["python", "rust"]
    
    tags_no_lang = cascade.parse_tags_response('```\n["c++", "go"]\n```')
    assert tags_no_lang == ["c++", "go"]

def test_parse_tags_response_invalid_json():
    """Verify that invalid JSON response defaults to empty array without crashing."""
    cascade = AICascade()
    # Invalid JSON syntax
    assert cascade.parse_tags_response('["python", "rust"') == []
    # Not a list
    assert cascade.parse_tags_response('{"tags": ["python"]}') == []
    # Arbitrary text
    assert cascade.parse_tags_response('Here are the tags: python, machine learning') == []
    # Empty string
    assert cascade.parse_tags_response('') == []

def test_tag_normalization():
    """Verify tag values are lowercased, stripped, and capped at 5 tags."""
    cascade = AICascade()
    input_tags = [" Python ", "Machine Learning", "   ", "RUST", "AI", "science", "extra1", "extra2"]
    normalized = cascade._normalize_tags(input_tags)
    # Output: lowercase, strip, remove empty, cap at 5
    assert normalized == ["python", "machine learning", "rust", "ai", "science"]
    assert len(normalized) == 5

# --- INTEGRATION & API ENDPOINT TESTS ---

class RecordingCursor:
    def __init__(self, total_count=0, rows=None):
        self.executed = []
        self.total_count = total_count
        self.rows = rows or []
        self.rowcount = 0
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
        
    async def execute(self, query, params=None):
        self.executed.append((query, params))
        if "INSERT INTO" in query.upper():
            self.rowcount = 1
        
    async def fetchone(self):
        last_query = self.executed[-1][0].lower() if self.executed else ""
        if "users" in last_query:
            # Mock user context lookup
            return (42, "123456789")
        if "insert into items" in last_query:
            # Mock inserted item returning id and created_at
            return (123, datetime.now(timezone.utc))
        return (self.total_count,)
        
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

def test_get_tags_endpoint(client, override_db):
    """GET /api/tags returns tag counts sorted by frequency desc."""
    global current_cursor
    
    # Mock tags unnested frequency query return
    mock_rows = [
        ("python", 12),
        ("machine learning", 8),
        ("research", 6),
    ]
    current_cursor = RecordingCursor(rows=mock_rows)
    
    token = get_auth_token()
    response = client.get("/api/tags", cookies={"recall_session": token})
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert data[0] == {"tag": "python", "count": 12}
    assert data[1] == {"tag": "machine learning", "count": 8}
    assert data[2] == {"tag": "research", "count": 6}

    # Verify query structure
    query, params = current_cursor.executed[1]
    assert "SELECT DISTINCT unnest(tags)" in query
    assert "WHERE user_id = %s" in query
    assert "ORDER BY count DESC" in query
    assert "LIMIT 50" in query
    assert params == (42,)

def test_get_items_filtered_by_tag(client, override_db):
    """GET /api/items?tag=python filters database query by tag."""
    global current_cursor
    
    now = datetime.now(timezone.utc)
    mock_rows = [
        (10, "Title 10", "Summary 10", "url", "https://example.com/10", ["python", "ai"], now),
    ]
    current_cursor = RecordingCursor(total_count=1, rows=mock_rows)
    
    token = get_auth_token()
    response = client.get("/api/items?tag=python", cookies={"recall_session": token})
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["tags"] == ["python", "ai"]

    # Verify query includes tag condition
    count_query, count_params = current_cursor.executed[1]
    assert "%s = ANY(tags)" in count_query
    assert count_params == (42, "python")

# --- TELEGRAM WEBHOOK /TAGS BOT COMMAND TEST ---

def test_telegram_tags_command(client, override_db):
    """Telegram webhook receives /tags and returns formatted counts list."""
    global current_cursor
    
    mock_rows = [
        ("machine learning", 12),
        ("python", 8),
        ("research", 6),
    ]
    current_cursor = RecordingCursor(rows=mock_rows)
    
    webhook_payload = {
        "update_id": 9999,
        "message": {
            "chat": {"id": 123456789},
            "text": "/tags",
            "date": 1441645532
        }
    }
    
    # Mocking Upstash Redis and send_telegram_ack so we don't make outbound network calls
    with mock.patch("backend.routes.webhook.send_telegram_ack") as mock_ack, \
         mock.patch("backend.routes.webhook.run_upstash_command", return_value={}) as mock_redis, \
         mock.patch("backend.routes.webhook.check_rate_limit", return_value=None):
        
        response = client.post("/webhook", json=webhook_payload)
        assert response.status_code == 200
        
        # Give background tasks time to execute since FastAPI runs them in a background worker thread
        # In test client context, they execute synchronously at endpoint completion, but we still verify
        mock_ack.assert_called_once()
        chat_id, reply_text = mock_ack.call_args[0]
        assert chat_id == "123456789"
        assert "Your top tags" in reply_text
        assert "1. machine learning (12)" in reply_text
        assert "2. python (8)" in reply_text
        assert "3. research (6)" in reply_text

def test_create_item_with_autotags(client, override_db):
    """POST /api/items calls AICascade and saves item with normalized tags."""
    global current_cursor
    current_cursor = RecordingCursor()
    
    token = get_auth_token()
    payload = {
        "url": "https://fastapi.tiangolo.com",
        "title": "FastAPI Web Framework"
    }
    
    mock_ai_response = {
        "summary": "FastAPI is a modern web framework.",
        "tags": ["Python", "fastapi", "  ", "WEB", "api", "framework", "extra"]
    }
    
    with mock.patch("backend.services.ai_cascade.AICascade.summarise", return_value=mock_ai_response) as mock_summarise, \
         mock.patch("backend.services.search_service.embed_text", return_value=[0.1]*384):
        
        response = client.post("/api/items", json=payload, cookies={"recall_session": token})
        assert response.status_code == 201
        
        data = response.json()
        assert data["id"] == 123
        assert data["summary"] == "FastAPI is a modern web framework."
        # Tags must be lowercased, stripped of spaces, and sliced to max 5
        assert data["tags"] == ["python", "fastapi", "web", "api", "framework"]
        
        mock_summarise.assert_called_once_with("URL: https://fastapi.tiangolo.com\nTitle: FastAPI Web Framework")
        
        # Verify cursor execution contains tags
        assert len(current_cursor.executed) == 2
        query, params = current_cursor.executed[1]
        assert "INSERT INTO items" in query
        assert params[1] == "https://fastapi.tiangolo.com"
        assert params[6] == ["python", "fastapi", "web", "api", "framework"]

