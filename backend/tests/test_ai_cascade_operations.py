import asyncio
import pytest
import unittest.mock as mock
import json
from contextlib import asynccontextmanager
from fastapi.testclient import TestClient

from backend.main import app
from backend.middleware.twa_auth import UserContext, get_current_user
from backend.db.connection import get_db
from backend.services.ai_cascade.persistence.manager import persistence_manager
from backend.services.ai_cascade.models import SummaryResult, ExecutionContext

# ------------------------------------------------------------------------------
# Mock rate limiting and DB pool globally for all metrics tests
# ------------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def mock_metrics_rate_limit():
    """Mock metrics route rate limiter so tests don't try to query Upstash Redis."""
    with mock.patch("backend.routes.metrics.rate_limit", return_value=lambda *args, **kwargs: None):
        yield


@pytest.fixture(autouse=True)
def mock_global_db():
    """Mock database pool checkout globally to prevent 503 Service Unavailable errors on unauthenticated routes."""
    conn = mock.Mock()
    cursor = mock.AsyncMock()
    
    @asynccontextmanager
    async def mock_cursor_context():
        yield cursor
        
    conn.cursor = mock_cursor_context
    
    async def override_get_db():
        yield conn
        
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


# ------------------------------------------------------------------------------
# 1. Unit Tests for Persistence Logging
# ------------------------------------------------------------------------------

@pytest.mark.anyio
async def test_persistence_manager_logs_to_db():
    """Verify that PersistenceManager asynchronously logs detailed AI routing decisions to PostgreSQL."""
    mock_pool = mock.Mock()
    mock_conn = mock.AsyncMock()
    
    @asynccontextmanager
    async def mock_conn_context():
        yield mock_conn
        
    mock_pool.connection = mock_conn_context

    # Setup the execution context with custom attempts
    ctx = ExecutionContext(execution_id="exec-12345", request_id="req-99999")
    ctx.attempts.append({
        "provider": "gemini",
        "model": "gemini-3.1-flash-lite",
        "latency_ms": 320.5,
        "status": "succeeded",
        "error": ""
    })

    res = SummaryResult(
        provider_used="gemini",
        model_used="gemini-3.1-flash-lite",
        summary="This is a fully verified test summary of key points.",
        tags=["unit", "test"],
        key_points=["Point 1", "Point 2"],
        context_prompt="What did you think of the test?",
        metadata={"raw_response": '{"summary": "Test"}', "execution_id": "exec-12345"}
    )

    with mock.patch("backend.db.connection._pool", mock_pool):
        persistence_manager.save_result(
            res,
            cache_hit=False,
            user_id=1337,
            execution_context=ctx
        )

        await asyncio.sleep(0.05)

        assert mock_conn.execute.call_count == 1
        
        query, params = mock_conn.execute.call_args[0]
        assert "INSERT INTO ai_decision_logs" in query
        assert params[0] == 1337  # user_id
        assert params[1] == "req-99999"  # request_id
        assert params[2] == "exec-12345"  # execution_id
        assert params[5] == "gemini"  # provider_used
        assert params[6] == "gemini-3.1-flash-lite"  # model_used
        assert params[7] is True  # success

        attempts_logged = json.loads(params[8])
        assert len(attempts_logged) == 1
        assert attempts_logged[0]["provider"] == "gemini"
        assert attempts_logged[0]["latency_ms"] == 320.5

        final_output = json.loads(params[9])
        assert final_output["summary"] == "This is a fully verified test summary of key points."


@pytest.mark.anyio
async def test_persistence_manager_logs_fail_open():
    """Verify that database pool failures during logging don't raise exceptions or block application execution."""
    mock_pool = mock.Mock()
    
    @asynccontextmanager
    async def mock_conn_context_fail():
        raise Exception("Neon Database is temporarily down.")
        yield
        
    mock_pool.connection = mock_conn_context_fail

    ctx = ExecutionContext()
    res = SummaryResult(
        provider_used="groq",
        model_used="openai/gpt-oss-120b",
        summary="Test summary",
        tags=[],
        key_points=[],
        context_prompt="",
        metadata={}
    )

    with mock.patch("backend.db.connection._pool", mock_pool):
        persistence_manager.save_result(
            res,
            cache_hit=False,
            user_id=999,
            execution_context=ctx
        )
        await asyncio.sleep(0.05)


# ------------------------------------------------------------------------------
# 2. FastAPI Integration Tests for Metrics API Endpoints
# ------------------------------------------------------------------------------

