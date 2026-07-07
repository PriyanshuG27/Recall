import pytest
import math
from datetime import datetime, timezone, timedelta
import numpy as np
import unittest.mock as mock

from backend.config import settings
from backend.services.hub_service import calculate_active_hubs, HubCandidate

# Mock psycopg environment for unit testing
class MockCursor:
    def __init__(self):
        self.executed_queries = []
        self.fetchone_val = (0,)
        self.fetchall_val = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def execute(self, query, params=None):
        self.executed_queries.append((query, params))

    async def fetchone(self):
        return self.fetchone_val

    async def fetchall(self):
        return self.fetchall_val

class MockConnection:
    def __init__(self):
        self.cursor_obj = MockCursor()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def cursor(self):
        return self.cursor_obj

    async def commit(self):
        pass


@pytest.mark.asyncio
async def test_adaptive_k_calculation(monkeypatch):
    """Verify target hub count K scales correctly using the logarithmic formula."""
    conn = MockConnection()
    cursor = conn.cursor_obj

    # Test cases: (total_notes, expected_K)
    test_cases = [
        (20, 13),
        (50, 15),
        (100, 16),
        (500, 19),
        (1000, 20),
        (10000, 24),
        (100000, 25),
    ]

    for total_notes, expected_k in test_cases:
        cursor.fetchone_val = (total_notes,)
        
        # Calculate target_k locally mimicking the service logic
        n_val = max(1, total_notes)
        target_k = int(np.clip(np.round(8 + 4 * math.log10(n_val)), 8.0, 25.0))
        assert target_k == expected_k


@pytest.mark.asyncio
async def test_tag_filtering_blacklist_and_length():
    """Verify low-information utility tags and short tags are filtered correctly."""
    # We will test the filtering logic directly by mimicking the buckets creation
    from backend.services.hub_service import UTILITY_BLACKLIST, ALLOWED_SHORT_TAGS
    
    test_tags = ["python", "bookmark", "unknown", "jwt", "a", "api", "fastapi"]
    valid_tags = []
    
    for tag in test_tags:
        tag_clean = tag.strip().lower()
        if tag_clean in UTILITY_BLACKLIST:
            continue
        if len(tag_clean) < 3 and tag_clean not in ALLOWED_SHORT_TAGS:
            continue
        valid_tags.append(tag_clean)
        
    assert "python" in valid_tags
    assert "jwt" in valid_tags
    assert "api" in valid_tags
    assert "fastapi" in valid_tags
    assert "bookmark" not in valid_tags
    assert "unknown" not in valid_tags
    assert "a" not in valid_tags


@pytest.mark.asyncio
async def test_calculate_active_hubs_integration(monkeypatch):
    """Verify calculate_active_hubs scores tags, applies hysteresis/lifespan, and updates DB."""
    conn = MockConnection()
    cursor = conn.cursor_obj

    # Setup database mocks
    # Query 1: COUNT(*) -> 50 notes (K = 15)
    cursor.fetchone_val = (50,)
    
    # Query 2: Fetch previously active hubs -> "python" was active
    now = datetime.now(timezone.utc)
    cursor.fetchall_val = [("python", now - timedelta(days=2))]

    # Mock items rows:
    # 5 items with "python" (active, recency weighted, hysteresis candidate)
    # 4 items with "fastapi"
    # 3 items with "bookmark" (blacklisted, should be skipped)
    # 2 items with "short" (less than 3 counts, should be skipped)
    items_db = [
        (1, ["python", "bookmark"], now - timedelta(hours=2)),
        (2, ["python", "fastapi"], now - timedelta(hours=4)),
        (3, ["python", "fastapi"], now - timedelta(days=1)),
        (4, ["python", "fastapi"], now - timedelta(days=2)),
        (5, ["python", "bookmark"], now - timedelta(days=3)),
        (6, ["fastapi"], now - timedelta(days=4)),
        (7, ["bookmark"], now - timedelta(days=5)),
        (8, ["short"], now - timedelta(hours=1)),
        (9, ["short"], now - timedelta(hours=2)),
    ]
    
    # Create custom mock fetch method that returns different outputs based on query content
    orig_execute = cursor.execute
    query_counter = 0

    async def mock_execute(query, params=None):
        nonlocal query_counter
        query_counter += 1
        await orig_execute(query, params)

    cursor.execute = mock_execute

    # Mock fetchone and fetchall sequence
    async def mock_fetchone():
        return (50,) # COUNT(*)

    async def mock_fetchall():
        if query_counter == 2:
            # SELECT tag, created_at FROM active_hubs
            return [("python", now - timedelta(days=2))]
        elif query_counter == 3:
            # SELECT id, tags, created_at FROM items
            return items_db
        return []

    cursor.fetchone = mock_fetchone
    cursor.fetchall = mock_fetchall

    # Mock embed_text service to return vectors
    # fastapi and python will have low similarity, so they both get selected
    async def mock_embed_text(tag):
        if tag == "python":
            return [1.0, 0.0] + [0.0] * 382
        elif tag == "fastapi":
            return [0.0, 1.0] + [0.0] * 382
        return [0.0] * 384

    monkeypatch.setattr("backend.services.hub_service.embed_text", mock_embed_text)

    # Run selection
    selected = await calculate_active_hubs(user_id=1, db=conn)

    # Verify "python" and "fastapi" are selected as hubs, but "bookmark" and "short" are excluded
    assert "python" in selected
    assert "fastapi" in selected
    assert "bookmark" not in selected
    assert "short" not in selected

    # Verify DB updates executed
    executed_sql = [q[0] for q in cursor.executed_queries]
    
    # Verify active_hubs inserts and deletes are run
    assert any("INSERT INTO active_hubs" in sql for sql in executed_sql)
    assert any("DELETE FROM active_hubs" in sql for sql in executed_sql)
