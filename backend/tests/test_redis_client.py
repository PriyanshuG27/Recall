import pytest
import unittest.mock as mock
import redis.asyncio as aioredis
from backend.services.redis_client import redis, RedisUnavailableError, RedisAuthError, UpstashRedis

@pytest.mark.asyncio
async def test_redis_lpush():
    mock_client = mock.AsyncMock()
    mock_client.lpush.return_value = 3
    with mock.patch.object(redis, "_get_client", return_value=mock_client):
        res = await redis.lpush("mykey", "myval")
        assert res == 3
        mock_client.lpush.assert_called_once_with(redis._hash_key("mykey"), "myval")

@pytest.mark.asyncio
async def test_redis_brpop():
    mock_client = mock.AsyncMock()
    mock_client.brpop.return_value = ("mykey", "myval")
    with mock.patch.object(redis, "_get_client", return_value=mock_client):
        res = await redis.brpop("mykey", timeout=10)
        assert res == ("mykey", "myval")

@pytest.mark.asyncio
async def test_redis_brpop_timeout():
    mock_client = mock.AsyncMock()
    mock_client.brpop.return_value = None
    with mock.patch.object(redis, "_get_client", return_value=mock_client):
        res = await redis.brpop("mykey")
        assert res is None

@pytest.mark.asyncio
async def test_redis_pipeline_format():
    mock_client = mock.MagicMock()
    mock_pipe = mock.AsyncMock()
    mock_client.pipeline.return_value.__aenter__.return_value = mock_pipe
    mock_pipe.execute.return_value = ["OK", "val1"]
    with mock.patch.object(redis, "_get_client", return_value=mock_client):
        res = await redis.pipeline([["SET", "k1", "v1"], ["GET", "k1"]])
        assert res == ["OK", "val1"]

@pytest.mark.asyncio
async def test_redis_eval():
    mock_client = mock.AsyncMock()
    mock_client.eval.return_value = 1
    with mock.patch.object(redis, "_get_client", return_value=mock_client):
        res = await redis.eval("return 1", 0)
        assert res == 1

@pytest.mark.asyncio
async def test_redis_ping():
    mock_client = mock.AsyncMock()
    mock_client.ping.return_value = True
    with mock.patch.object(redis, "_get_client", return_value=mock_client):
        res = await redis.ping()
        assert res is True

@pytest.mark.asyncio
async def test_redis_auth_error():
    mock_client = mock.AsyncMock()
    mock_client.lpush.side_effect = aioredis.AuthenticationError("Auth failed")
    with mock.patch.object(redis, "_get_client", return_value=mock_client):
        with pytest.raises(RedisAuthError):
            await redis.lpush("mykey", "myval")

@pytest.mark.asyncio
async def test_redis_timeout_exception():
    mock_client = mock.AsyncMock()
    mock_client.lpush.side_effect = aioredis.RedisError("Timeout")
    with mock.patch.object(redis, "_get_client", return_value=mock_client):
        with pytest.raises(RedisUnavailableError):
            await redis.lpush("mykey", "myval")

def test_redis_hash_key(monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, "ENV", "development")
    client = UpstashRedis()
    # Non-numeric keys shouldn't hash
    assert client._hash_key("mykey") == "mykey"
    assert client._hash_key("user:profile") == "user:profile"
    
    # Numeric parts should hash
    h1 = client._hash_key("user:last_frontend_active:101")
    assert h1.startswith("user:last_frontend_active:")
    assert len(h1.split(":")[-1]) == 16
    
    h2 = client._hash_key("pending_timezone:123456789")
    assert h2.startswith("pending_timezone:")
    assert len(h2.split(":")[-1]) == 16
    
    h3 = client._hash_key("pending_timezone:-123456789")
    assert h3.startswith("pending_timezone:")
    assert len(h3.split(":")[-1]) == 16

@pytest.mark.asyncio
async def test_redis_request_hashing(monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, "ENV", "development")
    client = UpstashRedis()
    
    mock_client = mock.MagicMock()
    mock_pipe = mock.AsyncMock()
    mock_client.pipeline.return_value.__aenter__.return_value = mock_pipe
    mock_pipe.execute.return_value = ["OK"]
    
    with mock.patch.object(client, "_get_client", return_value=mock_client):
        # Pipeline command
        await client.pipeline([["SET", "pending_timezone:123456789", "val"]])
        mock_pipe.execute_command.assert_called_once()
        called_cmd = mock_pipe.execute_command.call_args[0]
        assert called_cmd[0] == "SET"
        assert called_cmd[1].startswith("pending_timezone:")
        assert not called_cmd[1].endswith("123456789")
