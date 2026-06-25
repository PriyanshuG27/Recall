import pytest
import time
from datetime import datetime, timezone
import unittest.mock as mock
from fastapi.testclient import TestClient

from backend.main import app
from backend.middleware.twa_auth import generate_jwt
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

@pytest.fixture(autouse=True)
def mock_redis():
    with mock.patch("backend.services.redis_client.redis.get", return_value=None), \
         mock.patch("backend.services.redis_client.redis.setex", return_value=True), \
         mock.patch("backend.services.redis_client.redis.delete", return_value=0):
        yield

# --- MOCK DB STRUCTURES ---

class MockCursor:
    def __init__(self, user_id=42, item_rows=None, hub_rows=None, edge_rows=None):
        self.executed = []
        self.user_id = user_id
        self.item_rows = item_rows or []
        self.hub_rows = hub_rows or []
        self.edge_rows = edge_rows or []
        self.rowcount = 1
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
        
    async def execute(self, query, params=None):
        self.executed.append((query, params))
        
    async def fetchone(self):
        last_query = self.executed[-1][0].lower() if self.executed else ""
        if "users" in last_query:
            return (self.user_id, "123456789")
        return None
        
    async def fetchall(self):
        last_query = self.executed[-1][0].lower() if self.executed else ""
        if "items" in last_query:
            if "lateral" in last_query:
                return self.edge_rows
            return self.item_rows
        if "semantic_hubs" in last_query:
            return self.hub_rows
        return []

class MockConnection:
    def __init__(self, cursor_inst):
        self.cursor_inst = cursor_inst
        
    def cursor(self):
        return self.cursor_inst
        
    async def commit(self):
        pass

# --- FIXTURES ---

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

def get_auth_token(user_id=42):
    payload = {
        "sub": str(user_id),
        "chat_id": "123456789",
        "exp": int(time.time()) + 3600
    }
    return generate_jwt(payload, settings.JWT_SECRET)

# --- TESTS ---

def test_graph_api_auth_required(client, override_db):
    """GET /api/graph returns 401 when no JWT auth cookie is provided."""
    response = client.get("/api/graph")
    assert response.status_code == 401

def test_graph_api_user_isolation(client, override_db):
    """Verify that User A cannot see User B's graph and queries only reference the authenticated user ID."""
    global current_cursor
    
    # Set up user 42
    current_cursor = MockCursor(user_id=42, item_rows=[], hub_rows=[])
    token = get_auth_token(user_id=42)
    
    response = client.get("/api/graph", cookies={"recall_session": token})
    assert response.status_code == 200
    
    # Assert all database queries executed filtered by the user_id (which should be 42)
    for query, params in current_cursor.executed:
        # Check if the query has parameters, and verify the first parameter is user_id = 42
        if params:
            assert params[0] == 42

def test_graph_api_schema_and_hub_validation(client, override_db):
    """Verify the schema format, that member_ids are validated, and is_hub is correctly resolved."""
    global current_cursor
    
    now = datetime.now(timezone.utc)
    
    # Items (embeddings: 1 and 2 are similar, 3 is not similar to 1 or 2)
    item_rows = [
        # (id, title, source_type, created_at, embedding)
        (1, "ML Research", "url", now, [1.0, 0.0, 0.0]),
        (2, "Machine Learning Notes", "pdf", now, [0.9, 0.1, 0.0]),
        (3, "Cooking Recipes", "text", now, [0.0, 1.0, 0.0])
    ]
    # Hub 1 contains valid items 1 and 2, plus deleted item 99
    hub_rows = [
        # (id, label, member_ids)
        (10, "Machine Learning", [1, 2, 99])
    ]
    
    current_cursor = MockCursor(user_id=42, item_rows=item_rows, hub_rows=hub_rows, edge_rows=[(1, 2, 0.1)])
    token = get_auth_token(user_id=42)
    
    response = client.get("/api/graph", cookies={"recall_session": token})
    assert response.status_code == 200
    
    data = response.json()
    
    # 1. Nodes verification
    assert "nodes" in data
    nodes = data["nodes"]
    assert len(nodes) == 3
    
    # Check node 1 (in hub)
    node1 = next(n for n in nodes if n["id"] == 1)
    assert node1["title"] == "ML Research"
    assert node1["source_type"] == "url"
    assert node1["is_hub"] is True
    
    # Check node 2 (in hub)
    node2 = next(n for n in nodes if n["id"] == 2)
    assert node2["is_hub"] is True
    
    # Check node 3 (not in hub)
    node3 = next(n for n in nodes if n["id"] == 3)
    assert node3["is_hub"] is False
    
    # 2. Hub verification (item 99 must be excluded since it's not in items)
    assert "hubs" in data
    hubs = data["hubs"]
    assert len(hubs) == 1
    assert hubs[0]["id"] == 10
    assert hubs[0]["label"] == "Machine Learning"
    assert hubs[0]["member_ids"] == [1, 2] # 99 was filtered out
    
    # 3. Edges verification (1 and 2 similarity > 0.75)
    assert "edges" in data
    edges = data["edges"]
    assert len(edges) == 1
    assert edges[0]["source"] == 1
    assert edges[0]["target"] == 2
    assert edges[0]["weight"] > 0.75
    
    # 4. Security Check (ensure raw_text is completely absent from response)
    # The dictionary keys/values should not contain 'raw_text'
    assert "raw_text" not in str(data).lower()

