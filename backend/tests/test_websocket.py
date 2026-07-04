import pytest
import time
import asyncio
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import unittest.mock as mock

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
        TELEGRAM_BOT_TOKEN = "1234567890:" + "ABCdefGHIjklmnoPQRstuvwxyZ123456789"
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

@pytest.fixture(autouse=True)
def mock_redis_global(monkeypatch):
    mock_redis = mock.AsyncMock()

    async def mock_brpop(key, timeout=0):
        await asyncio.sleep(0.01)
        return None

    mock_redis.brpop = mock.AsyncMock(side_effect=mock_brpop)
    mock_redis.sadd = mock.AsyncMock(return_value=1)
    mock_redis.srem = mock.AsyncMock(return_value=1)
    mock_redis.set = mock.AsyncMock(return_value=1)
    mock_redis.delete = mock.AsyncMock(return_value=1)
    mock_redis.smembers = mock.AsyncMock(return_value=[])
    mock_redis.pipeline = mock.AsyncMock(return_value=[])

    import backend.routes.websocket
    monkeypatch.setattr(backend.routes.websocket, "redis", mock_redis)
    return mock_redis

@pytest.fixture
def client():
    from backend.main import app
    return TestClient(app)

def generate_jwt(payload, secret):
    import jwt
    return jwt.encode(payload, secret, algorithm="HS256")

def test_path_websocket_no_token(client):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/") as websocket:
            pass
    assert exc_info.value.code in (4003, 1000)

def test_path_websocket_invalid_token(client):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/invalid_token") as websocket:
            pass
    assert exc_info.value.code in (4001, 1000)

def test_path_websocket_expired_token(client):
    token = generate_jwt({"sub": "42", "exp": int(time.time()) - 10}, VALID_ENV["JWT_SECRET"])
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/{token}") as websocket:
            pass
    assert exc_info.value.code in (4001, 1000)

def test_path_websocket_valid_connection_flow(client):
    token = generate_jwt({"sub": "42", "exp": int(time.time()) + 3600}, VALID_ENV["JWT_SECRET"])
    with client.websocket_connect(f"/ws/{token}") as websocket:
        resp = websocket.receive_json()
        assert resp == {"type": "connected", "user_id": 42}

def test_path_websocket_registry_addition_and_removal(client):
    from backend.routes.websocket import active_connections
    token = generate_jwt({"sub": "88", "exp": int(time.time()) + 3600}, VALID_ENV["JWT_SECRET"])
    
    with client.websocket_connect(f"/ws/{token}") as websocket:
        resp = websocket.receive_json()
        assert resp == {"type": "connected", "user_id": 88}
        assert 88 in active_connections

    for _ in range(20):
        if 88 not in active_connections:
            break
        time.sleep(0.01)
    assert 88 not in active_connections

@pytest.mark.asyncio
async def test_path_websocket_redis_broadcast(mock_redis_global):
    from backend.routes.websocket import broadcast, active_connections
    
    mock_ws = mock.AsyncMock()
    mock_ws.send_json.side_effect = Exception("Send error")
    active_connections[99] = mock_ws

    mock_redis_global.smembers.return_value = ["conn_1", "conn_2"]
    mock_redis_global.pipeline.side_effect = [
        [1, "1"],
        [1, 1]
    ]

    await broadcast(99, {"type": "new_saved_item"})
    
    mock_redis_global.smembers.assert_called_once_with("ws:connections:user:99")
    assert 99 not in active_connections
