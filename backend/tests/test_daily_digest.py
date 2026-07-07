import pytest
import unittest.mock as mock
import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.scheduler.scheduler import (
    start_scheduler,
    stop_scheduler,
    daily_digest_sender
)
import backend.scheduler.scheduler as scheduler_module

class MockCursor:
    def __init__(self, select_users_data=None, count_items_data=None, titles_data=None, count_quizzes_data=None):
        self.executed = []
        self.select_users_data = select_users_data or []
        self.count_items_data = count_items_data or [(0,)]
        self.titles_data = titles_data or []
        self.count_quizzes_data = count_quizzes_data or [(0,)]
        
        self._select_idx = 0
        self._count_items_idx = 0
        self._titles_idx = 0
        self._count_quizzes_idx = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def execute(self, query, params=None):
        self.executed.append((query, params))

    async def fetchall(self):
        query_norm = " ".join(self.executed[-1][0].upper().split())
        if "SELECT ID, TELEGRAM_CHAT_ID" in query_norm:
            return self.select_users_data
        elif "SELECT TITLE" in query_norm:
            return self.titles_data
        return []

    async def fetchone(self):
        query_norm = " ".join(self.executed[-1][0].upper().split())
        if "SELECT COUNT(*) FROM ITEMS" in query_norm:
            return self.count_items_data
        elif "SELECT COUNT(*) FROM QUIZZES" in query_norm:
            return self.count_quizzes_data
        return None

class MockConnection:
    def __init__(self, cursor_inst):
        self.cursor_inst = cursor_inst

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def cursor(self):
        return self.cursor_inst

    async def commit(self):
        pass

    async def execute(self, query, params=None):
        pass

class MockPool:
    def __init__(self, connection_inst):
        self.connection_inst = connection_inst

    def connection(self):
        return self.connection_inst

@pytest.mark.asyncio
async def test_digest_scheduler_registration():
    """Verify that starting the scheduler registers daily_digest_sender with misfire_grace_time=60."""
    try:
        await start_scheduler()
        assert scheduler_module._scheduler is not None
        
        job = scheduler_module._scheduler.get_job("daily_digest_sender")
        assert job is not None
        assert job.misfire_grace_time == 60
        
        # Verify CronTrigger runs hourly
        assert isinstance(job.trigger, CronTrigger)
    finally:
        await stop_scheduler()

@pytest.mark.asyncio
@mock.patch("backend.scheduler.scheduler.send_telegram_message")
async def test_daily_digest_sender_with_items(mock_send):
    """Verify daily_digest_sender formatting and execution when yesterday had saved items."""
    mock_send.return_value = True
    
    # 1 User, saved 2 items yesterday, 1 quiz due today, 5 day streak
    users_data = [(42, "chat_12345", 5)]
    items_count = (2,)
    titles_data = [("Item One",), ("Item Two",)]
    quiz_count = (1,)
    
    cursor = MockCursor(
        select_users_data=users_data,
        count_items_data=items_count,
        titles_data=titles_data,
        count_quizzes_data=quiz_count
    )
    conn = MockConnection(cursor)
    pool = MockPool(conn)
    
    with mock.patch("backend.scheduler.scheduler.get_pool", return_value=pool):
        await daily_digest_sender()
        
    assert mock_send.call_count == 1
    call_args = mock_send.call_args[0]
    assert call_args[0] == "chat_12345"
    
    message = call_args[1]
    assert "📬 Good morning! Your Recall daily digest:" in message
    assert "Yesterday you saved 2 items." in message
    assert "📖 New knowledge:" in message
    assert "• Item One" in message
    assert "• Item Two" in message
    assert "🧠 Quizzes due today: 1" in message
    assert "🔥 5 day streak" in message

@pytest.mark.asyncio
@mock.patch("backend.scheduler.scheduler.send_telegram_message")
async def test_daily_digest_sender_zero_items(mock_send):
    """Verify daily_digest_sender omits the saved items section when N=0."""
    mock_send.return_value = True
    
    # 1 User, saved 0 items yesterday, 3 quizzes due today, 10 day streak
    users_data = [(99, "chat_9999", 10)]
    items_count = (0,)
    titles_data = []
    quiz_count = (3,)
    
    cursor = MockCursor(
        select_users_data=users_data,
        count_items_data=items_count,
        titles_data=titles_data,
        count_quizzes_data=quiz_count
    )
    conn = MockConnection(cursor)
    pool = MockPool(conn)
    
    with mock.patch("backend.scheduler.scheduler.get_pool", return_value=pool):
        await daily_digest_sender()
        
    assert mock_send.call_count == 1
    call_args = mock_send.call_args[0]
    
    message = call_args[1]
    assert "📬 Good morning! Your Recall daily digest:" in message
    assert "Yesterday you saved" not in message
    assert "📖 New knowledge:" not in message
    assert "🧠 Quizzes due today: 3" in message
    assert "🔥 10 day streak" in message

