import pytest
import unittest.mock as mock
import json
import logging
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from backend.main import app
from backend.middleware.twa_auth import generate_jwt
from backend.config import settings
from backend.db.connection import get_db
from backend.services.encryption import encrypt
from backend.services.rate_limiter import RateLimitExceeded

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

class MockCursor:
    def __init__(self):
        self.executed = []
        self.fetchone_val = None
        self.fetchall_val = []
        self.items_rows = []
        self.reminders_rows = []
        self.quizzes_rows = []
        self._items_iter = None
        self._reminders_iter = None
        self._quizzes_iter = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def execute(self, query, params=None):
        self.executed.append((query, params))
        query_lower = query.lower()
        if "items" in query_lower:
            self._items_iter = iter(self.items_rows)
        elif "reminders" in query_lower:
            self._reminders_iter = iter(self.reminders_rows)
        elif "quizzes" in query_lower:
            self._quizzes_iter = iter(self.quizzes_rows)

    async def fetchone(self):
        return self.fetchone_val

    async def fetchall(self):
        return self.fetchall_val

    def __aiter__(self):
        return self

    async def __anext__(self):
        # Determine which iterator to use based on the last executed query
        last_query = self.executed[-1][0].lower() if self.executed else ""
        if "items" in last_query and self._items_iter is not None:
            try:
                return next(self._items_iter)
            except StopIteration:
                raise StopAsyncIteration
        elif "reminders" in last_query and self._reminders_iter is not None:
            try:
                return next(self._reminders_iter)
            except StopIteration:
                raise StopAsyncIteration
        elif "quizzes" in last_query and self._quizzes_iter is not None:
            try:
                return next(self._quizzes_iter)
            except StopIteration:
                raise StopAsyncIteration
        raise StopAsyncIteration

class MockConnection:
    def __init__(self, cursor_inst):
        self.cursor_inst = cursor_inst

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def cursor(self):
        return self.cursor_inst

    async def commit(self):
        pass

@pytest.fixture()
def mock_db_connection():
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

def test_export_requires_auth(client, mock_db_connection):
    """GET /api/export should block unauthorized requests and return 401."""
    resp = client.get("/api/export")
    assert resp.status_code == 401

def test_export_success(client, mock_db_connection, caplog):
    """GET /api/export successfully streams data portability JSON and logs audit record."""
    # Authenticated session cookie
    payload = {"sub": "123456789", "chat_id": "123456789"}
    token = generate_jwt(payload, settings.JWT_SECRET)

    # Mock DB returns
    mock_db_connection.fetchone_val = ("123456789", 5, 330, datetime.now(timezone.utc))
    
    mock_db_connection.items_rows = [
        (101, "url", "https://example.com", encrypt("Decrypted Content 1"), "summary 1", "title 1", ["tag1"], datetime.now(timezone.utc)),
        (102, "text", None, None, "summary 2", "title 2", None, datetime.now(timezone.utc)),
    ]
    mock_db_connection.reminders_rows = [
        (201, 101, "Send reminder 1", datetime.now(timezone.utc), "pending", datetime.now(timezone.utc))
    ]
    mock_db_connection.quizzes_rows = [
        (301, 101, "Question 1", ["opt1", "opt2"], 0, "exp", 2.5, 3, datetime.now(timezone.utc).date(), datetime.now(timezone.utc))
    ]

    with caplog.at_level(logging.INFO), \
         mock.patch("backend.services.rate_limiter.check_rate_limit", new_callable=mock.AsyncMock, return_value=True):
        resp = client.get("/api/export", cookies={"recall_session": token})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"
        
        # Check attachment disposition headers
        disp = resp.headers["content-disposition"]
        assert "attachment" in disp
        assert "recall-export-" in disp
        assert ".json" in disp

        # Retrieve full stream payload
        data = resp.json()
        assert "export_date" in data
        assert data["user"]["telegram_chat_id"] == "123456789"
        assert data["user"]["streak_count"] == 5
        assert data["user"]["timezone_offset"] == 330
        
        # Verify items mapping and decryption
        assert len(data["items"]) == 2
        assert data["items"][0]["id"] == 101
        assert data["items"][0]["raw_text_decrypted"] == "Decrypted Content 1"
        assert data["items"][1]["raw_text_decrypted"] is None
        
        # Ensure credentials columns are not present in export
        assert "google_refresh_token" not in data["user"]
        assert "google_refresh_token" not in data

        # Verify reminders and quizzes
        assert len(data["reminders"]) == 1
        assert data["reminders"][0]["message"] == "Send reminder 1"
        assert len(data["quizzes"]) == 1
        assert data["quizzes"][0]["question"] == "Question 1"

        # Verify audit logging
        audit_logs = [record.message for record in caplog.records if "Audit Log - Export completed:" in record.message]
        assert len(audit_logs) == 1
        assert "user_id=123456789" in audit_logs[0]
        assert "item_count=2" in audit_logs[0]

def test_export_rate_limit_429(client, mock_db_connection):
    """A second request within 24 hours triggers a RateLimitExceeded and returns 429."""
    payload = {"sub": "42", "chat_id": "123456789"}
    token = generate_jwt(payload, settings.JWT_SECRET)
    mock_db_connection.fetchone_val = ("42", 5, 330, datetime.now(timezone.utc))

    with mock.patch("backend.services.rate_limiter.check_rate_limit", side_effect=RateLimitExceeded(retry_after=43200.0)):
        resp = client.get("/api/export", cookies={"recall_session": token})
        assert resp.status_code == 429
        assert resp.headers["retry-after"] == "43200"
        assert resp.json() == {
            "error": "rate_limit_exceeded",
            "retry_after": 43200
        }
