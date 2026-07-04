import pytest
import unittest.mock as mock
from backend.worker import process_task

@pytest.mark.asyncio
async def test_worker_process_task_unknown_type():
    payload = {
        "chat_id": "999888",
        "content_type": "unknown_invalid_type",
        "update_id": "u_invalid"
    }
    with mock.patch("backend.worker.upsert_user", new_callable=mock.AsyncMock, return_value=1), \
         mock.patch("backend.worker._pool") as mock_pool, \
         mock.patch("backend.worker.send_telegram_message", new_callable=mock.AsyncMock) as mock_send:
        
        conn = mock.MagicMock()
        conn.execute = mock.AsyncMock()
        conn.commit = mock.AsyncMock()
        cursor = mock.AsyncMock()
        conn.cursor.return_value.__aenter__.return_value = cursor
        mock_pool.connection.return_value.__aenter__.return_value = conn
        
        await process_task(payload)

@pytest.mark.asyncio
async def test_worker_process_task_text_flow():
    payload = {
        "chat_id": "999888",
        "content_type": "text",
        "text": "FastAPI async testing content",
        "update_id": "u_text"
    }
    with mock.patch("backend.worker.upsert_user", new_callable=mock.AsyncMock, return_value=1), \
         mock.patch("backend.worker._pool") as mock_pool, \
         mock.patch("backend.worker.send_telegram_message", new_callable=mock.AsyncMock) as mock_send, \
         mock.patch("backend.worker.AICascade") as mock_cascade_cls:
        
        mock_cascade = mock.MagicMock()
        mock_cascade.summarise = mock.AsyncMock(return_value={"summary": "sum", "tags": ["test"], "context_prompt": "prompt?"})
        mock_cascade_cls.return_value = mock_cascade

        conn = mock.MagicMock()
        conn.execute = mock.AsyncMock()
        conn.commit = mock.AsyncMock()
        cursor = mock.AsyncMock()
        from datetime import datetime
        cursor.fetchone.return_value = (101, datetime.now(), "summary")
        conn.cursor.return_value.__aenter__.return_value = cursor
        mock_pool.connection.return_value.__aenter__.return_value = conn
        
        await process_task(payload)
        assert mock_send.called
