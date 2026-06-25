import time
import pytest
import json
import asyncio
import httpx
from datetime import datetime, timezone, timedelta
import unittest.mock as mock
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

class MockDbState:
    def __init__(self):
        self.processed = set()
        self.users = {"12345": 1, "67890": 2}
        self.streak_counts = {1: 5, 2: 0}
        
        # Pre-seed items
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        from backend.services.encryption import encrypt
        self.items = [
            {
                "id": 10,
                "user_id": 1,
                "source_type": "url",
                "title": "Article 1",
                "source_url": "https://google.com",
                "created_at": now - timedelta(hours=2)
            },
            {
                "id": 11,
                "user_id": 1,
                "source_type": "voice",
                "title": "Voice note",
                "source_url": "mock_voice_file_id",
                "created_at": now - timedelta(days=1)
            },
            {
                "id": 12,
                "user_id": 1,
                "source_type": "text",
                "title": "Text note",
                "raw_text": encrypt("Hello Recall Note"),
                "created_at": now - timedelta(hours=3)
            },
            {
                "id": 20,
                "user_id": 2,
                "source_type": "url",
                "title": "Other User Article",
                "source_url": "https://other.com",
                "created_at": now - timedelta(minutes=5)
            }
        ]
        self.quizzes = [
            {"id": 100, "user_id": 1},
            {"id": 101, "user_id": 1}
        ]

class StatefulMockCursor:
    def __init__(self, state):
        self.state = state
        self.rowcount = 0
        self._last_val = None
        self._rows = []
        self._row_idx = 0
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
        
    async def execute(self, query, params=None):
        query_upper = query.upper()
        self._rows = []
        self._row_idx = 0
        self._last_val = None
        
        if "INSERT INTO PROCESSED_UPDATES" in query_upper:
            update_id = params[0]
            if update_id in self.state.processed:
                self.rowcount = 0
            else:
                self.state.processed.add(update_id)
                self.rowcount = 1
                
        elif "INSERT INTO USERS" in query_upper:
            chat_id = params[0]
            if chat_id not in self.state.users:
                user_id = len(self.state.users) + 1
                self.state.users[chat_id] = user_id
                self.state.streak_counts[user_id] = 0
            self._last_val = self.state.users[chat_id]
            
        elif "SELECT ID FROM USERS" in query_upper:
            chat_id = params[0]
            self._last_val = self.state.users.get(chat_id)
            
        elif "SELECT ID, TITLE, SOURCE_TYPE, CREATED_AT FROM ITEMS" in query_upper:
            u_id = params[0]
            user_items = [item for item in self.state.items if item["user_id"] == u_id]
            user_items.sort(key=lambda x: x["created_at"], reverse=True)
            self._rows = [(item["id"], item["title"], item["source_type"], item["created_at"]) for item in user_items]
            
        elif "SELECT SOURCE_TYPE, SOURCE_URL, RAW_TEXT, TITLE FROM ITEMS" in query_upper:
            item_id = params[0]
            u_id = params[1]
            found = [item for item in self.state.items if item["id"] == item_id and item["user_id"] == u_id]
            if found:
                item = found[0]
                self._rows = [(
                    item["source_type"],
                    item.get("source_url"),
                    item.get("raw_text"),
                    item.get("title")
                )]
            
        elif "DELETE FROM ITEMS" in query_upper:
            item_id = params[0]
            u_id = params[1]
            before_len = len(self.state.items)
            self.state.items = [item for item in self.state.items if not (item["id"] == item_id and item["user_id"] == u_id)]
            after_len = len(self.state.items)
            self.rowcount = before_len - after_len
            
        elif "SELECT SOURCE_TYPE, COUNT(*)" in query_upper:
            u_id = params[0]
            from collections import Counter
            counts = Counter(item["source_type"] for item in self.state.items if item["user_id"] == u_id)
            self._rows = list(counts.items())
            
        elif "SELECT COUNT(*) FROM QUIZZES" in query_upper:
            u_id = params[0]
            count = sum(1 for q in self.state.quizzes if q["user_id"] == u_id)
            self._rows = [(count,)]
            
        elif "SELECT STREAK_COUNT FROM USERS" in query_upper:
            u_id = params[0]
            streak = self.state.streak_counts.get(u_id, 0)
            self._rows = [(streak,)]

    async def fetchone(self):
        if self._last_val is not None:
            val = (self._last_val, str(self._last_val))
            self._last_val = None
            return val
        if self._rows and self._row_idx < len(self._rows):
            val = self._rows[self._row_idx]
            self._row_idx += 1
            return val
        return None
        
    async def fetchall(self):
        res = self._rows[self._row_idx:]
        self._row_idx = len(self._rows)
        return res

class StatefulMockConnection:
    def __init__(self, state):
        self.state = state
        self._cursor = StatefulMockCursor(state)
        
    def cursor(self):
        return self._cursor
        
    async def commit(self):
        pass

@pytest.fixture()
def db_state():
    return MockDbState()

@pytest.fixture(autouse=True)
def override_db(patch_env, db_state):
    from backend.db.connection import get_db
    
    async def _mock_get_db():
        yield StatefulMockConnection(db_state)
        
    app.dependency_overrides[get_db] = _mock_get_db
    yield
    app.dependency_overrides.pop(get_db, None)

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

