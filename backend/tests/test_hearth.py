import pytest
import time
import json
import unittest.mock as mock
from datetime import datetime, timezone, timedelta
from fastapi import Depends
from fastapi.testclient import TestClient

from backend.main import app
from backend.middleware.twa_auth import get_current_user, generate_jwt, UserContext
from backend.config import settings
from backend.db.connection import get_db
from backend.routes.hearth import shared_days_to_score, get_stage

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


# ── Score & Stage Formula tests ──────────────────────────────────────────────

def test_shared_days_to_score_curve():
    # Curve maps:
    # 0 days -> 0 score
    # 20 days -> 16 score
    # 40 days -> 33 score
    # 65 days -> 52 score
    # 120 days -> 73 score
    # 200 days -> capped at 96 score
    assert shared_days_to_score(0) == 0.0
    assert shared_days_to_score(20) == 16.0
    assert shared_days_to_score(40) == 33.0
    assert shared_days_to_score(65) == 52.0
    assert shared_days_to_score(120) == 72.9
    assert shared_days_to_score(200) == 96.0
    assert shared_days_to_score(1000) == 96.0


def test_get_stage():
    assert get_stage(0) == "Hut"
    assert get_stage(19) == "Hut"
    assert get_stage(20) == "Cottage"
    assert get_stage(39) == "Cottage"
    assert get_stage(40) == "House"
    assert get_stage(64) == "House"
    assert get_stage(65) == "Manor"
    assert get_stage(119) == "Manor"
    assert get_stage(120) == "Villa"
    assert get_stage(199) == "Villa"
    assert get_stage(200) == "Castle"


# ── Mocking DB layer ──────────────────────────────────────────────────────────

class RecordingCursor:
    def __init__(self, user_id=42, fetchone_val=None, fetchall_val=None, fetchval_val=None):
        self.executed = []
        self.user_id = user_id
        self.fetchone_val = fetchone_val
        self.fetchall_val = fetchall_val or []
        self.fetchval_val = fetchval_val

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def execute(self, query, params=None):
        self.executed.append((query, params))

    async def fetchone(self):
        # Specific overrides for query targets
        last_query = self.executed[-1][0].lower() if self.executed else ""
        
        # 1. Select 1 presence checks (highest priority)
        if "select 1" in last_query:
            return (1,) if self.fetchval_val else None

        # 2. User details
        if "from users" in last_query:
            if "telegram_chat_id" in last_query:
                return (self.user_id, "123456789")
            return ("Alice", "alice_user")

        # 3. Invite details
        if "from journey_invites" in last_query:
            if self.fetchone_val is not None:
                return self.fetchone_val
            if self.fetchval_val:
                return (self.fetchval_val,)
            return None

        # 4. Pair details
        if "from journey_pairs" in last_query:
            if self.fetchone_val is not None:
                return self.fetchone_val
            if self.fetchval_val:
                return (self.fetchval_val,)
            return None

        return self.fetchone_val

    async def fetchval(self, query, *args):
        self.executed.append((query, args))
        last_query = query.lower()
        
        if "from journey_pairs" in last_query:
            return self.fetchval_val

        if "from journey_invites" in last_query:
            return self.fetchval_val

        if "from items" in last_query:
            return self.fetchval_val

        return self.fetchval_val

    async def fetchrow(self, query, *args):
        # fetchrow mapping for asyncpg-style helpers
        self.executed.append((query, args))
        last_query = query.lower()
        
        if "from journey_pairs" in last_query:
            return self.fetchone_val

        if "from users" in last_query:
            return {"first_name": "Alice", "username": "alice_user", "telegram_chat_id": "123456789"}

        if "from journey_invites" in last_query:
            return self.fetchone_val

        return self.fetchone_val

    async def fetchall(self):
        return self.fetchall_val


