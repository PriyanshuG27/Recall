import pytest
import unittest.mock as mock
import io
import zipfile
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from backend.main import app
from backend.middleware.twa_auth import generate_jwt
from backend.config import settings
from backend.db.connection import get_db
from backend.services.encryption import encrypt

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
        self.items_rows = []
        self._items_iter = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def execute(self, query, params=None):
        self.executed.append((query, params))
        query_lower = query.lower()
        if "items" in query_lower:
            self._items_iter = iter(self.items_rows)

    async def fetchone(self):
        if self.executed:
            last_query = self.executed[-1][0].lower()
            if "users" in last_query:
                return (123456789, "123456789")
            elif "insert into items" in last_query:
                return (101,)
        return self.fetchone_val

    async def fetchall(self):
        return self.fetchall_val

    def __aiter__(self):
        return self

    async def __anext__(self):
        last_query = self.executed[-1][0].lower() if self.executed else ""
        if "items" in last_query and self._items_iter is not None:
            try:
                return next(self._items_iter)
            except StopIteration:
                raise StopAsyncIteration
        raise StopAsyncIteration

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
def mock_db_connection():
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

def test_okf_serialization_format():
    from backend.services.okf_service import serialize_item_to_okf
    created = datetime(2026, 6, 12, 14, 30, 0, tzinfo=timezone.utc)
    okf_str = serialize_item_to_okf(
        title="Stoicism Guide",
        tags=["philosophy", "STOIC"],
        created_at=created,
        source_url="https://plato.stanford.edu",
        context_note="Read for weekly summary.",
        category="text",
        content="This is the main stoicism text content."
    )
    
    assert "title: Stoicism Guide" in okf_str
    assert 'tags: ["philosophy", "stoic"]' in okf_str
    assert "saved_date: 2026-06-12 14:30:00" in okf_str
    assert "source_url: https://plato.stanford.edu" in okf_str
    assert 'context_note: "Read for weekly summary."' in okf_str
    assert "category: text" in okf_str
    assert "This is the main stoicism text content." in okf_str

def test_okf_parsing_format():
    from backend.services.okf_service import parse_okf_to_item
    okf_content = """---
title: Stoicism Guide
tags: ["philosophy", "stoic"]
saved_date: 2026-06-12 14:30:00
source_url: https://plato.stanford.edu
context_note: "Read for weekly summary."
category: text
---

This is the main stoicism text content."""
    
    parsed = parse_okf_to_item(okf_content)
    assert parsed["title"] == "Stoicism Guide"
    assert parsed["tags"] == ["philosophy", "stoic"]
    assert parsed["source_url"] == "https://plato.stanford.edu"
    assert parsed["context_note"] == "Read for weekly summary."
    assert parsed["category"] == "text"
    assert parsed["raw_text"] == "This is the main stoicism text content."

def test_export_zip_success(client, mock_db_connection):
    """GET /api/export/zip streams zip containing OKF Markdown files."""
    payload = {"sub": "123456789", "chat_id": "123456789"}
    token = generate_jwt(payload, settings.JWT_SECRET)

    mock_db_connection.items_rows = [
        (101, "url", "https://example.com", encrypt("Decrypted Content 1"), "summary 1", "title 1", ["tag1"], datetime.now(timezone.utc), "Prompt 1"),
        (102, "text", None, None, "summary 2", "title 2", None, datetime.now(timezone.utc), None),
    ]

    resp = client.get("/api/export/zip", cookies={"recall_session": token})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers["content-disposition"]
    assert "recall-obsidian-export-" in resp.headers["content-disposition"]

    # Parse zip
    zip_bytes = resp.content
    zip_buffer = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(zip_buffer, "r") as zf:
        namelist = zf.namelist()
        assert len(namelist) == 2
        assert any("title_1_101.md" in name for name in namelist)
        assert any("title_2_102.md" in name for name in namelist)

        # Check content of one file
        filename = [name for name in namelist if "title_1_101.md" in name][0]
        okf_str = zf.read(filename).decode("utf-8")
        assert "title: title 1" in okf_str
        assert 'tags: ["tag1"]' in okf_str
        assert "Decrypted Content 1" in okf_str

