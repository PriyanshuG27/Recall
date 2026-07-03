import pytest
import unittest.mock as mock
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from backend.main import app
from backend.config import settings
from backend.db.connection import get_db
from backend.middleware.twa_auth import generate_jwt
from backend.services.encryption import encrypt

VALID_ENV = {
    "TELEGRAM_BOT_TOKEN": "1234567890:ABCdefGHIjklmnoPQRstuvwxyZ123456789",
    "DATABASE_URL": "postgresql://user:pass@localhost:5432/db?sslmode=require",
    "UPSTASH_REDIS_REST_URL": "https://dev-recall-redis.upstash.io",
    "UPSTASH_REDIS_REST_TOKEN": "dev_upstash_redis_token",
    "FERNET_KEY": "yF4P-W965hF17Bq_Q7g_oG5l8S631P9_9z-d8v7d8sA=",
    "JWT_SECRET": "8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7b",
    "ENV": "test",
}

@pytest.fixture(autouse=True)
def patch_env(monkeypatch):
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

class MockCursor:
    def __init__(self):
        self.executed = []
        self.fetchone_val = (10, datetime.now(timezone.utc))  # (id, created_at)
        self.fetchall_val = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def execute(self, query, params=None):
        self.executed.append((query, params))

    async def fetchone(self):
        return self.fetchone_val

    async def fetchall(self):
        return self.fetchall_val

class MockConnection:
    def __init__(self, cursor_inst):
        self.cursor_inst = cursor_inst

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def cursor(self):
        return self.cursor_inst

    async def commit(self):
        pass

@pytest.fixture()
def mock_db():
    cursor = MockCursor()
    conn = MockConnection(cursor)
    
    async def _mock_get_db():
        yield conn
        
    app.dependency_overrides[get_db] = _mock_get_db
    yield cursor
    app.dependency_overrides.pop(get_db, None)

@pytest.fixture()
def client():
    with mock.patch("backend.db.connection.open_pool", return_value=None), \
         mock.patch("backend.db.connection.close_pool", return_value=None):
        with TestClient(app) as c:
            yield c

@pytest.mark.anyio
async def test_extension_save_unauthorized(client, mock_db):
    """Verify HTTP 401 is returned if no token or invalid Bearer token is provided."""
    # 1. No Authorization header
    resp = client.post("/api/extension/save", json={"url": "https://test.com"})
    assert resp.status_code == 401

    # 2. Malformed Authorization header
    resp = client.post(
        "/api/extension/save",
        json={"url": "https://test.com"},
        headers={"Authorization": "Bearer invalid-jwt-sig"}
    )
    assert resp.status_code == 401