class RecordingConnection:
    def __init__(self, cursor_inst):
        self.cursor_inst = cursor_inst
        self.committed = False

    def cursor(self, *args, **kwargs):
        return self.cursor_inst

    def transaction(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def execute(self, query, *args):
        await self.cursor_inst.execute(query, args)
        return self.cursor_inst

    async def fetchrow(self, query, *args):
        return await self.cursor_inst.fetchrow(query, *args)

    async def fetchval(self, query, *args):
        return await self.cursor_inst.fetchval(query, *args)

    async def commit(self):
        self.committed = True


current_cursor = RecordingCursor(user_id=42)

@pytest.fixture(autouse=True)
def override_db():
    global current_cursor
    current_cursor = RecordingCursor(user_id=42)

    async def _mock_get_db():
        yield RecordingConnection(current_cursor)

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


# ── Endpoint Tests ────────────────────────────────────────────────────────────

def test_get_hearth_unpaired(client):
    """GET /api/hearth returns empty journeys list if no active pair exists."""
    global current_cursor
    current_cursor.fetchall_val = []  # No pairs in DB
    
    token = get_auth_token(user_id=42)
    response = client.get("/api/hearth", cookies={"recall_session": token})
    
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["journeys"] == []


def test_get_hearth_paired(client):
    """GET /api/hearth returns paired details when user is in a pair."""
    global current_cursor
    # Mock active pair row
    current_cursor.fetchall_val = [{
        "id": 5,
        "user_a_id": 42,
        "user_b_id": 99,
        "shared_days": 35,
        "created_at": datetime.now(timezone.utc)
    }]
    # Mock partner activity
    current_cursor.fetchval_val = 1
    
    token = get_auth_token(user_id=42)
    response = client.get("/api/hearth", cookies={"recall_session": token})
    
    assert response.status_code == 200
    res_data = response.json()
    assert len(res_data["journeys"]) == 1
    journey = res_data["journeys"][0]
    assert journey["pair_id"] == "5"
    assert journey["is_paired"] is True
    assert journey["shared_days"] == 35
    assert journey["score"] == 28.75  # 16 + (35 - 20) * 0.85
    assert journey["stage"] == "Cottage"
    assert journey["partner_name"] == "Alice"
    assert journey["partner_active_today"] is True
    assert journey["self_active_today"] is True


def test_get_hearth_status(client):
    """GET /api/hearth/status returns quick boolean fields."""
    global current_cursor
    current_cursor.fetchval_val = True
    
    token = get_auth_token(user_id=42)
    response = client.get("/api/hearth/status", cookies={"recall_session": token})
    
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["is_paired"] is True
    assert res_data["has_pending_invite"] is True


def test_create_invite_multiple_pairs_allowed(client):
    """POST /api/hearth/invite succeeds even if user is already paired."""
    current_cursor.fetchval_val = None
    current_cursor.fetchone_val = None  # No existing pending invite
    
    token = get_auth_token(user_id=42)
    response = client.post("/api/hearth/invite", cookies={"recall_session": token})
    
    assert response.status_code == 200
    res_data = response.json()
    assert "invite_code" in res_data
    assert res_data["invite_code"].startswith("RCL-")


def test_leave_journey_success(client):
    """DELETE /api/hearth/leave/{pair_id} deletes the pair and sends Telegram notice."""
    global current_cursor
    # Mock finding the pair where user is a member
    current_cursor.fetchone_val = {
        "id": 5,
        "user_a_id": 42,
        "user_b_id": 99
    }
    
    with mock.patch("backend.routes.hearth._notify_telegram", return_value=None) as mock_notify:
        token = get_auth_token(user_id=42)
        response = client.delete("/api/hearth/leave/5", cookies={"recall_session": token})
        
        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_notify.assert_called_once()


def test_create_invite_success(client):
    """POST /api/hearth/invite creates a new code or returns active pending one."""
    global current_cursor
    current_cursor.fetchval_val = None  # Not paired
    current_cursor.fetchone_val = None  # No existing pending invite
    
    token = get_auth_token(user_id=42)
    response = client.post("/api/hearth/invite", cookies={"recall_session": token})
    
    assert response.status_code == 200
    res_data = response.json()
    assert "invite_code" in res_data
    assert res_data["invite_code"].startswith("RCL-")
    assert "invite_url" in res_data


def test_accept_invite_self(client):
    """POST /api/hearth/accept fails when attempting to pair with oneself."""
    global current_cursor
    # Inviter ID is 42 (same as current user)
    current_cursor.fetchone_val = {
        "id": 10,
        "inviter_id": 42
    }
    
    token = get_auth_token(user_id=42)
    response = client.post("/api/hearth/accept", json={"invite_code": "RCL-1234-5678"}, cookies={"recall_session": token})
    
    assert response.status_code == 400
    assert "Cannot pair with yourself" in response.json()["detail"]


def test_accept_invite_success(client):
    """POST /api/hearth/accept pairs both users successfully and sends Telegram notice."""
    global current_cursor
    # Invite is valid, inviter is user 99
    current_cursor.fetchone_val = {
        "id": 10,
        "inviter_id": 99
    }
    current_cursor.fetchval_val = None  # Neither is already paired
    
    with mock.patch("backend.routes.hearth._notify_telegram", return_value=None) as mock_notify:
        token = get_auth_token(user_id=42)
        response = client.post("/api/hearth/accept", json={"invite_code": "RCL-9999-0000"}, cookies={"recall_session": token})
        
        assert response.status_code == 200
        res_data = response.json()
        assert res_data["success"] is True
        assert res_data["message"] == "Hearth lit"
        mock_notify.assert_called_once()


@pytest.mark.asyncio
async def test_scheduler_tick_hearth_shared_days():
    """tick_hearth_shared_days increments shared_days for pairs where both users saved items yesterday."""
    from backend.scheduler.scheduler import tick_hearth_shared_days
    
    # Mock database connection and cursor
    mock_cursor = mock.AsyncMock()
    mock_conn = mock.AsyncMock()
    mock_conn.execute.return_value = mock_cursor
    mock_conn.fetchval = mock.AsyncMock()
    
    # 1. Mock active pairs
    # Pair 1: user 42 and 99
    # Pair 2: user 10 and 11
    mock_cursor.fetchall.return_value = [
        (1, 42, 99),
        (2, 10, 11)
    ]
    
    # 2. Mock fetchval returns:
    # For Pair 1: both active (returns 1 for both)
    # For Pair 2: only one active (returns 1 for user 10, None for user 11)
    side_effects = [
        1, # user 42 active
        1, # user 99 active
        1, # user 10 active
        None # user 11 inactive
    ]
    mock_conn.fetchval.side_effect = side_effects
    
    class MockConnectionContext:
        def __init__(self, conn):
            self.conn = conn
        async def __aenter__(self):
            return self.conn
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    class MockPool:
        def __init__(self, conn):
            self.conn = conn
        def connection(self):
            return MockConnectionContext(self.conn)

    mock_pool = MockPool(mock_conn)
    
    with mock.patch("backend.scheduler.scheduler.get_pool", return_value=mock_pool):
        await tick_hearth_shared_days()
        
        # Verify db queries
        # Pair 1: should update
        # Pair 2: should not update
        # Check execute calls for UPDATE
        update_calls = [
            c for c in mock_conn.execute.call_args_list 
            if "UPDATE journey_pairs" in c[0][0]
        ]
        assert len(update_calls) == 1
        assert update_calls[0][0][1] == (1,) # Pair ID 1 was updated

