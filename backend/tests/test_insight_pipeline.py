import pytest
import unittest.mock as mock
import time

class MockRedis:
    def __init__(self):
        self.store = {}
        self.zset = {}

    async def get(self, key):
        return self.store.get(key)

    async def setex(self, key, seconds, value):
        self.store[key] = str(value)
        return True

    async def delete(self, key):
        if key in self.store:
            del self.store[key]
            return 1
        return 0

    async def zadd(self, key, score, member):
        if key not in self.zset:
            self.zset[key] = {}
        self.zset[key][member] = float(score)
        return 1

    async def zrem(self, key, member):
        if key in self.zset and member in self.zset[key]:
            del self.zset[key][member]
            return 1
        return 0

    async def zrangebyscore(self, key, min_score, max_score):
        if key not in self.zset:
            return []
        min_s = float("-inf") if min_score == "-inf" else float(min_score)
        max_s = float("+inf") if max_score == "+inf" else float(max_score)
        res = []
        for member, score in self.zset[key].items():
            if min_s <= score <= max_s:
                res.append(member)
        return res

    async def _request(self, path, payload):
        command = payload[0].upper()
        if command == "LRANGE":
            key = payload[1]
            return {"result": [x for x in self.store.get(key, [])]}
        elif command == "LPUSH":
            key = payload[1]
            val = payload[2]
            if key not in self.store:
                self.store[key] = []
            self.store[key].insert(0, val)
            return {"result": len(self.store[key])}
        elif command == "LTRIM":
            key = payload[1]
            start = int(payload[2])
            stop = int(payload[3])
            if key in self.store:
                self.store[key] = self.store[key][start:stop+1]
            return {"result": "OK"}
        elif command == "HGETALL":
            key = payload[1]
            res = []
            for k, v in self.store.get(key, {}).items():
                res.extend([k, str(v)])
            return {"result": res}
        elif command == "HSET":
            key = payload[1]
            field = payload[2]
            val = payload[3]
            if key not in self.store:
                self.store[key] = {}
            self.store[key][field] = val
            return {"result": 1}
        elif command == "HINCRBY":
            key = payload[1]
            field = payload[2]
            inc = int(payload[3])
            if key not in self.store:
                self.store[key] = {}
            curr = int(self.store[key].get(field, 0))
            new_val = curr + inc
            self.store[key][field] = new_val
            return {"result": new_val}
        elif command == "INCR":
            key = payload[1]
            curr = int(self.store.get(key, 0))
            new_val = curr + 1
            self.store[key] = str(new_val)
            return {"result": new_val}
        elif command == "HGET":
            key = payload[1]
            field = payload[2]
            val = self.store.get(key, {}).get(field)
            return {"result": val}
        return {"result": None}

# Instantiate and patch global redis client before importing scheduler
from backend.services.redis_client import redis
mock_redis_inst = MockRedis()

@pytest.fixture(autouse=True)
def setup_redis():
    # Backup original methods
    orig_get = redis.get
    orig_setex = redis.setex
    orig_delete = redis.delete
    orig_zadd = redis.zadd
    orig_zrem = redis.zrem
    orig_zrangebyscore = redis.zrangebyscore
    orig_request = redis._request

    redis.get = mock_redis_inst.get
    redis.setex = mock_redis_inst.setex
    redis.delete = mock_redis_inst.delete
    redis.zadd = mock_redis_inst.zadd
    redis.zrem = mock_redis_inst.zrem
    redis.zrangebyscore = mock_redis_inst.zrangebyscore
    redis._request = mock_redis_inst._request
    yield

    # Restore original methods
    redis.get = orig_get
    redis.setex = orig_setex
    redis.delete = orig_delete
    redis.zadd = orig_zadd
    redis.zrem = orig_zrem
    redis.zrangebyscore = orig_zrangebyscore
    redis._request = orig_request

# Now import scheduler modules safely
from backend.scheduler.scheduler import (
    scan_insight_candidates_for_user,
    daily_digest_sender,
    reminders_dispatcher
)

class MockCursor:
    def __init__(self, fetchall_data=None, fetchone_data=None):
        self.executed = []
        self.fetchall_data = fetchall_data or []
        self.fetchone_data = fetchone_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def execute(self, query, params=None):
        self.executed.append((query, params))

    async def fetchall(self):
        return self.fetchall_data

    async def fetchone(self):
        return self.fetchone_data


class MockConnection:
    def __init__(self, cursor_inst):
        self.cursor_inst = cursor_inst

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def cursor(self):
        return self.cursor_inst

    async def execute(self, query, params=None):
        pass

    async def commit(self):
        pass

    async def rollback(self):
        pass


