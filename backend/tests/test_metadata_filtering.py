import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import ValidationError

from backend.models.schemas import SearchRequest
from backend.services.search_service import hybrid_search, _build_metadata_filters

def test_search_request_trimming_and_normalization():
    """Verify that SearchRequest trims whitespace, discards empty tags/types, and normalizes empty lists to None."""
    # Test valid dates
    now = datetime.now(timezone.utc)
    req = SearchRequest(
        query="test",
        source_types=["", "  pdf  ", "text", "   "],
        tags=["   ", "  ai  ", "", "db"],
        start_date=now,
        end_date=now + timedelta(days=1)
    )
    assert req.source_types == ["pdf", "text"]
    assert req.tags == ["ai", "db"]
    
    # Test empty list normalization
    req_empty = SearchRequest(
        query="test",
        source_types=["   ", ""],
        tags=[""]
    )
    assert req_empty.source_types is None
    assert req_empty.tags is None

def test_search_request_date_ordering_validation():
    """Verify that start_date > end_date raises a validation error (422 Unprocessable Entity)."""
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError) as excinfo:
        SearchRequest(
            query="test",
            start_date=now + timedelta(days=1),
            end_date=now
        )
    assert "start_date must be less than or equal to end_date" in str(excinfo.value)

def test_build_metadata_filters_helper():
    """Verify that _build_metadata_filters builds clean SQL conditions and normalizes dates to UTC."""
    now = datetime.now(timezone.utc)
    conds, params = _build_metadata_filters(
        alias="i",
        source_types=["pdf"],
        tags=["ai"],
        start_date=now,
        end_date=now + timedelta(days=1)
    )
    assert len(conds) == 4
    assert conds[0] == "i.source_type = ANY(%s)"
    assert conds[1] == "i.tags && %s"
    assert conds[2] == "i.created_at >= %s"
    assert conds[3] == "i.created_at <= %s"
    assert params[0] == ["pdf"]
    assert params[1] == ["ai"]
    assert params[2] == now.astimezone(timezone.utc)

@pytest.mark.anyio
async def test_hybrid_search_equivalence_without_filters():
    """Verify that hybrid_search with no filters doesn't change query structure or parameters compared to baseline."""
    mock_cursor = MagicMock()
    mock_cursor.execute = AsyncMock()
    mock_cursor.fetchall = AsyncMock(return_value=[])
    mock_db = MagicMock()
    mock_db.cursor = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_cursor)))

    with patch("backend.services.search_service.embed_text", new=AsyncMock(return_value=[0.1]*384)):
        # Run with no filters
        results = await hybrid_search("query text", 42, mock_db)
        assert results == []
        
        # Verify the executed query contains no metadata filter clauses
        executed_args = mock_cursor.execute.call_args[0]
        query_sql = executed_args[0]
        params = executed_args[1]
        
        # SQL should contain base clauses but no filter templates
        assert "source_type = ANY" not in query_sql
        assert "tags &&" not in query_sql
        assert "created_at >=" not in query_sql
        
        # Confirm default baseline parameter count (17 placeholders: 5 direct, 4 chunk, 1 combined, 4 text, 3 best, 2 final)
        assert len(params) == 20

@pytest.mark.anyio
async def test_hybrid_search_parameter_ordering_combinatorics():
    """Verify that hybrid_search handles different combinations of active filters correctly without parameter drift."""
    now = datetime.now(timezone.utc)
    
    # Filter combinations to test
    combinations = [
        # (source_types, tags, start_date, end_date, expected_filters_count)
        (["pdf"], None, None, None, 1),
        (None, ["ai"], None, None, 1),
        (None, None, now, now + timedelta(days=1), 2),
        (["pdf", "text"], ["ai"], None, None, 2),
        (None, ["ai"], now, None, 2),
        (["pdf"], ["ai"], now, now + timedelta(days=1), 4)
    ]
    
    for source_types, tags, start_date, end_date, expected_count in combinations:
        mock_cursor = MagicMock()
        mock_cursor.execute = AsyncMock()
        mock_cursor.fetchall = AsyncMock(return_value=[])
        mock_db = MagicMock()
        mock_db.cursor = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_cursor)))

        with patch("backend.services.search_service.embed_text", new=AsyncMock(return_value=[0.1]*384)):
            await hybrid_search(
                query="query",
                user_id=42,
                db=mock_db,
                source_types=source_types,
                tags=tags,
                start_date=start_date,
                end_date=end_date
            )
            
            # Extract arguments executed on the cursor
            executed_args = mock_cursor.execute.call_args[0]
            query_sql = executed_args[0]
            params = executed_args[1]
            
            # Verify placeholders and parameter alignment
            if source_types:
                assert "i.source_type = ANY(%s)" in query_sql
            if tags:
                assert "i.tags && %s" in query_sql
            if start_date:
                assert "i.created_at >= %s" in query_sql
            if end_date:
                assert "i.created_at <= %s" in query_sql

            # Direct check that the parameters array length matches placeholders in the query
            placeholders_count = query_sql.count("%s")
            assert len(params) == placeholders_count

@pytest.mark.anyio
async def test_empty_results_bypasses_reranker():
    """Verify that if database returns 0 RRF candidate matches, hybrid_search skips reranking and returns [] immediately."""
    mock_cursor = MagicMock()
    mock_cursor.execute = AsyncMock()
    mock_cursor.fetchall = AsyncMock(return_value=[])
    mock_db = MagicMock()
    mock_db.cursor = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_cursor)))

    # Track if reranker is called
    reranker_called = False
    
    def mock_rerank(query, results):
        nonlocal reranker_called
        reranker_called = True
        return results

    with patch("backend.services.search_service.embed_text", new=AsyncMock(return_value=[0.1]*384)), \
         patch("backend.services.reranker.reranker_service.rerank", side_effect=mock_rerank), \
         patch("backend.services.search_service.settings.ENABLE_RERANKING", True):
         
        results = await hybrid_search("query", 42, mock_db)
        assert results == []
        # Reranker should NOT have been called since database returned 0 rows
        assert not reranker_called
