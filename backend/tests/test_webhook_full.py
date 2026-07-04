import pytest
import unittest.mock as mock
from fastapi.testclient import TestClient
from backend.main import app
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
    cur.fetchone.return_value = (1, "Test Question", ["A", "B", "C"], 0, "Explanation")
    cur.fetchall.return_value = []
    
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

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides = {}

def test_webhook_candidate_confirm_callback(client):
    payload = {
        "update_id": 10001,
        "callback_query": {
            "id": "cb123",
            "data": "candidate_confirm:10",
            "message": {
                "message_id": 99,
                "chat": {"id": 12345},
                "text": "Idea text 💡 extra info"
            }
        }
    }
    with mock.patch("backend.routes.webhook.upsert_user", new_callable=mock.AsyncMock, return_value=1), \
         mock.patch("backend.routes.webhook.http_client.post", new_callable=mock.AsyncMock) as mock_post, \
         mock.patch("backend.routes.webhook.redis.zrem", new_callable=mock.AsyncMock):
        res = client.post("/webhook", json=payload)
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}
        assert mock_post.called

def test_webhook_candidate_drift_callback(client):
    payload = {
        "update_id": 10002,
        "callback_query": {
            "id": "cb124",
            "data": "candidate_drift:10",
            "message": {
                "message_id": 99,
                "chat": {"id": 12345},
                "text": "Idea text 💡 extra info"
            }
        }
    }
    with mock.patch("backend.routes.webhook.upsert_user", new_callable=mock.AsyncMock, return_value=1), \
         mock.patch("backend.routes.webhook.http_client.post", new_callable=mock.AsyncMock) as mock_post, \
         mock.patch("backend.routes.webhook.redis.zrem", new_callable=mock.AsyncMock):
        res = client.post("/webhook", json=payload)
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}
        assert mock_post.called

def test_webhook_quiz_next_callback_no_due(client, mock_db):
    mock_db.cursor.return_value.__aenter__.return_value.fetchone.return_value = None
    payload = {
        "update_id": 10003,
        "callback_query": {
            "id": "cb125",
            "data": "quiz:next",
            "message": {
                "message_id": 99,
                "chat": {"id": 12345},
                "text": "Quiz text"
            }
        }
    }
    with mock.patch("backend.routes.webhook.upsert_user", new_callable=mock.AsyncMock, return_value=1), \
         mock.patch("backend.routes.webhook.http_client.post", new_callable=mock.AsyncMock):
        res = client.post("/webhook", json=payload)
        assert res.status_code == 200

def test_webhook_quiz_next_callback_with_due(client, mock_db):
    mock_db.cursor.return_value.__aenter__.return_value.fetchone.return_value = (
        5, "What is 2+2?", ["3", "4", "5"], 1, "Basic math"
    )
    payload = {
        "update_id": 10004,
        "callback_query": {
            "id": "cb126",
            "data": "quiz:next",
            "message": {
                "message_id": 99,
                "chat": {"id": 12345},
                "text": "Quiz text"
            }
        }
    }
    with mock.patch("backend.routes.webhook.upsert_user", new_callable=mock.AsyncMock, return_value=1), \
         mock.patch("backend.routes.webhook.http_client.post", new_callable=mock.AsyncMock):
        res = client.post("/webhook", json=payload)
        assert res.status_code == 200

def test_webhook_quiz_ans_callback(client, mock_db):
    mock_db.cursor.return_value.__aenter__.return_value.fetchone.return_value = (
        "Question?", ["Option A", "Option B"], 0, "Explanation text", 2.5, 1, 1
    )
    payload = {
        "update_id": 10005,
        "callback_query": {
            "id": "cb127",
            "data": "quiz_ans:5:0",
            "message": {
                "message_id": 99,
                "chat": {"id": 12345},
                "text": "Quiz question text"
            }
        }
    }
    with mock.patch("backend.routes.webhook.upsert_user", new_callable=mock.AsyncMock, return_value=1), \
         mock.patch("backend.routes.webhook.http_client.post", new_callable=mock.AsyncMock):
        res = client.post("/webhook", json=payload)
        assert res.status_code == 200

def test_webhook_start_command(client):
    payload = {
        "update_id": 10006,
        "message": {
            "message_id": 1,
            "chat": {"id": 12345},
            "text": "/start"
        }
    }
    with mock.patch("backend.routes.webhook.upsert_user", new_callable=mock.AsyncMock, return_value=1), \
         mock.patch("backend.routes.webhook.http_client.post", new_callable=mock.AsyncMock):
        res = client.post("/webhook", json=payload)
        assert res.status_code == 200

def test_webhook_quiz_command(client, mock_db):
    mock_db.cursor.return_value.__aenter__.return_value.fetchone.return_value = (
        1, "Question?", ["Opt 1", "Opt 2"], 0, "Exp"
    )
    payload = {
        "update_id": 10007,
        "message": {
            "message_id": 2,
            "chat": {"id": 12345},
            "text": "/quiz"
        }
    }
    with mock.patch("backend.routes.webhook.upsert_user", new_callable=mock.AsyncMock, return_value=1), \
         mock.patch("backend.routes.webhook.http_client.post", new_callable=mock.AsyncMock):
        res = client.post("/webhook", json=payload)
        assert res.status_code == 200

def test_webhook_stats_command(client, mock_db):
    mock_db.cursor.return_value.__aenter__.return_value.fetchone.return_value = (10, 5, 3)
    payload = {
        "update_id": 10008,
        "message": {
            "message_id": 3,
            "chat": {"id": 12345},
            "text": "/stats"
        }
    }
    with mock.patch("backend.routes.webhook.upsert_user", new_callable=mock.AsyncMock, return_value=1), \
         mock.patch("backend.routes.webhook.http_client.post", new_callable=mock.AsyncMock):
        res = client.post("/webhook", json=payload)
        assert res.status_code == 200

def test_webhook_plain_text_message(client):
    payload = {
        "update_id": 10009,
        "message": {
            "message_id": 4,
            "chat": {"id": 12345},
            "text": "Remember to buy milk tomorrow at 5pm"
        }
    }
    with mock.patch("backend.routes.webhook.upsert_user", new_callable=mock.AsyncMock, return_value=1), \
         mock.patch("backend.routes.webhook.check_rate_limit", new_callable=mock.AsyncMock), \
         mock.patch("backend.routes.webhook.http_client.post", new_callable=mock.AsyncMock):
        res = client.post("/webhook", json=payload)
        assert res.status_code == 200
