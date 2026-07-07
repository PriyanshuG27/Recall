import pytest
from unittest import mock
import json
from datetime import date, datetime, timezone, timedelta
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.ai_cascade import AICascade
from backend.routes.webhook import (
    process_quiz_me_callback,
    process_remind_me_callback,
    process_remind_set_callback
)
from backend.services.encryption import encrypt

class TelegramMockDbState:
    def __init__(self):
        self.processed = set()
        self.users = {"12345": 1, "54321": 2}
        self.streak_counts = {1: 5, 2: 0}
        self.items = []
        self.quizzes = []

class TelegramMockCursor:
    def __init__(self, state):
        self.state = state
        self._rows = []
        self._row_idx = 0
        self.rowcount = 0
        self._last_val = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def execute(self, query, params=None):
        query_upper = query.upper()
        self._rows = []
        self._row_idx = 0
        self.rowcount = 0
        self._last_val = None

        if "SELECT ID FROM USERS" in query_upper:
            chat_id = str(params[0])
            self._last_val = self.state.users.get(chat_id)

        elif "INSERT INTO USERS" in query_upper:
            chat_id = str(params[0])
            if chat_id not in self.state.users:
                user_id = len(self.state.users) + 1
                self.state.users[chat_id] = user_id
            self._last_val = self.state.users[chat_id]

        elif "SELECT" in query_upper and "QUIZZES" in query_upper:
            # Query format: SELECT id, question, options, correct_index, explanation FROM quizzes WHERE item_id = %s AND user_id = %s LIMIT 1;
            if "ITEM_ID =" in query_upper:
                item_id, user_id = params[0], params[1]
                found = [q for q in self.state.quizzes if q["item_id"] == item_id and q["user_id"] == user_id]
            else:
                user_id = params[0]
                found = [q for q in self.state.quizzes if q["user_id"] == user_id]
                
            if found:
                q = found[0]
                self._rows = [(q["id"], q["question"], q["options"], q["correct_index"], q["explanation"])]
                
        elif "SELECT" in query_upper and "ITEMS" in query_upper:
            # Query format: SELECT source_type, raw_text, summary, title FROM items WHERE id = %s AND user_id = %s;
            item_id, user_id = params[0], params[1]
            found = [item for item in self.state.items if item["id"] == item_id and item["user_id"] == user_id]
            if found:
                item = found[0]
                if "SOURCE_TYPE" in query_upper:
                    self._rows = [(item["source_type"], item.get("raw_text", ""), item.get("summary", ""), item["title"])]
                else:
                    self._rows = [(item["title"],)]

        elif "SELECT TIMEZONE_OFFSET" in query_upper:
            user_id = params[0]
            self._rows = [(0,)]

        elif "INSERT INTO PROCESSED_UPDATES" in query_upper:
            self.rowcount = 1

        elif "INSERT INTO QUIZZES" in query_upper:
            # INSERT INTO quizzes (user_id, item_id, question, options, correct_index, explanation) ...
            user_id, item_id, question, options, correct_index, explanation = params
            new_id = len(self.state.quizzes) + 1
            new_quiz = {
                "id": new_id,
                "user_id": user_id,
                "item_id": item_id,
                "question": question,
                "options": options,
                "correct_index": correct_index,
                "explanation": explanation
            }
            self.state.quizzes.append(new_quiz)
            self._rows = [(new_id, question, options, correct_index, explanation)]
            self.rowcount = 1

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

class TelegramMockConnection:
    def __init__(self, state):
        self.state = state
        self._cursor = TelegramMockCursor(state)

    def cursor(self):
        return self._cursor

    async def commit(self):
        pass

@pytest.fixture()
def db_state():
    return TelegramMockDbState()

@pytest.fixture(autouse=True)
def override_db(db_state):
    from backend.db.connection import get_db
    async def _mock_get_db():
        yield TelegramMockConnection(db_state)
    app.dependency_overrides[get_db] = _mock_get_db
    yield
    app.dependency_overrides.pop(get_db, None)