def test_import_zip_invalid_file(client, mock_db_connection):
    """POST /api/import/zip with a non-zip file returns 400."""
    payload = {"sub": "123456789", "chat_id": "123456789"}
    token = generate_jwt(payload, settings.JWT_SECRET)

    files = {"file": ("test.txt", b"some plain text", "text/plain")}
    resp = client.post("/api/import/zip", files=files, cookies={"recall_session": token})
    assert resp.status_code == 400
    assert "must be a ZIP archive" in resp.json()["detail"]

def test_import_zip_success(client, mock_db_connection):
    """POST /api/import/zip successfully decompresses, parses OKF notes, and commits chunks."""
    payload = {"sub": "123456789", "chat_id": "123456789"}
    token = generate_jwt(payload, settings.JWT_SECRET)

    # 1. Create a mock ZIP in memory containing two OKF Markdown files
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("FastAPI_Semaphores.md", """---
title: FastAPI Semaphores
tags: ["fastapi", "python"]
source_url: https://fastapi.tiangolo.com
context_note: "Useful for limit concurrency."
category: text
---
FastAPI concurrency can be limited using asyncio.Semaphore. This is a very useful technique.
This sentence is long enough to verify sentence chunking works.
""")
        zf.writestr("Stoicism.md", """---
title: Stoicism
tags: ["stoic"]
category: text
---
Stoicism teaches self-control and fortitude.
""")
    zip_bytes = zip_buffer.getvalue()

    # Mock DB response for user
    mock_db_connection.fetchone_val = (101,)  # parent item id returned on INSERT

    # Mock embed_text and redis.delete
    mock_embed = mock.AsyncMock(return_value=[0.1]*384)
    mock_redis_delete = mock.AsyncMock()

    with mock.patch("backend.services.search_service.embed_text", new=mock_embed), \
         mock.patch("backend.services.redis_client.redis.delete", new=mock_redis_delete):
        
        files = {"file": ("obsidian_vault.zip", zip_bytes, "application/zip")}
        resp = client.post("/api/import/zip", files=files, cookies={"recall_session": token})
        
        assert resp.status_code == 200
        assert resp.json() == {"status": "success", "imported_count": 2}
        
        # Verify invalidate cache was called
        mock_redis_delete.assert_called_once_with("graph:123456789")
        
        # Check executions in mock db
        insert_queries = [query for query, params in mock_db_connection.executed if "INSERT INTO items" in query]
        assert len(insert_queries) == 2
        
        chunk_queries = [query for query, params in mock_db_connection.executed if "INSERT INTO item_chunks" in query]
        assert len(chunk_queries) > 0  # Chunk insertions happened successfully

def test_import_zip_invalid_magic_bytes(client, mock_db_connection):
    """POST /api/import/zip with a .zip file having non-zip magic bytes returns 400."""
    payload = {"sub": "123456789", "chat_id": "123456789"}
    token = generate_jwt(payload, settings.JWT_SECRET)

    files = {"file": ("malicious.zip", b"not a zip file content header", "application/zip")}
    resp = client.post("/api/import/zip", files=files, cookies={"recall_session": token})
    assert resp.status_code == 400
    assert "magic bytes mismatch" in resp.json()["detail"]

def test_import_zip_payload_too_large(client, mock_db_connection):
    """POST /api/import/zip with a file exceeding 25MB returns 413."""
    payload = {"sub": "123456789", "chat_id": "123456789"}
    token = generate_jwt(payload, settings.JWT_SECRET)

    large_content = b"a" * (25 * 1024 * 1024 + 1)
    files = {"file": ("huge.zip", large_content, "application/zip")}
    resp = client.post("/api/import/zip", files=files, cookies={"recall_session": token})
    assert resp.status_code == 413
    assert "exceeds the maximum size limit" in resp.json()["detail"]
