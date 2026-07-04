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
