import pytest
import unittest.mock as mock
from datetime import datetime, timezone
from backend.services.pulse_service import calculate_user_pulse, update_user_pulse

@pytest.mark.asyncio
async def test_calculate_user_pulse_string_last_active():
    mock_cur = mock.AsyncMock()
    mock_cur.fetchone.side_effect = [
        (10,),  # items count
        (8, 10), # retention: 80%
        ("2026-06-01T12:00:00+00:00",) # iso string
    ]

    pulse = await calculate_user_pulse(mock_cur, 42)
    assert 0 <= pulse <= 100

@pytest.mark.asyncio
async def test_calculate_user_pulse_invalid_date():
    mock_cur = mock.AsyncMock()
    mock_cur.fetchone.side_effect = [
        (0,),
        (0, 0),
        ("invalid-date-string",)
    ]

    pulse = await calculate_user_pulse(mock_cur, 42)
    assert 0 <= pulse <= 100

@pytest.mark.asyncio
async def test_update_user_pulse():
    mock_cur = mock.AsyncMock()
    mock_cur.fetchone.side_effect = [
        (5,),
        (5, 5),
        (datetime.now(timezone.utc),)
    ]

    score = await update_user_pulse(mock_cur, 42)
    assert score >= 0
    mock_cur.execute.assert_called()
