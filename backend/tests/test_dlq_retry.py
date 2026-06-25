"""
backend/tests/test_dlq_retry.py
================================
Unit tests for the admin queue monitoring and DLQ retry endpoints.
"""

import pytest
import json
import unittest.mock as mock
from datetime import datetime, timezone
from fastapi import status
from fastapi.testclient import TestClient

from backend.main import app
from backend.db.connection import get_db

VALID_ENV = {
    "TELEGRAM_BOT_TOKEN": "1234567890:ABCdefGHIjklmnoPQRstuvwxyZ123456789",
    "DATABASE_URL": "postgresql://user:pass@localhost:5432/db?sslmode=require",
    "UPSTASH_REDIS_REST_URL": "https://dev-recall-redis.upstash.io",
    "UPSTASH_REDIS_REST_TOKEN": "dev_upstash_redis_token",
    "FERNET_KEY": "yF4P-W965hF17Bq_Q7g_oG5l8S631P9_9z-d8v7d8sA=",
    "JWT_SECRET": "8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7b",
    "WEBSITE_URL": "http://localhost:5173",
    "INTERNAL_API_KEY": "super_secret_admin_key",
    "ENV": "test",
}

@pytest.fixture(autouse=True)
def patch_env(monkeypatch):
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)
    from backend.config import settings
    if settings:
        monkeypatch.setattr(settings, "INTERNAL_API_KEY", "super_secret_admin_key")

# --- Mock DB Structures ---

class MockCursor:
    def __init__(self, dlq_rows=None):
        self.executed = []
        self.dlq_rows = dlq_rows or []
        self.rowcount = 1
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
        
    async def execute(self, query, params=None):
        self.executed.append((query, params))
        
    async def fetchone(self):
        last_query = self.executed[-1][0].lower() if self.executed else ""
        if "count(*)" in last_query:
            return (len(self.dlq_rows),)
        if "failed_at" in last_query:
            if self.dlq_rows:
                return (self.dlq_rows[0][1],)
            return None
        if "task_payload" in last_query:
            if self.dlq_rows:
                # Returns payload
                return (self.dlq_rows[0][0],)
            return None
        return None

    async def fetchall(self):
        return []

class MockConnection:
    def __init__(self, cursor_inst):
        self.cursor_inst = cursor_inst
        
    def cursor(self):
        return self.cursor_inst
        
    async def commit(self):
        pass

# --- Fixtures ---

current_cursor = None

@pytest.fixture()
def override_db():
    global current_cursor
    current_cursor = None
    
    async def _mock_get_db():
        yield MockConnection(current_cursor)
        
    app.dependency_overrides[get_db] = _mock_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def client():
    with mock.patch("backend.db.connection.open_pool", return_value=None), \
         mock.patch("backend.db.connection.close_pool", return_value=None):
        with TestClient(app) as c:
            yield c


def test_admin_endpoints_require_authorization(client, override_db):
    """Verify that admin endpoints return 401/422 if X-Internal-Key is missing or incorrect."""
    # 1. Missing header
    resp = client.get("/api/admin/queue")
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY  # fastapi header validation
    
    # 2. Invalid key header
    resp = client.get("/api/admin/queue", headers={"X-Internal-Key": "wrong_key"})
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
    assert resp.json()["detail"] == "Unauthorized: Invalid internal API key."

    # 3. Retry missing header
    resp = client.post("/api/admin/dlq/1/retry")
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # 4. Retry invalid key header
    resp = client.post("/api/admin/dlq/1/retry", headers={"X-Internal-Key": "wrong_key"})
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_admin_queue_metrics(client, override_db, monkeypatch):
    """Verify that GET /api/admin/queue retrieves correct Redis and DLQ metrics."""
    global current_cursor
    
    # Set up unretried DLQ rows (payload, failed_at)
    sample_time = datetime(2026, 6, 25, 12, 0, 0, tzinfo=timezone.utc)
    dlq_data = [
        ({"chat_id": "12345", "content_type": "text"}, sample_time)
    ]
    current_cursor = MockCursor(dlq_rows=dlq_data)
    
    # Mock redis llen
    mock_redis = mock.AsyncMock()
    mock_redis.llen = mock.AsyncMock(return_value=12)
    monkeypatch.setattr("backend.services.redis_client.redis", mock_redis)
    
    # Mock semaphore available slots
    mock_semaphore = mock.MagicMock()
    mock_semaphore._value = 2
    monkeypatch.setattr("backend.worker.worker_semaphore", mock_semaphore)
    
    resp = client.get("/api/admin/queue", headers={"X-Internal-Key": "super_secret_admin_key"})
    
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["queue_length"] == 12
    assert data["dead_letter_count"] == 1
    assert data["oldest_dead_letter"] == sample_time.isoformat()
    assert data["processing_slots"]["available"] == 2
    assert data["processing_slots"]["total"] == 3


def test_retry_dlq_task_requeues_and_updates(client, override_db, monkeypatch):
    """Verify that POST /api/admin/dlq/{id}/retry pops payload to Redis and marks retried=TRUE."""
    global current_cursor
    
    task_payload = {"chat_id": "7732257445", "content_type": "text", "update_id": "9999"}
    current_cursor = MockCursor(dlq_rows=[(task_payload, None)])
    
    # Mock redis lpush
    mock_redis = mock.AsyncMock()
    monkeypatch.setattr("backend.services.redis_client.redis", mock_redis)
    
    resp = client.post("/api/admin/dlq/42/retry", headers={"X-Internal-Key": "super_secret_admin_key"})
    
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json() == {"queued": True}
    
    # Verify LPUSH was called with task json
    mock_redis.lpush.assert_called_once_with("recall:tasks", json.dumps(task_payload))
    
    # Verify UPDATE query was executed
    executed_queries = [q[0] for q in current_cursor.executed]
    update_query = [q for q in executed_queries if "update dead_letter_queue" in q.lower()]
    assert len(update_query) == 1
