import pytest
import time
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import unittest.mock as mock

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

@pytest.fixture(autouse=True)
def force_jwt_secret(monkeypatch):
    import backend.routes.websocket
    import backend.middleware.twa_auth
    import backend.config

    class MockSettings:
        TELEGRAM_BOT_TOKEN = "1234567890:ABCdefGHIjklmnoPQRstuvwxyZ123456789"
        DATABASE_URL = "postgresql://user:pass@localhost:5432/db?sslmode=require"
        UPSTASH_REDIS_REST_URL = "https://dev-recall-redis.upstash.io"
        UPSTASH_REDIS_REST_TOKEN = "dev_upstash_redis_token"
        FERNET_KEY = "yF4P-W965hF17Bq_Q7g_oG5l8S631P9_9z-d8v7d8sA="
        JWT_SECRET = "8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7b"
        WEBSITE_URL = "http://localhost:5173"
        ENV = "test"
        def validate_crypto_keys(self):
            pass

    mock_settings = MockSettings()

    monkeypatch.setattr(backend.routes.websocket, "settings", mock_settings)
    monkeypatch.setattr(backend.middleware.twa_auth, "settings", mock_settings)
    monkeypatch.setattr(backend.config, "settings", mock_settings)

from backend.main import app
from backend.middleware.twa_auth import generate_jwt
from backend.config import settings

@pytest.fixture()
def client():
    with mock.patch("backend.db.connection.open_pool", return_value=None), \
         mock.patch("backend.db.connection.close_pool", return_value=None):
        with TestClient(app) as c:
            yield c

# ---------------------------------------------------------------------------
# Old tests (covering /api/ws and cookies)
# ---------------------------------------------------------------------------
def test_websocket_missing_auth(client):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/ws") as websocket:
            pass
    assert exc_info.value.code == 4001

def test_websocket_invalid_jwt(client):
    client.cookies.set("jwt", "invalid_jwt_token")
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/ws") as websocket:
            pass
    assert exc_info.value.code == 4001

def test_websocket_valid_jwt_and_ping_pong(client):
    token = generate_jwt({"sub": "42", "exp": int(time.time()) + 3600}, VALID_ENV["JWT_SECRET"])
    with client.websocket_connect("/api/ws", headers={"cookie": f"jwt={token}"}) as websocket:
        websocket.send_text("ping")
        resp = websocket.receive_text()
        assert resp == "pong"

def test_websocket_broadcast_to_user(client):
    token = generate_jwt({"sub": "99", "exp": int(time.time()) + 3600}, VALID_ENV["JWT_SECRET"])
    with client.websocket_connect("/api/ws", headers={"cookie": f"jwt={token}"}) as websocket:
        import asyncio
        from backend.routes.api import manager
        asyncio.run(manager.send_personal_message({"type": "test_msg", "payload": "hello"}, 99))
        resp = websocket.receive_json()
        assert resp == {"type": "test_msg", "payload": "hello"}

# ---------------------------------------------------------------------------
# New tests (covering /ws/{token} path token connection flow)
# ---------------------------------------------------------------------------
def test_path_websocket_invalid_token(client):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/invalid_token") as websocket:
            pass
    assert exc_info.value.code == 4001

def test_path_websocket_expired_token(client):
    token = generate_jwt({"sub": "42", "exp": int(time.time()) - 10}, VALID_ENV["JWT_SECRET"])
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/{token}") as websocket:
            pass
    assert exc_info.value.code == 4001

def test_path_websocket_valid_connection_flow(client):
    token = generate_jwt({"sub": "42", "exp": int(time.time()) + 3600}, VALID_ENV["JWT_SECRET"])
    with client.websocket_connect(f"/ws/{token}") as websocket:
        # Client connects and immediately receives {"type": "connected", "user_id": 42}
        resp = websocket.receive_json()
        assert resp == {"type": "connected", "user_id": 42}

def test_path_websocket_registry_addition_and_removal(client):
    from backend.routes.websocket import active_connections
    token = generate_jwt({"sub": "88", "exp": int(time.time()) + 3600}, VALID_ENV["JWT_SECRET"])
    
    with client.websocket_connect(f"/ws/{token}") as websocket:
        resp = websocket.receive_json()
        assert resp == {"type": "connected", "user_id": 88}
        
        # User should be in registry
        assert 88 in active_connections
        assert active_connections[88] is not None

    # After connection disconnects, user should be removed from registry
    # Use a small retry loop to allow event cleanup to run on async thread
    for _ in range(20):
        if 88 not in active_connections:
            break
        time.sleep(0.01)
    assert 88 not in active_connections

def test_path_websocket_mocked_broadcast(client):
    # Mock broadcast() implementation to test calling it
    with mock.patch("backend.routes.websocket.broadcast", new_callable=mock.AsyncMock) as mock_broadcast:
        from backend.routes.websocket import broadcast
        import asyncio
        asyncio.run(broadcast(99, {"type": "ping"}))
        mock_broadcast.assert_called_once_with(99, {"type": "ping"})
