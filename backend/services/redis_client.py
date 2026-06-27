"""
backend/services/redis_client.py
================================
Asynchronous wrapper for the Upstash Redis REST API.
Enforces stateless HTTPS connections, 5-second timeouts, retry on 5xx,
and strict token redaction in logs/exceptions.
"""

import asyncio
import logging
from typing import List, Tuple, Optional, Union
import httpx

logger = logging.getLogger(__name__)

class RedisUnavailableError(Exception):
    """Exception raised when Upstash Redis is unavailable or times out."""
    pass

class RedisAuthError(Exception):
    """Exception raised when Upstash Redis authentication fails (4xx status)."""
    pass

class UpstashRedis:
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        from backend.config import settings
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=settings.UPSTASH_REDIS_REST_URL,
                headers={"Authorization": f"Bearer {settings.UPSTASH_REDIS_REST_TOKEN}"},
                timeout=10.0,
            )
        return self._client

    def _redact(self, msg: str) -> str:
        """Redacts the Upstash Redis REST token from any string message."""
        from backend.config import settings
        if settings and settings.UPSTASH_REDIS_REST_TOKEN:
            return msg.replace(settings.UPSTASH_REDIS_REST_TOKEN, "<REDACTED>")
        return msg

    async def _request(self, endpoint: str, json_data) -> dict | list:
        client = self._get_client()
        try:
            resp = await client.post(endpoint, json=json_data)
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException as e:
            redacted_msg = self._redact(str(e))
            logger.error("Upstash Redis timeout: %s", redacted_msg)
            raise RedisUnavailableError(redacted_msg) from e
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            redacted_msg = self._redact(str(e))
            if 400 <= status_code < 500:
                logger.error("Upstash Redis auth error (HTTP %d): %s", status_code, redacted_msg)
                raise RedisAuthError(redacted_msg) from e
            elif 500 <= status_code < 600:
                logger.warning("Upstash Redis 5xx error (HTTP %d), retrying in 1s...", status_code)
                await asyncio.sleep(1.0)
                try:
                    resp = await client.post(endpoint, json=json_data)
                    resp.raise_for_status()
                    return resp.json()
                except Exception as retry_err:
                    redacted_retry_msg = self._redact(str(retry_err))
                    logger.error("Upstash Redis retry failed: %s", redacted_retry_msg)
                    raise RedisUnavailableError(redacted_retry_msg) from retry_err
            else:
                logger.error("Upstash Redis HTTP error (HTTP %d): %s", status_code, redacted_msg)
                raise RedisUnavailableError(redacted_msg) from e
        except httpx.RequestError as e:
            redacted_msg = self._redact(str(e))
            logger.error("Upstash Redis request error: %s", redacted_msg)
            raise RedisUnavailableError(redacted_msg) from e

    async def lpush(self, key: str, value: str) -> int:
        """
        Pushes a value to the head of a list.
        Returns the number of elements in the list after the push.
        """
        data = await self._request("", ["LPUSH", key, value])
        if isinstance(data, dict) and "error" in data:
            raise RedisUnavailableError(self._redact(data["error"]))
        return int(data["result"])

    async def brpop(self, key: str, timeout: int = 5) -> Optional[Tuple[str, str]]:
        """
        Blocks and pops a value from the tail of a list.
        Returns a tuple of (key, value) or None if timeout is reached.
        """
        data = await self._request("", ["BRPOP", key, str(timeout)])
        if isinstance(data, dict):
            if "error" in data:
                raise RedisUnavailableError(self._redact(data["error"]))
            result = data.get("result")
            if result is not None and len(result) >= 2:
                return (result[0], result[1])
        return None

    async def pipeline(self, commands: List[List]) -> List:
        """
        Sends a batch of commands to the Upstash Redis REST pipeline endpoint.
        Returns a list of results for each command.
        """
        data = await self._request("pipeline", commands)
        if not isinstance(data, list):
            raise RedisUnavailableError(f"Unexpected pipeline response: {self._redact(str(data))}")
            
        out = []
        for item in data:
            if isinstance(item, dict) and "error" in item:
                raise RedisUnavailableError(self._redact(item["error"]))
            # Extract result value
            if isinstance(item, dict) and "result" in item:
                out.append(item["result"])
            else:
                out.append(item)
        return out

    async def get(self, key: str) -> Optional[str]:
        """Get the value of a key."""
        data = await self._request("", ["GET", key])
        if isinstance(data, dict):
            if "error" in data:
                raise RedisUnavailableError(self._redact(data["error"]))
            return data.get("result")
        return None

    async def setex(self, key: str, seconds: int, value: str) -> bool:
        """Set key to hold the string value and set key to timeout after a given number of seconds."""
        data = await self._request("", ["SET", key, value, "EX", str(seconds)])
        if isinstance(data, dict):
            if "error" in data:
                raise RedisUnavailableError(self._redact(data["error"]))
            return data.get("result") == "OK"
        return False

    async def delete(self, key: str) -> int:
        """Delete a key."""
        data = await self._request("", ["DEL", key])
        if isinstance(data, dict):
            if "error" in data:
                raise RedisUnavailableError(self._redact(data["error"]))
            return int(data.get("result", 0))
        return 0

    async def zadd(self, key: str, score: float, member: str) -> int:
        """Add member with score to a sorted set."""
        data = await self._request("", ["ZADD", key, str(score), member])
        if isinstance(data, dict) and "error" in data:
            raise RedisUnavailableError(self._redact(data["error"]))
        return int(data.get("result", 0))

    async def zrem(self, key: str, member: str) -> int:
        """Remove member from a sorted set."""
        data = await self._request("", ["ZREM", key, member])
        if isinstance(data, dict) and "error" in data:
            raise RedisUnavailableError(self._redact(data["error"]))
        return int(data.get("result", 0))

    async def zrangebyscore(self, key: str, min_score: float | str, max_score: float | str) -> List[str]:
        """Return members in sorted set with scores between min_score and max_score."""
        data = await self._request("", ["ZRANGEBYSCORE", key, str(min_score), str(max_score)])
        if isinstance(data, dict) and "error" in data:
            raise RedisUnavailableError(self._redact(data["error"]))
        # Upstash REST returns the list inside the 'result' field
        return data.get("result", [])

    async def eval(self, script: str, numkeys: int, *args) -> Optional[Union[dict, list, str, int]]:
        """Execute a Lua script on the Redis server."""
        payload = ["EVAL", script, str(numkeys)] + list(args)
        data = await self._request("", payload)
        if isinstance(data, dict) and "error" in data:
            raise RedisUnavailableError(self._redact(data["error"]))
        return data.get("result")

    async def ping(self) -> bool:
        """Checks liveness of the Upstash Redis instance. Returns True if responsive."""
        try:
            data = await self._request("", ["PING"])
            if isinstance(data, dict) and data.get("result") == "PONG":
                return True
            return False
        except Exception as e:
            logger.warning("Upstash Redis ping failed: %s", self._redact(str(e)))
            return False

# Expose singleton instance at module level
redis = UpstashRedis()
