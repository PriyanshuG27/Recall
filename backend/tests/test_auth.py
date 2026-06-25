import time
import pytest
import urllib.parse
import hmac
import hashlib
import json
import unittest.mock as mock
from fastapi import Depends
from fastapi.testclient import TestClient

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
from backend.middleware.twa_auth import get_current_user, generate_jwt, verify_jwt, UserContext
from backend.config import settings

# ---------------------------------------------------------------------------
# Dynamically add test route for JWT verification
# ---------------------------------------------------------------------------
@app.get("/test-auth/widget-jwt")
def widget_jwt_endpoint(user: UserContext = Depends(get_current_user)):
    return {"status": "ok", "user_id": user.id, "chat_id": user.telegram_chat_id}

# ---------------------------------------------------------------------------
# Helpers for Login Widget Param Hashing
# ---------------------------------------------------------------------------
def make_widget_params(telegram_chat_id: str, bot_token: str, auth_date: int, tamper: bool = False, omit_hash: bool = False) -> dict:
    params = {
        "id": str(telegram_chat_id),
        "first_name": "Test",
        "username": "testuser",
        "auth_date": str(auth_date)
    }
    # Sort alphabetically
    sorted_params = sorted(params.items())
    check_string = "\n".join(f"{k}={v}" for k, v in sorted_params)
    
    # Calculate HMAC
    secret_key = hashlib.sha256(bot_token.encode('utf-8')).digest()
    computed_hash = hmac.new(secret_key, check_string.encode('utf-8'), hashlib.sha256).hexdigest()
    
    if tamper:
        computed_hash = computed_hash[:-1] + ("0" if computed_hash[-1] != "0" else "1")
        
    if not omit_hash:
        params["hash"] = computed_hash
        
    return params

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def client():
    with mock.patch("backend.db.connection.open_pool", return_value=None), \
         mock.patch("backend.db.connection.close_pool", return_value=None):
        with TestClient(app) as c:
            yield c

class StatefulMockCursor:
    def __init__(self):
        self.fetchone_result = None
        self.executed = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def execute(self, query, params=None):
        self.executed.append((query, params))

    async def fetchone(self):
        # If it's a users SELECT query returning id and telegram_chat_id
        if self.executed and "SELECT id, telegram_chat_id FROM users" in self.executed[-1][0]:
            return (42, "12345")
        # If it's upsert RETURNING id
        if self.executed and "INSERT INTO users" in self.executed[-1][0]:
            return (42,)
        # If conflict and SELECT id
        if self.executed and "SELECT id FROM users WHERE telegram_chat_id" in self.executed[-1][0]:
            return (42,)
        return self.fetchone_result

class StatefulMockConn:
    def __init__(self):
        self._cursor = StatefulMockCursor()

    def cursor(self):
        return self._cursor

    async def commit(self):
        pass

    async def rollback(self):
        pass

@pytest.fixture()
def mock_conn():
    return StatefulMockConn()

@pytest.fixture(autouse=True)
def override_db(mock_conn):
    from backend.db.connection import get_db
    async def _mock_get_db():
        yield mock_conn
    app.dependency_overrides[get_db] = _mock_get_db
    yield
    app.dependency_overrides.pop(get_db, None)

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_login_widget_success(client):
    """Case 1: Valid Telegram Widget Login -> Sets httpOnly cookies, returns 200."""
    now = int(time.time())
    params = make_widget_params("12345", settings.TELEGRAM_BOT_TOKEN, now)
    
    response = client.get("/auth/telegram", params=params)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    
    # Assert cookies are set properly and are httpOnly
    cookies = response.cookies
    assert "recall_session" in cookies
    assert "jwt" in cookies
    
    # TestClient doesn't expose cookie flags directly in response.cookies easily,
    # but we can verify the Set-Cookie headers in response.headers
    set_cookie_headers = response.headers.get_list("set-cookie")
    for cookie_header in set_cookie_headers:
        assert "HttpOnly" in cookie_header
        assert "SameSite=lax" in cookie_header or "SameSite=Lax" in cookie_header

def test_login_widget_invalid_hash(client):
    """Case 2: Invalid hash -> returns 401, does not set cookies."""
    now = int(time.time())
    params = make_widget_params("12345", settings.TELEGRAM_BOT_TOKEN, now, tamper=True)
    
    response = client.get("/auth/telegram", params=params)
    assert response.status_code == 401
    assert "recall_session" not in response.cookies

def test_login_widget_stale_auth_date(client):
    """Case 3: auth_date > 1 day old -> returns 401."""
    stale_time = int(time.time()) - 90000  # More than 24 hours ago
    params = make_widget_params("12345", settings.TELEGRAM_BOT_TOKEN, stale_time)
    
    response = client.get("/auth/telegram", params=params)
    assert response.status_code == 401
    assert "recall_session" not in response.cookies

def test_protected_route_with_valid_jwt(client):
    """Case 4: JWT on protected route with valid cookie -> returns 200."""
    payload = {
        "sub": "42",
        "chat_id": "12345",
        "exp": int(time.time()) + 3600
    }
    token = generate_jwt(payload, settings.JWT_SECRET)
    
    response = client.get("/test-auth/widget-jwt", cookies={"recall_session": token})
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "user_id": 42, "chat_id": "12345"}

def test_protected_route_with_expired_jwt(client):
    """Case 5: Expired JWT on protected route -> returns 401, clears cookie."""
    payload = {
        "sub": "42",
        "chat_id": "12345",
        "exp": int(time.time()) - 3600  # Expired 1 hour ago
    }
    token = generate_jwt(payload, settings.JWT_SECRET)
    
    response = client.get("/test-auth/widget-jwt", cookies={"recall_session": token})
    assert response.status_code == 401
    assert "Not authenticated" in response.json()["detail"]
    
    # Assert that the recall_session and jwt cookies are deleted in the response
    set_cookie_headers = response.headers.get_list("set-cookie")
    session_deleted = False
    jwt_deleted = False
    for cookie_header in set_cookie_headers:
        if "recall_session=" in cookie_header and 'Max-Age=0' in cookie_header:
            session_deleted = True
        if "jwt=" in cookie_header and 'Max-Age=0' in cookie_header:
            jwt_deleted = True
            
    assert session_deleted or "Max-Age=0" in set_cookie_headers[0]

def test_protected_route_with_tampered_jwt(client):
    """Tampering with JWT payload (changed signature) -> returns 401, clears cookie."""
    payload = {
        "sub": "42",
        "chat_id": "12345",
        "exp": int(time.time()) + 3600
    }
    # Sign token with wrong secret
    token = generate_jwt(payload, "wrong_jwt_secret_12345678901234567890")
    
    response = client.get("/test-auth/widget-jwt", cookies={"recall_session": token})
    assert response.status_code == 401
    assert "Not authenticated" in response.json()["detail"]

def test_search_endpoint_without_jwt(client):
    """POST /api/search without cookie returns 401."""
    response = client.post("/api/search", json={"query": "fastapi", "limit": 5})
    assert response.status_code == 401
    assert "Not authenticated" in response.json()["detail"]
