"""
backend/tests/test_health.py
==============================
Unit tests for the FastAPI app and /health endpoint.
"""

import pytest
from fastapi.testclient import TestClient


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


@pytest.fixture()
def client(monkeypatch):
    """
    TestClient with the DB pool open/close mocked out.
    This ensures /health tests don't require a real Neon DB connection.
    """
    import unittest.mock as mock

    # Mock pool open/close so lifespan doesn't try to connect to real DB
    with mock.patch("backend.db.connection.open_pool", return_value=None), \
         mock.patch("backend.db.connection.close_pool", return_value=None):

        from backend.main import app
        with TestClient(app) as c:
            yield c


def test_health_returns_200(client):
    """GET /health must return HTTP 200."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_response_schema(client):
    """GET /health must return {status, timestamp}."""
    response = client.get("/health")
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


def test_health_timestamp_is_iso(client):
    """Timestamp in /health must be a valid ISO 8601 string."""
    from datetime import datetime
    response = client.get("/health")
    ts = response.json()["timestamp"]
    # Should parse without raising
    dt = datetime.fromisoformat(ts)
    assert dt is not None
