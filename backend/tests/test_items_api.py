import pytest
import time
import math
import unittest.mock as mock
from datetime import datetime, date, timezone
from fastapi import Depends
from fastapi.testclient import TestClient

from backend.main import app
from backend.middleware.twa_auth import get_current_user, generate_jwt, UserContext
from backend.config import settings
from backend.db.connection import get_db

# Patch environment variables
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
    def __init__(self, total_count=0, rows=None):
        self.executed = []
        self.total_count = total_count
        self.rows = rows or []
        
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

# Global/context variable to pass current cursor to mock DB dependency
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

def get_auth_token():
    payload = {
        "sub": "42",  # User ID 42
        "chat_id": "123456789",
        "exp": int(time.time()) + 3600
    }
    return generate_jwt(payload, settings.JWT_SECRET)

def test_get_items_unauthenticated(client):
    """GET /api/items without authentication cookie or header must return 401."""
    response = client.get("/api/items")
    assert response.status_code == 401

def test_get_items_basic_pagination(client):
    """GET /api/items with authentication must return paginated results and map fields correctly."""
    global current_cursor
    
    now = datetime.now(timezone.utc)
    mock_rows = [
        (10, "Title 10", "Summary 10", "url", "https://example.com/10", ["tagA", "tagB"], now),
        (9, "Title 9", "Summary 9", "text", None, ["tagA"], now),
    ]
    current_cursor = RecordingCursor(total_count=100, rows=mock_rows)
    
    token = get_auth_token()
    response = client.get("/api/items?page=2&limit=5", cookies={"recall_session": token})
    
    assert response.status_code == 200
    data = response.json()
    
    assert "items" in data
    assert data["total"] == 100
    assert data["page"] == 2
    assert data["pages"] == 20
    
    items = data["items"]
    assert len(items) == 2
    
    assert items[0]["id"] == 10
    assert items[0]["title"] == "Title 10"
    assert items[0]["summary"] == "Summary 10"
    assert items[0]["source_type"] == "url"
    assert items[0]["source_url"] == "https://example.com/10"
    assert items[0]["tags"] == ["tagA", "tagB"]
    
    # Check that raw_text and user_id are NOT present in the returned items
    for item in items:
        assert "raw_text" not in item
        assert "user_id" not in item
        
    assert len(current_cursor.executed) == 3
    
    # Executed[0] is user lookup. Executed[1] is COUNT.
    count_query, count_params = current_cursor.executed[1]
    assert "SELECT COUNT(*)" in count_query
    assert "WHERE i.user_id = %s" in count_query
    assert count_params == (42,)
    
    # Executed[2] is items query.
    items_query, items_params = current_cursor.executed[2]
    assert "SELECT i.id, i.title, i.summary" in items_query
    assert "ORDER BY i.created_at DESC" in items_query
    assert "LIMIT %s OFFSET %s" in items_query
    assert items_params == (42, 5, 5)

def test_get_items_limit_clamping_and_validation(client):
    """GET /api/items with limit > 50 must return 400 Bad Request."""
    global current_cursor
    current_cursor = RecordingCursor()
    token = get_auth_token()
    response = client.get("/api/items?limit=51", cookies={"recall_session": token})
    assert response.status_code == 400
    assert "Limit cannot exceed 50" in response.json()["detail"]

def test_get_items_filters_composition(client):
    """GET /api/items query builder dynamically appends and serializes search parameters."""
    global current_cursor
    
    current_cursor = RecordingCursor(total_count=5, rows=[])
    token = get_auth_token()
    
    response = client.get(
        "/api/items?source_type=voice&tag=rust&from_date=2026-06-01&to_date=2026-06-25",
        cookies={"recall_session": token}
    )
    assert response.status_code == 200
    
    assert len(current_cursor.executed) == 3
    # Executed[0] is user lookup. Executed[1] is COUNT.
    count_query, count_params = current_cursor.executed[1]
    
    assert "WHERE i.user_id = %s" in count_query
    assert "AND i.source_type = %s" in count_query
    assert "AND %s = ANY(i.tags)" in count_query
    assert "AND i.created_at >= %s" in count_query
    assert "AND i.created_at <= %s" in count_query
    
    expected_params = (
        42,
        "voice",
        "rust",
        date(2026, 6, 1),
        date(2026, 6, 25)
    )
    assert count_params == expected_params
    
    # Executed[2] is items query.
    items_query, items_params = current_cursor.executed[2]
    assert items_params == expected_params + (20, 0)
