import pytest
from unittest import mock
import psycopg
from backend.services.ai_cascade.telemetry.cost_manager import (
    CostManager,
    cost_tracking_context,
    current_user_id_var,
    current_chat_id_var,
    current_task_var,
    current_request_id_var,
    MODEL_PRICING
)

# ==============================================================================
# UNIT TESTS FOR TOKEN ESTIMATION & COST CALCULATION
# ==============================================================================

def test_estimate_tokens():
    assert CostManager.estimate_tokens(None) == 0
    assert CostManager.estimate_tokens("") == 0
    assert CostManager.estimate_tokens("hello") == 1  # 5 chars / 4 = 1.25 -> 1
    assert CostManager.estimate_tokens("a" * 40) == 10  # 40 chars / 4 = 10

def test_calculate_cost_gemini():
    # Gemini 3.1 Flash Lite pricing: input=$0.075/1M, output=$0.30/1M
    cost = CostManager.calculate_cost(
        provider="gemini",
        model="gemini-3.1-flash-lite",
        prompt_tokens=100_000,
        completion_tokens=200_000
    )
    expected_input = (100_000 / 1_000_000) * 0.075
    expected_output = (200_000 / 1_000_000) * 0.30
    assert cost == round(expected_input + expected_output, 8)

def test_calculate_cost_groq():
    # qwen/qwen3-32b pricing: input=$0.20/1M, output=$0.20/1M
    cost = CostManager.calculate_cost(
        provider="groq",
        model="qwen/qwen3-32b",
        prompt_tokens=500_000,
        completion_tokens=500_000
    )
    expected = (1_000_000 / 1_000_000) * 0.20
    assert cost == round(expected, 8)

def test_calculate_cost_whisper():
    # Whisper pricing: $0.0010 per minute
    cost = CostManager.calculate_cost(
        provider="groq",
        model="whisper-large-v3-turbo",
        duration_seconds=90  # 1.5 minutes
    )
    expected = (90 / 60.0) * 0.0010
    assert cost == round(expected, 8)

def test_calculate_cost_modal():
    # Modal pricing: flat rate
    cost = CostManager.calculate_cost(
        provider="modal",
        model="summary"
    )
    assert cost == MODEL_PRICING["modal-summary"]["flat_cost"]

def test_calculate_cost_fallback():
    # Unknown model should fall back to default (gemini-3.1-flash-lite)
    cost = CostManager.calculate_cost(
        provider="unknown",
        model="nonexistent-model",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000
    )
    expected = (1_000_000 / 1_000_000) * 0.075 + (1_000_000 / 1_000_000) * 0.30
    assert cost == round(expected, 8)


# ==============================================================================
# ASYNC TESTS FOR CONTEXT AND DATABASE LOGGING
# ==============================================================================

@pytest.mark.asyncio
async def test_cost_tracking_context():
    assert current_user_id_var.get() is None
    assert current_chat_id_var.get() is None
    
    async with cost_tracking_context(chat_id="chat123", user_id=42, task="test_task", request_id="req999"):
        assert current_user_id_var.get() == 42
        assert current_chat_id_var.get() == "chat123"
        assert current_task_var.get() == "test_task"
        assert current_request_id_var.get() == "req999"

    # Verify context resets on exit
    assert current_user_id_var.get() is None
    assert current_chat_id_var.get() is None
    assert current_task_var.get() is None
    assert current_request_id_var.get() is None

@pytest.mark.asyncio
async def test_log_usage_with_cursor():
    mock_cursor = mock.AsyncMock(spec=psycopg.AsyncCursor)
    # Mock user ID lookup returns nothing (direct lookup by chat_id)
    mock_cursor.fetchone = mock.AsyncMock(return_value=[123])

    async with cost_tracking_context(chat_id="chat_tele", task="summarise", request_id="req111"):
        cost = await CostManager.log_usage(
            provider="gemini",
            model="gemini-3.1-flash-lite",
            prompt_tokens=10_000,
            completion_tokens=5_000,
            cursor=mock_cursor
        )
        
        # Verify cost was calculated correctly
        assert cost == round((10_000 / 1_000_000) * 0.075 + (5_000 / 1_000_000) * 0.30, 8)
        
        # Verify db lookup for user_id was executed since chat_id was passed in context but no user_id
        mock_cursor.execute.assert_any_call(
            "SELECT id FROM users WHERE telegram_chat_id = %s LIMIT 1;",
            ("chat_tele",)
        )
        
        # Verify db insert was called with the resolved user_id (123) and calculated cost
        mock_cursor.execute.assert_any_call(
            mock.ANY, # SQL query string
            (
                123,          # user_id
                "req111",      # request_id
                "gemini",      # provider
                "gemini-3.1-flash-lite", # model
                "summarise",   # task
                10_000,        # prompt_tokens
                5_000,         # completion_tokens
                15_000,        # total_tokens
                0.0,           # duration_seconds
                cost           # cost_usd
            )
        )

@pytest.mark.asyncio
async def test_log_usage_safe_fail():
    mock_cursor = mock.AsyncMock(spec=psycopg.AsyncCursor)
    # Force exception inside cursor execution
    mock_cursor.execute.side_effect = Exception("DB connection lost")

    async with cost_tracking_context(chat_id="chat_fail", task="summarise"):
        # This should execute and complete without raising the DB exception
        cost = await CostManager.log_usage(
            provider="gemini",
            model="gemini-3.1-flash-lite",
            prompt_tokens=10_000,
            completion_tokens=5_000,
            cursor=mock_cursor
        )
        assert cost > 0  # Calculation should still succeed and return
