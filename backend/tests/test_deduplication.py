import pytest
import hashlib
import json
from unittest.mock import patch, MagicMock, AsyncMock

from backend.worker import process_task
from backend.exceptions import DuplicateItemException
from backend.services.voice_ingester import ingest_voice

@pytest.fixture
def mock_db_connection():
    conn = MagicMock()
    cursor_mock = AsyncMock()
    
    # Setup cursor context manager
    conn.cursor.return_value.__aenter__.return_value = cursor_mock
    
    # We also need to mock conn.execute for other parts
    conn.execute = AsyncMock()
    conn.commit = AsyncMock()
    
    return conn, cursor_mock

@pytest.mark.asyncio
async def test_text_deduplication_found(mock_db_connection):
    """Test that text ingestion stops early if content_hash matches."""
    with patch("backend.worker.upsert_user", new_callable=AsyncMock) as mock_upsert, \
         patch("backend.worker.send_telegram_message", new_callable=AsyncMock) as mock_send, \
         patch("backend.worker.AICascade") as mock_cascade, \
         patch("backend.worker._pool") as mock_pool:
         
        mock_upsert.return_value = 1
        
        # Mock connection and cursor
        conn, cursor = mock_db_connection
        mock_pool.connection.return_value.__aenter__.return_value = conn
        
        # Simulate that the exact text content_hash already exists
        cursor.fetchone.return_value = (10,)
        
        task_payload = {
            "chat_id": "123",
            "content_type": "text",
            "text": "This is exactly the same text.",
            "update_id": "u1"
        }
        
        await process_task(task_payload)
        
        # Verification
        mock_send.assert_called_once_with("123", "This looks like something you've already saved.")
        mock_cascade.assert_not_called()
        # Verify it checked for the hash
        expected_hash = hashlib.sha256("This is exactly the same text.".encode()).hexdigest()[:16]
        cursor.execute.assert_called_with(
            "SELECT id FROM items WHERE user_id=%s AND content_hash=%s LIMIT 1", 
            (1, expected_hash)
        )

@pytest.mark.asyncio
async def test_url_deduplication_found(mock_db_connection):
    """Test URL deduplication."""
    with patch("backend.worker.upsert_user", new_callable=AsyncMock) as mock_upsert, \
         patch("backend.worker.send_telegram_message", new_callable=AsyncMock) as mock_send, \
         patch("backend.worker.ingest_url", new_callable=AsyncMock) as mock_ingest, \
         patch("backend.worker._pool") as mock_pool:
         
        mock_upsert.return_value = 1
        conn, cursor = mock_db_connection
        mock_pool.connection.return_value.__aenter__.return_value = conn
        
        # Simulate URL already exists
        cursor.fetchone.return_value = (42, "Existing URL Title")
        
        task_payload = {
            "chat_id": "123",
            "content_type": "url",
            "text": "https://example.com",
            "update_id": "u2"
        }
        
        await process_task(task_payload)
        
        # Verification
        mock_send.assert_called_once_with("123", "Already saved! Item ID: 42 — Existing URL Title")
        mock_ingest.assert_not_called()
        cursor.execute.assert_called_with(
            "SELECT id, title FROM items WHERE user_id=%s AND source_url=%s LIMIT 1", 
            (1, "https://example.com")
        )

@pytest.mark.asyncio
async def test_voice_deduplication_exception_handled(mock_db_connection):
    """Test that voice ingester raising DuplicateItemException is caught and user notified."""
    with patch("backend.worker.upsert_user", new_callable=AsyncMock) as mock_upsert, \
         patch("backend.worker.send_telegram_message", new_callable=AsyncMock) as mock_send, \
         patch("backend.worker.ingest_voice", new_callable=AsyncMock) as mock_ingest_voice, \
         patch("backend.worker._pool") as mock_pool:
         
        mock_upsert.return_value = 1
        conn, cursor = mock_db_connection
        mock_pool.connection.return_value.__aenter__.return_value = conn
        
        # Simulate ingest_voice raising duplicate exception
        mock_ingest_voice.side_effect = DuplicateItemException(99)
        
        task_payload = {
            "chat_id": "123",
            "content_type": "voice",
            "file_id": "file_xxx",
            "update_id": "u3"
        }
        
        await process_task(task_payload)
        
        # Verification
        mock_send.assert_called_once_with("123", "This looks like something you've already saved.")

@pytest.mark.asyncio
async def test_image_deduplication_exception_handled(mock_db_connection):
    """Test that image ingester raising DuplicateItemException is caught and user notified."""
    with patch("backend.worker.upsert_user", new_callable=AsyncMock) as mock_upsert, \
         patch("backend.worker.send_telegram_message", new_callable=AsyncMock) as mock_send, \
         patch("backend.worker.ingest_image", new_callable=AsyncMock) as mock_ingest_image, \
         patch("backend.worker._pool") as mock_pool:
         
        mock_upsert.return_value = 1
        conn, cursor = mock_db_connection
        mock_pool.connection.return_value.__aenter__.return_value = conn
        
        # Simulate ingest_image raising duplicate exception
        mock_ingest_image.side_effect = DuplicateItemException(99)
        
        task_payload = {
            "chat_id": "123",
            "content_type": "image",
            "file_id": "file_image_xxx",
            "update_id": "u4"
        }
        
        await process_task(task_payload)
        
        # Verification
        mock_send.assert_called_once_with("123", "This looks like something you've already saved.")

@pytest.mark.asyncio
async def test_pdf_deduplication_exception_handled(mock_db_connection):
    """Test that pdf ingester raising DuplicateItemException is caught and user notified."""
    with patch("backend.worker.upsert_user", new_callable=AsyncMock) as mock_upsert, \
         patch("backend.worker.send_telegram_message", new_callable=AsyncMock) as mock_send, \
         patch("backend.worker.ingest_pdf", new_callable=AsyncMock) as mock_ingest_pdf, \
         patch("backend.worker._pool") as mock_pool, \
         patch("backend.services.telegram_downloader.download_telegram_file_robust", new_callable=AsyncMock) as mock_download, \
         patch("fitz.open") as mock_fitz_open:
         
        mock_upsert.return_value = 1
        conn, cursor = mock_db_connection
        mock_pool.connection.return_value.__aenter__.return_value = conn
        
        mock_download.return_value = "dummy.pdf"
        # Mock fitz.open to return a document with page count
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 5
        mock_fitz_open.return_value = mock_doc
        
        # Simulate ingest_pdf raising duplicate exception
        mock_ingest_pdf.side_effect = DuplicateItemException(99)
        
        task_payload = {
            "chat_id": "123",
            "content_type": "pdf",
            "file_id": "file_pdf_xxx",
            "update_id": "u5"
        }
        
        await process_task(task_payload)
        
        # Verification
        mock_send.assert_called_once_with("123", "This looks like something you've already saved.")