@pytest.fixture
def auth_client():
    """FastAPI TestClient with overridden active user authentication dependency."""
    async def override_get_current_user():
        return UserContext(id=42, telegram_chat_id="12345")
        
    app.dependency_overrides[get_current_user] = override_get_current_user
    # Yield client directly without context manager to avoid lifespan hooks
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def mock_db_conn():
    """Mock connection context dependency returning mock cursor datasets."""
    conn = mock.Mock()
    cursor = mock.AsyncMock()
    
    @asynccontextmanager
    async def mock_cursor_context():
        yield cursor
        
    conn.cursor = mock_cursor_context

    # Mock fetchone for cost query, fetchall for decision logs query
    cursor.fetchone.return_value = (100, 50, 150, 0.0035)
    cursor.fetchall.return_value = [
        ([{"provider": "gemini", "model": "gemini-3.1-flash-lite", "latency_ms": 250.0, "status": "succeeded"}], True),
        ([{"provider": "groq", "model": "openai/gpt-oss-120b", "latency_ms": 120.0, "status": "failed"}], False)
    ]

    async def override_get_db():
        yield conn

    app.dependency_overrides[get_db] = override_get_db
    yield conn
    app.dependency_overrides.pop(get_db, None)


def test_metrics_ai_unauthenticated():
    """Verify that accessing metrics endpoints without auth results in 401 Unauthorized."""
    c = TestClient(app)
    response = c.get("/api/metrics/ai")
    assert response.status_code == 401


def test_metrics_ai_success(auth_client, mock_db_conn):
    """Verify that authenticated /api/metrics/ai retrieves aggregated database metrics."""
    response = auth_client.get("/api/metrics/ai?hours=48")
    assert response.status_code == 200
    
    data = response.json()
    assert data["window_hours"] == 48
    assert data["summary"]["total_calls"] == 2
    assert data["summary"]["success_calls"] == 1
    assert data["costs"]["total_tokens"] == 150
    assert data["costs"]["total_cost_usd"] == 0.0035

    # Check provider breakdown calculations
    gemini_stats = data["provider_breakdown"]["gemini:gemini-3.1-flash-lite"]
    assert gemini_stats["total_calls"] == 1
    assert gemini_stats["avg_latency_ms"] == 250.0

    groq_stats = data["provider_breakdown"]["groq:openai/gpt-oss-120b"]
    assert groq_stats["total_calls"] == 1
    assert groq_stats["failure_rate"] == 1.0


@pytest.mark.anyio
async def test_metrics_health_success(auth_client):
    """Verify that /api/metrics/health endpoint fetches provider circuit status from Redis."""
    async def mock_redis_get(key: str):
        if "consecutive_failures" in key:
            return "3"
        if "cooldown" in key:
            return "active-cooldown"
        return None

    with mock.patch("backend.routes.metrics.redis.get", mock_redis_get):
        response = auth_client.get("/api/metrics/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "ok"
        providers = data["providers"]
        
        # Verify mocked circuit statuses mapping
        assert providers["groq"]["status"] == "unhealthy"
        assert providers["groq"]["consecutive_failures"] == 3
        assert providers["groq"]["in_cooldown"] is True


# ------------------------------------------------------------------------------
# 3. Unit Tests for Feature Flags & Observability
# ------------------------------------------------------------------------------

@pytest.mark.anyio
async def test_feature_flag_cache_bypass():
    """Verify that setting ENABLE_CACHE=false bypasses cache lookups in LegacyAdapter."""
    from backend.services.ai_cascade.legacy import legacy_adapter
    from backend.services.ai_cascade.shared.exceptions import ProviderError
    
    mock_cache = mock.AsyncMock()
    mock_engine = mock.AsyncMock()
    
    # We patch settings.enable_cache to return False
    with mock.patch("backend.services.ai_cascade.config.settings.CascadeSettings.enable_cache", new_callable=mock.PropertyMock, return_value=False), \
         mock.patch("backend.services.ai_cascade.legacy.adapter.cache_manager", mock_cache), \
         mock.patch("backend.services.ai_cascade.legacy.adapter.legacy_adapter.engine", mock_engine):
         
         # Mock execute_plan to raise ProviderError to stop early or return success
         mock_engine.execute_plan.side_effect = ProviderError("Planned stop")
         
         with pytest.raises(ProviderError):
             await legacy_adapter.execute_summary_pipeline("This is a simple transcript.")
             
         # Verify cache lookup was bypassed
         assert mock_cache.get_llm_response.call_count == 0


def test_feature_flag_repair_bypass():
    """Verify that setting ENABLE_REPAIR=false disables JSON repair and immediately raises validation error on dirty JSON."""
    from backend.services.ai_cascade.validators import ValidatorRegistry
    from backend.services.ai_cascade.shared.exceptions import OutputValidationError
    
    validator = ValidatorRegistry.get_validator("summary")
    dirty_json = "Some explanation: \n```json\n{\n  \"summary\": \"Direct JSON output\"\n}\n```"

    # We patch settings.enable_repair to return False
    with mock.patch("backend.services.ai_cascade.config.settings.CascadeSettings.enable_repair", new_callable=mock.PropertyMock, return_value=False):
        # With repair disabled, parse_json should immediately fail since dirty_json is not direct raw JSON
        with pytest.raises(OutputValidationError) as exc_info:
            validator.parse_json(dirty_json)
        assert "repair disabled" in str(exc_info.value)

