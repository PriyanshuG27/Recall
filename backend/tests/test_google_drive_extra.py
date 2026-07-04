import pytest
import unittest.mock as mock
from backend.services.google_drive import run_google_drive_sync

@pytest.mark.asyncio
async def test_run_google_drive_sync_pool_none():
    with mock.patch("backend.db.connection._pool", None):
        res = await run_google_drive_sync(42)
        assert res is None

@pytest.mark.asyncio
async def test_run_google_drive_sync_no_token():
    mock_pool = mock.MagicMock()
    mock_conn = mock.AsyncMock()
    mock_cur = mock.AsyncMock()
    mock_cur.fetchone.return_value = (None,)
    mock_conn.cursor.return_value.__aenter__.return_value = mock_cur
    mock_pool.connection.return_value.__aenter__.return_value = mock_conn

    with mock.patch("backend.db.connection._pool", mock_pool):
        res = await run_google_drive_sync(42)
        assert res is None
