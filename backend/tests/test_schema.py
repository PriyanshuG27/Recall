import pytest
from datetime import datetime, date, timezone
from fastapi.testclient import TestClient
import importlib
import unittest.mock as mock

from backend.models.schemas import (
    ItemResponse,
    ItemCreateRequest,
    SearchRequest,
    SearchResultItem,
    SearchResponse,
    GraphNode,
    GraphEdge,
    GraphHub,
    GraphResponse,
    QuizResponse,
    QuizAnswerRequest,
    QuizStatsResponse,
    ReminderResponse,
    ReminderCreateRequest,
    ErrorResponse,
)

def test_pydantic_schemas_validation():
    # 1. ItemResponse (assert raw_text is not a field)
    assert "raw_text" not in ItemResponse.model_fields
    assert "embedding" not in ItemResponse.model_fields

    item_data = {
        "id": 1,
        "user_id": 42,
        "source_type": "url",
        "source_url": "https://neon.tech",
        "summary": "This is a summary of neon.tech.",
        "title": "Neon Serverless Postgres",
        "tags": ["postgres", "neon"],
        "created_at": datetime.now(timezone.utc)
    }
    item_model = ItemResponse(**item_data)
    assert item_model.id == 1
    assert item_model.tags == ["postgres", "neon"]

    # 2. SearchResponse
    search_data = {
        "results": [
            {
                "item": item_data,
                "score": 0.95
            }
        ]
    }
    search_model = SearchResponse(**search_data)
    assert len(search_model.results) == 1
    assert search_model.results[0].score == 0.95

    # 3. GraphResponse
    graph_data = {
        "nodes": [
            {"id": 1, "title": "Item 1", "source_type": "url", "created_at": "2026-06-25T00:00:00Z", "is_hub": True},
            {"id": 2, "title": "Item 2", "source_type": "pdf", "created_at": "2026-06-25T01:00:00Z", "is_hub": False}
        ],
        "edges": [
            {"source": 1, "target": 2, "weight": 0.88}
        ],
        "hubs": [
            {"id": 100, "label": "Tech Hub", "member_ids": [1]}
        ]
    }
    graph_model = GraphResponse(**graph_data)
    assert len(graph_model.nodes) == 2
    assert graph_model.edges[0].weight == 0.88
    assert len(graph_model.hubs) == 1
    assert graph_model.hubs[0].member_ids == [1]

    # 4. QuizResponse
    quiz_data = {
        "id": 10,
        "user_id": 42,
        "item_id": 1,
        "question": "What is Neon?",
        "options": ["Postgres", "Redis", "MongoDB", "MySQL"],
        "correct_index": 0,
        "explanation": "Neon is a serverless Postgres service.",
        "ease_factor": 2.5,
        "interval_days": 3,
        "next_review": date.today(),
        "created_at": datetime.now(timezone.utc)
    }
    quiz_model = QuizResponse(**quiz_data)
    assert quiz_model.id == 10
    assert quiz_model.correct_index == 0

    # 5. QuizStatsResponse
    stats_data = {
        "total_quizzes": 10,
        "due_today": 2,
        "completed_reviews": 5,
        "average_ease_factor": 2.6,
        "streak": 3
    }
    stats_model = QuizStatsResponse(**stats_data)
    assert stats_model.streak == 3

    # 6. ReminderResponse
    reminder_data = {
        "id": 5,
        "user_id": 42,
        "item_id": 1,
        "message": "Review Neon notes",
        "remind_at": datetime.now(timezone.utc),
        "status": "pending",
        "created_at": datetime.now(timezone.utc)
    }
    reminder_model = ReminderResponse(**reminder_data)
    assert reminder_model.id == 5
    assert reminder_model.status == "pending"

    # 7. ErrorResponse
    error_data = {
        "error": "unauthorized",
        "message": "Invalid JWT credentials."
    }
    error_model = ErrorResponse(**error_data)
    assert error_model.error == "unauthorized"


def test_openapi_json_endpoint():
    # Make sure we don't start the real connection pool
    with mock.patch("backend.db.connection.open_pool", return_value=None), \
         mock.patch("backend.db.connection.close_pool", return_value=None):
        from backend.main import app
        with TestClient(app) as client:
            resp = client.get("/openapi.json")
            assert resp.status_code == 200
            schema = resp.json()
            assert schema["openapi"].startswith("3.")
            assert "paths" in schema
            assert "/api/items" in schema["paths"]
            assert "/auth/telegram" in schema["paths"]


def test_docs_disabled_in_production(monkeypatch):
    # Set production env before reloading app
    monkeypatch.setenv("ENV", "production")
    
    # Reload config and main modules to pick up production environment
    import backend.config as config
    import backend.main as main
    
    importlib.reload(config)
    
    with mock.patch("backend.db.connection.open_pool", return_value=None), \
         mock.patch("backend.db.connection.close_pool", return_value=None):
        
        # Reload main so the application is built with docs_url=None
        importlib.reload(main)
        
        with TestClient(main.app) as client:
            resp = client.get("/docs")
            assert resp.status_code == 404
            
    # Reset config/main back to default test environment
    monkeypatch.setenv("ENV", "test")
    importlib.reload(config)
    importlib.reload(main)
