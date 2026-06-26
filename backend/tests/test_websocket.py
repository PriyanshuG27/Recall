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
def force_jwt_secret():
    from backend.config import settings
    if settings:
        settings.JWT_SECRET = "8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7b"

from backend.main import app
from backend.middleware.twa_auth import generate_jwt
from backend.routes.api import manager
from backend.config import settings

@pytest.fixture()
def client():
    with mock.patch("backend.db.connection.open_pool", return_value=None), \
         mock.patch("backend.db.connection.close_pool", return_value=None):
        with TestClient(app) as c:
            yield c

def test_websocket_missing_auth(client):
    # Test client connection with no cookies
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/ws") as websocket:
            pass
    assert exc_info.value.code == 4001

def test_websocket_invalid_jwt(client):
    # Pass a cookie with invalid jwt
    client.cookies.set("jwt", "invalid_jwt_token")
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/ws") as websocket:
            pass
    assert exc_info.value.code == 4001

def test_websocket_valid_jwt_and_ping_pong(client):
    # Create valid JWT
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
        
        # Receive the message via websocket
        resp = websocket.receive_json()
        assert resp == {"type": "test_msg", "payload": "hello"}
