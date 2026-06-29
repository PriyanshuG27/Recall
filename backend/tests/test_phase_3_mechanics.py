import pytest
import datetime
from datetime import timezone
import unittest.mock as mock
from fastapi.testclient import TestClient

from backend.main import app
from backend.worker import compute_passive_context
from backend.scheduler.scheduler import near_miss_calibration, recall_moment_dispatcher
from backend.middleware.twa_auth import generate_jwt
from backend.db.connection import get_db
from backend.config import settings

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


# --- Mock Database Infrastructure ---

class MockCursor:
    def __init__(self, fetchone_result=None, fetchall_result=None):
        self.executed = []
        self.fetchone_result = fetchone_result
        self.fetchall_result = fetchall_result or []
        self.rowcount = 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def execute(self, query, params=None):
        self.executed.append((query, params))

    async def fetchone(self):
        if self.fetchone_result is not None:
            return self.fetchone_result
        query_lower = self.executed[-1][0].lower() if self.executed else ""
        if "timezone_offset" in query_lower:
            return (330,)  # +5.5 hours (IST)
        if "count" in query_lower:
            return (2,)
        if "users" in query_lower:
            return (42, "123456")
        return None

    async def fetchall(self):
        return self.fetchall_result


class MockConnection:
    def __init__(self, cursor_inst):
        self.cursor_inst = cursor_inst

    def cursor(self):
        return self.cursor_inst

    async def commit(self):
        pass


class MockPool:
    def __init__(self, conn_inst):
        self.conn_inst = conn_inst

    def connection(self):
        class ConnContext:
            def __init__(self, conn):
                self.conn = conn
            async def __aenter__(self):
                return self.conn
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        return ConnContext(self.conn_inst)


# --- 1. Ingestion Time-of-Day Bucketing Tests ---

@pytest.mark.asyncio
async def test_time_bucketing_morning():
    """Verify hour mapping correctly assigns morning time bucket."""
    mock_cur = MockCursor(fetchone_result=(0,))
    mock_conn = MockConnection(mock_cur)

    target_dt = datetime.datetime(2026, 6, 29, 8, 0, 0, tzinfo=timezone.utc)
    with mock.patch("backend.worker.datetime") as mock_dt:
        mock_dt.now.return_value = target_dt
        mock_dt.timedelta = datetime.timedelta

        res_json = await compute_passive_context(42, "text", mock_conn)
        import json
        bucket = json.loads(res_json).get("time_of_day")
        assert bucket == "morning"


@pytest.mark.asyncio
async def test_time_bucketing_night_with_offset():
    """Verify timezone offset correctly adjusts UTC time into night bucket."""
    mock_cur = MockCursor(fetchone_result=(330,))
    mock_conn = MockConnection(mock_cur)

    target_dt = datetime.datetime(2026, 6, 29, 19, 30, 0, tzinfo=timezone.utc)
    with mock.patch("backend.worker.datetime") as mock_dt:
        mock_dt.now.return_value = target_dt
        mock_dt.timedelta = datetime.timedelta

        res_json = await compute_passive_context(42, "text", mock_conn)
        import json
        bucket = json.loads(res_json).get("time_of_day")
        assert bucket == "night"


# --- 2. Near-Miss Calibration Math Tests ---

@pytest.mark.asyncio
async def test_near_miss_calibration_narrow_band():
    """Verify threshold increases when conversion rate is < 20%."""
    near_miss_rows = [
        (1, 10, 11, 0.72, datetime.datetime.now() - datetime.timedelta(days=15)),
        (2, 12, 13, 0.73, datetime.datetime.now() - datetime.timedelta(days=16))
    ]
    
    mock_cur = MockCursor(fetchall_result=near_miss_rows)
    async def custom_fetchone():
        last_query = mock_cur.executed[-1][0].lower() if mock_cur.executed else ""
        if "near_miss_lower_bound" in last_query:
            return (0.710,)
        return None
    mock_cur.fetchone = custom_fetchone
    
    mock_conn = MockConnection(mock_cur)
    mock_pool = MockPool(mock_conn)

    with mock.patch("backend.scheduler.scheduler.get_pool", return_value=mock_pool):
        mock_cur.fetchall_result = near_miss_rows
        async def custom_fetchall():
            last_query = mock_cur.executed[-1][0].lower() if mock_cur.executed else ""
            if "near_miss_lower_bound" in last_query:
                return [(42, 0.710)]
            return near_miss_rows
        mock_cur.fetchall = custom_fetchall

        await near_miss_calibration()
        
        updates = [ex for ex in mock_cur.executed if "UPDATE users" in ex[0]]
        assert len(updates) == 1
        assert float(updates[0][1][0]) == pytest.approx(0.720)


