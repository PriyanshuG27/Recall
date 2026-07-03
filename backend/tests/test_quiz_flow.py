import time
import pytest
import json
from datetime import datetime, timezone, timedelta, date
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

class QuizTestDbState:
    def __init__(self):
        self.processed = set()
        self.users = {"12345": 1, "67890": 2}
        self.streak_counts = {1: 5, 2: 0}
        self.quizzes = [
            {
                "id": 100,
                "user_id": 1,
                "question": "What is the complexity of HNSW search?",
                "options": json.dumps(["O(1)", "O(log N)", "O(N)", "O(N log N)"]),
                "correct_index": 1,
                "explanation": "HNSW search has logarithmic complexity O(log N).",
                "ease_factor": 2.5,
                "interval_days": 1,
                "next_review": date.today()
            },
            {
                "id": 101,
                "user_id": 1,
                "question": "Which index is used for GIN trigram?",
                "options": json.dumps(["B-tree", "GIN", "HNSW", "Hash"]),
                "correct_index": 1,
                "explanation": "GIN index is used with pg_trgm for GIN trigram search.",
                "ease_factor": 2.5,
                "interval_days": 1,
                "next_review": date.today()
            }
        ]

class QuizMockCursor:
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
            
        elif "FROM QUIZZES" in query_upper and "QUESTION" in query_upper and "SELECT ID," in query_upper:
            u_id = params[0]
            user_quizzes = [q for q in self.state.quizzes if q["user_id"] == u_id and q["next_review"] <= date.today()]
            user_quizzes.sort(key=lambda x: x["next_review"])
            if user_quizzes:
                quiz = user_quizzes[0]
                self._rows = [(
                    quiz["id"],
                    quiz["question"],
                    quiz["options"],
                    quiz["correct_index"],
                    quiz["explanation"]
                )]
                
        elif "FROM QUIZZES" in query_upper and "EASE_FACTOR" in query_upper:
            quiz_id = params[0]
            if len(params) > 1:
                u_id = params[1]
                found = [q for q in self.state.quizzes if q["id"] == quiz_id and q["user_id"] == u_id]
            else:
                found = [q for q in self.state.quizzes if q["id"] == quiz_id]
                
            if found:
                quiz = found[0]
                self._rows = [(
                    quiz.get("user_id"),
                    quiz["ease_factor"],
                    quiz["interval_days"],
                    quiz["correct_index"],
                    quiz["explanation"],
                    quiz["question"],
                    quiz["options"],
                    quiz["next_review"]
                )]
                
        elif "UPDATE QUIZZES" in query_upper:
            if len(params) == 5:
                ef, interval, next_rev, q_id, u_id = params
                for q in self.state.quizzes:
                    if q["id"] == q_id and q["user_id"] == u_id:
                        q["ease_factor"] = ef
                        q["interval_days"] = interval
                        q["next_review"] = next_rev
            else:
                ef, interval, next_rev, q_id = params
                for q in self.state.quizzes:
                    if q["id"] == q_id:
                        q["ease_factor"] = ef
                        q["interval_days"] = interval
                        q["next_review"] = next_rev
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

class QuizMockConnection:
    def __init__(self, state):
        self.state = state
        self._cursor = QuizMockCursor(state)
        
    def cursor(self):
        return self._cursor
        
    async def commit(self):
        pass

@pytest.fixture()
def db_state():
    return QuizTestDbState()

@pytest.fixture(autouse=True)
def override_db(patch_env, db_state):
    from backend.db.connection import get_db
    
    async def _mock_get_db():
        yield QuizMockConnection(db_state)
        
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

def make_telegram_callback_update(update_id: int, chat_id: int, data: str, message_id: int = 999) -> dict:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cb_{update_id}",
            "from": {"id": chat_id},
            "message": {
                "message_id": message_id,
                "chat": {"id": chat_id},
                "text": "What is the complexity of HNSW search?"
            },
            "data": data
        }
    }

