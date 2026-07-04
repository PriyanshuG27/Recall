import pytest
import unittest.mock as mock
from backend.worker import get_next_mood_category

@pytest.mark.asyncio
async def test_get_next_mood_category():
    mock_redis = mock.AsyncMock()
    mock_redis._request.side_effect = [
        {"result": ["curiosity", "timing"]},
        {"result": ["future", "10", "friction", "5"]}
    ]

    with mock.patch("backend.worker.redis", mock_redis):
        mood = await get_next_mood_category("12345")
        assert mood in ["curiosity", "timing", "future", "friction", "identity", "connection", "stakes", "surprise"]