@pytest.mark.anyio
async def test_extension_save_url_success(client, mock_db, monkeypatch):
    """Verify saving a URL item from extension works with Bearer JWT."""
    import time
    token_payload = {
        "sub": "42",
        "chat_id": "123456",
        "exp": int(time.time()) + 3600
    }
    jwt_token = generate_jwt(token_payload, settings.JWT_SECRET)

    # Mock DB user retrieval
    async def mock_fetchone_user():
        if "SELECT id" in mock_db.executed[-1][0]:
            return (42, "123456")
        return (10, datetime.now(timezone.utc))
        
    mock_db.fetchone = mock_fetchone_user

    # Mock AI Cascade summaries
    async def mock_summarise(self, text):
        return {"summary": "AI Summary of URL", "tags": ["tag1", "tag2"]}
    monkeypatch.setattr("backend.services.ai_cascade.AICascade.summarise", mock_summarise)

    # Mock embed_text
    async def mock_embed(text):
        return [0.1] * 384
    monkeypatch.setattr("backend.services.search_service.embed_text", mock_embed)

    resp = client.post(
        "/api/extension/save",
        json={"url": "https://google.com/test", "title": "My Test Title"},
        headers={"Authorization": f"Bearer {jwt_token}"}
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["source_type"] == "url"
    assert data["source_url"] == "https://google.com/test"
    assert data["title"] == "My Test Title"
    assert data["summary"] == "AI Summary of URL"
    assert "tag1" in data["tags"]

@pytest.mark.anyio
async def test_extension_save_text_success(client, mock_db, monkeypatch):
    """Verify saving a selection text item from extension works with Bearer JWT."""
    import time
    token_payload = {
        "sub": "42",
        "chat_id": "123456",
        "exp": int(time.time()) + 3600
    }
    jwt_token = generate_jwt(token_payload, settings.JWT_SECRET)

    async def mock_fetchone_user():
        if "SELECT id" in mock_db.executed[-1][0]:
            return (42, "123456")
        return (10, datetime.now(timezone.utc))
        
    mock_db.fetchone = mock_fetchone_user

    async def mock_summarise(self, text):
        return {"summary": "AI Summary of text selection", "tags": ["text"]}
    monkeypatch.setattr("backend.services.ai_cascade.AICascade.summarise", mock_summarise)

    async def mock_embed(text):
        return [0.1] * 384
    monkeypatch.setattr("backend.services.search_service.embed_text", mock_embed)

    resp = client.post(
        "/api/extension/save",
        json={"url": "https://mysite.com/page", "text": "This is selected paragraph from website.", "title": "Page Title"},
        headers={"Authorization": f"Bearer {jwt_token}"}
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["source_type"] == "text"
    assert data["source_url"] == "https://mysite.com/page"
    assert data["title"] == "Page Title"
    assert data["summary"] == "AI Summary of text selection"
    assert "text" in data["tags"]


@pytest.mark.anyio
async def test_extension_save_duplicate_url(client, mock_db):
    """Verify duplicate URL check returns HTTP 200 and the existing item."""
    import time
    token_payload = {
        "sub": "42",
        "chat_id": "123456",
        "exp": int(time.time()) + 3600
    }
    jwt_token = generate_jwt(token_payload, settings.JWT_SECRET)

    async def mock_fetchone_duplicate():
        last_query = mock_db.executed[-1][0]
        if "SELECT id" in last_query and "FROM users" in last_query:
            return (42, "123456")
        elif "FROM items" in last_query:
            return (99, 42, "url", "https://existing.com", "Existing Summary", "Existing Title", ["oldtag"], datetime.now(timezone.utc))
        return None
        
    mock_db.fetchone = mock_fetchone_duplicate

    resp = client.post(
        "/api/extension/save",
        json={"url": "https://existing.com", "title": "New Title (Ignored)"},
        headers={"Authorization": f"Bearer {jwt_token}"}
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 99
    assert data["title"] == "Existing Title"
    assert data["summary"] == "Existing Summary"
    assert "oldtag" in data["tags"]


@pytest.mark.anyio
async def test_extension_save_with_context_note_success(client, mock_db, monkeypatch):
    """Verify saving from extension with a custom context_note maps the note to DB."""
    import time
    token_payload = {
        "sub": "42",
        "chat_id": "123456",
        "exp": int(time.time()) + 3600
    }
    jwt_token = generate_jwt(token_payload, settings.JWT_SECRET)

    async def mock_fetchone_user():
        if "SELECT id" in mock_db.executed[-1][0]:
            return (42, "123456")
        return (10, datetime.now(timezone.utc))
        
    mock_db.fetchone = mock_fetchone_user

    async def mock_summarise(self, text):
        return {"summary": "AI Summary", "tags": ["tag1"]}
    monkeypatch.setattr("backend.services.ai_cascade.AICascade.summarise", mock_summarise)

    async def mock_embed(text):
        return [0.1] * 384
    monkeypatch.setattr("backend.services.search_service.embed_text", mock_embed)

    resp = client.post(
        "/api/extension/save",
        json={
            "url": "https://google.com/context-test", 
            "title": "Context Title",
            "context_note": "This is my custom user context note!"
        },
        headers={"Authorization": f"Bearer {jwt_token}"}
    )

    assert resp.status_code == 201
    
    # Check that context_note was passed to the INSERT statement
    insert_queries = [query for query, params in mock_db.executed if "INSERT INTO items" in query]
    assert len(insert_queries) == 1
    
    # Retrieve the params of the insert query
    params = [params for query, params in mock_db.executed if "INSERT INTO items" in query][0]
    assert "This is my custom user context note!" in params


@pytest.mark.anyio
async def test_extension_check_already_saved(client, mock_db):
    import time
    token_payload = {
        "sub": "42",
        "chat_id": "123456",
        "exp": int(time.time()) + 3600
    }
    jwt_token = generate_jwt(token_payload, settings.JWT_SECRET)

    # Mock user exists, then SELECT id returned (exists)
    async def mock_fetchone_already_saved():
        if "users" in mock_db.executed[-1][0]:
            return (42, "123456")
        return (100,)
    mock_db.fetchone = mock_fetchone_already_saved
    
    resp = client.get(
        "/api/extension/check?url=https://existing.com",
        headers={"Authorization": f"Bearer {jwt_token}"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"exists": True}


@pytest.mark.anyio
async def test_extension_check_not_saved(client, mock_db):
    import time
    token_payload = {
        "sub": "42",
        "chat_id": "123456",
        "exp": int(time.time()) + 3600
    }
    jwt_token = generate_jwt(token_payload, settings.JWT_SECRET)

    # Mock user exists, then SELECT id returns None (does not exist)
    async def mock_fetchone_not_saved():
        if "SELECT id" in mock_db.executed[-1][0] and "users" in mock_db.executed[-1][0]:
            return (42, "123456")
        return None
    mock_db.fetchone = mock_fetchone_not_saved
    
    resp = client.get(
        "/api/extension/check?url=https://new-url.com",
        headers={"Authorization": f"Bearer {jwt_token}"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"exists": False}


@pytest.mark.anyio
async def test_extension_download_success(client):
    resp = client.get("/api/extension/download")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers.get("content-disposition", "") or "filename=" in resp.headers.get("content-disposition", "")


@pytest.mark.anyio
async def test_extension_suggest_tags_success(client, mock_db, monkeypatch):
    """Verify that calling suggest_tags endpoint returns the AI generated tags."""
    import time
    token_payload = {
        "sub": "42",
        "chat_id": "123456",
        "exp": int(time.time()) + 3600
    }
    jwt_token = generate_jwt(token_payload, settings.JWT_SECRET)

    async def mock_fetchone_user():
        return (42, "123456")
    mock_db.fetchone = mock_fetchone_user

    async def mock_summarise(self, text):
        return {"summary": "AI Summary", "tags": ["rust", "wasm"]}
    monkeypatch.setattr("backend.services.ai_cascade.AICascade.summarise", mock_summarise)

    resp = client.get(
        "/api/extension/suggest_tags?url=https://test.com&title=RustProgramming&text=SampleText",
        headers={"Authorization": f"Bearer {jwt_token}"}
    )
    assert resp.status_code == 200
    assert resp.json() == ["rust", "wasm"]


@pytest.mark.anyio
async def test_extension_save_with_custom_tags_success(client, mock_db, monkeypatch):
    """Verify saving from extension with custom tags overrides AI tag generation."""
    import time
    token_payload = {
        "sub": "42",
        "chat_id": "123456",
        "exp": int(time.time()) + 3600
    }
    jwt_token = generate_jwt(token_payload, settings.JWT_SECRET)

    async def mock_fetchone_user():
        if "SELECT id" in mock_db.executed[-1][0]:
            return (42, "123456")
        return (10, datetime.now(timezone.utc))
    mock_db.fetchone = mock_fetchone_user

    async def mock_summarise(self, text):
        return {"summary": "AI Summary", "tags": ["tag-ai"]}
    monkeypatch.setattr("backend.services.ai_cascade.AICascade.summarise", mock_summarise)

    async def mock_embed(text):
        return [0.1] * 384
    monkeypatch.setattr("backend.services.search_service.embed_text", mock_embed)

    resp = client.post(
        "/api/extension/save",
        json={
            "url": "https://google.com/custom-tags-test",
            "title": "Custom Tags Title",
            "tags": ["custom-t1", "custom-t2"]
        },
        headers={"Authorization": f"Bearer {jwt_token}"}
    )

    assert resp.status_code == 201
    
    # Retrieve the params of the insert query
    params = [params for query, params in mock_db.executed if "INSERT INTO items" in query][0]
    # Check that custom tags are stored instead of AI tags ["tag-ai"]
    assert "custom-t1" in params[7]
    assert "custom-t2" in params[7]
    assert "tag-ai" not in params[7]