@pytest.fixture()
def mock_pool(db_state):
    class MockConnectionContextManager:
        def __init__(self, conn):
            self.conn = conn
        async def __aenter__(self):
            return self.conn
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_conn = TelegramMockConnection(db_state)
    with mock.patch("backend.db.connection._pool") as m:
        m.connection.return_value = MockConnectionContextManager(mock_conn)
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
# 1. AICascade.generate_quiz Tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_generate_quiz_mock_env():
    # In test environment, generate_quiz returns mock question
    cascade = AICascade()
    res = await cascade.generate_quiz("some text")
    assert res is not None
    assert res["question"] == "What is the primary language used in this project?"
    assert res["correct_index"] == 0

@pytest.mark.anyio
async def test_generate_quiz_real_llm_parse():
    cascade = AICascade()
    # Force real LLM logic (bypass mock check)
    cascade._force_production_llm = True
    
    mock_response = json.dumps({
        "question": "What is 2+2?",
        "options": ["3", "4", "5", "6"],
        "correct_index": 1,
        "explanation": "Simple math"
    })
    
    with mock.patch("backend.services.ai_cascade.executor.retry.RetryEngine.execute_with_retry", new_callable=mock.AsyncMock, return_value=mock_response), \
         mock.patch("backend.services.ai_cascade.settings") as mock_settings:
        mock_settings.COMPUTE_PROVIDER = "groq"
        mock_settings.GROQ_API_KEY = "dummy"
        mock_settings.ENV = "production"
        
        res = await cascade.generate_quiz("testing math content")
        assert res is not None
        assert res["question"] == "What is 2+2?"
        assert res["correct_index"] == 1
        assert res["options"] == ["3", "4", "5", "6"]

@pytest.mark.anyio
async def test_generate_quiz_invalid_json():
    cascade = AICascade()
    cascade._force_production_llm = True
    
    with mock.patch("backend.services.ai_cascade.executor.retry.RetryEngine.execute_with_retry", new_callable=mock.AsyncMock, return_value="Invalid JSON response"), \
         mock.patch("backend.services.ai_cascade.settings") as mock_settings:
        mock_settings.COMPUTE_PROVIDER = "groq"
        mock_settings.GROQ_API_KEY = "dummy"
        mock_settings.ENV = "production"
        
        res = await cascade.generate_quiz("testing content")
        assert res is None


# ---------------------------------------------------------------------------
# 2. Webhook Callback Routing Tests
# ---------------------------------------------------------------------------

def test_webhook_quiz_me_routing(client):
    payload = {
        "update_id": 9999,
        "callback_query": {
            "id": "cb_quiz_me",
            "from": {"id": 12345},
            "message": {
                "message_id": 555,
                "chat": {"id": 12345},
                "text": "Saved Item"
            },
            "data": "quiz_me:42"
        }
    }
    with mock.patch("backend.routes.webhook.process_quiz_me_callback") as mock_task:
        resp = client.post("/webhook", json=payload)
        assert resp.status_code == 200
        assert resp.json()["detail"] == "callback_query_processed"
        mock_task.assert_called_once()

def test_webhook_remind_me_routing(client):
    payload = {
        "update_id": 9999,
        "callback_query": {
            "id": "cb_remind_me",
            "from": {"id": 12345},
            "message": {
                "message_id": 555,
                "chat": {"id": 12345},
                "text": "Saved Item"
            },
            "data": "remind_me:42"
        }
    }
    with mock.patch("backend.routes.webhook.process_remind_me_callback") as mock_task:
        resp = client.post("/webhook", json=payload)
        assert resp.status_code == 200
        assert resp.json()["detail"] == "callback_query_processed"
        mock_task.assert_called_once()

def test_webhook_remind_set_routing(client):
    payload = {
        "update_id": 9999,
        "callback_query": {
            "id": "cb_remind_set",
            "from": {"id": 12345},
            "message": {
                "message_id": 555,
                "chat": {"id": 12345},
                "text": "Saved Item"
            },
            "data": "remind_set:42:1h"
        }
    }
    with mock.patch("backend.routes.webhook.process_remind_set_callback") as mock_task:
        resp = client.post("/webhook", json=payload)
        assert resp.status_code == 200
        assert resp.json()["detail"] == "callback_query_processed"
        mock_task.assert_called_once()


