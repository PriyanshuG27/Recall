import pytest
import asyncio
from backend.services.http_client import get_http_client, close_http_client

@pytest.mark.asyncio
async def test_get_http_client_and_close():
    client1 = get_http_client()
    assert client1 is not None
    assert not client1.is_closed

    client2 = get_http_client()
    assert client1 is client2

    await close_http_client()
    assert client1.is_closed

    # Test call when no loop is running
    client3 = get_http_client()
    assert client3 is not None
    await close_http_client()