@pytest.mark.asyncio
@mock.patch("backend.scheduler.scheduler.send_telegram_message")
async def test_daily_digest_delivery_isolation(mock_send):
    """Verify that a failure in one user's Telegram delivery does not affect others."""
    # User 1: message fails to send; User 2: succeeds
    mock_send.side_effect = [Exception("API timeout"), True]
    
    # 2 Users
    users_data = [(101, "chat_failed", 2), (102, "chat_success", 3)]
    items_count = (0,)
    titles_data = []
    quiz_count = (0,)
    
    cursor = MockCursor(
        select_users_data=users_data,
        count_items_data=items_count,
        titles_data=titles_data,
        count_quizzes_data=quiz_count
    )
    conn = MockConnection(cursor)
    pool = MockPool(conn)
    
    with mock.patch("backend.scheduler.scheduler.get_pool", return_value=pool):
        await daily_digest_sender()
        
    # Check that mock_send was called twice (delivery isolation succeeded)
    assert mock_send.call_count == 2
    assert mock_send.call_args_list[0][0][0] == "chat_failed"
    assert mock_send.call_args_list[1][0][0] == "chat_success"


@pytest.mark.asyncio
@mock.patch("backend.scheduler.scheduler.send_telegram_message")
@mock.patch("backend.scheduler.scheduler.redis")
async def test_daily_digest_near_miss_alert(mock_redis, mock_send):
    """Verify daily_digest_sender fires near-miss alerts for Hour 11."""
    mock_send.return_value = True
    mock_redis.get = mock.AsyncMock(return_value=None)
    mock_redis.setex = mock.AsyncMock()

    # User, chat, streak, local_hour
    users_data = [(200, "chat_near_miss", 3, 11)]
    
    class CustomMockCursor(MockCursor):
        async def fetchall(self):
            query_norm = " ".join(self.executed[-1][0].upper().split())
            if "SELECT ID, TELEGRAM_CHAT_ID" in query_norm:
                return users_data
            return []
            
        async def fetchone(self):
            query_norm = " ".join(self.executed[-1][0].upper().split())
            if "SELECT C.ID, C.ITEM_ID_A" in query_norm:
                import datetime
                return (123, 1, 2, 0.82, "First Save", datetime.datetime.now() - datetime.timedelta(days=5), "Second Save", datetime.datetime.now())
            if "SELECT LABEL FROM SEMANTIC_HUBS" in query_norm:
                return ("Machine Learning",)
            return None

    conn = MockConnection(CustomMockCursor())
    pool = MockPool(conn)

    with mock.patch("backend.scheduler.scheduler.get_pool", return_value=pool):
        await daily_digest_sender()

    assert mock_send.call_count == 1
    call_args = mock_send.call_args[0]
    assert call_args[0] == "chat_near_miss"
    assert "Your graph almost made a connection" in call_args[1]
    assert "Machine Learning" in call_args[1]
    mock_redis.setex.assert_called_with("user:near_miss_sent_cooldown:200", 3 * 86400, "1")


@pytest.mark.asyncio
@mock.patch("backend.scheduler.scheduler.send_telegram_message")
@mock.patch("backend.scheduler.scheduler.redis")
async def test_daily_digest_cooling_hub_warning(mock_redis, mock_send):
    """Verify daily_digest_sender fires cooling hub warnings for Hour 16."""
    mock_send.return_value = True
    mock_redis.get = mock.AsyncMock(return_value=None)
    mock_redis.setex = mock.AsyncMock()

    # User, chat, streak, local_hour
    users_data = [(300, "chat_cooling", 5, 16)]
    
    class CustomMockCursor(MockCursor):
        async def fetchall(self):
            query_norm = " ".join(self.executed[-1][0].upper().split())
            if "SELECT ID, TELEGRAM_CHAT_ID" in query_norm:
                return users_data
            return []
            
        async def fetchone(self):
            query_norm = " ".join(self.executed[-1][0].upper().split())
            if "SELECT COUNT(*) FROM SEMANTIC_HUBS" in query_norm:
                return (3,)
            return None

    conn = MockConnection(CustomMockCursor())
    pool = MockPool(conn)

    with mock.patch("backend.scheduler.scheduler.get_pool", return_value=pool):
        await daily_digest_sender()

    assert mock_send.call_count == 1
    call_args = mock_send.call_args[0]
    assert call_args[0] == "chat_cooling"
    assert "Your living graph is cooling down" in call_args[1]
    mock_redis.setex.assert_called_with("user:cooling_sent_cooldown:300", 10 * 86400, "1")