@pytest.mark.asyncio
async def test_scan_insight_candidates_success():
    """Verify that scan_insight_candidates_for_user finds cross-cluster candidate pairs and inserts them."""
    user_id = 123
    
    cursor = MockCursor(
        fetchall_data=[(10, 20, 0.78)]
    )
    hubs_data = [(1, [10]), (2, [20])]
    
    execute_calls = []
    async def custom_execute(query, params=None):
        execute_calls.append((query, params))
        if "semantic_hubs" in query:
            cursor.fetchall_data = hubs_data
        elif "insight_candidates" in query:
            cursor.fetchone_data = None
            
    cursor.execute = custom_execute
    
    conn = MockConnection(cursor)
    mock_pool = mock.MagicMock()
    mock_pool.connection = mock.MagicMock(return_value=conn)
    
    await scan_insight_candidates_for_user(user_id, mock_pool)
    
    inserted = False
    for query, params in execute_calls:
        if "INSERT INTO insight_candidates" in query:
            inserted = True
            assert params[0] == user_id
            assert params[1] == 10
            assert params[2] == 20
            assert params[3] == 0.78
            assert params[4] == "confirmed"
    assert inserted


@pytest.mark.asyncio
async def test_morning_mystery_trigger():
    user_id = 234
    chat_id = "7732257445"
    
    # Reset mock redis store
    mock_redis_inst.store.clear()
    mock_redis_inst.zset.clear()

    users_row = [(user_id, chat_id, 3, 8)]
    execute_calls = []
    
    async def custom_execute(query, params=None):
        execute_calls.append((query, params))
        if "FROM users" in query:
            cursor.fetchall_data = users_row
        elif "COUNT(*)" in query and "items" in query:
            cursor.fetchone_data = (1,)
        elif "title" in query and "items" in query:
            cursor.fetchall_data = [("Title 1",)]
        elif "COUNT(*)" in query and "quizzes" in query:
            cursor.fetchone_data = (2,)
        elif "insight_candidates" in query:
            cursor.fetchone_data = (45, 10, 20)
            cursor.fetchall_data = [(45, 10, 20)]

    cursor = MockCursor()
    cursor.execute = custom_execute
    conn = MockConnection(cursor)
    mock_pool = mock.MagicMock()
    mock_pool.connection = mock.MagicMock(return_value=conn)
    
    with mock.patch("backend.scheduler.scheduler.get_pool", return_value=mock_pool):
        with mock.patch("backend.scheduler.scheduler.send_telegram_message", mock.AsyncMock()) as mock_tg:
            await daily_digest_sender()
            
            assert mock_tg.call_count == 2
            assert "daily digest" in mock_tg.call_args_list[0][0][1]
            assert "collapsed into the same idea" in mock_tg.call_args_list[1][0][1]
            
            expiry_val = await mock_redis_inst.zrangebyscore("reminders:active", "-inf", "+inf")
            assert "drift:45" in expiry_val


@pytest.mark.asyncio
async def test_evening_answer_trigger():
    user_id = 345
    chat_id = "888999"
    
    # Reset mock redis store
    mock_redis_inst.store.clear()
    mock_redis_inst.zset.clear()

    users_row = [(user_id, chat_id, 4, 20)]
    execute_calls = []
    
    async def custom_execute(query, params=None):
        execute_calls.append((query, params))
        if "FROM users" in query:
            cursor.fetchall_data = users_row
        elif "insight_candidates" in query:
            cursor.fetchone_data = (45, 10, 20, "Title A", "Summary A", ["tagA"], "Title B", "Summary B", ["tagB"])
            cursor.fetchall_data = [(45, 10, 20, "Title A", "Summary A", ["tagA"], "Title B", "Summary B", ["tagB"])]

    cursor = MockCursor()
    cursor.execute = custom_execute
    conn = MockConnection(cursor)
    mock_pool = mock.MagicMock()
    mock_pool.connection = mock.MagicMock(return_value=conn)
    
    mock_cascade_inst = mock.AsyncMock()
    mock_cascade_inst.generate_insight = mock.AsyncMock(return_value="Connection: both talks focus on React rendering pipelines.")
    
    with mock.patch("backend.scheduler.scheduler.get_pool", return_value=mock_pool):
        with mock.patch("backend.scheduler.scheduler.send_telegram_message", mock.AsyncMock()) as mock_tg:
            with mock.patch("backend.services.ai_cascade.AICascade", return_value=mock_cascade_inst):
                await mock_redis_inst.zadd("reminders:active", float(time.time() + 3600), "drift:45")
                
                await daily_digest_sender()
                
                assert mock_tg.call_count == 1
                assert "React rendering pipelines" in mock_tg.call_args_list[0][0][1]
                
                expiry_val = await mock_redis_inst.zrangebyscore("reminders:active", "-inf", "+inf")
                assert "drift:45" not in expiry_val


@pytest.mark.asyncio
async def test_reminders_dispatcher_drift_expiry():
    # Reset mock redis store
    mock_redis_inst.store.clear()
    mock_redis_inst.zset.clear()

    await mock_redis_inst.zadd("reminders:active", float(time.time() - 100), "drift:45")
    
    cursor = MockCursor()
    conn = MockConnection(cursor)
    mock_pool = mock.MagicMock()
    mock_pool.connection = mock.MagicMock(return_value=conn)
    
    with mock.patch("backend.scheduler.scheduler.get_pool", return_value=mock_pool):
        await reminders_dispatcher()
        
        updated = False
        for query, params in cursor.executed:
            if "UPDATE insight_candidates" in query:
                updated = True
                assert params[0] == [45]
        assert updated
        
        expiry_val = await mock_redis_inst.zrangebyscore("reminders:active", "-inf", "+inf")
        assert "drift:45" not in expiry_val