def test_quiz_command_success(client, db_state):
    # Tests that /quiz command outputs bold question and 2x2 keyboard layout
    with mock.patch("backend.routes.webhook.http_client.post", new_callable=mock.AsyncMock) as mock_post:
        payload = make_telegram_update(3001, 12345, "/quiz")
        response = client.post("/webhook", json=payload)
        
        assert response.status_code == 200
        assert response.json()["detail"] == "quiz_processed"
        
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        json_payload = kwargs["json"]
        
        assert json_payload["chat_id"] == "12345"
        assert json_payload["text"] == "<b>What is the complexity of HNSW search?</b>"
        assert json_payload["parse_mode"] == "HTML"
        assert "inline_keyboard" in json_payload["reply_markup"]
        
        ikb = json_payload["reply_markup"]["inline_keyboard"]
        assert len(ikb) == 4  # 4x1 vertical layout
        assert len(ikb[0]) == 1
        assert len(ikb[1]) == 1
        assert len(ikb[2]) == 1
        assert len(ikb[3]) == 1
        
        # Verify text prefixes and callback format
        assert ikb[0][0]["text"] == "A. O(1)"
        assert ikb[0][0]["callback_data"] == "quiz:100:0"
        assert ikb[1][0]["text"] == "B. O(log N)"
        assert ikb[1][0]["callback_data"] == "quiz:100:1"
        assert ikb[2][0]["text"] == "C. O(N)"
        assert ikb[2][0]["callback_data"] == "quiz:100:2"
        assert ikb[3][0]["text"] == "D. O(N log N)"
        assert ikb[3][0]["callback_data"] == "quiz:100:3"

def test_quiz_command_empty(client, db_state, mock_telegram_ack):
    # Clear due quizzes
    db_state.quizzes = []
    
    payload = make_telegram_update(3002, 12345, "/quiz")
    response = client.post("/webhook", json=payload)
    
    assert response.status_code == 200
    assert response.json()["detail"] == "quiz_processed"
    mock_telegram_ack.assert_called_once_with("12345", "🎉 No quizzes due! Come back tomorrow.")

def test_callback_quiz_correct_answer(client, db_state):
    # Index 1 is the correct answer ("O(log N)") for quiz 100
    callback_payload = make_telegram_callback_update(3003, 12345, "quiz:100:1")
    
    with mock.patch("backend.routes.webhook.http_client.post", new_callable=mock.AsyncMock) as mock_post:
        response = client.post("/webhook", json=callback_payload)
        
        assert response.status_code == 200
        assert response.json()["detail"] == "callback_query_processed"
        
        # Verify database update (SM-2: quality=5)
        # ease_factor: 2.5 -> 2.6, interval: 1 -> round_half_up(1 * 2.5) = 3
        updated_quiz = db_state.quizzes[0]
        assert updated_quiz["ease_factor"] == 2.6
        assert updated_quiz["interval_days"] == 3
        assert updated_quiz["next_review"] == date.today() + timedelta(days=3)
        
        # 2 HTTP post calls: 1 to answerCallbackQuery, 1 to editMessageText
        assert mock_post.call_count == 2
        
        # Find edit call payload
        edit_call = [call for call in mock_post.call_args_list if "editMessageText" in call[0][0]]
        assert len(edit_call) == 1
        _, edit_kwargs = edit_call[0]
        json_payload = edit_kwargs["json"]
        
        assert "✅ Correct!" in json_payload["text"]
        assert "HNSW search has logarithmic complexity O(log N)" in json_payload["text"]
        assert f"Next review: {(date.today() + timedelta(days=3)).strftime('%Y-%m-%d')}" in json_payload["text"]
        
        # Verify Next button
        next_button = json_payload["reply_markup"]["inline_keyboard"]
        assert len(next_button) == 1
        assert next_button[0][0]["text"] == "Next Quiz →"
        assert next_button[0][0]["callback_data"] == "quiz:next"

def test_callback_quiz_incorrect_answer(client, db_state):
    # Index 0 is incorrect ("O(1)") for quiz 100
    callback_payload = make_telegram_callback_update(3004, 12345, "quiz:100:0")
    
    with mock.patch("backend.routes.webhook.http_client.post", new_callable=mock.AsyncMock) as mock_post:
        response = client.post("/webhook", json=callback_payload)
        
        assert response.status_code == 200
        assert response.json()["detail"] == "callback_query_processed"
        
        # Verify database update (SM-2: quality=2)
        # ease_factor: max(1.3, 2.5 - 0.8) = 1.7, interval = 1
        updated_quiz = db_state.quizzes[0]
        assert updated_quiz["ease_factor"] == 1.7
        assert updated_quiz["interval_days"] == 1
        assert updated_quiz["next_review"] == date.today() + timedelta(days=1)
        
        # Find edit call payload
        edit_call = [call for call in mock_post.call_args_list if "editMessageText" in call[0][0]]
        assert len(edit_call) == 1
        _, edit_kwargs = edit_call[0]
        json_payload = edit_kwargs["json"]
        
        assert "❌ The answer was O(log N)" in json_payload["text"]
        assert "HNSW search has logarithmic complexity O(log N)" in json_payload["text"]
        assert "Review again in 1 day." in json_payload["text"]