def make_telegram_update(update_id: int, chat_id: int, text: str) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 999,
            "chat": {"id": chat_id},
            "date": int(time.time()),
            "text": text
        }
    }

def test_command_help(client, mock_telegram_ack):
    payload = make_telegram_update(2001, 12345, "/help")
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    assert response.json()["detail"] == "help_sent"
    
    mock_telegram_ack.assert_called_once()
    args = mock_telegram_ack.call_args[0]
    assert args[0] == "12345"
    assert "/start" in args[1]
    assert "/stats" in args[1]
    assert "/search" in args[1]
    assert "/delete" in args[1]

def test_command_list(client, mock_telegram_ack):
    payload = make_telegram_update(2002, 12345, "/list")
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    assert response.json()["detail"] == "list_sent"
    
    mock_telegram_ack.assert_called_once()
    args = mock_telegram_ack.call_args[0]
    assert args[0] == "12345"
    assert "📋 Your last 10 saves:" in args[1]
    assert "Article 1" in args[1]
    assert "Voice note" in args[1]
    assert "/file_10" in args[1]
    assert "/file_11" in args[1]

def test_command_delete_success(client, db_state, mock_telegram_ack):
    # User 1 deletes item 10
    payload = make_telegram_update(2003, 12345, "/delete 10")
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    assert response.json()["detail"] == "delete_processed"
    
    mock_telegram_ack.assert_called_once_with("12345", "Deleted ✓")
    # Verify item 10 is deleted from state
    assert not any(item["id"] == 10 for item in db_state.items)

def test_command_delete_unowned(client, db_state, mock_telegram_ack):
    # User 1 attempts to delete User 2's item 20
    payload = make_telegram_update(2004, 12345, "/delete 20")
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    assert response.json()["detail"] == "delete_processed"
    
    mock_telegram_ack.assert_called_once_with("12345", "Item not found.")
    # Verify item 20 is still in state
    assert any(item["id"] == 20 for item in db_state.items)

def test_command_delete_invalid_arg(client, mock_telegram_ack):
    # User sends /delete without args
    payload = make_telegram_update(2005, 12345, "/delete")
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    mock_telegram_ack.assert_called_once_with("12345", "Please provide a valid item ID: /delete 42")
    
    # User sends /delete with non-integer arg
    mock_telegram_ack.reset_mock()
    payload = make_telegram_update(2006, 12345, "/delete abc")
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    mock_telegram_ack.assert_called_once_with("12345", "Please provide a valid item ID: /delete 42")

def test_command_stats(client, mock_telegram_ack):
    payload = make_telegram_update(2007, 12345, "/stats")
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    assert response.json()["detail"] == "stats_sent"
    
    mock_telegram_ack.assert_called_once()
    args = mock_telegram_ack.call_args[0]
    assert args[0] == "12345"
    assert "📊 Your Recall stats:" in args[1]
    assert "Total saves: 3" in args[1]
    assert "Links: 1" in args[1]
    assert "Voice: 1" in args[1]
    assert "Texts: 1" in args[1]
    assert "Quizzes answered: 2" in args[1]
    assert "Current streak: 🔥 5 days" in args[1]

def test_command_unknown(client, mock_telegram_ack):
    payload = make_telegram_update(2008, 12345, "/unknown_cmd")
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    assert response.json()["detail"] == "unknown_command_sent"
    
    mock_telegram_ack.assert_called_once_with("12345", "Unknown command. Type /help to see all commands.")

# --- /FILE COMMAND TESTS ---

def test_command_file_missing_arg(client, mock_telegram_ack):
    payload = make_telegram_update(2009, 12345, "/file")
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    assert response.json()["detail"] == "file_processed"
    mock_telegram_ack.assert_called_once_with("12345", "Please provide an item ID: /file 42")

def test_command_file_invalid_arg(client, mock_telegram_ack):
    payload = make_telegram_update(2010, 12345, "/file abc")
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    assert response.json()["detail"] == "file_processed"
    mock_telegram_ack.assert_called_once_with("12345", "Please provide a valid item ID: /file 42")

def test_command_file_not_found(client, mock_telegram_ack):
    payload = make_telegram_update(2011, 12345, "/file 999")
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    assert response.json()["detail"] == "file_processed"
    mock_telegram_ack.assert_called_once_with("12345", "Item not found.")

def test_command_file_voice_success(client, mock_telegram_ack):
    # Mock send_telegram_media inside webhook
    with mock.patch("backend.routes.webhook.send_telegram_media") as mock_media:
        payload = make_telegram_update(2012, 12345, "/file 11")
        response = client.post("/webhook", json=payload)
        assert response.status_code == 200
        assert response.json()["detail"] == "file_processed"
        mock_media.assert_called_once_with("12345", "voice", "mock_voice_file_id", "Voice note")

def test_command_file_note_success(client, mock_telegram_ack):
    payload = make_telegram_update(2013, 12345, "/file 12")
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    assert response.json()["detail"] == "file_processed"
    mock_telegram_ack.assert_called_once_with("12345", "📝 Saved Note:\nHello Recall Note")

def test_command_file_clickable_link(client, mock_telegram_ack):
    # Tests clicking a /file_12 command link
    payload = make_telegram_update(2014, 12345, "/file_12")
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    assert response.json()["detail"] == "file_processed"
    mock_telegram_ack.assert_called_once_with("12345", "📝 Saved Note:\nHello Recall Note")
