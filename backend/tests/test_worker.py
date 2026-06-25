"""
backend/tests/test_worker.py
============================
Unit tests for the backend task worker loop (worker.py).
"""

import pytest
import asyncio
import json
import unittest.mock as mock
from datetime import datetime, timezone

from backend.worker import process_task, worker_semaphore

# --- Mock DB Structures ---

class MockCursor:
    def __init__(self):
        self.executed = []
        self.rowcount = 1
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
        
    async def execute(self, query, params=None):
        self.executed.append((query, params))
        
    async def fetchone(self):
        last_query = self.executed[-1][0].lower() if self.executed else ""
        if "insert into items" in last_query:
            return (101,)
        if "select title" in last_query:
            return ("Mock Page Title", "Mock Summary")
        if "select raw_text" in last_query:
            # We encrypt "Mock Transcript" to match voice note raw_text
            # But let's mock encrypt/decrypt, or return mock encrypted
            return (b"gAAAAAB...", "Mock Voice Summary")
        return None

class MockConnection:
    def __init__(self):
        self.cursor_inst = MockCursor()
        
    def cursor(self):
        return self.cursor_inst
        
    async def commit(self):
        pass
        
    async def execute(self, query, params=None):
        pass
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

class MockPool:
    def __init__(self):
        self.conn = MockConnection()
        
    def connection(self):
        return self.conn


@pytest.mark.asyncio
async def test_process_text_task(monkeypatch):
    """Verify that a text task is parsed, saved, and acknowledged properly."""
    mock_pool = MockPool()
    monkeypatch.setattr("backend.worker._pool", mock_pool)
    
    mock_redis = mock.AsyncMock()
    monkeypatch.setattr("backend.worker.redis", mock_redis)
    
    monkeypatch.setattr("backend.worker.upsert_user", mock.AsyncMock(return_value=42))
    
    mock_cascade = mock.MagicMock()
    mock_cascade.summarise = mock.AsyncMock(return_value={"summary": "Mock Text Summary", "tags": ["tag1"]})
    monkeypatch.setattr("backend.worker.AICascade", lambda: mock_cascade)
    
    monkeypatch.setattr("backend.worker.embed_text", mock.AsyncMock(return_value=[0.1]*384))
    
    mock_send = mock.AsyncMock()
    monkeypatch.setattr("backend.worker.send_telegram_message", mock_send)
    
    task = {
        "update_id": "1001",
        "chat_id": "7732257445",
        "content_type": "text",
        "text": "Hello Recall!"
    }
    
    await process_task(task)
    
    mock_redis.delete.assert_called_once_with("graph:42")
    mock_send.assert_called_once_with("7732257445", "Saved ✓ — [Hello Recall!]")


@pytest.mark.asyncio
async def test_process_url_task(monkeypatch):
    """Verify that a URL task calls ingest_url and replies to the user."""
    mock_pool = MockPool()
    monkeypatch.setattr("backend.worker._pool", mock_pool)
    
    mock_redis = mock.AsyncMock()
    monkeypatch.setattr("backend.worker.redis", mock_redis)
    
    monkeypatch.setattr("backend.worker.upsert_user", mock.AsyncMock(return_value=42))
    monkeypatch.setattr("backend.worker.ingest_url", mock.AsyncMock(return_value=102))
    
    mock_send = mock.AsyncMock()
    monkeypatch.setattr("backend.worker.send_telegram_message", mock_send)
    
    task = {
        "update_id": "1002",
        "chat_id": "7732257445",
        "content_type": "url",
        "text": "https://fastapi.tiangolo.com"
    }
    
    await process_task(task)
    
    mock_redis.delete.assert_called_once_with("graph:42")
    mock_send.assert_called_once_with("7732257445", "Saved ✓ — Mock Page Title")


