import pytest
import unittest.mock as mock
from datetime import datetime, timezone, timedelta

from fastapi.testclient import TestClient
from backend.main import app
from backend.config import settings
from backend.db.connection import get_db
from backend.middleware.twa_auth import generate_jwt
from backend.services.pulse_service import calculate_user_pulse, update_user_pulse

VALID_ENV = {
    "TELEGRAM_BOT_TOKEN": "1234567890:ABCdefGHIjklmnoPQRstuvwxyZ123456789",
    "DATABASE_URL": "postgresql://user:pass@localhost:5432/db?sslmode=require",
    "UPSTASH_REDIS_REST_URL": "https://dev-recall-redis.upstash.io",
    "UPSTASH_REDIS_REST_TOKEN": "dev_upstash_redis_token",
    "FERNET_KEY": "yF4P-W965hF17Bq_Q7g_oG5l8S631P9_9z-d8v7d8sA=",
    "JWT_SECRET": "8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7b",
    "ENV": "test",
}

@pytest.fixture(autouse=True)
def patch_env(monkeypatch):
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

class MockCursor:
    def __init__(self):
        self.executed = []
        self.fetchone_val = None
        self.fetchall_val = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def execute(self, query, params=None):
        self.executed.append((query, params))

    async def fetchone(self):
        if self.fetchone_val is not None:
            return self.fetchone_val
        return None

    async def fetchall(self):
        return self.fetchall_val

class MockConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def cursor(self):
        return self.cursor_obj

    async def commit(self):
        pass

@pytest.fixture()
def mock_db():
    cursor = MockCursor()
    conn = MockConnection(cursor)
    
    async def _mock_get_db():
        yield conn
        
    app.dependency_overrides[get_db] = _mock_get_db
    yield cursor
    app.dependency_overrides.pop(get_db, None)

@pytest.fixture()
def client():
    with mock.patch("backend.db.connection.open_pool", return_value=None), \
         mock.patch("backend.db.connection.close_pool", return_value=None):
        with TestClient(app) as c:
            yield c

@pytest.mark.anyio
async def test_pulse_calculation_no_activity(mock_db):
    """Test pulse score defaults when a user has zero items, quizzes, or activity."""
    # Psycopg mock executes:
    # 1. Total items count (SELECT COUNT(*))
    # 2. Retention rate (SELECT COUNT(CASE...))
    # 3. Last activity timestamp (SELECT COALESCE...)
    async def mock_fetchone():
        last_query = mock_db.executed[-1][0]
        if "COUNT(*)" in last_query and "items" in last_query:
            return (0,)
        elif "quality >= 3" in last_query:
            return (0, 0)
        elif "COALESCE" in last_query:
            return (datetime.now(timezone.utc),)
        return None

    mock_db.fetchone = mock_fetchone

    pulse = await calculate_user_pulse(mock_db, 1)
    # Total items = 0 -> Score = 0
    # Retention rate = default 0.5 -> Score = 25.0
    # Days inactive = 0 -> Score = 0
    # Expected pulse = 25
    assert pulse == 25

@pytest.mark.anyio
async def test_pulse_calculation_with_active_saves(mock_db):
    """Test pulse score scales with item count and active retention."""
    async def mock_fetchone():
        last_query = mock_db.executed[-1][0]
        if "COUNT(*)" in last_query and "items" in last_query:
            return (10,)  # 10 saved items
        elif "quality >= 3" in last_query:
            return (4, 5)  # 4 correct out of 5 attempts (80% retention)
        elif "COALESCE" in last_query:
            # Last active 1 day ago
            return (datetime.now(timezone.utc) - timedelta(days=1),)
        return None

    mock_db.fetchone = mock_fetchone

    pulse = await calculate_user_pulse(mock_db, 1)
    # Score_items = 15.0 * ln(11) = 35.97
    # Score_retention = 50.0 * 0.8 = 40.0
    # Score_decay = 5.0 * 1 = 5.0
    # Expected raw = 35.97 + 40.0 - 5.0 = 70.97
    # Expected pulse = 71
    assert pulse == 71

@pytest.mark.anyio
async def test_get_tag_portraits_endpoint(client, mock_db):
    """Verify that calling /api/tags/portraits returns saved portraits."""
    import time
    token_payload = {
        "sub": "42",
        "chat_id": "123456",
        "exp": int(time.time()) + 3600
    }
    jwt_token = generate_jwt(token_payload, settings.JWT_SECRET)

    async def mock_fetchall():
        last_query = mock_db.executed[-1][0]
        if "tag_portraits" in last_query:
            return [("python", "A python programming cluster", "🐍"), ("react", "Frontend UI notes", "⚛️")]
        return []

    async def mock_fetchone():
        return (42, "123456")

    mock_db.fetchall = mock_fetchall
    mock_db.fetchone = mock_fetchone

    resp = client.get(
        "/api/tags/portraits",
        headers={"Authorization": f"Bearer {jwt_token}"}
    )
    assert resp.status_code == 200
    res_dict = resp.json()
    assert "python" in res_dict
    assert res_dict["python"]["description"] == "A python programming cluster"
    assert res_dict["python"]["icon"] == "🐍"
    assert "react" in res_dict
    assert res_dict["react"]["icon"] == "⚛️"
