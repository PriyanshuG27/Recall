import pytest
import unittest.mock as mock
import math
from backend.scheduler.scheduler import (
    spaced_repetition_nudge_dispatcher,
    weekly_mind_map_dispatcher,
    monthly_memory_rhythm_scanner
)
from backend.services.mind_map_service import generate_weekly_svg_mind_map

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
        # Dynamically support multi-query mock responses if fetchall_data is a list of lists
        if self.fetchall_data and isinstance(self.fetchall_data[0], list):
            res = self.fetchall_data.pop(0)
            return res
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

    async def execute(self, query, params=None):
        await self.cursor_inst.execute(query, params)

    async def commit(self):
        pass

@pytest.mark.asyncio
@mock.patch("backend.scheduler.scheduler.get_pool")
@mock.patch("backend.scheduler.scheduler.send_telegram_message")
@mock.patch("backend.services.redis_client.redis.get")
@mock.patch("backend.services.redis_client.redis.setex")
async def test_spaced_repetition_nudge_dispatcher(mock_setex, mock_get, mock_send, mock_get_pool):
    """Verify that spaced_repetition_nudge_dispatcher triggers nudges and sets Redis lockouts."""
    # 1. Setup mock DB and Redis
    cursor = MockCursor(fetchall_data=[(10, "123456")])
    conn = MockConnection(cursor)
    mock_pool = mock.MagicMock()
    mock_pool.connection = mock.MagicMock(return_value=conn)
    mock_get_pool.return_value = mock_pool
    
    mock_get.return_value = None  # No Redis lockout
    mock_send.return_value = True  # Send succeeds
    
    # 2. Run dispatcher
    await spaced_repetition_nudge_dispatcher()
    
    # 3. Assertions
    mock_send.assert_called_once()
    assert "Your graph is cooling down!" in mock_send.call_args[0][1]
    assert mock_send.call_args[0][0] == "123456"
    assert mock_send.call_args[1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "quiz:next"
    
    # Verify Redis lockout key is set for 7 days
    mock_get.assert_called_with("sr_nudge_sent:10")
    mock_setex.assert_called_with("sr_nudge_sent:10", 604800, "1")

@pytest.mark.asyncio
async def test_generate_weekly_svg_mind_map_empty():
    """Verify SVG mind map generation when no tags exist."""
    cursor = MockCursor(fetchall_data=[])
    svg = await generate_weekly_svg_mind_map(cursor, user_id=1)
    
    assert "<svg" in svg
    assert "No constellation mapped yet" in svg

@pytest.mark.asyncio
async def test_generate_weekly_svg_mind_map_success():
    """Verify SVG mind map correctly plots tags and layout elements."""
    # Fetchall mock calls: 1. recent tags, 2. overall tags (none needed because len >= 5), 3. item tags for edges
    recent_tags = [("python", 10), ("fastapi", 8), ("react", 6), ("neon", 4), ("redis", 2)]
    item_tags = [
        (["python", "fastapi"],),
        (["react", "redis"],),
    ]
    cursor = MockCursor(fetchall_data=[recent_tags, item_tags])
    
    svg = await generate_weekly_svg_mind_map(cursor, user_id=1)
    
    assert "<svg" in svg
    assert "RECALL CONSTELLATION" in svg
    assert "#PYTHON" in svg
    assert "#FASTAPI" in svg
    assert "#REACT" in svg
    assert "#NEON" in svg
    assert "#REDIS" in svg
    assert "stroke-dasharray" in svg  # Connecting edge styling

@pytest.mark.asyncio
@mock.patch("backend.scheduler.scheduler.get_pool")
@mock.patch("backend.scheduler.scheduler.send_telegram_photo")
@mock.patch("backend.services.mind_map_service.generate_weekly_svg_mind_map")
async def test_weekly_mind_map_dispatcher(mock_gen_svg, mock_send_photo, mock_get_pool):
    """Verify weekly mind map dispatcher fetches users, generates SVG, converts it, and uploads to Telegram."""
    cursor = MockCursor(fetchall_data=[(22, "987654")])
    conn = MockConnection(cursor)
    mock_pool = mock.MagicMock()
    mock_pool.connection = mock.MagicMock(return_value=conn)
    mock_get_pool.return_value = mock_pool
    
    mock_gen_svg.return_value = '<svg width="100" height="100"><circle cx="50" cy="50" r="40" fill="red"/></svg>'
    mock_send_photo.return_value = True
    
    await weekly_mind_map_dispatcher()
    
    mock_gen_svg.assert_called_once()
    mock_send_photo.assert_called_once()
    assert mock_send_photo.call_args[1]["chat_id"] == "987654"
    assert mock_send_photo.call_args[1]["filename"] == "weekly_mind_map.png"
    assert len(mock_send_photo.call_args[1]["photo_bytes"]) > 0
    assert mock_send_photo.call_args[1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "quiz:next"

@pytest.mark.asyncio
@mock.patch("backend.scheduler.scheduler.get_pool")
@mock.patch("backend.scheduler.scheduler.send_telegram_message")
async def test_monthly_memory_rhythm_scanner(mock_send, mock_get_pool):
    """Verify monthly scanner calculates shifts correctly and notifies user."""
    # fetchall mock inputs: 
    # 1. users list
    # 2. tags_30 for user 33
    # 3. tags_90 for user 33
    users_list = [(33, "555666")]
    tags_30 = [("python", 15), ("fastapi", 10)]
    tags_90 = [("python", 5), ("philosophy", 10)]
    
    cursor = MockCursor(fetchall_data=[users_list, tags_30, tags_90])
    conn = MockConnection(cursor)
    mock_pool = mock.MagicMock()
    mock_pool.connection = mock.MagicMock(return_value=conn)
    mock_get_pool.return_value = mock_pool
    
    await monthly_memory_rhythm_scanner()
    
    mock_send.assert_called_once()
    assert mock_send.call_args[0][0] == "555666"
    assert "Your Monthly Memory Rhythm is Shifting!" in mock_send.call_args[0][1]
    assert "#python" in mock_send.call_args[0][1]      # Surging tag
    assert "#philosophy" in mock_send.call_args[0][1]  # Cooling tag
