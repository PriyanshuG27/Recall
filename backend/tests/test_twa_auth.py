import time
import pytest
import urllib.parse
import hmac
import hashlib
import json
import unittest.mock as mock
from fastapi import Depends, HTTPException
from fastapi.testclient import TestClient

# Make sure env vars are patched before importing app or config
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
from backend.middleware.twa_auth import (
    get_twa_user,
    get_jwt_user,
    get_current_user,
    generate_jwt,
    UserContext
)
from backend.config import settings


# ---------------------------------------------------------------------------
# Dynamically add test routes for middleware verification
# ---------------------------------------------------------------------------
@app.get("/test-auth/twa")
def twa_endpoint(user: UserContext = Depends(get_twa_user)):
    return {"status": "ok", "user_id": user.id, "chat_id": user.telegram_chat_id}


@app.get("/test-auth/jwt")
def jwt_endpoint(user: UserContext = Depends(get_jwt_user)):
    return {"status": "ok", "user_id": user.id, "chat_id": user.telegram_chat_id}


@app.get("/test-auth/current")
def current_endpoint(user: UserContext = Depends(get_current_user)):
    return {"status": "ok", "user_id": user.id, "chat_id": user.telegram_chat_id}


# ---------------------------------------------------------------------------
# Helpers for generating test tokens / headers
# ---------------------------------------------------------------------------
def make_twa_init_data(telegram_user_id: int, bot_token: str, auth_date: int, tamper: bool = False, omit_hash: bool = False) -> str:
    user_data = {"id": telegram_user_id, "first_name": "Test", "username": "testuser"}
    params = {
        "auth_date": str(auth_date),
        "query_id": "AAHdF24KAAAAAN0XbgrN2Y37",
        "user": json.dumps(user_data)
    }
    
    # Sort alphabetically
    sorted_params = sorted(params.items())
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted_params)
    
    # Calculate HMAC
    secret_key = hmac.new(b"WebAppData", bot_token.encode('utf-8'), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode('utf-8'), hashlib.sha256).hexdigest()
    
    if tamper:
        # Tamper with computed hash by changing its last character
        computed_hash = computed_hash[:-1] + ("0" if computed_hash[-1] != "0" else "1")
        
    if not omit_hash:
        params["hash"] = computed_hash
        
    return urllib.parse.urlencode(params)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def client():
    """TestClient that mocks database pool lifecycle."""
    with mock.patch("backend.db.connection.open_pool", return_value=None), \
         mock.patch("backend.db.connection.close_pool", return_value=None):
        with TestClient(app) as c:
            yield c


@pytest.fixture()
def mock_db_conn():
    """Mock connection and cursor supporting async context manager."""
    class MockCursor:
        def __init__(self):
            self.result = None
            
        async def __aenter__(self):
            return self
            
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
            
        async def execute(self, query, params=None):
            pass
            
        async def fetchone(self):
            return self.result

    class MockConn:
        def __init__(self):
            self._cursor = MockCursor()
            
        def cursor(self):
            return self._cursor

    return MockConn()


@pytest.fixture(autouse=True)
def override_db(mock_db_conn):
    """Override get_db to return our mock DB connection."""
    from backend.db.connection import get_db
    
    async def _mock_get_db():
        yield mock_db_conn
        
    app.dependency_overrides[get_db] = _mock_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Unit Tests: TWA HMAC Authentication (get_twa_user)
# ---------------------------------------------------------------------------
def test_twa_valid_init_data(client, mock_db_conn):
    """Case 1: Valid initData -> 200 with user context attached."""
    now = int(time.time())
    init_data = make_twa_init_data(12345, settings.TELEGRAM_BOT_TOKEN, now)
    
    # Mock user exists in database
    mock_db_conn.cursor().result = (42, "12345")
    
    response = client.get(
        "/test-auth/twa",
        headers={"Authorization": f"TelegramInitData {init_data}"}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "user_id": 42, "chat_id": "12345"}


def test_twa_invalid_hash(client, mock_db_conn):
    """Case 2: Tampered TWA hash -> 401."""
    now = int(time.time())
    init_data = make_twa_init_data(12345, settings.TELEGRAM_BOT_TOKEN, now, tamper=True)
    
    mock_db_conn.cursor().result = (42, "12345")
    
    response = client.get(
        "/test-auth/twa",
        headers={"Authorization": f"TelegramInitData {init_data}"}
    )
    assert response.status_code == 401
    assert "Not authenticated" in response.json().get("detail", "")


def test_twa_expired_auth_date(client, mock_db_conn):
    """Case 3: Expired auth_date (> 1 hour) -> 401."""
    expired_time = int(time.time()) - 3601  # 1 hour and 1 second ago
    init_data = make_twa_init_data(12345, settings.TELEGRAM_BOT_TOKEN, expired_time)
    
    mock_db_conn.cursor().result = (42, "12345")
    
    response = client.get(
        "/test-auth/twa",
        headers={"Authorization": f"TelegramInitData {init_data}"}
    )
    assert response.status_code == 401
    assert "Not authenticated" in response.json().get("detail", "")


def test_twa_missing_hash_field(client, mock_db_conn):
    """Case 4: Missing hash field -> 401."""
    now = int(time.time())
    init_data = make_twa_init_data(12345, settings.TELEGRAM_BOT_TOKEN, now, omit_hash=True)
    
    mock_db_conn.cursor().result = (42, "12345")
    
    response = client.get(
        "/test-auth/twa",
        headers={"Authorization": f"TelegramInitData {init_data}"}
    )
    assert response.status_code == 401
    assert "Not authenticated" in response.json().get("detail", "")


