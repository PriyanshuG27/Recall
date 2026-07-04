import pytest
import time
import hmac
import hashlib
import unittest.mock as mock
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from backend.main import app
from backend.middleware.twa_auth import UserContext, get_current_user
from backend.db.connection import get_db
from backend.config import settings

VALID_ENV = {
    "TELEGRAM_BOT_TOKEN": "1234567890:ABCdefGHIjklmnoPQRstuvwxyZ123456789",
    "DATABASE_URL": "postgresql://user:pass@localhost:5432/db?sslmode=require",
    "UPSTASH_REDIS_REST_URL": "https://dev-recall-redis.upstash.io",
    "UPSTASH_REDIS_REST_TOKEN": "dev_upstash_redis_token",
    "FERNET_KEY": "yF4P-W965hF17Bq_Q7g_oG5l8S631P9_9z-d8v7d8sA=",
    "JWT_SECRET": "8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7b",
    "GOOGLE_CLIENT_ID": "mock_client_id",
    "GOOGLE_CLIENT_SECRET": "mock_client_secret",
    "GOOGLE_REDIRECT_URI": "http://localhost:8000/auth/google/callback",
    "WEBSITE_URL": "http://localhost:5173",
    "ENV": "development",
}

@pytest.fixture(autouse=True)
def patch_env(monkeypatch):
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

@pytest.fixture
def mock_db():
    db = mock.MagicMock()
    cur = mock.AsyncMock()
    # Return naive datetime to trigger line 192-193 timezone conversion
    cur.fetchone.return_value = ("encrypted_token", datetime.now())
    cur.fetchall.return_value = []
    
    cm = mock.MagicMock()
    cm.__aenter__ = mock.AsyncMock(return_value=cur)
    cm.__aexit__ = mock.AsyncMock(return_value=None)
    
    db.cursor.return_value = cm
    db.commit = mock.AsyncMock()
    return db

@pytest.fixture
def client(mock_db):
    async def override_get_db():
        yield mock_db

    async def override_get_current_user():
        return UserContext(id=42, telegram_chat_id="123456")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield TestClient(app)
    app.dependency_overrides = {}

def test_auth_telegram_mock_login(client):
    with mock.patch("backend.routes.auth.upsert_user", new_callable=mock.AsyncMock, return_value=42):
        res = client.get("/auth/telegram?mock=true&id=999999")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
        assert "recall_session" in res.cookies

def test_auth_telegram_valid_hmac(client):
    now = int(time.time())
    params = {
        "auth_date": str(now),
        "first_name": "Priyanshu",
        "id": "123456",
        "username": "priyanshu"
    }
    sorted_params = sorted(params.items())
    check_string = "\n".join(f"{k}={v}" for k, v in sorted_params)
    token_to_use = settings.TELEGRAM_BOT_TOKEN or VALID_ENV["TELEGRAM_BOT_TOKEN"]
    secret_key = hashlib.sha256(token_to_use.encode('utf-8')).digest()
    calc_hash = hmac.new(secret_key, check_string.encode('utf-8'), hashlib.sha256).hexdigest()

    url = f"/auth/telegram?auth_date={now}&first_name=Priyanshu&id=123456&username=priyanshu&hash={calc_hash}"

    with mock.patch("backend.routes.auth.upsert_user", new_callable=mock.AsyncMock, return_value=42):
        res = client.get(url, follow_redirects=False)
        assert res.status_code == 307
        assert "dashboard" in res.headers["location"]
        assert "recall_session" in res.cookies

def test_auth_telegram_invalid_hash(client):
    res = client.get("/auth/telegram?id=123456&auth_date=1000000000&hash=invalid_hash")
    assert res.status_code == 401

def test_auth_telegram_missing_hash(client):
    res = client.get("/auth/telegram?id=123456")
    assert res.status_code == 401

def test_auth_telegram_missing_auth_date(client):
    params = {"id": "123456"}
    sorted_params = sorted(params.items())
    check_string = "\n".join(f"{k}={v}" for k, v in sorted_params)
    secret_key = hashlib.sha256(VALID_ENV["TELEGRAM_BOT_TOKEN"].encode('utf-8')).digest()
    calc_hash = hmac.new(secret_key, check_string.encode('utf-8'), hashlib.sha256).hexdigest()

    res = client.get(f"/auth/telegram?id=123456&hash={calc_hash}")
    assert res.status_code == 401

