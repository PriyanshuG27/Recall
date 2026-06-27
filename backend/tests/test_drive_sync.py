import pytest
import unittest.mock as mock
import httpx
from datetime import datetime, timezone

from backend.config import settings
from backend.services.drive_sync import sync_user_to_drive
from backend.services.encryption import encrypt
from backend.scheduler.scheduler import weekly_drive_sync

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

class MockCursor:
    def __init__(self):
        self.executed = []
        self.fetchone_val = None
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

@pytest.mark.anyio
async def test_sync_user_to_drive_no_token():
    """If no Google refresh token is set for the user, return gracefully without API requests."""
    cursor = MockCursor()
    cursor.fetchone_val = (None, "123456789", 330)  # (token, chat_id, timezone_offset)
    conn = MockConnection(cursor)

    with mock.patch("httpx.AsyncClient") as mock_client:
        await sync_user_to_drive(1, conn)
        mock_client.assert_not_called()

@pytest.mark.anyio
async def test_sync_user_to_drive_success(monkeypatch):
    """Verify standard successful synchronization flow."""
    cursor = MockCursor()
    # Mock user details
    cursor.fetchone_val = (encrypt("my_refresh_token"), "123456789", 330)
    # Mock recent items
    cursor.fetchall_val = [
        ("Google Doc Sync", "Testing Drive integration", "https://example.com/doc", datetime.now(timezone.utc)),
        (None, "Testing untitled item", None, datetime.now(timezone.utc)),
    ]
    conn = MockConnection(cursor)

    called_urls = []
    def mock_http_request(request):
        url = str(request.url)
        called_urls.append((request.method, url))
        if "oauth2.googleapis.com/token" in url:
            return httpx.Response(200, json={"access_token": "mock_access_token"})
        elif "drive/v3/files" in url and request.method == "GET":
            if "mimeType" in url and "vnd.google-apps.folder" in url:
                # Folder search -> Recall folder exists
                return httpx.Response(200, json={"files": [{"id": "folder_id_123", "name": "Recall"}]})
            else:
                # File search -> Doc does not exist
                return httpx.Response(200, json={"files": []})
        elif "drive/v3/files" in url and request.method == "POST":
            # File or folder creation
            return httpx.Response(200, json={"id": "doc_id_456"})
        elif "/v1/documents/doc_id_456" in url and request.method == "GET":
            # Fetch doc length/structure
            return httpx.Response(200, json={"body": {"content": [{"endIndex": 2}]}})
        elif "/v1/documents/doc_id_456:batchUpdate" in url and request.method == "POST":
            # Document update
            return httpx.Response(200, json={})
        return httpx.Response(404)

    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(mock_http_request)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=transport, **kwargs))

    await sync_user_to_drive(1, conn)

    # Verify query for last sync update
    updates = [q for q, p in cursor.executed if "UPDATE users" in q and "google_last_sync" in q]
    assert len(updates) == 1

    # Verify API requests
    methods_and_urls = [pair for pair in called_urls]
    assert ("POST", "https://oauth2.googleapis.com/token") in methods_and_urls
    assert ("GET", "https://www.googleapis.com/drive/v3/files?q=name+%3D+%27Recall%27+and+mimeType+%3D+%27application%2Fvnd.google-apps.folder%27+and+trashed+%3D+false&spaces=drive&fields=files%28id%29") in methods_and_urls
    assert ("POST", "https://docs.googleapis.com/v1/documents/doc_id_456:batchUpdate") in methods_and_urls

@pytest.mark.anyio
async def test_sync_user_to_drive_revoked_401(monkeypatch):
    """Google returns 401: clear refresh token and notify user via Telegram sendMessage."""
    cursor = MockCursor()
    cursor.fetchone_val = (encrypt("revoked_refresh_token"), "123456789", 330)
    conn = MockConnection(cursor)

    called_urls = []
    def mock_http_request(request):
        url = str(request.url)
        called_urls.append((request.method, url))
        if "oauth2.googleapis.com/token" in url:
            return httpx.Response(401, json={"error": "invalid_grant"})
        elif "telegram.org/bot" in url and "sendMessage" in url:
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404)

    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(mock_http_request)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=transport, **kwargs))

    await sync_user_to_drive(1, conn)

    # Verify token cleared in database
    clears = [q for q, p in cursor.executed if "UPDATE users" in q and "google_refresh_token = NULL" in q]
    assert len(clears) == 1

    # Verify Telegram sendMessage request
    telegram_calls = [url for method, url in called_urls if "telegram.org" in url]
    assert len(telegram_calls) == 1

@pytest.mark.anyio
async def test_sync_user_to_drive_quota_403(monkeypatch):
    """Google returns 403: log quota/permission error and skip user without clearing token."""
    cursor = MockCursor()
    cursor.fetchone_val = (encrypt("my_refresh_token"), "123456789", 330)
    conn = MockConnection(cursor)

    called_urls = []
    def mock_http_request(request):
        url = str(request.url)
        called_urls.append((request.method, url))
        if "oauth2.googleapis.com/token" in url:
            return httpx.Response(403, json={"error": "rateLimitExceeded"})
        return httpx.Response(404)

    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(mock_http_request)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=transport, **kwargs))

    await sync_user_to_drive(1, conn)

    # Ensure google_refresh_token was NOT cleared
    clears = [q for q, p in cursor.executed if "google_refresh_token = NULL" in q]
    assert len(clears) == 0

@pytest.mark.anyio
async def test_weekly_drive_sync_job(monkeypatch):
    """Verify that weekly_drive_sync queries users and runs sync_user_to_drive for each connected user."""
    cursor = MockCursor()
    cursor.fetchall_val = [(10,), (20,)]  # Two connected users
    conn = MockConnection(cursor)

    # Mock DB pool connection
    mock_pool = mock.MagicMock()
    mock_pool.connection = lambda: MockConnection(cursor)
    
    with mock.patch("backend.scheduler.scheduler.get_pool", return_value=mock_pool), \
         mock.patch("backend.services.drive_sync.sync_user_to_drive") as mock_sync:
        await weekly_drive_sync()
        
        # Verify sync was executed for both users
        assert mock_sync.call_count == 2
        mock_sync.assert_any_call(10, mock.ANY)
        mock_sync.assert_any_call(20, mock.ANY)