def test_twa_user_not_found(client, mock_db_conn):
    """TWA user validated but not found in DB -> 401."""
    now = int(time.time())
    init_data = make_twa_init_data(12345, settings.TELEGRAM_BOT_TOKEN, now)
    
    # Mock user NOT in DB
    mock_db_conn.cursor().result = None
    
    response = client.get(
        "/test-auth/twa",
        headers={"Authorization": f"TelegramInitData {init_data}"}
    )
    assert response.status_code == 401
    assert "Not authenticated" in response.json().get("detail", "")


# ---------------------------------------------------------------------------
# Unit Tests: JWT Cookie Authentication (get_jwt_user)
# ---------------------------------------------------------------------------
def test_jwt_valid_cookie(client, mock_db_conn):
    """Valid JWT cookie -> 200 with user context attached."""
    payload = {"sub": "42", "chat_id": "12345", "exp": int(time.time()) + 3600}
    token = generate_jwt(payload, settings.JWT_SECRET)
    
    mock_db_conn.cursor().result = (42, "12345")
    
    response = client.get("/test-auth/jwt", headers={"Cookie": f"jwt={token}"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "user_id": 42, "chat_id": "12345"}


def test_jwt_expired_cookie(client, mock_db_conn):
    """Expired JWT cookie -> 401."""
    payload = {"sub": "42", "chat_id": "12345", "exp": int(time.time()) - 10}
    token = generate_jwt(payload, settings.JWT_SECRET)
    
    mock_db_conn.cursor().result = (42, "12345")
    
    response = client.get("/test-auth/jwt", headers={"Cookie": f"jwt={token}"})
    assert response.status_code == 401
    assert "Not authenticated" in response.json().get("detail", "")


def test_jwt_invalid_signature(client, mock_db_conn):
    """JWT cookie with invalid signature -> 401."""
    payload = {"sub": "42", "chat_id": "12345", "exp": int(time.time()) + 3600}
    token = generate_jwt(payload, "wrong_secret_12345678901234567890123456")
    
    mock_db_conn.cursor().result = (42, "12345")
    
    response = client.get("/test-auth/jwt", headers={"Cookie": f"jwt={token}"})
    assert response.status_code == 401
    assert "Not authenticated" in response.json().get("detail", "")


# ---------------------------------------------------------------------------
# Unit Tests: Unified Authentication (get_current_user)
# ---------------------------------------------------------------------------
def test_unified_jwt_takes_precedence_and_succeeds(client, mock_db_conn):
    """Unified auth: Valid JWT cookie succeeds, TWA header ignored."""
    # Generate valid JWT
    payload = {"sub": "42", "chat_id": "12345", "exp": int(time.time()) + 3600}
    token = generate_jwt(payload, settings.JWT_SECRET)
    
    # Generate an expired/invalid TWA header to ensure it's not even evaluated
    init_data = "invalid_twa_data"
    
    mock_db_conn.cursor().result = (42, "12345")
    
    response = client.get(
        "/test-auth/current",
        headers={
            "Cookie": f"jwt={token}",
            "Authorization": f"TelegramInitData {init_data}"
        }
    )
    assert response.status_code == 200
    assert response.json()["user_id"] == 42


def test_unified_jwt_fails_immediately(client, mock_db_conn):
    """Unified auth: Invalid JWT cookie fails immediately, TWA header ignored (no double auth)."""
    # Generate expired JWT
    payload = {"sub": "42", "chat_id": "12345", "exp": int(time.time()) - 10}
    token = generate_jwt(payload, settings.JWT_SECRET)
    
    # Generate valid TWA initData
    now = int(time.time())
    init_data = make_twa_init_data(12345, settings.TELEGRAM_BOT_TOKEN, now)
    
    mock_db_conn.cursor().result = (42, "12345")
    
    response = client.get(
        "/test-auth/current",
        headers={
            "Cookie": f"jwt={token}",
            "Authorization": f"TelegramInitData {init_data}"
        }
    )
    # Must fail because JWT cookie was present but invalid (no fallback to TWA)
    assert response.status_code == 401
    assert "Not authenticated" in response.json().get("detail", "")


def test_unified_fallback_to_twa_succeeds(client, mock_db_conn):
    """Unified auth: JWT cookie missing, valid TWA header succeeds."""
    now = int(time.time())
    init_data = make_twa_init_data(12345, settings.TELEGRAM_BOT_TOKEN, now)
    
    mock_db_conn.cursor().result = (42, "12345")
    
    response = client.get(
        "/test-auth/current",
        headers={"Authorization": f"TelegramInitData {init_data}"}
    )
    assert response.status_code == 200
    assert response.json()["user_id"] == 42


def test_unified_fallback_to_twa_fails(client, mock_db_conn):
    """Unified auth: JWT cookie missing, invalid TWA header fails."""
    now = int(time.time())
    init_data = make_twa_init_data(12345, settings.TELEGRAM_BOT_TOKEN, now, tamper=True)
    
    mock_db_conn.cursor().result = (42, "12345")
    
    response = client.get(
        "/test-auth/current",
        headers={"Authorization": f"TelegramInitData {init_data}"}
    )
    assert response.status_code == 401
    assert "Not authenticated" in response.json().get("detail", "")


def test_unified_missing_both_fails(client):
    """Unified auth: Neither JWT nor TWA header present -> 401."""
    response = client.get("/test-auth/current")
    assert response.status_code == 401
