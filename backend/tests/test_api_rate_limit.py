import pytest
import time
import unittest.mock as mock
from fastapi.testclient import TestClient
from backend.main import app
from backend.middleware.twa_auth import get_current_user, generate_jwt, UserContext
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


class MockRedisRateLimitState:
    def __init__(self):
        self.state = {}

    async def eval(self, script, numkeys, *args):
        key = args[0]
        now = int(args[1])
        window_start = int(args[2])
        member_id = args[3]
        limit = int(args[5])
        
        if key not in self.state:
            self.state[key] = []
            
        # ZREMRANGEBYSCORE key 0 window_start
        self.state[key] = [t for t in self.state[key] if t > window_start]
        
        # ZADD key now member_id
        self.state[key].append(now)
        self.state[key].sort()
        
        card = len(self.state[key])
        oldest_member = f"{self.state[key][0]}-mockuuid"
        return [card, oldest_member]


class DummyCursor:
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
        
    async def execute(self, query, params=None):
        pass
        
    async def fetchone(self):
        return (42, "123456789", 0)
        
    async def fetchall(self):
        return []


class DummyConnection:
    def cursor(self):
        return DummyCursor()
        
    async def commit(self):
        pass
        
    async def rollback(self):
        pass


@pytest.fixture(autouse=True)
def override_db():
    async def _mock_get_db():
        yield DummyConnection()
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


def test_exempt_routes(client):
    # /auth/telegram (and auth routes generally) should not trigger rate limit checks.
    with mock.patch("backend.services.redis_client.redis.eval") as mock_eval:
        resp = client.get("/health")
        assert resp.status_code == 200
        client.get("/auth/telegram")
        assert not mock_eval.called


def test_rate_limit_exceeded_response(client):
    token = get_auth_token(user_id=42)
    db_state = MockRedisRateLimitState()
    
    with mock.patch("backend.services.redis_client.redis.eval", side_effect=db_state.eval):
        # POST /api/search limit = 60
        for _ in range(60):
            resp = client.post("/api/search", json={"query": "test"}, cookies={"recall_session": token})
            assert resp.status_code == 200
            
        resp = client.post("/api/search", json={"query": "test"}, cookies={"recall_session": token})
        assert resp.status_code == 429
        
        data = resp.json()
        assert data["error"] == "rate_limit_exceeded"
        assert "retry_after" in data
        
        assert "Retry-After" in resp.headers
        assert resp.headers["Retry-After"] == str(data["retry_after"])
        
        assert "rate:search:42" in db_state.state


def test_different_limits_search_vs_sync(client):
    token = get_auth_token(user_id=42)
    db_state = MockRedisRateLimitState()
    
    with mock.patch("backend.services.redis_client.redis.eval", side_effect=db_state.eval), \
         mock.patch("backend.services.drive_sync.sync_user_to_drive", new_callable=mock.AsyncMock) as mock_sync:
        # drive/sync has limit = 5 per hour
        for _ in range(5):
            resp = client.post("/api/drive/sync", cookies={"recall_session": token})
            assert resp.status_code == 200 or resp.status_code == 202

        resp = client.post("/api/drive/sync", cookies={"recall_session": token})
        assert resp.status_code == 429
        assert resp.json()["error"] == "rate_limit_exceeded"
        assert "rate:sync:42" in db_state.state