@pytest.mark.asyncio
async def test_near_miss_calibration_widen_band():
    """Verify threshold decreases when conversion rate is > 60%."""
    near_miss_rows = [
        (1, 10, 11, 0.72, datetime.datetime.now() - datetime.timedelta(days=15))
    ]
    
    mock_cur = MockCursor()
    async def custom_fetchone():
        last_query = mock_cur.executed[-1][0].lower() if mock_cur.executed else ""
        if "near_miss_lower_bound" in last_query:
            return (0.710,)
        if "confirmed" in last_query:
            return (1,)
        return None
    mock_cur.fetchone = custom_fetchone
    
    mock_conn = MockConnection(mock_cur)
    mock_pool = MockPool(mock_conn)

    with mock.patch("backend.scheduler.scheduler.get_pool", return_value=mock_pool):
        async def custom_fetchall():
            last_query = mock_cur.executed[-1][0].lower() if mock_cur.executed else ""
            if "near_miss_lower_bound" in last_query:
                return [(42, 0.710)]
            return near_miss_rows
        mock_cur.fetchall = custom_fetchall

        await near_miss_calibration()
        
        updates = [ex for ex in mock_cur.executed if "UPDATE users" in ex[0]]
        assert len(updates) == 1
        assert float(updates[0][1][0]) == pytest.approx(0.700)


# --- 3. Recall Moment Limits and Time Jitter Tests ---

@pytest.mark.asyncio
async def test_recall_moment_skips_recent_sends():
    """Verify scheduler skips user if they had a Recall Moment in the last 7 days."""
    last_sent = datetime.datetime.now(timezone.utc) - datetime.timedelta(days=2)
    users_rows = [(42, "123456", 0, last_sent)]

    mock_cur = MockCursor(fetchall_result=users_rows)
    mock_conn = MockConnection(mock_cur)
    mock_pool = MockPool(mock_conn)

    with mock.patch("backend.scheduler.scheduler.get_pool", return_value=mock_pool):
        await recall_moment_dispatcher()
        candidate_queries = [ex for ex in mock_cur.executed if "insight_candidates" in ex[0]]
        assert len(candidate_queries) == 0


@pytest.mark.asyncio
async def test_recall_moment_skips_outside_hours():
    """Verify scheduler skips user if local time is outside 10:00 AM - 4:00 PM window."""
    users_rows = [(42, "123456", 0, None)]
    mock_cur = MockCursor(fetchall_result=users_rows)
    mock_conn = MockConnection(mock_cur)
    mock_pool = MockPool(mock_conn)

    target_dt = datetime.datetime(2026, 6, 29, 23, 0, 0, tzinfo=timezone.utc)
    with mock.patch("backend.scheduler.scheduler.get_pool", return_value=mock_pool), \
         mock.patch("backend.scheduler.scheduler.datetime.datetime") as mock_dt:
        mock_dt.now.return_value = target_dt
        
        await recall_moment_dispatcher()
        candidate_queries = [ex for ex in mock_cur.executed if "insight_candidates" in ex[0]]
        assert len(candidate_queries) == 0


# --- 4. Active Candidates API Endpoint Tests ---

@pytest.fixture()
def override_db():
    async def _mock_get_db():
        candidate_rows = [
            (1, 10, 11, 0.73, datetime.datetime.now(timezone.utc) + datetime.timedelta(hours=5), "delivered", "Tension insight")
        ]
        yield MockConnection(MockCursor(fetchall_result=candidate_rows))
    app.dependency_overrides[get_db] = _mock_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


def test_get_active_candidates_api(override_db):
    """Verify active candidates API returns correct format and status code."""
    with mock.patch("backend.db.connection.open_pool", return_value=None), \
         mock.patch("backend.db.connection.close_pool", return_value=None), \
         mock.patch("backend.routes.api.rate_limit", return_value=lambda x: None):
             
        token = generate_jwt({"sub": "42"}, settings.JWT_SECRET)
        headers = {"Authorization": f"Bearer {token}"}
        
        with TestClient(app) as client:
            res = client.get("/api/candidates/active", headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert len(data) == 1
            assert data[0]["item_id_a"] == 10
            assert data[0]["item_id_b"] == 11
            assert data[0]["similarity_score"] == 0.73
            assert data[0]["status"] == "delivered"


def test_callback_query_candidate_confirm(override_db):
    """Verify that clicking 'Keep Connection' updates candidate in DB and removes from Redis."""
    with mock.patch("backend.db.connection.open_pool", return_value=None), \
         mock.patch("backend.db.connection.close_pool", return_value=None), \
         mock.patch("backend.routes.webhook.redis") as mock_redis, \
         mock.patch("backend.routes.webhook.http_client") as mock_http:
             
        mock_redis.zrem = mock.AsyncMock(return_value=1)
        mock_http.post = mock.AsyncMock()

        payload = {
            "update_id": 99999,
            "callback_query": {
                "id": "cb_id_123",
                "from": {"id": 12345, "is_bot": False, "first_name": "Test"},
                "message": {
                    "message_id": 8888,
                    "chat": {"id": 7732257445, "type": "private"},
                    "text": "Insight connecting checklist and Chernobyl\n💡 This connection expires in 6 hours!"
                },
                "data": "candidate_confirm:1"
            }
        }
        
        with TestClient(app) as client:
            res = client.post("/webhook", json=payload)
            assert res.status_code == 200
            mock_redis.zrem.assert_called_once_with("reminders:active", "drift:1")
            called_urls = [args[0][0] for args in mock_http.post.call_args_list]
            assert any("editMessageText" in url for url in called_urls)
