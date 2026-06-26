import pytest
import unittest.mock as mock
import numpy as np
import networkx as nx

from backend.scheduler.scheduler import louvain_clustering

VALID_ENV = {
    "TELEGRAM_BOT_TOKEN": "1234567890:ABCdefGHIjklmnoPQRstuvwxyZ123456789",
    "DATABASE_URL": "postgresql://user:pass@localhost:5432/db?sslmode=require",
    "UPSTASH_REDIS_REST_URL": "https://dev-recall-redis.upstash.io",
    "UPSTASH_REDIS_REST_TOKEN": "dev_upstash_redis_token",
    "FERNET_KEY": "yF4P-W965hF17Bq_Q7g_oG5l8S631P9_9z-d8v7d8sA=",
    "JWT_SECRET": "8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7b",
    "WEBSITE_URL": "http://localhost:5173",
    "ENV": "test",
}


@pytest.fixture(autouse=True)
def patch_env(monkeypatch):
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)


class MockCursor:
    def __init__(self, item_rows=None):
        self.executed = []
        # Return 8 items (so we can partition them into two clusters of 3 and one of 2)
        self.item_rows = item_rows or [
            (1, str([0.1] * 384), "Summary 1"),
            (2, str([0.2] * 384), "Summary 2"),
            (3, str([0.3] * 384), "Summary 3"),
            (4, str([0.4] * 384), "Summary 4"),
            (5, str([0.5] * 384), "Summary 5"),
            (6, str([0.6] * 384), "Summary 6"),
            (7, str([0.7] * 384), "Summary 7"),
            (8, str([0.8] * 384), "Summary 8"),
        ]

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def execute(self, query, params=None):
        self.executed.append((query, params))

    async def fetchall(self):
        last_query = self.executed[-1][0].lower() if self.executed else ""
        if "users" in last_query:
            return [(42,)]
        if "items" in last_query:
            return self.item_rows
        return []

    async def fetchone(self):
        last_query = self.executed[-1][0].lower() if self.executed else ""
        if "insert into semantic_hubs" in last_query:
            inserts = [x for x in self.executed if "insert into semantic_hubs" in x[0].lower()]
            return (len(inserts),)
        return None


class MockConnection:
    def __init__(self, cursor_inst):
        self.cursor_inst = cursor_inst

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def cursor(self):
        return self.cursor_inst

    async def commit(self):
        pass


