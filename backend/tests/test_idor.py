import pytest
import time
import unittest.mock as mock
from datetime import datetime, timezone
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
    def __init__(self, user_id=42, delete_returning_row=None):
        self.executed = []
        self.user_id = user_id
        self.delete_returning_row = delete_returning_row
        
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
        if "delete from items" in last_query:
            return self.delete_returning_row
        return None

class RecordingConnection:
    def __init__(self, cursor_inst):
        self.cursor_inst = cursor_inst
        self.committed = False
        self.rolled_back = False
        
    def cursor(self):
        return self.cursor_inst
        
    async def commit(self):
        self.committed = True
        
    async def rollback(self):
        self.rolled_back = True

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
    payload = {
        "sub": str(user_id),
        "chat_id": "123456789",
        "exp": int(time.time()) + 3600
    }
    return generate_jwt(payload, settings.JWT_SECRET)

def test_delete_own_item_success(client):
    """User A deletes their own item -> returns 204, database transaction is committed."""
    global current_cursor
    current_cursor = RecordingCursor(user_id=42, delete_returning_row=(5, "url"))
    
    token = get_auth_token(user_id=42)
    response = client.delete("/api/items/5", cookies={"recall_session": token})
    
    assert response.status_code == 204
    assert len(current_cursor.executed) == 4
    
    q_query, q_params = current_cursor.executed[1]
    assert "DELETE FROM quizzes" in q_query
    assert q_params == (5, 42)
    
    chunk_query, chunk_params = current_cursor.executed[2]
    assert "DELETE FROM item_chunks" in chunk_query
    assert chunk_params == (5, 42)
    
    item_query, item_params = current_cursor.executed[3]
    assert "DELETE FROM items" in item_query
    assert "user_id = %s" in item_query
    assert item_params == (5, 42)

def test_delete_other_user_item_idor_prevented(client):
    """User B attempts to delete User A's item -> returns 404, not 204."""
    global current_cursor
    current_cursor = RecordingCursor(user_id=100, delete_returning_row=None)
    
    token = get_auth_token(user_id=100)
    response = client.delete("/api/items/5", cookies={"recall_session": token})
    
    assert response.status_code == 404
    assert response.json()["detail"] == "Item not found"
    assert len(current_cursor.executed) == 4
    
    chunk_query, chunk_params = current_cursor.executed[2]
    assert "DELETE FROM item_chunks" in chunk_query
    assert chunk_params == (5, 100)
    
    item_query, item_params = current_cursor.executed[3]
    assert "DELETE FROM items" in item_query
    assert "user_id = %s" in item_query
    assert item_params == (5, 100)