# ---------------------------------------------------------------------------
# 3. Background Task Handler Tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_process_quiz_me_callback_existing_quiz(mock_pool, db_state):
    # Pre-add quiz to mock state
    db_state.quizzes = [{
        "id": 88,
        "user_id": 1,
        "item_id": 42,
        "question": "What is 1+1?",
        "options": json.dumps(["1", "2", "3", "4"]),
        "correct_index": 1,
        "explanation": "Math"
    }]
    
    with mock.patch("backend.routes.webhook.http_client.post", new_callable=mock.AsyncMock) as mock_post:
        await process_quiz_me_callback("12345", 1, 42, "cb_1")
        # Should call answerCallbackQuery and sendMessage
        assert mock_post.call_count == 2
        
        # Verify sendMessage payload
        send_call = mock_post.call_args_list[1]
        payload = send_call.kwargs.get("json") or send_call[1].get("json")
        assert "What is 1+1?" in payload["text"]
        assert "quiz:88:0" in payload["reply_markup"]["inline_keyboard"][0][0]["callback_data"]

@pytest.mark.anyio
async def test_process_quiz_me_callback_generates_new_quiz(mock_pool, db_state):
    # Empty quizzes, but item exists
    db_state.items = [{
        "id": 42,
        "user_id": 1,
        "source_type": "text",
        "title": "Ingested note",
        "raw_text": encrypt("This is a note about cognitive systems."),
        "created_at": datetime.now(timezone.utc)
    }]
    db_state.quizzes = []
    
    with mock.patch("backend.routes.webhook.http_client.post", new_callable=mock.AsyncMock) as mock_post:
        await process_quiz_me_callback("12345", 1, 42, "cb_2")
        
        # Generates quiz (mock returns template), inserts it, and sends
        assert len(db_state.quizzes) == 1
        assert db_state.quizzes[0]["question"] == "What is the primary language used in this project?"
        assert mock_post.call_count == 2

@pytest.mark.anyio
async def test_process_remind_me_callback(mock_pool, db_state):
    with mock.patch("backend.routes.webhook.http_client.post", new_callable=mock.AsyncMock) as mock_post:
        await process_remind_me_callback("12345", 1, 42, "cb_3")
        assert mock_post.call_count == 2
        # Verify choices sendMessage payload
        send_call = mock_post.call_args_list[1]
        payload = send_call.kwargs.get("json") or send_call[1].get("json")
        assert "Select when you would like to be reminded" in payload["text"]
        assert "remind_set:42:1h" in payload["reply_markup"]["inline_keyboard"][0][0]["callback_data"]

@pytest.mark.anyio
async def test_process_remind_set_callback(mock_pool, db_state):
    db_state.items = [{
        "id": 42,
        "user_id": 1,
        "source_type": "text",
        "title": "ML Notes",
        "raw_text": encrypt("some content"),
        "created_at": datetime.now(timezone.utc)
    }]
    
    with mock.patch("backend.routes.webhook.http_client.post", new_callable=mock.AsyncMock) as mock_post, \
         mock.patch("backend.services.reminder_service.create_reminder", new_callable=mock.AsyncMock) as mock_create:
        mock_create.return_value = (99, "Review Item: ML Notes", False)
        
        await process_remind_set_callback(
            chat_id="12345",
            user_id=1,
            item_id=42,
            interval="1h",
            callback_query_id="cb_4",
            message_id=555
        )
        
        # Verify reminder creation call
        mock_create.assert_called_once()
        assert mock_create.call_args[0][0] == 1
        assert "Review Item: ML Notes" in mock_create.call_args[0][1]
        
        # Should call answerCallbackQuery and editMessageText
        assert mock_post.call_count == 2
        edit_call = mock_post.call_args_list[1]
        edit_payload = edit_call.kwargs.get("json") or edit_call[1].get("json")
        assert "Reminder set for item 'ML Notes'" in edit_payload["text"]
        assert edit_payload["reply_markup"] == {"inline_keyboard": []}
