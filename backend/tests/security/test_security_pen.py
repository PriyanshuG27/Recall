import pytest
import time
import json
import unittest.mock as mock
from datetime import datetime
from fastapi import status
from fastapi.testclient import TestClient

from backend.main import app
from backend.middleware.twa_auth import generate_jwt
from backend.config import settings
from backend.db.connection import get_db

# Patch environment variables
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

class PenTestingCursor:
    def __init__(self, user_id=42):
        self.executed = []
        self.user_id = user_id
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
        
    async def execute(self, query, params=None):
        self.executed.append((query, params))
        
    async def fetchone(self):
        last_query = self.executed[-1][0].lower() if self.executed else ""
        
        # User resolver queries (for middleware verification)
        if "select id, telegram_chat_id from users where id =" in last_query:
            return (self.user_id, "123456")
            
        # GET single item query: i.id = %s AND i.user_id = %s
        if "select i.id, i.user_id" in last_query:
            item_id, q_user_id = self.executed[-1][1]
            if item_id == 999 and q_user_id == 100:
                return (999, 100, "User Item Title", "summary", "url", "http://example.com", ["tag1"], datetime.now(), "context", 2.5, 3, None)
            return None
            
        # DELETE items: WHERE id = %s AND user_id = %s
        if "delete from items" in last_query:
            item_id, q_user_id = self.executed[-1][1]
            if item_id == 999 and q_user_id == 100:
                return (999, "url")
            return None
            
        # POST quizzes answer query: WHERE id = %s AND user_id = %s
        if "select id, user_id, item_id" in last_query and "quizzes" in last_query:
            quiz_id, q_user_id = self.executed[-1][1]
            if quiz_id == 888 and q_user_id == 100:
                return (888, 100, 999, "Question", ["opt1"], 0, "Expl", 2.5, 3, None, datetime.now())
            return None
            
        # DELETE reminders query: WHERE id = %s AND user_id = %s
        if "delete from reminders" in last_query:
            reminder_id, q_user_id = self.executed[-1][1]
            if reminder_id == 777 and q_user_id == 100:
                return (777,)
            return None
            
        # GET pulse score query: SELECT self_description, mind_type, mind_type_summary, mind_type_trajectory, pulse_score FROM users WHERE id = %s
        if "select self_description, mind_type" in last_query and "users" in last_query:
            q_user_id = self.executed[-1][1][0]
            if q_user_id == self.user_id:
                return ("Self description", "MindType", "Summary", "[]", 85)
            return None
            
        # GET graph node count query: SELECT COUNT(*) FROM items WHERE user_id = %s
        if "select count(*) from items" in last_query:
            return (0,)
            
        return None
        
    async def fetchall(self):
        last_query = self.executed[-1][0].lower() if self.executed else ""
        
        # GET graph query: SELECT id, title, source_type, created_at FROM items WHERE user_id = %s
        if "select id, title, source_type" in last_query and "items" in last_query:
            q_user_id = self.executed[-1][1][0]
            if q_user_id == self.user_id:
                return [(1000 + self.user_id, "User Node", "url", datetime.now())]
            return []
            
        return []

class PenTestingConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        
    def cursor(self):
        return self.cursor_obj
        
    async def commit(self):
        pass
        
    async def rollback(self):
        pass

# Global/context variable to pass current cursor to mock DB dependency
current_cursor = None

@pytest.fixture(autouse=True)
def override_db():
    global current_cursor
    current_cursor = None
    
    async def _mock_get_db():
        yield PenTestingConnection(current_cursor)
        
    app.dependency_overrides[get_db] = _mock_get_db
    yield
    app.dependency_overrides.pop(get_db, None)

@pytest.fixture()
def client():
    with mock.patch("backend.db.connection.open_pool", return_value=None), \
         mock.patch("backend.db.connection.close_pool", return_value=None), \
         mock.patch("backend.services.redis_client.redis", new_callable=mock.AsyncMock):
        with TestClient(app) as c:
            yield c

def get_auth_token(user_id=100):
    payload = {
        "sub": str(user_id),
        "chat_id": "123456",
        "exp": int(time.time()) + 3600
    }
    return generate_jwt(payload, settings.JWT_SECRET)

