import pytest
import unittest.mock as mock
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

class RecordingCursor:
    def __init__(self):
        self.executed = []
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
        
    async def execute(self, query, params=None):
        self.executed.append((query, params))
        
    async def fetchone(self):
        # Match user check queries
        last_query = self.executed[-1][0].lower() if self.executed else ""
        if "users" in last_query:
            return (42, "123456789")
        return None

class RecordingConnection:
    def __init__(self, cursor_inst):
        self.cursor_inst = cursor_inst
        
    def cursor(self):
        return self.cursor_inst
        
    async def commit(self):
        pass

@pytest.fixture()
def mock_db_connection():
    cursor = RecordingCursor()
    conn = RecordingConnection(cursor)
    
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

def test_drive_endpoints_require_auth(client, mock_db_connection):
    """Endpoints should block requests with no auth cookie and return 401."""
    # 1. Sync
    resp = client.post("/api/drive/sync")
    assert resp.status_code == 401
    
    # 2. Disconnect
    resp = client.delete("/api/drive")
    assert resp.status_code == 401

def test_disconnect_drive_success(client, mock_db_connection):
    """DELETE /api/drive successfully updates the database to clear the refresh token."""
    # Generate authenticated cookie
    payload = {"sub": "42", "chat_id": "123456789"}
    token = generate_jwt(payload, settings.JWT_SECRET)
    
    resp = client.delete("/api/drive", cookies={"recall_session": token})
    assert resp.status_code == 204
    
    # Verify update query was executed to set refresh token to NULL
    queries = [q[0].strip() for q in mock_db_connection.executed]
    update_queries = [q for q in queries if "UPDATE users" in q and "SET google_refresh_token = NULL" in q]
    assert len(update_queries) == 1

def test_sync_drive_success(client, mock_db_connection):
    """POST /api/drive/sync triggers sync and returns 200."""
    payload = {"sub": "42", "chat_id": "123456789"}
    token = generate_jwt(payload, settings.JWT_SECRET)
    
    with mock.patch("backend.services.drive_sync.sync_user_to_drive") as mock_sync:
        resp = client.post("/api/drive/sync", cookies={"recall_session": token})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        mock_sync.assert_called_once()

@pytest.mark.anyio
async def test_run_google_drive_sync_success(monkeypatch):
    import httpx
    from backend.services.google_drive import run_google_drive_sync
    import backend.db.connection as db_conn
    from backend.services.encryption import encrypt

    # Mock DB cursor
    class MockCursor:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
        async def execute(self, query, params=None):
            pass
        async def fetchone(self):
            # Returns encrypted token
            return (encrypt("my_refresh_token"),)
        async def fetchall(self):
            # Returns items
            return [
                ("url", "FastAPI", "FastAPI summary", encrypt("FastAPI content"), None),
                ("pdf", "Layout paper", "Layout summary", encrypt("Layout content"), None),
            ]

    class MockConnection:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
        def cursor(self):
            return MockCursor()

    # Mock DB pool connection context manager
    mock_pool = mock.MagicMock()
    mock_pool.connection = lambda: MockConnection()
    monkeypatch.setattr(db_conn, "_pool", mock_pool)

    # Mock HTTP client responses
    called_urls = []
    def mock_http_request(request):
        url = str(request.url)
        called_urls.append((request.method, url))
        if "oauth2.googleapis.com/token" in url:
            return httpx.Response(200, json={"access_token": "mock_access_token"})
        elif "drive/v3/files" in url and request.method == "GET":
            if "mimeType" in url:
                # Folder search
                return httpx.Response(200, json={"files": [{"id": "folder_id_123", "name": "Recall"}]})
            else:
                # File search
                return httpx.Response(200, json={"files": [{"id": "backup_file_id_123", "name": "Recall Backup.md"}]})
        elif "upload/drive/v3/files/backup_file_id_123" in url and request.method == "PATCH":
            # Upload update
            return httpx.Response(200, json={"id": "backup_file_id_123"})
        return httpx.Response(404)

    # Intercept HTTP client
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(mock_http_request)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=transport, **kwargs))

    # Run the sync function
    await run_google_drive_sync(42)

    # Verify expected API endpoints were called
    methods_and_urls = [(method, url) for method, url in called_urls]
    assert ("POST", "https://oauth2.googleapis.com/token") in methods_and_urls
    assert ("GET", "https://www.googleapis.com/drive/v3/files?q=name+%3D+%27Recall%27+and+mimeType+%3D+%27application%2Fvnd.google-apps.folder%27+and+trashed+%3D+false&spaces=drive&fields=files%28id%29") in methods_and_urls
    assert ("GET", "https://www.googleapis.com/drive/v3/files?q=name+%3D+%27Recall+Backup.md%27+and+%27folder_id_123%27+in+parents+and+trashed+%3D+false&spaces=drive&fields=files%28id%2C+name%29") in methods_and_urls
    assert ("PATCH", "https://www.googleapis.com/upload/drive/v3/files/backup_file_id_123?uploadType=media") in methods_and_urls
