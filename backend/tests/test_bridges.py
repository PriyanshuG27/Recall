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

class RecordingCursor:
    def __init__(self, user_id=42, fetchone_val=None, fetchall_val=None, milestones=None):
        self.executed = []
        self.user_id = user_id
        self.fetchone_val = fetchone_val
        self.fetchall_val = fetchall_val or []
        self.milestones = milestones or {"unlocked": ["compatibility"]}
        self.item_count = 100
        self.rowcount = 1
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
        
    async def execute(self, query, params=None):
        self.executed.append((query, params))
        
    async def fetchone(self):
        last_query = self.executed[-1][0].lower() if self.executed else ""
        if "returning id" in last_query:
            return (15,)  # returning new bridge ID
        if "select id from cognitive_bridges" in last_query:
            return None
        if "cognitive_bridges" in last_query:
            return self.fetchone_val
        if "node_milestones" in last_query:
            return (self.milestones,)
        if "users" in last_query and "id =" in last_query:
            return (self.user_id, "123456789")
        if "count(*)" in last_query:
            return (self.item_count,)
        return self.fetchone_val
        
    async def fetchall(self):
        last_query, last_params = self.executed[-1] if self.executed else ("", None)
        last_query = last_query.lower()
        if "embedding <=> b.embedding" in last_query:
            now = datetime.now(timezone.utc)
            mock_emb = [0.05] * 384
            return [
                (101, "FastAPI Concurrency", "Asyncio event loop in detail", "Tech & Systems", mock_emb, 201, "Async Python", "Event loops in python", "Tech & Systems", mock_emb, 0.85, now, now),
                (102, "Stoicism Tips", "Marcus Aurelius notes", "Philosophy & Reflection", mock_emb, 202, "Meditations Notes", "Stoic philosophy overview", "Philosophy & Reflection", mock_emb, 0.72, now, now)
            ]
        if "tags" in last_query:
            if last_params and last_params[0] == 42:
                return [
                    (["python", "asyncio"],)
                ]
            else:
                return [
                    (["stoicism", "philosophy"],)
                ]
        if "save_time_bucket" in last_query:
            return [
                ("morning", 12),
                ("night", 25)
            ]
        return self.fetchall_val

class RecordingConnection:
    def __init__(self, cursor_inst):
        self.cursor_inst = cursor_inst
        self.committed = False
        
    def cursor(self):
        return self.cursor_inst
        
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

# ── Tests ─────────────────────────────────────────────────────────────────────

def test_list_bridges_success(client):
    """GET /api/bridges returns List[BridgeListItem] successfully."""
    global current_cursor
    dt = datetime.now(timezone.utc)
    mock_bridges = [
        (10, 42, 99, 85.5, dt, "Alice", None, None, "Bob", None, "BLVN")
    ]
    current_cursor.fetchall_val = mock_bridges
    
    token = get_auth_token(user_id=42)
    response = client.get("/api/bridges", cookies={"recall_session": token})
    
    assert response.status_code == 200
    res_data = response.json()
    assert len(res_data) == 1
    assert res_data[0]["id"] == 10
    assert res_data[0]["friend_id"] == 99
    assert res_data[0]["friend_name"] == "Bob"
    assert res_data[0]["compatibility_score"] == 85.5

def test_generate_invite_locked(client):
    """POST /api/bridges/invite returns 403 Forbidden if milestones are locked."""
    global current_cursor
    current_cursor.milestones = {"unlocked": []}
    current_cursor.item_count = 12
    
    token = get_auth_token(user_id=42)
    response = client.post("/api/bridges/invite", cookies={"recall_session": token})
    assert response.status_code == 403
    assert "Milestone locked" in response.json()["detail"]

def test_generate_invite_success(client):
    """POST /api/bridges/invite generates a connection code if unlocked."""
    global current_cursor
    current_cursor.milestones = {"unlocked": ["compatibility"]}
    current_cursor.item_count = 55
    
    token = get_auth_token(user_id=42)
    response = client.post("/api/bridges/invite", cookies={"recall_session": token})
    assert response.status_code == 200
    res_data = response.json()
    assert "code" in res_data
    assert res_data["code"].startswith("MIND-")

