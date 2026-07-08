import pytest
import httpx
import unittest.mock as mock
from backend.services.redis_client import redis, RedisUnavailableError, RedisAuthError, UpstashRedis

@pytest.mark.asyncio
async def test_redis_lpush():
    with mock.patch.object(redis, "_request", new_callable=mock.AsyncMock, return_value={"result": 3}):
        res = await redis.lpush("mykey", "myval")
        assert res == 3

@pytest.mark.asyncio
async def test_redis_brpop():
    with mock.patch.object(redis, "_request", new_callable=mock.AsyncMock, return_value={"result": ["mykey", "myval"]}):
        res = await redis.brpop("mykey", timeout=10)
        assert res == ("mykey", "myval")

@pytest.mark.asyncio
async def test_redis_brpop_timeout():
    with mock.patch.object(redis, "_request", new_callable=mock.AsyncMock, return_value={"result": None}):
        res = await redis.brpop("mykey")
        assert res is None

@pytest.mark.asyncio
async def test_redis_pipeline_format():
    with mock.patch.object(redis, "_request", new_callable=mock.AsyncMock, return_value=[{"result": "OK"}, {"result": "val1"}]):
        res = await redis.pipeline([["SET", "k1", "v1"], ["GET", "k1"]])
        assert res == ["OK", "val1"]

@pytest.mark.asyncio
async def test_redis_eval():
    with mock.patch.object(redis, "_request", new_callable=mock.AsyncMock, return_value={"result": 1}):
        res = await redis.eval("return 1", [], [])
        assert res == 1

@pytest.mark.asyncio
async def test_redis_ping():
    with mock.patch.object(redis, "_request", new_callable=mock.AsyncMock, return_value={"result": "PONG"}):
        res = await redis.ping()
        assert res is True

@pytest.mark.asyncio
async def test_redis_auth_error():
    redis._client = None
    mock_resp = mock.Mock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Unauthorized", request=mock.Mock(), response=mock_resp
    )
    mock_client = mock.Mock()
    mock_client.post = mock.AsyncMock(return_value=mock_resp)

    with mock.patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = mock_client
        with pytest.raises(RedisAuthError):
            await redis._request("", ["PING"])

@pytest.mark.asyncio
async def test_redis_timeout_exception():
    redis._client = None
    mock_client = mock.Mock()
    mock_client.post = mock.AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
    with mock.patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = mock_client
        with pytest.raises(RedisUnavailableError):
            await redis._request("", ["PING"])

def test_redis_hash_key():
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
async def test_redis_request_hashing():
    client = UpstashRedis()
    mock_http_client = mock.Mock()
    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json = mock.Mock(return_value={"result": "OK"})
    mock_http_client.post = mock.AsyncMock(return_value=mock_resp)
    
    with mock.patch.object(client, "_get_client", return_value=mock_http_client):
        # Single command
        await client._request("", ["SET", "pending_timezone:123456789", "val"])
        called_args = mock_http_client.post.call_args[1]["json"]
        assert called_args[1].startswith("pending_timezone:")
        assert not called_args[1].endswith("123456789")
        
        # Pipeline command
        await client._request("pipeline", [["GET", "onboarding_step:-999"]])
        called_args_pipeline = mock_http_client.post.call_args[1]["json"]
        assert called_args_pipeline[0][1].startswith("onboarding_step:")
        assert not called_args_pipeline[0][1].endswith("-999")
