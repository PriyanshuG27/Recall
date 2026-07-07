import time
import pytest
import json
import asyncio
import httpx
import unittest.mock as mock
from fastapi import Depends
from fastapi.testclient import TestClient

# Mock environment setup
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


from backend.main import app
from backend.routes.webhook import ACK_MESSAGES


# ---------------------------------------------------------------------------
# Stateful DB Mock for Idempotency
# ---------------------------------------------------------------------------
class MockDbState:
    def __init__(self):
        self.processed = set()
        self.users = {}  # telegram_chat_id -> internal_id


class StatefulMockCursor:
    def __init__(self, state, lock):
        self.state = state
        self.lock = lock
        self.rowcount = 0
        self._last_val = None
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
        
    async def execute(self, query, params=None):
        query_upper = query.upper()
        if "INSERT INTO PROCESSED_UPDATES" in query_upper:
            update_id = params[0]
            # Use lock to guarantee thread/async-safety for concurrent tests
            async with self.lock:
                if update_id in self.state.processed:
                    self.rowcount = 0
                else:
                    self.state.processed.add(update_id)
                    self.rowcount = 1
        elif "INSERT INTO USERS" in query_upper:
            chat_id = params[0]
            async with self.lock:
                if chat_id in self.state.users:
                    self._last_val = None
                else:
                    user_id = len(self.state.users) + 1
                    self.state.users[chat_id] = user_id
                    self._last_val = user_id
        elif "SELECT ID FROM USERS" in query_upper or "SELECT ID, TELEGRAM_CHAT_ID FROM USERS" in query_upper:
            chat_id = params[0]
            async with self.lock:
                user_id = self.state.users.get(chat_id)
                self._last_val = user_id
        elif "SELECT COUNT(*)" in query_upper:
            self._last_val = 3
                    
    async def fetchone(self):
        if self._last_val is not None:
            val = (self._last_val, str(self._last_val))  # return tuple matching row shape if needed
            self._last_val = None
            return val
        return None


class StatefulMockConnection:
    def __init__(self, state, lock):
        self.state = state
        self._cursor = StatefulMockCursor(state, lock)
        
    def cursor(self):
        return self._cursor
        
    async def commit(self):
        pass


@pytest.fixture()
def db_state():
    return MockDbState()


@pytest.fixture(autouse=True)
def override_db(db_state):
    from backend.db.connection import get_db
    lock = asyncio.Lock()
    
    async def _mock_get_db():
        yield StatefulMockConnection(db_state, lock)
        
    app.dependency_overrides[get_db] = _mock_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Mocks for external network tasks
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def mock_redis():
    with mock.patch("backend.routes.webhook.redis", new_callable=mock.AsyncMock) as m:
        async def dynamic_pipeline(cmds):
            results = []
            for cmd in cmds:
                name = cmd[0].upper()
                if name == "RPUSH":
                    results.append(1)
                elif name == "SETEX":
                    results.append(True)
                elif name == "LRANGE":
                    results.append([])
                elif name == "DEL":
                    results.append(1)
                else:
                    results.append(None)
            return results
        m.pipeline.side_effect = dynamic_pipeline
        m.get.return_value = None
        m.setex.return_value = True
        yield m

@pytest.fixture(autouse=True)
def mock_sleep():
    with mock.patch("asyncio.sleep", new_callable=mock.AsyncMock) as m:
        yield m


@pytest.fixture()
def mock_telegram_ack():
    with mock.patch("backend.routes.webhook.send_telegram_ack", new_callable=mock.AsyncMock) as m:
        yield m


@pytest.fixture(autouse=True)
def mock_rate_limit():
    with mock.patch("backend.routes.webhook.check_rate_limit", new_callable=mock.AsyncMock) as m:
        yield m


@pytest.fixture()
def client():
    with mock.patch("backend.db.connection.open_pool", return_value=None), \
         mock.patch("backend.db.connection.close_pool", return_value=None):
        with TestClient(app) as c:
            yield c


# ---------------------------------------------------------------------------
# Webhook Payload Builder
# ---------------------------------------------------------------------------
def make_telegram_update(update_id: int, chat_id: int, message_fields: dict) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 999,
            "chat": {"id": chat_id},
            "date": int(time.time()),
            **message_fields
        }
    }


# ---------------------------------------------------------------------------
# Unit Tests: Idempotency (TESTING.md §1)
# ---------------------------------------------------------------------------
def test_first_delivery(client, db_state, mock_redis, mock_telegram_ack):
    """Case 1: First delivery -> 200, db entry created, task enqueued, Telegram ACK sent."""
    payload = make_telegram_update(111, 12345, {"text": "Hello world"})
    
    start_time = time.perf_counter()
    response = client.post("/webhook", json=payload)
    end_time = time.perf_counter()
    
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "111" in db_state.processed
    
    # Verify task enqueued in Redis
    assert mock_redis.pipeline.call_count == 1
    pipeline_cmds = mock_redis.pipeline.call_args[0][0]
    assert pipeline_cmds[0][0] == "RPUSH"
    assert pipeline_cmds[0][1] == "batch:12345"
    task_payload = json.loads(pipeline_cmds[0][2])
    assert task_payload["update_id"] == "111"
    assert task_payload["content_type"] == "text"
    assert task_payload["text"] == "Hello world"
    
    # Verify Telegram ACK dispatched
    assert mock_telegram_ack.call_count == 1
    mock_telegram_ack.assert_called_with("12345", ACK_MESSAGES["text"], None, 999)
    
    # Time must be < 50ms (0.05 seconds)
    assert (end_time - start_time) < 0.05


