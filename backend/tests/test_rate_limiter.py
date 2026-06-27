import pytest
import time
import asyncio
import unittest.mock as mock
from backend.services.rate_limiter import check_rate_limit, RateLimitExceeded

class MockRedisRateLimitState:
    def __init__(self):
        # Maps key -> list of timestamps (int ms)
        self.state = {}

    async def eval(self, script, numkeys, *args):
        key = args[0]
        now = int(args[1])
        window_start = int(args[2])
        member_id = args[3]
        limit = int(args[5])
        
        if key not in self.state:
            self.state[key] = []
            
        # ZREMRANGEBYSCORE key 0 window_start
        self.state[key] = [t for t in self.state[key] if t > window_start]
        
        # ZADD key now member_id
        self.state[key].append(now)
        self.state[key].sort()
        
        card = len(self.state[key])
        
        oldest_member = f"{self.state[key][0]}-mockuuid"
        return [card, oldest_member]

@pytest.mark.asyncio
async def test_rate_limiter_under_limit():
    db_state = MockRedisRateLimitState()
    with mock.patch("backend.services.redis_client.redis.eval", side_effect=db_state.eval):
        # 20 requests in the same minute should all pass
        current_time = 1719270000.0  # ms: 1719270000000
        for i in range(20):
            with mock.patch("time.time", return_value=current_time):
                await check_rate_limit("user_a")
        
        # Card should be 20
        assert len(db_state.state["rate:user_a"]) == 20

@pytest.mark.asyncio
async def test_rate_limiter_over_limit():
    db_state = MockRedisRateLimitState()
    with mock.patch("backend.services.redis_client.redis.eval", side_effect=db_state.eval):
        current_time = 1719270000.0  # ms: 1719270000000
        
        # Send 20 requests
        for i in range(20):
            with mock.patch("time.time", return_value=current_time):
                await check_rate_limit("user_a")
                
        # The 21st request in the same window must raise RateLimitExceeded
        with mock.patch("time.time", return_value=current_time):
            with pytest.raises(RateLimitExceeded) as exc_info:
                await check_rate_limit("user_a")
            assert exc_info.value.retry_after == 60.0

@pytest.mark.asyncio
async def test_rate_limiter_window_expiry():
    db_state = MockRedisRateLimitState()
    with mock.patch("backend.services.redis_client.redis.eval", side_effect=db_state.eval):
        start_time = 1719270000.0  # ms: 1719270000000
        
        # Send 20 requests at start_time
        for i in range(20):
            with mock.patch("time.time", return_value=start_time):
                await check_rate_limit("user_a")
                
        # Send 21st request after 61 seconds -> should succeed because window has reset
        expiry_time = start_time + 61.0
        with mock.patch("time.time", return_value=expiry_time):
            # Should not raise exception
            await check_rate_limit("user_a")
            
        # ZSET should only contain the 21st request timestamp because ZREMRANGEBYSCORE removed the rest
        assert len(db_state.state["rate:user_a"]) == 1

@pytest.mark.asyncio
async def test_rate_limiter_different_users():
    db_state = MockRedisRateLimitState()
    with mock.patch("backend.services.redis_client.redis.eval", side_effect=db_state.eval):
        current_time = 1719270000.0
        
        # 20 requests from user A
        for i in range(20):
            with mock.patch("time.time", return_value=current_time):
                await check_rate_limit("user_a")
                
        # 20 requests from user B in the same window -> both must pass (per-user isolation)
        for i in range(20):
            with mock.patch("time.time", return_value=current_time):
                await check_rate_limit("user_b")
                
        # Over limit for A and B independently
        with mock.patch("time.time", return_value=current_time):
            with pytest.raises(RateLimitExceeded):
                await check_rate_limit("user_a")
            with pytest.raises(RateLimitExceeded):
                await check_rate_limit("user_b")
