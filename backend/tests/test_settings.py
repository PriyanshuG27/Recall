import time
import pytest
import unittest.mock as mock
from fastapi.testclient import TestClient

# Mock environment variables
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

from backend.main import app
from backend.middleware.twa_auth import get_current_user, generate_jwt, UserContext
from backend.config import settings

class MockCursor:
    def __init__(self):
        self.query_history = []
        self.mock_timezone_offset = 300 # 5 hours in minutes

    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
        
    async def execute(self, query, params=None):
        self.query_history.append((query, params))
        if "UPDATE users" in query:
            self.mock_timezone_offset = params[0]
        
    async def fetchone(self):
        last_query = self.query_history[-1][0].upper()
        if "SELECT TIMEZONE_OFFSET, STREAK_COUNT, GOOGLE_REFRESH_TOKEN FROM USERS" in last_query:
            return (self.mock_timezone_offset, 5, "mock_google_token")
        if "SELECT COUNT(*) FROM ITEMS" in last_query:
            return (10,)
        if "SELECT COUNT(*) FROM QUIZZES" in last_query:
            return (4,)
        if "SELECT TIMEZONE_OFFSET FROM USERS" in last_query:
            return (self.mock_timezone_offset,)
        if "SELECT ID, TELEGRAM_CHAT_ID FROM USERS" in last_query:
            return (42, "123456789")
        if "SELECT ID FROM USERS" in last_query:
            return (42,)
        return None

class MockConnection:
    def __init__(self):
        self._cursor = MockCursor()

    def cursor(self):
        return self._cursor
        
    async def commit(self):
        pass

@pytest.fixture(autouse=True)
def override_db(monkeypatch):
    conn = MockConnection()
    from backend.db.connection import get_db
    async def _mock_get_db():
        yield conn
    app.dependency_overrides[get_db] = _mock_get_db
    monkeypatch.setattr("backend.routes.api.get_db", _mock_get_db)
    yield conn
    app.dependency_overrides.pop(get_db, None)

@pytest.fixture()
def client():
    with mock.patch("backend.db.connection.open_pool", return_value=None), \
         mock.patch("backend.db.connection.close_pool", return_value=None):
        with TestClient(app) as c:
            yield c

@pytest.fixture()
def auth_cookie():
    payload = {
        "sub": "42",
        "chat_id": "123456789",
        "exp": int(time.time()) + 3600
    }
    return {"recall_session": generate_jwt(payload, settings.JWT_SECRET)}

def test_get_settings(client, override_db, auth_cookie):
    response = client.get("/api/me", cookies=auth_cookie)
    assert response.status_code == 200
    data = response.json()
    assert data["timezone_offset"] == 5
    assert data["streak_count"] == 5
    assert data["drive_connected"] is True
    assert data["total_saves"] == 10
    assert data["quizzes_answered"] == 4

def test_patch_settings(client, override_db, auth_cookie):
    response = client.patch("/api/me", json={"timezone_offset": 3}, cookies=auth_cookie)
    assert response.status_code == 200
    data = response.json()
    assert data["timezone_offset"] == 3
    
    history = override_db.cursor().query_history
    update_query = next((item for item in history if "UPDATE users" in item[0]), None)
    assert update_query is not None
    assert update_query[1][0] == 180

def test_delete_account(client, override_db, auth_cookie):
    response = client.delete("/api/me", cookies=auth_cookie)
    assert response.status_code == 204
    
    history = override_db.cursor().query_history
    delete_query = next((item for item in history if "DELETE FROM users" in item[0]), None)
    assert delete_query is not None
    assert delete_query[1][0] == 42
    
    cookies = response.cookies
    assert "recall_session" not in cookies or cookies["recall_session"] == ""
    assert "jwt" not in cookies or cookies["jwt"] == ""
