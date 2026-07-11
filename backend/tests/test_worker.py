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
        query = self.executed[-1][0].lower() if self.executed else ""
        if "insert into items" in query:
            return (101,)
        if "select title" in query and "summary" in query:
            return ("Mock Page Title", "Mock Summary", ["tech", "python"])
        if "select summary" in query:
            return ("Mock Voice Summary", ["voice"])
        if "select raw_text" in query:
            return (b"gAAAAAB...", "Mock Voice Summary")
        return None

    async def fetchall(self):
        query = self.executed[-1][0].lower() if self.executed else ""
        if "select id, title, summary, tags, embedding" in query:
            # mock embedding string value with 384 dimensions
            mock_emb_str = "[" + ",".join(["0.1"]*384) + "]"
            return [(101, "Mock Page Title", "Mock Summary", ["tech"], mock_emb_str, "url", "https://example.com", None)]
        return []

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
        
    def connection(self, **kwargs):
        return self.conn


@pytest.mark.asyncio
async def test_process_text_task(monkeypatch):
    """Verify that a text task is parsed, saved, and acknowledged properly."""
    mock_pool = MockPool()
    monkeypatch.setattr("backend.db.connection._pool", mock_pool)
    
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
    # New Phase-6 format: emoji_title + summary + divider + tags + Saved.
    call_args = mock_send.call_args
    sent_text = call_args[0][1]
    sent_kwargs = call_args[1] if call_args[1] else {}
    sent_markup = call_args[0][2] if len(call_args[0]) > 2 else sent_kwargs.get("reply_markup")
    assert "Hello Recall!" in sent_text
    assert "Mock Text Summary" in sent_text
    assert "Saved." in sent_text
    assert sent_markup is not None


@pytest.mark.asyncio
async def test_process_url_task(monkeypatch):
    """Verify that a URL task calls ingest_url and replies to the user."""
    mock_pool = MockPool()
    monkeypatch.setattr("backend.db.connection._pool", mock_pool)
    
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
    # New Phase-6 format: intelligence-brief with divider and Saved.
    call_args = mock_send.call_args
    sent_text = call_args[0][1]
    sent_kwargs = call_args[1] if call_args[1] else {}
    sent_markup = call_args[0][2] if len(call_args[0]) > 2 else sent_kwargs.get("reply_markup")
    assert "Mock Page Title" in sent_text
    assert "Mock Summary" in sent_text
    assert "Saved." in sent_text
    assert sent_markup is not None



@pytest.mark.asyncio
async def test_process_url_task_private_google_drive(monkeypatch):
    """Verify that a private Google Drive URL error is handled gracefully with instruction response."""
    mock_pool = MockPool()
    monkeypatch.setattr("backend.db.connection._pool", mock_pool)
    
    mock_redis = mock.AsyncMock()
    monkeypatch.setattr("backend.worker.redis", mock_redis)
    
    monkeypatch.setattr("backend.worker.upsert_user", mock.AsyncMock(return_value=42))
    
    async def mock_ingest_error(*args, **kwargs):
        raise ValueError("private Google Drive link")
    monkeypatch.setattr("backend.worker.ingest_url", mock_ingest_error)
    
    mock_send = mock.AsyncMock()
    monkeypatch.setattr("backend.worker.send_telegram_message", mock_send)
    
    task = {
        "update_id": "1003",
        "chat_id": "7732257445",
        "content_type": "url",
        "text": "https://drive.google.com/file/d/123/view"
    }
    
    await process_task(task)
    
    # Verify no graph delete (since it didn't save)
    assert not mock_redis.delete.called
    
    # Verify bot message uses the new calm, short error message
    mock_send.assert_called_once()
    called_text = mock_send.call_args[0][1]
    assert "That Drive file is private" in called_text
    assert "Share it publicly" in called_text


@pytest.mark.asyncio
async def test_process_pdf_task(monkeypatch):
    """Verify that a PDF task downloads, counts pages, calls ingest_pdf, and replies."""
    mock_pool = MockPool()
    monkeypatch.setattr("backend.db.connection._pool", mock_pool)
    
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
    # New Phase-6 format: intelligence brief — no page count, no "Saved ✓"
    call_args = mock_send.call_args
    sent_text = call_args[0][1]
    sent_kwargs = call_args[1] if call_args[1] else {}
    sent_markup = call_args[0][2] if len(call_args[0]) > 2 else sent_kwargs.get("reply_markup")
    assert "document.pdf" in sent_text
    assert "Saved." in sent_text
    assert "Pages:" not in sent_text
    assert sent_markup is not None


@pytest.mark.asyncio
async def test_process_voice_task(monkeypatch):
    """Verify that a voice task calls ingest_voice, decrypts, and replies."""
    mock_pool = MockPool()
    monkeypatch.setattr("backend.db.connection._pool", mock_pool)
    
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
    # New Phase-6 format: compact summary-based brief, no transcript dump
    call_args = mock_send.call_args
    sent_text = call_args[0][1]
    sent_kwargs = call_args[1] if call_args[1] else {}
    sent_markup = call_args[0][2] if len(call_args[0]) > 2 else sent_kwargs.get("reply_markup")
    assert "Voice note" in sent_text
    assert "Saved." in sent_text
    assert sent_markup is not None


@pytest.mark.asyncio
async def test_process_task_failure_fallback(monkeypatch):
    """Verify that a task failure writes to DLQ and saves a minimal bookmark fallback."""
    mock_pool = MockPool()
    monkeypatch.setattr("backend.db.connection._pool", mock_pool)
    
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


@pytest.mark.asyncio
async def test_process_batch_with_deferred_replies(monkeypatch):
    """Verify that process_batch_task correctly pulls and applies deferred replies from Redis."""
    mock_pool = MockPool()
    monkeypatch.setattr("backend.db.connection._pool", mock_pool)
    
    mock_redis = mock.AsyncMock()
    # Mock lrange to return a deferred context note reply
    deferred_reply = json.dumps({"text": "Delicious Noida burger concept", "message_id": 124})
    mock_redis.lrange.side_effect = lambda key, start, stop: [deferred_reply] if "deferred_replies" in key else []
    monkeypatch.setattr("backend.worker.redis", mock_redis)
    
    monkeypatch.setattr("backend.worker.upsert_user", mock.AsyncMock(return_value=42))
    
    # Mock process_single_item to return a fake saved item id
    monkeypatch.setattr("backend.worker.process_single_item", mock.AsyncMock(return_value=(101, True)))
    
    mock_send = mock.AsyncMock()
    monkeypatch.setattr("backend.worker.send_telegram_message", mock_send)
    monkeypatch.setattr("backend.worker.check_user_milestones", mock.AsyncMock())
    
    # Pushing batch task
    task = {
        "is_batch": True,
        "chat_id": "7732257445",
        "update_id": "9999",
        "items": [
            {
                "content_type": "url",
                "text": "https://www.instagram.com/reel/abc/",
                "message_id": 122
            }
        ]
    }
    
    from backend.worker import process_batch_task
    await process_batch_task(task, 42, "7732257445")
    
    # Verify that lrange was checked for the user's message_id
    mock_redis.lrange.assert_called_with("deferred_replies:7732257445:122", 0, -1)
    
    # Verify that the deferred reply key was deleted
    mock_redis.delete.assert_any_call("deferred_replies:7732257445:122")
