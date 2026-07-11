"""
backend/services/redis_client.py
================================
Asynchronous client for Upstash Redis using TCP protocol.
Provides connection pooling, automatic string decoding, key hashing for privacy,
and custom error mapping.
"""

import asyncio
import logging
import urllib.parse
from typing import List, Tuple, Optional, Union
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

class RedisUnavailableError(Exception):
    """Exception raised when Upstash Redis is unavailable or times out."""
    pass

class RedisAuthError(Exception):
    """Exception raised when Upstash Redis authentication fails."""
    pass

class UpstashRedis:
    def __init__(self):
        self._pool: Optional[aioredis.ConnectionPool] = None
        self._client: Optional[aioredis.Redis] = None

    def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            from backend.config import settings
            
            # Determine connection URL
            redis_url = getattr(settings, "REDIS_URL", None) or getattr(settings, "UPSTASH_REDIS_URL", None)
            if not redis_url:
                rest_url = settings.UPSTASH_REDIS_REST_URL or ""
                token = settings.UPSTASH_REDIS_REST_TOKEN or ""
                
                host = rest_url.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
                if not host or host in ("localhost", "127.0.0.1"):
                    redis_url = "redis://localhost:6379"
                else:
                    escaped_token = urllib.parse.quote(token)
                    redis_url = f"rediss://default:{escaped_token}@{host}:6379"
            
            logger.info("Initializing TCP Redis Connection Pool...")
            self._pool = aioredis.ConnectionPool.from_url(
                redis_url,
                max_connections=20,
                decode_responses=True,
                socket_timeout=10.0,
                socket_connect_timeout=5.0
            )
            self._client = aioredis.Redis(connection_pool=self._pool)
        return self._client

    def _redact(self, msg: str) -> str:
        """Redacts the Upstash Redis REST token/password from any message."""
        from backend.config import settings
        if settings and settings.UPSTASH_REDIS_REST_TOKEN:
            return msg.replace(settings.UPSTASH_REDIS_REST_TOKEN, "<REDACTED>")
        return msg

    def _hash_key(self, key: str) -> str:
        if not isinstance(key, str):
            return key
        import hashlib
        from backend.config import settings

        prefix = ""
        if settings and settings.ENV == "test":
            if not key.startswith("test:"):
                prefix = "test:"

        parts = key.split(":")
        hashed_parts = []
        for part in parts:
            is_numeric = False
            if part.isdigit():
                is_numeric = True
            elif part.startswith("-") and part[1:].isdigit():
                is_numeric = True
                
            if is_numeric:
                hashed = hashlib.sha256(part.encode("utf-8")).hexdigest()[:16]
                hashed_parts.append(hashed)
            else:
                hashed_parts.append(part)
        return prefix + ":".join(hashed_parts)

    async def lpush(self, key: str, value: str) -> int:
        """Push a value to the head of a list."""
        try:
            client = self._get_client()
            res = await client.lpush(self._hash_key(key), value)
            return int(res)
        except aioredis.AuthenticationError as ae:
            raise RedisAuthError(self._redact(str(ae)))
        except aioredis.RedisError as re:
            raise RedisUnavailableError(self._redact(str(re)))

    async def llen(self, key: str) -> int:
        """Return the length of a list."""
        try:
            client = self._get_client()
            res = await client.llen(self._hash_key(key))
            return int(res)
        except aioredis.RedisError as re:
            raise RedisUnavailableError(self._redact(str(re)))

    async def lindex(self, key: str, index: int) -> Optional[str]:
        """Get an element from a list by its index."""
        try:
            client = self._get_client()
            res = await client.lindex(self._hash_key(key), index)
            return res
        except aioredis.RedisError as re:
            raise RedisUnavailableError(self._redact(str(re)))

    async def brpop(self, key: str, timeout: int = 5) -> Optional[Tuple[str, str]]:
        """Blocking pop from the tail of a list."""
        try:
            client = self._get_client()
            res = await client.brpop(self._hash_key(key), timeout=timeout)
            if res:
                return (res[0], res[1])
            return None
        except aioredis.RedisError as re:
            raise RedisUnavailableError(self._redact(str(re)))

    async def pipeline(self, commands: List[List]) -> List:
        """Execute a batch of commands atomically inside a pipeline."""
        try:
            client = self._get_client()
            async with client.pipeline(transaction=True) as pipe:
                for cmd in commands:
                    hashed_cmd = list(pipe.execute_command.__code__.co_varnames) # Stub
                    # Map and hash key parameters in command array
                    hashed_cmd = list(cmd)
                    if len(hashed_cmd) > 1:
                        cmd_name = str(hashed_cmd[0]).upper()
                        if cmd_name == "EVAL" and len(hashed_cmd) > 2:
                            try:
                                num_keys = int(hashed_cmd[2])
                                for idx in range(3, min(3 + num_keys, len(hashed_cmd))):
                                    hashed_cmd[idx] = self._hash_key(hashed_cmd[idx])
                            except ValueError:
                                pass
                        else:
                            hashed_cmd[1] = self._hash_key(hashed_cmd[1])
                            if len(hashed_cmd) > 2 and cmd_name == "BRPOPLPUSH":
                                hashed_cmd[2] = self._hash_key(hashed_cmd[2])
                    pipe.execute_command(*hashed_cmd)
                res = await pipe.execute()
                return res
        except aioredis.AuthenticationError as ae:
            raise RedisAuthError(self._redact(str(ae)))
        except aioredis.RedisError as re:
            raise RedisUnavailableError(self._redact(str(re)))

    async def get(self, key: str) -> Optional[str]:
        """Get the value of a key."""
        try:
            client = self._get_client()
            res = await client.get(self._hash_key(key))
            return res
        except aioredis.RedisError as re:
            raise RedisUnavailableError(self._redact(str(re)))

    async def setex(self, key: str, seconds: int, value: str) -> bool:
        """Set the value and expiration of a key."""
        try:
            client = self._get_client()
            await client.setex(self._hash_key(key), seconds, value)
            return True
        except aioredis.AuthenticationError as ae:
            raise RedisAuthError(self._redact(str(ae)))
        except aioredis.RedisError as re:
            raise RedisUnavailableError(self._redact(str(re)))

    async def delete(self, key: str) -> int:
        """Delete a key."""
        try:
            client = self._get_client()
            res = await client.delete(self._hash_key(key))
            return int(res)
        except aioredis.RedisError as re:
            raise RedisUnavailableError(self._redact(str(re)))

    async def expire(self, key: str, seconds: int) -> bool:
        """Set a key's time to live in seconds."""
        try:
            client = self._get_client()
            res = await client.expire(self._hash_key(key), seconds)
            return bool(res)
        except aioredis.RedisError as re:
            raise RedisUnavailableError(self._redact(str(re)))

    async def zadd(self, key: str, score: float, member: str) -> int:
        """Add a member to a sorted set."""
        try:
            client = self._get_client()
            res = await client.zadd(self._hash_key(key), {member: score})
            return int(res)
        except aioredis.RedisError as re:
            raise RedisUnavailableError(self._redact(str(re)))

    async def zrem(self, key: str, member: str) -> int:
        """Remove a member from a sorted set."""
        try:
            client = self._get_client()
            res = await client.zrem(self._hash_key(key), member)
            return int(res)
        except aioredis.RedisError as re:
            raise RedisUnavailableError(self._redact(str(re)))

    async def zrangebyscore(self, key: str, min_score: float | str, max_score: float | str) -> List[str]:
        """Return a range of members in a sorted set by score."""
        try:
            client = self._get_client()
            res = await client.zrangebyscore(self._hash_key(key), min_score, max_score)
            return list(res)
        except aioredis.RedisError as re:
            raise RedisUnavailableError(self._redact(str(re)))

    async def eval(self, script: str, numkeys: int, *args) -> Optional[Union[dict, list, str, int]]:
        """Execute a Lua script server-side."""
        try:
            client = self._get_client()
            hashed_args = list(args)
            for idx in range(min(numkeys, len(hashed_args))):
                hashed_args[idx] = self._hash_key(hashed_args[idx])
            res = await client.eval(script, numkeys, *hashed_args)
            return res
        except aioredis.RedisError as re:
            raise RedisUnavailableError(self._redact(str(re)))

    async def rpush(self, key: str, value: str) -> int:
        """Push a value to the tail of a list."""
        try:
            client = self._get_client()
            res = await client.rpush(self._hash_key(key), value)
            return int(res)
        except aioredis.RedisError as re:
            raise RedisUnavailableError(self._redact(str(re)))

    async def lrange(self, key: str, start: int, stop: int) -> List[str]:
        """Return a range of elements from a list."""
        try:
            client = self._get_client()
            res = await client.lrange(self._hash_key(key), start, stop)
            return list(res)
        except aioredis.RedisError as re:
            raise RedisUnavailableError(self._redact(str(re)))

    async def brpoplpush(self, source: str, destination: str, timeout: int) -> Optional[str]:
        """Blocking pop from source and push to destination."""
        try:
            client = self._get_client()
            res = await client.brpoplpush(self._hash_key(source), self._hash_key(destination), timeout=timeout)
            return res
        except aioredis.RedisError as re:
            raise RedisUnavailableError(self._redact(str(re)))

    async def lrem(self, key: str, count: int, value: str) -> int:
        """Remove occurrences of a value from a list."""
        try:
            client = self._get_client()
            res = await client.lrem(self._hash_key(key), count, value)
            return int(res)
        except aioredis.RedisError as re:
            raise RedisUnavailableError(self._redact(str(re)))

    async def sadd(self, key: str, member: str) -> int:
        """Add a member to a set."""
        try:
            client = self._get_client()
            res = await client.sadd(self._hash_key(key), member)
            return int(res)
        except aioredis.RedisError as re:
            raise RedisUnavailableError(self._redact(str(re)))

    async def srem(self, key: str, member: str) -> int:
        """Remove a member from a set."""
        try:
            client = self._get_client()
            res = await client.srem(self._hash_key(key), member)
            return int(res)
        except aioredis.RedisError as re:
            raise RedisUnavailableError(self._redact(str(re)))

    async def smembers(self, key: str) -> List[str]:
        """Return all members in a set."""
        try:
            client = self._get_client()
            res = await client.smembers(self._hash_key(key))
            return list(res)
        except aioredis.RedisError as re:
            raise RedisUnavailableError(self._redact(str(re)))

    async def sismember(self, key: str, member: str) -> int:
        """Check set membership."""
        try:
            client = self._get_client()
            res = await client.sismember(self._hash_key(key), member)
            return 1 if res else 0
        except aioredis.RedisError as re:
            raise RedisUnavailableError(self._redact(str(re)))

    async def ping(self) -> bool:
        """Checks liveness of the Redis instance."""
        try:
            client = self._get_client()
            res = await client.ping()
            return bool(res)
        except Exception as e:
            logger.warning("Redis ping failed: %s", self._redact(str(e)))
            return False

# Expose singleton instance at module level
redis = UpstashRedis()
