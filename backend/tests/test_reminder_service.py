import pytest
from datetime import datetime, timedelta, timezone, date, time
from backend.services.reminder_service import parse_time_expression, create_reminder
from unittest import mock

@pytest.fixture(autouse=True)
def mock_redis_service():
    with mock.patch("backend.services.reminder_service.redis", new_callable=mock.AsyncMock) as m:
        yield m

class MockDbState:
    def __init__(self, active_count=0):
        self.active_count = active_count
        self.inserted_row = None

class MockCursor:
    def __init__(self, state):
        self.state = state

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def execute(self, query, params=None):
        query_upper = query.upper()
        if "INSERT INTO REMINDERS" in query_upper:
            # params = (user_id, message, remind_at)
            self.state.inserted_row = (100, params[0], None, params[1], params[2], "pending", datetime.now(timezone.utc))

    async def fetchone(self):
        if self.state.inserted_row:
            val = (self.state.inserted_row[0],)
            return val
        return (self.state.active_count,)

class MockConnection:
    def __init__(self, state):
        self.state = state
        self._cursor = MockCursor(state)

    def cursor(self):
        return self._cursor

    async def commit(self):
        pass

def test_parse_time_expression_relative_minutes():
    # Xm format
    delta, abs_fmt, msg = parse_time_expression("30m Review ML notes")
    assert delta == timedelta(minutes=30)
    assert abs_fmt is None
    assert msg == "Review ML notes"

    # Xmin format
    delta, abs_fmt, msg = parse_time_expression("45min Read article")
    assert delta == timedelta(minutes=45)
    assert abs_fmt is None
    assert msg == "Read article"

def test_parse_time_expression_relative_hours():
    # Xh format
    delta, abs_fmt, msg = parse_time_expression("2h Check logs")
    assert delta == timedelta(hours=2)
    assert abs_fmt is None
    assert msg == "Check logs"

    # Xhr format
    delta, abs_fmt, msg = parse_time_expression("4hr Run training")
    assert delta == timedelta(hours=4)
    assert abs_fmt is None
    assert msg == "Run training"

def test_parse_time_expression_relative_days():
    # Xd format
    delta, abs_fmt, msg = parse_time_expression("3d Revisit bookmark")
    assert delta == timedelta(days=3)
    assert abs_fmt is None
    assert msg == "Revisit bookmark"

    # Xday format
    delta, abs_fmt, msg = parse_time_expression("5day Follow up client")
    assert delta == timedelta(days=5)
    assert abs_fmt is None
    assert msg == "Follow up client"

def test_parse_time_expression_absolute_tomorrow():
    # "tomorrow"
    delta, abs_fmt, msg = parse_time_expression("tomorrow call boss")
    assert delta is None
    assert abs_fmt == "tomorrow"
    assert msg == "call boss"

    # "tomorrow morning"
    delta, abs_fmt, msg = parse_time_expression("tomorrow morning call boss")
    assert delta is None
    assert abs_fmt == "tomorrow_morning"
    assert msg == "call boss"

    # "tomorrow evening"
    delta, abs_fmt, msg = parse_time_expression("tomorrow evening call boss")
    assert delta is None
    assert abs_fmt == "tomorrow_evening"
    assert msg == "call boss"

def test_parse_time_expression_absolute_next_week():
    # "next week"
    delta, abs_fmt, msg = parse_time_expression("next week check research paper")
    assert delta is None
    assert abs_fmt == "next_week"
    assert msg == "check research paper"

def test_parse_time_expression_invalid():
    # Invalid time syntax
    delta, abs_fmt, msg = parse_time_expression("invalid_time Check paper")
    assert delta is None
    assert abs_fmt is None
    assert msg == ""

@pytest.mark.asyncio
async def test_create_reminder_happy_path():
    state = MockDbState(active_count=5)
    conn = MockConnection(state)
    target_time = datetime.now(timezone.utc) + timedelta(hours=2)
    
    r_id, msg, truncated = await create_reminder(42, "Check backend logs", target_time, conn)
    assert r_id == 100
    assert msg == "Check backend logs"
    assert truncated is False

@pytest.mark.asyncio
async def test_create_reminder_truncation():
    state = MockDbState(active_count=5)
    conn = MockConnection(state)
    target_time = datetime.now(timezone.utc) + timedelta(hours=2)
    
    # Message longer than 500 characters
    long_msg = "A" * 600
    r_id, msg, truncated = await create_reminder(42, long_msg, target_time, conn)
    assert r_id == 100
    assert len(msg) == 500
    assert truncated is True

@pytest.mark.asyncio
async def test_create_reminder_limit_exceeded():
    # User already has 20 active reminders
    state = MockDbState(active_count=20)
    conn = MockConnection(state)
    target_time = datetime.now(timezone.utc) + timedelta(hours=2)
    
    with pytest.raises(ValueError, match="limit of 20 active reminders"):
        await create_reminder(42, "Check logs", target_time, conn)
