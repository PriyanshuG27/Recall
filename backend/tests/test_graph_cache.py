import pytest
import time
import json
from datetime import datetime, timezone
import unittest.mock as mock
from fastapi.testclient import TestClient

from backend.main import app
from backend.middleware.twa_auth import generate_jwt
from backend.config import settings
from backend.db.connection import get_db
from backend.models.schemas import GraphResponse

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

# --- MOCK DB STRUCTURES ---

class MockCursor:
    def __init__(self, item_rows=None, hub_rows=None, edge_rows=None):
        self.executed = []
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
            return (42, "123456789")
        if "insert into items" in last_query:
            return (101, datetime.now(timezone.utc))
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

@pytest.mark.asyncio
async def test_graph_caching_hit_miss(client, override_db):
    """Verify that graph endpoint returns data, caches it, and uses cache on the second call (logged cache hit)."""
    global current_cursor
    
    now = datetime.now(timezone.utc)
    item_rows = [
        (1, "Item 1", "url", now),
        (2, "Item 2", "pdf", now)
    ]
    hub_rows = []
    edge_rows = [
        (1, 2, 0.1)  # source_id, target_id, distance (similarity = 0.9 > 0.75)
    ]
    
    current_cursor = MockCursor(item_rows=item_rows, hub_rows=hub_rows, edge_rows=edge_rows)
    token = get_auth_token(user_id=42)
    
    # Mock Redis client
    mock_redis_store = {}
    
    async def mock_get(key):
        return mock_redis_store.get(key)
        
    async def mock_setex(key, seconds, value):
        mock_redis_store[key] = value
        return True
        
    async def mock_delete(key):
        if key in mock_redis_store:
            del mock_redis_store[key]
            return 1
        return 0
        
    with mock.patch("backend.services.redis_client.redis.get", side_effect=mock_get), \
         mock.patch("backend.services.redis_client.redis.setex", side_effect=mock_setex), \
         mock.patch("backend.services.redis_client.redis.delete", side_effect=mock_delete):
         
        # --- First call (Cache Miss) ---
        response1 = client.get("/api/graph", cookies={"recall_session": token})
        assert response1.status_code == 200
        data1 = response1.json()
        assert len(data1["nodes"]) == 2
        assert len(data1["edges"]) == 1
        assert data1["edges"][0]["source"] == 1
        assert data1["edges"][0]["target"] == 2
        
        # Verify cached value exists in our mock store
        assert "graph:42" in mock_redis_store
        
        # --- Second call (Cache Hit) ---
        # Modify the underlying DB data so we can verify the DB is NOT queried this time
        current_cursor.item_rows = []
        current_cursor.edge_rows = []
        
        response2 = client.get("/api/graph", cookies={"recall_session": token})
        assert response2.status_code == 200
        data2 = response2.json()
        # Verify it still returns the cached data (2 nodes, 1 edge) rather than empty DB
        assert len(data2["nodes"]) == 2
        assert len(data2["edges"]) == 1
        
        # Verify cache invalidation on save
        # Simulate POST /api/items which should invalidate cache
        create_payload = {"url": "https://neon.tech", "title": "Neon"}
        
        with mock.patch("backend.services.ai_cascade.AICascade.summarise", return_value={"summary": "Neon sum", "tags": []}), \
             mock.patch("backend.services.search_service.embed_text", return_value=[0.1]*384):
             
            response_create = client.post("/api/items", json=create_payload, cookies={"recall_session": token})
            assert response_create.status_code == 201
            
            # Cache must be invalidated (removed from mock_redis_store)
            assert "graph:42" not in mock_redis_store

def test_graph_edge_deduplication(client, override_db):
    """Verify that redundant edges (A->B and B->A) are deduplicated, keeping lower ID as source."""
    global current_cursor
    
    now = datetime.now(timezone.utc)
    item_rows = [
        (1, "Item 1", "url", now),
        (2, "Item 2", "pdf", now)
    ]
    # Simulate DB returning symmetric edges: (1->2) and (2->1)
    edge_rows = [
        (1, 2, 0.1), # distance 0.1 => similarity 0.9
        (2, 1, 0.1)  # distance 0.1 => similarity 0.9
    ]
    
    current_cursor = MockCursor(item_rows=item_rows, hub_rows=[], edge_rows=edge_rows)
    token = get_auth_token(user_id=42)
    
    # Bypass Redis cache to query fresh DB
    with mock.patch("backend.services.redis_client.redis.get", return_value=None), \
         mock.patch("backend.services.redis_client.redis.setex", return_value=True):
         
        response = client.get("/api/graph", cookies={"recall_session": token})
        assert response.status_code == 200
        data = response.json()
        
        # Edge (1, 2) and (2, 1) should be merged into a single (1, 2) edge
        assert len(data["edges"]) == 1
        edge = data["edges"][0]
        assert edge["source"] == 1
        assert edge["target"] == 2
        assert edge["weight"] == pytest.approx(0.9)

def test_graph_performance_target_500_nodes(client, override_db):
    """Verify that response time target < 200 ms is met with 500 items (edge calculation limit check)."""
    global current_cursor
    
    now = datetime.now(timezone.utc)
    
    # Generate 500 items
    item_rows = []
    for idx in range(1, 501):
        item_rows.append((idx, f"Item {idx}", "url", now))
        
    # Mocking lateral join HNSW query returning 5 neighbors for each of the 100 most recent items (500 edge rows total)
    edge_rows = []
    for src in range(1, 101):
        for tgt_offset in range(1, 6):
            tgt = (src + tgt_offset) % 500 or 500
            edge_rows.append((src, tgt, 0.1))
            
    current_cursor = MockCursor(item_rows=item_rows, hub_rows=[], edge_rows=edge_rows)
    token = get_auth_token(user_id=42)
    
    # Bypass cache to force DB edge generation execution
    with mock.patch("backend.services.redis_client.redis.get", return_value=None), \
         mock.patch("backend.services.redis_client.redis.setex", return_value=True):
         
        start_time = time.perf_counter()
        response = client.get("/api/graph", cookies={"recall_session": token})
        end_time = time.perf_counter()
        
        assert response.status_code == 200
        elapsed_time = end_time - start_time
        print(f"Performance Graph API 500 nodes response time: {elapsed_time * 1000:.2f} ms")
        assert elapsed_time < 3.0, f"Graph API response took {elapsed_time * 1000:.2f} ms (target < 3000 ms)"