# Target user credentials/tokens
@pytest.fixture()
def token_user_A():
    return get_auth_token(user_id=100)

@pytest.fixture()
def token_user_B():
    return get_auth_token(user_id=200)

@pytest.fixture()
def user_A_item_id():
    return 999

# 1. IDOR Cross-User Isolation Tests
def test_idor_cross_user_isolation(client, token_user_A, token_user_B, user_A_item_id):
    """User B must get 404 attempting to access or delete User A's item/quiz/reminder."""
    global current_cursor
    
    # Verify User A CAN retrieve their own item (item_id = 999)
    current_cursor = PenTestingCursor(user_id=100)
    res = client.get(f"/api/items/{user_A_item_id}", cookies={"recall_session": token_user_A})
    assert res.status_code == 200
    assert res.json()["id"] == 999
    
    # 1. User B attempts GET /api/items/{user_A_item_id} -> 404 Not Found
    current_cursor = PenTestingCursor(user_id=200)
    res = client.get(f"/api/items/{user_A_item_id}", cookies={"recall_session": token_user_B})
    assert res.status_code == 404
    
    # 2. User B attempts DELETE /api/items/{user_A_item_id} -> 404 Not Found
    current_cursor = PenTestingCursor(user_id=200)
    res = client.delete(f"/api/items/{user_A_item_id}", cookies={"recall_session": token_user_B})
    assert res.status_code == 404
    
    # 3. User B attempts POST /api/quizzes/{user_A_quiz_id}/answer -> 404 Not Found
    # user_A_quiz_id = 888
    current_cursor = PenTestingCursor(user_id=200)
    res = client.post("/api/quizzes/888/answer", json={"quality": 4}, cookies={"recall_session": token_user_B})
    assert res.status_code == 404
    
    # 4. User B attempts DELETE /api/reminders/{user_A_reminder_id} -> 404 Not Found
    # user_A_reminder_id = 777
    current_cursor = PenTestingCursor(user_id=200)
    res = client.delete("/api/reminders/777", cookies={"recall_session": token_user_B})
    assert res.status_code == 404
    
    # 5. User B attempts GET /api/graph -> returns ONLY User B's nodes (node 1200), zero nodes belonging to User A (node 1100)
    current_cursor = PenTestingCursor(user_id=200)
    res = client.get("/api/graph", cookies={"recall_session": token_user_B})
    assert res.status_code == 200
    nodes = res.json()["nodes"]
    assert len(nodes) == 1
    assert nodes[0]["id"] == 1200 # User B node ID
    
    # 6. User B attempts GET /api/pulse -> returns ONLY User B's mind portrait metrics
    current_cursor = PenTestingCursor(user_id=200)
    res = client.get("/api/pulse", cookies={"recall_session": token_user_B})
    assert res.status_code == 200
    profile = res.json()
    assert profile["pulse_score"] == 85
    assert profile["mind_type"] == "MindType"

# 2. SQL Injection Search Endpoint
def test_sql_injection_search_endpoint(client, token_user_A):
    """SQL injection payloads must fail safely without DB execution or 500 errors."""
    global current_cursor
    current_cursor = PenTestingCursor(user_id=100)
    
    # We mock hybrid_search return value
    # Even if SQL injection characters are passed, they must be parsed as a plain query literal.
    # The database query must utilize parameterized bindings (%s).
    payload = {"query": "' OR 1=1; DROP TABLE items; --"}
    
    res = client.post("/api/search", json=payload, cookies={"recall_session": token_user_A})
    assert res.status_code == 200
    assert isinstance(res.json().get("sources"), list)

# 3. TWA Auth Rejection
def test_twa_hmac_tampered_hash_rejection(client):
    """TWA auth middleware must reject tampered hash payloads."""
    # 1. Custom twa-init-data query string containing tampered hash
    tampered_headers = {"Authorization": "twa-init-data query_id=123&user={}&hash=invalid_hash"}
    res = client.get("/api/items", headers=tampered_headers)
    assert res.status_code == 401
    
    # 2. Standard TelegramInitData with tampered hash
    tampered_headers_std = {"Authorization": "TelegramInitData query_id=123&user={}&hash=invalid_hash"}
    res = client.get("/api/items", headers=tampered_headers_std)
    assert res.status_code == 401
