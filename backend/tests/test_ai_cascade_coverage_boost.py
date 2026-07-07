import pytest
import unittest.mock as mock
import json
from backend.services.ai_cascade import AICascade

@pytest.mark.asyncio
async def test_ai_cascade_generate_context_question_prod():
    cascade = AICascade()
    cascade._force_production_llm = True
    
    with mock.patch("backend.services.ai_cascade.settings.GROQ_API_KEY", "mock_key"), \
         mock.patch.object(cascade, "_call_groq_llm", new_callable=mock.AsyncMock, return_value="What feature are you building?"):
        q = await cascade.generate_context_question("FastAPI Web App", "Building API routes")
        assert "building" in q.lower() or "what" in q.lower()

@pytest.mark.asyncio
async def test_ai_cascade_generate_insight_prod():
    cascade = AICascade()
    cascade._force_production_llm = True
    item_a = {"title": "FastAPI Guide", "summary": "Async python web framework", "tags": ["tech"]}
    item_b = {"title": "PostgreSQL Optimization", "summary": "Indexing and queries", "tags": ["db"]}

    from backend.services.ai_cascade.executor.retry import RetryEngine
    with mock.patch.object(RetryEngine, "execute_with_retry", new_callable=mock.AsyncMock, return_value="Insight: Combine FastAPI with Postgres indexing."):
        insight = await cascade.generate_insight(item_a, item_b, 5)
        assert insight is not None
        assert "FastAPI" in insight or "Postgres" in insight

@pytest.mark.asyncio
async def test_ai_cascade_generate_insight_no_genuine_tension():
    cascade = AICascade()
    cascade._force_production_llm = True
    item_a = {"title": "Sony WH-1000XM5 Headphone Review", "summary": "Noise cancelling headphones"}
    item_b = {"title": "Baking Sourdough Bread", "summary": "Flour and water recipe"}

    from backend.services.ai_cascade.executor.retry import RetryEngine
    with mock.patch.object(RetryEngine, "execute_with_retry", new_callable=mock.AsyncMock, return_value="NO_GENUINE_TENSION"):
        insight = await cascade.generate_insight(item_a, item_b, 10)
        assert insight is None

@pytest.mark.asyncio
async def test_ai_cascade_generate_quiz_prod():
    cascade = AICascade()
    cascade._force_production_llm = True
    text_content = "Python Asyncio event loops and coroutines for high throughput web development."

    mock_quiz_json = json.dumps({
        "question": "What is an event loop?",
        "options": ["A core execution mechanism", "A database table", "A CSS style", "A physical hardware component"],
        "correct_index": 0,
        "explanation": "Event loops schedule and execute asynchronous tasks."
    })

    from backend.services.ai_cascade.executor.retry import RetryEngine
    with mock.patch.object(RetryEngine, "execute_with_retry", new_callable=mock.AsyncMock, return_value=mock_quiz_json):
        quiz = await cascade.generate_quiz(text_content)
        assert isinstance(quiz, dict)
        assert quiz["question"] == "What is an event loop?"