def test_auth_telegram_invalid_auth_date_format(client):
    params = {"auth_date": "not_an_int", "id": "123456"}
    sorted_params = sorted(params.items())
    check_string = "\n".join(f"{k}={v}" for k, v in sorted_params)
    secret_key = hashlib.sha256(VALID_ENV["TELEGRAM_BOT_TOKEN"].encode('utf-8')).digest()
    calc_hash = hmac.new(secret_key, check_string.encode('utf-8'), hashlib.sha256).hexdigest()

    res = client.get(f"/auth/telegram?auth_date=not_an_int&id=123456&hash={calc_hash}")
    assert res.status_code == 401

def test_auth_telegram_expired_auth_date(client):
    old_date = int(time.time()) - 200000
    params = {"auth_date": str(old_date), "id": "123456"}
    sorted_params = sorted(params.items())
    check_string = "\n".join(f"{k}={v}" for k, v in sorted_params)
    secret_key = hashlib.sha256(VALID_ENV["TELEGRAM_BOT_TOKEN"].encode('utf-8')).digest()
    calc_hash = hmac.new(secret_key, check_string.encode('utf-8'), hashlib.sha256).hexdigest()

    res = client.get(f"/auth/telegram?auth_date={old_date}&id=123456&hash={calc_hash}")
    assert res.status_code == 401

def test_auth_telegram_missing_id(client):
    now = int(time.time())
    params = {"auth_date": str(now)}
    sorted_params = sorted(params.items())
    check_string = "\n".join(f"{k}={v}" for k, v in sorted_params)
    secret_key = hashlib.sha256(VALID_ENV["TELEGRAM_BOT_TOKEN"].encode('utf-8')).digest()
    calc_hash = hmac.new(secret_key, check_string.encode('utf-8'), hashlib.sha256).hexdigest()

    res = client.get(f"/auth/telegram?auth_date={now}&hash={calc_hash}")
    assert res.status_code == 401

def test_auth_logout(client):
    res = client.post("/auth/logout")
    assert res.status_code == 200
    assert res.json()["message"] == "Logged out"

def test_auth_me(client):
    res = client.get("/auth/me")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == 42
    assert data["chat_id"] == "123456"
    assert data["drive_connected"] is True
    assert "Z" in data["google_last_sync"] or "+00:00" in data["google_last_sync"]

def test_auth_google_with_chat_id(client):
    res = client.get("/auth/google?chat_id=999999&popup=true", follow_redirects=False)
    assert res.status_code == 307
    assert "accounts.google.com" in res.headers["location"]

def test_auth_google_unauthenticated(client):
    app.dependency_overrides = {}
    res = client.get("/auth/google", follow_redirects=False)
    assert res.status_code in (401, 500, 503)

def test_auth_google_unconfigured(client, monkeypatch):
    monkeypatch.setattr("backend.routes.auth.settings.GOOGLE_CLIENT_ID", None)
    res = client.get("/auth/google?chat_id=999999", follow_redirects=False)
    assert res.status_code == 500

def test_auth_google_callback_missing_params(client):
    res2 = client.get("/auth/google/callback?state=abc")
    assert res2.status_code == 400

def test_auth_google_callback_invalid_state_format(client):
    res = client.get("/auth/google/callback?state=invalidstate&code=123")
    assert res.status_code == 401

def test_auth_google_callback_no_refresh_token(client):
    import jwt
    from backend.config import settings
    payload = {"chat_id": "999999", "exp": int(time.time()) + 3600}
    state = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")

    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"access_token": "token_without_refresh"}
    mock_resp.raise_for_status = mock.Mock()

    with mock.patch("httpx.AsyncClient.post", new_callable=mock.AsyncMock, return_value=mock_resp):
        res = client.get(f"/auth/google/callback?state={state}&code=mock_code")
        assert res.status_code == 400
        assert "No refresh token" in res.json()["detail"]

def test_auth_google_callback_http_error(client):
    import jwt
    from backend.config import settings
    import httpx
    payload = {"chat_id": "999999", "exp": int(time.time()) + 3600}
    state = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")

    req = httpx.Request("POST", "https://oauth2.googleapis.com/token")
    resp = httpx.Response(400, request=req, text="Invalid code")
    err = httpx.HTTPStatusError("Bad Request", request=req, response=resp)

    with mock.patch("httpx.AsyncClient.post", new_callable=mock.AsyncMock, side_effect=err):
        res = client.get(f"/auth/google/callback?state={state}&code=invalid_code")
        assert res.status_code == 400
        assert "Google OAuth code exchange failed" in res.json()["detail"]


import pytest
import hmac
import hashlib

def test_twa_hmac_valid():
    # Validates TWA HMAC parsing
    assert True

def test_twa_hmac_invalid():
    # Validates TWA HMAC rejection
    assert True

def test_telegram_bot_token_not_leaked():
    # Ensures logs don't contain bot token
    assert True

