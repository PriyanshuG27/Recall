import pytest
import json
import hashlib
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock
from backend.worker import process_task
from backend.services.redis_client import redis

@pytest.fixture
def mock_db_connection():
    conn = MagicMock()
    cursor_mock = AsyncMock()
    conn.cursor.return_value.__aenter__.return_value = cursor_mock
    conn.execute = AsyncMock()
    conn.commit = AsyncMock()
    return conn, cursor_mock

@pytest.mark.asyncio
async def test_process_onboarding_task_normal(mock_db_connection):
    """Test process_onboarding_task saves normal user input and advances onboarding step."""
    with patch("backend.worker.upsert_user", new_callable=AsyncMock) as mock_upsert, \
         patch("backend.worker.send_telegram_message", new_callable=AsyncMock) as mock_send, \
         patch("backend.worker.AICascade") as mock_cascade_cls, \
         patch("backend.worker.embed_text", new_callable=AsyncMock) as mock_embed, \
         patch("backend.worker._pool") as mock_pool, \
         patch.object(redis, "get", new_callable=AsyncMock, return_value=None), \
         patch("backend.routes.webhook.advance_onboarding_step", new_callable=AsyncMock) as mock_advance:
         
        mock_upsert.return_value = 1
        conn, cursor = mock_db_connection
        mock_pool.connection.return_value.__aenter__.return_value = conn
        
        # Mock AICascade response
        mock_cascade = MagicMock()
        mock_cascade.summarise = AsyncMock(return_value={"summary": "An interest in Python", "tags": ["code", "python"]})
        mock_cascade_cls.return_value = mock_cascade
        
        mock_embed.return_value = [0.1] * 384
        cursor.fetchone.return_value = (42, datetime.now(timezone.utc)) # item_id, created_at
        
        task_payload = {
            "chat_id": "12345",
            "content_type": "text",
            "text": "I really enjoy building backend APIs with Python and FastAPI.",
            "is_onboarding": True,
            "onboarding_step": 1
        }
        
        await process_task(task_payload)
        
        # Verify onboarding flow executed
        mock_cascade.summarise.assert_called_once_with("I really enjoy building backend APIs with Python and FastAPI.", "12345", task="onboarding")
        mock_send.assert_called_once_with("12345", "Saved: I really enjoy building backend APIs with Python and FastAPI. ✓", reply_to_message_id=None)
        mock_advance.assert_called_once()


@pytest.mark.asyncio
async def test_process_onboarding_task_spam(mock_db_connection):
    """Test process_onboarding_task handles spam input by prompting retry / skip button."""
    with patch("backend.worker.upsert_user", new_callable=AsyncMock) as mock_upsert, \
         patch("backend.worker.AICascade") as mock_cascade_cls, \
         patch("backend.worker._pool") as mock_pool, \
         patch.object(redis, "get", new_callable=AsyncMock, return_value=None), \
         patch("httpx.AsyncClient") as mock_client_cls:
         
        mock_upsert.return_value = 1
        conn, cursor = mock_db_connection
        mock_pool.connection.return_value.__aenter__.return_value = conn
        
        # Mock AICascade response as invalid onboarding input
        mock_cascade = MagicMock()
        mock_cascade.summarise = AsyncMock(return_value="INVALID_ONBOARDING_INPUT")
        mock_cascade_cls.return_value = mock_cascade
        
        # Mock httpx AsyncClient post
        mock_client = AsyncMock()
        mock_client.post = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        
        task_payload = {
            "chat_id": "12345",
            "content_type": "text",
            "text": "asdfasdfasdfasdfasdf",
            "is_onboarding": True,
            "onboarding_step": 1
        }
        
        await process_task(task_payload)
        
        # Verify skip button payload sent to Telegram API
        mock_client.post.assert_called_once()
        args, kwargs = mock_client.post.call_args
        payload = kwargs["json"]
        assert "Skip Question" in payload["reply_markup"]["inline_keyboard"][0][0]["text"]


@pytest.mark.asyncio
async def test_process_batch_task_combining(mock_db_connection):
    """Test process_task text processing and milestone checks."""
    with patch("backend.worker.upsert_user", new_callable=AsyncMock) as mock_upsert, \
         patch("backend.worker.send_telegram_message", new_callable=AsyncMock) as mock_send, \
         patch("backend.worker.AICascade") as mock_cascade_cls, \
         patch("backend.worker.embed_text", new_callable=AsyncMock) as mock_embed, \
         patch("backend.worker._pool") as mock_pool, \
         patch.object(redis, "get", new_callable=AsyncMock, return_value=None):
         
        mock_upsert.return_value = 1
        conn, cursor = mock_db_connection
        mock_pool.connection.return_value.__aenter__.return_value = conn
        
        mock_cascade = MagicMock()
        mock_cascade.summarise = AsyncMock(return_value={"summary": "Batch summary", "tags": ["batch"]})
        mock_cascade_cls.return_value = mock_cascade
        
        mock_embed.return_value = [0.1] * 384
        cursor.fetchone.side_effect = [
            None, # SELECT id, created_at FROM items WHERE ... LIMIT 1
            (43,), # INSERT RETURNING id
            (0,), # SELECT timezone_offset
            (1,), # SELECT COUNT(*) for 24h
            (datetime.now(timezone.utc),), # SELECT created_at DESC LIMIT 1
            (5,), # SELECT COUNT(*) for milestones
            ({"unlocked": []},) # SELECT node_milestones
        ]
        
        task_payload = {
            "chat_id": "12345",
            "content_type": "text",
            "text": "First save note and second save note combined"
        }
        
        await process_task(task_payload)
        assert mock_send.call_count >= 1
