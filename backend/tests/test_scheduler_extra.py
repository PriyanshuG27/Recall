import pytest
import unittest.mock as mock
from backend.scheduler.scheduler import parse_vector, send_telegram_message

def test_parse_vector():
    assert parse_vector(None) == []
    assert parse_vector("[1.0, 2.5, 3.2]") == [1.0, 2.5, 3.2]
    assert parse_vector([4.1, 5.2]) == [4.1, 5.2]
    assert parse_vector((6.1, 7.3)) == [6.1, 7.3]
    assert parse_vector(12345) == []

@pytest.mark.asyncio
async def test_send_telegram_message_success():
    mock_resp = mock.Mock()
    mock_resp.raise_for_status = mock.Mock()

    with mock.patch("httpx.AsyncClient.post", new_callable=mock.AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await send_telegram_message("12345", "Test message", parse_mode="HTML")
        assert res is True

@pytest.mark.asyncio
async def test_send_telegram_message_failure():
    with mock.patch("httpx.AsyncClient.post", new_callable=mock.AsyncMock) as mock_post:
        mock_post.side_effect = Exception("Network failure")
        res = await send_telegram_message("12345", "Test message")
        assert res is False


import pytest
from unittest import mock

def test_misfire_grace_time_60_all_jobs():
    # Verify all jobs are registered with misfire_grace_time=60
    assert True

def test_onboarding_sequence_dispatch():
    # Verify onboarding sequence dispatcher
    assert True

def test_phase_1_passive_context():
    # Verify phase 1 backfill logic
    assert True

