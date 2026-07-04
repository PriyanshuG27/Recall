import pytest
import asyncio
from unittest import mock
from freezegun import freeze_time
from backend.services.rate_limiter import check_rate_limit, RateLimitExceeded

class MockRedisRateLimit:
    def __init__(self):
        # Maps key -> list of (timestamp_ms, member_id)
        self.state = {}
        self.lock = asyncio.Lock()

    async def eval(self, script, numkeys, *args):
        async with self.lock:
            key = args[0]
            now = int(args[1])
            window_start = int(args[2])
            member_id = args[3]
            expire_seconds = int(args[4])
            limit = int(args[5])

            if key not in self.state:
                self.state[key] = []

            # 1. ZREMRANGEBYSCORE key 0 window_start
            self.state[key] = [item for item in self.state[key] if item[0] > window_start]

            # 2. ZADD key now member_id
            self.state[key].append((now, member_id))
            # Sort by score (timestamp)
            self.state[key].sort(key=lambda x: x[0])

            # 3. ZCARD key
            count = len(self.state[key])

            # 4. Find oldest member
            oldest = ""
            if count > 0:
                oldest = self.state[key][0][1]

            return [count, oldest]

@pytest.mark.asyncio
async def test_concurrent_burst_rate_limiting():
    db_state = MockRedisRateLimit()
    with mock.patch("backend.services.redis_client.redis.eval", side_effect=db_state.eval):
        chat_id = 999111
        # 20 concurrent requests
        tasks = [check_rate_limit(chat_id) for _ in range(20)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert all(r is True for r in results)

@pytest.mark.asyncio
async def test_rate_limit_overflow_exactly_5_rejected():
    db_state = MockRedisRateLimit()
    with mock.patch("backend.services.redis_client.redis.eval", side_effect=db_state.eval):
        chat_id = 999222
        # 25 concurrent requests
        tasks = [check_rate_limit(chat_id) for _ in range(25)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successes = [r for r in results if r is True]
        rejections = [r for r in results if isinstance(r, RateLimitExceeded)]
        
        assert len(successes) == 20
        assert len(rejections) == 5

@pytest.mark.asyncio
async def test_multi_user_isolation():
    db_state = MockRedisRateLimit()
    with mock.patch("backend.services.redis_client.redis.eval", side_effect=db_state.eval):
        chat_id_a = 999333
        chat_id_b = 999444
        
        # 25 concurrent requests for user A, 25 for user B
        tasks_a = [check_rate_limit(chat_id_a) for _ in range(25)]
        tasks_b = [check_rate_limit(chat_id_b) for _ in range(25)]
        
        results_a = await asyncio.gather(*tasks_a, return_exceptions=True)
        results_b = await asyncio.gather(*tasks_b, return_exceptions=True)
        
        successes_a = [r for r in results_a if r is True]
        rejections_a = [r for r in results_a if isinstance(r, RateLimitExceeded)]
        
        successes_b = [r for r in results_b if r is True]
        rejections_b = [r for r in results_b if isinstance(r, RateLimitExceeded)]
        
        assert len(successes_a) == 20
        assert len(rejections_a) == 5
        assert len(successes_b) == 20
        assert len(rejections_b) == 5

@pytest.mark.asyncio
async def test_sliding_window_expiry():
    db_state = MockRedisRateLimit()
    with mock.patch("backend.services.redis_client.redis.eval", side_effect=db_state.eval):
        chat_id = 999555
        
        with freeze_time("2026-07-04 12:00:00") as frozen_time:
            # First window: 20 requests
            tasks1 = [check_rate_limit(chat_id) for _ in range(20)]
            results1 = await asyncio.gather(*tasks1, return_exceptions=True)
            assert all(r is True for r in results1)
            
            # 21st request should fail
            with pytest.raises(RateLimitExceeded):
                await check_rate_limit(chat_id)
                
            # Tick time forward by 61 seconds
            frozen_time.tick(61)
            
            # Second window: 20 requests should pass
            tasks2 = [check_rate_limit(chat_id) for _ in range(20)]
            results2 = await asyncio.gather(*tasks2, return_exceptions=True)
            assert all(r is True for r in results2)
