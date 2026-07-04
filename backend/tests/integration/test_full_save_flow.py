import pytest
import asyncio
import json
import os
import sys
import uuid
import time
from pathlib import Path
from unittest import mock
import psycopg
from fastapi.testclient import TestClient

# Configure SelectorEventLoop on Windows for psycopg3 async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

def run_async(coro):
    """Run an async coroutine synchronously on the Selector event loop."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

# ---------------------------------------------------------------------------
# Load .env.local to override mock settings with real Neon dev/test database
# ---------------------------------------------------------------------------
def load_real_env():
    project_root = Path(__file__).resolve().parents[3]
    env_local_path = project_root / "backend" / ".env.local"
    
    if not env_local_path.exists():
        env_local_path = Path(__file__).resolve().parents[2] / ".env.local"
        
    if env_local_path.exists():
        for line in env_local_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip().strip('"').strip("'")
                val = val.strip().strip('"').strip("'")
                os.environ[key] = val

load_real_env()

from backend.config import settings
if "DATABASE_URL" in os.environ:
    settings.DATABASE_URL = os.environ["DATABASE_URL"]
if "UPSTASH_REDIS_REST_URL" in os.environ:
    settings.UPSTASH_REDIS_REST_URL = os.environ["UPSTASH_REDIS_REST_URL"]
if "UPSTASH_REDIS_REST_TOKEN" in os.environ:
    settings.UPSTASH_REDIS_REST_TOKEN = os.environ["UPSTASH_REDIS_REST_TOKEN"]

from backend.main import app
from backend.db.connection import open_pool, close_pool
import backend.db.connection
backend.db.connection.seed_static_centroids = mock.AsyncMock()

from backend.worker import process_task, upsert_user
from backend.services.encryption import encrypt, decrypt
from backend.services.redis_client import redis, UpstashRedis

# Monkeypatch UpstashRedis to run real REST requests in tests (bypassing auto-mocking)
async def real_request(self, endpoint: str, json_data) -> dict | list:
    client = self._get_client()
    resp = await client.post(endpoint, json=json_data)
    resp.raise_for_status()
    return resp.json()

_original_upstash_request = UpstashRedis._request

@pytest.fixture(scope="module", autouse=True)
def patch_real_upstash_request():
    UpstashRedis._request = real_request
    yield
    UpstashRedis._request = _original_upstash_request

def clear_redis_client():
    """Clear the cached HTTP client inside UpstashRedis to prevent cross-event-loop issues."""
    redis._client = None

# ---------------------------------------------------------------------------
# Verification & Database Protection
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module", autouse=True)
def validate_database_branch():
    db_url = settings.DATABASE_URL
    if not db_url:
        pytest.fail("DATABASE_URL is not configured.")
    if "production" in db_url.lower() or "main" in db_url.lower():
        pytest.fail(f"Refusing execution: DATABASE_URL points to production or main branch: {db_url}")
    return db_url

# ---------------------------------------------------------------------------
# Test Mocks & Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def mock_asyncio_sleep():
    """Mock asyncio.sleep to instantly resolve and speed up batch debouncing."""
    with mock.patch("asyncio.sleep", new_callable=mock.AsyncMock) as m:
        yield m

@pytest.fixture(autouse=True)
def mock_webhook_http_client():
    """Mock the global http_client inside webhook.py to prevent any real Telegram API calls."""
    mock_client = mock.MagicMock()
    mock_client.post = mock.AsyncMock()
    with mock.patch("backend.routes.webhook.http_client", mock_client):
        yield mock_client

@pytest.fixture(autouse=True)
def mock_rate_limit():
    """Mock rate limiting to avoid Redis event loop conflicts during webhook intake."""
    with mock.patch("backend.routes.webhook.check_rate_limit", new_callable=mock.AsyncMock) as m:
        yield m

@pytest.fixture
def mock_websocket_broadcast():
    """Mock WebSocket broadcast to assert message propagation."""
    with mock.patch("backend.routes.websocket.broadcast", new_callable=mock.AsyncMock) as m:
        yield m

@pytest.fixture
def mock_cobalt_and_ai():
    """Mock yt-dlp download, Cobalt API download fallback, and AI cascade inference."""
    async def mock_download_fail(*args, **kwargs):
        raise RuntimeError("Direct yt-dlp download failed simulated error.")

    async def mock_try_cobalt(url, cobalt_url):
        return "http://mock-cobalt-server.local/stream/reel.mp3"

    async def mock_download_audio(url, dest):
        with open(dest, "wb") as f:
            f.write(b"dummy mp3 audio data")
        return True

    def mock_extract_info(url, ydl_opts=None):
        return {"title": "Mocked Instagram Reel Video Title", "description": "Mocked Instagram Reel Video Description"}

    async def mock_scrape_meta(url):
        return "Mocked Instagram Reel Video Title", "Mocked Instagram Reel Video Description"

    mock_cascade = mock.MagicMock()
    mock_cascade.transcribe = mock.AsyncMock(return_value="Sanitized Instagram Reel Transcription")
    mock_cascade.sanitize_transcript = mock.AsyncMock(return_value="Sanitized Instagram Reel Transcription")
    mock_cascade.summarise = mock.AsyncMock(return_value={
        "summary": "An amazing Instagram Reel summary detail.",
        "tags": ["instagram", "reel", "ingestion"],
        "context_prompt": "context prompt value"
    })

    async def mock_embed(text):
        return [0.1] * 384

    with mock.patch("backend.services.youtube_ingester._sync_yt_dlp_download", side_effect=mock_download_fail), \
         mock.patch("backend.services.youtube_ingester._try_cobalt", side_effect=mock_try_cobalt), \
         mock.patch("backend.services.youtube_ingester._download_audio_from_url", side_effect=mock_download_audio), \
         mock.patch("backend.services.youtube_ingester._sync_yt_dlp_extract_info", side_effect=mock_extract_info), \
         mock.patch("backend.services.youtube_ingester._scrape_instagram_meta", side_effect=mock_scrape_meta), \
         mock.patch("backend.services.youtube_ingester.AICascade", return_value=mock_cascade), \
         mock.patch("backend.worker.AICascade", return_value=mock_cascade), \
         mock.patch("backend.services.youtube_ingester.embed_text", side_effect=mock_embed), \
         mock.patch("backend.worker.embed_text", side_effect=mock_embed):
        yield {
            "cascade": mock_cascade,
            "embed": mock_embed
        }

@pytest.fixture
def client():
    from backend.db.connection import get_db
    
    async def override_get_db():
        async with await psycopg.AsyncConnection.connect(settings.DATABASE_URL) as conn:
            yield conn
            
    app.dependency_overrides[get_db] = override_get_db
    try:
        with mock.patch("backend.db.connection.open_pool", new_callable=mock.AsyncMock), \
             mock.patch("backend.db.connection.close_pool", new_callable=mock.AsyncMock):
            with TestClient(app) as c:
                yield c
    finally:
        app.dependency_overrides.pop(get_db, None)

# ---------------------------------------------------------------------------
# Helper DB/Redis Sweeper
# ---------------------------------------------------------------------------
async def sweep_test_state():
    pool = backend.db.connection._pool
    if pool:
        try:
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT id FROM users WHERE telegram_chat_id = '1001';")
                    row = await cur.fetchone()
                    if row:
                        user_id = row[0]
                        await cur.execute("DELETE FROM dead_letter_queue WHERE user_id = %s;", (user_id,))
                        await cur.execute("DELETE FROM items WHERE user_id = %s;", (user_id,))
                        await cur.execute("DELETE FROM users WHERE id = %s;", (user_id,))
                    
                    await cur.execute("DELETE FROM processed_updates WHERE update_id IN ('888123', '888124');")
                    await conn.commit()
        except Exception as e:
            print(f"Sweep DB failed: {e}")

    try:
        await redis.delete("batch:1001")
        await redis.delete("batch_last:1001")
        await redis.delete("recall:tasks")
        await redis.delete("onboarding_step:1001")
    except Exception as e:
        print(f"Sweep Redis failed: {e}")

# ---------------------------------------------------------------------------
# Scenario Tests
# ---------------------------------------------------------------------------
def test_full_instagram_reels_save_flow(client, mock_cobalt_and_ai, mock_websocket_broadcast):
    """Scenario 1: Instagram Reels Ingestion & Passive Context Enrichment."""
    payload = {
        "update_id": 888123,
        "message": {
            "message_id": 456,
            "from": {"id": 1001, "first_name": "IngestTester"},
            "chat": {"id": 1001},
            "text": "https://www.instagram.com/reel/C8x9yZ123/"
        }
    }
    
    async def run_scenario_1():
        # Open connection pool inside this event loop
        await open_pool()
        import backend.worker
        backend.worker._pool = backend.db.connection._pool
        
        try:
            # Perform initial sweep of any lingering test data
            await sweep_test_state()
            
            # 1. Trigger POST /webhook (returns ACK in < 50ms)
            clear_redis_client()
            response = client.post("/webhook", json=payload)
            assert response.status_code == 200
            assert response.json().get("status") == "ok"
            clear_redis_client()
            
            # 2. Resolve the user ID for chat_id '1001'
            pool = backend.db.connection._pool
            async with pool.connection() as conn:
                user_id = await upsert_user("1001", conn)
                await conn.commit()

            # 3. Manually construct task payload (bypassing BackgroundTasks timer debouncer)
            task_payload = {
                "chat_id": "1001",
                "user_id": user_id,
                "is_batch": True,
                "items": [
                    {
                        "update_id": "888123",
                        "content_type": "url",
                        "text": "https://www.instagram.com/reel/C8x9yZ123/",
                        "file_id": None,
                        "timestamp": time.time(),
                        "message_id": 456
                    }
                ]
            }
            
            # Execute worker processing (mocking Telegram API messaging to avoid Bad Request)
            with mock.patch("backend.worker.send_telegram_message", new_callable=mock.AsyncMock):
                await process_task(task_payload)
            
            # 4. Assert DB item written with passive_context metadata
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT raw_text, passive_context, save_time_bucket FROM items WHERE user_id = %s;", (user_id,))
                    item_row = await cur.fetchone()
                    assert item_row is not None
                    
                    raw_text, passive_context, save_time_bucket = item_row
                    assert passive_context is not None
                    p_ctx = passive_context
                    assert p_ctx["input_method"] == "url"
                    assert "time_of_day" in p_ctx
                    assert "day_of_week" in p_ctx
                    assert save_time_bucket == p_ctx["time_of_day"]
                    
                    # Assert raw_text is Fernet encrypted (starts with 'gAAAAA')
                    assert raw_text.startswith("gAAAAA")
                    decrypted_text = decrypt(raw_text)
                    assert "C8x9yZ123" in decrypted_text
            
            # 5. Assert WebSocket new_node broadcast sent to subscriber
            mock_websocket_broadcast.assert_called_once()
            ws_user_id, ws_event = mock_websocket_broadcast.call_args[0]
            assert ws_user_id == user_id
            assert ws_event["type"] == "new_node"
            assert ws_event["node"]["source_type"] in ("url", "instagram")
            
            # Final sweep of state
            await sweep_test_state()
            
        finally:
            # Safely close connection pool inside this event loop
            await close_pool()
            clear_redis_client()

    run_async(run_scenario_1())


def test_ai_cascade_fallback_and_dlq(client, mock_websocket_broadcast):
    """Scenario 2: AI Cascade Fallback & DLQ Writing."""
    payload = {
        "update_id": 888124,
        "message": {
            "message_id": 457,
            "from": {"id": 1001, "first_name": "IngestTester"},
            "chat": {"id": 1001},
            "document": {
                "file_name": "complex_scanned.pdf",
                "mime_type": "application/pdf",
                "file_id": "file_pdf_123",
                "file_size": 1048576
            }
        }
    }
    
    async def run_scenario_2():
        # Open connection pool inside this event loop
        await open_pool()
        import backend.worker
        backend.worker._pool = backend.db.connection._pool
        
        try:
            # Perform initial sweep of any lingering test data
            await sweep_test_state()
            
            # 1. Trigger POST /webhook
            clear_redis_client()
            response = client.post("/webhook", json=payload)
            assert response.status_code == 200
            assert response.json().get("status") == "ok"
            clear_redis_client()
            
            # 2. Resolve user ID
            pool = backend.db.connection._pool
            async with pool.connection() as conn:
                user_id = await upsert_user("1001", conn)
                await conn.commit()

            # 3. Construct single-item task payload
            task_payload = {
                "update_id": "888124",
                "chat_id": "1001",
                "content_type": "pdf",
                "file_id": "file_pdf_123",
                "text": None,
                "message_id": 457
            }
            
            async def mock_download_pdf(*args, **kwargs):
                temp_pdf = args[1]
                with open(temp_pdf, "wb") as f:
                    f.write(b"%PDF-1.4 mock scanned document contents")
                return temp_pdf
                
            # Mock Modal GPU/AICascade failure (raises TimeoutError/500)
            async def mock_ingest_pdf_fail(*args, **kwargs):
                raise RuntimeError("Modal GPU TimeoutError / 500 Internal Error")
                
            with mock.patch("backend.services.telegram_downloader.download_telegram_file_robust", side_effect=mock_download_pdf), \
                 mock.patch("backend.worker.ingest_pdf", side_effect=mock_ingest_pdf_fail), \
                 mock.patch("backend.worker.send_telegram_message", new_callable=mock.AsyncMock):
                 
                # Execute worker processing (triggers DLQ fallback)
                await process_task(task_payload)
                
            # 4. Verify fallback bookmark item is created with title and empty raw_text (or encrypted file_id fallback)
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    # Check items table for fallback bookmark
                    await cur.execute("SELECT raw_text, summary, title FROM items WHERE user_id = %s;", (user_id,))
                    item_rows = await cur.fetchall()
                    assert len(item_rows) == 1
                    enc_raw_text, summary, title = item_rows[0]
                    
                    # Verify raw_text is Fernet encrypted file_id fallback
                    assert enc_raw_text.startswith("gAAAAA")
                    decrypted_raw = decrypt(enc_raw_text)
                    assert decrypted_raw == "file_pdf_123"
                    assert "Could not process" in summary
                    assert title == "Bookmark: Pdf note"
                    
                    # Check dead_letter_queue table for failed payload write
                    await cur.execute("SELECT task_payload, error_message FROM dead_letter_queue WHERE user_id = %s;", (user_id,))
                    dlq_rows = await cur.fetchall()
                    assert len(dlq_rows) == 1
                    dlq_payload, dlq_err = dlq_rows[0]
                    assert "Modal GPU TimeoutError" in dlq_err
                    assert dlq_payload["content_type"] == "pdf"
                    
            # 5. Assert DLQ record exists
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT id FROM dead_letter_queue WHERE user_id = %s;", (user_id,))
                    dlq_row = await cur.fetchone()
                    assert dlq_row is not None
            
            # Final sweep of state
            await sweep_test_state()
            
        finally:
            # Safely close connection pool inside this event loop
            await close_pool()
            clear_redis_client()

    run_async(run_scenario_2())