def test_connect_self_invite(client):
    """POST /api/bridges/connect returns 400 when trying to connect using own code."""
    global current_cursor
    current_cursor.milestones = {"unlocked": ["compatibility"]}
    current_cursor.item_count = 55
    # invite inviter is same as current user (42)
    current_cursor.fetchone_val = (42,)
    
    token = get_auth_token(user_id=42)
    response = client.post("/api/bridges/connect", json={"code": "MIND-1234-5678"}, cookies={"recall_session": token})
    assert response.status_code == 400
    assert "cannot connect with yourself" in response.json()["detail"]

def test_connect_success(client):
    """POST /api/bridges/connect establishes a connection with a friend's code."""
    global current_cursor
    current_cursor.milestones = {"unlocked": ["compatibility"]}
    current_cursor.item_count = 55
    # invite inviter is friend (99)
    current_cursor.fetchone_val = (99,)
    
    token = get_auth_token(user_id=42)
    response = client.post("/api/bridges/connect", json={"code": "MIND-8888-9999"}, cookies={"recall_session": token})
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "connected"
    assert res_data["bridge_id"] == 15



def test_get_bridge_details_access_denied(client):
    """GET /api/bridges/{id} returns 403 if user is not member of bridge."""
    global current_cursor
    # User 42 is not part of bridge (bridge has 88 and 99)
    current_cursor.fetchone_val = (10, 88, 99, 75.0, "Friend1", None, "FLVN", "Friend2", None, "BLVN", datetime.now(timezone.utc), datetime.now(timezone.utc), datetime.now(timezone.utc), datetime.now(timezone.utc))
    
    token = get_auth_token(user_id=42)
    response = client.get("/api/bridges/10", cookies={"recall_session": token})
    assert response.status_code == 403

def test_get_bridge_details_success(client):
    """GET /api/bridges/{id} returns detailed overlap matrix successfully."""
    global current_cursor
    # Current user (42) and friend (99)
    current_cursor.fetchone_val = (10, 42, 99, 78.5, "Alice", None, "FLVN", "Bob", None, "BLVN", datetime.now(timezone.utc), datetime.now(timezone.utc), datetime.now(timezone.utc), datetime.now(timezone.utc))
    
    # Mock LLM response to avoid live calls
    with mock.patch("backend.services.ai_cascade.AICascade.call_llm", return_value="Dynamic synergy text description mock."):
        token = get_auth_token(user_id=42)
        response = client.get("/api/bridges/10", cookies={"recall_session": token})
        
        assert response.status_code == 200
        res_data = response.json()
        assert res_data["id"] == 10
        assert res_data["friend_name"] == "Bob"
        assert res_data["compatibility_score"] == 78.5
        assert len(res_data["synapses"]) == 2
        assert res_data["synapses"][0]["item_a"]["title"] == "FastAPI Concurrency"
        assert res_data["synapses"][0]["item_b"]["title"] == "Async Python"
        assert res_data["unique_user"] == ["python", "asyncio"]
        assert res_data["synergy_narrative"] == "Dynamic synergy text description mock."

def test_delete_bridge_success(client):
    """DELETE /api/bridges/{id} deletes the connection if authorized."""
    global current_cursor
    current_cursor.fetchone_val = (10, 42, 99)
    
    token = get_auth_token(user_id=42)
    response = client.delete("/api/bridges/10", cookies={"recall_session": token})
    assert response.status_code == 200
    assert response.json()["status"] == "deleted"
    
    # Verify DB queries: auth, check, delete
    assert len(current_cursor.executed) == 3
    assert "DELETE FROM cognitive_bridges" in current_cursor.executed[2][0]

def test_update_bridge_ceremony_success(client):
    """POST /api/bridges/{id}/ceremony updates the last ceremony timestamp."""
    global current_cursor
    current_cursor.fetchone_val = (10, 42, 99)
    
    token = get_auth_token(user_id=42)
    response = client.post("/api/bridges/10/ceremony", cookies={"recall_session": token})
    assert response.status_code == 200
    assert response.json()["status"] == "updated"
    
    # Verify DB queries: auth, check, update
    assert "UPDATE cognitive_bridges SET last_ceremony_at" in current_cursor.executed[2][0]