def test_duplicate_delivery(client, db_state, mock_redis, mock_telegram_ack):
    """Case 2: Duplicate delivery -> 200 returned immediately, no new task, db unchanged."""
    payload = make_telegram_update(111, 12345, {"text": "Hello world"})
    
    # Pre-populate db with the update_id
    db_state.processed.add("111")
    
    response = client.post("/webhook", json=payload)
    
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "detail": "duplicate"}
    
    # No Redis LPUSH and no Telegram ACK
    assert mock_redis.pipeline.call_count == 0
    assert mock_telegram_ack.call_count == 0


def test_different_update_id(client, db_state, mock_redis, mock_telegram_ack):
    """Case 3: Different update_id -> enqueues second task independently."""
    payload1 = make_telegram_update(111, 12345, {"text": "Hello world"})
    payload2 = make_telegram_update(112, 12345, {"text": "Hello again"})
    
    response1 = client.post("/webhook", json=payload1)
    response2 = client.post("/webhook", json=payload2)
    
    assert response1.status_code == 200
    assert response2.status_code == 200
    assert "111" in db_state.processed
    assert "112" in db_state.processed
    
    assert mock_redis.pipeline.call_count == 2
    assert mock_telegram_ack.call_count == 2


@pytest.mark.anyio
async def test_concurrent_duplicates(db_state, mock_redis, mock_telegram_ack):
    """Case 4: Concurrent duplicates -> exactly one task is enqueued."""
    payload = make_telegram_update(113, 12345, {"text": "Concurrent"})
    
    with mock.patch("backend.db.connection.open_pool", return_value=None), \
         mock.patch("backend.db.connection.close_pool", return_value=None):
         
        # Use httpx.AsyncClient to execute requests concurrently
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            tasks = [
                ac.post("/webhook", json=payload),
                ac.post("/webhook", json=payload),
                ac.post("/webhook", json=payload)
            ]
            responses = await asyncio.gather(*tasks)
            
    # All must return 200 OK
    for r in responses:
        assert r.status_code == 200
        
    # DB must have exactly one record
    assert "113" in db_state.processed
    assert len(db_state.processed) == 1
    
    # Only one task enqueued and one ACK sent
    assert mock_redis.pipeline.call_count == 1
    assert mock_telegram_ack.call_count == 1


# ---------------------------------------------------------------------------
# Unit Tests: Content Type Detection & ACK Messages
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "message_fields,expected_type,expected_ack",
    [
        ({"voice": {"file_id": "voice_1"}}, "voice", ACK_MESSAGES["voice"]),
        ({"document": {"file_name": "doc.pdf", "mime_type": "application/pdf", "file_id": "pdf_1"}}, "pdf", ACK_MESSAGES["pdf"]),
        ({"text": "https://google.com"}, "url", ACK_MESSAGES["url"]),
        ({"photo": [{"file_id": "ph_small", "file_size": 10}, {"file_id": "ph_large", "file_size": 100}]}, "photo", ACK_MESSAGES["photo"]),
        ({"text": "Just plain text here"}, "text", ACK_MESSAGES["text"]),
        ({"video": {"file_id": "vid_1"}}, "unsupported", ACK_MESSAGES["unsupported"]),
    ]
)
def test_content_type_ack_mapping(client, mock_redis, mock_telegram_ack, message_fields, expected_type, expected_ack):
    """Verifies that all 6 content types parse correctly and dispatch correct ACKs."""
    payload = make_telegram_update(999, 12345, message_fields)
    
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    
    # Verify task content type in Redis push (only if supported)
    if expected_type == "unsupported":
        assert mock_redis.pipeline.call_count == 0
    else:
        assert mock_redis.pipeline.call_count == 1
        pipeline_cmds = mock_redis.pipeline.call_args[0][0]
        assert pipeline_cmds[0][0] == "RPUSH"
        assert pipeline_cmds[0][1] == "batch:12345"
        task_payload = json.loads(pipeline_cmds[0][2])
        assert task_payload["content_type"] == expected_type
    
    # Verify Telegram ACK string
    assert mock_telegram_ack.call_count == 1
    mock_telegram_ack.assert_called_with("12345", expected_ack, None, 999)


def test_webhook_start_command(client, db_state, mock_redis, mock_telegram_ack):
    """Verifies that sending /start upserts the user and replies with the welcome message."""
    payload = make_telegram_update(1001, 77777, {"text": "/start"})
    
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "detail": "welcome_sent"}
    
    # User should be in mocked database state
    assert "77777" in db_state.users
    assert db_state.users["77777"] == 1
    
    # Redis push should not happen for /start command
    assert mock_redis.pipeline.call_count == 0
    
    # Welcome ACK message sent to user
    welcome_msg = (
        "Welcome back to Recall! Forward me any link, voice note, PDF, or image and I'll remember it for you.\n\n"
        "💡 <b>We also support screenshots!</b> You can send us screenshots of your <b>WhatsApp Saved Messages</b> (or chats containing links), and we will automatically scrape, clean, and save them for you!"
    )
    assert mock_telegram_ack.call_count == 1
    mock_telegram_ack.assert_called_with("77777", welcome_msg, "HTML")


def test_webhook_rate_limit_exceeded(client, mock_redis, mock_telegram_ack):
    """Verifies that when rate limit is exceeded, webhook returns 200 and does NOT queue task or send ACK."""
    from backend.services.rate_limiter import RateLimitExceeded
    
    with mock.patch("backend.routes.webhook.check_rate_limit", side_effect=RateLimitExceeded(retry_after=42.0)):
        payload = make_telegram_update(1002, 12345, {"text": "hello"})
        response = client.post("/webhook", json=payload)
        
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "detail": "rate_limited"}
        
        # Verify no task queued and no ACK sent
        assert mock_redis.pipeline.call_count == 0
        assert mock_telegram_ack.call_count == 0