def test_graph_api_edge_limit_cutoff(client, override_db):
    """Verify that when items > 200, we skip full pairwise comparison and return only hub-membership edges."""
    global current_cursor
    
    now = datetime.now(timezone.utc)
    
    # Generate 205 items
    item_rows = []
    for idx in range(1, 206):
        # Even indices are similar, odd indices are similar
        emb = [1.0, 0.0, 0.0] if idx % 2 == 0 else [0.0, 1.0, 0.0]
        item_rows.append((idx, f"Item {idx}", "text", now, emb))
        
    # Semantic Hub contains only items 1 and 2
    hub_rows = [
        (10, "Small Hub", [1, 2])
    ]
    
    current_cursor = MockCursor(user_id=42, item_rows=item_rows, hub_rows=hub_rows)
    token = get_auth_token(user_id=42)
    
    response = client.get("/api/graph", cookies={"recall_session": token})
    assert response.status_code == 200
    
    data = response.json()
    assert len(data["nodes"]) == 205
    assert len(data["hubs"]) == 1
    
    # Because items > 200, pairwise calculation is skipped. 
    # Items 1 and 2 belong to the same hub but are NOT similar (emb1=[0,1,0], emb2=[1,0,0], similarity=0).
    # Therefore, no edges should be returned. If pairwise was calculated, there would be thousands of edges.
    assert len(data["edges"]) == 0
    
    # Now let's try with similar items in the same hub
    hub_rows_similar = [
        (10, "Similar Hub", [2, 4]) # item 2 [1,0,0] and item 4 [1,0,0], similarity = 1.0 > 0.75
    ]
    current_cursor = MockCursor(user_id=42, item_rows=item_rows, hub_rows=hub_rows_similar, edge_rows=[(2, 4, 0.0)])
    response_similar = client.get("/api/graph", cookies={"recall_session": token})
    data_similar = response_similar.json()
    
    # We should have exactly 1 edge because 2 and 4 share the same hub and are similar
    assert len(data_similar["edges"]) == 1
    assert data_similar["edges"][0]["source"] == 2
    assert data_similar["edges"][0]["target"] == 4

def test_graph_api_performance_target(client, override_db):
    """Verify that response time is less than 200 ms for 100 nodes."""
    global current_cursor
    
    now = datetime.now(timezone.utc)
    
    # Generate 100 items
    item_rows = []
    for idx in range(1, 101):
        emb = [0.1] * 384
        item_rows.append((idx, f"Performance Item {idx}", "url", now, emb))
        
    # Generate 5 hubs
    hub_rows = []
    for idx in range(1, 6):
        hub_rows.append((idx, f"Hub {idx}", list(range((idx-1)*20 + 1, idx*20 + 1))))
        
    current_cursor = MockCursor(user_id=42, item_rows=item_rows, hub_rows=hub_rows)
    token = get_auth_token(user_id=42)
    
    start_time = time.perf_counter()
    response = client.get("/api/graph", cookies={"recall_session": token})
    end_time = time.perf_counter()
    
    assert response.status_code == 200
    elapsed_time = end_time - start_time
    
    # Performance assertion: response must be generated within 200ms (0.2s)
    print(f"Performance Graph API response time: {elapsed_time * 1000:.2f} ms")
    assert elapsed_time < 0.2, f"Graph API response took {elapsed_time * 1000:.2f} ms (target < 200 ms)"