def test_callback_quiz_ownership_validation(client, db_state):
    # chat_id 67890 maps to user_id 2 in db_state, but quiz 100 belongs to user_id 1
    callback_payload = make_telegram_callback_update(3005, 67890, "quiz:100:1")
    
    with mock.patch("backend.routes.webhook.http_client.post", new_callable=mock.AsyncMock) as mock_post:
        response = client.post("/webhook", json=callback_payload)
        
        assert response.status_code == 200
        assert response.json()["detail"] == "quiz_ownership_rejected"
        
        # DB should not be updated
        assert db_state.quizzes[0]["ease_factor"] == 2.5
        
        # Only 1 HTTP call to answerCallbackQuery (with rejected ownership message)
        assert mock_post.call_count == 1
        _, kwargs = mock_post.call_args
        assert "This quiz does not belong to you" in kwargs["json"]["text"]

def test_callback_quiz_stale_click(client, db_state):
    # Pre-mark quiz 100 as answered (next_review in future)
    db_state.quizzes[0]["next_review"] = date.today() + timedelta(days=3)
    db_state.quizzes[0]["ease_factor"] = 2.6
    db_state.quizzes[0]["interval_days"] = 3
    
    callback_payload = make_telegram_callback_update(3006, 12345, "quiz:100:1")
    
    with mock.patch("backend.routes.webhook.http_client.post", new_callable=mock.AsyncMock) as mock_post:
        response = client.post("/webhook", json=callback_payload)
        
        assert response.status_code == 200
        assert response.json()["detail"] == "stale_callback_ignored"
        
        # No DB change or editMessageText triggers
        assert db_state.quizzes[0]["ease_factor"] == 2.6
        assert mock_post.call_count == 1  # Only 1 call to answerCallbackQuery to clean spinner

def test_callback_quiz_non_existent(client, db_state):
    # Quiz ID 999 does not exist
    callback_payload = make_telegram_callback_update(3007, 12345, "quiz:999:1")
    
    with mock.patch("backend.routes.webhook.http_client.post", new_callable=mock.AsyncMock) as mock_post:
        response = client.post("/webhook", json=callback_payload)
        
        assert response.status_code == 200
        assert response.json()["detail"] == "quiz_not_found"
        assert mock_post.call_count == 1  # Only answers callback query to prevent hang

def test_callback_quiz_next_available(client, db_state):
    # Marks quiz 100 as reviewed so quiz 101 becomes the next oldest due
    db_state.quizzes[0]["next_review"] = date.today() + timedelta(days=3)
    
    callback_payload = make_telegram_callback_update(3008, 12345, "quiz:next")
    
    with mock.patch("backend.routes.webhook.http_client.post", new_callable=mock.AsyncMock) as mock_post:
        response = client.post("/webhook", json=callback_payload)
        
        assert response.status_code == 200
        assert response.json()["detail"] == "callback_query_processed"
        
        # Edit message called to load quiz 101
        edit_call = [call for call in mock_post.call_args_list if "editMessageText" in call[0][0]]
        assert len(edit_call) == 1
        _, edit_kwargs = edit_call[0]
        json_payload = edit_kwargs["json"]
        
        assert json_payload["text"] == "<b>Which index is used for GIN trigram?</b>"
        ikb = json_payload["reply_markup"]["inline_keyboard"]
        assert len(ikb) == 4
        assert ikb[0][0]["text"] == "A. B-tree"
        assert ikb[0][0]["callback_data"] == "quiz:101:0"

def test_callback_quiz_next_empty(client, db_state):
    # Mark all quizzes as done
    db_state.quizzes[0]["next_review"] = date.today() + timedelta(days=3)
    db_state.quizzes[1]["next_review"] = date.today() + timedelta(days=3)
    
    callback_payload = make_telegram_callback_update(3009, 12345, "quiz:next")
    
    with mock.patch("backend.routes.webhook.http_client.post", new_callable=mock.AsyncMock) as mock_post:
        response = client.post("/webhook", json=callback_payload)
        
        assert response.status_code == 200
        assert response.json()["detail"] == "callback_query_processed"
        
        edit_call = [call for call in mock_post.call_args_list if "editMessageText" in call[0][0]]
        assert len(edit_call) == 1
        _, edit_kwargs = edit_call[0]
        json_payload = edit_kwargs["json"]
        
        assert json_payload["text"] == "🎉 No quizzes due! Come back tomorrow."
        assert json_payload["reply_markup"]["inline_keyboard"] == []