def test_kintsugi_decay_progression():
    """Test that a stone progresses through all 5 decay stages on successive inactive cycles."""
    from backend.routes.bridges import simulate_kintsugi_decay, SynapsePair, ThoughtBrief
    
    bridge_created = datetime.now(timezone.utc) - timedelta(days=50)
    syn_date = bridge_created + timedelta(days=2)
    syn = SynapsePair(
        item_a=ThoughtBrief(id=1, title="A", summary="S", created_at=syn_date),
        item_b=ThoughtBrief(id=2, title="B", summary="S", created_at=syn_date),
        similarity=0.8
    )
    
    # Day 43 = 6 complete cycles. Cycle 0 active, Cycles 1,2,3,4,5 inactive. 5 decays.
    sim_time = bridge_created + timedelta(days=43)
    
    syns_res, inactive, active_rep, front = simulate_kintsugi_decay(bridge_created, [syn], sim_time)
    
    assert len(syns_res) == 1
    assert syns_res[0].decay_stage == "BROKEN"
    assert syns_res[0].has_gold_seam is True
    assert inactive == 5
    assert active_rep == 0

def test_kintsugi_decay_front_movement():
    """Test that the decay front moves down to the next oldest stone when the newest is BROKEN."""
    from backend.routes.bridges import simulate_kintsugi_decay, SynapsePair, ThoughtBrief
    
    bridge_created = datetime.now(timezone.utc) - timedelta(days=50)
    syn1 = SynapsePair(
        item_a=ThoughtBrief(id=1, title="A", summary="S", created_at=bridge_created + timedelta(days=2)),
        item_b=ThoughtBrief(id=2, title="B", summary="S", created_at=bridge_created + timedelta(days=2)),
        similarity=0.8
    )
    syn2 = SynapsePair(
        item_a=ThoughtBrief(id=3, title="C", summary="S", created_at=bridge_created + timedelta(days=9)),
        item_b=ThoughtBrief(id=4, title="D", summary="S", created_at=bridge_created + timedelta(days=9)),
        similarity=0.8
    )
    
    # Day 50 = 7 completed cycles (0 to 6). Cycle 0 active, Cycle 1 active, Cycles 2,3,4,5,6 inactive.
    # Cycles 2,3,4,5 decay syn2 to BROKEN. Cycle 6 decays syn1 to WEAKENED.
    sim_time = bridge_created + timedelta(days=50)
    
    syns_res, inactive, active_rep, front = simulate_kintsugi_decay(bridge_created, [syn1, syn2], sim_time)
    
    assert syns_res[1].decay_stage == "BROKEN"
    assert syns_res[0].decay_stage == "WEAKENED"
    assert front == 0

def test_kintsugi_repair_oldest_first():
    """Test that active cycles repair the oldest damaged stone first, rather than the newest."""
    from backend.routes.bridges import simulate_kintsugi_decay, SynapsePair, ThoughtBrief
    
    bridge_created = datetime.now(timezone.utc) - timedelta(days=60)
    syn1 = SynapsePair(
        item_a=ThoughtBrief(id=1, title="A", summary="S", created_at=bridge_created + timedelta(days=2)),
        item_b=ThoughtBrief(id=2, title="B", summary="S", created_at=bridge_created + timedelta(days=2)),
        similarity=0.8
    )
    syn2 = SynapsePair(
        item_a=ThoughtBrief(id=3, title="C", summary="S", created_at=bridge_created + timedelta(days=9)),
        item_b=ThoughtBrief(id=4, title="D", summary="S", created_at=bridge_created + timedelta(days=9)),
        similarity=0.8
    )
    syn3 = SynapsePair(
        item_a=ThoughtBrief(id=5, title="E", summary="S", created_at=bridge_created + timedelta(days=50)),
        item_b=ThoughtBrief(id=6, title="F", summary="S", created_at=bridge_created + timedelta(days=50)),
        similarity=0.8
    )
    
    # Day 52 = Cycle 7 active (syn3 placed). Completed cycles 0 to 6.
    # Cycle 0, 1 active. Cycles 2, 3, 4, 5 inactive (Syn2 -> BROKEN).
    # Cycle 6 inactive (Syn1 -> WEAKENED).
    # Cycle 7 active (triggers repair on oldest damaged: Syn1. Syn1 -> STABLE).
    sim_time = bridge_created + timedelta(days=52)
    
    syns_res, inactive, active_rep, front = simulate_kintsugi_decay(bridge_created, [syn1, syn2, syn3], sim_time)
    
    assert syns_res[0].decay_stage == "STABLE"
    assert syns_res[1].decay_stage == "BROKEN"
    assert syns_res[2].decay_stage == "STABLE"

