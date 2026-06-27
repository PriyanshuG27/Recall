import pytest
import unittest.mock as mock
import datetime
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.scheduler.scheduler import (
    start_scheduler,
    stop_scheduler,
    reminders_dispatcher,
    partition_creator,
    drive_nudge_sender,
    processed_updates_cleanup,
    louvain_clustering
)
import backend.scheduler.scheduler as scheduler_module


class MockCursor:
    def __init__(self, fetchall_data=None, fetchone_data=None):
        self.executed = []
        self.fetchall_data = fetchall_data or []
        self.fetchone_data = fetchone_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def execute(self, query, params=None):
        self.executed.append((query, params))

    async def fetchall(self):
        return self.fetchall_data

    async def fetchone(self):
        return self.fetchone_data


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

    async def rollback(self):
        pass


@pytest.mark.asyncio
async def test_scheduler_jobs_registration():
    """Verify that starting the scheduler registers all 5 jobs with misfire_grace_time=60."""
    try:
        await start_scheduler()
        
        # scheduler_module._scheduler should be initialized
        assert scheduler_module._scheduler is not None
        assert isinstance(scheduler_module._scheduler, AsyncIOScheduler)
        
        jobs = scheduler_module._scheduler.get_jobs()
        job_ids = [job.id for job in jobs]
        
        # Verify all 5 jobs exist
        expected_jobs = [
            "reminders_dispatcher",
            "louvain_clustering",
            "partition_creator",
            "drive_nudge_sender",
            "processed_updates_cleanup"
        ]
        for ej in expected_jobs:
            assert ej in job_ids
            job = scheduler_module._scheduler.get_job(ej)
            assert job.misfire_grace_time == 60
    finally:
        await stop_scheduler()


@pytest.mark.asyncio
async def test_reminders_dispatcher_success():
    """Verify reminders_dispatcher pulls pending reminders, sends Telegram message, and marks as sent."""
    # Setup mock reminder row: (reminder_id, message, telegram_chat_id)
    cursor = MockCursor(fetchall_data=[(101, "Test Message", "999888")])
    conn = MockConnection(cursor)
    mock_pool = mock.MagicMock()
    mock_pool.connection = mock.MagicMock(return_value=conn)
    
    mock_redis = mock.AsyncMock()
    mock_redis.zrangebyscore.return_value = ["101"]
    mock_redis.zrem.return_value = 1
    
    with mock.patch("backend.scheduler.scheduler._pool", mock_pool), \
         mock.patch("backend.scheduler.scheduler.redis", mock_redis), \
         mock.patch("backend.scheduler.scheduler.send_telegram_message", new_callable=mock.AsyncMock) as mock_send:
        
        mock_send.return_value = True
        
        await reminders_dispatcher()
        
        # Verify Telegram send was called
        mock_send.assert_called_once_with("999888", "🔔 Reminder:\n\nTest Message")
        
        # Verify SELECT and UPDATE query execution
        assert len(cursor.executed) == 2
        
        select_query = cursor.executed[0][0]
        assert "select" in select_query.lower()
        assert "reminders" in select_query.lower()
        assert "pending" in select_query.lower()
        
        update_query, params = cursor.executed[1]
        assert "update" in update_query.lower()
        assert "reminders" in update_query.lower()
        assert "status" in update_query.lower()
        assert params == ("sent", 101)
        
        mock_redis.zrangebyscore.assert_called_once()
        mock_redis.zrem.assert_called_once_with("reminders:active", "101")


@pytest.mark.asyncio
async def test_reminders_dispatcher_failure():
    """Verify reminders_dispatcher updates status to 'failed' if Telegram API call fails."""
    cursor = MockCursor(fetchall_data=[(202, "Failed Alert", "111222")])
    conn = MockConnection(cursor)
    mock_pool = mock.MagicMock()
    mock_pool.connection = mock.MagicMock(return_value=conn)
    
    mock_redis = mock.AsyncMock()
    mock_redis.zrangebyscore.return_value = ["202"]
    mock_redis.zrem.return_value = 1
    
    with mock.patch("backend.scheduler.scheduler._pool", mock_pool), \
         mock.patch("backend.scheduler.scheduler.redis", mock_redis), \
         mock.patch("backend.scheduler.scheduler.send_telegram_message", new_callable=mock.AsyncMock) as mock_send:
        
        mock_send.return_value = False  # Simulate Telegram failure
        
        await reminders_dispatcher()
        
        # Verify Telegram send called
        mock_send.assert_called_once_with("111222", "🔔 Reminder:\n\nFailed Alert")
        
        # Verify status is marked as 'failed' in database
        assert len(cursor.executed) == 2
        update_query, params = cursor.executed[1]
        assert params == ("failed", 202)
        
        mock_redis.zrangebyscore.assert_called_once()
        mock_redis.zrem.assert_called_once_with("reminders:active", "202")