@pytest.mark.asyncio
async def test_louvain_clustering_success():
    # 1. Setup DB mocks
    cursor = MockCursor()
    conn = MockConnection(cursor)

    mock_pool = mock.MagicMock()
    mock_pool.connection = mock.MagicMock(return_value=conn)

    # 2. Mock AI Cascade to return a mock theme name
    mock_ai_cascade = mock.AsyncMock()
    mock_ai_cascade.summarise = mock.AsyncMock(return_value="Machine Learning Artificial Intelligence")

    # 3. Mock Redis cache and WS manager
    mock_redis = mock.AsyncMock()
    mock_redis.delete = mock.AsyncMock(return_value=1)
    
    mock_ws_manager = mock.AsyncMock()
    mock_ws_manager.send_personal_message = mock.AsyncMock()

    # 4. Mock networkx Graph and best_partition
    # Partition mapping:
    # Items 1, 2, 3 -> Community 0 (size 3: creates hub)
    # Items 4, 5, 6 -> Community 1 (size 3: creates hub)
    # Items 7, 8    -> Community 2 (size 2: ignored because size < 3)
    mock_partition = {1: 0, 2: 0, 3: 0, 4: 1, 5: 1, 6: 1, 7: 2, 8: 2}

    with mock.patch("backend.scheduler.scheduler._pool", mock_pool), \
         mock.patch("backend.scheduler.scheduler.AICascade", return_value=mock_ai_cascade), \
         mock.patch("backend.scheduler.scheduler.redis", mock_redis), \
         mock.patch("backend.routes.websocket.broadcast", new_callable=mock.AsyncMock) as mock_broadcast, \
         mock.patch("backend.scheduler.scheduler.nx.Graph") as mock_graph_cls, \
         mock.patch("backend.scheduler.scheduler.community_louvain.best_partition", return_value=mock_partition):

        # Setup mock graph instance to inspect additions
        mock_graph = mock.MagicMock()
        mock_graph_cls.return_value = mock_graph

        # Trigger Louvain job
        await louvain_clustering()

        # Check graph additions (nodes and edges setup)
        mock_graph.add_nodes_from.assert_called_once()
        
        # Check that we deleted old hubs
        delete_queries = [x for x in cursor.executed if "delete from semantic_hubs" in x[0].lower()]
        assert len(delete_queries) == 1
        assert delete_queries[0][1] == (42,)

        # Check that we inserted new hubs (exactly 2 hubs since community 2 is size 2 < 3)
        insert_queries = [x for x in cursor.executed if "insert into semantic_hubs" in x[0].lower()]
        assert len(insert_queries) == 2

        # Verify hub details: user_id, label, centroid, member_ids
        # Community 0: member_ids = [1, 2, 3]
        # Community 1: member_ids = [4, 5, 6]
        h0_params = insert_queries[0][1]
        h1_params = insert_queries[1][1]
        
        assert h0_params[0] == 42
        assert h0_params[1] == "Machine Learning Artificial Intelligence" # Max 4 words
        assert h0_params[3] == [1, 2, 3]

        assert h1_params[0] == 42
        assert h1_params[1] == "Machine Learning Artificial Intelligence"
        assert h1_params[3] == [4, 5, 6]

        # Verify label truncation if LLM returned > 4 words
        # (Mock label is 4 words, let's do a test with 5 words below)

        # Check Redis invalidation
        mock_redis.delete.assert_called_once_with("graph:42")

        # Check WS broadcast
        mock_broadcast.assert_called_once_with(
            42,
            {
                "type": "hubs_updated",
                "hubs": [
                    {
                        "id": "1",
                        "label": "Machine Learning Artificial Intelligence",
                        "member_ids": [1, 2, 3]
                    },
                    {
                        "id": "2",
                        "label": "Machine Learning Artificial Intelligence",
                        "member_ids": [4, 5, 6]
                    }
                ]
            }
        )


@pytest.mark.asyncio
async def test_louvain_clustering_label_truncation():
    # Setup mocks for 5-word label truncation test
    cursor = MockCursor()
    conn = MockConnection(cursor)

    mock_pool = mock.MagicMock()
    mock_pool.connection = mock.MagicMock(return_value=conn)

    # Return 5-word theme: "A Deep Learning Neural Network"
    mock_ai_cascade = mock.AsyncMock()
    mock_ai_cascade.summarise = mock.AsyncMock(return_value="A Deep Learning Neural Network")

    mock_redis = mock.AsyncMock()
    mock_partition = {1: 0, 2: 0, 3: 0} # Single cluster of size 3

    with mock.patch("backend.scheduler.scheduler._pool", mock_pool), \
         mock.patch("backend.scheduler.scheduler.AICascade", return_value=mock_ai_cascade), \
         mock.patch("backend.scheduler.scheduler.redis", mock_redis), \
         mock.patch("backend.routes.websocket.broadcast", new_callable=mock.AsyncMock), \
         mock.patch("backend.scheduler.scheduler.nx.Graph"), \
         mock.patch("backend.scheduler.scheduler.community_louvain.best_partition", return_value=mock_partition):

        await louvain_clustering()

        # Check that the inserted hub label is truncated to 4 words: "A Deep Learning Neural"
        insert_queries = [x for x in cursor.executed if "insert into semantic_hubs" in x[0].lower()]
        assert len(insert_queries) == 1
        label_param = insert_queries[0][1][1]
        assert label_param == "A Deep Learning Neural"


@pytest.mark.asyncio
async def test_louvain_clustering_skips_user_on_error():
    # Test error resilience: skips user on error without failing overall job
    cursor = MockCursor()
    
    # Mock connection execute to throw an error on the items query
    async def throw_err(query, params=None):
        if "items" in query.lower():
            raise ValueError("Simulated DB query error")
            
    conn = MockConnection(cursor)
    cursor.execute = throw_err

    mock_pool = mock.MagicMock()
    mock_pool.connection = mock.MagicMock(return_value=conn)

    with mock.patch("backend.scheduler.scheduler._pool", mock_pool):
        # Should complete without raising exception
        await louvain_clustering()
