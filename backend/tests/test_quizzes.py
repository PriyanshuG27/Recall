import pytest
import time
import json
import unittest.mock as mock
from datetime import datetime, date, timezone, timedelta
from fastapi import Depends
from fastapi.testclient import TestClient

from backend.main import app
from backend.middleware.twa_auth import get_current_user, generate_jwt, UserContext
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

class RecordingCursor:
    def __init__(self, user_id=42, fetchone_val=None, fetchall_val=None):
        self.executed = []
        self.user_id = user_id
        self.fetchone_val = fetchone_val
        self.fetchall_val = fetchall_val or []
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
        return self.fetchone_val
        
    async def fetchall(self):
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

def test_get_due_quizzes_success(client):
    """GET /api/quizzes/due returns List[QuizResponse] for the user."""
    global current_cursor
    due_quizzes = [
        (1, 42, 10, "What is capital of France?", json.dumps(["London", "Paris", "Berlin", "Rome"]), 1, "Explanation here", 2.5, 1, date.today(), datetime.now(timezone.utc))
    ]
    current_cursor = RecordingCursor(user_id=42, fetchall_val=due_quizzes)
    
    token = get_auth_token(user_id=42)
    response = client.get("/api/quizzes/due", cookies={"recall_session": token})
    
    assert response.status_code == 200
    res_data = response.json()
    assert len(res_data) == 1
    assert res_data[0]["id"] == 1
    assert res_data[0]["question"] == "What is capital of France?"
    assert res_data[0]["options"] == ["London", "Paris", "Berlin", "Rome"]
    assert res_data[0]["correct_index"] == 1

def test_answer_quiz_success(client):
    """POST /api/quizzes/{id}/answer updates the quiz matching the SM-2 logic and commits it."""
    global current_cursor
    # Quiz entry in DB: id=1, user_id=42, item_id=10, question, options, correct_index, explanation, ease_factor=2.5, interval_days=1, next_review, created_at
    quiz_row = (1, 42, 10, "Question?", json.dumps(["A", "B"]), 0, "Expl", 2.5, 1, date.today(), datetime.now(timezone.utc))
    current_cursor = RecordingCursor(user_id=42, fetchone_val=quiz_row)
    
    token = get_auth_token(user_id=42)
    # Answer correct easy (quality = 5)
    response = client.post("/api/quizzes/1/answer", json={"quality": 5}, cookies={"recall_session": token})
    
    assert response.status_code == 200
    data = response.json()
    # SM-2 calculation: ef=2.5, interval=1, quality=5 -> new_ef = 2.6, new_interval = 3
    assert data["ease_factor"] == 2.6
    assert data["interval_days"] == 3
    assert data["next_review"] == (date.today() + timedelta(days=3)).isoformat()
    
    # Verify DB queries: 1. get user, 2. select quiz, 3. update quiz, 4. log answer, plus 4 pulse score queries
    assert len(current_cursor.executed) == 8
    update_query, update_params = current_cursor.executed[2]
    assert "UPDATE quizzes" in update_query
    assert pytest.approx(update_params[0]) == 2.6
    assert update_params[1] == 3
    assert update_params[2] == date.today() + timedelta(days=3)
    assert update_params[3] == 1
    assert update_params[4] == 42

    insert_query, insert_params = current_cursor.executed[3]
    assert "INSERT INTO quiz_answers" in insert_query
    assert insert_params[0] == 42
    assert insert_params[1] == 1
    assert insert_params[2] == 5

def test_answer_quiz_invalid_quality(client):
    """POST /api/quizzes/{id}/answer returns 400 (or 422 standard) if quality is outside 0-5."""
    token = get_auth_token(user_id=42)
    
    # Quality = 6 is invalid
    response = client.post("/api/quizzes/1/answer", json={"quality": 6}, cookies={"recall_session": token})
    assert response.status_code in (400, 422)

def test_answer_quiz_not_found_or_forbidden(client):
    """POST /api/quizzes/{id}/answer returns 404 if the quiz does not exist or belongs to another user."""
    global current_cursor
    # Quiz not found under user 42 (fetchone returns None)
    current_cursor = RecordingCursor(user_id=42, fetchone_val=None)
    
    token = get_auth_token(user_id=42)
    response = client.post("/api/quizzes/1/answer", json={"quality": 4}, cookies={"recall_session": token})
    
    assert response.status_code == 404
    assert response.json()["detail"] == "Quiz not found."