@pytest.mark.asyncio
async def test_partition_creator_success():
    """Verify partition_creator executes the DDL query safely and idempotently."""
    cursor = MockCursor()
    conn = MockConnection(cursor)
    mock_pool = mock.MagicMock()
    mock_pool.connection = mock.MagicMock(return_value=conn)
    
    # Lock the date to a specific month to predict bounds
    test_date = datetime.date(2026, 6, 25)
    
    with mock.patch("backend.scheduler.scheduler._pool", mock_pool), \
         mock.patch("datetime.date") as mock_date:
        
        mock_date.today.return_value = test_date
        
        await partition_creator()
        
        # In June 2026, it should create a partition for July 2026 (y2026m07)
        # Bounds: start 2026-07-01 to end 2026-08-01
        assert len(cursor.executed) == 1
        query = cursor.executed[0][0]
        
        assert "create table if not exists items_y2026m07" in query.lower()
        assert "partition of items" in query.lower()
        assert "'2026-07-01 00:00:00'" in query
        assert "'2026-08-01 00:00:00'" in query


@pytest.mark.asyncio
async def test_partition_creator_failure_logs_critical():
    """Verify that an exception in partition_creator gets logged with CRITICAL severity."""
    mock_pool = mock.MagicMock()
    # Simulate DB pool lookup error
    mock_pool.connection.side_effect = Exception("Neon connection pool timeout")
    
    with mock.patch("backend.scheduler.scheduler._pool", mock_pool), \
         mock.patch("backend.scheduler.scheduler.logger.critical") as mock_log_crit:
        
        await partition_creator()
        
        # Should catch exception and log at CRITICAL level
        mock_log_crit.assert_called_once()
        log_msg = mock_log_crit.call_args[0][0]
        assert "partition creation failed" in log_msg.lower()


@pytest.mark.asyncio
async def test_drive_nudge_sender_success():
    """Verify drive_nudge_sender sends nudges to qualifying users and updates drive_nudge_sent flag."""
    # Mock user row: (user_id, telegram_chat_id, streak_count)
    cursor = MockCursor(fetchall_data=[(10, "chat_john", 4)])
    conn = MockConnection(cursor)
    mock_pool = mock.MagicMock()
    mock_pool.connection = mock.MagicMock(return_value=conn)
    
    with mock.patch("backend.scheduler.scheduler._pool", mock_pool), \
         mock.patch("backend.scheduler.scheduler.send_telegram_message", new_callable=mock.AsyncMock) as mock_send:
        
        mock_send.return_value = True
        
        await drive_nudge_sender()
        
        mock_send.assert_called_once()
        assert "chat_john" in mock_send.call_args[0][0]
        assert "streak" in mock_send.call_args[0][1].lower()
        
        # Check database update query
        update_queries = [x for x in cursor.executed if "update" in x[0].lower()]
        assert len(update_queries) == 1
        assert "drive_nudge_sent = true" in update_queries[0][0].lower()
        assert update_queries[0][1] == (10,)


@pytest.mark.asyncio
async def test_drive_nudge_sender_skipped_on_send_failure():
    """Verify drive_nudge_sender does NOT update drive_nudge_sent if Telegram fails."""
    cursor = MockCursor(fetchall_data=[(10, "chat_john", 4)])
    conn = MockConnection(cursor)
    mock_pool = mock.MagicMock()
    mock_pool.connection = mock.MagicMock(return_value=conn)
    
    with mock.patch("backend.scheduler.scheduler._pool", mock_pool), \
         mock.patch("backend.scheduler.scheduler.send_telegram_message", new_callable=mock.AsyncMock) as mock_send:
        
        mock_send.return_value = False  # Simulate send failure
        
        await drive_nudge_sender()
        
        mock_send.assert_called_once()
        
        # Update queries list should be empty
        update_queries = [x for x in cursor.executed if "update" in x[0].lower()]
        assert len(update_queries) == 0


@pytest.mark.asyncio
async def test_processed_updates_cleanup():
    """Verify processed_updates_cleanup triggers the DELETE statement."""
    cursor = MockCursor()
    conn = MockConnection(cursor)
    mock_pool = mock.MagicMock()
    mock_pool.connection = mock.MagicMock(return_value=conn)
    
    with mock.patch("backend.scheduler.scheduler._pool", mock_pool):
        await processed_updates_cleanup()
        
        assert len(cursor.executed) == 1
        query = cursor.executed[0][0]
        assert "delete from processed_updates" in query.lower()
        assert "30 days" in query.lower()


@pytest.mark.asyncio
async def test_scheduler_resilience_on_exception():
    """Verify that when one job throws an exception, it does not stop the scheduler execution."""
    mock_pool = mock.MagicMock()
    # Force connection error to throw an exception
    mock_pool.connection.side_effect = Exception("DB Connection Refused")
    
    mock_redis = mock.AsyncMock()
    mock_redis.zrangebyscore.return_value = []
    
    with mock.patch("backend.scheduler.scheduler._pool", mock_pool), \
         mock.patch("backend.scheduler.scheduler.redis", mock_redis):
        # Triggering a job with a forced exception should be caught and logged
        # and NOT bubble up/crash the thread
        await processed_updates_cleanup()
        await reminders_dispatcher()
        await drive_nudge_sender()
        
        # Test complete - verified that no exception was raised out of the methods