def test_kintsugi_gold_seam_permanence():
    """Test that has_gold_seam persists even through subsequent decay and repair cycles."""
    from backend.routes.bridges import simulate_kintsugi_decay, SynapsePair, ThoughtBrief
    
    bridge_created = datetime.now(timezone.utc) - timedelta(days=50)
    syn = SynapsePair(
        item_a=ThoughtBrief(id=1, title="A", summary="S", created_at=bridge_created + timedelta(days=2)),
        item_b=ThoughtBrief(id=2, title="B", summary="S", created_at=bridge_created + timedelta(days=2)),
        similarity=0.8
    )
    syn_c3 = SynapsePair(
        item_a=ThoughtBrief(id=3, title="X", summary="S", created_at=bridge_created + timedelta(days=22)),
        item_b=ThoughtBrief(id=4, title="Y", summary="S", created_at=bridge_created + timedelta(days=22)),
        similarity=0.8
    )
    syn_c4 = SynapsePair(
        item_a=ThoughtBrief(id=5, title="W", summary="S", created_at=bridge_created + timedelta(days=29)),
        item_b=ThoughtBrief(id=6, title="Z", summary="S", created_at=bridge_created + timedelta(days=29)),
        similarity=0.8
    )
    
    # Day 31 = Cycle 4 ongoing. Completed cycles 0 to 3.
    # Cycle 0 active (Syn1 placed, STABLE).
    # Cycle 1, 2 inactive (Syn1 -> SMALL_CRACK, has_gold_seam=True).
    # Cycle 3 active (Syn1 -> WEAKENED).
    # Cycle 4 active (Syn1 -> STABLE).
    # We verify that it returns to STABLE while preserving has_gold_seam = True.
    sim_time = bridge_created + timedelta(days=31)
    
    syns_res, inactive, active_rep, front = simulate_kintsugi_decay(bridge_created, [syn, syn_c3, syn_c4], sim_time)
    
    assert syns_res[0].decay_stage == "STABLE"
    assert syns_res[0].has_gold_seam is True

def test_kintsugi_foundation_immunity():
    """Test that base/foundation stones are immune to decay by verifying empty list behavior."""
    from backend.routes.bridges import simulate_kintsugi_decay
    
    bridge_created = datetime.now(timezone.utc) - timedelta(days=50)
    sim_time = bridge_created + timedelta(days=35)
    
    syns_res, inactive, active_rep, front = simulate_kintsugi_decay(bridge_created, [], sim_time)
    assert len(syns_res) == 0
    assert front is None

def test_kintsugi_boundary_edge_cases():
    """Test synapses created exactly at the 7-day boundary (23:59:59 vs 00:00:01)."""
    from backend.routes.bridges import simulate_kintsugi_decay, SynapsePair, ThoughtBrief
    
    bridge_created = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=20)
    
    date_k = bridge_created + timedelta(seconds=604799)
    date_kp1 = bridge_created + timedelta(seconds=604801)
    
    syn_k = SynapsePair(
        item_a=ThoughtBrief(id=1, title="K", summary="S", created_at=date_k),
        item_b=ThoughtBrief(id=2, title="K", summary="S", created_at=date_k),
        similarity=0.8
    )
    syn_kp1 = SynapsePair(
        item_a=ThoughtBrief(id=3, title="KP1", summary="S", created_at=date_kp1),
        item_b=ThoughtBrief(id=4, title="KP1", summary="S", created_at=date_kp1),
        similarity=0.8
    )
    
    syns_res, inactive, active_rep, front = simulate_kintsugi_decay(bridge_created, [syn_k, syn_kp1], bridge_created + timedelta(days=15))
    
    res_k = next(s for s in syns_res if s.item_a.id == 1)
    res_kp1 = next(s for s in syns_res if s.item_a.id == 3)
    
    assert res_k.placement_cycle == 0
    assert res_kp1.placement_cycle == 1
