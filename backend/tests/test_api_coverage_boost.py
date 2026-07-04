import pytest
import unittest.mock as mock
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from backend.main import app
from backend.middleware.twa_auth import UserContext, get_current_user, generate_jwt
from backend.config import settings
from backend.db.connection import get_db

class MockCursor:
    def __init__(self):
        self.executed = []
        self.now = datetime.now(timezone.utc)
        self.today = self.now.date()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def execute(self, query, params=None):
        self.executed.append((query, params))

    async def fetchone(self):
        query = self.executed[-1][0].lower() if self.executed else ""
        if "max(created_at)" in query:
            return (self.now,)
        elif "timezone_offset" in query:
            return (0, 5, None, None, True)
        elif "self_description" in query:
            return ("developer", "Synthesis", "summary text", "trajectory text", 85)
        elif "count(*)" in query or "count(" in query:
            return (10,)
        elif "streak_count" in query:
            return (5, self.today, False, 0)
        elif "items" in query:
            return (101, "Test Item", "url", "https://example.com", "Summary 1", ["tag1"], self.now, "title")
        return (42, "123456", "Test User")

    async def fetchall(self):
        query = self.executed[-1][0].lower() if self.executed else ""
        if "from reminders" in query:
            return [(1, 101, "msg", self.now, "pending", self.now)]
        elif "from quizzes" in query:
            return [(1, 101, "q?", ["a", "b"], 0, "exp", 2.5, 3, self.today, self.now)]
        elif "generate_series" in query:
            return [(self.today, True), (self.today, True)]
        elif "cross join" in query or "lateral" in query:
            return [(101, 102, 0.1)]
        elif "semantic_hubs" in query:
            return [(1, "Hub 1", [101], self.now, 3)]
        elif "raw_text" in query:
            return [(101, "url", "https://example.com", "raw text", "Summary 1", "Test Title", ["tag1"], self.now)]
        elif "left join quizzes" in query or "from items i" in query:
            return [(101, "Test Title", "Summary 1", "url", "https://example.com", ["tag1"], self.now, "note", 2.5, 3, self.today)]
        elif "items" in query:
            return [(101, "Test Item", "url", self.now)]
        return [(101, "Test Item", "url", "https://example.com", "Summary 1", ["tag1"], self.now)]

    def __aiter__(self):
        async def _gen():
            rows = await self.fetchall()
            for r in rows:
                yield r
        return _gen()

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

@pytest.fixture
def mock_db():
    cursor = MockCursor()
    return MockConnection(cursor)

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

def get_auth_cookie():
    payload = {"sub": "42", "chat_id": "123456"}
    return {"recall_session": generate_jwt(payload, settings.JWT_SECRET)}

def test_api_me_endpoint(client):
    with mock.patch("backend.services.user_service.get_and_update_user_streak", new_callable=mock.AsyncMock, return_value=5):
        res = client.get("/api/me", cookies=get_auth_cookie())
        assert res.status_code == 200

def test_api_items_list(client):
    res = client.get("/api/items?limit=10&offset=0", cookies=get_auth_cookie())
    assert res.status_code == 200

def test_api_search_endpoint(client):
    with mock.patch("backend.services.rate_limiter.check_rate_limit", new_callable=mock.AsyncMock, return_value=True), \
         mock.patch("backend.services.search_service.hybrid_search", new_callable=mock.AsyncMock, return_value=[]):
        res = client.post("/api/search", json={"query": "fastapi"}, cookies=get_auth_cookie())
        assert res.status_code == 200

def test_api_graph_endpoint(client):
    with mock.patch("backend.services.redis_client.redis.get", new_callable=mock.AsyncMock, return_value=None), \
         mock.patch("backend.services.redis_client.redis.setex", new_callable=mock.AsyncMock, return_value=True):
        res = client.get("/api/graph", cookies=get_auth_cookie())
        assert res.status_code == 200

def test_api_export_endpoint(client):
    with mock.patch("backend.services.rate_limiter.check_rate_limit", new_callable=mock.AsyncMock, return_value=True):
        res = client.get("/api/export", cookies=get_auth_cookie())
        assert res.status_code == 200

def test_api_pulse_endpoint(client):
    res = client.get("/api/pulse", cookies=get_auth_cookie())
    assert res.status_code == 200

def test_api_delete_item(client):
    with mock.patch("backend.services.redis_client.redis.delete", new_callable=mock.AsyncMock, return_value=1):
        res = client.delete("/api/items/101", cookies=get_auth_cookie())
        assert res.status_code in [200, 204, 404]
