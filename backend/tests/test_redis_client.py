import pytest
import httpx
import unittest.mock as mock
from backend.services.redis_client import redis, RedisUnavailableError, RedisAuthError

@pytest.mark.asyncio
async def test_redis_lpush():
    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"result": 3}
    
    with mock.patch("httpx.AsyncClient.post", new_callable=mock.AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        
        res = await redis.lpush("mykey", "myval")
        assert res == 3
        
        # Verify call arguments
        mock_post.assert_called_once_with("", json=["LPUSH", "mykey", "myval"])

@pytest.mark.asyncio
async def test_redis_brpop():
    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"result": ["mykey", "myval"]}
    
    with mock.patch("httpx.AsyncClient.post", new_callable=mock.AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        
        res = await redis.brpop("mykey", timeout=10)
        assert res == ("mykey", "myval")
        
        mock_post.assert_called_once_with("", json=["BRPOP", "mykey", "10"])

@pytest.mark.asyncio
async def test_redis_brpop_timeout():
    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"result": None}
    
    with mock.patch("httpx.AsyncClient.post", new_callable=mock.AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        
        res = await redis.brpop("mykey")
        assert res is None
        
        mock_post.assert_called_once_with("", json=["BRPOP", "mykey", "5"])

@pytest.mark.asyncio
async def test_redis_pipeline_format():
    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {"result": "OK"},
        {"result": "val1"}
    ]
    
    with mock.patch("httpx.AsyncClient.post", new_callable=mock.AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        
        commands = [
            ["SET", "k1", "v1"],
            ["GET", "k1"]
        ]
        res = await redis.pipeline(commands)
        assert res == ["OK", "val1"]
        
        # Verify the pipeline endpoint and JSON format are correct
        mock_post.assert_called_once_with("pipeline", json=commands)

@pytest.mark.asyncio
async def test_redis_ping():
    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"result": "PONG"}
    
    with mock.patch("httpx.AsyncClient.post", new_callable=mock.AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        
        res = await redis.ping()
        assert res is True
        
        mock_post.assert_called_once_with("", json=["PING"])

@pytest.mark.asyncio
async def test_redis_timeout_exception():
    with mock.patch("httpx.AsyncClient.post", new_callable=mock.AsyncMock) as mock_post:
        mock_post.side_effect = httpx.TimeoutException("Connection timed out")
        
        with pytest.raises(RedisUnavailableError) as exc_info:
            await redis.lpush("k", "v")
        assert "timed out" in str(exc_info.value).lower()

@pytest.mark.asyncio
async def test_redis_auth_error():
    request = httpx.Request("POST", "https://localhost")
    response = httpx.Response(401, request=request)
    
    with mock.patch("httpx.AsyncClient.post", new_callable=mock.AsyncMock) as mock_post:
        mock_post.return_value = response
        
        with pytest.raises(RedisAuthError):
            await redis.lpush("k", "v")

@pytest.mark.asyncio
async def test_redis_get_setex_delete():
    mock_resp_get = mock.Mock()
    mock_resp_get.status_code = 200
    mock_resp_get.json.return_value = {"result": "cached_graph"}
    
    mock_resp_set = mock.Mock()
    mock_resp_set.status_code = 200
    mock_resp_set.json.return_value = {"result": "OK"}
    
    mock_resp_del = mock.Mock()
    mock_resp_del.status_code = 200
    mock_resp_del.json.return_value = {"result": 1}
    
    with mock.patch("httpx.AsyncClient.post", new_callable=mock.AsyncMock) as mock_post:
        # 1. Test GET
        mock_post.return_value = mock_resp_get
        res_get = await redis.get("graph:42")
        assert res_get == "cached_graph"
        mock_post.assert_called_with("", json=["GET", "graph:42"])
        
        # 2. Test SETEX
        mock_post.return_value = mock_resp_set
        res_set = await redis.setex("graph:42", 60, "cached_graph")
        assert res_set is True
        mock_post.assert_called_with("", json=["SET", "graph:42", "cached_graph", "EX", "60"])
        
        # 3. Test DELETE
        mock_post.return_value = mock_resp_del
        res_del = await redis.delete("graph:42")
        assert res_del == 1
        mock_post.assert_called_with("", json=["DEL", "graph:42"])

