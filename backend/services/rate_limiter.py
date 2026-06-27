"""
backend/services/rate_limiter.py
================================
Redis sliding window rate limiter for Recall.
"""

import time
import uuid
import logging
from typing import Union
from fastapi import Depends
from backend.services.redis_client import redis
from backend.middleware.twa_auth import get_current_user, UserContext

logger = logging.getLogger(__name__)

class RateLimitExceeded(Exception):
    """Exception raised when a user exceeds their rolling window request quota."""
    def __init__(self, retry_after: float):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after:.1f} seconds.")


RATE_LIMIT_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window_start = tonumber(ARGV[2])
local member_id = ARGV[3]
local expire_seconds = tonumber(ARGV[4])
local limit = tonumber(ARGV[5])

redis.call("ZREMRANGEBYSCORE", key, 0, window_start)
redis.call("ZADD", key, now, member_id)
local count = redis.call("ZCARD", key)
redis.call("EXPIRE", key, expire_seconds)

local oldest = ""
if count > limit then
    local oldest_list = redis.call("ZRANGE", key, 0, 0)
    if oldest_list and #oldest_list > 0 then
        oldest = oldest_list[1]
    end
end

return {count, oldest}
"""


async def check_rate_limit(
    user_id: Union[int, str],
    key_prefix: str = "webhook",
    limit: int = 20,
    window_seconds: int = 60
) -> None:
    """
    Checks if a user is within their rate limit of `limit` requests per `window_seconds`.
    If exceeded, raises RateLimitExceeded with the calculated wait time.
    """
    if key_prefix == "webhook":
        key = f"rate:{user_id}"
    else:
        key = f"rate:{key_prefix}:{user_id}"
        
    now = int(time.time() * 1000)  # Current timestamp in ms
    window_start = now - (window_seconds * 1000)
    
    # Member format: {timestamp_ms}-{uuid} to ensure uniqueness of every request
    member_id = f"{now}-{uuid.uuid4()}"
    expire_seconds = window_seconds + 1
    
    try:
        results = await redis.eval(
            RATE_LIMIT_LUA,
            1,
            key,
            str(now),
            str(window_start),
            member_id,
            str(expire_seconds),
            str(limit)
        )
        if not results or len(results) < 2:
            return
            
        count = int(results[0])
        oldest_member = results[1]
        
        if count > limit:
            oldest_score = now  # Fallback
            
            if oldest_member:
                try:
                    oldest_score = int(oldest_member.split("-")[0])
                except Exception:
                    pass
                    
            elapsed_since_oldest = now - oldest_score
            retry_after = window_seconds - (elapsed_since_oldest / 1000.0)
            
            # Bound retry_after between [0, window_seconds]
            retry_after = max(0.0, min(float(window_seconds), retry_after))
            
            logger.warning("Rate limit exceeded for key %s: count=%d, retry_after=%.2fs", key, count, retry_after)
            raise RateLimitExceeded(retry_after=retry_after)
            
    except RateLimitExceeded:
        raise
    except Exception as e:
        # Fail open: log error but do not crash webhook or block user if Redis fails
        logger.exception("Rate limiter error for key %s. Failing open: %s", key, e)


def rate_limit(
    prefix: str,
    limit: int,
    window: int = 60
):
    """
    FastAPI dependency factory that returns a dependency check for rate limits.
    """
    async def _dependency(
        user: UserContext = Depends(get_current_user)
    ):
        user_id = getattr(user, "user_id", getattr(user, "id", None))
        await check_rate_limit(
            user_id=user_id,
            key_prefix=prefix,
            limit=limit,
            window_seconds=window,
        )
    return _dependency