@pytest.mark.asyncio
async def test_process_pdf_task(monkeypatch):
    """Verify that a PDF task downloads, counts pages, calls ingest_pdf, and replies."""
    mock_pool = MockPool()
    monkeypatch.setattr("backend.worker._pool", mock_pool)
    
    mock_redis = mock.AsyncMock()
    monkeypatch.setattr("backend.worker.redis", mock_redis)
    
    monkeypatch.setattr("backend.worker.upsert_user", mock.AsyncMock(return_value=42))
    monkeypatch.setattr("backend.worker.ingest_pdf", mock.AsyncMock(return_value=103))
    
    # Mock httpx download
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"PDF dummy bytes"
    mock_response.json = lambda: {"ok": True, "result": {"file_path": "path/document.pdf", "file_size": 1000}}
    
    mock_client = mock.AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get = mock.AsyncMock(return_value=mock_response)

    class MockStreamContext:
        def __init__(self, response):
            self.response = response
        async def __aenter__(self):
            return self.response
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_stream_resp = mock.MagicMock()
    mock_stream_resp.status_code = 200
    mock_stream_resp.raise_for_status = mock.Mock()
    
    async def mock_aiter_bytes(*args, **kwargs):
        yield b"PDF dummy bytes"
        
    mock_stream_resp.aiter_bytes = mock_aiter_bytes
    
    mock_client.stream = mock.Mock(return_value=MockStreamContext(mock_stream_resp))
    
    monkeypatch.setattr("httpx.AsyncClient", lambda **kwargs: mock_client)
    
    # Mock opening fitz
    mock_doc = mock.MagicMock()
    mock_doc.__len__ = mock.MagicMock(return_value=4)
    monkeypatch.setattr("fitz.open", lambda p: mock_doc)
    
    mock_send = mock.AsyncMock()
    monkeypatch.setattr("backend.worker.send_telegram_message", mock_send)
    
    task = {
        "update_id": "1003",
        "chat_id": "7732257445",
        "content_type": "pdf",
        "file_id": "file_pdf_123"
    }
    
    await process_task(task)
    
    mock_redis.delete.assert_called_once_with("graph:42")
    # Verify page count and filename formatting
    mock_send.assert_called_once_with(
        "7732257445",
        "📄 document.pdf\n\nNo summary available.\n\nPages: 4 | Saved ✓"
    )


@pytest.mark.asyncio
async def test_process_voice_task(monkeypatch):
    """Verify that a voice task calls ingest_voice, decrypts, and replies."""
    mock_pool = MockPool()
    monkeypatch.setattr("backend.worker._pool", mock_pool)
    
    mock_redis = mock.AsyncMock()
    monkeypatch.setattr("backend.worker.redis", mock_redis)
    
    monkeypatch.setattr("backend.worker.upsert_user", mock.AsyncMock(return_value=42))
    monkeypatch.setattr("backend.worker.ingest_voice", mock.AsyncMock(return_value=104))
    monkeypatch.setattr("backend.worker.decrypt", lambda x: "Mock Transcript Decrypted")
    
    mock_send = mock.AsyncMock()
    monkeypatch.setattr("backend.worker.send_telegram_message", mock_send)
    
    task = {
        "update_id": "1004",
        "chat_id": "7732257445",
        "content_type": "voice",
        "file_id": "file_voice_123"
    }
    
    await process_task(task)
    
    mock_redis.delete.assert_called_once_with("graph:42")
    mock_send.assert_called_once_with(
        "7732257445",
        "🎙 Transcribed:\nMock Transcript Decrypted...\n\n📝 Summary:\nMock Voice Summary\n\nSaved ✓"
    )


@pytest.mark.asyncio
async def test_process_task_failure_fallback(monkeypatch):
    """Verify that a task failure writes to DLQ and saves a minimal bookmark fallback."""
    mock_pool = MockPool()
    monkeypatch.setattr("backend.worker._pool", mock_pool)
    
    mock_redis = mock.AsyncMock()
    monkeypatch.setattr("backend.worker.redis", mock_redis)
    
    monkeypatch.setattr("backend.worker.upsert_user", mock.AsyncMock(return_value=42))
    
    # Inject failure by forcing text ingestion to throw an exception
    mock_cascade = mock.MagicMock()
    mock_cascade.summarise = mock.AsyncMock(side_effect=RuntimeError("AI Cascade Exhausted"))
    monkeypatch.setattr("backend.worker.AICascade", lambda: mock_cascade)
    
    mock_write_dlq = mock.AsyncMock()
    monkeypatch.setattr("backend.worker.write_to_dlq", mock_write_dlq)
    
    mock_save_bookmark = mock.AsyncMock(return_value=201)
    monkeypatch.setattr("backend.worker.save_minimal_bookmark", mock_save_bookmark)
    
    mock_failure_msg = mock.AsyncMock()
    monkeypatch.setattr("backend.worker.send_failure_message", mock_failure_msg)
    
    task = {
        "update_id": "1005",
        "chat_id": "7732257445",
        "content_type": "text",
        "text": "Failed Text Note"
    }
    
    await process_task(task)
    
    # Assert fallback logic executed
    mock_write_dlq.assert_called_once()
    mock_save_bookmark.assert_called_once_with(42, "text", None, "Failed Text Note", mock.ANY)
    mock_failure_msg.assert_called_once_with("7732257445", "text")
    # Redis graph cache should not be deleted on total ingestion failure
    mock_redis.delete.assert_not_called()
