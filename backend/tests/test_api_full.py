import pytest
import unittest.mock as mock
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from backend.main import app
from backend.middleware.twa_auth import UserContext, get_current_user
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

@pytest.fixture
def mock_db():
    db = mock.MagicMock()
    cur = mock.AsyncMock()
    cur.rowcount = 1
    cur.fetchone.return_value = (
        1, "Title", "Summary", "text", "http://example.com", ["tag1"], datetime.now(timezone.utc), "Note",
        2.5, 1, datetime.now(timezone.utc).date()
    )
    cur.fetchall.return_value = [
        (1, "Title", "Summary", "text", "http://example.com", ["tag1"], datetime.now(timezone.utc), "Note",
         2.5, 1, datetime.now(timezone.utc).date())
    ]
    
    cm = mock.MagicMock()
    cm.__aenter__ = mock.AsyncMock(return_value=cur)
    cm.__aexit__ = mock.AsyncMock(return_value=None)
    
    db.cursor.return_value = cm
    db.commit = mock.AsyncMock()
    return db

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

def test_get_items_success(client):
    res = client.get("/api/items?page=1&limit=10&source_type=text&tag=tag1")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert data["total"] == 1

def test_get_items_limit_exceeded(client):
    res = client.get("/api/items?limit=100")
    assert res.status_code == 400

def test_delete_item_success(client, mock_db):
    mock_db.cursor.return_value.__aenter__.return_value.rowcount = 1
    res = client.delete("/api/items/1")
    assert res.status_code in (200, 204)

def test_get_tags_success(client, mock_db):
    mock_db.cursor.return_value.__aenter__.return_value.fetchall.return_value = [("tag1", 5), ("tag2", 3)]
    res = client.get("/api/tags")
    assert res.status_code == 200
    assert len(res.json()) == 2

def test_get_graph_success(client, mock_db):
    cur = mock_db.cursor.return_value.__aenter__.return_value
    cur.fetchall.return_value = []
    res = client.get("/api/graph")
    assert res.status_code == 200

def test_get_reminders(client, mock_db):
    mock_db.cursor.return_value.__aenter__.return_value.fetchall.return_value = [
        (1, 42, None, "Reminder text", datetime.now(timezone.utc), "active", datetime.now(timezone.utc))
    ]
    res = client.get("/api/reminders")
    assert res.status_code == 200

def test_delete_reminder(client, mock_db):
    mock_db.cursor.return_value.__aenter__.return_value.rowcount = 1
    res = client.delete("/api/reminders/1")
    assert res.status_code in (200, 204)

def test_get_user_me(client, mock_db):
    cur = mock_db.cursor.return_value.__aenter__.return_value
    cur.fetchone.side_effect = [
        (0, 5, "token", datetime.now(timezone.utc), True), # users row
        (10,), # total items count
        (5,),  # total quizzes count
        (datetime.now(timezone.utc),) # max created_at
    ]
    cur.fetchall.return_value = [(datetime.now().date(), True)] * 7
    with mock.patch("backend.services.user_service.get_and_update_user_streak", new_callable=mock.AsyncMock, return_value=5):
        res = client.get("/api/me")
        assert res.status_code == 200
        assert res.json()["total_saves"] == 10

def test_update_user_me(client, mock_db):
    cur = mock_db.cursor.return_value.__aenter__.return_value
    cur.fetchone.side_effect = [
        (0, 5, "token", datetime.now(timezone.utc), True), # fetch user row in patch_user_me
        (0, 5, "token", datetime.now(timezone.utc), True), # fetch user row in get_user_me
        (10,), # total items count
        (5,),  # total quizzes count
        (datetime.now(timezone.utc),) # max created_at
    ]
    cur.fetchall.return_value = [(datetime.now().date(), True)] * 7
    with mock.patch("backend.services.user_service.get_and_update_user_streak", new_callable=mock.AsyncMock, return_value=5):
        res = client.patch("/api/me", json={"theme": "light"})
        assert res.status_code == 200
