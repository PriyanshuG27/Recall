import pytest
import unittest.mock as mock
from fastapi.testclient import TestClient
from backend.main import app
from backend.routes.webhook import detect_content_type, ACK_MESSAGES
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
    cur.rowcount = 0
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

def test_detect_content_type_voice():
    msg = {"voice": {"file_id": "v123"}}
    ctype, text, fid = detect_content_type(msg)
    assert ctype == "voice"
    assert fid == "v123"

def test_detect_content_type_audio():
    msg = {"audio": {"file_id": "a123"}}
    ctype, text, fid = detect_content_type(msg)
    assert ctype == "voice"
    assert fid == "a123"

def test_detect_content_type_pdf_doc():
    msg = {"document": {"mime_type": "application/pdf", "file_id": "pdf123"}}
    ctype, text, fid = detect_content_type(msg)
    assert ctype == "pdf"
    assert fid == "pdf123"

def test_detect_content_type_audio_doc():
    msg = {"document": {"mime_type": "audio/mp3", "file_name": "song.mp3", "file_id": "aud123"}}
    ctype, text, fid = detect_content_type(msg)
    assert ctype == "voice"
    assert fid == "aud123"

def test_detect_content_type_photo():
    msg = {"photo": [{"file_id": "p1"}, {"file_id": "p2"}]}
    ctype, text, fid = detect_content_type(msg)
    assert ctype == "photo"
    assert fid == "p2"

def test_detect_content_type_location():
    msg = {"location": {"latitude": 37.77, "longitude": -122.41}}
    ctype, text, fid = detect_content_type(msg)
    assert ctype == "location"
    assert "37.77" in text

def test_detect_content_type_url():
    msg = {"text": "https://github.com", "entities": [{"type": "url"}]}
    ctype, text, fid = detect_content_type(msg)
    assert ctype == "url"
    assert text == "https://github.com"

def test_detect_content_type_text():
    msg = {"text": "Just plain notes"}
    ctype, text, fid = detect_content_type(msg)
    assert ctype == "text"
    assert text == "Just plain notes"

def test_detect_content_type_unsupported():
    msg = {"sticker": {"file_id": "s1"}}
    ctype, text, fid = detect_content_type(msg)
    assert ctype == "unsupported"

def test_webhook_invalid_update(client):
    res = client.post("/webhook", json={})
    assert res.status_code == 200
    assert res.json()["detail"] == "invalid_update"

def test_webhook_duplicate_update(client):
    res = client.post("/webhook", json={"update_id": 12345, "message": {"chat": {"id": 123}}})
    assert res.status_code == 200
    assert res.json()["detail"] == "duplicate"

def test_webhook_security_missing_secret(client, monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", "super-secret-token")
    
    payload = {"update_id": 99999, "message": {"chat": {"id": 12345}, "text": "Hello"}}
    # No header -> should be 403
    res = client.post("/webhook", json=payload)
    assert res.status_code == 403
    assert res.json()["detail"] == "Unauthorized"

def test_webhook_security_invalid_secret(client, monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", "super-secret-token")
    
    payload = {"update_id": 99999, "message": {"chat": {"id": 12345}, "text": "Hello"}}
    headers = {"X-Telegram-Bot-Api-Secret-Token": "wrong-token"}
    # Invalid header -> should be 403
    res = client.post("/webhook", json=payload, headers=headers)
    assert res.status_code == 403
    assert res.json()["detail"] == "Unauthorized"

def test_webhook_security_valid_secret(client, monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", "super-secret-token")
    
    payload = {"update_id": 99999, "message": {"chat": {"id": 12345}, "text": "Hello"}}
    headers = {"X-Telegram-Bot-Api-Secret-Token": "super-secret-token"}
    
    # We also mock internal methods so it doesn't process and return ok or duplicate
    with mock.patch("backend.routes.webhook.upsert_user", new_callable=mock.AsyncMock, return_value=1), \
         mock.patch("backend.routes.webhook.check_rate_limit", new_callable=mock.AsyncMock):
        res = client.post("/webhook", json=payload, headers=headers)
        # Should bypass 403 and return 200
        assert res.status_code == 200

