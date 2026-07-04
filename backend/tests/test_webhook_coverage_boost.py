import pytest
import unittest.mock as mock
from fastapi.testclient import TestClient
from backend.main import app
from backend.db.connection import get_db

@pytest.fixture
def mock_db():
    db = mock.MagicMock()
    cur = mock.AsyncMock()
    cur.fetchone.return_value = (1, "2026-07-04 10:00:00")
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

def test_webhook_callback_query_onboarding(client):
    payload = {
        "update_id": 999001,
        "callback_query": {
            "id": "cb_123",
            "from": {"id": 888111, "first_name": "Tester"},
            "message": {"message_id": 444, "chat": {"id": 888111}},
            "data": "onboarding_opt:tech"
        }
    }
    with mock.patch("backend.routes.webhook.redis.setex", new_callable=mock.AsyncMock, return_value=True), \
         mock.patch("backend.routes.webhook.redis.lpush", new_callable=mock.AsyncMock, return_value=1):
        res = client.post("/webhook", json=payload)
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

def test_webhook_callback_query_quiz(client):
    payload = {
        "update_id": 999002,
        "callback_query": {
            "id": "cb_124",
            "from": {"id": 888111, "first_name": "Tester"},
            "message": {"message_id": 445, "chat": {"id": 888111}},
            "data": "quiz_ans:101:2"
        }
    }
    with mock.patch("backend.routes.webhook.redis.setex", new_callable=mock.AsyncMock, return_value=True), \
         mock.patch("backend.routes.webhook.redis.lpush", new_callable=mock.AsyncMock, return_value=1):
        res = client.post("/webhook", json=payload)
        assert res.status_code == 200

def test_webhook_location_message(client):
    payload = {
        "update_id": 999003,
        "message": {
            "message_id": 446,
            "from": {"id": 888111, "first_name": "LocationTester"},
            "chat": {"id": 888111},
            "location": {
                "latitude": 28.6139,
                "longitude": 77.2090
            }
        }
    }
    with mock.patch("backend.routes.webhook.redis.setex", new_callable=mock.AsyncMock, return_value=True), \
         mock.patch("backend.routes.webhook.redis.lpush", new_callable=mock.AsyncMock, return_value=1):
        res = client.post("/webhook", json=payload)
        assert res.status_code == 200

def test_webhook_match_command(client):
    payload = {
        "update_id": 999004,
        "message": {
            "message_id": 447,
            "from": {"id": 888111, "first_name": "MatchUser"},
            "chat": {"id": 888111},
            "text": "/match"
        }
    }
    with mock.patch("backend.routes.webhook.redis.setex", new_callable=mock.AsyncMock, return_value=True), \
         mock.patch("backend.routes.webhook.redis.lpush", new_callable=mock.AsyncMock, return_value=1):
        res = client.post("/webhook", json=payload)
        assert res.status_code == 200
